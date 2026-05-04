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

## Event Store Constraint

Migration must preserve:

```text
agent_events append-only behavior
unique(task_id, sequence)
event replay compatibility
```

