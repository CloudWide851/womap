from __future__ import annotations

import hashlib
import platform
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.features.performance.detectors import run_fixed_command


CommandRunner = Callable[[Sequence[str], float], str | None]


@dataclass(frozen=True)
class SystemStateSnapshot:
    platform: str
    fingerprints: dict[str, str]
    observed: dict[str, bool]


def capture_system_state(
    *,
    platform_name: str | None = None,
    command_runner: CommandRunner = run_fixed_command,
    sys_block_root: Path = Path("/sys/block"),
) -> SystemStateSnapshot:
    system = (platform_name or platform.system()).casefold()
    if system.startswith("win"):
        values = _capture_windows(command_runner)
        platform_kind = "windows"
    elif system.startswith("linux"):
        values = _capture_linux(command_runner, sys_block_root)
        platform_kind = "linux"
    else:
        values = {"platform_state": None}
        platform_kind = "other"
    return SystemStateSnapshot(
        platform=platform_kind,
        fingerprints={key: _fingerprint(value) for key, value in sorted(values.items())},
        observed={key: value is not None for key, value in sorted(values.items())},
    )


def compare_system_state(
    before: SystemStateSnapshot,
    after: SystemStateSnapshot,
) -> dict[str, object]:
    keys = sorted(set(before.fingerprints) | set(after.fingerprints))
    unchanged = {
        key: (
            before.observed.get(key) is True
            and after.observed.get(key) is True
            and before.fingerprints.get(key) == after.fingerprints.get(key)
        )
        for key in keys
    }
    same_platform = before.platform == after.platform
    return {
        "platform": before.platform if same_platform else "changed",
        "unchanged": unchanged,
        "all_unchanged": same_platform and all(unchanged.values()),
    }


def _capture_windows(command_runner: CommandRunner) -> dict[str, str | None]:
    return {
        "power": command_runner(["powercfg.exe", "/GETACTIVESCHEME"], 3.0),
        "application_gpu_preference": command_runner(
            [
                "reg.exe",
                "query",
                r"HKCU\Software\Microsoft\DirectX\UserGpuPreferences",
            ],
            3.0,
        ),
        "defender_exclusions": command_runner(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "Get-MpPreference | Select-Object ExclusionPath,ExclusionProcess,ExclusionExtension | ConvertTo-Json -Compress",
            ],
            10.0,
        ),
        "page_file": command_runner(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "$c=Get-CimInstance Win32_ComputerSystem;"
                "$p=Get-CimInstance Win32_PageFileSetting;"
                "[pscustomobject]@{automatic=$c.AutomaticManagedPagefile;settings=$p} | ConvertTo-Json -Compress -Depth 3",
            ],
            5.0,
        ),
    }


def _capture_linux(
    command_runner: CommandRunner,
    sys_block_root: Path,
) -> dict[str, str | None]:
    schedulers: list[str] = []
    try:
        for scheduler in sorted(sys_block_root.glob("*/queue/scheduler")):
            schedulers.append(
                f"{scheduler.parents[1].name}:{scheduler.read_text(encoding='ascii', errors='replace').strip()}"
            )
    except OSError:
        schedulers = []
    return {
        "power": command_runner(["powerprofilesctl", "get"], 3.0),
        "sysctl": command_runner(
            [
                "sysctl",
                "-n",
                "vm.swappiness",
                "vm.dirty_ratio",
                "vm.dirty_background_ratio",
            ],
            3.0,
        ),
        "io_scheduler": "\n".join(schedulers) if schedulers else None,
    }


def _fingerprint(value: str | None) -> str:
    normalized = " ".join((value or "[unavailable]").split())
    return hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()
