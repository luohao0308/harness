# Desktop 下一阶段能力路线实施计划

_状态：approved | 更新：2026-08-19 | 关联任务：`REL-001`、`DESK-002`、`DESK-003`、`DESK-004`、`DESK-005`、`DESK-006` | 关联设计：[DESIGN.md](../../DESIGN.md)_

## 1. 目标、成功标准与停止条件

- 目标结果：在现有 Desktop 任务工作台之上，依次关闭发布证据、人工待处理、变更审查、自动化、本地知识和完整离线 Agent 六个闭环。
- 可验收成功标准：每个切片都交付一个用户可观察结果，具有定向测试、跨边界契约检查和对应运行证据。
- 完成后停止条件：六个切片按顺序完成，任务板和 Feature Catalog 同步，且没有用 Desktop 复制网页端 Dashboard、Trace、Eval 或审计中心。

## 2. 范围与非范围

### 范围

- Desktop Release P95 证据、任务工作台、Run/Approval、Git/文件变更、Trigger、Knowledge/RAG、本地 Runtime、SQLite、离线模型与工具安全。
- 复用现有 Agent Run、Event Store、Policy/Approval、Knowledge、Desktop IPC 和系统通知契约。

### 非范围

- 把网页端的统计、成本、Trace、Eval 或全量审计页面搬进 Electron 主导航。
- 放宽启动预算、使用 warm profile 替代正式冷启动证据，或开放未经签名和隔离的任意插件执行。
- 未经单独授权触发生产发布、签名/公证、真实第三方凭据或破坏性迁移。

## 3. 当前证据基线

- 代码/配置：Desktop 已具备任务工作台、Team、Terminal、Files、Approvals、本地 `harnessd`、SQLite、离线简单任务、更新和跨平台打包。
- 测试/CI：Desktop 严格类型检查、主进程构建、全量 Vitest、打包和启动预算契约已有通过记录。
- 契约/数据：Agent Run、Event Store、Approval、Knowledge/RAG、Profile-scoped SQLite 和可信 preload/IPC 已有权威实现。
- 运行事实：本地优化包五样本曾通过，但正式 macOS/Windows/Linux Release runner 证据仍由 `REL-001` 跟踪。
- Unknown：正式三平台 runner 的冷启动分布，以及完整离线 Agent 对本地模型和工具组合的性能上限。

## 4. 规模判定与用户确认

- 规模：large
- 触发信号：六个顺序阶段、跨 Desktop/Console/API/CI/Knowledge/Policy、多项独立验收，并包含 Release 与离线安全边界。
- 确认状态：approved；用户已于 2026-08-17 确认 S4 新增数据库迁移和对外 API additive 扩展的修订方案
- 用户确认时间或消息指针：2026-08-17，用户先确认“按照推荐路线”，随后确认开始执行。
- 用户调整：由于当前没有正式 macOS/Windows/Linux Release 测试环境，`REL-001` 暂停为外部环境阻塞；用户批准顺序例外，从 `DESK-002` 开始实施，不触发外部 Release。

