# PRD: 本地 Agent Codex CLI Adapter V4

## Summary

V4 在 V1/V2/V3 已完成的 local-agent pairing、Workspace ChatSurface、API-owned Run/Event/Message 投影、以及本地 host tool safety 基线之上，接入第一个非 hao 的真实本地 Agent：Codex CLI。

本版目标不是重新设计 bridge，也不是让 Codex 绕过 Harness。Codex CLI 必须作为现有 local-agent bridge protocol 的一个 `adapter_kind=codex` 实现：配对、注册、心跳、任务拉取、ack、assistant delta/done/error 上报、会话绑定和 pending/offline projection 继续由 API/DB 统一管理。

V4 的安全边界是保守的：Codex adapter 只验收受限 assistant-response 接入和可恢复会话语义。除非 Codex adapter 能在执行前通过 V3 `tool-requests` 协议申请授权，否则不得暴露 host write、shell mutation、git mutation、network、env/secret read 等副作用能力；不能把 Codex CLI 内部工具事件伪装成 Harness-authorized `ToolCall(SUCCESS)`。

## Requirements Summary

- 后端把 `codex` 从 disabled future adapter 升级为 V4 supported adapter，同时 `claude_code` 继续 disabled。
- `hao bridge pair --adapter codex` 和 `hao bridge run --adapter codex` 可注册 Codex connection，且仍使用 hash-stored pair token、device token、daemon、heartbeat、task pull、ack、event receipt 和 revoke 机制。
- Agent Studio 自动识别列表把 Codex CLI 显示为 V4 enabled；`hao bridge pair --adapter codex` 必须先 probe 本地 `codex`，缺少 executable 时在注册前 fail closed，不消费 pair token、不创建 connection、不启动 daemon。
- Workspace 使用现有 local connection selector、binding、ChatSurface 和 pending/offline projection；不新增独立 Codex 聊天 UI。
- Codex task handling 调用本地 `codex exec` 的可检测命令面，通过 stdin 或 `0600` 临时输入文件传递 prompt，解析 stdout JSONL 或 final-message fallback，并投影为 local-agent `assistant_delta` / `assistant_done` / `assistant_error`。
- V4 不使用生产 native Codex resume；即使 Codex 输出 session id，也只能作为 advisory metadata，服务端能力固定为 `supports_resume=false`，`resume_mode=context_replay_new_session`，UI 必须标记为上下文重放的新外部会话。
- Codex adapter 默认不声明 V3 host tool risk capabilities；副作用 capability 在 V4 UI 禁用。任何 side-effect result/report 缺少 V3 authorized `tool_request_id` 时继续被后端拒绝。
- `--dangerously-bypass-approvals-and-sandbox` 禁止出现在 Codex adapter 生成命令中。V4 smoke 使用 read-only sandbox 或等价最小权限配置。
- device token、raw cwd、Codex prompt、command argv、subprocess env、stdout/stderr、session ids 和 local paths 按 V3 privacy baseline 截断/脱敏；raw device token 继续只存在 `bridge.device-token`。

## Evidence From Current Code

