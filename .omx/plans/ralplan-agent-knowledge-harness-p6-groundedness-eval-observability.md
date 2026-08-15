# RALPLAN: Agent Knowledge Harness P6 Groundedness Eval And Observability

Status: consensus-approved plan

Context snapshot: `.omx/context/agent-knowledge-harness-p6-groundedness-eval-observability-20260517T173624Z.md`

## Requirements Summary

P6 makes hallucination control measurable by extending the existing Eval, Run Detail, and Observability surfaces. It must not rebuild P1-P5 foundations, introduce an LLM judge, or absorb P7 release/demo hardening.

The chosen approach is to keep Eval as the sole quality judgment owner:

- Eval computes pass/fail, grounding quality metrics, `RegressionDelta`, and stable failure reasons.
- Observability only filters and projects Eval-owned trace/metrics through a dedicated grounding-quality endpoint/service.
- Run Detail saves evidence indexes/contracts/selectors only; it does not become a new judgment source.
- P1-P5 immutable evidence records remain source evidence, not mutable P6 output targets.

Primary backend touchpoints:

- `services/api-server/app/api/evals.py`
- `services/api-server/app/api/schemas.py`
- `services/api-server/app/api/observability.py`
- `services/api-server/app/db/models.py`
- `services/api-server/tests/test_evals.py`
- `services/api-server/tests/test_eval_regression.py`
- `services/api-server/tests/test_observability.py`

Primary frontend touchpoints:

- `apps/agent-console/src/features/tasks/api.ts`
- `apps/agent-console/src/features/evals/components/EvalRunResults.tsx`
- `apps/agent-console/src/features/evals/pages/EvalHarnessPage.tsx`
- `apps/agent-console/src/features/runs/pages/RunDetailPage.tsx`
- `apps/agent-console/src/features/runs/pages/__tests__/RunDetailPage.helpers.test.ts`
- `apps/agent-console/src/features/observability/pages/ObservabilityPage.tsx`

## RALPLAN-DR Summary

### Principles

1. P6 extends existing Eval, Run Detail, and Observability surfaces; it does not introduce a second quality judgment system.
2. Eval owns `GroundingTraceV1`, trace serialization/normalization, quality metrics, pass/fail, and regression gates.
3. Observability is read-only projection/filtering over Eval-owned fields; it must not recompute grounding quality or failure reasons.
4. New trace and metric fields are versioned, backward compatible, and covered by contract tests.
5. Run Detail stores drilldown evidence indexes/contracts/selectors only; Eval trace derives every pass/fail reason.

### Decision Drivers

1. **Verifiability:** every grounding/citation/fallback/unsupported-claim result must be reproducible from persisted P1-P5 evidence plus Eval contract fields.
2. **Scope control:** P6 must deliver deterministic quality measurement without pulling in normalized claim warehouses, LLM judges, seeded demos, or private deployment hardening.
3. **Product usefulness:** Eval Harness shows quality regression; Observability filters and aggregates quality state; Run Detail remains the per-run evidence drilldown.

### Viable Options

**Option A: versioned JSON trace + Eval metrics, with Observability projection. Chosen.**

- Pros: minimal schema disturbance, fits current `EvalResult.grader_trace_json` and `EvalRun.metrics_json`, reuses existing Eval regression path, fastest testable P6 slice.
- Cons: JSON can drift without typed normalizer/serializer; claim-level analytics remain limited.
- Failure modes: frontend/backend key drift, untyped defaults, projection queries growing awkward.
- Mitigation: `GroundingTraceV1`, one Eval-owned normalizer/serializer, stable default keys, contract tests, deferred normalized table ADR.

**Option B: normalized quality snapshot / claim-level tables. Rejected for P6.**

- Pros: stronger indexing, BI, per-claim trend analysis, clean future LLM-judge integration.
- Cons: migration/backfill cost, dual-write consistency risk, premature claim schema before deterministic semantics are proven.
- Failure modes: table and trace disagreement; scope expands into P7/P8 analytics.
- Rejection rationale: good follow-up if JSON projection proves insufficient; too broad for first P6 slice.

**Option C: LLM judge / external evaluator. Rejected for P6.**

- Pros: can evaluate semantic claim support beyond deterministic snippets and citation keys.
- Cons: non-determinism, cost, calibration burden, external dependency, unstable regression gates.
- Failure modes: judge drift, false regressions, provider outages, blurred Eval/Observability ownership.
- Rejection rationale: P6 needs deterministic regression semantics first.

