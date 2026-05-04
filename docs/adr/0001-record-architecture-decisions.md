# ADR 0001: Record Architecture Decisions

## Status

accepted

## Context

The project requires stable architecture decisions for AI-driven implementation. Without ADR records, future agents may drift from fixed technology choices and execution order.

## Decision

All architecture decisions are recorded in `docs/adr`. AI execution documents reference ADR decisions through `docs/ai/reference/architecture-and-decisions.md`.

## Consequences

- Technology changes require a new ADR.
- AI agents must not change fixed decisions without ADR update.
- Documentation and implementation stay aligned.