| 切片 | 目标结果 | 修改范围 | 依赖 | 验收方式 | 回退点 | 状态 |
|---|---|---|---|---|---|---|
| S1 / `REL-001` | 正式三平台启动 P95 证据 | Release CI、Desktop packaging、证据归档 | 无 | 三个平台各一份五样本通过报告，聚合证据校验通过 | 任一平台失败即阻止 Release，任务保持开启 | blocked |
| S2 / `DESK-002` | 统一待处理中心 | Workspace、Run、Approval、Team、Sync UI/API | S1（经用户批准在 S1 外部阻塞期间先行） | 一处聚合并处理审批、失败、冲突和人工介入项 | 隐藏入口，保留原分散入口和数据 | completed |
| S3 / `DESK-003` | 原生变更审查工作区 | Desktop IPC、文件/Git 服务、Diff UI、Run 审计 | S2 | 根目录内查看状态/Diff并安全接受或撤销，行为可审计 | 关闭写操作并保留只读 Diff；工作区文件不迁移 | completed |
| S4 / `DESK-004` | Trigger 与后台自动化 | Trigger API、调度/文件/Git/Webhook、Run/Event、Desktop UI | S3 | 触发器可创建、禁用、幂等执行并追溯到 Run | 全局禁用触发执行，保留配置与历史 | completed |
| S5 / `DESK-005` | 项目知识自动索引 | Desktop 目录选择、Knowledge API、增量索引、Context/RAG | S4 | 忽略规则、增量更新、索引状态和来源引用可验证 | 停止监听并解绑知识源，不修改原文件 | completed |
| S6 / `DESK-006` | 完整离线 Agent | 本地 Runtime、SQLite、模型、受限工具、审批、事件同步 | S5 | 断网下完成可审计 Agent Run，重连后幂等同步 | 禁用完整离线模式，保留现有离线简单任务 | completed |

执行状态只允许 `pending`、`in_progress`、`completed`、`blocked`；发现需要重新确认的实质偏移时临时使用 `awaiting_user_confirmation`，确认后恢复为 `in_progress`。同一时间最多一个切片为 `in_progress`。

## 5. 原则与决策

| 决策 | 选择 | 理由 | 代价 |
|---|---|---|---|
| 产品边界 | Desktop 负责执行与处理，Web 负责统计与观测 | 遵守现有 `DESIGN.md`，避免双重控制台 | 部分深度证据仍需跳转 Web |
| 实施顺序 | 严格串行 | 后一切片复用前一切片的注意力、审查和事件能力 | 总交付周期较并行更长 |
| 数据权威 | 复用现有 Run/Event/Approval/Knowledge | 保持审计和恢复语义一致 | 需要跨模块契约测试 |
| 离线安全 | 受限工具、审批和可同步事件 | 不让离线模式绕过 Harness 安全边界 | 功能范围小于完全本地任意执行 |

## 6. 实施切片

### S1：正式 Release 启动证据

- 状态：blocked
- 修改范围：`.github/workflows/release.yml`、`apps/desktop-app/scripts`、Release 证据与文档。
- 步骤：完成发布前置核对；由受控 tag 运行三平台打包测量；失败时按诊断字段修复波动；通过后归档证据。
- 切片验收：macOS/Windows/Linux x64 各五样本，所有 P95 保持现有预算且 `desktop-startup-evidence.json` 校验通过。
- 回退点：不放宽预算；失败时不创建 Release，保留上一可用产物。
- 阻塞与恢复：当前没有可用的正式三平台 Release runner；任一受控 macOS/Windows/Linux 矩阵环境具备后恢复，本地或单平台结果不替代验收。

### S2：统一待处理中心

- 状态：completed
- 修改范围：Desktop 任务工作台、Approval、Run、Team、同步冲突和本地 Runtime 健康投影。
- 步骤：定义统一待处理投影；聚合来源；实现筛选与直接动作；补通知和空/错/恢复状态。
- 切片验收：用户可在单一入口识别并处理全部支持类型，动作回写原权威对象且幂等。
- 回退点：移除聚合入口，原审批、Run、Team 和同步入口继续工作。

### S3：原生变更审查工作区

- 状态：completed
- 修改范围：可信 Git/文件 IPC、Diff/patch 展示、分块接受/撤销、Run/Approval 审计。
- 步骤：建立只读状态与 Diff；加入根目录和 symlink 边界；实现显式确认的写动作；绑定 Run 证据。
- 切片验收：常规、未跟踪、二进制、冲突和目录逃逸场景均有明确结果，禁止强制 Git 操作。
- 回退点：降级为只读 Diff，任何失败不修改用户工作区。

### S4：Trigger 与后台自动化

