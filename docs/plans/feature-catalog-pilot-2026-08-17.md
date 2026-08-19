# Feature Catalog 试点实施计划

_状态：completed | 更新：2026-08-17 | 关联任务：FCAT-001 | 关联设计：无_

## 1. 目标、成功标准与停止条件

- 目标结果：在 Harness 仓库内建立机器可读的完整功能目录、确定性人类视图、AI 任务匹配和 CI 漂移门禁，为后续抽离到 dev-workflow 提供已验证试点。
- 可验收成功标准：目录至少覆盖 8 个顶层领域和 30 个具体功能；每个具体功能具有实现状态、成熟度、支持端、验收标准、代码/规格/测试证据和已知缺口；生成矩阵可重复；AI brief 可按任务命中功能；Docs CI 可拒绝无效或漂移目录。
- 完成后停止条件：四个切片全部通过，任务与机器进度完成回写，Wiki 留存验证证据；不在本任务中抽离或发布 dev-workflow 包。

## 2. 范围与非范围

### 范围

- `docs/development/ai/feature-catalog.schema.json` 与 `feature-catalog.json`。
- 功能目录校验、查询和 Markdown 生成功具。
- 自动生成的 `docs/FEATURE-MATRIX.md` 与文档导航。
- `agent-context-brief.py` 的低 token 功能匹配。
- `validate-docs.py`、`check-docs.sh` 与现有 Docs CI 契约。
- 当前任务、计划、机器进度和 Wiki 证据回写。

### 非范围

- 产品运行时代码、API、数据库、前端交互或部署行为。
- 新增 Python、Node 或系统依赖。
- 在本任务中修改或发布 dev-workflow 分发仓库。
- 用人工百分比替代验收状态或生产成熟度证据。

## 3. 当前证据基线

- 代码/配置：`scripts/agent-context-brief.py` 已生成 Module Index 并负责任务路由；`docs/architecture/module-map.json` 与 `docs/development/ai/context-index.json` 已采用标准库 JSON 路径。
- 测试/CI：`scripts/validate-docs.py` 负责结构与启动契约，`scripts/check-docs.sh` 统一调用校验和链接检查，Docs CI 使用 Python 3.11 标准入口。
- 契约/数据：`PROJECT-SUMMARY.md`、`MODULE-INDEX.md`、`SPEC-INDEX.md`、`TASKS.md` 与 `task-progress.yaml` 分别记录稳定事实、模块、规格、当前任务和历史进度，但没有统一功能成熟度目录。
- 运行事实：Stage 07 与 Agent Knowledge Harness P0-P7 已关闭；当前外部发布证据缺口为 `REL-001`。
- Unknown：首次全量目录完成后，具体功能粒度是否需要进一步拆分；通过生成矩阵的可读性和 brief 命中证据评估，不在实现前猜测。

## 4. 规模判定与用户确认

- 规模：large
- 触发信号：跨文档数据、生成工具、AI 启动路由和 CI 校验；包含四个顺序切片和多个独立验收结果。
- 确认状态：approved
- 用户确认时间或消息指针：2026-08-17，用户消息“已确认”。
- 用户调整：无；采用已展示的四切片顺序。

| 切片 | 目标结果 | 修改范围 | 依赖 | 验收方式 | 回退点 | 状态 |
|---|---|---|---|---|---|---|
| S1 | 建立目录契约与首版清单 | Schema、Catalog、计划与当前任务状态 | 无 | 层级、状态、证据和路径人工核对；至少 8 个领域、30 个具体功能 | 删除新增目录文件并恢复任务状态 | completed |
| S2 | 交付校验、查询和确定性矩阵 | `scripts/feature_catalog.py`、`docs/FEATURE-MATRIX.md`、导航 | S1 | `--validate`、`--generate`、`--check`；重复生成无差异 | 移除工具和生成视图 | completed |
| S3 | 接入 AI 启动路由 | `agent-context-brief.py`、`context-index.json`、brief fixtures | S2 | RAG、Desktop 启动、Team 等任务命中正确功能且保持低 token | 移除功能匹配与路由条目 | completed |
| S4 | 接入 CI 门禁并完成留痕 | Docs 校验、测试、任务进度、Wiki | S3 | Docs/链接/brief/漂移/whitespace 检查通过 | 回退新增门禁，保留已验证目录数据 | completed |

状态只允许 `pending`、`in_progress`、`completed`、`blocked`，且同一时间最多一个切片为 `in_progress`。

## 5. 原则与决策

| 决策 | 选择 | 理由 | 代价 |
|---|---|---|---|
| 试点格式 | JSON + JSON Schema | 与现有索引一致，标准库可读，Docs CI 无新依赖 | 不提供原生 YAML 编辑体验 |
| 权威边界 | Catalog 记录全量能力与成熟度，Task Board 只记录当前工作 | 避免重复任务权威源 | 需要校验关联任务和缺口 |
| 进度表达 | 实现状态与成熟度分离 | 防止“已实现”等同“生产可用” | 条目字段比单一状态更多 |
| 人类视图 | 从 Catalog 确定性生成 | 防止双份手工维护 | 修改必须经过生成命令 |
| AI 路由 | task brief 只输出高分匹配项 | 保持低 token 启动路径 | 需要维护功能关键词 |