- 后端当前协议版本和 adapter gate 在 `services/api-server/app/api/agents/agent_local.py:14` 至 `services/api-server/app/api/agents/agent_local.py:16`：supported 只有 `fake` / `hao`，`codex` / `claude_code` disabled。
- connection response 已会返回 `adapter_kind`、`workspace_root`、`capabilities_json` 和 `risk_capabilities_json`：`services/api-server/app/api/agents/agent_local.py:129` 至 `services/api-server/app/api/agents/agent_local.py:149`。
- Workspace binding 已可记录 `adapter_session_id` 和 `resume_mode`：`services/api-server/app/api/agents/agent_local.py:586` 至 `services/api-server/app/api/agents/agent_local.py:646`。
- Workspace local send 已创建 user message、Run 和 bridge task，并按 adapter kind 选择 run mode：`services/api-server/app/api/agents/agent_local.py:687` 至 `services/api-server/app/api/agents/agent_local.py:760`。
- bridge event ingest 已通过 receipt 幂等写回 `AgentEvent` / `AgentMessage` / `ToolCall`：`services/api-server/app/api/agents/agent_local.py:955` 至 `services/api-server/app/api/agents/agent_local.py:1020`。
- V3 tool request/decision/result 协议入口已存在：`services/api-server/app/api/agents/agent_local.py:1023` 至 `services/api-server/app/api/agents/agent_local.py:1160`。
- `_default_local_agent_name()` 已包含 Codex CLI label，但 `_normalized_capabilities()` 仍只把 fake/hao 视为 enabled：`services/api-server/app/api/agents/agent_local.py:3144` 至 `services/api-server/app/api/agents/agent_local.py:3158`。
- CLI bridge parser 当前 `--adapter` choices 只有 `fake` / `hao`：`services/api-server/app/cli/hao/main.py:169` 至 `services/api-server/app/cli/hao/main.py:175`，以及 `services/api-server/app/cli/hao/main.py:186` 至 `services/api-server/app/cli/hao/main.py:192`。
- bridge capabilities 当前只为 hao 声明 resume/cancel/risk capabilities：`services/api-server/app/cli/hao/main.py:483` 至 `services/api-server/app/cli/hao/main.py:496`。
- daemon pair/run 已保护 device token 与 bridge state：`services/api-server/app/cli/hao/main.py:965` 至 `services/api-server/app/cli/hao/main.py:1128`。
- bridge task handler 当前只分派 fake 和 hao：`services/api-server/app/cli/hao/main.py:1131` 至 `services/api-server/app/cli/hao/main.py:1176`。
- Agent Studio adapter list 当前把 Codex CLI 标为 future disabled：`apps/agent-console/src/features/agents/pages/AgentListPage.tsx:783` 至 `apps/agent-console/src/features/agents/pages/AgentListPage.tsx:816`。
- Workspace local send 已把 `adapter_kind` 写入 pending assistant metadata：`apps/agent-console/src/features/agents/pages/AgentWorkspacePage.tsx:640` 至 `apps/agent-console/src/features/agents/pages/AgentWorkspacePage.tsx:704`。
- 当前 regression 明确拒绝 disabled Codex registration：`services/api-server/tests/test_local_agents.py:346` 至 `services/api-server/tests/test_local_agents.py:366`。
- pair-token 默认 scope 当前仍是 `{"executable": true, "adapters": ["fake", "hao"]}`：`services/api-server/app/api/agents/agent_local.py:253` 至 `services/api-server/app/api/agents/agent_local.py:260`。V4 必须把默认或 adapter-scoped pairing 闭环到 `codex`。
- connection 当前只持久化脱敏 `workspace_root`，bridge disk state allowlist 也不保存 raw root：`services/api-server/app/api/agents/agent_local.py:376` 至 `services/api-server/app/api/agents/agent_local.py:390`，以及 `services/api-server/app/cli/hao/main.py:518` 至 `services/api-server/app/cli/hao/main.py:530`。V4 执行前必须新增非 raw-path 的 workspace identity 证明，防止 paired workspace drift。
- 本机 Codex CLI help 证实 `codex exec` 支持 `--json`、`--output-last-message`、`-C/--cd`、`--sandbox read-only|workspace-write|danger-full-access`、`exec resume`；V4 计划基于这些可检测能力，不依赖未证实的 pre-tool hook。

## Goals

