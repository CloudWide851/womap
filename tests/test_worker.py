from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.features.imports.repository import ImportRepository
from app.features.imports.service import ImportService
from app.features.jobs.execution import (
    JobExecutionState,
    JobLeaseLost,
    assert_job_execution,
    job_execution,
    sanitize_job_error,
)
from app.features.jobs.policies import new_job_runtime_fields
from app.features.jobs.queue_repository import JobQueueRepository
from app.features.jobs.repository import JobRepository
from app.features.jobs.schemas import JobProgressDetail, SpatialAnalysisJobProgressDetail
from app.features.jobs.worker import apply_process_priority
from app.features.spatial_analyses.repository import SpatialAnalysisRepository
from app.models.job import Job
from app.shared.config import get_settings
from app.shared.config import PerformanceWorkerSettings


def _utc(hour: int = 12, minute: int = 0) -> datetime:
    return datetime(2026, 7, 18, hour, minute, tzinfo=timezone.utc)


def _job(
    job_id: str,
    job_type: str = "spatial-analysis",
    *,
    status: str = "queued",
    created_at: datetime | None = None,
    available_at: datetime | None = None,
    attempt_count: int = 0,
    max_attempts: int | None = None,
) -> Job:
    runtime = (
        new_job_runtime_fields(job_type)
        if job_type != "unknown-job"
        else {"priority": 100, "resource_class": "cpu-io", "max_attempts": 2}
    )
    if max_attempts is not None:
        runtime["max_attempts"] = max_attempts
    detail = (
        JobProgressDetail().model_dump()
        if job_type.startswith("import-")
        else SpatialAnalysisJobProgressDetail().model_dump()
    )
    return Job(
        id=job_id,
        job_type=job_type,
        status=status,
        progress=0,
        message="test job",
        payload={"source_id": "source-1", "dataset_ids": ["dataset-1"]},
        result={"detail": detail},
        created_at=created_at or _utc(),
        updated_at=created_at or _utc(),
        available_at=available_at or _utc(),
        attempt_count=attempt_count,
        **runtime,
    )


@pytest_asyncio.fixture
async def sqlite_sessions(
    tmp_path: Path,
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'worker.sqlite3').as_posix()}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(Job.__table__.create)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def postgresql_worker_sessions(
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    url = get_settings().database.sqlalchemy_url().set(host="127.0.0.1")
    admin_engine = create_async_engine(
        url,
        pool_pre_ping=True,
        connect_args={"ssl": False},
    )
    schema = f"womap_worker_{uuid4().hex}"
    async with admin_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url,
        pool_pre_ping=True,
        connect_args={
            "server_settings": {"search_path": f"{schema},public"},
            "ssl": False,
        },
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Job.__table__.create)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin_engine.dispose()


@pytest.mark.asyncio
async def test_claim_preserves_fifo_and_skips_delayed_jobs(
    sqlite_sessions: async_sessionmaker[AsyncSession],
) -> None:
    now = _utc()
    async with sqlite_sessions() as session:
        delayed = _job("delayed", available_at=now + timedelta(minutes=1))
        first = _job("first", created_at=now - timedelta(seconds=2))
        second = _job("second", created_at=now - timedelta(seconds=1))
        session.add_all([delayed, second, first])
        await session.commit()

    async with sqlite_sessions() as session:
        claimed = await JobQueueRepository(session).claim_next("owner-a", 120, now=now)

    assert claimed is not None
    assert claimed.id == "first"
    assert claimed.attempt_count == 1
    assert claimed.lease_owner_hash == "owner-a"


@pytest.mark.asyncio
async def test_two_postgresql_workers_claim_one_job_only_once(
    postgresql_worker_sessions: async_sessionmaker[AsyncSession],
) -> None:
    now = _utc()
    async with postgresql_worker_sessions() as session:
        session.add(_job("shared"))
        await session.commit()

    async def claim(owner: str) -> Job | None:
        async with postgresql_worker_sessions() as session:
            return await JobQueueRepository(session).claim_next(owner, 120, now=now)

    claimed = await asyncio.gather(claim("owner-a"), claim("owner-b"))

    assert sum(job is not None for job in claimed) == 1
    async with postgresql_worker_sessions() as session:
        stored = await session.get(Job, "shared")
        assert stored is not None
        assert stored.status == "running"
        assert stored.attempt_count == 1


