from __future__ import annotations

import math
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


@dataclass
class _PoolMetric:
    active: int = 0
    peak: int = 0
    checkouts: int = 0
    timeouts: int = 0
    waits_ms: deque[float] = field(default_factory=lambda: deque(maxlen=2048))


class RuntimeMetrics:
    """Small, process-local and bounded operational metric registry."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pools: dict[str, _PoolMetric] = {}
        self._cache = {
            "hit": 0,
            "miss": 0,
            "write": 0,
            "error": 0,
            "corruption": 0,
            "oversize": 0,
        }
        self._range_requests = 0
        self._range_bytes = 0
        self._range_statuses: dict[int, int] = {}

    def pool_checkout(self, pool: str) -> None:
        with self._lock:
            metric = self._pools.setdefault(pool, _PoolMetric())
            metric.active += 1
            metric.peak = max(metric.peak, metric.active)
            metric.checkouts += 1

    def pool_checkin(self, pool: str) -> None:
        with self._lock:
            metric = self._pools.setdefault(pool, _PoolMetric())
            metric.active = max(0, metric.active - 1)

    def pool_acquire(self, pool: str, wait_ms: float) -> None:
        with self._lock:
            self._pools.setdefault(pool, _PoolMetric()).waits_ms.append(max(0.0, wait_ms))

    def pool_timeout(self, pool: str) -> None:
        with self._lock:
            self._pools.setdefault(pool, _PoolMetric()).timeouts += 1

    def cache_event(self, event: str) -> None:
        if event not in self._cache:
            raise ValueError(f"unknown cache metric: {event}")
        with self._lock:
            self._cache[event] += 1

    def range_response(self, status_code: int, byte_count: int) -> None:
        with self._lock:
            self._range_requests += 1
            self._range_bytes += max(0, byte_count)
            self._range_statuses[status_code] = self._range_statuses.get(status_code, 0) + 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            pools: dict[str, dict[str, int | float]] = {}
            for name, metric in self._pools.items():
                waits = list(metric.waits_ms)
                pools[name] = {
                    "active": metric.active,
                    "peak": metric.peak,
                    "checkouts": metric.checkouts,
                    "timeouts": metric.timeouts,
                    "samples": len(waits),
                    "wait_p50_ms": round(_percentile(waits, 0.50), 3),
                    "wait_p95_ms": round(_percentile(waits, 0.95), 3),
                    "wait_max_ms": round(max(waits, default=0.0), 3),
                }
            cache = dict(self._cache)
            lookups = cache["hit"] + cache["miss"]
            cache["hit_rate"] = round(cache["hit"] / lookups, 4) if lookups else 0.0
            return {
                "database_pools": pools,
                "cache": cache,
                "range": {
                    "requests": self._range_requests,
                    "bytes": self._range_bytes,
                    "statuses": {str(key): value for key, value in self._range_statuses.items()},
                },
            }

    def reset(self) -> None:
        with self._lock:
            self._pools.clear()
            for key in self._cache:
                self._cache[key] = 0
            self._range_requests = 0
            self._range_bytes = 0
            self._range_statuses.clear()


runtime_metrics = RuntimeMetrics()
