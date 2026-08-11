# Prompt Eval Runbook

本文件定义运行时 Agent Prompt 的评测流程。

## Eval Inputs

```text
docs/development/ai/reference/runtime-agent-prompts.md
docs/development/ai/reference/prompt-contracts.yaml
docs/testing/evals/prompt-eval-cases.yaml
```

## Eval Targets

```text
planner
executor
subagent
tool_use
recovery
replay_debugger
```

## Execution Flow

```text
1. Load prompt contract.
2. Load eval cases.
3. For each case, call model through Model Gateway.
4. Validate JSON output.
5. Validate required fields.
6. Validate required events.
7. Validate forbidden actions are absent.
8. Store eval result artifact.
```

## Pass Criteria

```text
json_valid: true
schema_valid: true
required_events_present: true
forbidden_actions_absent: true
```

## Failure Handling

Prompt eval failure blocks release. Prompt contract update requires ADR entry when behavior changes platform execution semantics.

