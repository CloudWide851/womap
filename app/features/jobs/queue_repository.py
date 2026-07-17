from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.jobs.policies import job_policy
from app.models.job import Job


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobQueueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def claim_next(
        self,
        owner_hash: str,
        lease_seconds: int,
        *,
        now: datetime | None = None,
    ) -> Job | None:
        current = now or utc_now()
        statement = (
            select(Job)
            .where(
                Job.status == "queued",
                Job.available_at <= current,
                Job.cancel_requested_at.is_(None),
                Job.attempt_count < Job.max_attempts,
            )
            .order_by(Job.priority, Job.available_at, Job.created_at, Job.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = await self.session.scalar(statement)
        if job is None:
            await self.session.rollback()
            return None
        job.status = "running"
        job.lease_owner_hash = owner_hash
        job.heartbeat_at = current
        job.lease_expires_at = current + timedelta(seconds=lease_seconds)
        job.attempt_count += 1
        job.started_at = job.started_at or current
        job.finished_at = None
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def heartbeat(
        self,
        job_id: str,
        owner_hash: str,
        lease_seconds: int,
        *,
        now: datetime | None = None,
    ) -> bool:
        current = now or utc_now()
        result = await self.session.execute(
            update(Job)
            .where(
                Job.id == job_id,
                Job.status == "running",
                Job.lease_owner_hash == owner_hash,
                Job.lease_expires_at > current,
            )
            .values(
                heartbeat_at=current,
                lease_expires_at=current + timedelta(seconds=lease_seconds),
            )
            .execution_options(synchronize_session=False)
        )
        await self.session.commit()
        return bool(result.rowcount)

    async def recover_expired(self, *, now: datetime | None = None) -> dict[str, int]:
        current = now or utc_now()
        jobs = (
            await self.session.scalars(
                select(Job)
                .where(
                    Job.status == "running",
                    or_(Job.lease_expires_at.is_(None), Job.lease_expires_at <= current),
                )
                .with_for_update(skip_locked=True)
            )
        ).all()
        recovered = {"queued": 0, "interrupted": 0, "failed": 0}
        for job in jobs:
            job.lease_owner_hash = None
            job.lease_expires_at = None
            job.heartbeat_at = None
            try:
                policy = job_policy(job.job_type)
            except ValueError:
                job.status = "failed"
                job.finished_at = current
                job.message = "任务类型不在 Worker 允许列表中，已停止恢复。"
                recovered["failed"] += 1
                continue
            if job.cancel_requested_at is not None or policy.recovery == "interrupt":
                job.status = "interrupted"
                job.finished_at = current
                job.message = "任务进程已中断，请根据任务提示重新提交或继续。"
                recovered["interrupted"] += 1
            elif job.attempt_count < job.max_attempts:
                job.status = "queued"
                job.available_at = current
                job.finished_at = None
                job.message = "检测到过期租约，任务已重新进入队列。"
                recovered["queued"] += 1
            else:
                job.status = "failed"
                job.finished_at = current
                job.message = "任务进程异常退出，已达到最大恢复次数。"
                recovered["failed"] += 1
        await self.session.commit()
        return recovered

    async def interrupt_owned(self, job_id: str, owner_hash: str, message: str) -> bool:
        current = utc_now()
        result = await self.session.execute(
            update(Job)
            .where(
                Job.id == job_id,
                Job.status == "running",
                Job.lease_owner_hash == owner_hash,
            )
            .values(
                status="interrupted",
                message=message,
                finished_at=current,
                lease_owner_hash=None,
                lease_expires_at=None,
                heartbeat_at=None,
            )
        )
        await self.session.commit()
        return bool(result.rowcount)

    async def fail_owned(self, job_id: str, owner_hash: str, message: str) -> bool:
        current = utc_now()
        result = await self.session.execute(
            update(Job)
            .where(
                Job.id == job_id,
                Job.status == "running",
                Job.lease_owner_hash == owner_hash,
            )
            .values(
                status="failed",
                message=message[:500],
                finished_at=current,
                lease_owner_hash=None,
                lease_expires_at=None,
                heartbeat_at=None,
            )
        )
        await self.session.commit()
        return bool(result.rowcount)

    async def get(self, job_id: str) -> Job | None:
        return await self.session.get(Job, job_id)