## 6. 实施切片

### S1：目录契约与首版清单

- 状态：completed
- 修改范围：Schema、Catalog、计划索引、Task Board、Working Context。
- 步骤：定义层级和枚举；按现有规格、代码、测试和任务证据登记功能；对生产成熟度采用保守标注。
- 切片验收：至少 8 个顶层领域、30 个具体功能；所有本地路径存在；未把 `REL-001` 错标为生产验证完成。
- 回退点：删除新增目录文件并恢复当前任务文档。

### S2：校验、查询与矩阵生成

- 状态：completed
- 修改范围：标准库 Python 工具、生成矩阵、文档导航。
- 步骤：实现加载/验证/查询/生成/漂移检查；生成领域汇总和具体功能表。
- 切片验收：所有 CLI 模式通过；生成结果确定；故意构造的无效枚举、断链、重复 ID 和无证据成熟度能失败。
- 回退点：移除工具、矩阵与导航入口。

### S3：AI 启动路由

- 状态：completed
- 修改范围：brief 脚本、context index、路由契约 fixtures。
- 步骤：按任务关键词匹配功能；输出状态、成熟度、入口和缺口；保持最大条目数限制。
- 切片验收：代表性中英文任务命中预期功能；无匹配任务不增加噪声；现有路由 fixtures 不回归。
- 回退点：移除功能匹配段和 feature-catalog 路由。

### S4：CI 门禁与项目留痕

- 状态：completed
- 修改范围：Docs 校验入口、项目导航、机器进度、Wiki 会话与日志。
- 步骤：把目录和生成视图纳入 required files、结构校验和漂移检查；运行完整文档门禁；写回证据。
- 切片验收：`python3 scripts/validate-docs.py`、`bash scripts/check-docs.sh`、`python3 scripts/agent-context-brief.py` 代表性 fixtures、`git diff --check` 全部通过。
- 回退点：回退新增 CI 契约并保留目录与工具供后续修复。

## 7. 偏移控制

- 当前允许修改的切片范围：S1 的目录契约、首版数据和当前任务文档。
- 跨切片共享前置修改：本计划、计划索引、Task Board 和 Working Context。
- 需要重新确认的变化：改用外部依赖、修改产品运行时、改变四切片顺序、引入数据库/API/发布风险。
- 不需要重新确认的变化：字段命名、功能粒度和校验实现等切片内部调整，前提是不改变权威边界。

## 8. 契约、迁移与发布

- 兼容策略：新增文件和可选 brief 输出；不改变现有 CLI 默认参数含义。
- 数据迁移/回填：无数据库迁移；首版目录由现有权威文档和验证记录回填。
- 发布顺序：仓库内一次交付；后续 dev-workflow 抽离是独立任务。
- 回滚/恢复：逐切片删除新增入口；现有项目文档和运行时不受影响。

## 9. 测试与验证矩阵

| 层级 | 场景 | 命令/入口 | 通过条件 |
|---|---|---|---|
| 单元 | Catalog 枚举、层级、路径、证据和查询 | 标准库测试/CLI fixtures | 合法目录通过，代表性非法目录失败 |
| 集成/契约 | 矩阵生成与漂移、brief 功能命中 | `feature_catalog.py --check`、`agent-context-brief.py --task ...` | 输出确定且命中预期功能 |
| E2E/冒烟 | 全仓文档门禁 | `bash scripts/check-docs.sh` | 结构和链接全部通过 |
| 观测/部署 | 不适用 | `git diff --check` | 无空白错误或非预期生成物 |

## 10. 风险与缓解

| 风险 | 概率/影响 | 早期信号 | 缓解/恢复 |
|---|---|---|---|
| 功能条目过粗或遗漏 | 中/中 | 任务无法匹配或矩阵无法定位代码 | 首版覆盖核心链路，保留后续细化入口 |
| 成熟度被高估 | 中/高 | 缺少发布、恢复或跨环境证据却标为 production_proven | Schema 和校验要求成熟度证据，默认保守降级 |
| Catalog 与生成矩阵漂移 | 中/中 | Git diff 显示生成结果变化 | CI 执行确定性 `--check` |
| AI brief 输出过多 | 中/中 | 普通任务返回大量功能 | 分数排序和固定上限，无匹配不输出 |
| 文档校验依赖扩大 | 低/中 | 清洁环境缺包 | 仅使用 Python 标准库 |

## 11. 文档同步

- [x] `TASKS.md` / 上下文
- [x] `PROJECT-SUMMARY.md`：新增功能清单和成熟度矩阵路径速查。
- [x] 架构/ADR：无需修改，未改变运行时架构。
- [x] `设计/契约/生成物`
- [x] Runbook/工作日志

## 12. 完成定义

- [x] 大型计划已获得用户确认并记录切片版本。
- [x] 所有切片验收通过，且过程状态按顺序更新。
- [x] 适用测试、构建、迁移、重启和冒烟通过。
- [x] 契约、文档和长期知识已同步。
- [x] 最终证据、SHA/产物身份和剩余风险已记录。
