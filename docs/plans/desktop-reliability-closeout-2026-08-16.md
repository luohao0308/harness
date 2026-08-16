# Desktop 可靠性交付收口实施计划

_状态：in_progress | 更新：2026-08-17 | 关联任务：APP-001、APP-002、DESK-001、REL-001 | 关联证据：[Desktop 功能截图审计](../../omx_wiki/session-2026-08-07-desktop-functional-screenshot-audit.md)_

## 1. 目标、成功标准与停止条件

- 目标结果：关闭两个已知 Console 路由缺陷，恢复 Desktop 严格类型检查，并让 Release CI 对三平台打包启动五样本 P95 证据执行可审计的校验与发布阻断。
- 可验收成功标准：兼容入口可达；`npm run type-check`、Desktop 测试与构建通过；Release workflow 为每个平台生成、验证并上传唯一启动报告；文档与任务状态同步。
- 完成后停止条件：S1-S4 依次完成，适用验证通过，正式 CI 才能产生的外部证据缺口被明确保留或由真实运行关闭。

## 2. 范围与非范围

### 范围

- Agent Console 路由、路由清单和路由回归测试。
- Desktop TypeScript 项目边界、类型测试和相关最小代码修复。
- Release workflow、启动报告校验脚本与契约测试。
- `TASKS.md`、机器进度和 Wiki 交接证据。

### 非范围

- 新增 Desktop 产品模块或重做 Console 导航。
- 数据库迁移、生产发布、创建 Release tag、签名或公证。
- 用本地结果代替 GitHub macOS/Windows/Linux runner 的真实 P95 证据。

## 3. 当前证据基线

- 代码/配置：Console 只注册 `/settings/data-management`、`/subagent-specialists` 和 `/subagent-specialists/:specialistId`；审计使用的兼容入口未注册。
- 测试/CI：`cd apps/desktop-app && npm run type-check` 退出码为 2；`build:main` 与现有 Desktop 测试历史基线通过。Release workflow 已有三平台矩阵与启动检查，但未对上传报告增加独立跨工件确认。
- 契约/数据：不改变 API、事件或数据库契约。
- 运行事实：截图审计记录 `/settings/data` 为 404，`/subagents/specialists` 被动态路由误识别为子代理 ID 后显示加载失败。
- Unknown：正式 Release CI runner 的实际 P95 数值只能由后续 tag 运行产生。

## 4. 规模判定与用户确认

- 规模：large
- 触发信号：跨 Console、Desktop、Release CI 三个所有权边界；四个顺序切片；多个独立验收结果。
- 确认状态：approved
- 用户确认时间或消息指针：2026-08-16 当前 Codex 任务中用户回复“确认”。
- 用户调整：无。

| 切片 | 目标结果 | 修改范围 | 依赖 | 验收方式 | 回退点 | 状态 |
|---|---|---|---|---|---|---|
| S1 | 兼容路由恢复 | Console routes、inventory、tests | 无 | 路由单测、Console build | 回退路由与测试差异 | completed |
| S2 | Desktop type-check 通过 | Desktop tsconfig、package、最小类型修复 | S1 | type-check、build:main、Vitest | 回退类型项目配置 | completed |
| S3 | Release P95 工件校验闭环 | release workflow、startup scripts/tests | S2 | Node tests、YAML、workflow contract | 回退 CI/脚本差异 | in_progress |
| S4 | 全量验证与证据回写 | Task Board、progress、Wiki | S1-S3 | Console/Desktop/docs/diff gates | 回退文档状态更新 | pending |

## 5. 原则与决策

| 决策 | 选择 | 理由 | 代价 |
|---|---|---|---|
| 旧路径兼容 | 重定向到当前权威路径 | 不复制页面或 API loader，保持单一实现 | URL 会被规范化 |
| 类型边界 | 拆分运行时、浏览器与测试环境并修复真实类型错误 | 保留严格检查，不用 `skip` 或扩大 `any` 掩盖问题 | 需要多个 tsconfig |
| P95 证据 | CI 生成并独立校验平台报告 | 本地无法代表真实 runner | 外部数值仍依赖正式 tag 运行 |

## 6. 实施切片

### S1：Console 兼容路由

- 状态：completed
- 修改范围：`apps/agent-console/src/app/routes.tsx`、`routeInventory.ts`、路由测试和必要的 E2E 路由清单。
- 步骤：添加数据管理与专家库旧入口重定向；覆盖列表和详情路径；锁定静态优先于动态子代理 ID 的行为。
- 切片验收：路由契约测试通过，Console build 通过。
- 回退点：删除新增重定向和相应测试。