- 状态：completed
- 修改范围：定时、文件、Git、Webhook Trigger；后台调度；Run/Event 审计；Desktop 管理与通知。
- 只读发现：现有 Trigger 只支持 Webhook，配置列不可承载其他来源；公开 Webhook 每次同步创建一个停在 `PLANNED` 的 Run，没有调用回执、幂等键、投递历史或可靠重试。现有本地 `runtime_jobs` 已具备 SQLite 租约、fencing、active dedupe 和重试，但不是用户可配置 Trigger。
- 重新确认结果：完整验收必须扩展对外 Trigger API，并为 SQLite/PostgreSQL 新增迁移；二者均命中第 7 节的偏移确认门，用户已确认按下列修订链继续实施。
- 修订后的有序开发链：
  1. `S4.1` 持久化契约：扩展 `triggers` 的类型、名称、配置、运行游标和软删除字段；新增 `trigger_invocations`，以 `(trigger_id, idempotency_key)` 唯一约束绑定配置快照、状态、同一个 Run 和错误摘要。SQLite/PostgreSQL 使用同一 Alembic 迁移，现有 Webhook 行原位回填，不删除 secret 或历史。
  2. `S4.2` 可靠调用：抽出统一 Trigger invocation service；Webhook 保留原 URL、secret 仅创建时显示和现有响应字段，新增可选 `Idempotency-Key` 与 additive invocation 字段。首次调用创建一个 Run 并入队，重放返回同一 invocation/Run；后台执行复用现有 Plan、Executor、Policy/Approval，重试继续同一个 Run，不自动批准受控工具。
  3. `S4.3` 本地来源：本地 profile 的持久化轮询接入定时间隔、受工作区根限制的文件变化和 Git HEAD/branch 变化；来源事件先生成稳定幂等键再进入同一调用链。文件/Git 在 server profile fail closed，不读取服务器任意路径；Webhook 继续兼容 local/server。
  4. `S4.4` Desktop 管理：在 Agent Studio 增加 Trigger 管理面板和 Desktop rail 快捷入口，支持创建、启停、软删除、一次性 secret、最近调用与 Run 跳转；复用现有系统通知和待处理中心，不复制新的通知系统。
- API 兼容：现有 Webhook 创建、列表、启停、删除和调用路径保持可用；创建请求扩展为 `type + config` 的判别联合，旧 Webhook body 仍合法；删除改为软删除以保留历史；新增 invocation 列表/详情，不移除既有字段。
- kill switch：增加默认开启、可测试的全局自动化开关；关闭后停止调度并拒绝新调用，保留 Trigger、invocation 和 Run 历史，重新开启后只处理未过期的待执行项。
- 迁移/回滚：升级前验证 Alembic 单头；分别演练空库与已有 Webhook 数据的 SQLite/PostgreSQL upgrade/downgrade。功能回滚优先关闭 kill switch 和隐藏 Desktop 入口；Schema downgrade 仅在确认没有新类型/调用数据后执行，不自动删除用户数据。
- 切片验收：重复事件不重复执行，禁用即时生效，每次执行可追溯到配置快照与 Run。
- 回退点：全局 kill switch 停止触发，不删除配置或历史。
- 完成证据：SQLite/PostgreSQL 迁移、四类来源、invocation 幂等/租约/重试、local/server worker、workspace fail-closed、Desktop 管理、OpenAPI、宽窄屏和全量回归均通过；详见 [Wiki 记录](../../omx_wiki/session-2026-08-18-desktop-trigger-automation.md)。

### S5：项目知识自动索引

