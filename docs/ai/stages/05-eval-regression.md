# Stage 5: Eval And Regression Harness

## Goal

Make Eval Harness a first-class differentiator, not an afterthought.

## Input

- Agent Run trace.
- Dataset and cases.
- Grader configuration.
- Agent version metadata.

## Output

- Runs can be saved as Eval Cases.
- Dataset Eval Run grades cases.
- Regression metrics and review state are visible.

## Modules

- Eval Dataset
- Eval Case
- Eval Run
- Trace Grader
- Regression Gate
- Human Review entry

## API And Schema Changes

- Keep dataset, case, and eval run APIs.
- Add Agent Run semantic wrappers when migration reaches Eval routes.
- Eval metrics include task success rate, tool selection accuracy, policy violation rate, latency, cost, retry rate, and human escalation rate.

## Event Types

- `EVAL_CASE_CREATED`
- `EVAL_RUN_STARTED`
- `EVAL_CASE_GRADED`
- `EVAL_RUN_COMPLETED`
- `EVAL_RUN_FAILED`

## Frontend Display

- `/evals` shows datasets, cases, eval runs, metrics, and grader traces.
- Run Detail can save current Run as Eval Case.
- A/B and human review entries are disabled until API-backed.

## Tests

- Backend eval tests cover dataset, case from Run, eval run, grader result.
- Frontend build covers `/evals` and Run Detail eval controls.

## Acceptance

- User creates dataset.
- User saves Run as case.
- User runs eval and sees metrics.
- Regression state comes from API.

## Not Doing

- No external labeling vendor integration.
- No production traffic sampler until API exists.
- No fake A/B results.

## Vertical Slice Demo

```text
Open Run Detail
-> save Run as Eval Case
-> open /evals
-> run Dataset Eval
-> inspect metrics and grader trace
```