**Option D: merge P6 and P7. Rejected.**

- Pros: one larger dashboard/demo/release push.
- Cons: delayed P6 value, oversized PR, harder review, seeded demo and Docker handoff concerns mixed into quality contract work.
- Failure modes: scope creep, weak verification, unclear ownership.
- Rejection rationale: P7 remains release/demo hardening.

## Acceptance Criteria

### Trace Contract

Eval defines and owns a `GroundingTraceV1` contract plus a single normalizer/serializer path. New grounding traces must include:

- `grader_trace_schema_version: 1`
- `grader: string`
- `passed: boolean`
- `grounding_failures: string[]`
- `retrieval_session_id: string | null`
- `prompt_manifest_id: string | null`
- `policy_audit_ids: string[]`
- `hit_ids: string[]`
- `citation_keys: string[]`
- `citation_hit_ids: string[]`
- `required_evidence_snippets: string[]`
- `forbidden_evidence_snippets: string[]`
- `forbidden_evidence_leaked: boolean`
- `forbidden_leak_sources: string[]`
- `fallback_expected: boolean`
- `fallback_observed: boolean`
- `fallback_reason: string | null`
- `unsupported_markers: string[]`
- `claim_checks: GroundingClaimCheckV1[]`

`GroundingClaimCheckV1` item schema is reserved but explicit:

- `claim_id: string`
- `claim_text: string`
- `required_citation_keys: string[]`
- `matched_citation_keys: string[]`
- `unsupported: boolean`
- `grounded: boolean`
- `failure_reasons: string[]`
- `evidence_indexes: string[]`

P6 may emit `claim_checks: []`; it must not implement semantic claim-level judging.

Legacy trace compatibility:

- Missing `grader_trace_schema_version` is normalized as v0.
- Missing arrays default to `[]`.
- Missing booleans default to `false`.
- Missing nullable IDs/reasons default to `null`.
- Existing `grader`, `passed`, and `grounding_failures` consumers keep working.

### Eval Contract

`expected_json.grounding_contract` supports:

- `citation_keys`
- `hit_ids`
- `required_evidence_snippets`
- `forbidden_evidence_snippets`
- `fallback_expected`
- `unsupported_markers`
- existing selectors such as `retrieval_session_id`, `prompt_manifest_id`, `require_grounded`, `require_prompt_manifest`, `require_insufficient`, `allow_fixture_grounding`, and policy decisions.

Stable failure reason enums include:

- `missing_required_evidence`
- `forbidden_evidence_leaked`
- `fallback_expected_but_not_observed`
- `fallback_observed_but_not_expected`
- `unsupported_marker_present`
- `citation_hit_mismatch`
- existing grounding failures already emitted by the current grader.

All deterministic matching uses one fixed rule set:

- String comparisons trim leading/trailing whitespace and normalize line endings to `\n`.
- No lowercasing is applied; matching is case-sensitive.
- `citation_keys` and `hit_ids` use exact string matches after trimming.
- `required_evidence_snippets` and `forbidden_evidence_snippets` use case-sensitive substring matches against normalized evidence text fields.
- `fallback_observed` is derived only by Eval from deterministic grounding trace/evidence fields, not by frontend or Observability inference.

Forbidden evidence leakage is evaluated only by Eval against one normalized evidence input package:

- retrieval hits
- prompt manifest evidence
- citations
- policy/audit payloads
- model-call binding metadata only: `prompt_manifest_id`, `context_manifest_id`, `grounding_correlation_id`, request hash fields, and message-hash fields

Eval outputs the canonical leak result through `forbidden_evidence_leaked: boolean`, `forbidden_leak_sources: string[]`, and `grounding_failures[]`. Forbidden evidence leakage is absolute zero tolerance: any Eval-detected leak fails the case and marks the run as a regression. Downstream projections must not recompute leakage and must avoid rendering forbidden snippets directly.

Eval must not scan raw `ModelCall.request_json` or `ModelCall.response_json` for forbidden snippets. Model-call binding metadata is used to prove the evaluated prompt/context evidence is bound to the model attempt; leak text checks stay within the normalized retrieval/prompt/citation/policy evidence inputs above.

### Metrics And Regression

`EvalRun.metrics_json` adds:

