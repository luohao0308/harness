import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EvalRunResults } from "../EvalRunResults";
import type { EvalRun, RegressionDelta } from "../../../tasks/api";

function makeRun(overrides: Partial<EvalRun> = {}): EvalRun {
  return {
    id: "eval-run-1",
    dataset_id: "dataset-1",
    organization_id: "dev-org",
    agent_id: "default",
    status: "COMPLETED",
    metrics_json: {},
    created_by: "dev",
    started_at: "2026-05-27T00:00:00Z",
    completed_at: "2026-05-27T00:01:00Z",
    created_at: "2026-05-27T00:00:00Z",
    results: [],
    ...overrides,
  };
}

describe("EvalRunResults contract surface", () => {
  it("renders contract pass-rate metrics, cost totals, and per-case contract badges", () => {
    const run = makeRun({
      metrics_json: {
        task_success_rate: 0.5,
        tool_contract_pass_rate: 0.5,
        dialogue_contract_pass_rate: 1.0,
        cost_contract_pass_rate: 0.0,
        refusal_contract_pass_rate: 0.5,
        safety_contract_pass_rate: 0.0,
        persona_contract_pass_rate: 1.0,
        specialist_contract_pass_rate: 0.5,
        specialist_contract_configured_count: 2,
        total_specialist_invocations: 3,
        total_specialist_cost_usd: "0.006000",
        specialist_role_distribution: { reviewer: 0.67, researcher: 0.33 },
        overrefusal_rate: 0.5,
        safety_violation_total: 2,
        role_drift_total: 1,
        avg_cost_usd: "0.006000",
        total_cost_usd: "0.012000",
        total_prompt_tokens: 3000,
        total_completion_tokens: 1500,
        cost_per_passed_case_usd: "0.024000",
        tool_contract_configured_count: 2,
        dialogue_contract_configured_count: 1,
        cost_contract_configured_count: 1,
        refusal_contract_configured_count: 2,
        safety_contract_configured_count: 1,
        persona_contract_configured_count: 1,
        tool_contract_failure_breakdown: { missing_required_tool: 1 },
        cost_contract_failure_breakdown: { max_cost_usd: 1 },
        refusal_contract_failure_breakdown: { unexpected_refusal: 1 },
        safety_violation_breakdown: { banned_phrase: 2 },
        persona_contract_failure_breakdown: { role_drift: 1 },
        specialist_contract_failure_breakdown: { missing_specialist: 1 },
      },
      results: [
        {
          id: "result-1",
          eval_run_id: "eval-run-1",
          eval_case_id: "case-1",
          task_id: "task-1",
          status: "FAILED",
          scores_json: {
            task_success: 0,
            tool_contract_score: 0,
            dialogue_contract_score: 1,
            cost_contract_score: 0,
          },
          grader_trace_json: {
            grader: "deterministic_trace_grader_v1",
            passed: false,
            tool_contract: {
              configured: true,
              passed: false,
              failures: ["missing_required_tool:search"],
            },
            dialogue_contract: {
              configured: true,
              passed: true,
              failures: [],
            },
            cost_contract: {
              configured: true,
              passed: false,
              failures: ["max_cost_usd_exceeded:0.020000>0.005"],
              limit_exceeded: ["max_cost_usd"],
              actual_cost_usd: "0.020000",
              prompt_tokens: 1500,
              completion_tokens: 750,
            },
            refusal_contract: {
              configured: true,
              passed: false,
              outcome: "refuse",
              failures: ["unexpected_refusal"],
            },
            safety_contract: {
              configured: true,
              passed: false,
              violation_total: 2,
              failures: ["banned_phrase:私人邮箱"],
            },
            persona_contract: {
              configured: true,
              passed: false,
              role_drift_count: 1,
              failures: ["role_drift:我是通用 AI"],
            },
            specialist_contract: {
              configured: true,
              passed: false,
              total_specialist_invocations: 3,
              failures: ["missing_specialist:researcher"],
            },
          } as unknown as Record<string, unknown>,
          latency_ms: 200,
          cost_usd: "0.020000",
          error_message: "Trace failed",
          created_at: "2026-05-27T00:00:30Z",
        },
      ],
    });

    render(
      <EvalRunResults
        latestRun={run}
        regressionDelta={null}
        activeDatasetId="dataset-1"
        hasBaseline={false}
        onSetBaseline={() => {}}
      />,
    );

    expect(screen.getByText("工具契约通过率")).toBeInTheDocument();
    expect(screen.getByText("对话契约通过率")).toBeInTheDocument();
    expect(screen.getByText("成本契约通过率")).toBeInTheDocument();
    expect(screen.getByText("拒答契约通过率")).toBeInTheDocument();
    expect(screen.getByText("安全契约通过率")).toBeInTheDocument();
    expect(screen.getByText("人设契约通过率")).toBeInTheDocument();
    expect(screen.getByText("专家契约通过率")).toBeInTheDocument();
    expect(screen.getByText("专家调用总数")).toBeInTheDocument();
    expect(screen.getByText("专家累计成本（USD）")).toBeInTheDocument();
    expect(screen.getByText("安全命中总数")).toBeInTheDocument();
    expect(screen.getByText("累计成本（USD）")).toBeInTheDocument();
    expect(screen.getByText("$0.012000")).toBeInTheDocument();
    expect(screen.getByText("工具 失败")).toBeInTheDocument();
    expect(screen.getByText("对话 通过")).toBeInTheDocument();
    expect(screen.getByText("成本 失败")).toBeInTheDocument();
    expect(screen.getByText("拒答 失败")).toBeInTheDocument();
    expect(screen.getByText("安全 失败")).toBeInTheDocument();
    expect(screen.getByText("人设 失败")).toBeInTheDocument();
    expect(screen.getByText("专家 失败")).toBeInTheDocument();
    expect(screen.getByText(/工具契约 \(2\)/)).toBeInTheDocument();
    expect(screen.getByText(/成本契约 \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/拒答契约 \(2\)/)).toBeInTheDocument();
    expect(screen.getByText(/安全命中 \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/人设契约 \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/专家契约 \(2\)/)).toBeInTheDocument();
    expect(screen.getByText("专家角色分布")).toBeInTheDocument();
    expect(screen.getByText(/reviewer 67.0%/)).toBeInTheDocument();
    expect(screen.getByText("missing_specialist")).toBeInTheDocument();
    expect(screen.getByText("missing_required_tool")).toBeInTheDocument();
    expect(screen.getByText("max_cost_usd")).toBeInTheDocument();
    expect(screen.getByText("unexpected_refusal")).toBeInTheDocument();
    expect(screen.getByText("banned_phrase")).toBeInTheDocument();
    expect(screen.getByText("role_drift")).toBeInTheDocument();
  });

  it("renders contract deltas in regression card", () => {
    const run = makeRun({ metrics_json: { task_success_rate: 1 } });
    const delta: RegressionDelta = {
      baseline_run_id: "base-1",
      current_run_id: "eval-run-1",
      task_success_rate_delta: 0.04,
      tool_selection_accuracy_delta: 0,
      avg_latency_ms_delta: 5,
      grounding_pass_rate_delta: 0.07,
      citation_coverage_rate_delta: 0,
      unsupported_marker_rate_delta: 0,
      fallback_mismatch_rate_delta: 0,
      forbidden_evidence_leak_rate_delta: 0,
      required_evidence_miss_rate_delta: 0,
      tool_contract_pass_rate_delta: -0.23,
      dialogue_contract_pass_rate_delta: 0.11,
      cost_contract_pass_rate_delta: 0.17,
      refusal_contract_pass_rate_delta: -0.5,
      safety_contract_pass_rate_delta: -1,
      persona_contract_pass_rate_delta: 0.25,
      specialist_contract_pass_rate_delta: -0.12,
      overrefusal_rate_delta: 0.5,
      safety_violation_total_delta: 2,
      role_drift_total_delta: 1,
      avg_cost_usd_delta: "-0.001500",
      total_cost_usd_delta: "-0.005000",
      total_prompt_tokens_delta: -100,
      total_completion_tokens_delta: -50,
      newly_failing_case_ids: [],
      newly_passing_case_ids: [],
      newly_grounding_failing_case_ids: [],
      newly_forbidden_leak_case_ids: [],
      is_regression: false,
      total_cases: 4,
      passed_cases: 3,
      failed_cases: 1,
      grounding_sample_count: 4,
      low_sample_count: true,
      low_sample_caveat: null,
    };

    render(
      <EvalRunResults
        latestRun={run}
        regressionDelta={delta}
        activeDatasetId="dataset-1"
        hasBaseline={true}
        onSetBaseline={() => {}}
      />,
    );

    expect(screen.getByText("工具契约")).toBeInTheDocument();
    expect(screen.getByText("成本契约")).toBeInTheDocument();
    expect(screen.getByText("拒答契约")).toBeInTheDocument();
    expect(screen.getByText("安全契约")).toBeInTheDocument();
    expect(screen.getByText("人设契约")).toBeInTheDocument();
    expect(screen.getByText("专家契约")).toBeInTheDocument();
    expect(screen.getByText("安全命中")).toBeInTheDocument();
    expect(screen.getByText("平均成本 USD")).toBeInTheDocument();
    expect(screen.getByText("-23.0pp")).toBeInTheDocument();
    expect(screen.getByText("+17.0pp")).toBeInTheDocument();
    expect(screen.getByText("+11.0pp")).toBeInTheDocument();
    expect(screen.getByText("-50.0pp")).toBeInTheDocument();
    expect(screen.getByText("-100.0pp")).toBeInTheDocument();
    expect(screen.getByText("+25.0pp")).toBeInTheDocument();
    expect(screen.getByText("-12.0pp")).toBeInTheDocument();
  });
});
