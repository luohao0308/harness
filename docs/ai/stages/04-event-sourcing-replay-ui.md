# Stage 4: Event Sourcing And Replay UI

## Goal

Make Event Sourcing visible and useful for audit, recovery, and time-travel debugging.

## Input

- Agent Run event stream.
- Replay sequence requested by user.
- Current SQL projections.

## Output

- Run Detail and Observability expose event timeline.
- Replay reconstructs state to a sequence.
- Recovery and failure diagnosis are visible.

## Modules

- Event Store
- Replay Service
- Run Detail
- Observability
- Audit export path

## API And Schema Changes

- Keep Run workspace projection events ordered by sequence.
- Keep replay API on compatibility path until migrated to `/api/agents/runs/{run_id}/replay`.
- Observability summary reports event, tool, model, sandbox, latency, and run metrics.

## Event Types

- All Run, Plan, Step, Tool, Model, Sandbox, Assignment, Eval, Replay, and Recovery events.

## Frontend Display

- Right panel Event Stream in Workspace.
- Run Detail timeline with sequence, type, trace, actor, timestamp, payload preview.
- Replay panel with target sequence and reconstructed state summary.
- Observability event browser uses backend data.

## Tests

- Event Store tests cover append-only ordering.
- Replay tests cover reconstruction to sequence.
- Frontend build covers Run Detail event and replay panels.

## Acceptance

- User can inspect every state change of a Run.
- User can replay to a specific sequence.
- Event timeline is not static data.

## Not Doing

- No separate event warehouse.
- No arbitrary SQL event editor.
- No deletion of audit events.

## Vertical Slice Demo

```text
Create Run
-> Execute Run
-> open Run Detail
-> select sequence
-> Replay shows state at that point
```
