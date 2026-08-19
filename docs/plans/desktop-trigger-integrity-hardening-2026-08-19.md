# Desktop / Trigger Integrity Hardening

_状态：completed | 更新：2026-08-20 | 关联任务：HARD-001 | 关联设计：[DESIGN.md](../../DESIGN.md)_

## 1. 目标、成功标准与停止条件

- 目标结果：修复当前未提交改动中已确认的 Desktop、Trigger、离线同步和变更审查完整性问题，使新功能在跨组织、乱序请求、打包运行和并发文件变化下仍然 fail closed。
- 可验收成功标准：
  - Webhook 的受限 payload 能被实际 Agent Run 使用，同时不泄露未授权原始数据。
  - Trigger、Task、AgentRun、ToolCall、Approval 的组织和父子归属在服务端强制校验。
  - 离线同步 revision 单调应用，Project Knowledge cursor 能区分完整性/错误状态，并能处理并发快照。
  - 正式打包 Desktop 注册完整离线 Agent IPC；审批写入对文件版本做 compare-and-swap，冲突不覆盖用户修改。
  - Trigger 恢复通过 worker/outbox 异步执行；Change Review 审计响应丢失时不会让 Git 状态与服务端审计永久分裂。
  - Backend、Desktop、Console、文档和打包冒烟门禁均有针对性证据。
- 完成后停止条件：5 个切片按顺序完成并记录验证证据，任务板和相关设计/契约文档同步，剩余风险明确；不扩大到新的产品能力。

## 2. 范围与非范围

### 范围

- `services/api-server/app/triggers/`、`app/api/triggers.py`、`app/api/desktop_sync.py`、`app/api/tasks.py`、相关模型/Schema/worker 和测试。
- `apps/desktop-app/src/main.ts`、`services/local-runtime.ts`、`services/offline-sync-runtime.ts`、`services/offline-agent-runtime.ts`、离线队列/文件服务/变更审查服务及测试。
- `apps/agent-console` 中离线审批展示和必要的状态/冲突反馈。
- 相关 OpenAPI、设计、任务板、计划和验证记录。

### 非范围

- 不改变既有 Agent 规划语义、模型供应商、Trigger 类型的产品范围或 Desktop 信息架构。
- 不进行生产发布、签名/公证、真实第三方凭据操作或不可逆数据删除。
- 不把 `REL-001` 的跨平台 Release runner 证据混入本计划；该任务仍按现有外部阻塞处理。

## 3. 当前证据基线

- 代码/配置：当前工作树约 127 项未提交变更，无 staged diff；本次审查确认 10 个高/中优先级问题，集中在 Trigger、离线同步/Agent、Project Knowledge、Change Review。
- 测试/CI：审查前聚焦验证通过：Backend `83 passed`、Desktop `7 files / 49 tests passed`、`python3 scripts/validate-docs.py` 通过、`git diff --check` 通过；这些测试没有覆盖本计划的边界场景。
- 契约/数据：`DESIGN.md:233` 要求本地来源只接受 Desktop 选中的受控 workspace；离线 Task 当前以 `capability_snapshot_json.sync_revision` 记录 revision；Project Knowledge 以 snapshot cursor 做幂等短路。
- 运行事实：已复现跨组织 Task 覆盖、旧 revision 覆盖新终态、Project Knowledge 不完整/完整扫描 cursor 相同，以及 Git 子目录 Trigger 范围扩大问题。
- Unknown：正式打包应用在 managed runtime 下的离线 Agent IPC 端到端证据、现有生产数据库中是否存在跨归属 UUID 冲突、worker/outbox 部署环境的实际重试参数。

## 4. 规模判定与用户确认

- 规模：large
- 触发信号：跨 Backend/Desktop/Console 三个以上模块；包含权限/组织隔离、同步一致性、异步执行和审计契约；需要多个独立验收阶段和可能的兼容策略。
- 确认状态：approved
- 用户确认时间或消息指针：2026-08-19，用户消息“可以 现在执行”。
- 用户调整：无。

大型计划确认前切片如下：

