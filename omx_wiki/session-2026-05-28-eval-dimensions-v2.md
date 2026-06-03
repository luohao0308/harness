# Eval Dimensions v2 Refusal Safety Persona

Category: `session-log`

Tags: `agent-knowledge-harness`, `eval`, `refusal`, `safety`, `persona`, `regression`, `task-progress`

## Summary

Agent Knowledge Harness Eval Dimensions v2 is implemented locally on branch `p7-release-demo-hardening`.

This slice extends the P8.1 Eval JSON contract pattern with deterministic model-behavior graders for:

- `refusal_contract`: refusal calibration, expected answer/refusal/partial refusal, reason requirements, minimum length, and overrefusal markers.
- `safety_contract`: banned phrases and bounded regex patterns over assistant content plus optional tool arguments.
- `persona_contract`: role mention, role drift, tone markers, first-person drift, and optional out-of-scope response markers.

No new tables or migrations were added. All contract inputs remain in `EvalCase.expected_json`; scores and audit details remain in `EvalResult.scores_json` and `EvalResult.grader_trace_json`.

## Delivered

- Added three deterministic graders in `services/api-server/app/api/evals.py`.
- Wired refusal/safety/persona traces into `_grade_case`, pass/fail scoring, failure messages, and Eval Result trace output.
- Added aggregate metrics for new contract pass rates, refusal outcome distribution, overrefusal rate, safety violation totals/breakdown, and role drift total.
- Extended regression delta and gate logic with refusal/safety/persona pass-rate deltas, overrefusal delta, safety violation total delta, and role drift total delta.
- Added backend tests for refusal pass/fail, answer-vs-refusal calibration, overrefusal, safety phrase/regex/tool-argument scans, invalid regex handling, persona drift/tone/scope checks, and new regression fields.
- Extended Eval UI types, metric labels, delta cards, per-case contract badges, breakdown rows, and JSON presets for the three new contracts.

## Validation

```text
cd services/api-server && uv run pytest tests/test_evals.py::test_eval_run_grades_refusal_contract_outcomes tests/test_evals.py::test_eval_run_grades_safety_contract_content_patterns_and_tool_arguments tests/test_evals.py::test_eval_run_grades_persona_contract_role_tone_and_scope tests/test_eval_regression.py::TestRegressionDelta::test_behavior_contract_regression_fields_and_gate -q
4 passed

cd services/api-server && uv run pytest tests/test_evals.py tests/test_eval_regression.py -q
26 passed

cd services/api-server && uv run ruff check app tests
All checks passed

cd apps/agent-console && PATH="$HOME/.nvm/versions/node/v24.15.0/bin:$PATH" npm test -- EvalRunResults.contracts.test.tsx --run
1 file passed, 2 tests passed

cd apps/agent-console && PATH="$HOME/.nvm/versions/node/v24.15.0/bin:$PATH" npm run lint
passed

cd apps/agent-console && PATH="$HOME/.nvm/versions/node/v24.15.0/bin:$PATH" npm run build
passed, with existing Vite chunk-size warning

python3 scripts/validate-docs.py
docs validation passed

git diff --check
passed
```

## Notes

- Frontend validation used local nvm Node `v24.15.0` because the default shell Node was `v16.17.0`, below the console package `engines.node >=20` requirement and unable to start Vite/Vitest.
- Safety regex handling uses a 256-character pattern length guard plus compile-error trace failures. This keeps the v2 grader deterministic and dependency-free.
- `banned_categories` are recorded as metadata only in this slice; no classifier or LLM judge was added.

## Next

- Optional browser smoke for Eval preset creation can be added later if the product wants end-to-end coverage of the JSON preset buttons.
- A future classifier-backed safety category grader should remain a separate design because this slice intentionally stays marker/regex-only.
