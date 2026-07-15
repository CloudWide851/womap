"""建立 WOMAP 元数据基线，并安全采用已有表。"""

from alembic import op

import app.models  # noqa: F401
from app.db.base import Base

revision = "20260715_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新库创建既有业务表；已有库通过 checkfirst 原地采用，不搬移数据。"""
    bind = op.get_bind()
    baseline_tables = [
        table for name, table in Base.metadata.tables.items() if name != "auth_sessions"
    ]
    Base.metadata.create_all(bind=bind, tables=baseline_tables, checkfirst=True)


def downgrade() -> None:
    """基线采用不可逆，降级不得删除用户已有业务数据。"""
