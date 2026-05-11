# SSE Streaming Runbook

本 runbook 记录 Workspace 聊天页（`/agents/:agentId/workspace`）使用 Server-Sent Events（SSE）实现模型流式输出时，部署层（反向代理 / Ingress / CDN / API Gateway）必须满足的约束与常见排障清单。

前端不会对 `Content-Encoding` / `Transfer-Encoding` 做缓冲，但任何上游代理若对 `text/event-stream` 路径开启了 buffering 或 gzip 压缩，都会导致模型 `delta` 事件被聚合成大块后才下发，用户感知为「整条回答一次性出现」而不是逐字吐字。`useChatStream` 会在检测到可疑响应头时给对应 assistant 节点写入 `metadata.streaming_diagnostic = "possible_buffering"`，在气泡下方呈现一条琥珀色提示，作为排障线索。

> 对应需求：Req 2.1 / 2.2 / 2.3 / 2.7 / 2.8（agent-workspace-chat-v2-refine）
> 对应正确性属性：Property 2（单调流）、Property 3（commit 间隔 ≤ 16/32ms）、Property 6（SSE error classification）

## 前端行为速查

- 请求：`POST /api/agents/:agentId/runs/chat/stream`
- 响应 `Content-Type`：必须包含 `text/event-stream`
- 事件帧分隔符：`\n\n`
- 合法事件 `type`：`run_created` / `delta` / `think_delta` / `tool_call_requested` / `tool_call_result` / `artifact_created` / `usage` / `done` / `error`
- 前端 flush 策略：`useStreamFlush` 使用 `flushSync` 打破 React 18 automatic batching；高频场景（>120 delta/s）自动切 rAF 窗口合帧
- 诊断触发条件：
  - 响应头 `Content-Encoding` 命中 `gzip` / `br` / `deflate`
  - 或 `Transfer-Encoding` 缺失 `chunked` 同时 `Content-Length` 非空

出现诊断即意味着流可能被上游缓冲，**即便前端每个 `delta` 都 flush 也只能一次看到整块**；此时必须按下面的反代清单排查。

## 反向代理必须设置

### Nginx

```nginx
location /api/agents/ {
    proxy_pass http://api-server;

    # 关键：关闭 SSE 缓冲与压缩
    proxy_buffering off;
    gzip off;

    # 响应头约束
    proxy_set_header X-Accel-Buffering no;
    add_header Cache-Control no-cache;
    add_header X-Accel-Buffering no;

    # 心跳与长连接
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;

    chunked_transfer_encoding on;
}
```

### Kubernetes Ingress（nginx-ingress）

```yaml
metadata:
  annotations:
    nginx.ingress.kubernetes.io/proxy-buffering: "off"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"
    nginx.ingress.kubernetes.io/configuration-snippet: |
      add_header X-Accel-Buffering no always;
      add_header Cache-Control "no-cache" always;
      gzip off;
```

### Cloudflare / 公网 CDN

- 将 `/api/agents/*/runs/chat/stream` 路由配置为「不缓存 / 不压缩」
- 部分 CDN 需要在 Page Rule / Transform Rule 显式关闭 `Auto Minify` 与 `Brotli`
- 确认 `Content-Type: text/event-stream` 的响应未被 WAF 策略误判为 "异常长连接" 后主动切断

### AWS API Gateway / ALB

- **API Gateway REST** 不支持 SSE；改用 **HTTP API** 或直接将 ALB 指向后端
- ALB：启用 `http2` 监听器；目标组 `target_type = ip` 或 `instance`，后端需原生支持 chunked 响应
- 关闭 Lambda 响应的 `Content-Encoding: gzip`；API Gateway 的 `binaryMediaTypes` 不应包含 `text/event-stream`

### 通用排障

| 现象 | 定位 | 处置 |
| --- | --- | --- |
| 气泡一次性出现全文 | 代理 buffering 未关 | 按上文 Nginx / Ingress 清单开 `proxy_buffering off` |
| 响应头出现 `Content-Encoding: gzip` | 代理或后端主动压缩 | 在 SSE 路由上关闭 gzip；后端 FastAPI 默认不压缩 SSE，检查 Starlette middleware |
| 响应头无 `Transfer-Encoding: chunked` 且 `Content-Length` 非空 | 响应被完整缓冲后发出 | 多为代理 `proxy_buffering on` 副作用；同上 |
| 前端气泡出现琥珀色 "检测到可能的代理缓冲" | 诊断命中 | 打开浏览器 DevTools → Network 面板，勾选 `Preserve log`，选中 `/runs/chat/stream` 请求查看响应头 |
| 超过 60 秒没有任何事件 | 代理 `proxy_read_timeout` 太短 | 调到 ≥ 3600s |

## 本地开发注意事项

- 直接 `npm run dev`（Vite）走 `127.0.0.1:5173` → `127.0.0.1:8000`，中间无代理，默认即为逐字流式，若仍出现卡顿先排查后端是否阻塞事件循环
- 若使用 docker-compose 的 nginx（`deploy/docker-compose/docker-compose.yml`），确认 `deploy/nginx/agent-harness.conf` 已应用上文清单（默认工程已覆盖）

## 后端契约不变

本 runbook 涉及的约束仅影响部署层。前端 `useChatStream` 不会：
- 修改 `POST /api/agents/:agentId/runs/chat/stream` 的请求方法、URL 或请求体
- 修改 `AgentChatStreamEvent` 事件集合
- 主动中断流以对抗诊断（诊断仅写入 metadata，流继续）

排障完成后，假如 `streaming_diagnostic` 不再出现，说明反代层已经合规；此前已写入该字段的节点会随对话刷新自然消失。
