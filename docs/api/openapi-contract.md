# OpenAPI Contract

API 的唯一机器契约是 [openapi.yaml](./openapi.yaml)。本文件只定义契约使用规则和变更流程。

## Ownership

```text
机器契约：docs/api/openapi.yaml
后端 schema：services/api-server/app/api/schemas.py
后端路由：services/api-server/app/api/
前端 client：apps/agent-console/src/features/*/api.ts
```

## Required API Groups

```text
Tasks
Events
Subagents
Sandboxes
WarmPool
Replay
```

## Error Contract

所有错误响应必须使用统一结构：

```json
{
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "Task not found",
    "request_id": "req_123",
    "details": {}
  }
}
```

## Change Rules

- API 路径变更必须先更新 `docs/api/openapi.yaml`。
- Request schema 变更必须同步后端 Pydantic schema。
- Response schema 变更必须同步前端 API client。
- 新增错误码必须同步测试用例。
- SSE 契约变更必须同步 Nginx 配置和控制台 EventSource hook。

## Verification

```bash
python3 scripts/validate-docs.py
```

