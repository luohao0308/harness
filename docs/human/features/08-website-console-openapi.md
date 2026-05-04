# 08 官网、控制台与 OpenAPI 入口

## 目标

官网负责说明平台能力，控制台负责执行任务，OpenAPI 负责接口集成。三者分别服务不同用户，但入口需要互相连通。

## 入口职责

| 入口 | 职责 |
|---|---|
| 官网 | 产品介绍、架构说明、场景方案、部署说明、文档入口 |
| 控制台 | 任务执行、事件查看、结果查看、Replay、Settings、Observability |
| OpenAPI | 接口导入、API 调试、系统集成 |

## 官网页面

```text
/
/product
/architecture
/solutions
/security
/deployment
/docs
/contact
```

## 控制台页面

```text
/tasks
/tasks/new
/tasks/:taskId
/tasks/:taskId/events
/tasks/:taskId/subagents
/sandboxes
/observability
/settings/models
/settings/policies
```

## OpenAPI

```text
docs/api/openapi.yaml
docs/api/openapi.json
http://127.0.0.1:8000/openapi.json
```

## 联动

- 官网链接控制台任务列表和创建任务页。
- 官网链接 OpenAPI JSON 和 YAML。
- 官网链接部署文档、使用流程和 Runbook。
- 控制台使用后端 API 执行任务。
- OpenAPI 与后端实现保持一致。

## 验收

- 官网不执行任务。
- 控制台不承载营销内容。
- OpenAPI 可导入 Swagger、Apifox、Postman。
- 官网代码由用户提供，AI 只做接入、构建、后端联动和部署接入。
