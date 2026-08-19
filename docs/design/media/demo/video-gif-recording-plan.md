# Demo Video And GIF Recording Plan

## Objective

Record a portfolio demo that proves Forge Harness is a production AI control plane rather than a static chat UI.

## Recording Segments

1. Agent Workspace
   - Open `/agents`.
   - Select default Agent.
   - Show Chat, Plan, Execute, and Auto modes.

2. Agent Run Console
   - Submit a GitHub issue style goal.
   - Show generated Plan DAG.
   - Show Event Timeline receiving live events.

3. Multi-Agent And Subagent
   - Open Run Detail.
   - Show Multi-Agent topology, assignments, handoffs, and reducer output.
   - Show Subagent state and recovery panel.

4. Guardrail And Tool Runtime
   - Open Guardrail panel.
   - Show pending approval, approve or reject action, and tool audit status.
   - Open `/tools` and show builtin plus MCP-shaped tools.

5. Event Sourcing And Replay
   - Enter an event sequence.
   - Run Replay.
   - Show state summary, diagnosis, and failure point area.

6. Eval Harness
   - Save current Run as Eval Case.
   - Run Dataset Eval.
   - Show metrics on Run Detail and `/evals`.

7. Memory / Context / Model Routing
   - Click Context Router refresh.
   - Show model route, memory bundle, compression counts, and new events.

8. WarmPool Benchmark
   - Open `/sandboxes`.
   - Run Benchmark.
   - Show PASS status, warm p95, cold avg, and hit rate.

## Output Files

```text
docs/design/media/demo/assets/agent-run-console.gif
docs/design/media/demo/assets/portfolio-demo.mp4
docs/design/media/demo/assets/warm-pool-benchmark.gif
```

## Acceptance

The final recording shows one continuous Agent Run flowing through planning, execution, trace, guardrail, eval, context routing, replay, and benchmark.