| 切片 | 目标结果 | 修改范围 | 依赖 | 验收方式 | 回退点 | 状态 |
|---|---|---|---|---|---|---|
| S1 | Trigger payload、workspace 和离线证据归属闭环 | Backend Trigger / Desktop Sync / Schema / security tests | 无 | 后端安全与契约测试；恶意跨组织/跨 Run 样本 fail closed | 保留旧字段读兼容，关闭 Trigger automation kill switch | completed |
| S2 | 离线同步和 Project Knowledge 快照单调、可区分 | Desktop file scan / API sync / project indexes / concurrency tests | S1 的归属契约 | 乱序 revision、错误/截断/删除和并发 generation 测试 | 仅回退新增 cursor/revision 应用逻辑，不删除已有索引 | completed |
| S3 | 打包 Desktop 离线 Agent 可用且写审批不覆盖新内容 | Electron main/runtime/store/file service/Console | S1 的服务端导入契约 | managed/local 两种模式 IPC smoke；CAS 写入冲突测试 | 恢复旧 runtime 路径，写工具 fail closed | completed |
| S4 | Trigger 恢复异步化，Change Review 审计可对账 | Trigger service/tasks/workers/change-review | S1、S2 的幂等与状态契约 | HTTP 快速返回、worker 重试、审计响应丢失模拟 | 关闭恢复入口或只允许新 invocation，不回滚已记录事实 | completed |
| S5 | 全量回归、文档和交付证据闭环 | Tests, OpenAPI/docs, task board/wiki, packaged smoke | S1-S4 | Backend/Desktop/Console/docs/build/package gates | 保留已验证切片，按切片回退未发布改动 | completed |

## 5. 原则与决策

| 决策 | 选择 | 理由 | 代价 |
|---|---|---|---|
| 归属校验 | 服务端以 organization、Task、AgentRun 父子关系为最终事实源 | 客户端快照和 UUID 都不可作为授权依据 | 需要补充冲突/拒绝响应和测试夹具 |
| 同步顺序 | revision/generation 单调应用，旧请求幂等忽略或冲突 | Desktop 终态请求可能乱序到达 | 需要兼容旧客户端缺失 revision 的策略 |
| workspace 身份 | 使用 Desktop/Profile 已登记的 workspace identity，路径只作解析结果 | 绝对路径可被 API 调用方伪造 | 需要补登记/失效状态和本地 profile 绑定 |
| 文件审批 | 以 hash/mtime/存在性做 compare-and-swap，冲突时拒绝 | 避免等待审批期间静默覆盖用户改动 | 用户需要重新查看 diff 并批准 |
| 异步恢复 | 复用现有 dispatch/outbox/worker，API 只做状态转换 | 避免请求线程执行完整 Plan | 需要明确 worker 重试和可观测状态 |

## 6. 实施切片

### S1：Trigger 与离线证据边界修复

- 状态：completed
- 验证证据：Backend workspace/Trigger/Desktop sync 组合 `47 passed` 且 Ruff 通过；Desktop file/preload/local-runtime `36 passed` 且 type-check 通过；Console Automation `5 passed` 且 lint 通过；Docs 与 diff 门禁通过。
- 修改范围：`services/api-server/app/triggers/service.py`、`app/api/triggers.py`、`app/api/desktop_sync.py`、相关 Schema/模型和后端测试。
- 步骤：
  1. 设计受限 webhook payload 投影，保留大小/键数/敏感字段策略，并把可用投影绑定到 Run context/goal。
  2. 为 file/git Trigger 引入 Desktop/Profile workspace identity 校验；拒绝任意未登记绝对路径、父仓库监听和 workspace 外 repo。
  3. 离线导入现有 Task 时同时校验 organization；现有 AgentRun、AgentEvent、ModelCall、ToolCall、ToolApproval 命中 UUID 时校验组织及父 Task/Run 关系。
  4. 为拒绝、冲突、幂等和兼容旧快照补充测试，不在响应中返回真实 workspace 路径。
- 切片验收：恶意跨组织/跨 Run 快照返回拒绝且数据库无变化；合法 webhook 的受限 payload 可在 Agent 执行上下文中读取；workspace 越界和父仓库 Git Trigger 均无法创建或执行。
- 回退点：保留新增字段的向后读取；若 workspace identity 迁移尚未完成，Trigger automation 保持关闭，不能退回到信任任意路径。

### S2：离线同步与 Project Knowledge 一致性

