---
title: Error Registry
status: living
updated: 2026-06-20
maintained_by: auto+human-seed
---

# Error Registry

Symptom → root cause → fix. Extracted from omx_wiki session logs.
AI agents append new entries via session notes; do not delete entries.

Format per entry: Symptom / Root Cause / Fix / Source.

---

## db / tests

### ERR-001: SQLite TestClient "no such table" despite create_all() passing

- **Symptom:** Backend TestClient tests fail with `no such table: agents` or `no such table: system_settings` even though `Base.metadata.create_all()` runs without error.
- **Root Cause:** `sqlite+pysqlite:///:memory:` with the default connection pool creates one connection for schema creation and a different connection for TestClient request handling. SQLite in-memory databases are isolated per connection — the request handler sees an empty database.
- **Fix:** Use `sqlite+pysqlite://` with `poolclass=StaticPool` in test fixtures so that schema creation and TestClient requests share the same connection.
- **Source:** `omx_wiki/session-2026-06-16-local-dev-testclient-sqlite-staticpool.md`

---

## agents / streaming

### ERR-002: Streaming leaks pre-tool XML markers into user messages

- **Symptom:** Chat SSE sends raw assistant text chunks that include XML function-call markers (`<call>`, search query hints, `[D` citation-style prefixes) before tool results are available. Model internal reasoning appears in the user-facing message.
- **Root Cause:** Text streaming fires immediately without buffering to detect post-processing signals. The model emits partial text that is still deciding whether to call a tool.
- **Fix:** Buffer model chunks when the text shows signals such as `<call>`, `search:`, or `[D` patterns. Hold chunks until the signal resolves (tool call or plain text confirmed), then emit all at once.
- **Source:** `omx_wiki/session-2026-06-16-local-dev-testclient-sqlite-staticpool.md`

### ERR-006: Goal completion SSE event fires before content chunks stream

- **Symptom:** Frontend goal row shows "目标已完成" while final answer chunks are still streaming into the assistant bubble — completion appears before visible content.
- **Root Cause:** Backend emits the terminal `goal_progress` SSE event before synthesizing and streaming final-output model chunks for completed writing/reply goals.
- **Fix:** Always order: emit all content deltas first → emit terminal completion event last. Use a `running/generating` intermediate progress event before final-output chunks begin.
- **Source:** `omx_wiki/session-2026-06-19-frontend-goal-auth-error-compact-ui.md`

### ERR-010: Goal uses complete() instead of stream() — content arrives as one blob

- **Symptom:** Goal final output uses `AuditedModelGateway.complete()` after the run ends. Assistant bubble updates as a single blocking blob instead of streaming in real time.
- **Root Cause:** `complete()` is called outside the streaming request lifecycle, forcing all chunks to buffer and deliver at once.
- **Fix:** Use `AuditedModelGateway.stream(response_format="text")` during the original stream lifecycle. Forward each chunk as its own `delta` SSE event. Use stream usage metadata when available.
- **Source:** `omx_wiki/session-2026-06-19-frontend-goal-auth-error-compact-ui.md`

---

## agents / workspace / orchestration

### ERR-003: Workspace subagent created without specialist binding

- **Symptom:** Agent Workspace subagent request creates an uninspectable subagent with no role, prompt, capabilities, or structured output schema.
- **Root Cause:** `_apply_workspace_orchestration(mode="subagent")` calls `SubagentManager.spawn()` without a `specialist` argument — no specialist snapshot is created.
- **Fix:** Query `SubagentSpecialistRegistry` with workspace heuristics (keyword matching, user request hints, fallback defaults). Pass the selected specialist into `SubagentManager.spawn(specialist=...)`.
- **Source:** `omx_wiki/session-2026-06-19-agent-workspace-subagent-specialist-binding.md`

---

## agents / model-gateway / error handling

### ERR-004: HTTP 401 from model API buried in generic "goal failed" message

- **Symptom:** Goal pursuit fails with generic "目标暂未达成，遇到需要处理的阻塞。" — user cannot tell that the DeepSeek API key is invalid without diving into logs.
- **Root Cause:** Backend only checks terminal `FAILED` status and emits a fallback summary. It does not extract the actionable `MODEL_CALL_FAILED` event detail showing the upstream HTTP 401 for a specific key.
- **Fix:** Extract the newest useful failure detail from `AgentEvent` logs. Classify HTTP 401/403 as `kind: model_auth`. Emit a distinct SSE `error` event that Agent Console renders with a model-settings action link.
- **Source:** `omx_wiki/session-2026-06-19-frontend-goal-auth-error-compact-ui.md`

---

## agents / executor / goal-mode

### ERR-005: Pure writing goal fails because planner hints read_file on unattached capability

- **Symptom:** Pure writing/story goal fails before generating content with `agent X is not attached to capability read_file` because the planner output hints generic file-reading intent.
- **Root Cause:** Executor honors generic `read_file` / `list_files` hints from the planner without checking if the agent has those tools attached. Pure content-generation goals only need `mcp_artifact_put`.
- **Fix:** Feed the agent's actual capability list into the planner. For pure writing/reply/summary goals, ignore generic `read_file` hints and select `mcp_artifact_put` instead. Fail fast if the goal cannot be achieved with available tools.
- **Source:** `omx_wiki/session-2026-06-19-frontend-goal-auth-error-compact-ui.md`

---

## agents / local-agents / session

### ERR-007: Switching local agent bindings leaks previous agent's context

- **Symptom:** Switching between local agent bindings (e.g., Claude Code → hao → Claude Code) causes the new agent to see leftover context/message history from the previous agent.
- **Root Cause:** Frontend hydration restores a stale binding hint. Backend context replay filters persisted messages only by `source`/`agent_id` without checking `binding_id`/`connection_id`/`session_id`.
- **Fix:** Require exact binding/connection/session metadata match for all hydration paths (context truncation, Run links, agent workspace, message restoration). Enforce one active local agent per AgentSession with a unique constraint. Migrate historical dirty states to `conflict`.
- **Source:** `omx_wiki/project-handoff-current-state.md`

---

## local-agents / codex / config

### ERR-009: Codex CLI fails to start — "unknown field state" in hooks.json

- **Symptom:** Codex CLI startup fails with `failed to parse hooks config ~/.codex/hooks.json: unknown field state, expected hooks`.
- **Root Cause:** Legacy OMX hook package serialized hook trust state into the top-level `state` object in `~/.codex/hooks.json`. Codex 0.141.0+ rejects unknown fields at the root level.
- **Fix:** Regenerate `~/.codex/hooks.json` to contain only the `hooks` root with managed events. Move trust state to `~/.codex/config.toml` under `[hooks.state]`. Upgrade OMX/Codex to match schema expectations.
- **Source:** `omx_wiki/project-handoff-current-state.md`

### ERR-012: Codex subprocess fails with "not running in trusted directory"

- **Symptom:** Codex CLI subprocess fails with `not running in trusted directory` when started from a workspace root that is not a git repository.
- **Root Cause:** `--skip-git-repo-check` flag is not passed before stdin in the subprocess invocation. Codex enforces git trust even in temporary workspace directories.
- **Fix:** Add `--skip-git-repo-check` before the stdin argument when the adapter supports it. Raise `UnavailableAdapterError` / skip gracefully if the Codex version does not support the flag.
- **Source:** `omx_wiki/project-handoff-current-state.md`