- `grounding_pass_rate`
- `citation_coverage_rate`
- `unsupported_marker_rate`
- `fallback_mismatch_rate`
- `forbidden_evidence_leak_rate`
- `required_evidence_miss_rate`
- `grounding_failure_total`

`RegressionDelta` adds:

- `grounding_pass_rate_delta`
- `citation_coverage_rate_delta`
- `unsupported_marker_rate_delta`
- `fallback_mismatch_rate_delta`
- `forbidden_evidence_leak_rate_delta`
- `required_evidence_miss_rate_delta`
- `newly_grounding_failing_case_ids`
- `newly_forbidden_leak_case_ids`
- grounding sample counts or equivalent low-sample caveat fields.

Initial gate constants:

- Existing `task_success_rate_delta < -0.10` remains a regression.
- `grounding_pass_rate_delta < -0.05` is a regression.
- `forbidden_evidence_leak_rate > 0` is a regression.
- Any newly forbidden-leak case is a regression.
- `unsupported_marker_rate_delta > 0.05` is a regression.
- `fallback_mismatch_rate_delta > 0.05` is a regression.

These thresholds are initial constants. For low case counts, API/UI must expose sample count or a low-confidence caveat instead of presenting the delta as a stable trend.

### Observability Contract

Add a dedicated read-only projection surface, for example `GET /api/observability/grounding-quality`.

It may filter/project only Eval-owned traces and metrics, with org-scoped access controls. Suggested filters:

- dataset
- eval run ID
- agent ID
- time range
- failure type
- grounding pass/fail
- forbidden leak presence
- fallback mismatch
- unsupported marker presence

It must not recompute grounding quality, unsupported claims, pass/fail reasons, gate status, citation coverage, or fallback correctness from logs/traces/raw evidence.

For forbidden evidence leakage, Observability may display only Eval-owned fields such as `forbidden_evidence_leaked`, `forbidden_leak_sources`, counts, and redacted/hash-style identifiers. It must not scan original evidence or render forbidden snippet text.

### Run Detail Contract

Run Detail save flow stores evidence indexes/contracts/selectors only:

- citation keys
- retrieval hit IDs
- fallback expectation
- existing exact retrieval and prompt-manifest selectors

Run Detail may auto-populate only objective evidence indexes/selectors already present in the run evidence, such as citation keys, retrieval hit IDs, fallback expectation, retrieval session ID, prompt manifest ID, and policy decisions. It must not infer `required_evidence_snippets`, `forbidden_evidence_snippets`, or `unsupported_markers` from retrieved text, citations, model calls, or rendered output.

`required_evidence_snippets`, `forbidden_evidence_snippets`, and `unsupported_markers` are explicit Eval contract inputs. They may come from a deliberate Eval Case editor/manual API payload, but if no explicit user-authored contract value exists, Run Detail leaves them absent. Downstream UI must prefer redacted/count/hash display for any explicit forbidden snippet contract value and avoid rendering forbidden snippet text directly.

Run Detail may display failure reasons only when they come from Eval trace/result data. It must not create independent pass/fail logic.

For forbidden evidence leakage, Run Detail may show Eval-owned leak status and `forbidden_leak_sources`; it must not scan evidence or independently decide whether a leak occurred.

### Frontend Contract

Eval Harness displays:

- new grounding metric cards
- grounding regression deltas and gate status
- sample-count/low-confidence caveat for small datasets
- per-case failure reasons from Eval trace

Observability displays:

- grounding-quality summary cards
- filters backed by the dedicated projection endpoint
- links to Run Detail / Eval Run detail
- no client-side recomputation of quality judgment

Frontend types in `apps/agent-console/src/features/tasks/api.ts` must match backend schemas.

## Implementation Phases

Keep P6 reviewable by landing the work in three ordered phases. Do not start downstream projection/UI work until the upstream Eval contract and focused backend tests are passing.

### Phase 1: Backend Eval Contract And Metrics

1. **Add Eval-owned trace contract helpers.**
   - In `services/api-server/app/api/evals.py`, introduce `GroundingTraceV1`-shaped helpers such as `_grounding_trace_v1(...)`, `_normalize_grader_trace(...)`, and one serialization path.
   - Normalize v0/missing-version traces into stable v1 defaults.
   - Ensure `_grade_case()` and `_grade_grounding_contract()` use the normalizer before aggregating metrics.

