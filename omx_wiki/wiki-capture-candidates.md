# Wiki Capture Candidates

Category: `convention`

Tags: `wiki`, `handoff`, `capture-policy`, `project-memory`, `session-log`

## Purpose

This page defines what is worth moving from `.omx/`, docs, or chat history into `omx_wiki/`.

The wiki should not duplicate every implementation diff. It should capture durable project knowledge that helps a future agent make the correct next move.

## Capture These

### 1. Product-Level Decisions

Examples:

- `Model + Harness = Agent`.
- Private deployable internal-test platform as the accepted target.
- Agent Run as product execution object; `/api/tasks/*` as compatibility detail.
- Website as public information shell, not product center.

Recommended category: `decision`.

### 2. Handoff And Current State

Examples:

- Current stage/status.
- Next known work.
- Required reading order.
- Which docs are stale or secondary.

Recommended category: `reference` or `session-log`.

### 3. Accepted Constraints

Examples:

- Chat space is absolute priority for Workspace.
- Harness evidence stays in lightweight header/chips.
- No Kubernetes/full RBAC/SaaS commercialization in first phase.

Recommended category: `decision` or `pattern`.

### 4. Verification Gates

Examples:

- Stage 07 canonical smoke command.
- Browser smoke command.
- Release gate commands that prove a claim.

Recommended category: `reference`.

### 5. Repeated Local Development Traps

Examples:

- Port `8000` occupied by another service.
- CORS origin mismatch between Vite and backend.
- Which backend command starts the correct Harness API.

Recommended category: `debugging` or `environment`.

## Do Not Capture By Default

- Raw command output unless it is evidence for a completed gate.
- Every minor UI tweak.
- Long chat transcripts that are already summarized in `.omx/interviews`.
- Temporary hypotheses that were disproven.
- Unverified future plans with no source artifact.

## Current High-Value Pages

- [[project-handoff-current-state]]
- [[deep-interview-private-harness-chain]]
- [[workspace-demo-ready-constraints]]
- [[local-dev-backend-port-cors]]
- [[session-2026-05-13-workspace-browser-smoke]]

## Concrete Historical Tasks Worth Capturing

Already captured or now covered:

- Project positioning deep-interview: private deployable Harness chain as the accepted goal.
- Stage 07 closure: canonical Agent Run smoke and correlated run/task/replay/tool/sandbox/subagent/eval/observability evidence.
- Workspace demo-ready phase: `Model + Harness = Agent` must be visible without sacrificing chat space.
- Browser smoke hardening: Playwright coverage for Workspace desktop and 390px behavior.
- Local backend failure: wrong service on `8000` causing CORS and `Failed to fetch`.

Still worth capturing later if those threads become active again:

- DeepSeek model replacement and composer/Inspector fixes.
- Tools / Plan mode / slash command alignment.
- Workspace integrated Harness UI decisions.
- Streaming/SSE hardening decisions and Nginx no-buffering behavior.
- Local native Postgres/service startup notes.

## Related Pages

- [[project-handoff-current-state]]
- [[deep-interview-private-harness-chain]]