1. Adapter enablement and discovery
   - 将 `codex` 加入后端 supported adapter set；`claude_code` 保持 disabled。
   - 注册时接受 `adapter_kind=codex`，但必须校验 `protocol_version=local-agent-v1`、pair token、pair code、org/user/agent scope 和 token 单次消费。
   - pairing token 默认 adapter scope 必须从 `["fake", "hao"]` 扩展为 V4 supported adapters `["fake", "hao", "codex"]`；显式 adapter-scoped token 仍可缩窄范围，且 `codex` registration 必须在 token 消费前验证 `scope.adapters` 包含 `codex`。
   - Codex connection capabilities 至少包含：
     - `adapter_kind=codex`
     - `supports_streaming` 根据 `codex exec --json` probe 结果设置
     - `supports_resume=false` in V4；native Codex resume 的 probe、session-id extraction、workspace identity validation 和 resume sandbox authority proof 留到后续版本
     - `supports_cancel=false`，除非 adapter 实现可验证 process cancellation + terminal event
     - `host_tools_authorized=false`
     - `resume_mode=context_replay_new_session`
   - `risk_capabilities` V4 默认为空或只包含 `workspace_read_constrained`；不得包含 host write、shell、git、network、secret。

2. Codex CLI adapter implementation
   - 新增 adapter dispatch，例如 `_handle_codex_bridge_task()`，但保留 fake/hao 分支不变。
   - Codex command builder 必须：
     - 使用 `codex exec`
     - 使用 `-C <workspace_root>` 指向 paired workspace
     - 使用 `--json` when available
     - 使用 `--output-last-message <tempfile>` as final fallback
     - 使用 `--sandbox read-only` 或等价最小权限
     - 使用 prompt stdin `-`，或在 stdin 不可用时使用 mode `0600` 临时输入文件；prompt 不得作为 positional argv 传入
     - 使用 sanitized subprocess env allowlist；不得继承 Harness、bridge、provider key、token、secret 或 proxy 等敏感环境变量
     - 不传 `--dangerously-bypass-approvals-and-sandbox`
     - 不把 device token、raw Harness auth token、raw pair token、raw secret 或 bridge state path 放入 argv
   - Prompt wrapper 必须说明本轮由 Harness local-agent bridge 管理，Codex 不得修改文件、执行副作用命令、读取 env/secret、安装包或发起网络请求；若任务需要这些能力，应输出需要权限的说明，而不是自行执行。
   - stdout JSONL parser 将 assistant text incremental 投影为 `assistant_delta`；若 JSON schema 不匹配，降级为 bounded final-message `assistant_done` 或 `assistant_error`。
   - 子进程 exit non-zero、timeout、JSON parse hard failure、Codex unavailable、revoked connection、task terminal conflict 都上报 `assistant_error`，不能生成 successful assistant message。

3. Resume semantics
   - 如果 Codex JSONL 提供稳定 session id，adapter 只能将其作为 sanitized advisory metadata 记录，不能把它作为 V4 production native resume authority。
   - V4 后端 binding 继续可恢复 Harness history，但外部 Codex 侧每轮使用 `resume_mode=context_replay_new_session` 新开会话；UI 显示“上下文重放，新 Codex 会话”。
   - `codex exec resume <session_id>` 是后续版本范围；V4 不生成 production native resume 命令。
   - 当前本机 `codex exec resume --help` 暴露 `-c/--config` 但不暴露 `--sandbox` / `-C`；因此 V4 implementation 默认不得 native-resume。
   - 不允许用 `codex resume --last` 作为 production resume 默认路径，因为 `--last` 可能跨 workspace 或跨用户选错会话。

4. Safety and V3 compatibility
   - Codex adapter 的 side-effect host tools 在 V4 UI/API capabilities 中禁用。
   - 若未来 Codex JSONL 输出 tool/command events，V4 只能作为 observation 写 `AgentEvent`；不得写 `ToolCall(SUCCESS)`，除非先经过 V3 `tool-requests` pre-execution authorization。
   - Codex adapter 不使用 generic server `ToolRunner.execute_approved_call()` 执行本地 host action。
   - V3 legacy side-effect result rejection 继续覆盖 `adapter_kind=codex`。
   - Codex stdout/stderr、last-message、JSON event payload、prompt wrapper、session metadata 全部做 byte cap、secret scan、path redaction。

