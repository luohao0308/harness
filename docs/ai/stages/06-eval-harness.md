# Stage 6: Eval Harness

## Goal

Ship Dataset, Eval Case, Eval Run, Eval Result, Trace Grader, regression metrics, and console display.

## Input

Saved Agent runs and manually authored eval inputs.

## Output

Eval dataset, case, run, result, metrics, grader trace, and audit events.

## Modules

Eval API, Eval data models, Trace Grader, Console Eval page, Admin Audit.

## API And Schema Changes

Use `/api/evals/datasets`, `/api/evals/datasets/{dataset_id}/cases/from-run/{task_id}`, `/api/evals/datasets/{dataset_id}/runs`, `/api/evals/runs`.

## Event Types

`EVAL_DATASET_CREATED`, `EVAL_CASE_CREATED`, `EVAL_RUN_STARTED`, `EVAL_CASE_GRADED`, `EVAL_RUN_COMPLETED`, `EVAL_RUN_FAILED`.

## Frontend Display

Eval Harness page shows datasets, case queue, save-from-run control, eval run button, metrics, result rows, and grader trace names.

## Tests

Backend tests create a completed run, save it as an eval case, run the grader, verify metrics, and verify audit events.

## Acceptance

A user can turn any run into a regression case and run a measurable eval from the console.

## Not Doing

LLM-as-judge and human review queue are later expansions.

## Vertical Slice Demo

```text
Run a task
-> open /evals
-> create Dataset
-> paste Run ID
-> save Case
-> Run Eval
-> inspect metrics
```
