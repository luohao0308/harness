# Harness Workspace Agent Instructions

This repository already has a low-token startup path. New sessions must use it.

## First Reads

1. `docs/development/ai/agent-startup-context.md`
2. `docs/development/ai/task-progress.yaml`
3. `python3 scripts/agent-context-brief.py --task "<user task>"`

## Working Rule

- Read only the wiki, plans, and context files named by the brief.
- Use `docs/development/ai/00-execution-protocol.md` as the execution contract.
- Do not read the whole wiki unless the brief points to a gap.

## Completion Rule

- Update `docs/development/ai/task-progress.yaml` when work is complete or blocked.
- Update a relevant `omx_wiki/` session or handoff page with evidence.
- Add `omx_wiki/index.md` and `omx_wiki/log.md` entries when new wiki pages are created.

## Verification

- Run `python3 scripts/validate-docs.py` before claiming completion for docs or startup-routing work.
- Keep diffs small and avoid touching unrelated changes.


<!-- AI-WORKFLOW:CORE:START -->
# AI 协作协议（通用核心）

本文件是项目级 AI 协作规则的通用核心。它定义信息如何读取、任务如何推进、变更如何验证和知识如何沉淀，不绑定具体模型、编辑器、编程语言、框架或业务领域。

## 共享信息源

| 文件或目录 | 职责 |
|---|---|
| `AGENTS.md` | 项目级 AI 行为规则、协作约束和安全边界 |
| `docs/README.md` | 文档导航、读取顺序和权威边界 |
| `docs/TASKS.md` | 当前任务状态、待办、阻塞和技术债 |
| `docs/WORKING-CONTEXT.md` | 当前主任务的短期上下文和交接摘要 |
| `docs/WORKFLOW-ADOPTION.md` | dev-workflow 首次接入状态、既有文档映射和审计记录 |
| `docs/PROJECT-SUMMARY.md` | 稳定项目事实、模块摘要、技术决策、命令和路径速查 |
| `.dev-workflow/manifest.json` | 已安装版本、流程包、文件归属和机器可读接入状态 |
| `docs/project-memory/` | 长期、可复用且已经验证的操作知识 |
| `docs/architecture/`（如启用） | 系统、仓库、模块和运行时架构 |
| `docs/design/` 或根 `DESIGN.md`（如启用） | 当前有效的产品/技术设计与验收口径 |
| `docs/plans/`（如启用） | 多步骤变更的范围、阶段、风险和完成标准 |
| `docs/development/`（如启用） | 开发命令、Git 隔离、验证矩阵和变更影响规则 |
| `docs/contracts/`（如启用） | API、事件、Schema、CLI 等机器契约 |
| `docs/operations/`（如启用） | 发布、Preflight、健康检查、观测和回滚 |
| `docs/工作日志/`（如启用） | 历史过程和验证证据 |

## 读取顺序

1. 读取本文件，了解项目级规则、安全边界和局部规则层级。
2. 读取 `docs/README.md`，确认文档导航和权威范围。
3. 读取 `docs/TASKS.md`，确认当前任务状态、阻塞和技术债。
4. 如果 `docs/WORKING-CONTEXT.md` 的 `status` 为 `active` 且未超过 `expires`，读取它。
5. 如果启用了并行任务上下文，按 `docs/working-context/README.md` 选择当前任务对应的上下文文件，不要把多个任务混进一个文件。
6. 如果 `docs/WORKFLOW-ADOPTION.md` 仍为 `pending`，先完成首次项目画像和既有文档映射，再开始需要项目事实的代码修改。
7. 根据当前任务按需读取 `PROJECT-SUMMARY.md`、架构/设计/计划/契约/测试/运维文档；不要无差别加载整个文档目录。

## 首次接入与项目画像

如果 `PROJECT-SUMMARY.md`、项目扩展区或开发命令仍是占位内容，先做一次只读项目画像扫描，再开始代码修改。至少确认：

