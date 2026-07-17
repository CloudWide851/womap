from __future__ import annotations

import argparse
import asyncio
import json

from app.features.performance.service import PerformanceService


def _gib(value: int | None) -> str:
    return "unknown" if value is None else f"{value / (1024**3):.1f} GiB"


async def _report(as_json: bool) -> int:
    report = await PerformanceService().get_capabilities()
    if as_json:
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return 0

    profile = report.runtime.profile
    print("Performance capability")
    print(
        f"  Profile: {profile.requested_profile} -> {profile.resolved_profile} "
        f"({profile.enforcement})"
    )
    print(
        f"  CPU: {report.system.cpu.logical_cores} logical; "
        f"memory total {_gib(report.system.memory.total_bytes)}, "
        f"available {_gib(report.system.memory.available_bytes)}"
    )
    if report.gpus:
        print("  GPU: " + "; ".join(f"{gpu.vendor} {gpu.name}" for gpu in report.gpus))
    else:
        print("  GPU: not detected")
    print(
        f"  Web render: browser WebGL probe; native compute: "
        f"disabled ({report.runtime.gpu_execution_reason})"
    )
    print(
        f"  GDAL threads/cache: {profile.gdal_threads} / {profile.gdal_cache_mib} MiB "
        "(diagnostic budget)"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Print a redacted WOMAP capability summary.")
    parser.add_argument("--json", action="store_true", help="Emit the safe response schema as JSON.")
    arguments = parser.parse_args()
    return asyncio.run(_report(arguments.json))


if __name__ == "__main__":
    raise SystemExit(main())
