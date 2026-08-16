# ADR 0003: Use Event Sourcing For Task State

## Status

accepted

## Context

Enterprise Agent execution requires auditability, recovery, replay debugging and compliance-grade history.

## Decision

Task state uses Event Store as the source of truth. `agent_events` is append-only. State is reconstructed from events ordered by task-local sequence.

## Consequences

- Every task action writes an event.
- `agent_events` update and delete operations are forbidden.
- Recovery and replay use event streams.
- Snapshots are created every 100 events.

