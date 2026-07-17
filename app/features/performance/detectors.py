from __future__ import annotations

import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from importlib import metadata
from pathlib import Path
from typing import Any

from app.features.performance.schemas import (
    CpuCapability,
    GpuCapability,
    MemoryCapability,
    SoftwareCapability,
    StorageCapability,
    SystemCapability,
)


CommandRunner = Callable[[Sequence[str], float], str | None]
_WINDOWS_HARDWARE_COMMAND = (
    "$cpu=Get-CimInstance Win32_Processor | Select-Object -First 1;"
    "$os=Get-CimInstance Win32_OperatingSystem;"
    "[pscustomobject]@{cpu_name=$cpu.Name;physical_cores=$cpu.NumberOfCores;"
    "total_memory=[int64]$os.TotalVisibleMemorySize*1024;"
    "available_memory=[int64]$os.FreePhysicalMemory*1024} | ConvertTo-Json -Compress"
)
_WINDOWS_GPU_COMMAND = (
    "Get-CimInstance Win32_VideoController | "
    "Select-Object Name,DriverVersion,AdapterRAM | ConvertTo-Json -Compress"
)
_PATH_PATTERN = re.compile(r"(?:[A-Za-z]:\\|/(?:home|users?|var|tmp)/)", re.IGNORECASE)


def _safe_text(value: object, *, limit: int = 160) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text or _PATH_PATTERN.search(text):
        return None
    return "".join(character for character in text if character.isprintable())[:limit]


