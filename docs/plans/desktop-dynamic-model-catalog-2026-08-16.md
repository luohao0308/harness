# Desktop 动态模型目录实施计划

_状态：completed | 更新：2026-08-16 | 关联任务：DESK-002 | 关联设计：[Desktop 动态模型目录记录](../../omx_wiki/session-2026-08-16-desktop-dynamic-model-catalog.md)_

## 1. 目标、成功标准与停止条件

- 目标结果：Desktop 使用用户实际检测并保存的模型目录，不再依赖特定供应商的硬编码模型列表。
- 可验收成功标准：检测结果能安全持久化并在重启后成为后端 allowlist；设置页只展示当前后端允许的模型；Base URL 变化或目录缺失时 fail closed 到当前模型。
- 完成后停止条件：四个切片依次验证通过，桌面实机完成检测、保存、重启和随机消息冒烟，文档与 Git 交付证据完整。

## 2. 范围与非范围

### 范围

- Electron preload/IPC、secure profile 与本地运行时 bootstrap。
- FastAPI 本地运行时模型配置和 allowlist。
- Desktop 设置页、模型高级设置页及其测试。
- 本地打包 Desktop 冒烟、文档与交付提交。

### 非范围

- 不新增启动时自动联网刷新。
- 不把模型 API Key 暴露给 renderer、日志或普通配置存储。
- 不改变浏览器部署的服务端模型目录治理方式。
- 不新增供应商 SDK 或依赖。

## 3. 当前证据基线

- 代码/配置：Desktop 当前只持久化 Base URL、默认模型和加密密钥；五模型 allowlist 由供应商 URL 特判生成。
- 测试/CI：上一版本后端、Desktop、Agent Console 定向测试、构建和 live 五模型调用已通过。
- 契约/数据：`LocalRuntimeModelConfigInput` 与 bootstrap 尚无模型目录字段。
- 运行事实：已验证供应商当前返回五个可调用模型；目录属于动态外部事实，不能长期硬编码。
- Unknown：供应商后续目录变化频率未知，因此只在显式检测并保存时更新，不在启动链增加网络依赖。

## 4. 规模判定与用户确认

- 规模：large
- 触发信号：跨 Desktop/IPC/backend/frontend 四个边界，包含四个顺序阶段和独立验收结果。
- 确认状态：approved
- 用户确认时间或消息指针：2026-08-16，用户回复“确认”。
- 用户调整：无。

| 切片 | 目标结果 | 修改范围 | 依赖 | 验收方式 | 回退点 | 状态 |
|---|---|---|---|---|---|---|
| S1 | 模型目录随 Desktop 配置安全持久化并进入 bootstrap | preload、IPC、secure profile | 无 | Desktop 单元测试与主进程构建 | 移除新增目录字段，旧 profile 仍兼容 | completed |
| S2 | 后端使用动态目录作为 allowlist | local runtime API、bootstrap、settings | S1 | 后端定向测试与 Ruff | 缺失目录时保留单模型 fail-closed | completed |
| S3 | 设置页保存并展示动态目录 | Desktop settings、Model Settings | S2 | Vitest、lint、build | 保留原保存路径，目录字段可省略 | completed |
| S4 | 完整回归、桌面冒烟与交付 | tests、docs、Desktop package、Git | S1-S3 | 检测/保存/重启/随机消息和交付门禁 | 回退本计划提交，不迁移用户数据 | completed |

## 5. 原则与决策

| 决策 | 选择 | 理由 | 代价 |
|---|---|---|---|
| 目录刷新 | 用户显式检测后随 Save 持久化 | 避免启动延迟和供应商故障影响 | 目录不会后台自动刷新 |
| 缺失目录 | 仅允许当前选中模型 | fail closed，避免显示或调用未验证模型 | 首次手填时只有一个可选模型 |
| 存储位置 | 复用 Desktop `secrets.json` 的受限 profile | 单一原子持久化点，已有 `0600` 与重启路径 | 非秘密目录与秘密字段同文件管理 |
| UI 来源 | 后端 allowlist 为权威，静态目录只补友好名称 | 动态模型不被静态前端列表隐藏 | 未知模型显示原始 ID |

## 6. 实施切片

### S1：Desktop 配置契约与持久化

- 状态：completed
- 修改范围：`apps/desktop-app/src/preload-api.ts`、`services/local-runtime*.ts` 及测试。
- 步骤：新增可选模型目录；严格校验、去重、限长；原子持久化并写入 bootstrap。
- 切片验收：旧 profile 可读；目录重启恢复；API Key 安全断言不回归；Desktop 定向测试和构建通过。
- 验证证据：`npx vitest run ...local-runtime-secrets.test.ts ...local-runtime.test.ts ...preload-extended.test.ts` -> 3 files / 34 tests passed；`npm run build:main` -> passed。
- 回退点：删除可选字段即可恢复旧契约，无数据迁移。