- 状态：completed
- 验证证据：Backend offline revision/Project Knowledge 组合 `33 passed` 且 Ruff 通过；Desktop offline sync/file scan `15 passed`、type-check 与 main build 通过；Console Project Knowledge `10 passed` 且 lint 通过；`git diff --check` 通过。
- 修改范围：`services/api-server/app/api/desktop_sync.py`、`app/knowledge/project_indexes.py`、`apps/desktop-app/src/services/file-service.ts`、相关 Store/测试。
- 步骤：
  1. 明确旧客户端无 revision、相同 revision、较旧 revision、较新 revision 的状态机和响应。
  2. 以 compare-and-swap 单调应用 `sync_revision`，避免旧终态覆盖新终态。
  3. 将 `complete`、scan errors、budget/truncation、root identity 纳入 Project Knowledge cursor；服务端按 generation/锁或条件更新拒绝旧快照。
  4. 覆盖删除、恢复、截断、读取失败、重复同步、后台 sync 与手动 scan 竞态。
- 切片验收：revision 10 后提交 revision 5 不改变服务端状态；同 revision 重试幂等；完整扫描与错误/截断扫描不会共享 cursor；并发旧 generation 不能覆盖新 generation。
- 回退点：新增 cursor 采用版本化前缀并兼容旧 cursor；发现旧数据无法迁移时只禁用自动 tombstone，不删除已有 Knowledge 内容。

### S3：打包 Desktop 离线 Agent 与审批写入

- 状态：completed
- 验证证据：Desktop managed/non-managed main 与 offline Agent IPC/CAS 组合 `29 passed`，完整 type-check 与 main build 通过；Console 审批摘要、冲突禁用和刷新预览 `6 passed`，lint 与生产 build 通过；`git diff --check` 通过。
- 修改范围：`apps/desktop-app/src/main.ts`、`services/local-runtime.ts`、`services/offline-sync-runtime.ts`、`services/offline-agent-runtime.ts`、离线 Store/File Service、`AdvancedFeaturesPage.tsx` 及测试。
- 步骤：
  1. 把 offline-agent IPC handler 注册从“是否启动同步 runtime”中拆出，验证 managed、local、remote/无 sidecar 模式的预期能力矩阵。
  2. 审批创建时记录目标路径、存在性、内容 hash、mtime/size 和受控 workspace identity。
  3. 执行批准写入前重新读取基线；发生变化时返回 conflict，保留待审状态，不写文件。
  4. Console 审批行展示受控相对路径、基线摘要、冲突状态和重新预览入口。
- 切片验收：正式打包 smoke 能调用 list/run/cancel/resume/approval；文件被外部修改后批准操作不改变文件；合法未修改文件仍能写入并产生完整证据。
- 回退点：IPC 不可用时 UI 明确降级且不显示可执行按钮；CAS 冲突只阻止本次写入，不回滚外部文件。

### S4：Trigger 恢复异步化与 Change Review 对账

- 状态：completed
- 验证证据：Backend Trigger resume/dispatch/Change Review audit 组合 `43 passed` 且 Ruff 通过；Desktop Change Review `11 passed`、完整 type-check 与 main build 通过；resume API 回归证明请求线程不执行 Plan 且 active dispatch 去重；completed audit 响应丢失回归证明同 operation ID 对账成功后不回滚 Git mutation。
- 修改范围：`services/api-server/app/api/tasks.py`、`app/triggers/service.py`、Trigger worker/outbox；`apps/desktop-app/src/services/change-review-core.ts`、服务端审计 API 和测试。
- 步骤：
  1. 将恢复操作拆为锁定/重置状态与 enqueue dispatch 两步，使用现有幂等 invocation ID 和 lease/fencing。
  2. API 快速返回可观测的 retrying/queued 状态；worker 负责执行、重试和最终 receipt 更新。
  3. Change Review completed audit 超时或响应丢失时按 operation ID 重试/查询，再决定是否补偿；必要时记录 compensated phase，而不是盲目回滚。
  4. 增加 worker 崩溃、重复消息、请求超时和服务器已完成但客户端未收到响应的模拟测试。
- 切片验收：恢复 API 不在请求线程执行完整 Plan；重复恢复不产生两个执行 lease；审计响应丢失后 Git 状态与服务端 operation receipt 可对账。
- 回退点：worker 不可用时恢复状态保持可见的 queued/blocked，不假装完成；Change Review 只允许显式人工补偿，不执行不可逆强制回滚。