- 状态：completed
- 修改范围：本地目录选择、忽略规则、文件监听、Knowledge 源生命周期、增量索引和引用展示。
- 只读发现：现有 Knowledge 已具备 Source/Document/Chunk 版本化、旧版本 stale、RAG RetrievalHit/Citation 和 Context/Run 证据；现有 file Trigger 已具备受控根目录、hash snapshot、删除发现、预算和 symlink 逃逸防护。两条链目前完全独立：Trigger observation 不读取/索引内容，Desktop `fs.watch` 只监听根目录且状态随窗口退出丢失，Knowledge API 也没有项目绑定、完整快照或单文件删除/tombstone 契约。
- 偏移确认结果：用户已确认新增 SQLite/PostgreSQL 持久化表和 additive Knowledge API，按以下修订链实施。
- 修订后的有序开发链：
  1. `S5.1` 持久化契约：新增 `project_knowledge_indexes` 和 `project_knowledge_files`，按 organization/agent/Desktop profile/root identity 隔离绑定、相对路径、内容 hash、当前 KnowledgeDocument、状态、完整快照游标和错误；绝对根路径只保留在受信 Desktop profile，不写入公开响应。
  2. `S5.2` 安全扫描：扩展 Desktop 可信 IPC，使用确定性的默认 ignore、用户规则、受支持文本扩展、单文件/总量/文件数/时限预算和 root realpath/symlink 边界生成完整 snapshot；窗口重启和 Profile 切换从各自 profile 状态恢复，不能把不完整扫描解释为删除。
  3. `S5.3` 增量索引：新增项目索引创建、列表、同步、暂停/恢复和解绑 API；同步先持久化幂等收据，再复用 `ingest_knowledge_source()` 创建或 version 文档，完整 snapshot 中缺失的文件标记 tombstone 并 stale 旧 chunk，历史 Retrieval/Citation 快照不删除。
  4. `S5.4` Desktop 管理与证据：在 Knowledge 工作台提供目录绑定、ignore、状态、错误、手动重扫和解绑；Desktop 常驻 renderer 协调首次/变化/重启同步，回答和 Run Detail 显示 `project://` 相对路径、文件 hash 和文档版本，不暴露绝对路径。
- 支持边界：首版仅索引可解码 UTF-8 的文本/Markdown/常见源码与配置文件；每文件沿用 Knowledge `120000` UTF-8 bytes 上限，扫描预算更严格时以较小值为准。默认忽略 `.git`、依赖、构建、缓存、虚拟环境、密钥/环境文件和隐藏生成目录；用户规则只能进一步排除，不能取消安全默认项。
- 切片验收：新增、修改、删除、忽略、重启和跨 Profile 隔离均通过，回答可显示真实本地来源。
- 回退点：停止监听并归档知识源，原始项目文件不受影响。
- 完成证据：项目索引/文件收据、SQLite/PostgreSQL 迁移、additive API、安全 Desktop snapshot、增删改/截断/tombstone、Profile/root 竞态、Console 生命周期管理和 `project://` Citation 均有回归；后端 `53`、Desktop `339`、Console 聚焦 `24` 项通过，宽屏/390px 无横向溢出和控制台错误；详见 [Wiki 记录](../../omx_wiki/session-2026-08-18-desktop-project-knowledge-discovery.md)。

### S6：完整离线 Agent

- 状态：completed
- 修改范围：本地 Run 状态机、SQLite、模型调用、受限工具、审批、取消/恢复和在线同步。
- 实施结果：新增 Profile 级离线 Run/Event/ModelCall/ToolCall/ToolApproval 证据；本地模型不可用时确定性降级；只允许 `workspace.list_files`、`workspace.read_text` 和 `workspace.write_text` 三个结构化工具，写入始终审批，模型输出永不转为工具调用；取消、崩溃、Profile 切换和恢复保持持久状态。
- 同步结果：终态快照复用离线队列，以稳定 UUID 幂等导入既有 Task、AgentRun、AgentEvent、ModelCall、ToolCall 和 ToolApproval；无效快照进入 sync conflict，遗留 `IN_PROGRESS` 操作在重启后重新排队。
- 切片验收：断网运行、工具审批、取消、重启恢复、提示注入防护和重连同步自动化通过；本地 macOS x64 directory package 构建通过但未签名/公证，正式三平台证据仍由 `REL-001` 跟踪。
- 回退点：通过能力开关禁用完整离线 Agent，保留现有确定性离线简单任务。