- 仓库拓扑（单仓库、Monorepo、多仓库工作区）及每个目录的所有权；
- 主要入口、模块边界、运行时依赖和本地启动方式；
- 测试、lint、类型检查、构建、迁移和 CI 入口；
- API/事件/Schema 等对外契约及其生成来源；
- 生产、部署、数据和凭据边界；
- 当前未知项、无法验证的假设和需要人类确认的事项。

把已经验证的稳定事实填入 `PROJECT-SUMMARY.md`，把项目专属约束填入本文件底部的扩展区。未确认的内容写成 Unknown，不要猜测。

首次接入完成后，更新 `docs/WORKFLOW-ADOPTION.md` 的状态和审计证据；安装清单中的 `onboarding.status` 应与其保持一致，并在最终审计后记录 UTC `lastAuditAt`。审计脚本本身是只读的，不会替接入者修改状态。既有项目的现有文档不因模板路径不同而被覆盖或复制成第二套权威源。

## 文档职责边界

- `TASKS.md` 只记录任务状态、明确待办、阻塞和技术债，不堆放完整过程证据。
- `WORKING-CONTEXT.md` 只记录当前主任务的临时目标、决策、阻塞、下一步和验证摘要；任务完成或过期后清理。
- `PROJECT-SUMMARY.md` 只保存稳定事实、命令、边界和路径速查，不作为实时任务或历史证据来源。
- `architecture/` 记录从代码和运行事实中确认的稳定结构，不记录一次性方案争论。
- `design/` 和 `plans/` 记录当前有效的目标、取舍、实施阶段和验收口径；被替代内容移入归档。
- `contracts/` 记录机器可验证的接口/事件/Schema 契约；人工指南不能悄悄替代机器契约。
- `project-memory/` 只保存长期、可复用、已经验证的经验，不保存当前任务状态或一次性推断。
- 工作日志只用于历史追溯，不能覆盖当前代码、接口或任务状态。
- 代码、测试结果和运行中接口是行为事实的最终证据；文档与代码冲突时必须显式报告并重新验证。

## 规则分层

- 根 `AGENTS.md` 负责全项目通用规则和项目级边界。
- 子项目可以放置同名 `AGENTS.md`，只补充该目录的技术命令、所有权和局部禁区，不复制通用核心。
- 更深目录的规则只能收窄局部范围，不能解除根规则的安全约束。
- 不为 Claude、Gemini、Cursor、Copilot 等工具复制整套规则；需要适配时由工具自身读取入口解决。

## 任务推进与移交

开始任务前：

- 明确目标、范围、成功标准和不在范围内的事项；
- 检查当前工作树、仓库拓扑和已有用户改动，不能覆盖或顺带提交无关变更；
- 识别是否需要设计、计划、契约、迁移、运维或独立审查；
- 只读取当前任务需要的文档和代码。

执行任务时：

- 优先复用现有模式和工具，保持变更小而可回退；
- 先验证假设，再修改；不要把未验证的推断写成稳定事实；
- 代码、配置、契约、数据或运行时行为变化时，执行与变更直接相关的检查；
- 如果启用了 `docs/plans/`，多文件或高风险变更先建立计划并链接到任务；
- 如果启用了 `docs/contracts/` 或 `docs/operations/`，按变更影响矩阵同步契约、迁移、发布和回滚材料。

需要移交时：

1. 在 `TASKS.md` 更新任务状态，并保留简短的交接指针；
2. 在 `WORKING-CONTEXT.md` 或任务专属上下文中记录已完成步骤、当前决策、阻塞、下一步和验证摘要；
3. 通知接手者按 `TASKS.md` → 上下文 → 领域文档 → 验证证据的顺序继续。

## 安全与变更边界

