# AI Execution Protocol

## Role

The executing AI works as an implementation agent for a Production Agent Harness Platform.

## Source Of Truth

Read these files before implementation:

1. `docs/00-product-spec.md`
2. `docs/01-system-architecture.md`
3. `docs/02-data-model-and-event-spec.md`
4. `docs/03-api-spec.md`
5. `docs/ai/task-progress.yaml`
6. The current file under `docs/ai/stages/`

## Execution Rules

- Implement the current stage as a runnable vertical slice.
- Do not build a normal chatbot as the product center.
- Do not add static console data.
- Do not add placeholder routes.
- Backend state must drive frontend state.
- Every state-changing Agent operation must write an event or audit record.
- Eval Harness remains a first-class module.
- PostgreSQL remains the production database path.

## Stage Completion

Before advancing a stage:

```text
cd services/api-server && .venv/bin/python -m pytest
cd services/api-server && .venv/bin/python -m ruff check app tests
cd apps/agent-console && npm run build
python3 scripts/validate-docs.py
```

Then update:

- `docs/ai/task-progress.yaml`
- `docs/task-progress.md`

## Product Boundary

The console entry is Agent Chat. The product is the Harness: Planner, Executor, Subagent Orchestrator, Event Sourcing, Tool Runtime, Guardrails, Eval Harness, Memory, Model Router, WarmPool, Trace, Replay, and Recovery.
