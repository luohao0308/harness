import importlib.util
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_lint_script() -> Any:
    path = REPO_ROOT / "scripts/check-migration-ids.py"
    spec = importlib.util.spec_from_file_location("check_migration_ids", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_migration_ids"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_current_migrations_pass_id_width_lint() -> None:
    checker = _load_lint_script()

    assert checker.main([str(REPO_ROOT / "services/api-server/alembic/versions")]) == 0


def test_id_width_lint_rejects_seed_longer_than_table_id(tmp_path: Path) -> None:
    checker = _load_lint_script()
    migration = tmp_path / "20260699_bad_seed_width.py"
    migration.write_text(
        """
import sqlalchemy as sa
from alembic import op


def upgrade():
    bad_table = op.create_table(
        "bad_seed_table",
        sa.Column("id", sa.String(length=15), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(
        bad_table,
        [{"id": "system-foo-bar-baz-qux-1234567890", "name": "bad"}],
    )
""".lstrip(),
        encoding="utf-8",
    )

    violations = checker.check_file(migration)

    assert len(violations) == 1
    assert violations[0].table_name == "bad_seed_table"
    assert violations[0].column_length == 15
    assert violations[0].seed.value == "system-foo-bar-baz-qux-1234567890"
    assert checker.main([str(migration)]) == 1
