# Test Spec: 本地 Agent Claude Code Adapter V5

## Scope

验证 V5 是否把 Claude Code 作为受限本地 Agent adapter 接入现有 local-agent bridge 和 Workspace ChatSurface，同时保持 V3/V4 安全边界不退化。

V5 验收范围：

- Claude Code adapter pairing/register/heartbeat/list/revoke。
- Claude Code executable probe and fail-before-register behavior。
- Claude Code bridge task ack、adapter start、assistant delta/done/error 投影。
- Claude Code unavailable / auth unavailable / parse failure / non-zero exit fail closed。
- Claude Code resume semantics：V5 always uses context replay new session; parsed session ids are advisory only。
- Claude Code host side-effect tools disabled；无授权 side-effect result 继续被拒绝。
- Agent Studio / Workspace UI 正确显示 Claude Code enabled、installed/status、context replay、host-tools-disabled、auth unavailable warning。

V5 不验收 Claude Code 文件写入、shell mutation、git mutation、network、env/secret read、native resume、MCP permission prompt bridge、Agent SDK callback、真实 provider credential smoke。

## Backend Tests

### Adapter Registration

- valid pair token registers `adapter_kind=claude_code` and returns device credential。
- pair token hash storage、TTL、single-use、pair code UX-only semantics remain unchanged。
- default pair-token adapter scope includes `claude_code` alongside `fake`、`hao`、`codex`。
- explicitly adapter-scoped pair token with `scope.adapters=["codex"]` rejects `adapter_kind=claude_code` before token consumption and still allows Codex afterward。
- replayed pair token cannot register a second Claude Code connection。
- cross-org/cross-user token cannot register Claude Code connection。
- invalid `protocol_version` still rejected。
- unsupported adapter names still return not enabled。
- Claude Code registration creates audit event `local_agent.connection.register` with `adapter_kind=claude_code` and no raw pair token/device token/raw Claude credential。

### Capability Normalization

- Claude Code connection response includes:
  - `adapter_kind=claude_code`
  - `supports_streaming=true`
  - `supports_resume=false`
  - `supports_cancel=false`
  - `host_tools_authorized=false`
  - `enabled_in_v5=true`
  - `resume_mode=context_replay_new_session`
  - `execution_mode=headless_bare_no_session_no_tools`
- Claude Code bridge self-report cannot enable host write/shell/git/network/env/secret/MCP/plugin/hook/subagent/browser risk capabilities。
- Bridge-reported `supports_resume=true` is normalized to false。
- `risk_capabilities_json` for V5 Claude Code does not include `host_write`, `shell`, `git`, `network`, `env_read`, `secret_read`, `mcp`, `plugin`, `hook`, or `subagent`。

### Binding And Send

- Claude Code connection can create `LocalAgentConversationBinding` using existing API。
- Binding stores/returns `resume_mode=context_replay_new_session`。
- Sending a Workspace local message to Claude Code:
  - creates user `AgentMessage`
  - creates/binds Workspace Run
  - queues `LocalAgentBridgeTask`
  - payload includes `adapter_kind=claude_code`
  - payload includes bounded Harness conversation context
  - payload includes `workspace_identity_hash`
  - returns idempotent response for same `client_message_id`
- non-owner cannot send executable Claude Code local message。
- revoked Claude Code connection cannot send or pull tasks。

### Bridge Task And Event Projection

- Claude Code bridge pull leases pending task and writes task leased event。
- Claude Code bridge ack marks task running and writes task ack event。
- adapter-start event is recorded with `adapter_kind=claude_code`, safe execution mode, and sanitized command mode。
- assistant delta events append bounded content and idempotent receipts。
- assistant done writes exactly one assistant `AgentMessage` into the bound `AgentSession`。
- duplicate Claude Code event id returns duplicate receipt and does not duplicate assistant content。
- assistant done before unresolved local tool state remains rejected by existing V3 guard。
- assistant error marks bridge task/run failed and does not write assistant success message。
- terminal bridge task rejects late fresh delta/done/error except duplicate receipt。

