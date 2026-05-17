# Web Research Fallback Runbook

P3 web research is a source-bound fallback for insufficient local knowledge. It is not a crawler and it does not fetch provider-returned URLs from the Harness backend.

## Configuration

- Default provider is `disabled`.
- First production provider is `tavily`; set `TAVILY_API_KEY` in the API server environment.
- `fake` is allowed only in `APP_ENV=development` or `APP_ENV=test`; production refuses fake fallback.
- User-facing runtime requests cannot override the configured provider.

Policy is stored in `settings.policies.web_research`:

```json
{
  "enabled": true,
  "require_allowlist": true,
  "allow_domains": ["example.com"],
  "deny_domains": [],
  "max_results": 2,
  "timeout_seconds": 8,
  "max_content_bytes": 1200,
  "max_calls_per_run": 1
}
```

Provider-side include/exclude domains are advisory only. Authoritative enforcement happens after results return and before source persistence or citation.

## Evidence Semantics

`verified_grounded=true` is legacy API wording. In P3 it means real-source-bound: a real provider result passed URL policy, was persisted, and has a citation bound to that persisted source. It does not mean the claim is factually verified or supported by the source.

Run Detail should be read as evidence state:

- `fixture_grounded=true`: deterministic fake fixture, rejected by Eval unless explicitly opted in.
- `Source-bound=true`: real provider source was persisted and cited.
- `policy_audits`: historical policy snapshots; do not reinterpret old runs from current settings.

## Live Smoke

CI does not call paid providers. Promotion states must be explicit:

- `P3 implementation complete, live smoke not run`
- `P3 live provider verified`

Run a live probe only as an explicit admin operation using a fixed low-risk query. Do not use customer query text for health checks.