2. **Extend grounding contract grading.**
   - In `services/api-server/app/api/evals.py`, read new `grounding_contract` fields: `citation_keys`, `hit_ids`, `required_evidence_snippets`, `forbidden_evidence_snippets`, `fallback_expected`, and `unsupported_markers`.
   - Emit stable failure reasons.
   - Build one normalized Eval evidence input package from retrieval hits, prompt manifest evidence, citations, policy/audit payloads, and model-call binding metadata.
   - Treat model-call binding metadata as IDs/hashes/refs only; do not scan raw `ModelCall.request_json` or `ModelCall.response_json` for leak text.
   - Enforce absolute zero tolerance for forbidden evidence leakage inside Eval only, and output `forbidden_evidence_leaked`, `forbidden_leak_sources`, and `grounding_failures[]`.
   - Apply the fixed matching rules for trim, case-sensitive exact matches, and case-sensitive snippet substring checks.
   - Keep all checks deterministic; no LLM judge or external evaluator.

3. **Extend metric aggregation and regression deltas.**
   - Update `_aggregate_metrics()` in `services/api-server/app/api/evals.py`.
   - Update `RegressionDelta` in `services/api-server/app/api/schemas.py`.
   - Update `get_regression_delta()` in `services/api-server/app/api/evals.py` with initial grounding gate constants and low-sample caveat output.
   - Preserve existing task/tool/latency regression fields.

Phase 1 stop condition: backend focused Eval/regression tests pass for trace schema, matching rules, forbidden leak zero tolerance, fallback observation semantics, and metrics/regression gates.

### Phase 2: Observability Read-Only Projection

4. **Add Observability read-only projection.**
   - In `services/api-server/app/api/observability.py`, add a dedicated grounding-quality projection endpoint or helper service.
   - Source data from org-scoped `EvalRun.metrics_json` and normalized `EvalResult.grader_trace_json`.
   - Do not inspect logs/traces/raw events to derive judgment.
   - For forbidden leaks, project only Eval-owned `forbidden_evidence_leaked`, `forbidden_leak_sources`, counts, and redacted/hash-style identifiers.

Phase 2 stop condition: Observability backend tests prove org-scoped projection, no cross-org leakage, and no recomputation from logs/traces/raw evidence.

### Phase 3: Frontend Display And Handoff

5. **Update frontend API types.**
   - Update `apps/agent-console/src/features/tasks/api.ts` for new metrics, regression deltas, trace fields, and observability projection response.
   - Ensure missing fields in old runs render as neutral/default, not broken UI.

6. **Update Eval UI.**
   - In `apps/agent-console/src/features/evals/components/EvalRunResults.tsx`, add metric cards, grounding deltas, gate status, sample-count caveat, and per-case failure reason display.
   - Keep `EvalHarnessPage.tsx` layout focused; do not turn it into release/demo dashboard.

7. **Update Run Detail evidence contract save/display.**
   - In `apps/agent-console/src/features/runs/pages/RunDetailPage.tsx`, extend Save Eval Case payload with the new evidence-index contract fields.
   - Auto-populate only objective evidence indexes/selectors already present in the run evidence: citation keys, retrieval hit IDs, fallback expectation, retrieval session ID, prompt manifest ID, and policy decisions.
   - Do not auto-populate or infer `required_evidence_snippets`, `forbidden_evidence_snippets`, or `unsupported_markers`; those remain explicit Eval contract inputs from a deliberate editor/manual payload.
   - Display saved contract/drilldown fields only as evidence selectors.
   - Display pass/fail reasons only from Eval result trace when available.
   - For forbidden snippets, do not render raw snippet text in downstream projection; render redacted/count/hash-style evidence and Eval-owned leak source labels.

8. **Update Observability UI.**
   - In `apps/agent-console/src/features/observability/pages/ObservabilityPage.tsx`, add grounding-quality projection cards/filters/list.
   - Link records to Run Detail/Eval Run details.
   - Avoid client-side recomputation of quality status.
   - For forbidden leaks, display only Eval-owned leak status/sources and redacted/hash-style identifiers.

9. **Refresh API/docs/progress only after implementation is verified.**
   - Update OpenAPI artifacts if this repo’s existing workflow requires it.
   - Update `docs/ai/task-progress.yaml`, `docs/task-progress.md`, and wiki/session notes at handoff.
   - Keep seeded demo data, broad release smoke, Docker handoff hardening, and demo polish in P7.

Phase 3 stop condition: frontend focused tests, lint/build, and final docs/progress validation pass.

## Verification Plan

Backend focused tests:

