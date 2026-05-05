# Harness 正式规格总入口

## 定位

本目录下所有文档统一纳入 Spec 体系。Spec 是产品、工程、运行、验收和变更的唯一事实源。代码实现、OpenAPI、控制台页面、部署配置和测试必须回到本规格体系校验。

配套索引：

- [Spec 功能索引](./SPEC-INDEX.md)
- [Spec 模板](./SPEC-TEMPLATE.md)

## Spec 层级

| 层级 | 目录 | 职责 |
|---|---|---|
| 产品规格 | `docs/human` | 用户能力、页面入口、使用流程、验收口径 |
| 功能规格 | `docs/human/features` | 单功能目标、接口、数据、事件、权限、状态和缺口 |
| 实施规格 | `docs/ai` | 阶段任务、执行协议、进度和 AI 落地步骤 |
| 参考规格 | `docs/ai/reference` | 架构、数据、部署、工具、Prompt、安全和前端机器契约 |
| API 规格 | `docs/api` | OpenAPI 机器契约和 API 变更规则 |
| 设计规格 | `docs/design` | Figma、页面清单、设计 Token 和控制台视觉规则 |
| 质量规格 | `docs/qa`、`docs/evals` | 测试策略、Prompt 评测和验收输入 |
| 安全规格 | `docs/security`、`docs/adr` | 威胁模型和架构决策记录 |
| 运行手册 | `docs/runbooks` | 本地开发、部署、迁移、回滚和排障步骤 |
| 演示规格 | `docs/demo` | 端到端演示脚本 |

## 规格优先级

| 优先级 | 来源 |
|---|---|
| 1 | `docs/api/openapi.yaml` |
| 2 | `docs/human/features/*.md` |
| 3 | `docs/ai/reference/*.md`、`*.yaml` |
| 4 | `docs/security/*`、`docs/qa/*`、`docs/evals/*` |
| 5 | `docs/runbooks/*`、`docs/demo/*` |
| 6 | 阶段执行文档 `docs/ai/*stage*.md` |

冲突处理规则：

```text
OpenAPI 与后端不一致：以 OpenAPI 为变更目标，随后同步后端 schema、路由、前端 client 和测试。
功能规格与阶段文档不一致：以功能规格为准，随后更新阶段文档和进度文档。
运行手册与部署配置不一致：以当前部署配置为准，随后更新运行手册。
设计规格与前端实现不一致：以设计规格为目标，随后同步组件和页面。
```

## 标准 Spec 结构

每个功能规格必须包含：

```text
目标
用户可见能力
后端契约
前端入口
数据模型
事件模型
权限模型
状态流转
外部服务契约
观测指标
当前实现状态
缺口
实现顺序
验收标准
```

不涉及的章节使用 `不涉及` 标记。

## Spec 状态

| 状态 | 含义 |
|---|---|
| 已落地 | 后端接口、数据来源、测试和前端入口已存在 |
| 基础落地 | 主链路已存在，生产级细节仍需增强 |
| 待增强 | Spec 已定义，代码只覆盖部分行为 |
| 待落地 | Spec 已定义，代码尚无稳定入口 |

## 变更流程

```text
1. 修改 Spec
2. 同步 OpenAPI
3. 修改后端 schema、路由、服务和测试
4. 修改前端 client、页面和状态
5. 修改部署配置和运行手册
6. 执行验证
7. 更新覆盖文档和进度文档
```

## 验证命令

```bash
python3 scripts/validate-docs.py
cd services/api-server && .venv/bin/python -m pytest
cd services/api-server && .venv/bin/python -m ruff check app tests
cd apps/agent-console && npm run lint
cd apps/agent-console && npm run build
cd apps/web-site && npm run lint
cd apps/web-site && npm run build
```

## 当前规格主线

```text
Model + Harness = Agent
User Goal
-> Planner
-> Executor
-> Tool / Model / Subagent
-> Docker Sandbox / WarmPool
-> Event Store
-> Replay / Result
-> Observability / Settings
-> OpenAPI / Console / Website
```

## 当前缺口主线

| 缺口 | 规格文件 | 目标 |
|---|---|---|
| Loki 日志采集 | `docs/human/features/10-observability-localization-spec.md` | 外部 Loki 采集链路增强 |
| Grafana 后端代理 | `docs/human/features/10-observability-localization-spec.md` | 已有 dashboard 列表接口，增强鉴权和 provisioning |
| OTel Trace 查询 | `docs/human/features/10-observability-localization-spec.md` | 已有 trace 查询接口，增强真实 OTel Trace 后端 |
| 控制台全量 i18n | `docs/human/features/10-observability-localization-spec.md` | 所有页面双语 |
| LLM Planner | `docs/human/features/02-planner-executor.md` | 真实模型规划、结构校验和计划版本 |
| Worker 级恢复 | `docs/human/features/03-event-sourcing-replay.md` | 长任务恢复编排 |
| 沙箱工具细节 | `docs/human/features/06-model-tool-audit.md` | 更多工具结果解析、超时分类和控制台细节 |

## 交付分层

| 交付层 | 含义 |
|---|---|
| 阶段 | 单项工程阶段 |
| 首个交付版 | 核心任务闭环 |
| 集成演示版 | 官网、控制台、后端、监控和部署打通 |
| 企业版 | 权限、审计、观测、恢复、沙箱治理和私有化增强 |