### S2：后端动态 allowlist

- 状态：completed
- 修改范围：`services/api-server/app/local_runtime/`、Settings 和测试。
- 步骤：接收/验证目录，bootstrap 注入，移除供应商 URL 特判；省略时退化为当前模型。
- 切片验收：有效、重复、缺失、选中模型不在目录和重启场景均有测试。
- 验证证据：`cd services/api-server && .venv/bin/python -m pytest tests/test_local_runtime_bootstrap.py -q` -> 46 passed；`.venv/bin/ruff check app/local_runtime/bootstrap.py app/local_runtime/api.py tests/test_local_runtime_bootstrap.py` -> passed。
- 回退点：恢复单模型配置，不影响密钥与 Base URL。

### S3：动态设置页

- 状态：completed
- 修改范围：Desktop 设置页、模型设置页、目录工具和测试。
- 步骤：绑定检测结果与规范化 Base URL；Save 发送可信目录；后端行驱动可用模型展示。
- 切片验收：Base URL 变化清空旧目录；新模型可选；不可用旧模型不显示。
- 验证证据：DesktopSettingsPage/ModelSettingsPage -> 2 files / 27 tests passed；`npm run lint -- --pretty false` -> passed；`npm run build` -> passed（2414 modules）。
- 回退点：可省略目录字段，保存继续兼容单模型模式。

### S4：集成验证与交付

- 状态：completed
- 修改范围：回归、Desktop 运行、文档和 Git。
- 步骤：完整质量门禁；桌面实机检测、保存、重启、随机消息；按切片提交并推送。
- 切片验收：全部命令和实机证据通过，无凭据进入 Git 或输出。
- 验证证据：后端全量 `1544 passed`；Desktop `38 files / 326 tests passed`；Console 模型/桌面定向 `43 passed`，隔离 `workspaceScope` `2 passed`；Console lint/build 与 Desktop package 通过；新包发现 6 模型、保存后 Settings 6 模型、重启恢复 6 模型、随机中文消息返回非空回复。
- 回退点：使用切片提交独立 revert；profile 新字段被旧版本忽略。

## 7. 偏移控制

- 当前允许修改的切片范围：S4 集成验证与交付。
- 跨切片共享前置修改：仅新增可选字段和测试夹具。
- 需要重新确认的变化：引入自动联网、额外数据存储、公共 API 破坏性变化或新的密钥处理方式。
- 不需要重新确认的变化：字段命名、校验帮助函数和测试组织等切片内部细节。

## 8. 契约、迁移与发布

- 兼容策略：新目录字段始终可选；旧 profile 与旧 renderer 调用继续有效。
- 数据迁移/回填：无；首次成功检测并保存时自然写入。
- 发布顺序：同一 Desktop 版本同时交付 Electron、sidecar 和 renderer。
- 回滚/恢复：旧版本忽略新增 profile 字段；后端缺失字段保持单模型 allowlist。

## 9. 测试与验证矩阵

| 层级 | 场景 | 命令/入口 | 通过条件 |
|---|---|---|---|
| 单元 | profile、IPC、bootstrap、API、UI | Desktop/FastAPI/Vitest 定向测试 | 全部通过 |
| 集成/契约 | renderer -> IPC -> backend -> restart | Desktop service 与 backend local-runtime tests | 目录一致且 fail closed |
| E2E/冒烟 | 检测、保存、重启、随机消息 | packaged Desktop live smoke | 可用模型响应且状态恢复 |
| 观测/部署 | lint、type/build、docs、diff、secret scan | 项目交付命令 | 无错误、无密钥泄漏 |

## 10. 风险与缓解

| 风险 | 概率/影响 | 早期信号 | 缓解/恢复 |
|---|---|---|---|
| renderer 伪造超大目录 | 中/中 | IPC payload 异常 | 主进程和后端双重限长、去重、格式校验 |
| Base URL 与旧目录串用 | 中/高 | 保存后出现错误模型 | UI 绑定 discovery URL，变更即失效；后端要求当前模型在目录内 |
| 动态模型被静态 UI 隐藏 | 高/中 | 高级页缺少新 ID | 使用后端 provider rows 构建目录，静态数据只补标签 |
| 供应商暂时不可用 | 中/中 | 检测失败 | 不覆盖已保存目录，启动不自动检测 |

## 11. 文档同步

- [x] `TASKS.md` / 上下文
- [ ] `PROJECT-SUMMARY.md`
- [ ] 架构/ADR
- [ ] 设计/契约/生成物
- [x] Runbook/工作日志

## 12. 完成定义

- [x] 大型计划已获得用户确认并记录切片版本。
- [x] 所有切片验收通过，且过程状态按顺序更新。
- [x] 适用测试、构建、重启和冒烟通过。
- [x] 契约、文档和长期知识已同步。
- [x] 最终证据、SHA/产物身份和剩余风险已记录。
