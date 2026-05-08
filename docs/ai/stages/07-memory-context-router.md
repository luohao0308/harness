# Stage 7: Memory / Context / Model Routing

## Goal

Add working memory, long-term memory, artifact memory, RAG context, context compression, and model routing.

## Input

Run context, traces, artifacts, user goal, task type, and model settings.

## Output

Routed model decision, memory context bundle, compressed trace, and routing trace.

## Modules

Memory Store, Context Compressor, Model Router, Model Gateway, Agent Workspace.

## API And Schema Changes

Expose `GET /api/tasks/{task_id}/context` for read-only memory projection.
Expose `POST /api/tasks/{task_id}/context/route` for persisted routing trace.

## Event Types

`MODEL_CALLED`, `MODEL_FALLBACK_USED`, `AGENT_SELECTED`, `CONTEXT_COMPRESSED`, `MODEL_ROUTED`.

## Frontend Display

Run Detail shows selected model, routing reason, working memory, artifact memory, RAG context, and compressed trace.

## Tests

Routing tests cover coding and grading policies, read-only projection, and persisted routing events.

## Acceptance

Different task types route to the configured model class and the decision is traceable through persisted events.

## Not Doing

External vector database operations are not required for the first slice.

## Vertical Slice Demo

```text
Create coding task
-> model router selects coding model
-> Run Detail shows memory bundle
-> trace shows CONTEXT_COMPRESSED and MODEL_ROUTED
```
