# Stage 8: Triggers System

## Goal

Enable external systems to start Harness Agent Runs through managed webhook triggers.
The user value is a real integration path from CI, ticketing, monitoring, or internal
business systems into an auditable Agent Run without requiring an interactive console user.

## Input

- Existing Agent management and Agent Run planning APIs.
- Existing organization scoped RBAC and API authentication.
- Tool Registry page disabled Triggers surface.
- Event Store for Run-level audit evidence.

## Output

- `triggers` table stores Agent-scoped webhook trigger configuration.
- Authenticated CRUD APIs manage trigger lifecycle.
- Public webhook endpoint verifies a shared secret proof and creates a new Agent Run.
- Tool Registry Triggers surface displays real trigger state and one-time secret creation output.

## Modules

- Backend models and migration for `triggers`.
- Backend Agent trigger management router.
- Backend public webhook router.
- Agent Run planner integration for trigger-created runs.
- Frontend Tool Registry Triggers section.
- Frontend task API client trigger functions.

## API And Schema Changes

### Data Model

`triggers`

| Field | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | Primary key UUID. |
| `organization_id` | `String(36)` | Required organization scope, indexed. |
| `agent_id` | `String(64)` | FK to `agents.id`, indexed. |
| `type` | `String(32)` | MVP value: `webhook`. |
| `endpoint_path` | `String(128)` | Public path segment, unique globally. |
| `secret_hash` | `String(64)` | SHA-256 hash of generated trigger secret. |
| `enabled` | `Boolean` | Whether public invocation is accepted. |
| `created_by` | `String(36)` | Managing user id. |
| `created_at` | `DateTime` | Creation timestamp. |
| `updated_at` | `DateTime` | Last config update. |
| `last_triggered_at` | `DateTime nullable` | Last successful public invocation. |

Indexes:

- unique `endpoint_path`;
- `(organization_id, agent_id, enabled)`;
- `(organization_id, created_at)`.

### Management Endpoints

`GET /api/agents/{agent_id}/triggers`

Response:

```json
{
  "items": [
    {
      "id": "uuid",
      "agent_id": "default",
      "type": "webhook",
      "endpoint_path": "default-ci-abc123",
      "enabled": true,
      "created_at": "2026-06-21T00:00:00Z",
      "updated_at": "2026-06-21T00:00:00Z",
      "last_triggered_at": null
    }
  ]
}
```

Permission: `AGENT_READ`.

`POST /api/agents/{agent_id}/triggers`

Request:

```json
{
  "type": "webhook",
  "endpoint_path": "optional-custom-slug",
  "enabled": true
}
```

Response includes the plaintext secret once:

```json
{
  "trigger": {
    "id": "uuid",
    "agent_id": "default",
    "type": "webhook",
    "endpoint_path": "default-ci-abc123",
    "enabled": true,
    "created_at": "2026-06-21T00:00:00Z",
    "updated_at": "2026-06-21T00:00:00Z",
    "last_triggered_at": null
  },
  "secret": "htrg_..."
}
```

Permission: `AGENT_CREATE`.

`PATCH /api/agents/{agent_id}/triggers/{trigger_id}`

Request:

```json
{
  "enabled": false
}
```

Permission: `AGENT_CREATE`.

`DELETE /api/agents/{agent_id}/triggers/{trigger_id}`

Permission: `AGENT_DELETE`.

### Public Invocation Endpoint

`POST /api/webhook/trigger/{endpoint_path}`

Headers:

- `X-Harness-Trigger-Secret: htrg_...`

Request:

```json
{
  "goal": "Run release readiness checks",
  "title": "CI release gate",
  "payload": {
    "repository": "internal/service",
    "sha": "abc123"
  }
}
```

Response:

```json
{
  "run_id": "uuid",
  "agent_id": "default",
  "status": "PLANNED",
  "trigger_id": "uuid"
}
```

The route is public and does not require JWT. It verifies the supplied secret with
constant-time hash comparison against `secret_hash`. A true HMAC signature cannot be
verified from a hash-only stored secret, so the MVP implements shared-secret proof
while preserving the required no-plaintext-at-rest property.

## Event Types

- `TRIGGER_CREATED`
- `TRIGGER_UPDATED`
- `TRIGGER_DELETED`
- `TRIGGER_INVOKED`
- `TRIGGER_REJECTED`

`TRIGGER_INVOKED` is appended to the created Run task with trigger id, endpoint path,
source IP metadata when available, and a redacted payload summary. Rejected invocations
do not have a Run task and are recorded through structured application logs in the MVP.

## Frontend Display

- `ToolRegistryPage.tsx` Triggers tile becomes API-backed.
- The Triggers section shows current Agent trigger rows with status, endpoint URL,
  last triggered time, and enable/disable/delete actions.
- Create trigger opens a compact form using existing `Card`, `Button`, `Badge`, `Table`,
  and feedback toast components.
- New secret is shown only in the create success state; subsequent list responses never
  include plaintext.
- State management uses React Query keys such as `["agent-triggers", agentId]`.

## Tests

- Backend migration creates and drops `triggers`.
- Backend tests cover create/list/update/delete.
- Backend tests cover public invocation success, disabled trigger rejection, and bad secret rejection.
- Frontend tests cover Triggers tile no longer disabled and trigger list/create state.
- Full requested branch validation:
  - `cd apps/agent-console && npm run build`
  - `cd services/api-server && uv run pytest tests/ -q`

## Acceptance

- Tool Registry Triggers surface is not disabled and shows real API-backed rows.
- Creating a webhook trigger returns plaintext secret exactly once.
- Public webhook call with the correct secret creates a planned Agent Run for the target Agent.
- Public webhook call without the correct secret returns `401` and does not create a Run.
- Trigger invocation writes Run-level event evidence.

## Not Doing

- No schedule/cron triggers in this slice.
- No third-party provider-specific webhook adapters.
- No encrypted secret vault for recoverable HMAC keys; hash-only shared-secret proof is the MVP.
- No automatic Run execution beyond the existing plan-mode Agent Run contract.

## Current Status

- `implemented`
- The Tool Registry Triggers tab is API-backed and manages webhook trigger rows for Agent `default`.
- Public webhook invocation uses `X-Harness-Trigger-Secret`, verifies the hash with constant-time comparison, and creates a planned Agent Run with `TRIGGER_INVOKED` evidence.

## Vertical Slice Demo

```text
Open /tools
-> select Agent default
-> create webhook trigger
-> copy one-time secret
-> POST /api/webhook/trigger/{endpoint_path}
-> inspect returned run_id
-> open Run Detail and verify TRIGGER_INVOKED evidence
```
