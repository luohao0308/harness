# Workspace Demo-Ready Constraints

Category: `decision`

Tags: `workspace`, `demo-ready`, `model-harness-agent`, `chat-first`, `browser-smoke`

## Decision

After Stage 07, the selected Workspace phase is productization: make `/agents/:agentId/workspace` demo-ready so users immediately understand:

```text
Model + Harness = Agent
```

This is not a new backend capability phase. It is a first-impression and interaction clarity phase.

## Source Artifacts

- `.omx/interviews/workspace-demo-ready-model-harness-agent-20260512T142202Z.md`
- `.omx/specs/deep-interview-workspace-demo-ready-model-harness-agent.md`
- `.omx/plans/prd-workspace-demo-ready-model-harness-agent.md`
- `.omx/plans/test-spec-workspace-demo-ready-model-harness-agent.md`
- `.omx/plans/test-spec-browser-e2e-smoke-agent-workspace.md`
- [[session-2026-05-13-workspace-browser-smoke]]

## Accepted Constraints

- Chat space is the absolute priority.
- Harness evidence must be lightweight: header/chip-level, not panel-level.
- First-screen proof focuses on:
  - current Model;
  - Tools/MCP capability;
  - Run status or Run entry.
- Eval, Observability, full Trace/Replay, and full Sandbox details remain secondary surfaces.
- The first viewport must not become a dashboard.
- Existing Workspace behavior should remain reachable: conversation history, slash commands, model selection, tool mentions, Inspector, Run Detail, export, clear, streaming, and Plan approval behavior.

## Interaction Contracts From Recent Work

- Header model picker and composer `/model` picker are distinct surfaces.
- Header Tools shows current tool capabilities.
- Composer settings owns Add files, Plan mode, and Plugins/MCP.
- Plugins/MCP shows MCP functions, for example `github.search`.
- Popovers are compact and close on outside click.
- No visible close button is required on these compact popovers.
- At 390px width, the Workspace must avoid horizontal overflow and keep composer/send usable.

## Browser Smoke

Command path:

```bash
cd apps/agent-console
npm run e2e:install
npm run e2e:smoke
npm run e2e:smoke:headed
```

Current smoke covers:

- `Model + Harness = Agent` visible.
- Header model picker keyboard selection.
- Top Tools panel excludes Plugins/MCP.
- Composer settings includes Add photos and files, Plan mode, Plugins/MCP.
- `/model` opens composer model picker.
- Plan mode placeholder changes.
- Deliberate backend stream failure shows recoverable connection error.
- 390px overflow and popover placement checks.

## Related Pages

- [[project-handoff-current-state]]
- [[session-2026-05-13-workspace-browser-smoke]]
- [[local-dev-backend-port-cors]]
