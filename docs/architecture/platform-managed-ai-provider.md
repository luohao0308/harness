# Platform-Managed AI Provider

## Status

- Status: active implementation contract
- Provider: `chybenzun-openai-compatible`
- Base URL: `https://chybenzun.top/v1`
- Protocol: `chat_completions`
- Default model: `deepseek-v4-flash`

## Runtime Contract

Harness exposes a server-owned OpenAI-compatible provider to Agent, Team,
Model Settings, and onboarding flows. The backend owns the provider URL,
credential, default model, and model allowlist. Browser code receives only
provider and model metadata.

The supported model allowlist is configured by `AI_PROVIDER_MODELS`. The
default `AI_PROVIDER_MODEL` must be present in that list, and Agent and Team
runtime selection rejects platform models outside it.

## Configuration

| Variable | Purpose |
| --- | --- |
| `AI_PROVIDER_PROTOCOL` | Must be `chat_completions`. |
| `AI_PROVIDER_BASE_URL` | HTTPS upstream URL, or HTTP loopback for local development. |
| `AI_PROVIDER_MODEL` | Default platform model. |
| `AI_PROVIDER_MODELS` | Comma-separated model allowlist. |
| `AI_PROVIDER_NAME` | Stable provider identifier. |
| `AI_PROVIDER_API_KEY` | Server-only upstream credential. Required in production. |

`AI_PROVIDER_API_KEY` must not appear in Vite, browser, or public website
environment templates. Compose and Helm inject it only into backend processes
that call the provider.

## Gateway Compatibility

The gateway sends a stable `Harness-AI-Gateway/1.0` user agent and supports
ordinary JSON completions, SSE streaming, and the provider's observed
concatenated `chat.completion.chunk` JSON response. Concatenated responses are
accepted only when chunks belong to one response, contain one terminal chunk,
have no data after termination, and report structurally valid usage.

Optional `max_output_tokens` and `temperature` values are validated before
they reach the upstream request. Temperature must be finite and within
`0..2`; booleans and non-numeric values are rejected.

## Verification

- Backend regression: `1418 passed`.
- Gateway regression: `52 passed`.
- Agent regression: `75 passed`.
- Frontend lint and production build passed.
- Team Vitest: `25 passed`.
- Team Playwright: `3 passed`.
- Live upstream model listing, complete, and stream probes passed without
  logging credentials or response bodies.
