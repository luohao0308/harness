# Session 2026-05-13 Workspace Browser Smoke

Category: `session-log`

Tags: `workspace`, `browser-smoke`, `playwright`, `agent-console`, `local-dev`, `cors`, `git`

## Summary

The Agent Workspace demo shell now has browser-level smoke coverage and tighter console chrome behavior for the product message:

```text
Model + Harness = Agent
```

The core UX constraint remains: chat space is primary, and Harness evidence should stay light as header chips or compact panels.

## Product Outcome

- Workspace route: `/agents/default/workspace`
- Browser smoke URL: `http://127.0.0.1:5177/agents/default/workspace`
- Backend URL: `http://127.0.0.1:8000`
- Header concept: `Model + Harness = Agent`
- Top model picker and slash `/model` picker are separate interaction surfaces.
- Top Tools panel shows tool capabilities only.
- Composer settings popover owns Add files, Plan mode, and Plugins/MCP.
- Plugins/MCP expands to MCP functions such as `github.search`.
- Popovers are compact and close on outside click.
- Workspace and narrow layout keep chrome compact so composer/chat remains usable at 390px.

## Files Added Or Updated

- `apps/agent-console/playwright.config.ts`
- `apps/agent-console/e2e/agent-workspace.smoke.spec.ts`
- `apps/agent-console/package.json`
- `apps/agent-console/package-lock.json`
- `apps/agent-console/README.md`
- `apps/agent-console/src/app/ConsoleShell.tsx`
- `apps/agent-console/src/app/__tests__/ConsoleShell.render.test.tsx`
- `docs/工作日志/archive/task-progress-legacy.md`
- `docs/development/ai/task-progress.yaml`
- `.gitignore`

## Browser Smoke Coverage

Command path:

```bash
cd apps/agent-console
npm run e2e:install
npm run e2e:smoke
npm run e2e:smoke:headed
```

Covered behaviors:

- Header Model picker opens compact list.
- ArrowUp/ArrowDown plus Enter can select a model.
- Top Tools panel shows tool capabilities and excludes Plugins/MCP.
- Composer settings popover shows Add photos and files, Plan mode, and Plugins/MCP.
- Composer settings has no visible close button and closes by outside click.
- Plugins/MCP reveals MCP function entries.
- `/model ` opens the composer-level model picker, distinct from the header picker.
- Plan mode changes the composer placeholder.
- Backend connection error display remains visible when the chat stream is deliberately failed.
- 390px viewport has no horizontal overflow and keeps composer/send usable.

## Local Backend Diagnosis

Observed frontend error:

```text
API_BASE_URL: http://127.0.0.1:8000 · Failed to fetch
```

Root cause:

- Port `8000` was occupied by another project: `/Users/luohao/Desktop/agent_workspace/hermes_free/backend`.
- The process was `uvicorn main:app --host 0.0.0.0 --port 8000`.
- It returned service identity `AI Workflow Control Plane`, not Harness API.
- CORS preflight from `http://127.0.0.1:5177` returned `Disallowed CORS origin`.

Fix:

```bash
cd services/api-server
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Verification:

```text
GET /health -> {"status":"ok","service":"api-server"}
OPTIONS /api/tasks from Origin http://127.0.0.1:5177 -> 200 OK
GET /api/tasks with dev token -> returned task list
Frontend /agents/default/workspace -> 200 OK
```

## Validation Record

Latest validation from this pass:

```text
cd apps/agent-console && npm run e2e:smoke -> 2 passed
cd apps/agent-console && npm test -> 96 passed
cd apps/agent-console && npm run lint -> passed
cd apps/agent-console && npm run build -> passed
cd services/api-server && .venv/bin/python -m pytest tests/test_cors.py -> 2 passed
python3 scripts/validate-docs.py -> passed
git diff --check -> passed
```

## Git Record

Pushed to `origin/main`:

```text
3fff603 Record Workspace browser hardening progress
ced5be0 Document Workspace browser smoke flow
a3903d2 Cover Workspace demo controls in browser smoke
7eaeab3 Add Workspace browser smoke tooling
9e8172f Keep Workspace chrome compact
```

Push range:

```text
2bfa627..3fff603 main -> main
```

## Deferred Work

- Broader browser e2e coverage for non-Workspace routes remains deferred.
- Current browser smoke intentionally focuses on the demo-critical Agent Workspace shell.

## Related Pages

- [[project-handoff-current-state]]
- [[workspace-demo-ready-constraints]]
- [[local-dev-backend-port-cors]]
- [[session-2026-05-13-workspace-browser-smoke]]
