# Frontend Agents Auth Timeout Recovery

Category: `session-log`

Tags: `frontend`, `agent-console`, `agents`, `auth`, `local-dev`

## Summary

`/agents/` could return Vite HTML but remain stuck on `正在验证登录状态...`. Browser inspection showed the React app never reached `/api/agents`; it was waiting on the auth bootstrap call. The local API process on `127.0.0.1:8000` accepted connections but did not respond to `/health` or `/api/auth/me`, so `AuthProvider` stayed in the loading state indefinitely.

## Changes

- `apps/agent-console/src/features/tasks/api.ts` now applies a 5 second timeout to `getMe()` through the existing request timeout path.
- `apps/agent-console/src/app/routes.tsx` now renders an explicit API connection error state for protected routes when auth validation fails, including the configured API base URL, error detail, and a `重新验证` action.
- `apps/agent-console/src/app/__tests__/routes.auth.test.tsx` covers the new auth error branch.
- The stale local `uvicorn --reload` process was cleared, and the Harness API was restarted from `services/api-server`.

## Validation

```text
curl --noproxy '*' http://127.0.0.1:8000/health
200 OK {"status":"ok","service":"api-server"}

curl --noproxy '*' http://127.0.0.1:8000/api/auth/me -H 'Authorization: Bearer dev-engineer-token'
200 OK dev-engineer / dev-org

Playwright browser check on http://127.0.0.1:5173/agents/
rendered 智能体工作室 with 5 agent cards; /api/auth/me, /api/agents, token optimizer, local-agent connections, and knowledge-source calls returned 200.

cd apps/agent-console && npm test -- src/app/__tests__/routes.auth.test.tsx src/features/agents/__tests__/AgentListPage.studio.test.tsx
17 passed

cd apps/agent-console && npx tsc --noEmit --pretty false --types vite/client --skipLibCheck --jsx react-jsx --lib DOM,DOM.Iterable,ES2022 --module ESNext --moduleResolution Bundler --target ES2020 --esModuleInterop --allowSyntheticDefaultImports src/app/routes.tsx src/features/tasks/api.ts
passed

python3 scripts/validate-docs.py
docs validation passed
```

## Notes

The failing API curl was initially reported as HTTP 502 when proxy environment variables were active. Retesting with `--noproxy '*'` showed the real local state: no healthy server after the stale process was killed, then a clean 200 after restarting the Harness API.