### Safety Regression

- Claude Code adapter cannot submit `tool_result` for shell/write/git/network/env/apply_patch without V3 authorized `tool_request_id`。
- Legacy `LocalAgentBridgeEventRequest(event_type="tool_result")` with `adapter_kind=claude_code` and side-effect tool name returns 409/403 and cannot create `ToolCall(SUCCESS)`。
- Claude Code internal command/tool observation, if parsed, can only create redacted `AgentEvent` observation and never successful authorized `ToolCall`。
- Claude Code adapter never triggers generic server `_execute_approved_tool_call()` / `ToolRunner.execute_approved_call()` for local host execution。
- Connection revoke terminalizes active Claude Code bridge tasks and rejects late events with revoked device token。
- Approval TTL/revoke behavior from V3 remains covered for any attempted Claude Code-origin local tool request and is hard-denied in V5。

### Privacy

- persisted bridge event receipt excludes:
  - raw device token
  - pair token
  - Harness bearer token
  - raw Claude API key/OAuth token/auth helper output
  - raw prompt containing secret-looking strings
  - raw stdin prompt/input
  - `/Users/...` and `/home/...` full paths
  - oversized stdout/stderr
- Claude Code stdout/stderr/final payloads are byte-capped and secret-redacted。
- Claude Code unavailable/auth errors do not dump full env, helper output, stdin payload, or absolute home path。
- `bridge.json` does not contain raw cwd, raw prompt, command argv, stdout/stderr, raw Claude credential, raw stdin payload, or raw device token。
- `bridge.device-token` remains mode `0600`。
- raw workspace root remains only in a mode `0600` workspace-root sidecar, not API payloads or bridge.json。
- Claude Code local persistence is disabled:
  - no session transcript saved under Claude config
  - no prompt history saved
  - no native resumable session authority created from V5 runs
  - no user home/keychain/OAuth credential path leaks into bridge state, API events, receipts, or logs

## CLI / Bridge Tests

### Parser And Probe

- `hao bridge pair --adapter claude_code` is accepted by argparse。
- `hao bridge run --adapter claude_code` is accepted by argparse。
- unsupported adapter still rejected by parser。
- Claude Code probe returns installed=false when `shutil.which("claude")` returns None。
- Claude Code probe captures version/help support without requiring provider credentials。
- Claude Code probe requires `--bare`, `-p` / `--print`, `--output-format stream-json`, `--include-partial-messages`, `--no-session-persistence`, `--permission-mode`, and `--tools` support。
- Probe failure before registration exits non-zero with user-visible unavailable reason, does not consume the pair token, does not create a connection, and does not start a daemon。
- Probe subprocess environment is sanitized and excludes Harness/local-agent/provider secrets。

### Command Builder

- generated command includes:
  - `claude`
  - `--bare`
  - `-p` or `--print`
  - `--output-format stream-json`
  - `--verbose`
  - `--include-partial-messages`
  - `--no-session-persistence`
  - `--permission-mode default`
  - `--tools ""`
  - safe stdin mode
- stdin payload is Harness prompt text and is not present in argv。
- generated no-tools mode disables:
  - `Read`
  - `Bash`
  - `Edit`
  - `MultiEdit`
  - `Write`
  - `WebFetch`
  - `WebSearch`
  - `NotebookEdit`
  - MCP tools, plugins, hooks, subagents, browser/remote-control helpers
- generated command does not include:
  - `--dangerously-skip-permissions`
  - `--permission-mode bypassPermissions`
  - `--permission-mode acceptEdits`
  - `--permission-mode auto`
  - `--permission-mode dontAsk`
  - `--continue` / `-c`
  - `--resume` / `-r`
  - `--add-dir`
  - `--remote`
  - `--remote-control`
  - `--mcp-config`
  - `--plugin-dir`
  - `--plugin-url`
  - `--agents`
  - `--allowedTools`
  - `--disallowedTools` as the primary no-tool mechanism
  - `--settings` in the required V5 path
  - `--setting-sources` in the required V5 path
  - `--include-hook-events`
  - raw device token
  - pair token
  - Harness bearer token
  - raw Claude credential/helper output
  - raw secret-looking prompt metadata in argv
  - positional prompt text