@pytest.mark.asyncio
async def test_heartbeat_requires_live_owner_and_unexpired_lease(
    sqlite_sessions: async_sessionmaker[AsyncSession],
) -> None:
    now = _utc()
    async with sqlite_sessions() as session:
        session.add(_job("heartbeat"))
        await session.commit()
    async with sqlite_sessions() as session:
        repository = JobQueueRepository(session)
        claimed = await repository.claim_next("owner-a", 60, now=now)
        assert claimed is not None
        assert await repository.heartbeat(
            "heartbeat", "owner-a", 60, now=now + timedelta(seconds=20)
        )
        assert not await repository.heartbeat(
            "heartbeat", "owner-b", 60, now=now + timedelta(seconds=30)
        )
        assert not await repository.heartbeat(
            "heartbeat", "owner-a", 60, now=now + timedelta(seconds=81)
        )


@pytest.mark.asyncio
async def test_expired_lease_retries_safe_job_and_interrupts_import(
    sqlite_sessions: async_sessionmaker[AsyncSession],
) -> None:
    now = _utc()
    retry = _job("retry", status="running", attempt_count=1)
    retry.lease_owner_hash = "old-owner"
    retry.lease_expires_at = now - timedelta(seconds=1)
    manual = _job("manual", "import-data", status="running", attempt_count=1)
    manual.lease_owner_hash = "old-owner"
    manual.lease_expires_at = now - timedelta(seconds=1)
    async with sqlite_sessions() as session:
        session.add_all([retry, manual])
        await session.commit()
        recovered = await JobQueueRepository(session).recover_expired(now=now)

    assert recovered == {"queued": 1, "interrupted": 1, "failed": 0}
    async with sqlite_sessions() as session:
        assert (await session.get(Job, "retry")).status == "queued"  # type: ignore[union-attr]
        assert (await session.get(Job, "manual")).status == "interrupted"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_owner_fencing_rejects_stale_worker_after_reclaim(
    sqlite_sessions: async_sessionmaker[AsyncSession],
) -> None:
    now = _utc()
    async with sqlite_sessions() as session:
        session.add(_job("fenced"))
        await session.commit()
    async with sqlite_sessions() as old_session:
        old_job = await JobQueueRepository(old_session).claim_next("old-owner", 30, now=now)
        assert old_job is not None
        async with sqlite_sessions() as recovery_session:
            await JobQueueRepository(recovery_session).recover_expired(
                now=now + timedelta(seconds=31)
            )
        async with sqlite_sessions() as new_session:
            reclaimed = await JobQueueRepository(new_session).claim_next(
                "new-owner", 30, now=now + timedelta(seconds=31)
            )
            assert reclaimed is not None

        with job_execution(JobExecutionState("old-owner", Event())):
            with pytest.raises(JobLeaseLost):
                await assert_job_execution(old_session, old_job)


@pytest.mark.asyncio
async def test_owner_fencing_rejects_an_expired_lease_before_recovery(
    sqlite_sessions: async_sessionmaker[AsyncSession],
) -> None:
    expired = _job("expired-owner", status="running", attempt_count=1)
    expired.lease_owner_hash = "old-owner"
    expired.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    async with sqlite_sessions() as session:
        session.add(expired)
        await session.commit()
        with job_execution(JobExecutionState("old-owner", Event())):
            with pytest.raises(JobLeaseLost):
                await assert_job_execution(session, expired)


@pytest.mark.asyncio
async def test_recovery_enforces_attempt_limit_and_unknown_allowlist(
    sqlite_sessions: async_sessionmaker[AsyncSession],
) -> None:
    now = _utc()
    exhausted = _job(
        "exhausted",
        status="running",
        attempt_count=2,
        max_attempts=2,
    )
    exhausted.lease_owner_hash = "old-owner"
    exhausted.lease_expires_at = now - timedelta(seconds=1)
    unknown = _job("unknown", "unknown-job", status="running", attempt_count=1)
    unknown.lease_owner_hash = "old-owner"
    unknown.lease_expires_at = now - timedelta(seconds=1)
    async with sqlite_sessions() as session:
        session.add_all([exhausted, unknown])
        await session.commit()
        recovered = await JobQueueRepository(session).recover_expired(now=now)

    assert recovered == {"queued": 0, "interrupted": 0, "failed": 2}
    async with sqlite_sessions() as session:
        unknown_job = await session.get(Job, "unknown")
        assert unknown_job is not None
        assert unknown_job.status == "failed"
        assert "允许列表" in (unknown_job.message or "")


