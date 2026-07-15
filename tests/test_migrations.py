from alembic.config import Config
from alembic.script import ScriptDirectory


def test_migration_history_has_one_expected_head() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert script.get_heads() == ["20260715_02"]
    assert script.get_revision("20260715_02").down_revision == "20260715_01"
