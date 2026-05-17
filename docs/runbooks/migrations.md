# Database Migration Runbook

本文件定义数据库迁移、验证和回滚流程。

## Create Migration

```bash
cd services/api-server
alembic revision --autogenerate -m "create_task_event_tables"
```

Review generated migration:

```bash
git diff app/db/migrations
```

Required checks:

```text
upgrade exists
downgrade exists
indexes exist
foreign keys exist
event table mutation rules preserved
```

## Apply Migration

```bash
cd services/api-server
alembic upgrade head
```

Verify:

```bash
alembic current
python -m pytest tests/test_event_store.py
```

## Rollback Migration

Rollback one revision:

```bash
cd services/api-server
alembic downgrade -1
```

Rollback to specific revision:

```bash
alembic downgrade <revision_id>
```

## Production Migration Order

```text
1. backup database
2. stop workers
3. apply migration
4. start API
5. run smoke tests
6. start workers
7. monitor errors
```

## Backup Command

```bash
pg_dump "$DATABASE_URL" > "/opt/agent-harness/backups/agent_harness_$(date +%Y%m%d_%H%M%S).sql"
```

## Knowledge Restore Verification

For Agent Knowledge Harness migrations, a backup/restore note is not enough.
After restoring the database and running migrations, verify:

```text
current retrieval returns ACTIVE source chunks only
DISABLED or ARCHIVED sources are not retrieved
historical Run Detail evidence renders by exact selector
lifecycle audit events exist for create/version/disable/archive actions
org-scoped sources stay isolated to their organization
```

Automated smoke coverage:
`tests/test_knowledge_rag.py::test_knowledge_lifecycle_migration_preserves_existing_p1_rows`
and
`tests/test_knowledge_rag.py::test_knowledge_restore_smoke_preserves_current_and_historical_contracts`.

Candidate-safe rule:

```text
If the P1 Docker/private baseline is unavailable, record:
Private deployment verification deferred.
P2 cannot be promoted to completed baseline.
```

## Event Store Constraint

Migration must preserve:

```text
agent_events append-only behavior
unique(task_id, sequence)
event replay compatibility
```
