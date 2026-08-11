# Stage 9: API Gateway External Publish

## Goal

Publish selected Agents as managed HTTP API endpoints so internal systems can invoke
Harness capabilities through stable route slugs and scoped API keys.
The user value is a controlled external integration surface with auditability,
rate-limit intent, and key rotation boundaries instead of ad hoc console-only runs.

## Input

- Existing Agent configuration and Agent Run APIs.
- Existing API key hashing pattern.
- Existing Sandboxes page disabled API Gateway infrastructure tile.
- Existing organization scoped RBAC.

## Output

- `api_gateway_routes` table stores Agent-to-public-route configuration.
- Authenticated CRUD APIs manage external publish routes.
- Public invoke endpoint authenticates by API key header and creates a planned Agent Run.
- Sandboxes API Gateway surface displays published routes and one-time API key output.

## Modules

- Backend models and migration for `api_gateway_routes`.
- Backend Agent gateway-route management router.
- Backend public gateway invoke router.
- Simple process-local rate limiter for MVP enforcement.
- Frontend Sandboxes API Gateway section.
- Frontend task API client gateway route functions.

## API And Schema Changes

### Data Model

`api_gateway_routes`

| Field | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | Primary key UUID. |
| `organization_id` | `String(36)` | Required organization scope, indexed. |
| `agent_id` | `String(64)` | FK to `agents.id`, indexed. |
| `slug` | `String(128)` | Public route slug, globally unique. |
| `api_key_hash` | `String(64)` | SHA-256 hash of route key. |
| `rate_limit` | `Integer` | Requests per minute. |
| `enabled` | `Boolean` | Whether invocation is accepted. |
| `description` | `Text` | Operator-visible route purpose. |
| `created_by` | `String(36)` | Managing user id. |
| `created_at` | `DateTime` | Creation timestamp. |
| `updated_at` | `DateTime` | Last config update. |
| `last_invoked_at` | `DateTime nullable` | Last successful invocation. |

Indexes:

- unique `slug`;
- `(organization_id, agent_id, enabled)`;
- `(organization_id, created_at)`.

### Management Endpoints

`GET /api/agents/{agent_id}/gateway-routes`

Permission: `AGENT_READ`.

Response:

```json
{
  "items": [
    {
      "id": "uuid",
      "agent_id": "default",
      "slug": "release-review",
      "rate_limit": 60,
      "enabled": true,
      "description": "Release review API",
      "created_at": "2026-06-21T00:00:00Z",
      "updated_at": "2026-06-21T00:00:00Z",
      "last_invoked_at": null
    }
  ]
}
```

`POST /api/agents/{agent_id}/gateway-routes`

Permission: `AGENT_CREATE`.

Request:

```json
{
  "slug": "release-review",
  "description": "Release review API",
  "rate_limit": 60,
  "enabled": true
}
```

Response includes plaintext API key once:

```json
{
  "route": {
    "id": "uuid",
    "agent_id": "default",
    "slug": "release-review",
    "rate_limit": 60,
    "enabled": true,
    "description": "Release review API",
    "created_at": "2026-06-21T00:00:00Z",
    "updated_at": "2026-06-21T00:00:00Z",
    "last_invoked_at": null
  },
  "api_key": "hgw_..."
}
```

`PATCH /api/agents/{agent_id}/gateway-routes/{route_id}`

Permission: `AGENT_CREATE`.

Request:

```json
{
  "description": "Updated purpose",
  "rate_limit": 30,
  "enabled": false
}
```

`DELETE /api/agents/{agent_id}/gateway-routes/{route_id}`

Permission: `AGENT_DELETE`.

### Public Invoke Endpoint

`POST /api/gateway/{slug}/invoke`

Headers:

- `X-Harness-Gateway-Key: hgw_...`

Request:

```json
{
  "goal": "Summarize this incident",
  "title": "Incident summary",
  "input": {
    "ticket_id": "INC-123",
    "body": "..."
  }
}
```

Response:

```json
{
  "run_id": "uuid",
  "agent_id": "default",
  "status": "PLANNED",
  "route_id": "uuid",
  "slug": "release-review"
}
```

## Event Types

- `API_GATEWAY_ROUTE_CREATED`
- `API_GATEWAY_ROUTE_UPDATED`
- `API_GATEWAY_ROUTE_DELETED`
- `API_GATEWAY_INVOKED`
- `API_GATEWAY_REJECTED`
- `API_GATEWAY_RATE_LIMITED`

`API_GATEWAY_INVOKED` is appended to the created Run task with route id, slug,
rate limit, and a redacted input summary.

## Frontend Display

- `SandboxesPage.tsx` API Gateway tile becomes API-backed.
- A compact API Gateway section lists published routes with slug, Agent, rate limit,
  enabled state, last invocation time, and invocation URL.
- Create route action opens a form using existing UI primitives and shows the generated
  API key only once.
- Route rows support enable/disable and delete.
- State management uses React Query keys such as `["agent-gateway-routes", agentId]`.
- Default Agent `default` is used for the MVP selector unless a broader Agent selector
  is already present on the page.

## Tests

- Backend migration creates and drops `api_gateway_routes`.
- Backend tests cover create/list/update/delete.
- Backend tests cover public invocation success, bad key rejection, disabled route rejection,
  and per-minute rate-limit rejection.
- Frontend tests cover API Gateway tile no longer disabled and route management state.
- Full requested branch validation:
  - `cd apps/agent-console && npm run build`
  - `cd services/api-server && uv run pytest tests/ -q`

## Acceptance

- Sandboxes API Gateway entry is no longer disabled.
- Creating a route returns a plaintext API key exactly once.
- `POST /api/gateway/{slug}/invoke` with a valid route key creates a planned Agent Run.
- Bad key, disabled route, and rate-limit excess do not create Runs.
- Run Detail can show `API_GATEWAY_INVOKED` event evidence for gateway-created Runs.

## Not Doing

- No streaming gateway response in this slice.
- No custom request/response schema builder.
- No distributed rate limiter; MVP enforcement is process-local.
- No API key plaintext recovery after creation.

## Current Status

- `implemented`
- The Sandboxes API Gateway tile is API-backed and manages published Agent endpoint rows for Agent `default`.
- Public gateway invocation uses `X-Harness-Gateway-Key`, verifies the stored key hash, enforces an MVP process-local rate limit, and creates a planned Agent Run with `API_GATEWAY_INVOKED` evidence.

## Vertical Slice Demo

```text
Open /sandboxes
-> create API Gateway route for Agent default
-> copy one-time API key
-> POST /api/gateway/{slug}/invoke
-> inspect returned run_id
-> open Run Detail and verify API_GATEWAY_INVOKED evidence
```