- `cd services/api-server && uv run pytest tests/test_evals.py tests/test_eval_regression.py tests/test_observability.py -q`
- Include assertions for:
  - `GroundingTraceV1` schema version and stable keys.
  - v0/missing-version normalization defaults.
  - `claim_checks` item schema/default `[]`.
  - citation key and hit ID matching.
  - fixed matching semantics: trim, case-sensitive exact ID/key matching, and case-sensitive snippet substring matching.
  - required evidence miss.
  - forbidden evidence absolute leak failure computed only by Eval from the normalized evidence input package.
  - model-call binding metadata contributes only IDs/hashes/refs; raw `ModelCall.request_json` / `response_json` is not scanned for forbidden text.
  - `forbidden_evidence_leaked`, `forbidden_leak_sources`, and `grounding_failures[]` output.
  - fallback expected/observed mismatch, with `fallback_observed` derived only from Eval-owned deterministic evidence fields.
  - unsupported marker detection.
  - grounding metric aggregation.
  - `RegressionDelta` grounding deltas and gate status.
  - low sample count/caveat output.
  - Observability org-scoped projection, no cross-org leakage, and no recomputation from logs/traces/raw evidence.

Frontend focused tests:

- `cd apps/agent-console && npm test -- EvalRunResults RunDetailPage ObservabilityPage`
- Include assertions for:
  - grounding metric and regression rendering.
  - failure reason display from Eval trace.
  - Run Detail save/load of objective evidence indexes/contracts.
  - Run Detail does not infer required snippets, forbidden snippets, or unsupported markers from run evidence.
  - forbidden leak display uses Eval-owned leak status/sources and does not render forbidden snippet text directly.
  - Observability projection rendering and filters.
  - old/missing fields render safely.

General gates:

- `cd services/api-server && uv run ruff check app tests`
- `cd services/api-server && uv run pytest -q` if shared schemas/models or regression behavior are broadly touched.
- `cd apps/agent-console && npm run lint`
- `cd apps/agent-console && npm run build`
- `python3 scripts/validate-docs.py` after docs/progress changes.
- Alembic upgrade only if implementation unexpectedly adds schema changes; Option A should not require a P6 migration.

## Risks And Mitigations

- **Risk: JSON trace drift.** Mitigate with `GroundingTraceV1`, one normalizer/serializer, stable defaults, and contract tests.
- **Risk: Observability becomes a second judge.** Mitigate with endpoint contract and tests proving projection comes from Eval trace/metrics only.
- **Risk: forbidden evidence leakage judgment spreads across layers.** Mitigate by making Eval the only leak scanner over a normalized evidence input package; downstream layers only project Eval-owned leak status/sources and avoid rendering forbidden snippet text directly.
- **Risk: forbidden evidence leakage handled as a soft metric.** Mitigate with Eval-owned absolute zero-tolerance failure and regression gate.
- **Risk: small datasets produce noisy deltas.** Mitigate with sample counts and low-confidence caveat fields in API/UI.
- **Risk: P6 expands into claim-level analytics.** Mitigate by defining `claim_checks[]` item schema but emitting `[]` until a later ADR authorizes claim-level judging/tables.
- **Risk: P6 absorbs P7 release/demo work.** Mitigate by leaving seeded demos, broad release smoke, Docker handoff hardening, and demo polish in P7.

## ADR

**Decision**

Implement P6 as deterministic grounding-quality Eval plus read-only Observability projection. Use versioned `EvalResult.grader_trace_json` and `EvalRun.metrics_json` first, with `GroundingTraceV1` owned by Eval. Do not add normalized claim tables or LLM judges in P6.

**Drivers**

- Current Eval already owns deterministic grading, trace output, aggregate metrics, and regression deltas.
- P1-P5 already persist the evidence needed for deterministic checks.
- P6 must produce measurable groundedness without destabilizing audit/storage boundaries.
- Observability should make quality state visible, not create an alternate quality engine.

**Alternatives Considered**

- Normalized quality/claim tables.
- LLM judge or external evaluator.
- Merging P6 with P7 release/demo hardening.

**Why Chosen**

Option A delivers the smallest auditable vertical slice: versioned trace contract, deterministic failure reasons, grounding metrics, regression gates, Observability projection, and UI drilldown. It keeps the work testable and bounded.

**Consequences**

