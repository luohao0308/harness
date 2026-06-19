---
title: Anti-Patterns
status: living
updated: 2026-06-20
maintained_by: human-seed
---

# Anti-Patterns

Design rules and "never do this" patterns extracted from omx_wiki session logs.
Each entry names the anti-pattern, explains why it's wrong, and gives the correct approach.

---

## AP-001: Trusting client-provided cache content without server validation

- **Anti-pattern:** Frontend sends an `existing_summary` hint to `/context/compress` and backend treats it as an accepted cache entry without checking session ownership or freshness.
- **Why it's wrong:** Clients can inject stale, cross-session, or adversarial summary content, leading to hallucinations or privacy leakage between sessions.
- **Do instead:** Keep DB-backed `workspace_context_caches` as the authoritative store. Accept client hints only as optimization signals ("try reusing this id"). Always validate ownership, timestamp, and session membership before trusting the content. Recompute if validation fails.
- **Source:** `omx_wiki/project-handoff-current-state.md`

---

## AP-002: Lazy runtime backfill of capabilities from legacy JSON

- **Anti-pattern:** At runtime, if `agent_capability_attachments` is empty, infer the capability list from the legacy `Agent.tools_json` field and treat it as current state.
- **Why it's wrong:** Legacy JSON becomes the runtime source of truth, making migration to immutable versioned capabilities impossible without continuous backfill logic. Any change to the legacy field breaks deterministic behavior.
- **Do instead:** Populate `agent_capability_attachments` once during migration. At runtime, use only attachment rows. Reject operations fail-closed if no attachments exist. Mark `tools_json` as migration-input-only after migration.
- **Source:** `omx_wiki/project-handoff-current-state.md`

---

## AP-003: Mixing server-side and client-side secret/capability resolution

- **Anti-pattern:** Both frontend and backend resolve secrets, API keys, or capabilities. Client-side storage persists raw values. Server falls back to env when frontend-provided values are missing.
- **Why it's wrong:** Multiple sources of truth and multiple paths for sensitive data leakage. Testing becomes brittle because behavior depends on both layers simultaneously.
- **Do instead:** Designate one authoritative store — encrypted backend storage. Frontend stores only opaque refs (e.g., `secret://dify`). Server owns resolution, fallback chain (user → org → env), and lifecycle. Frontend never holds raw secret values.
- **Source:** `omx_wiki/project-handoff-current-state.md`

---

## AP-004: Operating on resources with onboarding_confirmed=false

- **Anti-pattern:** Allow bind, send, pull-task, or tool-request operations on resources with `onboarding_confirmed=false` or `status=pending_confirmation`, treating missing flags as "not yet confirmed but OK to use."
- **Why it's wrong:** Users intend unconfirmed resources to be dormant. Executing operations on them creates hidden side effects and race conditions. Example: user unchecked Codex in the dialog, but the connection still pulls tasks because the gate only checks an inferred status.
- **Do instead:** Every executable operation must explicitly require `onboarding_confirmed=true` AND non-`pending_confirmation` status. Return 403 or 409 if either is violated. Offer recovery paths (re-confirm, re-register) but never auto-promote pending states.
- **Source:** `omx_wiki/project-handoff-current-state.md`

---

## AP-005: Emitting terminal SSE events before async content is fully delivered

- **Anti-pattern:** Emit a `completed` or other terminal status event in the SSE stream before all related content chunks (final answer text, goal summary, artifact metadata) have been delivered to the client.
- **Why it's wrong:** Frontend receives the terminal state first and may close subscriptions, reset UI, or navigate before the final content arrives. Users see incomplete results or race conditions. State and content diverge in the UI.
- **Do instead:** Always order: all content deltas → all metadata → terminal completion event. Never rely on thread scheduling or request ordering. Treat "content before completion" as a hard invariant, not a best-effort.
- **Source:** `omx_wiki/session-2026-06-19-frontend-goal-auth-error-compact-ui.md`

---

## AP-006: Honoring planner tool hints without checking capability attachments

- **Anti-pattern:** LLM planner outputs hints like "read this file" or "search the web"; executor honors those hints without checking whether the agent has the hinted tool attached.
- **Why it's wrong:** Plan fails at runtime when execution discovers missing attachments. The planner cannot self-correct without access to the agent's current capabilities.
- **Do instead:** Planner must receive the agent's actual capability list at plan time. Derive tool selection from goal + context, filtered to available capabilities. Fail fast if the goal cannot be achieved with available tools. Never allow hint-driven fallbacks that bypass attachment checks.
- **Source:** `omx_wiki/session-2026-06-19-frontend-goal-auth-error-compact-ui.md`

---

## AP-007: Hardcoding dev values (localhost, tokens, placeholders) in production paths

- **Anti-pattern:** Leave hardcoded `127.0.0.1:8000`, `localhost`, dev bearer token `dev-engineer-token`, or placeholder secret `changeme` in production-path code without a production-mode guard.
- **Why it's wrong:** Fallback to localhost in production silently routes to nothing instead of failing loudly. Dev tokens bypass auth. Production builds that embed dev values are not actually deployable.
- **Do instead:** Fail fast at startup: validate that `AUTH_JWT_SECRET` is set and non-placeholder. Require explicit env config for API base URLs. Guard dev-only code (tokens, fixtures, mocks) with `if DEBUG` or test-only imports. Never fall back to localhost in production.
- **Source:** `omx_wiki/project-handoff-current-state.md`

---

## AP-008: Deleting workspace conversation history instead of compressing it

- **Anti-pattern:** Delete or discard old messages to save storage. Replace old context with a summary and remove the originals.
- **Why it's wrong:** Deleting history breaks audit trails, eval evidence chains, and recovery paths. Compression summaries can hallucinate or lose nuance. Once deleted, the original context cannot be recovered for debugging or retraining.
- **Do instead:** Keep all raw history immutable. Compression generates a new summary message that references the original range — original messages remain in the store. Use DB indexes and lazy loading to manage performance without deletion. Compression affects only future prompt payloads, not stored history.
- **Source:** `omx_wiki/project-handoff-current-state.md`
