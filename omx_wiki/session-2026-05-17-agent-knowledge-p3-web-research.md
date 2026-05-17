# Session 2026-05-17 Agent Knowledge P3 Web Research

Category: `session-log`

Tags: `agent-knowledge-harness`, `web-research`, `knowledge-grounding`, `policy-audit`, `task-progress`, `git`

## Summary

P3 real policy-gated web research is implemented, verified, documented, committed, and pushed to `origin/main` through `76f11d5`.

The feature adds a real Tavily-backed web research fallback for cases where local knowledge evidence is insufficient. It is deliberately not a crawler: the Harness backend consumes provider-returned title, URL, snippet, score, and bounded metadata, and does not perform a second-hop HTTP fetch of provider-returned URLs.

## Delivered Scope

- Added Tavily as the first production web research provider via `services/api-server/app/knowledge_web.py`.
- Added `TAVILY_API_KEY` configuration and local-config-only provider health semantics.
- Added `settings.policies.web_research` defaults for enablement, allowlist, denylist, max results, timeout, content bounds, and per-run call limits.
- Added authoritative post-result URL policy in `services/api-server/app/sandbox/policies.py`; provider-side include/exclude domains are advisory only.
- Added URL normalization, credential rejection, private/local/link-local/metadata/multicast/reserved IP blocking, CNAME/DNS classification, and safe URL hash handling.
- Added `web_research_attempts` ledger and Alembic migration `20260517_0016` for per-run call reservation.
- Integrated web fallback into `services/api-server/app/knowledge.py` with policy snapshots, redacted query preview, source persistence, retrieval hits, citations, prompt manifests, events, and Eval behavior.
- Hardened fake web research so fixture evidence remains non-verified and environment-limited.
- Updated Run Detail wording from `Verified grounding` to `Source-bound`, added citation count and provider/request/raw badges.
- Added runbook `docs/runbooks/web-research.md`.
- Added user-facing HTML explanation report at `docs/reports/p3-web-research-implementation-2026-05-17.html`.

## Semantics

`verified_grounded=true` remains a legacy compatibility field. In P3 it means `real_source_bound_not_factual_verification`: a real provider result passed policy, was persisted, and has a citation bound to that persisted source.

It does not mean:

- the webpage content is factually true;
- the answer claim is fully supported by the citation;
- fake fixture evidence can be treated as real web evidence.

## Verification Evidence

Previously completed before commit splitting:

```text
cd services/api-server && uv run pytest tests/test_knowledge_rag.py tests/test_settings.py tests/test_evals.py tests/test_agents.py tests/test_tool_runner.py -q
96 passed

cd services/api-server && uv run ruff check app/api/agents.py app/api/schemas.py app/api/settings.py app/db/models.py app/knowledge.py app/knowledge_web.py app/core/config.py app/sandbox/policies.py tests/test_knowledge_rag.py tests/test_settings.py tests/test_evals.py tests/test_agents.py alembic/versions/20260517_0016_create_web_research_attempts.py
passed

DATABASE_URL=sqlite+pysqlite:////tmp/harness-p3-review-clean.db uv run alembic upgrade head
passed

cd apps/agent-console && npm run lint -- --pretty false
passed

cd apps/agent-console && npm run build
passed

cd apps/agent-console && npm test -- RunDetailPage KnowledgeManagementPanel
passed
```

Live Tavily smoke also passed in the implementation session with:

```text
source_bound=true
fixture=false
raw_content_available=false
usage_credits=1.0
```

## Commit Evidence

P3 commits pushed to `origin/main`:

```text
76f11d5 Document P3 web research handoff
50f6d33 Show source-bound web evidence in Run Detail
03f4814 Bind web research fallback evidence
39ec034 Enforce web research policy gates
7cb3e9a Persist web research attempt reservations
d3e8d24 Add Tavily web research adapter
```

Push evidence:

```text
git push origin main
11a4906..76f11d5  main -> main
```

## Local Service State

During the handoff, services were started on non-default local ports:

```text
Frontend: http://127.0.0.1:15180/
Backend:  http://127.0.0.1:18080
```

The temporary local SQLite database `/tmp/harness-p3-dev.db` was seeded for `dev-org` with web research enabled, `require_allowlist=true`, `allow_domains=["openai.com"]`, and provider `tavily`.

## Manual Frontend Example

Open:

```text
http://127.0.0.1:15180/agents/default/workspace
```

Ask:

```text
请基于 OpenAI 官网资料，说明 OpenAI API 是什么，并给出来源。
```

Expected Run Detail evidence:

- provider shows real web research / Tavily;
- `Source-bound` is true when accepted sources are persisted and cited;
- `Fixture evidence` is false;
- citation count is greater than zero;
- accepted source includes an OpenAI URL;
- policy audit shows allowed/denied decisions and historical snapshots.

## Next Work

P4 should be planned as memory/context router work. If future work wants the Harness backend to fetch webpage bodies itself, that must be a separate crawler/fetcher security design, not an extension hidden inside P3.

## Related Pages

- [[project-handoff-current-state]]
- [[agent-knowledge-harness-roadmap]]
- [[session-2026-05-16-agent-knowledge-p1-grounding-audit]]