@pytest.mark.asyncio
async def test_spatial_analysis_cancel_is_persisted_for_queued_and_running(
    sqlite_sessions: async_sessionmaker[AsyncSession],
) -> None:
    queued = _job("cancel-queued")
    running = _job("cancel-running", status="running", attempt_count=1)
    running.lease_owner_hash = "owner-a"
    running.lease_expires_at = _utc() + timedelta(seconds=60)
    async with sqlite_sessions() as session:
        session.add_all([queued, running])
        await session.commit()
        repository = SpatialAnalysisRepository(session)
        await repository.request_cancel(queued)
        await repository.request_cancel(running)

    async with sqlite_sessions() as session:
        stored_queued = await session.get(Job, "cancel-queued")
        stored_running = await session.get(Job, "cancel-running")
        assert stored_queued is not None and stored_queued.status == "interrupted"
        assert stored_queued.finished_at is not None
        assert stored_running is not None and stored_running.status == "running"
        assert stored_running.cancel_requested_at is not None
        assert stored_running.result["detail"]["stage"] == "canceling"


@pytest.mark.asyncio
async def test_interrupted_import_can_be_resumed_manually(
    sqlite_sessions: async_sessionmaker[AsyncSession],
) -> None:
    interrupted = _job("resume-import", "import-data", status="interrupted", attempt_count=1)
    interrupted.finished_at = _utc()
    async with sqlite_sessions() as session:
        session.add(interrupted)
        await session.commit()
        status = await ImportService(ImportRepository(session)).resume("resume-import")

    assert status.status == "queued"
    assert status.detail.stage == "queued"
    async with sqlite_sessions() as session:
        stored = await session.get(Job, "resume-import")
        assert stored is not None
        assert stored.max_attempts >= 2
        assert stored.finished_at is None


@pytest.mark.asyncio
async def test_finished_job_is_never_recovered_or_replayed(
    sqlite_sessions: async_sessionmaker[AsyncSession],
) -> None:
    done = _job("done", status="done", attempt_count=1)
    done.finished_at = _utc()
    async with sqlite_sessions() as session:
        session.add(done)
        await session.commit()
        repository = JobQueueRepository(session)
        assert await repository.recover_expired(now=_utc() + timedelta(days=1)) == {
            "queued": 0,
            "interrupted": 0,
            "failed": 0,
        }
        assert await repository.claim_next("owner", 60, now=_utc() + timedelta(days=1)) is None

    async with sqlite_sessions() as session:
        stored = await session.get(Job, "done")
        assert stored is not None and stored.status == "done"


def test_job_errors_are_redacted_before_persistence() -> None:
    error = RuntimeError(
        r"failed at C:\Users\person\private\asset.tif password=secret-value token=abc"
    )

    sanitized = sanitize_job_error(error)

    assert "C:\\Users" not in sanitized
    assert "secret-value" not in sanitized
    assert "token=abc" not in sanitized
    assert "<路径>" in sanitized
    assert "password=[redacted]" in sanitized


def test_job_status_hides_internal_recovery_state() -> None:
    job = _job("public-job", "import-data")
    job.result = {
        "detail": JobProgressDetail(stage="importing").model_dump(),
        "offsets": {"dataset-1": 2000},
        "staging_layers": {"dataset-1": 91},
        "completed_dataset_ids": ["dataset-1"],
        "workspace_id": 7,
        "download_ready": True,
    }

    status = JobRepository.to_status(job)

    assert status.detail.kind == "import"
    assert status.result == {"workspace_id": 7, "download_ready": True}


def test_windows_worker_does_not_reapply_inherited_below_normal_priority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel32 = SimpleNamespace(
        GetCurrentProcess=Mock(return_value=123),
        GetPriorityClass=Mock(return_value=0x00004000),
        SetPriorityClass=Mock(return_value=True),
    )
    monkeypatch.setattr("app.features.jobs.worker.platform.system", lambda: "Windows")
    monkeypatch.setattr(
        "app.features.jobs.worker.ctypes.WinDLL",
        lambda *_args, **_kwargs: kernel32,
        raising=False,
    )

    apply_process_priority(PerformanceWorkerSettings())

    kernel32.SetPriorityClass.assert_not_called()