- 不读取、提交或传播密码、Token、Cookie、私钥、完整签名 URL 或其他凭据；
- 未明确授权时，不执行生产环境破坏性操作、不可逆数据操作或强制 Git 操作；
- 不使用宽泛路径、批量删除或覆盖命令处理不明确的目标；
- 不修改与当前任务无关的代码、文档、生成物或私有运行时状态；
- 任何外部动态值、线上地址、镜像、服务状态和权限配置都必须重新验证，不能把历史快照当成当前状态；
- 数据库 Schema、数据回填和删除操作必须先明确备份、兼容窗口、验证和恢复路径。

## 验证与完成标准

完成前必须：

1. 针对变更运行能证明目标的最小有效验证；
2. 按项目适用性运行 lint、类型检查、测试、构建、迁移、契约或静态检查；
3. 运行时代码、配置、依赖或启动逻辑变化时，只重启当前任务拥有的服务并执行最小冒烟；
4. 检查差异、编码、Markdown 链接、生成文件和敏感信息；
5. 检查变更影响范围，更新需要同步的任务、摘要、架构、设计、契约、Runbook 或长期经验文档；
6. 汇报变更文件、验证命令、结果、证据路径和仍存在的风险；无法运行的检查必须写明原因和替代证据。

<!-- AI-WORKFLOW:CORE:END -->

## Harness 项目扩展

- 项目入口、稳定模块、命令和敏感边界以 [`docs/PROJECT-SUMMARY.md`](docs/PROJECT-SUMMARY.md) 为快速参考；细节按 [`docs/README.md`](docs/README.md) 选择领域入口。
- `docs/development/ai/` 是 AI 启动与阶段状态权威；面向人的产品、架构、运维和 Runbook 文档按 dev-workflow 领域目录维护，导航页不得复制权威正文。
- 业务代码变更前先读取 `docs/WORKFLOW-ADOPTION.md`、`docs/TASKS.md` 和任务 brief；需要跨模块或高风险变更时建立 `docs/plans/` 计划。
- API、事件、数据库 Schema、迁移、桌面 IPC 或同步协议变化时，按 `docs/contracts/`、`docs/SPEC-INDEX.md` 和对应测试/Runbook 同步；生成 OpenAPI 使用 `python3 scripts/generate-api-docs.py`。
- 常用验证：API `cd services/api-server && .venv/bin/python -m pytest tests` 与 `.venv/bin/python -m ruff check app tests`；Console `cd apps/agent-console && npm run lint && npm run build`；文档 `python3 scripts/validate-docs.py`；交付前 `git diff --check`。
- 生产发布、真实第三方凭据、签名/公证、不可逆迁移、强制 Git 操作和删除数据需要明确授权；本地测试和文档审计保持可逆并隔离用户已有改动。

### Harness 大型计划拆分与确认门

- 这是用户指定的项目级流程门，优先于普通任务的自动继续规则；它只适用于大型计划，不为小型、局部、可一次验证的变更增加重复确认；
- 用户明确提出“大规划”“roadmap”“多阶段计划”，或任务包含高风险契约/迁移/安全/发布改动时，直接按大型计划处理；其他任务若同时出现跨两个以上模块、三个以上顺序阶段、多个独立验收结果、预计无法在一个专注开发会话内完成等至少两个信号，也按大型计划处理；
- 大型计划在修改产品代码、配置、契约或外部状态前，先做只读证据收集，并自动拆成 `2-6` 个有序、可独立验证的开发切片；
- 必须向用户列出每个切片的目标结果、修改范围、依赖关系、验收方式和回退点，并把状态标记为 `awaiting_user_confirmation`；用户可以批准原拆分，或要求合并、继续拆分、重排、增删范围；
- 用户确认前不得开始实现、提交代码、创建交付 PR 或执行外部变更；用户确认后把拆分写入 `docs/plans/`，状态改为 `approved`，每次只允许一个切片处于 `in_progress`；
- 完成并验证当前切片、更新证据后自动进入下一切片，不需要逐片重复等待；如果新事实实质改变已确认的范围、顺序、接口、迁移或风险，则暂停后续实现，列出修订差异并重新等待确认；一般实现细节调整不触发重新确认。
