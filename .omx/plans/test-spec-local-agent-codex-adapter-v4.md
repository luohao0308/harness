# Test Spec: 本地 Agent Codex CLI Adapter V4

## Scope

验证 V4 是否把 Codex CLI 作为受限本地 Agent adapter 接入现有 local-agent bridge 和 Workspace ChatSurface，同时保持 V3 本地 host tool safety 不退化。

V4 验收范围：

- Codex adapter pairing/register/heartbeat/discovery。
- Codex bridge task ack、adapter start、assistant delta/done/error 投影。
- Codex unavailable / parse failure / non-zero exit fail closed。
- Codex resume semantics：V4 always uses context replay new session; parsed session ids are advisory only。
- Codex host side-effect tools disabled；无授权 side-effect result 继续被拒绝。
- Agent Studio / Workspace UI 正确显示 Codex enabled、installed/status/resume/host-tools-disabled。

V4 不验收 Claude Code，不验收 Codex 文件写入、shell mutation、git mutation、network、env/secret read。

## Backend Tests

### Adapter Registration

- valid pair token registers `adapter_kind=codex` and returns device credential。
- pair token hash storage、TTL、single-use、pair code UX-only semantics remain unchanged。
- default pair-token adapter scope includes `codex` alongside `fake` and `hao`。
- explicitly adapter-scoped pair token with `scope.adapters=["hao"]` rejects `adapter_kind=codex` before token consumption and still allows the intended adapter afterward。
- replayed pair token cannot register a second Codex connection。
- cross-org/cross-user token cannot register Codex connection。
- `adapter_kind=claude_code` still returns disabled/not enabled。
- invalid `protocol_version` still rejected。
- Codex registration creates audit event `local_agent.connection.register` with `adapter_kind=codex` and no raw pair token/device token。

### Capability Normalization

- Codex connection response includes:
  - `adapter_kind=codex`
  - `supports_streaming` from probe or safe default
  - `supports_resume=false`
  - `supports_cancel=false` unless implemented and tested
  - `host_tools_authorized=false`
  - `enabled_in_v4=true`
- Codex bridge self-report cannot enable host write/shell/git/network/secret risk capabilities。
- Bridge-reported `supports_resume=true` is normalized to false with `resume_mode=context_replay_new_session`。
- `risk_capabilities_json` for V4 Codex does not include `host_write`, `shell`, `git`, `network`, `env_read`, or `secret_read`。

### Binding And Send

- Codex connection can create `LocalAgentConversationBinding` using existing API。
- Binding stores or returns `resume_mode=context_replay_new_session` when native resume is unavailable。
- Sending a Workspace local message to Codex:
  - creates user `AgentMessage`
  - creates/binds Workspace Run
  - queues `LocalAgentBridgeTask`
  - payload includes `adapter_kind=codex`
  - returns idempotent response for same `client_message_id`
- non-owner cannot send executable Codex local message。
- revoked Codex connection cannot send or pull tasks。

### Bridge Task And Event Projection

- Codex bridge pull leases pending task and writes task leased event。
- Codex bridge ack marks task running and writes task ack event。
- adapter-start event is recorded with `adapter_kind=codex` and sanitized command mode。
- assistant delta events append bounded content and idempotent receipts。
- assistant done writes exactly one assistant `AgentMessage` into the bound `AgentSession`。
- duplicate Codex event id returns duplicate receipt and does not duplicate assistant content。
- assistant done before unresolved local tool state remains rejected by existing V3 guard。
- assistant error marks bridge task/run failed and does not write assistant success message。
- terminal bridge task rejects late fresh delta/done/error except duplicate receipt。

### Safety Regression

- Codex adapter cannot submit `tool_result` for shell/write/git/network/env/apply_patch without V3 authorized `tool_request_id`。
- Legacy `LocalAgentBridgeEventRequest(event_type="tool_result")` with `adapter_kind=codex` and side-effect tool name returns 409/403 and cannot create `ToolCall(SUCCESS)`。
- Codex internal command/tool observation, if parsed, can only create redacted `AgentEvent` observation and never successful authorized `ToolCall`。
- Codex adapter never triggers generic server `_execute_approved_tool_call()` / `ToolRunner.execute_approved_call()` for local host execution。
- Connection revoke terminalizes active Codex bridge tasks and rejects late events with revoked device token。
- Approval TTL/revoke behavior from V3 remains covered for codex-origin requests if any request is attempted。

### Privacy

- persisted bridge event receipt excludes:
  - raw device token
  - pair token
  - Harness bearer token
  - raw prompt containing secret-looking strings
  - `/Users/...` and `/home/...` full paths
  - oversized stdout/stderr
