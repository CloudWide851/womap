from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    from _bootstrap import ensure_repo_root

    ensure_repo_root()

from scripts.perf.reporting import build_report, write_report


@dataclass(frozen=True)
class NativeProcessSample:
    timestamp_seconds: float
    cpu_seconds: float
    rss_bytes: int
    thread_count: int
    handle_count: int | None
    read_bytes: int | None
    write_bytes: int | None


def sample_process(pid: int) -> NativeProcessSample | None:
    if platform.system().casefold() == "windows":
        return _sample_windows(pid)
    if platform.system().casefold() == "linux":
        return _sample_linux(pid)
    return None


def sample_series(pid: int, duration_seconds: float, interval_seconds: float) -> list[dict[str, Any]]:
    started = time.monotonic()
    deadline = started + duration_seconds
    previous: NativeProcessSample | None = None
    samples: list[dict[str, Any]] = []
    while True:
        sample = sample_process(pid)
        if sample is None:
            break
        cpu_percent: float | None = None
        if previous is not None:
            elapsed = sample.timestamp_seconds - previous.timestamp_seconds
            cpu_elapsed = sample.cpu_seconds - previous.cpu_seconds
            if elapsed > 0:
                cpu_percent = max(0.0, cpu_elapsed / elapsed * 100 / max(1, os.cpu_count() or 1))
        samples.append(
            {
                "offset_seconds": round(sample.timestamp_seconds - started, 3),
                "cpu_percent_total_capacity": round(cpu_percent, 3) if cpu_percent is not None else None,
                "rss_bytes": sample.rss_bytes,
                "thread_count": sample.thread_count,
                "handle_count": sample.handle_count,
                "read_bytes": sample.read_bytes,
                "write_bytes": sample.write_bytes,
            }
        )
        previous = sample
        if time.monotonic() >= deadline:
            break
        time.sleep(min(interval_seconds, max(0.0, deadline - time.monotonic())))
    return samples


def _sample_windows(pid: int) -> NativeProcessSample | None:
    command = (
        f"$p=Get-Process -Id {pid} -ErrorAction Stop;"
        "[pscustomobject]@{cpu_seconds=$p.CPU;rss_bytes=$p.WorkingSet64;"
        "thread_count=$p.Threads.Count;handle_count=$p.HandleCount;"
        "read_bytes=$p.IOReadBytes;write_bytes=$p.IOWriteBytes} | ConvertTo-Json -Compress"
    )
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout)
        return NativeProcessSample(
            timestamp_seconds=time.monotonic(),
            cpu_seconds=float(payload.get("cpu_seconds") or 0),
            rss_bytes=int(payload.get("rss_bytes") or 0),
            thread_count=int(payload.get("thread_count") or 0),
            handle_count=_optional_int(payload.get("handle_count")),
            read_bytes=_optional_int(payload.get("read_bytes")),
            write_bytes=_optional_int(payload.get("write_bytes")),
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _sample_linux(pid: int) -> NativeProcessSample | None:
    process_root = Path("/proc") / str(pid)
    try:
        stat_line = (process_root / "stat").read_text(encoding="ascii")
        closing_parenthesis = stat_line.rfind(")")
        fields = stat_line[closing_parenthesis + 2 :].split()
        clock_ticks = os.sysconf("SC_CLK_TCK")
        cpu_seconds = (int(fields[11]) + int(fields[12])) / clock_ticks
        thread_count = int(fields[17])
        resident_pages = int((process_root / "statm").read_text(encoding="ascii").split()[1])
        rss_bytes = resident_pages * os.sysconf("SC_PAGE_SIZE")
        io_values = _linux_io(process_root / "io")
        handle_count = sum(1 for _ in (process_root / "fd").iterdir())
    except (OSError, ValueError, IndexError):
        return None
    return NativeProcessSample(
        timestamp_seconds=time.monotonic(),
        cpu_seconds=cpu_seconds,
        rss_bytes=rss_bytes,
        thread_count=thread_count,
        handle_count=handle_count,
        read_bytes=io_values.get("read_bytes"),
        write_bytes=io_values.get("write_bytes"),
    )


def _linux_io(path: Path) -> dict[str, int]:
    try:
        return {
            key: int(value.strip())
            for key, value in (line.split(":", maxsplit=1) for line in path.read_text().splitlines())
            if key in {"read_bytes", "write_bytes"}
        }
    except (OSError, ValueError):
        return {}


def _optional_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Sample a process with native Windows/Linux APIs.")
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--duration-seconds", type=float, default=30.0)
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    parser.add_argument("--profile", choices=("ci-small", "workstation-medium"), default="ci-small")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".womap-data/perf/reports/process-samples.json"),
    )
    arguments = parser.parse_args()
    if arguments.pid < 1:
        parser.error("pid must be positive")
    if not 0.1 <= arguments.duration_seconds <= 3600:
        parser.error("duration must be between 0.1 and 3600 seconds")
    if not 0.1 <= arguments.interval_seconds <= 60:
        parser.error("interval must be between 0.1 and 60 seconds")
    samples = sample_series(arguments.pid, arguments.duration_seconds, arguments.interval_seconds)
    report = build_report(
        kind="process-samples",
        profile=arguments.profile,
        dataset_tier=arguments.profile,
        workload={
            "sample_count": len(samples),
            "duration_seconds": arguments.duration_seconds,
            "interval_seconds": arguments.interval_seconds,
        },
        metrics={"samples": samples},
    )
    write_report(arguments.output, report)
    print(f"Native process sampling completed with {len(samples)} sample(s).")
    return 0 if samples else 1


if __name__ == "__main__":
    raise SystemExit(main())