- JSON contracts must be treated as real API contracts, with normalizers and tests.
- Longitudinal claim analytics may need a future normalized table.
- Semantic unsupported-claim judging remains out of scope until a later ADR.
- P7 remains responsible for seeded demos, broad release smoke, Docker handoff hardening, and demo polish.

**Follow-ups**

- Design normalized claim-level storage if projection queries or analytics outgrow v1 trace.
- Define non-empty `claim_checks[]` semantics in a later P6.x/P7 ADR.
- Evaluate deterministic + LLM judge hybrid only after deterministic gates are stable.

## Execution Handoff

### Available Agent Types Roster

- `explore`: repo-local symbol/file/test-path mapping.
- `executor`: backend/frontend implementation.
- `test-engineer`: focused regression and UI tests.
- `verifier`: final evidence, gate checks, and contract validation.
- `code-reviewer`: risk review after implementation.
- `architect`: boundary decisions if trace schema, ownership, or storage concerns reappear.
- `debugger`: root-cause support if tests expose regressions.
- `writer`: docs/progress/wiki handoff after verified implementation.

### Ralph Guidance

Use `$ralph` for a single-owner implementation when sequential convergence is preferred.

Suggested staffing:

- `executor` with medium reasoning for backend contract and frontend surfaces.
- `test-engineer` with medium reasoning for focused test coverage.
- `verifier` with high reasoning for final gate evidence.
- `code-reviewer` with high reasoning before handoff.

Launch hint:

```text
$ralph "Implement .omx/plans/ralplan-agent-knowledge-harness-p6-groundedness-eval-observability.md. Preserve P6 boundaries: Eval owns GroundingTraceV1 and quality gates; Observability is read-only projection; Run Detail stores evidence contracts only; no LLM judge, normalized claim table, or P7 demo hardening."
```

### Team Guidance

Use `$team` if parallel delivery is worth the coordination overhead.

Suggested lanes:

- Backend Eval/Regression lane: `executor`, medium reasoning.
- Observability API/UI lane: `executor`, medium reasoning.
- Frontend Eval/Run Detail lane: `executor`, medium reasoning.
- Test/Verifier lane: `test-engineer`, medium reasoning plus `verifier`, high reasoning.
- Final review lane: `code-reviewer`, high reasoning.

Launch hint:

```text
$team "Implement P6 from .omx/plans/ralplan-agent-knowledge-harness-p6-groundedness-eval-observability.md with separate lanes for Eval contract/regression, Observability projection, frontend drilldown, and focused tests. Preserve Eval ownership and P7 boundary."
```

Team verification path:

1. Backend Eval lane proves trace contract, matching semantics, metric aggregation, regression gates, and Eval-only forbidden leak judgment with targeted tests.
2. Observability lane proves read-only projection after Backend Eval is green.
3. Frontend lane proves metric/failure rendering, Run Detail save contract, forbidden-snippet redaction, and Observability filters after projection API is stable.
4. Verifier checks `GroundingTraceV1`, v0 normalization, forbidden-leak zero tolerance, org scope, no Observability/Run Detail recomputation, and phase stop conditions.
5. Code-reviewer checks boundary risks and missing tests before shutdown.

### Goal-Mode Follow-Up Suggestions

- `$ultragoal` is the default goal-mode follow-up if P6 should be tracked as durable phased implementation work.
- `$ralph` is the better direct execution path for single-owner completion pressure.
- `$team` is the better direct execution path if backend/frontend/tests should proceed in parallel.
- `$autoresearch-goal` is not the default; P6 is implementation, not external research.
- `$performance-goal` is not the default; use it only if query/dashboard latency becomes the central objective.

## Consensus Changelog

- Planner recommended Option A: deterministic Eval extension plus Observability projection.
- Architect approved the direction but required stricter Eval/Observability ownership and versioned trace contracts.
- Critic required field-level acceptance criteria, Run Detail save contract, grounding regression semantics, focused tests, and fair alternatives.
- Revised plan added `GroundingTraceV1`, `claim_checks[]` item schema, zero-tolerance forbidden leakage, initial gate constants with low-sample caveats, and explicit P7 boundary.
- Final Critic verdict: APPROVE, conditional on preserving those constraints.
- User follow-up tightened the core boundary: forbidden evidence leakage is judged only by Eval over a normalized evidence input package; Observability and Run Detail only project Eval-owned leak status/sources and must not scan evidence or render forbidden snippets directly. Implementation sequencing was narrowed to Backend Eval contract and metrics, then Observability projection, then frontend display.