- workspace root outside paired root is rejected before subprocess spawn。
- Claude Code subprocess cwd is an adapter-owned private temp directory, not the paired workspace root。
- Claude Code subprocess timeout emits `assistant_error` and terminates child process。
- prompt is passed through stdin by default。
- if stdin is unavailable, prompt is passed through a mode `0600` temp input file and the file is deleted after process exit。
- if neither stdin nor private temp input is possible, command builder fails closed before spawning Claude Code。
- subprocess env is an allowlist, not inherited `os.environ`。
- subprocess env excludes `HARNESS_*`, `HAO_*`, `LOCAL_AGENT_*`, `*_TOKEN`, `*_SECRET`, `*_KEY`, `*_PASSWORD`, provider API key env vars, and proxy env vars unless an explicit V5 local-only auth option allowlists exactly one Claude credential source without persistence。
- tests inject fake secret env vars and prove they are absent from the spawned Claude Code env。
- subprocess env uses adapter-owned temp `HOME` and `CLAUDE_CONFIG_DIR`。
- subprocess env sets `CLAUDE_CODE_SKIP_PROMPT_HISTORY=1`, `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`, and `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1`。
- subprocess env excludes `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CODE_OAUTH_REFRESH_TOKEN`, and any keychain/home-derived credential path。

### Input And Isolation

- stdin input is created under a private temp dir only if stdin piping is unavailable; any temp input file is mode `0600` and deleted after process exit where possible。
- stdin input content is not stored in `bridge.json` or API events。
- `--tools ""` ensures the subprocess cannot read workspace files through Claude Code built-in tools。
- malformed stdin payload generation fails closed before subprocess spawn。
- requested auth helper/source, if supported, is stored only as a hash/ref in bridge state and appears in diagnostics only after path redaction。
- V5 required path does not use `--settings` or `apiKeyHelper`; auth-helper/settings support is deferred to V6。
- hostile config injection tests create user/project/local `.claude` and `~/.claude` files containing settings, permissions, hooks, MCP servers, plugins, skills/commands, CLAUDE.md, subagents, workflows, and auto-memory hints; `--bare` plus isolated temp `HOME` / `CLAUDE_CONFIG_DIR` must prevent them from loading。
- `system/init` fixture with non-empty tools/MCP/plugins/hooks/custom agents must produce `assistant_error` and no assistant success。

### JSON / Output Parsing

- synthetic stream-json text delta maps to local-agent assistant_delta event。
- synthetic `system/init` with empty tools, MCP servers, loaded plugins, hooks, and custom agents permits later assistant output。
- synthetic `system/init` with any built-in tool listed, including `Read`, `Bash`, `Edit`, `Write`, `WebFetch`, `WebSearch`, `Agent`, MCP tool, plugin tool, hook, channel, or browser helper, fails closed。
- synthetic final/result event maps to assistant_done。
- synthetic session id is captured only as advisory redacted metadata。
- unknown stream records are ignored or recorded as bounded observation without failing the whole task。
- malformed JSONL with valid final fallback returns assistant_done from redacted final content only if a valid empty-tool/config `system/init` or equivalent safety proof was already accepted。
- malformed JSONL without fallback returns assistant_error。
- empty final output returns assistant_error unless a known terminal empty success fixture is explicitly allowed。
- non-zero process exit returns assistant_error even if partial deltas were emitted。
- auth failure returns assistant_error and does not write assistant success。
- stream without safety metadata returns assistant_error unless implementation proves an equivalent no-tool/no-config invariant through another bounded metadata event。

### Resume

