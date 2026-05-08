# Stage 2: Event Store + Recovery

## Goal

Make every Agent run recoverable and replayable from append-only events.

## Input

Existing task event streams and task snapshots.

## Output

Replay endpoint, recovery projection, checkpoint state, and console replay view.

## Modules

EventStore, EventReplay, TaskSnapshot, recovery workers, Run Detail replay panel.

## API And Schema Changes

Use `/api/tasks/{task_id}/events`, `/api/tasks/{task_id}/events/stream`, `/api/tasks/{task_id}/replay`, `/api/tasks/{task_id}/resume`, `/api/tasks/{task_id}/steps/resume`.

## Event Types

All task, plan, step, model, tool, subagent, assignment, policy, sandbox, and eval task events.

## Frontend Display

Run Detail shows event timeline, replay sequence input, reconstructed state summary, failure point, and resume controls.

## Tests

Test event ordering, sequence uniqueness, snapshot creation, replay to sequence, and step resume.

## Acceptance

Stopping and restarting services does not lose run state. Replay to a specific sequence reconstructs the run.

## Not Doing

Distributed event log compaction is outside this stage.

## Vertical Slice Demo

```text
Run a task
-> open events
-> replay sequence N
-> resume from failed or cancelled state
```
