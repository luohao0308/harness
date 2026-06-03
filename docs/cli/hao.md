# hao Agent CLI

`hao` 是 AI Harness 的本地 Agent CLI。它参考现代 Agentic Coding 产品的本地工作流和权限体验，把读写文件、执行 shell、diff 展示、会话恢复放到开发者机器上的 CLI 进程中，同时把审计证据写回 Harness 后端。

后端不会替 `host` target 执行宿主机 shell 或文件写入。`host` target 的本机操作只由 CLI 执行；后端只接收 `ToolCall` 和 `AgentEvent` 审计记录。这条边界保持了 Docker sandbox WarmPool ADR 的宿主机执行禁令。

## 安装和入口

### npm 安装

`services/api-server` 现在同时暴露 npm package `@harness/hao`，安装后提供全局 `hao` 命令。npm 包是一个轻量 launcher，会调用随包安装的 Python CLI：

```text
uv run --project <package-root> hao ...
```

前置要求：

- Node.js 18+
- `uv` 已安装并在 `PATH` 中

如果 `hao --help` 显示的是 `install / uninstall / list / version`，
说明当前 PATH 里还是旧的同名 npm 包。先卸载旧包再安装本仓库的
`@harness/hao`：

```bash
npm uninstall -g hao
npm install -g /path/to/harness/services/api-server
command -v hao
```

`command -v hao` 应该解析到 `@harness/hao` 的安装树，而不是旧包。

从当前仓库本地安装：

```bash
npm install -g /path/to/harness/services/api-server
hao --help
hao -v
hao --version
hao version
hao doctor
```

发布到 npm registry 后安装：

```bash
npm install -g @harness/hao
hao --help
hao --version
```

如果 `uv` 不在 `PATH`，可以用 `HAO_UV_BIN=/absolute/path/to/uv` 指定。开发调试时也可以用 `HAO_PYTHON_PROJECT=/path/to/services/api-server` 覆盖 launcher 使用的 Python project。

### 仓库内开发入口

不安装 npm 包时，在仓库内运行：

```bash
cd services/api-server
uv sync
uv run hao --help
uv run hao doctor
```

`services/api-server/pyproject.toml` 暴露 console script：

```text
hao = "app.cli.hao:main"
```

`services/api-server/package.json` 暴露 npm bin：

```text
hao -> bin/hao.cjs
```

## 认证

保存本地 API 配置：

```bash
hao login --api-url http://127.0.0.1:8000 --token <token>
hao status
hao logout
hao auth set --api-url http://127.0.0.1:8000 --token <token>
hao auth status
```

`login` 等价于 `auth set`，`status` 等价于 `auth status`。`logout`
会清空 `~/.hao/config.toml` 里的持久 token，但保留 API URL；如果
环境变量 `HAO_API_URL` / `HAO_API_TOKEN` 已设置，它们仍然优先。

配置优先级：

1. `HAO_API_URL` / `HAO_API_TOKEN`
2. `~/.hao/config.toml`
3. 默认 API 地址 `http://127.0.0.1:8000`

`HAO_HOME` 会改变配置和会话根目录，默认是 `~/.hao`。

## 启动会话

```bash
hao --agent-id default --cwd . --mode confirm --target host
```

主要参数：

- `--agent-id ID`：目标 Harness Agent，默认 `default`。
- `--cwd PATH`：本机 workspace 根目录，默认当前目录。
- `--model-provider NAME` / `--model-name NAME`：写入 run 记录和状态栏的模型标识，默认 `default/default`。
- `--mode confirm|auto-edit|full-auto`：本机权限模式。
- `--target host|sandbox`：本机执行或 Harness sandbox 执行。

TUI 现在采用更接近 local Agent CLI 的 inline 终端布局：`hao` 不再切到单独的全屏 alternate screen，而是在当前 shell 输出流里显示 `hao Code` 欢迎框、主会话、底部 `›` 输入提示和状态提示。欢迎框按 local Agent CLI 的启动页结构排版，左侧是欢迎、图标、模型强度和当前目录，右侧是 Tips 和 What's new。底部状态会显示当前模型、推导出的强度标签、compact 圆环、输出风格、审批数和命令数。工具、diff、文件树、审批、命令、计划、输出、todo 和验证视图不再常驻右侧分屏；只有输入 `/tools`、`/diff`、`/tasks`、`/view ...` 等命令时才会打开底部工作台 drawer。

