# Frontend Goal Auth Error Compact UI

Category: session-log
Tags: `agent-console`, `workspace`, `goal-mode`, `model-auth`, `frontend-ui`, `browser-smoke`

## Summary

Agent Workspace `追踪目标模式` now treats model-key 401/403 failures as model configuration errors instead of vague goal blockers. Completed writing/reply/summary-style goals stream the visible final deliverable into the assistant bubble instead of only saying `目标已达成。` The goal progress row is smaller, and `编辑目标` uses the shared light project dialog instead of the oversized dark modal.

## Root Cause

The reproduced failed goal run had a real upstream DeepSeek HTTP 401 for the stored key suffix `****9b48`.

Executor recorded `MODEL_CALL_FAILED` and `TASK_FAILED`, but the goal stream only looked at the terminal `FAILED` status and emitted:

```text
目标暂未达成，遇到需要处理的阻塞。
```

That hid the actionable model-auth cause from the Workspace error UI.

A follow-up screenshot showed a separate failure for a pure writing goal:

```text
目标暂未达成： agent 客服 is not attached to capability read_file
```

That happened because a writing/story goal could still honor a generic `read_file` tool hint from the planner. The Agent had the artifact tool attached by the goal executor, but not `read_file`, so the goal failed before any final content could be generated.

The first visible-output implementation also used `AuditedModelGateway.complete()` after the run ended. That made the assistant bubble update as one blocking blob instead of a true streaming response.

A second follow-up showed the final answer streaming only after the goal row already said `目标已完成`. The SSE order was wrong for the user-visible state: backend emitted terminal completed `goal_progress` before final answer `delta` chunks.

A later UX follow-up removed the Run/Goal composer submit confirmation because users expect Enter to immediately submit the selected mode.

## Changes

- `services/api-server/app/api/agents/agent_chat/streaming.py`
  - extracts the newest useful failure detail from `AgentEvent`;
  - skips generic `Task failed: N step(s) failed` summaries when a better event exists;
  - classifies API-key HTTP 401/403 details as `model_auth`;
  - emits goal `error` SSE for model-auth failures, preserving the existing Agent Console model-settings action.
  - synthesizes the visible final deliverable for completed writing/reply/summary-style goals through `AuditedModelGateway.stream(response_format="text")`;
  - forwards every final-output model chunk as its own assistant `delta` event and uses stream usage metadata when available.
  - emits a `running/generating` goal progress event before final-output deltas, then emits the completed progress event only after all final-output chunks have streamed.
- `services/api-server/app/agents/executor.py`
  - folds the task title and goal into default tool selection;
  - treats pure writing/reply/story goals without project/file-reading intent as artifact-output work;
  - ignores generic `read_file` / `list_files` hints for those pure content goals and chooses `mcp_artifact_put`, preserving the capability attachment boundary.
- `apps/agent-console/src/features/agents/components/ChatSurface.tsx`
  - further shrinks the goal progress row above the composer;
  - replaces the old dark goal-edit modal with shared `ConfigDialog`;
  - keeps edit save/cancel, Escape close, and Cmd/Ctrl+Enter save behavior.
  - removes the second confirmation dialog from Run and Goal composer submission.
- `apps/agent-console/src/features/agents/components/ChatModeBanner.tsx`
  - updates Plan-Act Run mode copy so it no longer tells users to confirm creation.
- `apps/agent-console/src/components/ui/input.tsx`
  - makes `Textarea` support refs so compact dialogs can autofocus consistently.

## Validation

```text
cd services/api-server && .venv/bin/python -m pytest \
  tests/test_agents.py::test_agent_workspace_goal_mode_surfaces_model_auth_failure_as_error \
  tests/test_agents.py::test_agent_workspace_goal_mode_executes_without_plan_artifact \
  tests/test_agents.py::test_agent_workspace_goal_mode_sanitizes_unexpected_docker_runtime_error -q
3 passed

cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_chat/streaming.py tests/test_agents.py
passed

python3 -m py_compile services/api-server/app/api/agents/agent_chat/streaming.py services/api-server/tests/test_agents.py
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" \
  npx vitest run src/features/agents/__tests__/useChatStream.test.tsx src/features/agents/__tests__/ChatSurface.shell.test.tsx
39 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" \
  npx tsc --noEmit --pretty false --types vite/client --skipLibCheck --jsx react-jsx \
  --lib DOM,DOM.Iterable,ES2022 --module ESNext --moduleResolution Bundler --target ES2020 \
  --esModuleInterop --allowSyntheticDefaultImports \
  src/components/ui/input.tsx \
  src/features/agents/components/ChatSurface.tsx \
  src/features/agents/hooks/useChatStream.ts \
  src/features/tasks/api.ts
passed
```

Local service and browser checks:

