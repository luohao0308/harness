# Local Agent HAO Mock Provider Fallback

Category: `session-log`

Tags: `local-agent`, `hao`, `model-routing`, `mock-model`, `deepseek`, `live-verification`

## Problem

The user reported a HAO local Agent failure:

```text
Local Agent received the backend mock model response. Configure a real model/API key for the selected provider before using local Agent chat.
Run: 31d88315-589e-4b43-a9e2-e0a8e05e279c
```

Inspection showed that Run requested `openai-compatible` / `gpt-5.5`. Current model settings had `openai-compatible` missing its API key, while `deepseek-flash` / `deepseek-v4-flash` was configured as the real default. The previous HAO CLI fail-closed guard was correct, but backend send-time routing still allowed a HAO task to be created against a mock-backed provider.

## Fix

`services/api-server/app/api/agents/agent_local.py` now resolves an effective model for HAO sends before creating the workspace Run and bridge payload:

- If the selected provider is real, use it unchanged.
- If the selected provider would use local mock and a configured real provider exists, fall back to the configured real provider, preferring the default.
- Preserve the original requested provider/model in `model_fallback` metadata on the workspace request, bridge payload, and local message input snapshot.
- Leave non-HAO adapters unchanged.
- If no real provider exists in a test/offline environment, enqueue is not blocked; the HAO CLI mock-response guard still fails closed if execution returns mock content.

One stale local-agent test assertion was also corrected: connection heartbeat returns HTTP 200, matching the route contract and other heartbeat tests.

## Validation

Backend validation:

```text
services/api-server/.venv/bin/python -m pytest \
  services/api-server/tests/test_local_agents.py::test_hao_local_agent_send_falls_back_from_mock_provider_to_real_default \
  services/api-server/tests/test_hao_cli.py::test_hao_headless_rejects_local_bridge_mock_model_response -q
-> 2 passed

services/api-server/.venv/bin/python -m pytest \
  services/api-server/tests/test_local_agents.py \
  services/api-server/tests/test_hao_cli.py -q
-> 145 passed

services/api-server/.venv/bin/python -m ruff check \
  services/api-server/app/api/agents/agent_local.py \
  services/api-server/tests/test_local_agents.py \
  services/api-server/app/cli/hao/main.py \
  services/api-server/tests/test_hao_cli.py
-> passed

services/api-server/.venv/bin/python -m py_compile \
  services/api-server/app/api/agents/agent_local.py \
  services/api-server/tests/test_local_agents.py \
  services/api-server/app/cli/hao/main.py \
  services/api-server/tests/test_hao_cli.py
-> passed

python3 scripts/validate-docs.py
-> passed

git diff --check
-> passed
```

Live verification after restarting the local API and adapter-scoped bridge daemons:

```text
Model settings:
- default: deepseek-flash / deepseek-v4-flash, api_key_configured=true
- openai-compatible / gpt-5.5, api_key_configured=false

HAO binding: aee0f1fb-ce2d-4f8c-a987-41b36bbba47b
Requested model: openai-compatible / gpt-5.5
Bridge task: d611959f-ece4-4a1a-aaf1-381157fe871c
Run: 16496264-1f69-4e34-a6bc-a8e830d9b4c4
Effective model: deepseek-flash / deepseek-v4-flash
ModelCall: 335db88e-0cb9-43b8-a68b-2e5c712428b9 SUCCESS
Assistant reply: HAO_REAL_MODEL_OK
LOCAL_AGENT_MESSAGE_FAILED: 0
```

The bridge task payload recorded:

```json
{
  "requested_model_provider": "openai-compatible",
  "requested_model_name": "gpt-5.5",
  "fallback_model_provider": "deepseek-flash",
  "fallback_model_name": "deepseek-v4-flash",
  "fallback_reason": "selected_provider_would_use_local_mock"
}
```

After 35 seconds, both live local Agent connections still reported `online`:

```text
hao c465ba35-3782-44d9-a66c-0edfdf7933b2 online
codex fd9aed0d-a5ef-458a-92c6-5b8254ef9b14 online
```

## Outcome

The reported HAO mock-provider failure is fixed for the live configured environment. A HAO message can now be sent while the UI/request still names `openai-compatible` / `gpt-5.5`; the backend records the fallback and executes through the configured DeepSeek model instead of handing mock output to the local Agent bridge.