本地 Harness API 请求会忽略 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` 等环境代理配置，避免 `127.0.0.1` 服务被 SOCKS 代理环境变量污染。

常用 slash commands：

```text
/help [query]
/commands [query]
/init
/release-notes
/chat
/plan
/act
/continue
/branch <message_id>
/compact [instructions]
/compress [instructions]
/resume [session_id]
/config
/settings
/model [provider/model|provider model]
/permissions confirm|auto-edit|full-auto
/mode confirm|auto-edit|full-auto
/allowed-tools confirm|auto-edit|full-auto
/output-style default|concise|explanatory|review
/target host|sandbox
/view tools|diff|files|approvals|commands|plan|outputs|todos|verify
/diff
/tools
/files
/approvals
/outputs
/tasks
/bashes
/context
/usage
/cost
/stats
/approve <id>
/reject <id>
/cancel <command_id>
/retry <command_id>
/sessions
/clear
/quit
```

v4 之后，TUI 底部输入框更接近 local Agent CLI 的单输入体验：输入 `/` 会显示可过滤的命令菜单，`/help <query>` 和 `/commands <query>` 会输出同一份命令目录；`/permissions` 是 `/mode` 的 local Agent CLI 风格别名，`/model` 可以查看或切换后续请求记录的模型标识，`/context` 会显示下一轮发送给模型的本地上下文卡，`/usage` 会显示本地消息、工具、审批和命令计数。`/resume <session_id>` 可以在当前 TUI 内加载已有本地 session。

v4.1 继续补 local Agent CLI 风格命令面：

- `/config` 和 `/settings` 输出当前模型、模型强度、工作流、target、权限、输出风格、compact 圆环、session、run 和 cwd。
- `/cost`、`/stats` 作为 `/usage` 的别名，显示本地消息、工具、审批、命令、compact 圆环和 compact 计数；当前不伪造真实 token 成本。
- `/allowed-tools` 作为 `/permissions` 的别名，用 hao 的 `confirm / auto-edit / full-auto` 权限模型表达本地工具授权。
- `/output-style default|concise|explanatory|review` 会把响应风格提示写入下一轮本地 context message。
- `/tasks` 和 `/bashes` 打开本地命令任务视图，对应 shell/test/git 命令生命周期。
- `/compact [instructions]` 和 `/compress [instructions]` 会用一条确定性的本地 system 摘要替换较早的 active-path 消息，并保留最近 6 条消息进入下一轮 payload。它不是模型级摘要，不会伪造 token 计费；如果 active path 不超过 6 条消息，则只提示无需 compact。compact 状态会用 `○/◔/◑/◕/◉/●` 圆环显示压缩比例。

命令和工具输出现在按更接近终端任务卡片的格式展示：先显示工具名与状态，再显示 exit code、命令行、stdout/stderr 首行，完整输出仍记录在本地 session artifact 中。

v4.2 继续收敛到 local Agent CLI 风格页面：

- 默认界面取消顶部 Header/Footer 和右侧常驻工作台，进入后只显示欢迎卡、主会话、底部 `›` 输入行和一行轻量状态。
- 默认入口使用普通 Rich 终端循环，不再进入看起来像编辑器的 Textual 全屏 alternate screen。
- 欢迎卡照 local Agent CLI 启动页分成左右两栏：左侧 `Welcome back!`、图标、模型强度、cwd；右侧 Tips for getting started 和 What's new；卡片里的 `/init` 和 `/release-notes` 都是真实命令。
- 底部状态区显示 `provider/model · strength ...`，下一行显示 compact 圆环、已压缩比例、输出风格、审批数和命令数；`/model`、`/output-style`、`/compact`、工具审批和命令状态变化会刷新这块信息。
- `/init` 会在当前 `--cwd` 下创建 `HAO.md` workspace 指令文件；如果文件已存在，只提示 `exists`，不会覆盖。
- `/release-notes` 会在当前会话里输出 hao v4/v4.1/v4.2 的本地变更摘要。
- `/tools`、`/diff`、`/files`、`/approvals`、`/outputs`、`/tasks`、`/bashes`、`/view ...` 会按需打开底部工作台 drawer；`/clear` 会清空会话并隐藏 drawer。
- 真实终端里的用户输入只依赖终端自身 echo，不再额外打印第二条用户 transcript；UTF-8 输入会按字节安全解码，中文输入不会触发 `UnicodeDecodeError`。
- 401/403 stream 失败会输出 hao 自己的登录或权限提示，不再把 httpx 原始 MDN 链接整段吐到会话里。
- 本地 API client 使用 `trust_env=False`，`hao` 连接 Harness localhost 时不会因为全局代理缺少 `socksio` 而失败。

## v2 工作流模式

`hao` v2 把日常对话、计划和执行拆成三个可审计工作流：

| CLI 命令 | 后端 stream mode | 本地工具行为 |
| --- | --- | --- |
| `/chat` | `cli_agent` | 正常对话，可按权限模式执行本地工具 |
| `/plan` | `markdown_plan` | 只生成 Markdown 计划；CLI 不执行 host 或 sandbox 工具 |
| `/act` | `cli_agent` | 进入执行工作流，并带 `act_intent={"source":"slash_command","allow_local_tools":true}` |

CLI 会把 `interaction_mode` 和可选 `act_intent` 写入 stream payload、本地消息元数据、本地工具审计 payload，以及后端 `ToolCall` / `AgentEvent` 证据。这样恢复会话或审计运行时，可以区分普通聊天、计划和明确执行。

## 权限模式

| 模式 | 文件读取 | 文件写入 | shell / tests / git | 危险命令 |
| --- | --- | --- | --- | --- |
| `confirm` | 自动执行 | 需要确认 | 需要确认 | 硬阻断 |
| `auto-edit` | 自动执行 | 自动执行 | 需要确认 | 硬阻断 |
| `full-auto` | 自动执行 | 自动执行 | 安全命令自动执行，未分类命令转确认 | 硬阻断 |

危险命令策略覆盖明显不可逆或越权的操作，例如 `sudo`、`rm -rf /`、磁盘格式化、关机/重启、fork bomb、系统目录重定向和 `curl | sh` / `wget | sh` 安装脚本。命令输出会截断并在结果中标记 `truncated`。

## Host Target 工具

`--target host` 时，本地工具由 CLI 直接在 `--cwd` workspace 内执行：

- `read_file`
- `list_files`
- `search_files`
- `write_file`
- `apply_patch`
- `run_shell`
- `run_tests`
- `git`

文件路径必须是 workspace 内的相对路径。文件写入先生成 pending change 和 unified diff；确认提交后才落盘。shell 的默认 cwd 是 workspace 根目录。每个工具结果都会写入本地 session，并通过 `/api/agents/runs/{run_id}/local-tool-events` 写入后端审计。

`host` target 的本地工具结果只有在审计写入成功后才会作为 `tool` 消息回灌并触发下一轮继续。如果后端审计失败，CLI 会在本地 session 记录 `AUDIT_FAILED` 工具事件，不写入 `tool` 消息，也不会自动继续 agent loop。

shell、tests 和 git 命令会持久化命令生命周期：pending、running、success、failed、timeout、cancelled。`/cancel <command_id>` 会请求取消正在运行的命令，`/retry <command_id>` 会基于原始命令创建新的 retry 记录并关联 `retry_of_id`。

## Sandbox Target

`--target sandbox` 时，CLI 不触碰本机文件写入或本机 shell。工具调用会转到现有 Harness sandbox/tool 路径，并继续在 TUI 中展示审批和结果。后端仍负责 sandbox policy、ToolCall 和 EventStore 记录。

## 会话和恢复

本地状态默认写在 `~/.hao`：

```text
~/.hao/config.toml
~/.hao/hao.db
~/.hao/sessions/<session_id>/stream.jsonl
~/.hao/sessions/<session_id>/tool-events.jsonl
~/.hao/sessions/<session_id>/commands.jsonl
~/.hao/sessions/<session_id>/pending-changes/<change_id>.json
~/.hao/sessions/<session_id>/diffs/*.diff
~/.hao/sessions/<session_id>/outputs/*.json
```

查看和恢复：

```bash
hao sessions
hao resume
hao resume <session_id>
```

`hao resume` 无参数时恢复最近的本地 session，并继承该 session 的 agent、cwd、mode 和 target。

v2 Step 1A 之后，`SessionStore` 还会把消息组织成树状历史，持久化 `parent_id`、`branch_id`、`source_message_id`、`tool_event_id` 和 `active_leaf_id`。`hao resume` 只恢复当前 active path，不会把同 session 的兄弟分支一起载入；旧的 `~/.hao/hao.db` 会通过增量迁移补上这些列并回填线性历史。

## 后端协议

CLI 通过 Workspace chat stream 使用 `mode=cli_agent`。模型需要工具时，后端只发出 `tool_call_requested`，状态为 `pending_local`，不通过后端 ToolRunner 执行宿主机工具。

CLI 执行或拒绝本地工具后，会把结果写入本地 session，再调用：

```text
POST /api/agents/runs/{run_id}/local-tool-events
```

该 endpoint 写入现有 `ToolCall` 和 `AgentEvent` 形态，包括 `POLICY_CHECKED`、`TOOL_CALLED` / `TOOL_DENIED_BY_POLICY`、`TOOL_RESULT_RECEIVED` / `TOOL_FAILED` / `TOOL_TIMEOUT`。

本地工具结果同时以 `tool` 消息回灌到下一轮 stream，上下文组装会保留这些 tool 消息，而不是把它们降格成普通 system 记录。
