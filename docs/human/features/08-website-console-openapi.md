# 08 官网、控制台与 OpenAPI 入口 Spec

## 目标

官网负责说明平台能力，控制台负责执行任务，OpenAPI 负责接口集成。三者分别服务不同用户，但入口需要互相连通。

## 用户可见能力

| 能力 | 入口 | 用户结果 |
|---|---|---|
| 查看产品说明 | 官网 | 理解平台能力、架构和部署方式 |
| 进入控制台 | 官网、Nginx | 开始任务执行和运营管理 |
| 导入 OpenAPI | 官网、`docs/api` | Swagger、Apifox、Postman 导入 |
| 下载中文契约 | 官网、`docs/api` | 获取中文 JSON/YAML |

## 后端契约

```text
GET /openapi.json
GET /health
GET /metrics
```

OpenAPI 文件：

```text
docs/api/openapi.yaml
docs/api/openapi.json
apps/web-site/public/openapi.yaml
apps/web-site/public/openapi.json
```

## 前端入口

| 页面 | 数据来源 | 交互 |
|---|---|---|
| 官网 `/` | 静态内容、公开 OpenAPI 文件 | 产品入口、控制台入口、文档入口 |
| 官网 `/docs` | 文档链接、OpenAPI 文件 | 下载和导入接口契约 |
| 控制台 `/tasks` | Task API | 进入任务工作台 |
| 控制台 `/settings/*` | Settings API | 管理运行设置 |

## 数据模型

不涉及。

## 事件模型

不涉及。

## 权限模型

| 能力 | 角色 |
|---|---|
| 访问官网 | public |
| 下载 OpenAPI | public |
| 进入控制台 | authenticated user |
| 调用业务 API | 按 API 权限矩阵 |

## 状态流转

```text
访客 -> 官网 -> OpenAPI 下载
访客 -> 官网 -> 控制台登录 -> 任务工作台
研发 -> OpenAPI 导入 -> API 调试 -> 系统集成
```

## 外部服务契约

| 服务 | 用途 |
|---|---|
| Nginx | 官网、控制台和 API 反向代理 |
| Swagger / Apifox / Postman | OpenAPI 导入 |

## 观测指标

```text
http_requests_total
http_request_duration_seconds
```

## 当前实现状态

| 能力 | 状态 | 证据 |
|---|---|---|
| 官网 Next.js | 基础落地 | `apps/web-site` |
| 控制台 React + Vite | 已落地 | `apps/agent-console` |
| 中文 OpenAPI JSON/YAML | 已落地 | `docs/api` 与官网 public |
| 控制台任务入口 | 已落地 | `/tasks` |
| 控制台设置入口 | 已落地 | `/settings/models`、`/settings/policies` |
| 官网与控制台深度联动 | 已落地 | 官网首页、产品页和文档页链接控制台、OpenAPI、运行手册和真实控制台路径 |

## 缺口

| 缺口 | 影响 | 目标 |
|---|---|---|
| 官网最终设计接入 | 用户提供代码已按 Next.js 工程接入；后续仅保留视觉迭代空间 | 持续按 Figma 设计源微调 |
| 控制台全量本地化 | 主要页面和新增子 Agent 详情页已双语；后续新增页面继续巡检 | 默认中文，顶栏切换 English |

## 实现顺序

```text
1. 保持 OpenAPI 生成和公开文件同步
2. 官网接入用户提供代码
3. 官网链接控制台、文档和 OpenAPI
4. 控制台补全中文和 English 字典
5. Nginx 验证官网、控制台、API、OpenAPI 路径
```

## 验收标准

- 官网不执行任务。
- 控制台不承载营销内容。
- OpenAPI 能导入 Swagger、Apifox、Postman。
- 官网代码由用户提供，AI 只做接入、构建、后端联动和部署接入。
- 官网公开 JSON/YAML 与 `docs/api` 保持一致。
