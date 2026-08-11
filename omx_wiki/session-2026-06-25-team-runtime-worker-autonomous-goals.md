# Team Runtime Worker Autonomous Goals

Category: session-log
Tags: `team-mode`, `team-goal`, `team-runtime`, `background-worker`, `autonomous-agents`

## Summary

Team Mode now has a deployable background runtime worker for active Team Goals.
The previous Team Goal work gave the Leader durable goal state and deterministic
drift supervision. This session adds the missing no-frontend trigger: a runtime
service can scan active goals, choose runnable agents, and wake them through the
existing Team service until work moves.

This is intentionally the first runtime layer, not a real process pool for
separate long-lived worker agents. The worker owns scheduling ticks and wake
decisions; `TeamSessionService` still owns execution, mailbox reads, task state,
model turns, and event emission.

## Changes

- `services/api-server/app/workers/team_runtime_worker.py`
  - adds `tick_active_team_goals(...)` for deterministic tests and manual one-shot
    operation;
  - adds `run_team_runtime_service(...)` and `python -m app.workers.team_runtime_worker`
    for a long-running background service;
  - adds an inline wake backend and a real `ProcessPoolExecutor` wake backend so
    the scheduler can hand execution to child processes;
  - uses Postgres advisory lock or an in-process SQLite lock to avoid duplicate
    ticks;
  - caps scanned goals and wake count per tick;
  - logs and survives isolated service-loop tick failures.
- `services/api-server/tests/test_teams.py`
  - covers active-goal leader wakes without frontend `triggerWake`;
  - covers assigned task owner wakes without browser interaction;
  - covers one-time autonomous goal bootstrap when no user message exists;
  - covers idempotent bootstrap state.
- `deploy/docker-compose/docker-compose.yml`
  - adds `team-runtime`.
- `deploy/systemd/agent-team-runtime.service`
  - adds a systemd unit for non-Compose deployment.
- `deploy/monitoring/promtail.yml`
  - includes `team-runtime` in container log discovery.
- `docs/project-memory/runbooks/local-development.md`
  - documents the local worker command and tuning environment variables.
- `docs/project-memory/runbooks/deployment.md`
  - documents service enable/start/status/log checks for `agent-team-runtime`.

## Runtime Decision Order

1. Recover stale active wake state through `report_agent_inactivity_timeout(...)`.
2. Wake the first wakeable unread mailbox recipient.
3. Wake the first wakeable owner of an open assigned task.
4. If no runnable work exists and the active goal has not been bootstrapped,
   write one system goal message to the leader and wake the leader.
5. Otherwise wait.

When `TEAM_RUNTIME_EXECUTION_BACKEND=process_pool`, the coordinator commits its
tick-side database work first, then hands concrete wake requests to child
processes. Each child opens its own DB session and runs the same
`TeamSessionService.wake_agent(...)` path.

The bootstrap path stores `runtime_bootstrapped_at` in
`goal.supervisor_state_json`, so later ticks do not repeat the same startup
message.

## Validation

```text
services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_teams.py -q
46 passed

services/api-server/.venv/bin/python -m ruff check services/api-server/app/workers/team_runtime_worker.py services/api-server/tests/test_teams.py
passed

services/api-server/.venv/bin/python -m py_compile services/api-server/app/workers/team_runtime_worker.py
passed

AUTH_JWT_SECRET=<test-secret> HARNESS_SECRET_ENCRYPTION_KEY=<test-key> HARNESS_SECRET_ENCRYPTION_KEY_ID=<test-key-id> docker compose -f deploy/docker-compose/docker-compose.yml config
passed

python3 scripts/validate-docs.py
docs validation passed

git diff --check
passed
```

## Boundary

This closes the first autonomous Team Goal execution gap: a goal no longer needs
the browser page to be open for the next wake to happen. It does not yet create
an independent supervised pool of OS processes per teammate. That future layer
should build on this scheduler and decide how worker processes are started,
leased, monitored, messaged, and terminated.
