# Stage 9: Portfolio Demo + Docs

## Goal

Package the project as a demonstrable AI Harness Engineer portfolio system.

## Input

Implemented stages, eval results, benchmark results, API docs, and runbooks.

## Output

Demo script, README, API docs, Eval report, Benchmark report, GIF/video plan, and capability mapping.

## Modules

Docs, demo, API export, eval report, benchmark report.

## API And Schema Changes

OpenAPI export must match implemented routes in `docs/api` and `apps/web-site/public`.

## Event Types

Demo must include task, plan, tool, policy, replay, eval, and sandbox event types.

## Frontend Display

Console demo starts at Agent Workspace and ends with Eval Harness metrics plus WarmPool Benchmark.

## Tests

Full test suite, frontend build, docs validation, Docker Compose config, OpenAPI export, and browser smoke.

## Acceptance

The project can be explained and shown as Production Agent Harness Platform with reports, SDK example, and capability map.

## Not Doing

Unimplemented features are listed as roadmap, not presented as shipped.

## Vertical Slice Demo

```text
GitHub Issue
-> Agent Chat
-> DAG
-> Tools
-> Guardrail
-> Replay
-> Eval
-> Benchmark
```
