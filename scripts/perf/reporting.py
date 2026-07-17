from __future__ import annotations

import json
import math
import platform
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPORT_SCHEMA_VERSION = "womap.performance-report/v1"
_SENSITIVE_KEY = re.compile(r"password|secret|token|cookie|session|api[_-]?key", re.IGNORECASE)
_PATH_VALUE = re.compile(r"(?:[A-Za-z]:\\|/(?:home|users?|var|tmp)/)", re.IGNORECASE)
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?:password|secret|token|cookie|session|api[_-]?key)[\"']?\s*[:=]\s*\S+",
    re.IGNORECASE,
)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def percentile(values: Iterable[float], quantile: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, quantile)) * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def duration_summary(durations_seconds: Iterable[float], elapsed_seconds: float) -> dict[str, Any]:
    values = [max(0.0, float(value)) for value in durations_seconds]
    return {
        "count": len(values),
        "p50_ms": round(percentile(values, 0.50) * 1000, 3),
        "p95_ms": round(percentile(values, 0.95) * 1000, 3),
        "p99_ms": round(percentile(values, 0.99) * 1000, 3),
        "min_ms": round(min(values, default=0.0) * 1000, 3),
        "max_ms": round(max(values, default=0.0) * 1000, 3),
        "throughput_rps": round(len(values) / max(elapsed_seconds, 1e-9), 3),
    }


def environment_manifest(*, profile: str, dataset_tier: str) -> dict[str, Any]:
    return {
        "platform": _platform_kind(),
        "release": _safe_text(platform.release(), 80),
        "architecture": _safe_text(platform.machine(), 40),
        "python": platform.python_version(),
        "commit": _git_commit(),
        "profile": profile,
        "dataset_tier": dataset_tier,
    }


def build_report(
    *,
    kind: str,
    profile: str,
    dataset_tier: str,
    workload: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    return redact_report(
        {
            "schema_version": REPORT_SCHEMA_VERSION,
            "kind": kind,
            "created_at": utc_timestamp(),
            "environment": environment_manifest(profile=profile, dataset_tier=dataset_tier),
            "workload": workload,
            "metrics": metrics,
        }
    )


def validate_report(report: object) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise ValueError("performance report must be a JSON object")
    if report.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise ValueError("unsupported performance report schema")
    for key in ("kind", "created_at", "environment", "workload", "metrics"):
        if key not in report:
            raise ValueError(f"performance report is missing {key}")
    return report


def write_report(path: Path, report: dict[str, Any]) -> None:
    validate_report(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(redact_report(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def read_report(path: Path) -> dict[str, Any]:
    return validate_report(json.loads(path.read_text(encoding="utf-8")))


def redact_report(value: Any, *, key: str = "") -> Any:
    if _SENSITIVE_KEY.search(key):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(item_key): redact_report(item_value, key=str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact_report(item, key=key) for item in value]
    if isinstance(value, tuple):
        return [redact_report(item, key=key) for item in value]
    if isinstance(value, str):
        if _PATH_VALUE.search(value) or _SENSITIVE_ASSIGNMENT.search(value):
            return "[redacted]"
        return "".join(character for character in value if character.isprintable())[:1000]
    return value


def _git_commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return "unknown"
    commit = completed.stdout.strip()
    return commit if completed.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", commit) else "unknown"


def _platform_kind() -> str:
    if platform.system().casefold() == "windows":
        return "windows"
    if platform.system().casefold() == "linux":
        return "linux"
    return "other"


def _safe_text(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    return normalized[:limit] or "unknown"
