# Agent Console / Agent 控制台

面向企业级 AI Agent Harness 的前端控制台。负责 `/agents/:agentId/workspace`、Inspector、历史对话面板、Run Detail 等 Workspace Pro 的全部 UI。

Front-end console for the enterprise AI Agent Harness. Hosts the workspace, inspector, history panel, run detail and the rest of the Workspace Pro UI.

## Stack

- React 18 + TypeScript (strict mode)
- Vite 6, TailwindCSS 3, Zustand 5, React Query 5, React Router 7
- Vitest + fast-check for unit and property-based tests
- lucide-react icons, echarts for sparklines

## Develop / 本地开发

```bash
cd apps/agent-console
npm install
npm run dev        # vite, http://127.0.0.1:5173
npm run lint       # tsc --noEmit
npm run build      # tsc --noEmit && vite build
npm run test -- --run   # full vitest suite (P1–P24)
```

## Browser Smoke / 浏览器级验证

The Workspace demo shell has a Playwright smoke that runs the real Vite app in Chromium with deterministic API fixtures.

```bash
cd apps/agent-console
npm run e2e:install     # install Chromium once
npm run e2e:smoke       # http://127.0.0.1:5177/agents/default/workspace
npm run e2e:smoke:headed
```

The smoke covers the header Model picker, top Tools panel, composer settings, Plugins/MCP, `/model`, Plan mode, backend connection error display, and 390px viewport overflow.

## Streaming smoke / 流式验证

v4 为 `/agents/:agentId/workspace` 的聊天流加了一条专用的 SSE 响应头管线（FastAPI + Nginx + `useChatStream`）。下面的清单用于在每次部署或回归后确认「模型是真·逐 token 流式返回」。

The v4 release hardened the chat SSE pipeline (FastAPI + Nginx + `useChatStream`). Use this checklist after every deploy / regression to confirm the model is actually streaming token-by-token.

1. **启动 / Boot the stack**
   ```bash
   docker compose -f deploy/docker-compose/docker-compose.yml up -d
   ```

2. **打开 Workspace / Open the workspace**
   访问 <http://localhost:5173/agents/default/workspace>（或在 nginx 前代理下使用对应地址）。

   Navigate to <http://localhost:5173/agents/default/workspace> (or the nginx-fronted equivalent).

3. **发送一条消息 / Send a message**
   在 Composer 中输入任意文字并按 Enter 发送。

   Type any prompt into the Composer and press Enter.

4. **DevTools Network → `chat/stream` → Response Headers**

   必须存在 / Must be present：
   - `content-type: text/event-stream; charset=utf-8`
   - `cache-control: no-cache, no-transform`
   - `x-accel-buffering: no`

   禁止出现 / Must NOT appear：
   - `content-encoding: gzip|br|deflate`
   - `content-length`（必须是 `transfer-encoding: chunked` / must fall back to `transfer-encoding: chunked`）

5. **EventStream tab**
   切换到选中请求的 EventStream 面板，观察 `delta` 事件按时序逐条到达，而不是一次性全部出现。

   Switch to the EventStream panel on the selected request and confirm `delta` events arrive one at a time in order (not bulk-flushed at the end).

6. **Jump-to-latest smoke**
   向上滚动 ≥ 200px → `JumpToLatest` 按钮应出现；点击后平滑回到最底并恢复 `autoFollow`。

   Scroll up ≥ 200px in the message list → `JumpToLatest` button appears; clicking it smoothly returns to the bottom and restores `autoFollow`.

如果第 4 步任一 header 未通过、或第 5 步出现成块到达，说明代理或压缩层破坏了流式，对照 `deploy/nginx/agent-harness.conf` 的 `^/api/agents/.*/runs/(chat|plan)/stream$` block 与 `services/api-server/app/api/agents.py` 的 `_SSE_HEADERS` 常量排查。

If step 4 fails or step 5 shows bulk arrivals, a proxy or compression layer is breaking the stream — audit the `^/api/agents/.*/runs/(chat|plan)/stream$` block in `deploy/nginx/agent-harness.conf` and the `_SSE_HEADERS` constant in `services/api-server/app/api/agents.py`.