```text
tmux new-session -d -s harness_api ...
curl --noproxy '*' http://127.0.0.1:8000/health
{"status":"ok","service":"api-server"}

Playwright browser smoke on http://127.0.0.1:5173/agents/default/workspace with mocked goal model_auth SSE:
row 712x48
dialog 512x343
dialogBg rgb(255, 255, 255)
old `目标模型` label absent

Direct API SSE POST /api/agents/default/runs/chat/stream with the invalid DeepSeek key:
emitted `event: error` with `kind: model_auth`
did not emit `目标暂未达成，遇到需要处理的阻塞`

Backend visible-output regression:
cd services/api-server && .venv/bin/python -m pytest \
  tests/test_agents.py::test_agent_workspace_goal_mode_returns_visible_completed_output \
  tests/test_agents.py::test_agent_workspace_goal_mode_surfaces_model_auth_failure_as_error \
  tests/test_agents.py::test_agent_workspace_goal_mode_executes_without_plan_artifact -q
3 passed

Browser smoke with mocked completed goal SSE:
final story text rendered in the main assistant bubble
bottom goal row stayed status-only as `目标已完成`

Follow-up backend regression:
cd services/api-server && .venv/bin/python -m pytest \
  tests/test_agents.py::test_agent_workspace_goal_mode_returns_visible_completed_output \
  tests/test_agents.py::test_agent_workspace_goal_mode_writing_goal_ignores_unattached_read_hint \
  tests/test_agents.py::test_agent_workspace_goal_mode_surfaces_model_auth_failure_as_error \
  tests/test_agents.py::test_agent_workspace_goal_mode_uses_artifact_tool_without_sandbox -q
4 passed

Wider goal-mode regression:
cd services/api-server && .venv/bin/python -m pytest \
  tests/test_agents.py::test_agent_workspace_goal_mode_executes_without_plan_artifact \
  tests/test_agents.py::test_agent_workspace_goal_mode_continues_paused_existing_plan \
  tests/test_agents.py::test_agent_workspace_goal_mode_surfaces_model_auth_failure_as_error \
  tests/test_agents.py::test_agent_workspace_goal_mode_returns_visible_completed_output \
  tests/test_agents.py::test_agent_workspace_goal_mode_writing_goal_ignores_unattached_read_hint \
  tests/test_agents.py::test_agent_workspace_goal_mode_uses_artifact_tool_without_sandbox \
  tests/test_agents.py::test_agent_workspace_goal_mode_reports_sandbox_runtime_unavailable \
  tests/test_agents.py::test_agent_workspace_goal_mode_sanitizes_unexpected_docker_runtime_error -q
8 passed

Backend lint/compile:
cd services/api-server && .venv/bin/python -m ruff check \
  app/agents/executor.py app/api/agents/agent_chat/streaming.py tests/test_agents.py
passed

python3 -m py_compile \
  services/api-server/app/agents/executor.py \
  services/api-server/app/api/agents/agent_chat/streaming.py \
  services/api-server/tests/test_agents.py
passed

Frontend stream reducer/hook:
cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" \
  npx vitest run src/features/agents/__tests__/useChatStream.test.tsx
16 passed

Local API restart:
curl --noproxy '*' http://127.0.0.1:8000/health
{"status":"ok","service":"api-server"}

Follow-up event-order regression:
cd services/api-server && .venv/bin/python -m pytest \
  tests/test_agents.py::test_agent_workspace_goal_mode_returns_visible_completed_output \
  tests/test_agents.py::test_agent_workspace_goal_mode_writing_goal_ignores_unattached_read_hint \
  tests/test_agents.py::test_agent_workspace_goal_mode_executes_without_plan_artifact \
  tests/test_agents.py::test_agent_workspace_goal_mode_surfaces_model_auth_failure_as_error -q
4 passed

Wider goal-mode regression after event-order fix:
cd services/api-server && .venv/bin/python -m pytest \
  tests/test_agents.py::test_agent_workspace_goal_mode_executes_without_plan_artifact \
  tests/test_agents.py::test_agent_workspace_goal_mode_continues_paused_existing_plan \
  tests/test_agents.py::test_agent_workspace_goal_mode_surfaces_model_auth_failure_as_error \
  tests/test_agents.py::test_agent_workspace_goal_mode_returns_visible_completed_output \
  tests/test_agents.py::test_agent_workspace_goal_mode_writing_goal_ignores_unattached_read_hint \
  tests/test_agents.py::test_agent_workspace_goal_mode_uses_artifact_tool_without_sandbox \
  tests/test_agents.py::test_agent_workspace_goal_mode_reports_sandbox_runtime_unavailable \
  tests/test_agents.py::test_agent_workspace_goal_mode_sanitizes_unexpected_docker_runtime_error -q
8 passed

Backend stream order lint/compile:
cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_chat/streaming.py tests/test_agents.py
passed

python3 -m py_compile \
  services/api-server/app/api/agents/agent_chat/streaming.py \
  services/api-server/tests/test_agents.py
passed

Frontend Run/Goal no-confirm regression:
cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" \
  npx vitest run src/features/agents/__tests__/ChatSurface.shell.test.tsx
24 passed

Frontend targeted TypeScript:
cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" \
  npx tsc --noEmit --pretty false --types vite/client --skipLibCheck --jsx react-jsx \
  --lib DOM,DOM.Iterable,ES2022 --module ESNext --moduleResolution Bundler --target ES2020 \
  --esModuleInterop --allowSyntheticDefaultImports \
  src/features/agents/components/ChatSurface.tsx \
  src/features/agents/components/ChatModeBanner.tsx
passed
```

## Notes

This does not make an invalid provider key succeed. It makes the failure actionable: the UI now shows `模型密钥无效` and links to model settings, while the goal row remains visible as the failed pursuit state.

For completed goals, the output location is the normal assistant message bubble in the conversation, and final-output chunks arrive as normal `delta` events. While those chunks stream, the goal row remains `running/generating`; it switches to completed only after the final answer stream finishes. The compact goal row above the composer is intentionally status-only.
