# 安装并使用 hao CLI

`hao` 是 Harness 的本地 Agent CLI，用来在终端里连接 Harness 后端、启动本地 TUI、执行计划和执行任务。

OMX 是工作流、技能和子智能体编排层。`hao` 管理的是 Harness API 凭据、本地会话、宿主机或沙箱工具执行，以及运行审计；它不是浏览器登录入口。

## 前置要求

先确认本机有 Node.js 18 或更新版本，并且 `uv` 在 `PATH` 中。npm 包 `@harness/hao` 只是一个轻量启动器，真正运行时会调用随包安装的 Python CLI：

```bash
node -v
uv --version
```

在本地仓库安装时，从任意目录指定仓库里的 `services/api-server` 路径：

```bash
npm install -g /path/to/harness/services/api-server
```

如果已经在仓库根目录，也可以用相对路径：

```bash
npm install -g services/api-server
```

发布到 npm registry 后，才使用：

```bash
npm install -g @harness/hao
```

不要用 `npm install -g hao`。npm 上已有旧的同名 `hao` 包，它不是 Harness CLI。

## 确认装到的是正确的 hao

安装后先看命令解析到哪里：

```bash
command -v hao
realpath "$(command -v hao)"
hao --help
```

正确的帮助会包含 `login`、`status`、`logout`、`doctor`、`chat`、`plan`、`act`。如果帮助里只看到 `install / uninstall / list / version`，说明终端命中了旧的同名 npm 包。

当前版本可以用这些形式确认：

```bash
hao -v
hao -V
hao --version
hao version
```

这些命令应该输出类似：

```text
hao 0.1.0
```

如果帮助仍显示 `install / uninstall / list / version`，或者版本命令不能输出 `hao 0.1.0` 这类结果，优先按下面的旧包冲突流程处理。

## 旧包和 EEXIST 的处理

如果安装时报 `EEXIST`，说明全局位置已经有一个叫 `hao` 的文件或链接。先不要直接 `--force` 覆盖，优先清掉旧包再安装当前包：

```bash
npm uninstall -g hao
npm uninstall -g @harness/hao
npm install -g /path/to/harness/services/api-server
```

然后重新验证：

```bash
command -v hao
realpath "$(command -v hao)"
hao --version
hao --help
```

`npm warn Unknown user config "disturl"`、`deprecated glob`、`deprecated inflight` 这类输出通常是 npm 或旧依赖的警告；真正会阻断 npm 安装的是 `EEXIST` 这类文件冲突。缺少 `uv` 一般会在运行或验证 `hao` 时暴露，因为 npm 启动器需要调用 `uv run --project ... hao ...`。只有确认残留的 `hao` 文件来自旧 npm 全局安装，并且卸载命令清不掉时，才手动移除那个冲突文件。

## 登录和状态检查

`hao` 不走浏览器 OAuth 登录流程。它用 Harness API 地址和 bearer token 保存本地配置：

```bash
hao login --api-url http://127.0.0.1:8000 --token <token>
hao status
hao doctor
```

`login` 等价于 `auth set`，`status` 等价于 `auth status`。退出登录时用：

```bash
hao logout
hao status
```

`logout` 只清除持久化 token，保留 API URL，不会删除 `~/.hao` 下的会话、命令记录或本地数据库。环境变量 `HAO_API_URL` 和 `HAO_API_TOKEN` 会优先于本地配置文件。

## 启动 TUI 和执行任务

裸命令会启动本地 TUI：

```bash
hao
```

更推荐在具体项目目录里显式指定工作区和权限模式：

```bash
hao --cwd /path/to/workspace --mode confirm --target host
```

常用模式：

- `confirm`：读文件自动执行，写文件、shell、测试和 git 操作需要确认。
- `auto-edit`：读写文件自动执行，shell、测试和 git 操作需要确认。
- `full-auto`：安全命令可自动执行，危险命令仍会硬阻断。

一次性计划或执行可以直接用：

```bash
hao plan --cwd /path/to/workspace "先给这个改动写一个计划"
hao act --cwd /path/to/workspace --mode confirm --target host "实现这个改动并验证"
```

需要恢复本地会话时：

```bash
hao sessions
hao resume
hao resume <session_id>
```

## TUI 里的 slash commands