### S5：全量验证、文档与交付闭环

- 状态：completed
- 验证证据：Backend 全量 `1647 passed`、Ruff 通过；返工聚焦审计/Project Knowledge/迁移 `27 passed`、Ruff 通过；Desktop 全量 `42 files / 360 tests passed`、type-check 和 `build:main` 通过；Console 全量稳定复跑 `108 files / 812 tests passed`、`tsc --noEmit` 和生产 build 通过；Feature Catalog、OpenAPI 生成一致性、Docs validation、`git diff --check` 通过；macOS x64 directory package 和五样本启动报告通过（总启动 P95 `3846ms <= 6000ms`）。
- 独立审查结论：架构审查提出的文件写入 TOCTOU、Change Review 并发查重、Project Knowledge 墙钟排序和离线队列 entity 粗粒度冲突问题均已修复并有回归测试；独立 `code-reviewer` 两次因服务端 `429` 不可用，不能记为独立 APPROVE。
- 交付边界：本地包未签名、未公证，且只有 macOS x64；它不满足 `REL-001` 的正式 macOS/Windows/Linux Release runner 证据。已有文件的跨平台 CAS 无法证明时当前 fail closed，拒绝覆盖，不把该限制伪装成成功写入。
- 修改范围：各切片测试、`docs/TASKS.md`、`docs/plans/README.md`、必要的 API reference/OpenAPI、设计/Runbook/Wiki 证据。
- 步骤：
  1. 运行 Backend、Desktop、Console 的针对性测试、lint/type/build 和迁移/契约检查。
  2. 运行跨模式 Desktop packaged smoke、workspace 越界攻击样本、乱序同步和审批冲突冒烟。
  3. 更新功能矩阵、设计约束、任务板和验证记录；确认没有泄露绝对路径、payload 原文或凭据。
  4. 做一次独立 review，确认每个 finding 都有测试或明确残余风险。
- 切片验收：所有必需门禁通过；`python3 scripts/validate-docs.py`、`git diff --check` 通过；每个 finding 有测试证据和文件/产物定位。
- 回退点：任何平台 packaged smoke 失败时只阻止交付，不回退已验证的服务端数据边界修复；保留失败证据供后续修复。

## 7. 偏移控制

- 当前允许修改的切片范围：S1-S5 已完成；本计划不再有 `in_progress` 切片。
- 跨切片共享前置修改：错误码/冲突响应、workspace identity、revision 字段命名和测试 fixtures 必须先形成最小契约。
- 需要重新确认的变化：新增数据库破坏性迁移、改变公开 API 语义、放宽 workspace/组织授权、改变切片顺序，或引入生产发布/凭据操作。
- 不需要重新确认的变化：切片内部的实现、测试组织、错误文案、非破坏性索引或日志字段调整。

## 8. 契约、迁移与发布

- 兼容策略：优先 additive 字段和版本化 cursor；旧 Desktop 快照缺少 revision 时按明确的兼容分支处理，不将缺失值解释为最高版本。
- 数据迁移/回填：默认不做破坏性回填；若需要增加 workspace identity 或 receipt 字段，使用 expand/dual-read/收敛策略，并为旧记录保留人工复核路径。
- 发布顺序：先 Backend 接受新旧快照并 fail closed，再发布 Desktop runtime/Console；worker 改动最后启用恢复路径。
- 回滚/恢复：按切片回滚应用逻辑和 feature flag；不删除已导入证据、不强制覆盖用户文件、不执行生产数据库删除。

## 9. 测试与验证矩阵

