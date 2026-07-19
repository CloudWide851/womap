from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from functools import lru_cache
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis

from app.shared.config import get_settings
from app.shared.runtime_metrics import runtime_metrics


ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True)
class CacheLookup(Generic[ModelT]):
    value: ModelT | None
    hit: bool


class JsonCache(Protocol):
    async def get(self, logical_key: str, model: type[ModelT]) -> CacheLookup[ModelT]: ...

    async def set(self, logical_key: str, value: BaseModel) -> bool: ...


class NullCache:
    async def get(self, logical_key: str, model: type[ModelT]) -> CacheLookup[ModelT]:
        del logical_key, model
        return CacheLookup(value=None, hit=False)

    async def set(self, logical_key: str, value: BaseModel) -> bool:
        del logical_key, value
        return False


class RedisJsonCache:
    def __init__(
        self,
        client: Redis,
        *,
        namespace: str,
        ttl_seconds: int,
        max_entry_bytes: int,
        fail_open: bool = True,
        timeout_seconds: float = 2.0,
    ) -> None:
        self.client = client
        self.namespace = namespace
        self.ttl_seconds = ttl_seconds
        self.max_entry_bytes = max_entry_bytes
        self.fail_open = fail_open
        self.timeout_seconds = timeout_seconds

    def _key(self, logical_key: str) -> str:
        digest = hashlib.sha256(logical_key.encode("utf-8")).hexdigest()
        return f"{self.namespace}:{digest}"

    async def get(self, logical_key: str, model: type[ModelT]) -> CacheLookup[ModelT]:
        key = self._key(logical_key)
        try:
            async with asyncio.timeout(self.timeout_seconds):
                payload = await self.client.get(key)
            if payload is None:
                runtime_metrics.cache_event("miss")
                return CacheLookup(value=None, hit=False)
            if len(payload.encode("utf-8")) > self.max_entry_bytes:
                runtime_metrics.cache_event("oversize")
                await self._delete_corrupt(key)
                runtime_metrics.cache_event("miss")
                return CacheLookup(value=None, hit=False)
            try:
                value = model.model_validate_json(payload)
            except (ValidationError, ValueError, TypeError):
                runtime_metrics.cache_event("corruption")
                await self._delete_corrupt(key)
                runtime_metrics.cache_event("miss")
                return CacheLookup(value=None, hit=False)
            runtime_metrics.cache_event("hit")
            return CacheLookup(value=value, hit=True)
        except Exception:
            runtime_metrics.cache_event("error")
            runtime_metrics.cache_event("miss")
            if not self.fail_open:
                raise
            return CacheLookup(value=None, hit=False)

    async def set(self, logical_key: str, value: BaseModel) -> bool:
        payload = value.model_dump_json()
        if len(payload.encode("utf-8")) > self.max_entry_bytes:
            runtime_metrics.cache_event("oversize")
            return False
        try:
            async with asyncio.timeout(self.timeout_seconds):
                await self.client.set(self._key(logical_key), payload, ex=self.ttl_seconds)
            runtime_metrics.cache_event("write")
            return True
        except Exception:
            runtime_metrics.cache_event("error")
            if not self.fail_open:
                raise
            return False

    async def _delete_corrupt(self, key: str) -> None:
        try:
            async with asyncio.timeout(self.timeout_seconds):
                await self.client.delete(key)
        except Exception:
            runtime_metrics.cache_event("error")


@lru_cache
def get_performance_cache() -> JsonCache:
    settings = get_settings()
    cache = settings.performance.cache
    if not cache.enabled or not settings.redis.configured:
        return NullCache()
    return RedisJsonCache(
        Redis(**settings.redis.connection_kwargs()),
        namespace=cache.namespace,
        ttl_seconds=cache.ttl_seconds,
        max_entry_bytes=cache.max_entry_kib * 1024,
        fail_open=cache.fail_open,
    )


async def close_performance_cache() -> None:
    cache = get_performance_cache()
    if isinstance(cache, RedisJsonCache):
        try:
            await cache.client.aclose()
        except Exception:
            pass
    get_performance_cache.cache_clear()
