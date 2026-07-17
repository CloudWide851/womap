from importlib import import_module
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.shared.config import get_settings


def test_migration_history_has_one_expected_head() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert script.get_heads() == ["20260718_03"]
    assert script.get_revision("20260718_03").down_revision == "20260715_02"


@pytest.mark.asyncio
async def test_durable_job_migration_upgrades_downgrades_and_reupgrades_postgresql() -> None:
    revision = import_module("migrations.versions.20260718_03_durable_jobs")
    url = get_settings().database.sqlalchemy_url().set(host="127.0.0.1")
    admin_engine = create_async_engine(url, connect_args={"ssl": False})
    schema = f"womap_migration_{uuid4().hex}"
    async with admin_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url,
        connect_args={
            "server_settings": {"search_path": f"{schema},public"},
            "ssl": False,
        },
    )

    metadata = sa.MetaData()
    sa.Table(
        "jobs",
        metadata,
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    def apply_revision(sync_connection, action) -> None:
        context = MigrationContext.configure(sync_connection)
        with Operations.context(context):
            action()

    def inspect_jobs(sync_connection) -> tuple[set[str], set[str]]:
        inspector = sa.inspect(sync_connection)
        columns = {column["name"] for column in inspector.get_columns("jobs")}
        indexes = {index["name"] for index in inspector.get_indexes("jobs")}
        return columns, indexes

    try:
        async with engine.begin() as connection:
            await connection.run_sync(metadata.create_all)
            await connection.run_sync(lambda sync: apply_revision(sync, revision.upgrade))
            upgraded_columns, upgraded_indexes = await connection.run_sync(inspect_jobs)
            await connection.run_sync(lambda sync: apply_revision(sync, revision.downgrade))
            downgraded_columns, downgraded_indexes = await connection.run_sync(inspect_jobs)
            await connection.run_sync(lambda sync: apply_revision(sync, revision.upgrade))
            reupgraded_columns, reupgraded_indexes = await connection.run_sync(inspect_jobs)

        durable_columns = {
            "priority",
            "resource_class",
            "available_at",
            "lease_owner_hash",
            "lease_expires_at",
            "heartbeat_at",
            "attempt_count",
            "max_attempts",
            "cancel_requested_at",
            "started_at",
            "finished_at",
        }
        durable_indexes = {"ix_jobs_queue_claim", "ix_jobs_expired_lease"}
        assert durable_columns <= upgraded_columns
        assert durable_indexes <= upgraded_indexes
        assert durable_columns.isdisjoint(downgraded_columns)
        assert durable_indexes.isdisjoint(downgraded_indexes)
        assert durable_columns <= reupgraded_columns
        assert durable_indexes <= reupgraded_indexes
    finally:
        await engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin_engine.dispose()