5. UI
   - Agent Studio adapter card:
     - Codex CLI badge 从 “后续接入/Future” 改为 “V4 启用/V4 enabled”。
     - 显示 installed / not installed、online/offline、supports_resume、resume_mode、host tools disabled。
     - 未检测到 `codex` 时，给出 install required / unavailable 状态；pair 命令在注册前失败，不创建无法执行的 connection。
   - Workspace local-agent selector 继续显示 Codex connections；pending/offline/reconnect 文案沿用 V2。
   - ChatSurface / pending assistant metadata 显示 `adapter_kind=codex` 和 resume warning。
   - Run Detail events 可看到 Codex adapter start/error/done，且 tool calls 不显示伪造成功本地工具。

## Non-Goals

- V4 不接入 Claude Code adapter。
- V4 不开放 Codex host write、apply_patch、git mutation、network、package install、env/secret read。
- V4 不实现 Codex internal tool pre-execution hook；如果 Codex CLI 没有可拦截的稳定事件，V4 不把内部工具纳入 authorized ToolCall。
- V4 不依赖任何 native Codex resume 做确定性恢复，尤其不使用 `codex resume --last`。
- V4 不把 browser 变成本地执行端，也不让浏览器直接注册 connection。
- V4 不承诺电脑关机后继续执行，只延续 V1/V2 daemon alive 和 reconnect/pending 语义。

## Backend Contract

### Adapter Gate

- `LOCAL_AGENT_SUPPORTED_ADAPTERS` includes `codex`。
- `LOCAL_AGENT_DISABLED_ADAPTERS` keeps `claude_code`。
- Pair-token default adapter scope includes `codex` alongside `fake` and `hao`; explicit `scope.adapters` remains authoritative when supplied by the UI/API。
- Registration validates `adapter_kind` against `scope.adapters` before consuming the token or creating a connection, so a `hao`-only token cannot register Codex and remains non-consumed after the failed attempt。
- `test_local_agent_v1_rejects_disabled_adapters` must be replaced or split:
  - codex registration accepted when pairing token is valid;
  - claude_code still rejected.
  - codex rejected when the pairing token is explicitly scoped to another adapter.

### Capabilities Normalization

For `adapter_kind=codex`, `_normalized_capabilities()` must enforce server-owned defaults:

```json
{
  "adapter_kind": "codex",
  "supports_streaming": true,
  "supports_resume": false,
  "supports_cancel": false,
  "enabled_in_v4": true,
  "host_tools_authorized": false,
  "resume_mode": "context_replay_new_session"
}
```

The bridge may report richer capability probe results, but server normalization must never allow host side effects based only on bridge self-report. For V4 Codex, `supports_resume=true` is always normalized to false and `resume_mode=context_replay_new_session`.

### Bridge Event Contract

Required Codex event projection:

1. `LOCAL_AGENT_TASK_ACKED`
2. `LOCAL_AGENT_ADAPTER_STARTED`
   - payload: `adapter_kind=codex`, redacted workspace root, supports flags, command mode without argv secrets.
3. zero or more `LOCAL_AGENT_ASSISTANT_DELTA`
   - payload: bounded content chunk and Codex event id if present.
4. one terminal event:
   - `assistant_done` if final assistant content exists and bridge task has no unresolved local tool state;
   - `assistant_error` if Codex unavailable, exit non-zero, timeout, revoked, JSON parse hard failure, or safety violation.

If new event enum names are not necessary, implementation may reuse existing local-agent event types, but the payload must include `adapter_kind=codex` and must not include raw local secrets.

### Resume Binding