- V5 never uses native `claude --resume`, `claude -r`, `claude --continue`, `claude -c`, `--session-id`, background sessions, remote sessions, or remote-control for production bridge tasks。
- command builder never uses most-recent-session continuation for production task continuity。
- server-normalized capabilities always set Claude Code `supports_resume=false` and `resume_mode=context_replay_new_session`。
- each next task starts a fresh `claude -p` subprocess plus bounded Harness conversation context。
- parsed Claude Code session id can be persisted only as advisory adapter metadata, not as authority to resume an external Claude session。
- `--no-session-persistence` and `CLAUDE_CODE_SKIP_PROMPT_HISTORY=1` are present for every production bridge task。
- V5 smoke proves no Claude session transcript or prompt history appears under the adapter `CLAUDE_CONFIG_DIR` after completion。
- bridge loads raw workspace root only from the mode `0600` local workspace-root sidecar to recompute `workspace_identity_hash`, and rejects missing/unreadable/mismatched sidecar state before spawn。
- subprocess itself runs from a private temp cwd in V5 and receives no `--add-dir` workspace access。
- adapter must not derive resume cwd from API redacted `workspace_root` or daemon process cwd。

### Bridge State

- pair with Claude Code stores safe bridge state and separate `bridge.device-token`。
- pair with Claude Code stores raw workspace root only in a separate mode `0600` workspace-root sidecar; `bridge.json` stores only safe references and workspace identity metadata。
- bridge state may store Claude probe metadata, auth readiness status, and helper hash/ref only。
- state reload supports daemon restart without losing connection id or pending safe metadata。
- state reload does not restore raw prompts/stdout/stderr/argv, raw stdin input, raw Claude credential, nor raw workspace root from `bridge.json`。
- state reload does not restore native Claude session id as resumable authority。
- API persisted payloads include redacted workspace display and `workspace_identity_hash`, but never raw workspace root。
- legacy inline device-token migration from V3/V4 still works when adapter_kind=claude_code。

## Frontend Tests

### Agent Studio

- local Agent dialog shows Claude Code as V5 enabled, not future disabled。
- fake, hao, and Codex existing cards keep their V1/V3/V4 statuses。
- Claude Code card shows installed/not installed state based on connection/probe capabilities。
- Claude Code card shows host tools disabled。
- Claude Code card shows optional auth unavailable warning。
- Claude Code card shows resume badge:
  - context replay for V5 Claude Code because `supports_resume=false`
  - native resume remains future scope outside V5
- pairing command includes `--adapter claude_code` for adapter-scoped pairing。
- pairing command still does not call `/connections/register` from browser。
- revoke works for Claude Code connection and refreshes discovery list。

### Workspace

- Claude Code connection appears in local Agent connection selector。
- selecting Claude Code creates/resumes binding through existing endpoint。
- sending message uses existing `POST /api/agents/local-agent/bindings/{binding_id}/messages`。
- pending assistant shows `adapter_kind=claude_code` metadata and normal waiting/offline copy。
- offline Claude Code connection keeps readable history and queued/pending projection。
- context replay warning appears when Claude Code native resume is unavailable。
- permission warning appears when user asks for write/shell/git/network capability in Claude Code local mode。
- viewer/operator cannot send executable Claude Code local message。

### Run Detail

- Event Stream shows Claude Code task leased/acked/adapter started/delta/done/error。
- Tool Calls panel does not show successful local host ToolCall for Claude Code internal operations。
- local tool approval panel remains unchanged for hao/fake V3 scenarios。

## E2E / Smoke

### `claude-unavailable`

- Force Claude Code probe to installed=false or run with missing executable。
- Pair behavior is deterministic: `hao bridge pair --adapter claude_code` fails before registration, returns a clear unavailable reason, does not consume the pair token, does not create `LocalAgentConnection`, and does not start a daemon。
- Runtime unavailable behavior for an already-registered Claude Code connection is deterministic: bridge task emits `assistant_error`, not success。
- No raw local path/device token/Claude credential in persisted payloads。

### `claude-readonly-reply`

- Use a mocked Claude subprocess or safe fixture that emits stream-json assistant content。
- Pair `--adapter claude_code --once`。
- Send Workspace local message。
- Verify:
  - connection adapter_kind=claude_code
  - bridge task acked/running/completed
  - assistant message appears in AgentSession
  - Run events include adapter_kind=claude_code
  - no ToolCall success created
  - generated command/input isolation is safe
  - `system/init` proves empty tools/MCP/plugins/hooks/custom-agent surface
  - Claude local session persistence is absent
  - bridge state privacy invariants hold