- Codex stdout/stderr/final-message payloads are byte-capped and secret-redacted。
- Codex unavailable errors do not dump full env or absolute home path。
- `bridge.json` does not contain raw cwd, raw prompt, command argv, stdout/stderr, or raw device token。
- `bridge.device-token` remains mode `0600`。

## CLI / Bridge Tests

### Parser And Probe

- `hao bridge pair --adapter codex` is accepted by argparse。
- `hao bridge run --adapter codex` is accepted by argparse。
- unsupported adapter still rejected by parser。
- codex probe returns installed=false when `shutil.which("codex")` returns None。
- codex probe captures version/help support without requiring provider credentials。
- codex probe failure before registration exits non-zero with user-visible unavailable reason, does not consume the pair token, does not create a connection, and does not start a daemon。

### Command Builder

- generated command includes:
  - `codex`
  - `exec`
  - `--json` when available
  - `--output-last-message <tempfile>`
  - `-C <workspace-root>`
  - `--sandbox read-only` or stricter equivalent
  - `-` prompt placeholder for stdin
- generated command does not include:
  - `--dangerously-bypass-approvals-and-sandbox`
  - `--sandbox danger-full-access`
  - raw device token
  - pair token
  - Harness bearer token
  - raw secret-looking prompt metadata in argv
  - positional prompt text
  - `resume --last`
- workspace root outside paired root is rejected before subprocess spawn。
- Codex subprocess timeout emits `assistant_error` and terminates child process。
- prompt is passed through stdin by default。
- if stdin is unavailable, prompt is passed through a mode `0600` temp input file and the file is deleted after process exit。
- if neither stdin nor private temp input is possible, command builder fails closed before spawning Codex。
- subprocess env is an allowlist, not inherited `os.environ`。
- subprocess env excludes `HARNESS_*`, `HAO_*`, `LOCAL_AGENT_*`, `*_TOKEN`, `*_SECRET`, `*_KEY`, `*_PASSWORD`, provider API key env vars, and proxy env vars。
- tests inject fake secret env vars and prove they are absent from the spawned Codex env。

### JSONL / Output Parsing

- synthetic JSONL assistant delta maps to local-agent assistant_delta event。
- synthetic final event maps to assistant_done。
- unknown JSONL records are ignored or recorded as bounded observation without failing the whole task。
- malformed JSONL with valid `--output-last-message` fallback returns assistant_done from redacted final file。
- malformed JSONL without fallback returns assistant_error。
- empty final output returns assistant_error unless a known terminal empty success fixture is explicitly allowed。
- non-zero process exit returns assistant_error even if partial deltas were emitted。

### Resume

- V4 never uses native `codex exec resume` for production bridge tasks, even if a Codex session id is parsed。
- command builder never uses `codex exec resume --last` or `codex resume --last` for production bridge tasks。
- server-normalized capabilities always set Codex `supports_resume=false` and `resume_mode=context_replay_new_session`。
- each next task starts a new `codex exec` subprocess plus bounded Harness conversation context and `resume_mode=context_replay_new_session`。
- parsed Codex session id can be persisted only as advisory adapter metadata, not as authority to resume an external Codex session。
- subprocess loads raw workspace root only from the mode `0600` local workspace-root sidecar, recomputes `workspace_identity_hash`, and rejects missing/unreadable/mismatched sidecar state before spawn。
- adapter must not derive resume cwd from API redacted `workspace_root` or daemon process cwd。

### Bridge State

- pair with Codex stores safe bridge state and separate `bridge.device-token`。
- pair with Codex stores raw workspace root only in a separate mode `0600` workspace-root sidecar; `bridge.json` stores only safe references and workspace identity metadata。
- state reload supports daemon restart without losing connection id or pending safe metadata。
- state reload does not restore raw prompts/stdout/stderr/argv, nor raw workspace root from `bridge.json`。
- API persisted payloads include redacted workspace display and `workspace_identity_hash`, but never raw workspace root。
- legacy inline token migration from V3 still works when adapter_kind=codex。

## Frontend Tests

### Agent Studio

- local Agent dialog shows Codex CLI as V4 enabled, not future disabled。
- Claude Code remains future disabled。
- Codex card shows installed/not installed state based on connection/probe capabilities。
- Codex card shows host tools disabled。
- Codex card shows resume badge:
  - context replay for V4 Codex because `supports_resume=false`
  - native resume remains future scope outside V4
