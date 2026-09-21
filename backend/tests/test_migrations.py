from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config


def test_migration_chain_renders_complete_postgresql_schema() -> None:
    buffer = StringIO()
    config = Config("alembic.ini")
    with redirect_stdout(buffer):
        command.upgrade(config, "head", sql=True)

    sql = buffer.getvalue()
    assert "CREATE EXTENSION IF NOT EXISTS pgcrypto" in sql
    assert "CREATE EXTENSION IF NOT EXISTS citext" in sql
    assert sql.count("CREATE TABLE ") == 20  # 19 project tables + alembic_version
    assert "CREATE TABLE organizations" in sql
    assert "CREATE TABLE organization_setting_versions" in sql
    assert "CREATE TABLE category_activity_configs" in sql
    assert "CREATE TABLE daily_activity_values" in sql
    assert "CREATE TABLE weekly_activity_results" in sql
    assert sql.count("CREATE TYPE version_status") == 1


def test_initial_revision_is_static_and_does_not_import_live_models() -> None:
    revision = Path("migrations/versions/0001_initial_schema.py").read_text()
    assert "from app.models" not in revision
    assert "Base.metadata.create_all" not in revision
    assert 'revision: str = "0001_initial_schema"' in revision


def test_organization_settings_are_added_in_new_revision_not_0001() -> None:
    initial = Path("migrations/versions/0001_initial_schema.py").read_text()
    second = Path("migrations/versions/0002_org_setting_versions.py").read_text()

    assert "organization_setting_versions" not in initial
    assert 'revision: str = "0002_org_setting_versions"' in second
    assert 'down_revision: Union[str, None] = "0001_initial_schema"' in second
    assert "organization_setting_versions" in second


def test_all_alembic_revision_ids_fit_version_table_column() -> None:
    # Alembic creates alembic_version.version_num as VARCHAR(32) by default.
    # Keep every revision id within that limit so an otherwise-successful
    # migration cannot fail when Alembic records the new head.
    config = Config("alembic.ini")
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(config)
    revision_ids = [revision.revision for revision in script.walk_revisions()]
    assert revision_ids
    assert all(len(revision_id) <= 32 for revision_id in revision_ids)