- Existing `LocalAgentConversationBinding.adapter_session_id` and `resume_mode` are sufficient for V4 conversation projection; workspace identity can be stored in existing connection/binding metadata unless implementation needs a queryable column.
- On registration, the bridge canonicalizes the paired workspace root and the API persists only a non-sensitive `workspace_identity_hash` plus non-secret salt or equivalent metadata; the display `workspace_root` remains redacted and is never used as the resume authority.
- The bridge stores raw workspace root only in a separate mode `0600` local sidecar such as `bridge.workspace-root`; `bridge.json`, API events, receipts, logs and UI responses may contain only the hash/salt and redacted display path.
- Adapter metadata may include the same `workspace_identity_hash`; in V4 it is used to constrain fresh `codex exec` subprocesses, not to authorize native Codex resume.
- If raw-root sidecar is missing, unreadable or hash-mismatched, Codex execution fails closed with `assistant_error` instead of falling back to process cwd or a redacted path.
- If the sidecar hash is valid but a stored advisory `adapter_session_id` belongs to a different workspace hash, owner, connection or adapter kind, the adapter must ignore it and continue with `resume_mode=context_replay_new_session`.
- If implementation stores additional per-adapter state in `bridge.json`, it must use a disk allowlist equivalent to V3 and exclude raw prompts, raw cwd, argv, stdout/stderr, auth tokens, device token and raw workspace root.

## CLI / Bridge Contract

### Parser

- Add `codex` to `hao bridge pair --adapter` and `hao bridge run --adapter` choices.
- Display name default: `Codex CLI`。
- Capability probe:
  - `shutil.which("codex")`
  - `codex --version`
  - `codex exec --help`
  - `codex exec resume --help`
  - optional test-only smoke using the same stdin input contract: `codex exec --json --output-last-message <tmp> -C <tmp-workspace> --sandbox read-only -` with the probe prompt supplied on stdin, never as positional argv.

### Command Builder

Allowed command shape:

```text
codex exec --json --output-last-message <temp-file> -C <workspace-root> --sandbox read-only -
```

Prompt transport:

- Primary path: pass the prompt on subprocess stdin while using `-` as the Codex prompt argument.
- Fallback path: if stdin execution is unavailable in a target platform, write prompt to a mode `0600` temp input file under a private temp dir, feed it through stdin redirection or an equivalent safe input path, and delete it after process exit.
- Forbidden path: prompt text must not be passed as positional argv. If the adapter cannot avoid prompt-in-argv, it must fail closed before spawning Codex.
- The bridge must scan prompt wrapper and adapter-added metadata before spawn. If bridge-injected content contains device token, pair token, Harness bearer token, raw env value, or secret-looking material, the adapter must fail closed. User-authored message content is still model input, but it is never persisted in argv, bridge state, event receipt raw payloads, or logs.

Native resume command shapes are not allowed for V4 production bridge tasks. Future versions may add `codex exec resume <adapter-session-id>` only after deterministic session ownership, workspace identity binding, and read-only/equivalent sandbox authority are proven.

Workspace anchoring:

- Before spawning `codex exec`, validate that the task `workspace_identity_hash` matches the local sidecar root hash recorded at pairing time.
- The adapter must launch the subprocess with `cwd=<raw workspace root loaded from the 0600 sidecar>` only after the sidecar canonical path recomputes to the connection `workspace_identity_hash`.
- The adapter must never derive execution cwd from the redacted API `workspace_root` display value or the daemon process current directory.

Rejected command properties:

- `--dangerously-bypass-approvals-and-sandbox`
- `--sandbox danger-full-access`
- native resume
- workspace root outside paired root
- prompt or argv containing device token, pair token, Harness bearer token, raw env values or secret-looking strings
- use of `--last` for production task continuity

### Subprocess Environment

Codex subprocesses must run with a sanitized env allowlist, not inherited `os.environ`.

Allowed categories:

- `PATH` reduced to trusted binary directories needed to find `codex` and system tools.
- Locale/terminal basics such as `LANG`, `LC_ALL`, `LC_CTYPE`, `TERM` when needed.
- Temp paths such as `TMPDIR`, pointing to an adapter-owned private temp directory.
- `HOME` / `CODEX_HOME` only when required for Codex auth/config discovery; these values may be passed to the process but must never be persisted in events, bridge state, or logs without path redaction.

Always excluded:

