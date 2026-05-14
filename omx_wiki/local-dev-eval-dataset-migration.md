# Local Dev Eval Dataset Migration

Category: `debugging`

Tags: `local-dev`, `postgres`, `alembic`, `eval-case`, `run-detail`, `database`

## Symptom

Run Detail showed the `Save as Eval Case` button for a COMPLETED/FAILED Run, but the Dataset selector was empty and the button was disabled.

Direct API check:

```text
GET /api/evals/datasets -> 500 Internal Server Error
```

Backend traceback:

```text
psycopg.errors.UndefinedColumn: column eval_datasets.baseline_run_id does not exist
```

## Root Cause

The local Postgres schema lagged behind the application model. The migration file existed:

```text
services/api-server/alembic/versions/20260514_0010_add_eval_dataset_baseline_run_id.py
```

But the database was still at the previous revision and did not have:

```text
eval_datasets.baseline_run_id
```

## Fix

Run migrations from the API service directory:

```bash
cd services/api-server
./.venv/bin/python -m alembic upgrade head
```

Observed migration:

```text
Running upgrade 20260508_0009 -> 20260514_0010, add eval_dataset baseline_run_id
```

## Verification

After migration:

```text
GET /api/evals/datasets -> 200 OK
{"items":[],"next_cursor":null}
```

Full capture chain was also verified with a real COMPLETED Run:

1. Create `Saved Runs` dataset.
2. Save Eval Case from the Run.
3. `POST /api/evals/datasets/{dataset_id}/cases/from-run/{run_id}` returned `201 Created`.

## Preventive Pattern

If a UI selector is empty but should be populated from the API, check the API endpoint directly before changing frontend state.

For Eval Dataset issues, inspect:

- `services/api-server/app/api/evals.py`
- `services/api-server/app/db/models.py`
- `services/api-server/alembic/versions/`

## Related Pages

- [[agent-workspace-execution-evidence-architecture]]
- [[session-2026-05-14-workspace-execution-evidence]]
- [[local-dev-backend-port-cors]]
