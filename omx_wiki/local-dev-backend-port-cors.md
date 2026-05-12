# Local Dev Backend Port And CORS

Category: `debugging`

Tags: `local-dev`, `backend`, `cors`, `8000`, `5177`, `agent-console`

## Symptom

The Agent Console may show:

```text
API_BASE_URL: http://127.0.0.1:8000 · Failed to fetch
```

## Most Likely Cause Seen In This Project

Port `8000` can be occupied by a different project. In the recorded incident, the process was from:

```text
/Users/luohao/Desktop/agent_workspace/hermes_free/backend
```

It served:

```text
AI Workflow Control Plane
```

That is not the Harness API. Its CORS policy rejected the Agent Console origin `http://127.0.0.1:5177`.

## Correct Harness Backend Command

```bash
cd services/api-server
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Expected health response:

```text
{"status":"ok","service":"api-server"}
```

## Correct Frontend URL For Browser Smoke

```text
http://127.0.0.1:5177/agents/default/workspace
```

The Playwright smoke also starts Vite on `5177` through `apps/agent-console/playwright.config.ts`.

## Verification Commands

```bash
curl --noproxy '*' -sf http://127.0.0.1:8000/health
curl --noproxy '*' -i -s -X OPTIONS http://127.0.0.1:8000/api/tasks \
  -H 'Origin: http://127.0.0.1:5177' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
curl --noproxy '*' -I -s http://127.0.0.1:5177/agents/default/workspace
```

Expected:

- `/health` returns Harness `api-server`.
- CORS preflight returns `200 OK`.
- `access-control-allow-origin` includes `http://127.0.0.1:5177`.
- Workspace URL returns `200 OK`.

## Related Pages

- [[project-handoff-current-state]]
- [[workspace-demo-ready-constraints]]
- [[session-2026-05-13-workspace-browser-smoke]]