- `HARNESS_*`, `HAO_*`, `LOCAL_AGENT_*`, `X_LOCAL_AGENT_*`
- `*_TOKEN`, `*_SECRET`, `*_KEY`, `*_PASSWORD`, `*_CREDENTIAL*`
- provider key variables such as `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, `TAVILY_API_KEY`
- proxy variables such as `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY` unless a future policy explicitly allows networked Codex execution

If Codex cannot run without a secret-bearing env var, V4 must return `assistant_error` / unavailable and must not broaden the env.

### Output Parser

- JSONL parser must tolerate unknown event shapes by ignoring unknown records and keeping bounded raw error context.
- Assistant content extraction should support a small adapter-owned mapping table, with tests using synthetic JSONL events.
- If no streamable assistant content is found but `--output-last-message` exists, use the file after byte cap and secret/path redaction.
- Empty final content with zero exit should still become `assistant_error` unless Codex emits a known terminal success event with empty answer explicitly allowed by test.

## Frontend Contract

- `LOCAL_AGENT_ADAPTERS` marks Codex as enabled and updates copy from future disabled to V4 supported but host tools disabled.
- Readiness cards show:
  - fake: enabled, no local command execution
  - hao: enabled, host-tool approval capable
  - Codex CLI: enabled when detected, assistant-response adapter, host tools disabled
  - Claude Code: future disabled
- Connection rows show Codex resume badge:
  - `上下文重放` for V4 Codex because `supports_resume=false`
  - `原生恢复` remains future scope
- Workspace pending assistant keeps existing local-agent flow and adds no new card-in-card UI.
- Permission warning appears when user asks for file write/shell/git/network in Codex local mode: V4 does not expose those capabilities.

## Implementation Steps

1. Backend adapter gate
   - Update supported/disabled sets and capability normalization in `agent_local.py`.
   - Update backend tests for codex accepted / claude rejected / side-effect result still rejected.

2. CLI adapter probe and dispatch
   - Add codex parser choice.
   - Add `CodexCliAdapter` helper or local functions for probe, command building, JSONL parsing, redaction and timeout.
   - Dispatch `_handle_codex_bridge_task()` from existing bridge loop.
   - Keep fake and hao paths behavior-identical.

3. Resume and state
   - Store only sanitized Codex adapter session metadata.
   - Always set context replay mode for V4; keep native Codex resume as future scope.
   - Add tests that `--last` is not generated.

4. Frontend projection
   - Enable Codex adapter card and capability badges.
   - Add readiness/resume/host-tools-disabled warnings.
   - Preserve existing ChatSurface local mode.

5. Smoke and docs
   - Add deterministic V4 smoke script or extend local-agent smoke with `codex-unavailable`, `codex-readonly-reply`, and `codex-resume-mode` scenarios.
   - Update task progress and wiki evidence after implementation closeout.

## Acceptance Criteria

- Valid pair token can register `adapter_kind=codex`; invalid/replayed/cross-org token still fails.
- `adapter_kind=claude_code` still fails registration.
- Agent Studio no longer shows Codex as future disabled; it shows installed/online/resume/host-tools-disabled state.
- `hao bridge pair --adapter codex --once` can register and run fake/synthetic Codex output in tests without storing device token in `bridge.json`.
- Codex bridge task ack -> adapter started -> assistant delta/done projects into existing Workspace conversation and Run events.
- Codex unavailable produces `assistant_error` and does not complete bridge task as successful.
- Codex non-zero exit or parse failure produces `assistant_error`.
- Codex adapter never passes `--dangerously-bypass-approvals-and-sandbox` or `--sandbox danger-full-access`.
- Codex adapter passes prompt via stdin or a private `0600` temp input path, never positional argv.
- Codex adapter launches subprocesses with sanitized env allowlist and tests prove secret-bearing env vars are scrubbed.
- Codex adapter never uses `resume --last` for production task continuity.
- Codex execution is workspace-anchored through pre-spawn root validation and `subprocess.cwd=<paired workspace_root>`.
- Codex native resume does not occur in V4; every production task uses `resume_mode=context_replay_new_session`.
- Codex execution uses a pair-time `workspace_identity_hash`; raw workspace root is kept only in a `0600` local sidecar, and missing/mismatched sidecar state fails closed.
- Pairing default scope includes `codex`; explicit non-Codex adapter scope rejects Codex registration without consuming the pair token.
- Codex side-effect tool/result without V3 authorized `tool_request_id` remains rejected.
- No raw device token, prompt secret, env secret, raw home path, or large stdout/stderr is persisted in API/DB/bridge state.

## Risks And Mitigations

- Risk: Codex CLI JSON event schema may change.
  - Mitigation: parser tolerates unknown events and uses `--output-last-message` fallback; tests use adapter-owned fixtures and unknown-event cases.
- Risk: Codex CLI may not expose a stable pre-tool authorization hook.
  - Mitigation: V4 disables host tools and treats internal tool observations as non-authoritative; V5/V6 can add a verified pre-tool mapping if CLI support exists.
- Risk: `codex resume --last` can resume the wrong local session.
  - Mitigation: V4 does not native-resume Codex sessions; every production task uses context replay new session.
- Risk: read-only local execution can still expose sensitive file contents.
  - Mitigation: V4 redacts output, does not auto-enable broad risk capabilities, and flags host tools disabled; implementation smoke uses safe temp workspaces. A future read-audit extension can add finer-grained file-read authorization.
- Risk: enabling Codex breaks V1/V2/V3 fake/hao behavior.
  - Mitigation: keep adapter dispatch isolated and rerun local-agent, hao bridge, tool safety and frontend regression tests.

## Verification Steps

Required planning/implementation gates:

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

## RALPLAN-DR Summary

Principles:

- Harness remains the authority for session, Run, event, approval, audit and permission state.
- Local bridge remains untrusted; adapter self-report never grants side-effect authority.
- V4 must enable Codex without regressing fake/hao or V3 host tool safety.
- Unsupported Codex capabilities are visible as disabled, not hidden or silently attempted.

Decision drivers:

- User goal requires Codex CLI to appear in the same local Agent conversation flow.
- V3 security baseline must survive adapter expansion.
- Codex CLI command surface is useful but does not prove stable pre-tool approval interception.

Viable options:

- Option A: conservative Codex assistant-response adapter with disabled host tools.
  - Pros: delivers V4 adapter integration while preserving V3 safety.
  - Cons: Codex cannot yet mutate files through Harness-approved local tools.
- Option B: full Codex host-tool bridge in V4.
  - Pros: closer to native Codex Code behavior.
  - Cons: unsafe without verified pre-execution tool interception; would weaken V3.
- Option C: postpone Codex until a full generalized adapter framework exists.
  - Pros: minimizes V4 risk.
  - Cons: blocks the roadmap slice and delays user-visible local Agent expansion.

Favored option: Option A.

## ADR

Decision: V4 will implement Codex CLI as a supported local-agent adapter for pairing, discovery, Workspace conversation, assistant output projection and constrained resume semantics, while keeping host side-effect tools disabled unless they use the V3 authorization protocol.

Drivers: preserve Harness authority, expand adapter coverage, keep V3 safety intact, and avoid depending on unverified Codex internal hooks.

Alternatives considered: full Codex host-tool execution in V4; postponing Codex until all adapters are generalized; treating Codex CLI output as generic bridge events without adapter-specific constraints.

Why chosen: the conservative adapter delivers the next roadmap slice and creates reusable adapter infrastructure without opening a policy bypass.

Consequences: V4 may feel less powerful than native Codex because file writes and shell mutation are disabled. This is intentional until a later version can prove pre-execution authorization.

Follow-ups: V5 can add Claude Code or a generic external-CLI adapter contract; V6 can add verified tool interception/read-audit if Codex/Claude expose stable hooks.

## Review Gate

V4 plan must pass two independent reviews before implementation:

- Architecture reviewer: local-agent protocol fit, Run/Event/Session authority, resume semantics, adapter isolation.
- Security/test reviewer: V3 safety preservation, disabled side-effect capabilities, privacy, negative tests and smoke adequacy.

Implementation must not start until both reviewers return `PASS` / `APPROVE` or all blocking feedback is incorporated and re-reviewed.
