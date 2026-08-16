from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.cli.harnessd import runtime_paths
from app.local_runtime.data_import import import_legacy_data


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="harness-import-local-data",
        description="Import legacy Harness data into a fresh canonical local SQLite runtime.",
    )
    parser.add_argument("--runtime-data-dir", type=Path, required=True)
    parser.add_argument("--offline-sqlite", type=Path)
    parser.add_argument("--postgres-url")
    parser.add_argument("--owner-user-id", required=True)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--owner-email", default="local-owner@harness.invalid")
    parser.add_argument("--owner-name", default="Local Owner")
    parser.add_argument("--execute", action="store_true", help="select the validated candidate")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    api_server_dir = Path(__file__).resolve().parents[2]
    result = import_legacy_data(
        runtime_paths(args.runtime_data_dir),
        alembic_ini=api_server_dir / "alembic.ini",
        owner_user_id=args.owner_user_id,
        organization_id=args.organization_id,
        offline_sqlite=args.offline_sqlite,
        postgres_url=args.postgres_url,
        owner_email=args.owner_email,
        owner_name=args.owner_name,
        dry_run=not args.execute,
    )
    print(json.dumps(result.to_dict(), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