### `claude-resume-mode`

- First task may return deterministic session id fixture; second task still starts fresh `claude -p` with bounded Harness conversation context。
- Fixture without session id also uses context replay new session。
- Verify UI/API binding resume_mode projection。
- Verify command builder rejects `--resume`, `--continue`, `--session-id`, remote-control, and background session flags。
- Verify fresh execution validates workspace identity before spawn while running the subprocess in a private temp cwd。

### `claude-side-effect-rejected`

- Simulate Claude Code adapter reporting side-effect `tool_result` without V3 `tool_request_id`。
- Verify backend rejects result and no `ToolCall(SUCCESS)` exists。
- Verify bridge task can only complete with assistant_error or safe assistant text after unresolved tool state is absent。

## Required Commands

```bash
cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py -q
cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py tests/test_hao_cli_v2.py -q -k "bridge or claude or codex or adapter or pending_state_file"
cd services/api-server && .venv/bin/python -m pytest tests/test_tool_approvals.py tests/test_tool_runner.py -q
cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/api/schemas.py app/events/event_types.py app/cli/hao tests/test_local_agents.py tests/test_hao_cli.py tests/test_hao_cli_v2.py
cd services/api-server && .venv/bin/python -m py_compile app/api/agents/agent_local.py app/api/schemas.py app/events/event_types.py app/cli/hao/api_client.py app/cli/hao/main.py tests/test_local_agents.py tests/test_hao_cli.py tests/test_hao_cli_v2.py
python3 scripts/smoke-test-local-agent-v5.py --scenario claude-unavailable
python3 scripts/smoke-test-local-agent-v5.py --scenario claude-readonly-reply
python3 scripts/smoke-test-local-agent-v5.py --scenario claude-resume-mode
python3 scripts/smoke-test-local-agent-v5.py --scenario claude-side-effect-rejected
cd apps/agent-console && npm test -- AgentListPage.studio.test.tsx AgentWorkspacePage.team-launch.test.tsx ChatSurface.shell.test.tsx
cd apps/agent-console && npm run lint -- --pretty false
python3 scripts/validate-docs.py
git diff --check
```

## Acceptance Evidence

- Backend proves Claude Code is supported while existing adapters preserve behavior。
- CLI proves Claude Code parser/probe/command builder does not generate dangerous permission bypass, edit-accepting/auto/dontAsk mode, native resume, workspace add-dir, plugin/MCP/subagent, remote-control, built-in tool allowlists, raw prompt argv, or secret-bearing arguments。
- CLI and parser prove the actual Claude run reports an empty tool/config surface before assistant success projection。
- Bridge proves Claude Code assistant output projects through existing local-agent event/message path。
- Safety tests prove Claude Code cannot create successful side-effect ToolCall without V3 authorization。
- Frontend proves Claude Code appears in the same Agent Studio and Workspace local Agent surfaces with correct disabled capability warnings。
- Privacy tests prove bridge state and persisted payloads exclude raw tokens, raw paths, secrets, raw stdin input, and oversized process output。

## Out Of Scope For V5

- Claude Code write/apply_patch/git/network/env/secret capability。
- Stable pre-tool authorization via Claude Code MCP permission prompt or Agent SDK callback。
- Native Claude Code resume / continue / background / remote-control sessions。
- Multi-device Claude collaboration。
- Required live Claude credential smoke。
- Production guarantee for computer shutdown continuation beyond daemon reconnect semantics。

## Review Expectations

Two independent plan reviews must pass before implementation:

- Architecture/protocol reviewer: adapter truth boundary, workspace identity, resume semantics, API/DB authority, and UI integration.
- Security/test reviewer: command safety, credential handling, input privacy, negative tests, and deterministic smoke adequacy.

Implementation code review must run after V5 code is complete and before commit/push.
