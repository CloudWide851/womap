"""增加持久任务租约、取消和恢复字段。"""

from alembic import op
import sqlalchemy as sa


revision = "20260718_03"
down_revision = "20260715_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("jobs")}
    additions = [
        ("priority", sa.Column("priority", sa.Integer(), nullable=False, server_default="100")),
        (
            "resource_class",
            sa.Column("resource_class", sa.String(length=20), nullable=False, server_default="cpu-io"),
        ),
        (
            "available_at",
            sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        ),
        ("lease_owner_hash", sa.Column("lease_owner_hash", sa.String(length=64), nullable=True)),
        ("lease_expires_at", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True)),
        ("heartbeat_at", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True)),
        ("attempt_count", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0")),
        ("max_attempts", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="1")),
        (
            "cancel_requested_at",
            sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        ),
        ("started_at", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True)),
        ("finished_at", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True)),
    ]
    for name, column in additions:
        if name not in columns:
            op.add_column("jobs", column)

    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("jobs")}
    if "ix_jobs_queue_claim" not in indexes:
        op.create_index(
            "ix_jobs_queue_claim",
            "jobs",
            ["status", "priority", "available_at", "created_at"],
            postgresql_where=sa.text("status = 'queued'"),
        )
    if "ix_jobs_expired_lease" not in indexes:
        op.create_index(
            "ix_jobs_expired_lease",
            "jobs",
            ["status", "lease_expires_at"],
            postgresql_where=sa.text("status = 'running'"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("jobs")}
    for name in ("ix_jobs_expired_lease", "ix_jobs_queue_claim"):
        if name in indexes:
            op.drop_index(name, table_name="jobs")
    columns = {column["name"] for column in sa.inspect(bind).get_columns("jobs")}
    for name in (
        "finished_at",
        "started_at",
        "cancel_requested_at",
        "max_attempts",
        "attempt_count",
        "heartbeat_at",
        "lease_expires_at",
        "lease_owner_hash",
        "available_at",
        "resource_class",
        "priority",
    ):
        if name in columns:
            op.drop_column("jobs", name)
