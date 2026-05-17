# P6 Groundedness Eval And Observability

Category: session-log
Tags: `agent-knowledge-harness`, `eval`, `observability`, `grounding`, `forbidden-leak`, `run-detail`, `task-progress`, `git`

## Summary

Agent Knowledge Harness P6 is completed and pushed to `origin/main` through `83c8eee`.

P6 makes groundedness quality measurable through Eval-owned traces and downstream projections. Eval is the single authority for grounding pass/fail, failure reasons, citation selector checks, fallback expectation/observation, unsupported marker detection, and forbidden evidence leakage. Observability and Run Detail only project Eval-owned results and selectors.

## Commits

```text
beb8cb7 Enforce Eval-owned grounding quality
0bd0c72 Project grounding quality in Observability
c25321c Expose grounding quality in the console
3841bf6 Record P6 grounding handoff
83c8eee Add P6 grounding review report
```

## Delivered

- Added `GroundingTraceV1` normalization in Eval with stable grounding failure fields.
- Added Eval-owned grounding metrics and regression gates:
  - grounding pass rate;
  - citation coverage rate;
  - unsupported marker rate;
  - fallback mismatch rate;
  - forbidden evidence leak rate;
  - required evidence miss rate;
  - newly grounding-failing cases;
  - newly forbidden-leak cases;
  - low-sample caveat.
- Scoped forbidden evidence leakage to Eval's normalized evidence package:
  - retrieval hits;
  - prompt manifest;
  - citations;
  - policy/audit payload;
  - model-call binding metadata.
- Removed raw `ModelCall.request_json` / `response_json` scanning from forbidden leak detection.
- Added response scrubbing so `forbidden_evidence_snippets` does not leak through Eval Case or Eval Run API responses.
- Added Run Detail Eval Case save selector persistence:
  - `retrieval_session_id`;
  - `prompt_manifest_id`;
  - `hit_ids`;
  - `citation_keys`;
  - `citation_hit_ids`;
  - policy decisions;
  - fallback expectation.
- Added `GET /api/observability/grounding-quality` as a read-only projection over Eval-owned traces.
- Added Observability UI for Grounding Quality metrics, table, `eval_run_id` / `dataset_id` prefix filters, failure reason dropdown, leak status, leak sources, and evidence indexes.
- Added Eval Harness UI for grounding metrics, regression deltas, leak indicators, and failure reasons.
- Saved Chinese HTML review report at `docs/reports/p6-groundedness-eval-observability-code-review-2026-05-18.html`.

## Validation

```text
cd services/api-server && uv run pytest tests/test_evals.py tests/test_eval_regression.py tests/test_observability.py -q
36 passed

cd services/api-server && uv run ruff check app/api/evals.py app/api/observability.py tests/test_evals.py tests/test_eval_regression.py tests/test_observability.py
All checks passed

cd apps/agent-console && npm run lint
tsc --noEmit passed

git push origin main
8b211b3..83c8eee  main -> main
```

Manual payload check after the fix created Eval Case `50b5ebac` from Run `72910986-fee1-44bd-b453-4caf62760948` under Dataset `f16631d8-1d20-4a88-a689-59c1134e316c`. Its payload includes `hit_ids`, `citation_keys`, and `citation_hit_ids`, and does not include `forbidden_evidence_snippets`.

## Boundaries

- Eval remains the only layer that evaluates forbidden evidence leakage.
- Observability and Run Detail must not recompute leak status.
- Downstream projections must not render forbidden snippet text.
- Run Detail saved Eval Cases should store objective selectors and indexes, not inferred required/forbidden snippets.

## Next

The next planned lane is [[agent-knowledge-harness-roadmap]] P7: Release And Demo Hardening.

