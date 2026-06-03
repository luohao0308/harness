# Session 2026-05-30 Enterprise Sidebar Test Plan

## Summary

Created `.omx/plans/enterprise-left-sidebar-functional-test-plan.md` as the enterprise delivery test plan for Agent Console sidebar coverage.

## Scope Captured

- All 21 left-sidebar entries from `apps/agent-console/src/app/ConsoleShell.tsx`.
- Dynamic workflow routes from `apps/agent-console/src/app/routes.tsx`.
- Cross-feature Harness chains for Models, Workspace, Team Mode, Runs, Subagents, Tools, Knowledge, Observability, Evals, Policies, Data, Users, API Keys, Audit, and Help.
- Subagent invocation from both Agent Workspace and Team Mode, including `team_spawn_agent` assertions.
- Official-source model pricing gates for DeepSeek, current OpenAI Developers pricing rows, Kimi, Moonshot, and Z.AI.

## Evidence

- Plan file: `.omx/plans/enterprise-left-sidebar-functional-test-plan.md`
- Repo anchors:
  - `apps/agent-console/src/app/ConsoleShell.tsx`
  - `apps/agent-console/src/app/routes.tsx`
  - `services/api-server/app/db/models.py`
  - `services/api-server/app/observability/cost_rollup.py`
  - `services/api-server/app/api/evals/graders/cost.py`
  - `services/api-server/app/teams/service.py`
- Official price sources and gates:
  - `https://api-docs.deepseek.com/quick_start/pricing`
  - `https://developers.openai.com/api/docs/pricing`
  - `https://developers.openai.com/api/docs/models/gpt-5.5`
  - `https://platform.kimi.ai/docs/pricing/chat-k26`
  - `https://platform.kimi.ai/docs/pricing/chat-v1`
  - `https://docs.z.ai/guides/overview/pricing`
- DeepSeek, OpenAI, Kimi, Moonshot, and Z.AI values are now captured with source-backed rows in the executed repair.
- The previously listed legacy provider preset was removed from the target surface by user direction and must not be reintroduced as a blocked pricing row.
- OpenAI-compatible pricing is sourced from the official OpenAI Developers pricing/model pages, with source excerpts and hashes recorded in `model_pricing_sources.json`.

## Validation

- `python3 scripts/validate-docs.py`
- `git diff --check`

## Next Work

Implementation should start from the plan's L0 inventory gates and shared enterprise e2e fixture router, then add per-sidebar mocked browser tests before the cross-feature Harness chains.