## 7. 偏移控制

- 当前允许修改的切片范围：S2 至 S6 已完成；S1 `REL-001` 只保留阻塞状态和既有证据，不触发外部 Release。
- 跨切片共享前置修改：仅允许测试夹具、类型契约和文档导航等不改变后续产品范围的修改。
- 需要重新确认的变化：切片顺序、对外 API、数据库迁移、Release 行为、权限模型或离线工具风险实质变化。
- 不需要重新确认的变化：已确认切片内部的组件拆分、测试组织和等价实现细节。

## 8. 契约、迁移与发布

- 兼容策略：所有新入口保留现有 Workspace、Approval、Files、Knowledge 和离线简单任务路径。
- 数据迁移/回填：有 Schema 变化时必须提供 SQLite/PostgreSQL 双路径、升级/回滚和已有 Profile 测试。
- 发布顺序：默认按 S1 至 S6；本次经用户批准在 S1 外部环境阻塞期间先执行 S2，S2/S3/S4 完成后按已批准路线推进 S5，S1 环境具备时单独恢复验收。
- 回滚/恢复：优先功能开关、只读降级和保留原权威数据；不得删除用户工作区或离线队列。

## 9. 测试与验证矩阵

| 层级 | 场景 | 命令/入口 | 通过条件 |
|---|---|---|---|
| 单元 | Desktop 服务、状态投影、策略与幂等 | Desktop Vitest、Console Vitest、backend pytest | 变更范围全绿 |
| 集成/契约 | IPC、API、SQLite/PostgreSQL、Run/Event/Approval | 定向集成测试与迁移演练 | 双运行时契约一致，失败关闭 |
| E2E/冒烟 | 真实 Electron 的处理、Diff、Trigger、索引和离线流程 | Playwright/Electron package smoke | 用户主路径及错误恢复通过 |
| 观测/部署 | Release P95、后台执行、重启恢复与同步 | Release CI、诊断报告、事件证据 | 预算、幂等、恢复和审计满足切片标准 |

## 10. 风险与缓解

| 风险 | 概率/影响 | 早期信号 | 缓解/恢复 |
|---|---|---|---|
| 路线膨胀为第二套 Web Console | 中/高 | Desktop 出现统计和只读大盘 | 以 `DESIGN.md` 非目标为门禁 |
| Git/离线工具修改用户数据 | 中/高 | 隐式写入或缺少预览 | 根目录限制、Diff-first、审批和原子写 |
| Trigger 重复执行 | 中/高 | 一个事件生成多个 Run | 幂等键、租约、唯一约束和 kill switch |
| 本地索引泄露或跨 Profile 混用 | 低/高 | 来源归属不清 | Profile/Agent scope、忽略规则和来源审计 |
| 离线与在线状态分叉 | 中/高 | 重连覆盖终态或重复工具结果 | 终态不可变、fencing、幂等同步和冲突队列 |

## 11. 文档同步

- [x] `TASKS.md` / 路线登记
- [x] `PROJECT-SUMMARY.md`（已登记统一待处理中心稳定入口）
- [x] Feature Catalog、OpenAPI、任务板与 Wiki 证据同步
- [x] 设计/契约/Feature Catalog（S2/S3 已完成回写；S4 开始时继续维护）
- [x] 当前交接与机器进度

## 12. 完成定义

- [x] 大型计划已获得用户确认并记录切片版本。
- [x] 所有可执行切片验收通过，且过程状态按顺序更新；`REL-001` 保留外部阻塞。
- [x] 适用测试、构建、迁移、重启和本地 package 冒烟通过；正式三平台 runner 仍待外部环境。
- [x] 契约、文档和长期知识已同步。
- [x] 最终证据、产物身份和剩余风险已记录。
