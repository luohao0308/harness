# Performance Runbook

This runbook defines the P8 scale baseline for private Harness deployments.
Run it against staging or a private validation stack, not against customer
production traffic.

## Targets

| Surface | Target |
|---|---|
| List endpoints | p50 under 100 ms, p99 under 500 ms after cache warmup |
| Agent Run create | p50 under 300 ms for accepted requests |
| Cost rollup | cache hit on repeated identical window and grouping |
| Console bundle | largest JavaScript asset under 512000 bytes, main entry under 250000 bytes |
| Redis outage | read endpoints continue through DB fallback |

## Local Build Gates

```bash
cd apps/agent-console
npm run build
../../scripts/check-bundle-size.sh dist
```

Inspect the main entry asset:

```bash
find dist/assets -name 'index-*.js' -maxdepth 1 -print0 | xargs -0 stat -f '%z %N'
```

## k6 Setup

Install k6 on the load runner, then set the target API and token:

```bash
export HARNESS_LOAD_BASE_URL=http://127.0.0.1:8000
export HARNESS_LOAD_TOKEN=dev-engineer-token
```

Run the baseline:

```bash
k6 run tests/load/baseline.js
```

Run a short spike:

```bash
k6 run tests/load/spike.js
```

Run soak validation:

```bash
k6 run tests/load/soak.js
```

## Reading Results

Use `http_req_duration` for latency and `http_req_failed` for failure rate.
Compare cold and warm list calls to confirm query cache behavior. Confirm
Prometheus counters `query_cache_hit_total` and `query_cache_miss_total` move
for `agents`, `eval_datasets`, `capabilities`, `specialist_stats`, and
`cost_rollup`.

## Cache Checks

1. Call `GET /api/agents?limit=10` twice with the same token.
2. Confirm the second call increments `query_cache_hit_total{entity="agents"}`.
3. Create an Agent.
4. Call `GET /api/agents?limit=10` again.
5. Confirm the response includes the new Agent and increments a miss for the new
   entity version key.

Redis failure must degrade to DB reads, not API failure. Restore Redis before
using the latency numbers as a release baseline.

## Cursor Checks

Use a page size of 10 and follow `next_cursor` until it is null. The merged ids
must have no duplicates and no gaps against the source count. A client must pass
the cursor value unchanged.

## Static Assets

Production Compose serves hashed `/assets/*` files through a dedicated nginx
asset service with this header:

```text
Cache-Control: public, max-age=31536000, immutable
```

Upload to S3 and CloudFront after a clean Console build:

```bash
AWS_REGION=us-east-1 \
S3_BUCKET=my-harness-assets \
CLOUDFRONT_DISTRIBUTION_ID=E123456789 \
scripts/upload-assets-to-s3.sh apps/agent-console/dist
```

The API and Console remain usable without the CDN because the nginx asset
service stays in the production Compose profile.
