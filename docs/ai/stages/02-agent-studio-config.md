# Stage 2: Agent Studio Configuration Loop

## Goal

Make Agent Studio the build surface for Model plus Harness configuration.

## Input

- Existing named Agents.
- Model provider settings.
- Tool registry data.
- Prompt and sandbox controls.

## Output

- `/agents` becomes the Agent Studio entry.
- `/settings/models` persists model configuration.
- MiniMax is available as the default built-in preset.
- Agent Workspace reads selected configuration.

## Modules

- Agent Registry
- Model Settings
- Tool Registry
- Prompt summary
- Sandbox policy summary

## API And Schema Changes

- Keep `GET /api/agents`.
- Keep `GET /api/agents/{agent_id}`.
- Keep `GET /api/settings/models` and `PUT /api/settings/models`.
- Ensure MiniMax provider fields include endpoint, model name, protocol, API key env, and context metadata.

## Event Types

- `MODEL_CALLED`
- `MODEL_RESPONSE_RECEIVED`
- Settings changes are audit records when persistence layer supports settings audit.

## Frontend Display

- Agent cards show model, role, tools, routing tags, and workspace entry.
- Model settings show MiniMax preset and custom provider fields.
- Unsupported templates and RAG controls render disabled until API-backed.

## Tests

- Backend settings tests cover MiniMax defaults and save path.
- Model gateway tests cover Anthropic-compatible MiniMax payload.
- Frontend build validates Model Settings and Agent Studio components.

## Acceptance

- MiniMax preset is present by default.
- User saves model settings successfully.
- Agent Workspace shows the configured model state.

## Not Doing

- No template marketplace backend.
- No vector database ingestion.
- No visual prompt version diff.

## Vertical Slice Demo

```text
Open /settings/models
-> inspect MiniMax preset
-> save settings
-> open /agents
-> enter Workspace
-> run uses selected provider metadata
```