- pairing command still does not call `/connections/register` from browser。
- revoke works for Codex connection and refreshes discovery list。

### Workspace

- Codex connection appears in local Agent connection selector。
- selecting Codex creates/resumes binding through existing endpoint。
- sending message uses existing `POST /api/agents/local-agent/bindings/{binding_id}/messages`。
- pending assistant shows `adapter_kind=codex` metadata and normal waiting/offline copy。
- offline Codex connection keeps readable history and queued/pending projection。
- context replay warning appears when Codex native resume is unavailable。
- viewer/operator cannot send executable Codex local message。

### Run Detail

- Event Stream shows Codex task leased/acked/adapter started/delta/done/error。
- Tool Calls panel does not show successful local host ToolCall for Codex internal operations。
- local tool approval panel remains unchanged for hao/fake V3 scenarios。

## E2E / Smoke

### `codex-unavailable`

- Force Codex probe to installed=false or run with missing executable。
- Pair behavior is deterministic: `hao bridge pair --adapter codex` fails before registration, returns a clear unavailable reason, does not consume the pair token, does not create `LocalAgentConnection`, and does not start a daemon。
- Runtime unavailable behavior for an already-registered Codex connection is deterministic: bridge task emits `assistant_error`, not success。
- No raw local path/device token in persisted payloads。

### `codex-readonly-reply`

- Use a mocked Codex subprocess or safe local fixture that emits JSONL assistant content。
- Pair `--adapter codex --once`。
- Send Workspace local message。
- Verify:
  - connection adapter_kind=codex
  - bridge task acked/running/completed
  - assistant message appears in AgentSession
  - Run events include adapter_kind=codex
  - no ToolCall success created
  - bridge state privacy invariants hold

### `codex-resume-mode`

- First task may return deterministic session id fixture; second task still starts fresh `codex exec` with bounded Harness conversation context。
- Fixture without session id also uses context replay new session。
- Verify UI/API binding resume_mode projection。
- Verify command builder rejects `--last`。
- Verify fresh execution is workspace-anchored with `subprocess.cwd=<paired workspace_root>` and pre-spawn root validation。

### `codex-side-effect-rejected`

- Simulate Codex adapter reporting side-effect `tool_result` without V3 `tool_request_id`。
- Verify backend rejects result and no `ToolCall(SUCCESS)` exists。
- Verify bridge task can only complete with assistant_error or safe assistant text after unresolved tool state is absent。

## Required Commands

```bash
cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py -q
cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py tests/test_hao_cli_v2.py -q -k "bridge or codex or adapter or pending_state_file"
cd services/api-server && .venv/bin/python -m pytest tests/test_tool_approvals.py tests/test_tool_runner.py -q
cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/cli/hao tests/test_local_agents.py tests/test_hao_cli.py tests/test_hao_cli_v2.py
cd services/api-server && .venv/bin/python -m py_compile app/api/agents/agent_local.py app/cli/hao/api_client.py app/cli/hao/main.py tests/test_local_agents.py tests/test_hao_cli.py tests/test_hao_cli_v2.py
python3 scripts/smoke-test-local-agent-v4.py --scenario codex-unavailable
python3 scripts/smoke-test-local-agent-v4.py --scenario codex-readonly-reply
python3 scripts/smoke-test-local-agent-v4.py --scenario codex-resume-mode
python3 scripts/smoke-test-local-agent-v4.py --scenario codex-side-effect-rejected
cd apps/agent-console && npm test -- AgentListPage.studio.test.tsx AgentWorkspacePage.team-launch.test.tsx ChatSurface.shell.test.tsx
cd apps/agent-console && npm run lint -- --pretty false
python3 scripts/validate-docs.py
git diff --check
```

## Acceptance Evidence

- Backend proves Codex is supported while Claude remains disabled。
- CLI proves Codex parser/probe/command builder does not generate dangerous sandbox bypass or ambiguous resume。
- Bridge proves Codex assistant output projects through existing local-agent event/message path。
- Safety tests prove Codex cannot create successful side-effect ToolCall without V3 authorization。
- Frontend proves Codex appears in the same Agent Studio and Workspace local Agent surfaces with correct disabled capability warnings。
- Privacy tests prove bridge state and persisted payloads exclude raw tokens, raw paths, secrets and oversized process output。

## Out Of Scope For V4

- Claude Code adapter execution。
- Codex write/apply_patch/git/network/env/secret capability。
- Stable pre-tool authorization for Codex internal tools。
- Multi-device local Codex collaboration。
- Production guarantee for computer shutdown continuation beyond daemon reconnect semantics。
