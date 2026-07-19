from __future__ import annotations

import argparse
import asyncio
import ctypes
import hashlib
import json
import logging
import os
import platform
import secrets
import signal
from contextlib import suppress
from pathlib import Path
from threading import Event

from app.features.jobs.dispatcher import dispatch_job
from app.features.jobs.execution import (
    JobCancellationRequested,
    JobExecutionState,
    JobLeaseLost,
    job_execution,
)
from app.features.jobs.queue_repository import JobQueueRepository
from app.shared.config import PerformanceWorkerSettings, get_settings
from app.shared.database import create_worker_database


logger = logging.getLogger("womap.worker")


def apply_process_priority(settings: PerformanceWorkerSettings) -> None:
    system = platform.system().casefold()
    if system == "windows" and settings.windows_priority == "below_normal":
        below_normal_priority_class = 0x00004000
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        get_current_process = kernel32.GetCurrentProcess
        get_current_process.argtypes = []
        get_current_process.restype = ctypes.c_void_p
        get_priority_class = kernel32.GetPriorityClass
        get_priority_class.argtypes = [ctypes.c_void_p]
        get_priority_class.restype = ctypes.c_uint32
        set_priority_class = kernel32.SetPriorityClass
        set_priority_class.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        set_priority_class.restype = ctypes.c_bool
        process = get_current_process()
        if get_priority_class(process) == below_normal_priority_class:
            return
        if not set_priority_class(process, below_normal_priority_class):
            raise OSError("unable to apply below-normal worker priority")
    elif system == "linux" and settings.linux_nice:
        current_nice = os.nice(0)
        if current_nice < settings.linux_nice:
            os.nice(settings.linux_nice - current_nice)


def _write_ready_file(path: Path | None) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps({"pid": os.getpid(), "status": "ready"}),
        encoding="utf-8",
    )
    temporary.replace(path)


async def _watch_stop_file(path: Path | None, stop_event: Event) -> None:
    if path is None:
        return
    while not stop_event.is_set():
        if path.exists():
            stop_event.set()
            return
        await asyncio.sleep(0.25)


async def _heartbeat(
    session_factory,
    job_id: str,
    owner_hash: str,
    settings: PerformanceWorkerSettings,
    stop_event: Event,
) -> None:
    while not stop_event.is_set():
        await asyncio.sleep(settings.heartbeat_seconds)
        if stop_event.is_set():
            return
        async with session_factory() as session:
            alive = await JobQueueRepository(session).heartbeat(
                job_id,
                owner_hash,
                settings.lease_seconds,
            )
        if not alive:
            return


async def _execute_claimed_job(
    session_factory,
    job_id: str,
    job_type: str,
    owner_hash: str,
    settings: PerformanceWorkerSettings,
    stop_event: Event,
) -> None:
    heartbeat_task = asyncio.create_task(
        _heartbeat(session_factory, job_id, owner_hash, settings, stop_event)
    )
    try:
        with job_execution(JobExecutionState(owner_hash=owner_hash, stop_event=stop_event)):
            await dispatch_job(job_type, job_id, session_factory)
    except JobCancellationRequested:
        async with session_factory() as session:
            await JobQueueRepository(session).interrupt_owned(
                job_id, owner_hash, "任务已按请求安全中断。"
            )
    except JobLeaseLost:
        logger.warning("job_lease_lost job_id=%s", job_id)
    except Exception as exc:
        logger.error(
            "job_dispatch_failed job_id=%s error_type=%s",
            job_id,
            type(exc).__name__,
        )
        async with session_factory() as session:
            await JobQueueRepository(session).fail_owned(
                job_id, owner_hash, "任务处理进程发生未预期错误。"
            )
    finally:
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task

    async with session_factory() as session:
        job = await JobQueueRepository(session).get(job_id)
        if job is not None and job.status == "running" and job.lease_owner_hash == owner_hash:
            await JobQueueRepository(session).fail_owned(
                job_id, owner_hash, "任务处理器未写入终态。"
            )


async def run_worker(
    *,
    ready_file: Path | None = None,
    stop_file: Path | None = None,
    once: bool = False,
) -> int:
    settings = get_settings()
    if not settings.performance.worker.enabled:
        logger.error("worker_disabled")
        return 2
    if settings.database.kind != "postgresql":
        logger.error("worker_requires_postgresql")
        return 2

    apply_process_priority(settings.performance.worker)
    stop_event = Event()
    loop = asyncio.get_running_loop()

    def request_stop(*_: object) -> None:
        stop_event.set()

    for signal_name in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError, RuntimeError, ValueError):
            loop.add_signal_handler(signal_name, request_stop)
    with suppress(ValueError):
        signal.signal(signal.SIGINT, request_stop)
    with suppress(ValueError):
        signal.signal(signal.SIGTERM, request_stop)

    if stop_file is not None:
        stop_file.unlink(missing_ok=True)
    if ready_file is not None:
        ready_file.unlink(missing_ok=True)

    engine, session_factory = create_worker_database()
    owner_hash = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
    stop_watcher = asyncio.create_task(_watch_stop_file(stop_file, stop_event))
    try:
        async with session_factory() as session:
            await JobQueueRepository(session).recover_expired()
        _write_ready_file(ready_file)
        while not stop_event.is_set():
            async with session_factory() as session:
                job = await JobQueueRepository(session).claim_next(
                    owner_hash,
                    settings.performance.worker.lease_seconds,
                )
            if job is None:
                if once:
                    break
                await asyncio.sleep(settings.performance.worker.poll_interval_seconds)
                continue
            await _execute_claimed_job(
                session_factory,
                job.id,
                job.job_type,
                owner_hash,
                settings.performance.worker,
                stop_event,
            )
            if once:
                break
        return 0
    finally:
        stop_event.set()
        stop_watcher.cancel()
        with suppress(asyncio.CancelledError):
            await stop_watcher
        if ready_file is not None:
            ready_file.unlink(missing_ok=True)
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the durable WOMAP job worker.")
    parser.add_argument("--ready-file", type=Path)
    parser.add_argument("--stop-file", type=Path)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return asyncio.run(
        run_worker(ready_file=args.ready_file, stop_file=args.stop_file, once=args.once)
    )


if __name__ == "__main__":
    raise SystemExit(main())