| 层级 | 场景 | 命令/入口 | 通过条件 |
|---|---|---|---|
| 单元 | payload 投影、归属校验、revision/CAS、cursor、文件基线 | Backend/Desktop 对应 Vitest/Pytest 文件 | 正常、旧版本、恶意输入和冲突分支全覆盖 |
| 集成/契约 | Trigger API、离线导入、Project Knowledge 更新、worker receipt | `cd services/api-server && .venv/bin/python -m pytest tests/test_triggers.py tests/test_desktop_sync_operations.py tests/test_project_knowledge_indexes.py tests/test_trigger_dispatch_worker.py tests/test_trigger_runtime_jobs.py` | 组织隔离、幂等、乱序、重试和父子关系断言通过 |
| Desktop | managed/local/remote runtime IPC、审批冲突、Profile 切换/恢复 | `cd apps/desktop-app && npm test -- --run src/services/__tests__/offline-sync-runtime.test.ts src/services/__tests__/offline-agent-runtime.test.ts src/__tests__/change-review-core.test.ts`；`npm run type-check`；`npm run build:main` | 打包能力矩阵与本地测试一致，写冲突不覆盖文件 |
| Console | 审批详情、冲突/降级状态、无 preload 浏览器回退 | `cd apps/agent-console && npm test -- --run src/features/settings/pages/__tests__/AdvancedFeaturesPage.test.tsx`；`npm run lint`；`npm run build` | 状态可读、操作禁用条件正确、无横向溢出 |
| E2E/冒烟 | 安装包 offline-agent IPC、Trigger workspace 越界、审计响应丢失 | 现有 Electron/Chromium smoke 入口，加受控临时 workspace 和临时 SQLite | managed 包可运行；越界/冲突 fail closed；审计可对账 |
| 观测/部署 | worker 重试、lease、receipt、拒绝原因和冲突指标 | 结构化日志/事件断言；`python3 scripts/validate-docs.py`；`git diff --check` | 失败可定位到 operation/run/revision，不记录凭据或原始敏感 payload |

## 10. 风险与缓解

| 风险 | 概率/影响 | 早期信号 | 缓解/恢复 |
|---|---|---|---|
| 旧 Desktop 客户端缺少 revision/identity | 高/高 | 导入冲突率上升、旧快照被拒绝 | 版本化兼容分支、可观测拒绝原因、先服务端双读 |
| workspace identity 与现有 Profile 数据不一致 | 中/高 | 合法本地 Trigger 大量 403/409 | 只新增登记映射，不放宽任意路径；提供本地迁移诊断 |
| worker 重试造成重复执行 | 中/高 | 同 invocation 多个 active lease | invocation ID 幂等、数据库 lease fencing、重复消息测试 |
| CAS 审批让用户频繁看到冲突 | 中/中 | 写入冲突率高 | 展示基线摘要和新 diff，拒绝静默覆盖，不自动重试写入 |
| 计划切片互相修改造成回归 | 中/高 | focused tests 通过但 packaged smoke 失败 | 单切片 in_progress、每片独立验收、S5 独立 review |

### Pre-mortem

1. **失败场景：** 兼容旧快照时把缺失 revision 当成最新版本，旧状态继续覆盖新状态。**预警：** 旧客户端导入成功但 revision 为空。**缓解：** 缺失 revision 只能走显式兼容策略，并记录冲突/降级事件。
2. **失败场景：** managed runtime 修复只让单元测试通过，安装包仍未暴露 handler。**预警：** 测试 mock 没有真实 preload/main 注册链。**缓解：** S3 必须包含真实 packaged IPC smoke，并覆盖 managed/local 两种模式。
3. **失败场景：** 审批冲突被 UI 当成失败后自动重试，最终仍覆盖文件。**预警：** 同一 approval 出现多次 write 事件。**缓解：** 服务端/本地 Store 使用一次性决策状态，冲突是终态，必须重新生成审批。

## 11. 文档同步

- [x] `docs/TASKS.md` / 当前计划登记
- [x] `docs/PROJECT-SUMMARY.md`（本计划未改变稳定项目摘要，无需追加事实）
- [x] 架构/ADR（既有设计约束已覆盖；新增并发/冲突边界以测试和计划证据记录）
- [x] 设计/契约/生成物（workspace、revision、错误码变化已同步 OpenAPI 与相关设计）
- [x] Runbook/工作日志/Wiki（S5 最终证据已记录）

## 12. 完成定义

- [x] 大型计划已获得用户确认并记录切片版本；确认前不修改产品代码。
- [x] 所有切片按顺序完成，且每次只有一个切片为 `in_progress`。
- [x] 适用测试、lint、type-check、build、迁移、打包和冒烟通过。
- [x] 契约、设计、任务板和长期知识已同步。
- [x] 最终证据、产物身份、未覆盖环境和剩余风险已记录。
