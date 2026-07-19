from __future__ import annotations

import os

from app.shared.config import ResolvedPerformanceSettings, Settings, get_settings
from app.shared.system_resources import detect_memory_bytes


def resolve_runtime_performance(settings: Settings | None = None) -> ResolvedPerformanceSettings:
    active = settings or get_settings()
    total_memory_bytes, _ = detect_memory_bytes()
    return active.performance.resolve(
        logical_cpu_count=os.cpu_count(),
        total_memory_bytes=total_memory_bytes,
    )