def run_fixed_command(arguments: Sequence[str], timeout_seconds: float) -> str | None:
    creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        completed = subprocess.run(
            list(arguments),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            errors="replace",
            creationflags=creation_flags,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout[:65536]


class CapabilityDetector:
    def __init__(
        self,
        *,
        command_runner: CommandRunner = run_fixed_command,
        platform_name: str | None = None,
    ) -> None:
        self.command_runner = command_runner
        self.platform_name = (platform_name or sys.platform).lower()

    def detect_system(self, storage_path: Path) -> SystemCapability:
        platform_kind = self._platform_kind()
        logical_cores = max(1, os.cpu_count() or 1)
        physical_cores: int | None = None
        cpu_model = _safe_text(platform.processor())
        total_memory: int | None = None
        available_memory: int | None = None

        if platform_kind == "windows":
            host = self._windows_host()
            physical_cores = self._positive_int(host.get("physical_cores"))
            cpu_model = _safe_text(host.get("cpu_name")) or cpu_model
            total_memory = self._positive_int(host.get("total_memory"))
            available_memory = self._positive_int(host.get("available_memory"))
            if physical_cores is None:
                physical_cores = self._windows_physical_cores_native()
            if total_memory is None:
                total_memory, available_memory = self._windows_memory_native()
            cpu_model = cpu_model or _safe_text(os.environ.get("PROCESSOR_IDENTIFIER"))
        elif platform_kind == "linux":
            linux_host = self._linux_host()
            physical_cores = linux_host["physical_cores"]
            cpu_model = linux_host["cpu_model"] or cpu_model
            total_memory = linux_host["total_memory"]
            available_memory = linux_host["available_memory"]

        if total_memory is None:
            total_memory, available_memory = self._portable_memory()

        return SystemCapability(
            platform=platform_kind,
            release=_safe_text(platform.release(), limit=80) or "unknown",
            architecture=_safe_text(platform.machine(), limit=40) or "unknown",
            cpu=CpuCapability(
                logical_cores=logical_cores,
                physical_cores=physical_cores,
                model=cpu_model,
            ),
            memory=MemoryCapability(
                total_bytes=total_memory,
                available_bytes=available_memory,
            ),
            storage=self._storage(storage_path),
        )

    def detect_gpus(self) -> list[GpuCapability]:
        if self._platform_kind() == "windows":
            gpus = self._windows_gpus()
        else:
            gpus = self._linux_gpus()
        nvidia_gpus = self._nvidia_gpus()
        if not nvidia_gpus:
            return gpus
        return [*nvidia_gpus, *(gpu for gpu in gpus if gpu.vendor != "nvidia")]

    @staticmethod
    def detect_local_software() -> dict[str, SoftwareCapability]:
        python = SoftwareCapability(status="available", version=platform.python_version())
        try:
            import rasterio

            rasterio_capability = SoftwareCapability(
                status="available", version=_safe_text(rasterio.__version__, limit=40)
            )
            gdal_capability = SoftwareCapability(
                status="available", version=_safe_text(rasterio.__gdal_version__, limit=40)
            )
        except (ImportError, OSError):
            rasterio_capability = SoftwareCapability(status="unavailable")
            gdal_capability = SoftwareCapability(status="unavailable")

        cupy_version: str | None = None
        cupy_available = importlib.util.find_spec("cupy") is not None
        if cupy_available:
            for distribution in ("cupy", "cupy-cuda12x", "cupy-cuda11x"):
                try:
                    cupy_version = metadata.version(distribution)
                    break
                except metadata.PackageNotFoundError:
                    continue
        cupy = SoftwareCapability(
            status="available" if cupy_available else "unavailable",
            version=_safe_text(cupy_version, limit=40),
        )
        return {
            "python": python,
            "rasterio": rasterio_capability,
            "gdal": gdal_capability,
            "cupy": cupy,
        }

    def _platform_kind(self) -> str:
        if self.platform_name.startswith("win"):
            return "windows"
        if self.platform_name.startswith("linux"):
            return "linux"
        return "other"

    def _windows_host(self) -> dict[str, Any]:
        output = self.command_runner(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                _WINDOWS_HARDWARE_COMMAND,
            ],
            3.0,
        )
        parsed = self._parse_json(output)
        return parsed if isinstance(parsed, dict) else {}

    def _windows_gpus(self) -> list[GpuCapability]:
        output = self.command_runner(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                _WINDOWS_GPU_COMMAND,
            ],
            3.0,
        )
        parsed = self._parse_json(output)
        items = parsed if isinstance(parsed, list) else [parsed] if isinstance(parsed, dict) else []
        gpus: list[GpuCapability] = []
        for item in items:
            name = _safe_text(item.get("Name"))
            if not name:
                continue
            adapter_bytes = self._positive_int(item.get("AdapterRAM"))
            gpus.append(
                GpuCapability(
                    vendor=self._gpu_vendor(name),
                    name=name,
                    driver=_safe_text(item.get("DriverVersion"), limit=80),
                    memory_mib=adapter_bytes // (1024**2) if adapter_bytes else None,
                )
            )
        return gpus

    def _linux_gpus(self) -> list[GpuCapability]:
        output = self.command_runner(["lspci", "-mm"], 2.0)
        if not output:
            return []
        gpus: list[GpuCapability] = []
        for line in output.splitlines():
            if "VGA compatible controller" not in line and "3D controller" not in line:
                continue
            name = _safe_text(line, limit=120)
            if name:
                gpus.append(GpuCapability(vendor=self._gpu_vendor(name), name=name))
        return gpus

    def _nvidia_gpus(self) -> list[GpuCapability]:
        output = self.command_runner(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total,compute_cap",
                "--format=csv,noheader,nounits",
            ],
            2.0,
        )
        if not output:
            return []
        gpus: list[GpuCapability] = []
        for line in output.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 3:
                continue
            name = _safe_text(parts[0])
            if not name:
                continue
            gpus.append(
                GpuCapability(
                    vendor="nvidia",
                    name=name,
                    driver=_safe_text(parts[1], limit=80),
                    memory_mib=self._positive_int(parts[2]),
                    compute_capability=_safe_text(parts[3], limit=20) if len(parts) > 3 else None,
                )
            )
        return gpus

    @staticmethod
    def _linux_host() -> dict[str, Any]:
        result: dict[str, Any] = {
            "physical_cores": None,
            "cpu_model": None,
            "total_memory": None,
            "available_memory": None,
        }
        try:
            cpu_text = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace")
            core_pairs: set[tuple[str, str]] = set()
            current: dict[str, str] = {}
            for line in [*cpu_text.splitlines(), ""]:
                if not line.strip():
                    if current.get("physical id") is not None and current.get("core id") is not None:
                        core_pairs.add((current["physical id"], current["core id"]))
                    if result["cpu_model"] is None:
                        result["cpu_model"] = _safe_text(current.get("model name"))
                    current = {}
                elif ":" in line:
                    key, value = line.split(":", maxsplit=1)
                    current[key.strip()] = value.strip()
            result["physical_cores"] = len(core_pairs) or None
        except OSError:
            pass
        try:
            memory: dict[str, int] = {}
            for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
                key, value = line.split(":", maxsplit=1)
                memory[key] = int(value.strip().split()[0]) * 1024
            result["total_memory"] = memory.get("MemTotal")
            result["available_memory"] = memory.get("MemAvailable")
        except (OSError, ValueError, IndexError):
            pass
        return result

    @staticmethod
    def _portable_memory() -> tuple[int | None, int | None]:
        try:
            page_size = os.sysconf("SC_PAGE_SIZE")
            total_pages = os.sysconf("SC_PHYS_PAGES")
            available_pages = os.sysconf("SC_AVPHYS_PAGES")
            return page_size * total_pages, page_size * available_pages
        except (AttributeError, OSError, ValueError):
            return None, None

    @staticmethod
    def _windows_memory_native() -> tuple[int | None, int | None]:
        try:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_physical", ctypes.c_ulonglong),
                    ("available_physical", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("available_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended_virtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(MemoryStatus)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None, None
            return int(status.total_physical), int(status.available_physical)
        except (AttributeError, OSError, TypeError, ValueError):
            return None, None

    @staticmethod
    def _windows_physical_cores_native() -> int | None:
        try:
            import ctypes

            required_bytes = ctypes.c_ulong(0)
            kernel32 = ctypes.windll.kernel32
            kernel32.GetLogicalProcessorInformationEx(0, None, ctypes.byref(required_bytes))
            if required_bytes.value <= 0 or required_bytes.value > 16 * 1024 * 1024:
                return None
            buffer = ctypes.create_string_buffer(required_bytes.value)
            if not kernel32.GetLogicalProcessorInformationEx(
                0,
                ctypes.byref(buffer),
                ctypes.byref(required_bytes),
            ):
                return None
            offset = 0
            physical_cores = 0
            while offset + 8 <= required_bytes.value:
                relationship = ctypes.c_int.from_buffer(buffer, offset).value
                record_size = ctypes.c_ulong.from_buffer(buffer, offset + 4).value
                if record_size < 8 or offset + record_size > required_bytes.value:
                    return None
                if relationship == 0:
                    physical_cores += 1
                offset += record_size
            return physical_cores or None
        except (AttributeError, OSError, TypeError, ValueError):
            return None

    @staticmethod
    def _storage(path: Path) -> StorageCapability:
        candidate = path.expanduser()
        while not candidate.exists() and candidate != candidate.parent:
            candidate = candidate.parent
        try:
            usage = shutil.disk_usage(candidate)
        except OSError:
            return StorageCapability(status="unknown")
        return StorageCapability(status="available", free_bytes=usage.free, kind="unknown")

    @staticmethod
    def _positive_int(value: object) -> int | None:
        try:
            parsed = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError, OverflowError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _parse_json(output: str | None) -> object:
        if not output:
            return None
        try:
            return json.loads(output.strip())
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _gpu_vendor(name: str) -> str:
        normalized = name.casefold()
        if "nvidia" in normalized:
            return "nvidia"
        if "amd" in normalized or "radeon" in normalized:
            return "amd"
        if "intel" in normalized:
            return "intel"
        if "microsoft" in normalized:
            return "microsoft"
        return "other"
