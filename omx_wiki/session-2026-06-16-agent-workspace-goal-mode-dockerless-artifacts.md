# Agent Workspace Goal Mode Dockerless Artifacts

Category: `session-log`

Tags: `agent-workspace`, `goal-mode`, `sandbox`, `mcp`, `artifacts`, `docker`

## Summary

Agent Workspace `追踪目标模式` no longer forces Docker-backed sandbox execution for ordinary artifact or writing work.

The reported failure shape was:

```text
Error while fetching server API version: ('Connection aborted.', FileNotFoundError(2, 'No such file or directory'))
```

Root cause: goal mode forced `run.enable_sandbox = True`; the executor then selected Docker-backed `write_file` for artifact-like writing steps. On a local machine where Docker Desktop or the Docker daemon was unavailable, WarmPool acquisition leaked the Docker SDK API-version failure into the Run.

## Changes

- `AgentChatStreamRequest` now exposes `enable_sandbox` and `enable_network`, both defaulting to `false`.
- Goal-mode Run creation preserves the request sandbox/network flags instead of forcing sandbox on.
- Goal-mode Runs ensure `mcp_artifact_put` is attached before capability snapshotting.
- Executor default tool selection sends ordinary writing/artifact expectations to `mcp_artifact_put`; `write_file` is used only for explicit sandboxed artifact work.
- `mcp_artifact_put` is now low risk while retaining `audit_level="critical"`, so default policy can execute Harness artifact writes without admin approval or Docker.
- Sandbox acquisition failures are caught and converted to a recoverable `STEP_FAILED` event with `permission_boundary=sandbox_runtime` and a clear `Sandbox runtime unavailable...` message.
- Stream-level goal-mode fallback sanitizes unexpected Docker API-version exceptions if they escape a lower-level WarmPool path.
- The local browser repro after the first code fix was a stale 8000 API process that had not loaded the new `AgentChatStreamRequest` schema; restarting the API made `enable_sandbox/default=false` and `enable_network/default=false` visible in OpenAPI.

## Validation

- `cd services/api-server && .venv/bin/python -m pytest tests/test_agents.py -q` -> 71 passed
- Goal-mode Dockerless focused regression -> 3 passed
- `cd services/api-server && .venv/bin/python -m pytest tests/test_tasks.py -q` -> 14 passed
- Tool focused tests -> 5 passed
- Targeted Ruff for touched backend/test files -> passed
- `python3 -m py_compile` for touched backend/test files -> passed
- `curl --noproxy '*' http://127.0.0.1:8000/openapi.json` -> `AgentChatStreamRequest` exposes `enable_sandbox/default=false` and `enable_network/default=false` after local API restart
- `python3 scripts/validate-docs.py` -> passed after final docs writeback
- `git diff --check` -> passed after final docs writeback

## Acceptance

- Artifact-only goal work can complete without Docker.
- Explicitly sandboxed goal work still respects sandbox policy.
- If Docker is intentionally required but unavailable, the Run records or streams a clear sandbox-runtime failure instead of leaking raw Docker SDK connection text.