进入 TUI 后，底部输入框既可以直接输入自然语言，也可以输入 `/` 打开命令菜单。`/help [query]` 和 `/commands [query]` 会显示同一份可过滤命令目录。

当前 TUI 采用本地 Agent CLI 的 inline 终端页面：`hao` 不再切到单独的全屏编辑器式 alternate screen，而是在当前 shell 输出流里显示 `hao Code` 欢迎框、主会话和底部 `›` 输入提示。欢迎框按本地 Agent CLI 启动页排成左右两栏，左侧是 `Welcome back!`、图标、模型/计费和当前目录，右侧是 Tips 和 What's new。工具、diff、文件、审批、命令任务、输出、todo 和验证视图不会默认占用右侧分屏；输入 `/tools`、`/diff`、`/tasks`、`/view ...` 等命令时才会打开底部工作台抽屉。`/clear` 会清空当前可见会话并隐藏工作台抽屉。

`hao` 连接本地 Harness API 时会忽略全局 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` 环境代理，避免本机 `127.0.0.1` 请求因为 SOCKS 代理缺少 `socksio` 而失败。

真实终端里的用户输入只依赖终端自身 echo，`hao` 不会再额外打印第二条用户消息；中文等 UTF-8 输入会按字节安全解码，不会因为终端编码边界触发 `UnicodeDecodeError`。如果 stream 返回 401 或 403，TUI 会显示 hao 登录或权限提示，而不是 httpx 的原始 MDN 错误文本。

常用工作流命令：

- `/init`：在当前 `--cwd` 下创建 `HAO.md` workspace 指令文件；文件已存在时不会覆盖。
- `/release-notes`、`/whats-new`：查看 hao v4 系列本地变更摘要。
- `/chat`：切回普通对话。
- `/plan`：切到只规划模式，不执行本地或沙箱工具。
- `/act`、`/run`、`/execute`：切到可执行工作流。
- `/continue`：沿当前 active path 继续，不新增用户消息。
- `/branch <message_id>`：切到某条历史消息对应的分支。
- `/resume [session_id]`：列出或在当前 TUI 中加载本地 session。

常用配置和状态命令：

- `/model [provider/model|provider model]`：查看或切换后续请求记录的模型标识。
- `/permissions confirm|auto-edit|full-auto`、`/mode ...`、`/allowed-tools ...`：查看或切换本地权限模式。
- `/target host|sandbox`：切换宿主机执行或 Harness sandbox 执行。
- `/output-style default|concise|explanatory|review`：把回复风格提示写入下一轮本地 context。
- `/config`、`/settings`：查看当前模型、模型强度、工作流、target、权限、输出风格、compact 圆环、session、run 和 cwd。
- `/usage`、`/cost`、`/stats`：查看本地消息、工具、审批、命令、compact 圆环和 compact 计数；当前不会伪造真实 token 成本。

常用工作台命令：

- `/tools`、`/diff`、`/files`、`/approvals`、`/outputs`：打开底部工作台抽屉并切换视图。
- `/tasks`、`/bashes`：打开本地 shell/test/git 命令任务视图。
- `/view tools|diff|files|approvals|commands|plan|outputs|todos|verify`：打开指定工作台视图。
- `/todo [add|done|fail]`、`/todos`：维护当前分支的待办。
- `/verify [pass|fail]`：记录当前分支验证证据。
- `/approve <id>`、`/reject <id>`：处理待审批工具或待提交变更。
- `/cancel <command_id>`、`/retry <command_id>`：取消或重试本地命令。

`/compact [instructions]` 和 `/compress [instructions]` 会把较早的 active-path 消息替换成一条确定性的本地 system 摘要，并保留最近 6 条消息进入下一轮请求。它不是模型级摘要，也不会计真实 token 成本；如果当前 active path 不超过 6 条消息，只会提示无需 compact。底部状态区会用 `○/◔/◑/◕/◉/●` 圆环显示 compact 比例，并同时显示模型强度、输出风格、审批数和命令数。

工具和命令输出会以终端任务卡片展示状态、exit code、命令行、stdout/stderr 首行；完整输出仍保存在 `~/.hao/sessions/<session_id>/` 下的本地 artifact 中。

如果目标只是检查安装，不要直接进入长会话；先跑 `hao --help`、`hao --version`、`hao status` 和 `hao doctor`，确认命令、版本、凭据和后端连通性都正确。
