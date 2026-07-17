from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event
from typing import Iterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job


class JobLeaseLost(RuntimeError):
    pass


class JobCancellationRequested(RuntimeError):
    pass


_WINDOWS_PATH = re.compile(r"(?i)(?:[a-z]:[\\/]|\\\\)[^\s,;\"']+")
_POSIX_PATH = re.compile(r"(?<![A-Za-z0-9])/(?:[^/\s]+/)*[^\s,;:\"']+")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|token|secret|api[_-]?key|cookie|session(?:_id)?)\s*=\s*[^\s,;]+"
)


@dataclass(frozen=True)
class JobExecutionState:
    owner_hash: str
    stop_event: Event


_EXECUTION_STATE: ContextVar[JobExecutionState | None] = ContextVar(
    "womap_job_execution_state", default=None
)


@contextmanager
def job_execution(state: JobExecutionState) -> Iterator[None]:
    token = _EXECUTION_STATE.set(state)
    try:
        yield
    finally:
        _EXECUTION_STATE.reset(token)


async def assert_job_execution(session: AsyncSession, job: Job) -> None:
    state = _EXECUTION_STATE.get()
    if state is None:
        return
    current = datetime.now(timezone.utc)
    row = (
        await session.execute(
            select(
                Job.lease_owner_hash,
                Job.status,
                Job.cancel_requested_at,
            )
            .where(
                Job.id == job.id,
                Job.lease_expires_at > current,
            )
            .with_for_update()
        )
    ).one_or_none()
    if row is None or row.lease_owner_hash != state.owner_hash or row.status != "running":
        raise JobLeaseLost("任务租约已失效。")
    if row.cancel_requested_at is not None or state.stop_event.is_set():
        raise JobCancellationRequested("任务已请求中断。")


def apply_job_lifecycle(job: Job, status: str | None) -> None:
    if status is None:
        return
    now = datetime.now(timezone.utc)
    if status == "running" and job.started_at is None:
        job.started_at = now
    if status in {"done", "failed", "interrupted"}:
        job.finished_at = now
        job.lease_owner_hash = None
        job.lease_expires_at = None
        job.heartbeat_at = None
    elif status == "queued":
        job.finished_at = None
        job.lease_owner_hash = None
        job.lease_expires_at = None
        job.heartbeat_at = None
        job.cancel_requested_at = None


def sanitize_job_error(exc: BaseException, *, fallback: str = "任务处理失败。") -> str:
    """Keep actionable diagnostics while removing paths and common secret assignments."""
    message = str(exc).strip()
    if not message:
        return fallback
    message = _WINDOWS_PATH.sub("<路径>", message)
    message = _POSIX_PATH.sub("<路径>", message)
    message = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[redacted]", message)
    return message[:400]
