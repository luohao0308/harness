# Migration Conventions

These rules prevent seed data from exceeding database column widths and keep
foreign-key-shaped identifiers consistent across migrations.

## Identifier Width

- UUID-only primary keys use `sa.String(length=36)`.
- System seed identifiers with prefixes such as `system-`, `sys-`, `default-`,
  `retention-`, or similar human-readable names use at least
  `sa.String(length=128)`.
- Cross-table references must match the referenced table id width.
- If a seed id includes a string prefix, choose a column length at least
  `max(seed_id_length) + 64` unless the table is explicitly UUID-only.

## Required Lint

Run the migration id lint before opening or merging a migration PR:

```bash
python3 scripts/check-migration-ids.py services/api-server/alembic/versions
```

The script parses Alembic files with Python AST, finds `op.create_table()` id
column widths, then checks literal `op.bulk_insert()` seed ids for the same
table. It exits nonzero when a seed id is longer than the table id column.

Example failure:

```text
services/api-server/alembic/versions/20260699_bad.py:12: id 'system-foo-bar-baz-qux-1234567890' (length 33) exceeds bad_seed_table.id VARCHAR(15)
```

CI runs the same script in the `migration-id-lint` job before the PostgreSQL
`migration-preflight` job.

## Migration Review Checklist

- `upgrade()` and `downgrade()` both exist.
- New seed ids fit the created table id width.
- Foreign-key-shaped string lengths match the parent table.
- Historical migrations are not rewritten after they may have been applied.
- A patch migration is used for corrective cleanup of already-applied history.
- PostgreSQL `alembic upgrade head` passes after lint.