### S2：Desktop 类型检查

- 状态：completed
- 修改范围：`apps/desktop-app/tsconfig*.json`、`package.json` 与暴露出的最小类型修复。
- 步骤：建立明确的主进程、浏览器适配器和测试类型环境；修复真实 fixture/mock 类型漂移；保留严格模式。
- 切片验收：`npm run type-check`、`npm run build:main`、`npm test` 通过。
- 验证证据：三段式严格 `npm run type-check` 通过；`npm run build:main` 通过；Desktop 全量 `38 files / 324 tests` 通过。
- 回退点：恢复原脚本与 tsconfig，保留已有生产构建路径。

### S3：Release P95 校验

- 状态：in_progress
- 修改范围：`.github/workflows/release.yml`、Desktop 启动报告库与测试。
- 步骤：增加报告文件身份/平台/架构/样本数校验，确保上传工件唯一且发布依赖全部 Desktop job 成功。
- 切片验收：启动契约测试、脚本语法、YAML 解析和 workflow 静态契约通过。
- 回退点：恢复现有启动 budget job；不影响安装包构建。

### S4：验证与回写

- 状态：pending
- 修改范围：`docs/TASKS.md`、`docs/development/ai/task-progress.yaml`、相关 `omx_wiki/` 页面和日志。
- 步骤：运行目标验证与综合门禁；关闭已证明任务；对正式 runner 才能证明的证据保持准确状态。
- 切片验收：文档校验、Markdown 链接、`git diff --check` 通过，证据与实际命令一致。
- 回退点：恢复任务状态，避免误报完成。

## 7. 偏移控制

- 当前允许修改的切片范围：S3 Release workflow、启动报告校验脚本与契约测试。
- 跨切片共享前置修改：本计划文件。
- 需要重新确认的变化：新增 API/数据库契约、改变 Release 发布语义、扩大为新 Desktop 功能。
- 不需要重新确认的变化：切片内部的测试夹具、类型定义和校验脚本细节。

## 8. 契约、迁移与发布

- 兼容策略：旧 Console URL 使用客户端 `replace` 重定向到现有权威 URL。
- 数据迁移/回填：无。
- 发布顺序：代码和静态 CI 门禁先合并；真实跨平台 P95 由后续正式 Release tag 运行产生。
- 回滚/恢复：各切片均为配置、前端路由或文档的可逆变更。

## 9. 测试与验证矩阵

| 层级 | 场景 | 命令/入口 | 通过条件 |
|---|---|---|---|
| 单元 | 路由、启动报告聚合与校验 | 定向 Vitest / Node test | 全部退出 0 |
| 集成/契约 | Desktop 类型项目、主进程构建 | `npm run type-check && npm run build:main` | 无 TypeScript 错误 |
| E2E/冒烟 | Console 兼容 URL 与现有权威页面 | Playwright route smoke | 页面终态可用，无 404/ID 误解析 |
| 观测/部署 | 三平台启动报告 workflow | Release YAML/contract；正式 tag CI | 每平台 5 样本，P95 超限阻断发布 |

## 10. 风险与缓解

| 风险 | 概率/影响 | 早期信号 | 缓解/恢复 |
|---|---|---|---|
| 兼容路径抢占动态路由 | 中/中 | `/subagents/:id` 行为变化 | 明确静态路由并补两类路径回归 |
| 类型配置只隐藏测试错误 | 中/高 | `type-check` 通过但测试 fixture 未检查 | 单独 test tsconfig，不排除测试作为最终方案 |
| CI 报告命名或架构不一致 | 中/高 | 工件合并覆盖或误接收 | 平台/架构/样本数/唯一文件强校验 |
| 外部 P95 无法本地证明 | 高/中 | 缺正式 runner JSON | 明确保留 REL-001，直到真实 tag CI 证据存在 |

## 11. 文档同步

- [ ] `TASKS.md` / 上下文
- [ ] `task-progress.yaml`
- [ ] 相关 Wiki 交接与日志
- [ ] Desktop/Release 文档（若行为契约变化）

## 12. 完成定义

- [x] 大型计划已获得用户确认并记录切片版本。
- [ ] 所有切片验收通过，且过程状态按顺序更新。
- [ ] 适用测试、构建和冒烟通过。
- [ ] 契约、文档和长期知识已同步。
- [ ] 最终证据与剩余外部风险已记录。
