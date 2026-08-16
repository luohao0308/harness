# Stage 10: Version Rollout Management

## Goal

Persist Agent configuration snapshots and allow operators to activate a known version.
The user value is a recoverable Agent configuration history: prompt, model, routing,
tools metadata, and orchestration settings can be inspected and restored after changes.

## Input

- Existing Agent model and Agent Studio configuration fields.
- Existing organization scoped RBAC.
- Existing Sandboxes page disabled Version Rollout infrastructure tile.
- Existing Agent Run evidence model.

## Output

- `agent_versions` table stores immutable Agent configuration snapshots.
- Authenticated APIs list versions, create snapshots, and activate a prior version.
- Sandboxes Version Rollout surface displays version history and activation controls.
- Activating a version updates the Agent record in a transaction and marks exactly one active version.

## Modules

- Backend models and migration for `agent_versions`.
- Backend Agent versions router.
- Agent configuration snapshot helper.
- Frontend Sandboxes Version Rollout section.
- Frontend task API client version functions.

## API And Schema Changes

### Data Model

`agent_versions`

| Field | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | Primary key UUID. |
| `organization_id` | `String(36)` | Required organization scope, indexed. |
| `agent_id` | `String(64)` | FK to `agents.id`, indexed. |
| `version_number` | `Integer` | Monotonic per Agent. |
| `config_snapshot` | `JSON` | Immutable snapshot of Agent config fields. |
| `created_by` | `String(36)` | User id that created the snapshot. |
| `created_at` | `DateTime` | Snapshot creation timestamp. |
| `is_active` | `Boolean` | Whether this version is currently active. |

Indexes and constraints:

- unique `(organization_id, agent_id, version_number)`;
- `(organization_id, agent_id, is_active)`;
- code-level transaction ensures one active version per Agent.

Snapshot content:

```json
{
  "id": "default",
  "name": "Default Agent",
  "description": "...",
  "role": "generalist",
  "status": "ACTIVE",
  "model_provider": "default",
  "model_name": "default",
  "system_prompt": "...",
  "tools_json": [],
  "routing_tags": [],
  "max_parallel_assignments": 1
}
```

### Version Endpoints

`GET /api/agents/{agent_id}/versions`

Permission: `AGENT_READ`.

Response:

```json
{
  "items": [
    {
      "id": "uuid",
      "agent_id": "default",
      "version_number": 1,
      "config_snapshot": {},
      "created_by": "dev-engineer",
      "created_at": "2026-06-21T00:00:00Z",
      "is_active": true
    }
  ]
}
```

`POST /api/agents/{agent_id}/versions`

Permission: `AGENT_CREATE`.

Request:

```json
{
  "activate": false
}
```

Response: created version object.

`PATCH /api/agents/{agent_id}/versions/{version_id}/activate`

Permission: `AGENT_CREATE`.

Response:

```json
{
  "id": "uuid",
  "agent_id": "default",
  "version_number": 1,
  "config_snapshot": {},
  "created_by": "dev-engineer",
  "created_at": "2026-06-21T00:00:00Z",
  "is_active": true
}
```

## Event Types

- `AGENT_VERSION_CREATED`
- `AGENT_VERSION_ACTIVATED`

Version events are administrative audit events. They do not require a Run task id and
are stored in the version response/audit path for the MVP. Future Run creation can
snapshot the active `agent_version_id` onto Run metadata.

## Frontend Display

- `SandboxesPage.tsx` Version Rollout tile becomes API-backed.
- A compact Version Rollout section lists versions for Agent `default` with version number,
  active badge, created time, creator, and activation button.
- Create snapshot button creates the next version from the current Agent config.
- Activate button is disabled for the active version and shows feedback on success.
- Optional diff is a collapsed JSON comparison of selected version snapshot versus active snapshot.
- State management uses React Query keys such as `["agent-versions", agentId]`.

## Tests

- Backend migration creates and drops `agent_versions`.
- Backend tests cover version creation, monotonic numbering, list, activation, and org isolation.
- Backend tests verify activation updates the Agent config fields from the snapshot.
- Frontend tests cover Version Rollout tile no longer disabled and version list/activate state.
- Full requested branch validation:
  - `cd apps/agent-console && npm run build`
  - `cd services/api-server && uv run pytest tests/ -q`

## Acceptance

- Sandboxes Version Rollout entry is no longer disabled.
- Creating a snapshot persists an immutable config snapshot with the next version number.
- Activating a prior version updates the Agent and marks only that version active.
- Listing versions returns active and historical snapshots for the selected Agent.
- Operators can recover from a bad Agent config change by activating a previous version.

## Not Doing

- No traffic-splitting percentage rollout in this MVP.
- No automatic snapshot on every Agent edit unless future Agent Studio integration adds it.
- No Run pinning to historical versions in this slice.
- No branch/environment promotion workflow.

## Current Status

- `implemented`
- The Sandboxes Version Rollout tile is API-backed and manages Agent `default` configuration snapshots.
- Version activation restores snapshot fields onto the Agent record and marks exactly one version active for the organization/Agent pair.

## Vertical Slice Demo

```text
Open /sandboxes
-> create Agent default snapshot
-> edit Agent config through existing Agent Studio or seed data
-> create another snapshot
-> activate version 1
-> verify Agent config returns to version 1 snapshot values
```
