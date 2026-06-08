import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EvalHarnessPage } from "../EvalHarnessPage";

const apiBaseUrl = "http://127.0.0.1:8000";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function requestPath(input: RequestInfo | URL) {
  const url = String(input);
  return new URL(url.startsWith("http") ? url : `${apiBaseUrl}${url}`).pathname;
}

function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/evals"]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/evals" element={<EvalHarnessPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function evalRun(id: string, capability: Record<string, unknown> = {}, datasetId = "dataset-1") {
  return {
    id,
    dataset_id: datasetId,
    organization_id: "dev-org",
    agent_id: "default",
    status: "COMPLETED",
    metrics_json: { case_total: 2, passed_total: id.startsWith("native") ? 2 : 1 },
    capability_snapshot_json: capability,
    created_by: "dev-engineer",
    started_at: "2026-06-02T00:00:00Z",
    completed_at: "2026-06-02T00:01:00Z",
    created_at: "2026-06-02T00:00:00Z",
    results: [],
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("EvalHarnessPage LangGraph contrast experiments", () => {
  it("creates and displays a LangGraph-vs-native Eval experiment over normal EvalRun rows", async () => {
    const user = userEvent.setup();
    let createdExperiment = false;
    const experiment = {
      id: "experiment-1",
      dataset_id: "dataset-1",
      organization_id: "dev-org",
      name: "LangGraph vs Native Harness",
      description: "Console-created contrast experiment over normal Harness EvalRun rows.",
      status: "COMPLETED",
      metadata_json: {
        experiment_kind: "langgraph_vs_native_harness",
        regression_delta_replaced: false,
      },
      created_by: "dev-engineer",
      created_at: "2026-06-02T00:02:00Z",
      updated_at: "2026-06-02T00:02:00Z",
      eval_run_ids: ["native-run-1", "langgraph-run-1"],
      arms: [
        {
          id: "arm-native",
          experiment_id: "experiment-1",
          dataset_id: "dataset-1",
          eval_run_id: "native-run-1",
          organization_id: "dev-org",
          name: "native",
          arm_type: "baseline",
          status: "COMPLETED",
          capability_hashes_json: { capability_version_ids: ["native-capability-version"] },
          metrics_json: { case_total: 2, passed_total: 2 },
          error_message: null,
          created_at: "2026-06-02T00:02:00Z",
        },
        {
          id: "arm-langgraph",
          experiment_id: "experiment-1",
          dataset_id: "dataset-1",
          eval_run_id: "langgraph-run-1",
          organization_id: "dev-org",
          name: "langgraph",
          arm_type: "candidate",
          status: "COMPLETED",
          capability_hashes_json: { content_sha256_values: ["sha256:langgraph-workflow"] },
          metrics_json: { case_total: 2, passed_total: 1 },
          error_message: null,
          created_at: "2026-06-02T00:02:00Z",
        },
      ],
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/agents" && !init?.method) {
        return jsonResponse({
          items: [
            {
              id: "default",
              name: "默认智能体",
              description: "默认入口智能体",
              role: "executor",
              status: "ACTIVE",
              model_provider: "default",
              model_name: "default",
              system_prompt: "",
              tools_json: [],
              routing_tags: [],
              max_parallel_assignments: 1,
              capability_attachments: [],
              created_at: "2026-06-02T00:00:00Z",
              updated_at: "2026-06-02T00:00:00Z",
            },
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/evals/datasets" && !init?.method) {
        return jsonResponse({
          items: [
            {
              id: "dataset-1",
              organization_id: "dev-org",
              name: "LangGraph 数据集",
              description: "contrast dataset",
              status: "ACTIVE",
              baseline_run_id: "native-run-1",
              created_by: "dev-engineer",
              created_at: "2026-06-02T00:00:00Z",
              updated_at: "2026-06-02T00:00:00Z",
              case_count: 2,
            },
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/evals/datasets/dataset-1/cases" && !init?.method) {
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path === "/api/evals/runs" && !init?.method) {
        return jsonResponse({
          items: [
            evalRun("native-run-1", { capability_version_ids: ["native-capability-version"] }),
            evalRun("langgraph-run-1", { content_sha256_values: ["sha256:langgraph-workflow"] }),
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/evals/runs/native-run-1/regression" && !init?.method) {
        return jsonResponse({
          baseline_run_id: "native-run-1",
          current_run_id: "native-run-1",
          task_success_rate_delta: 0,
          tool_selection_accuracy_delta: 0,
          avg_latency_ms_delta: 0,
          grounding_pass_rate_delta: 0,
          citation_coverage_rate_delta: 0,
          unsupported_marker_rate_delta: 0,
          fallback_mismatch_rate_delta: 0,
          forbidden_evidence_leak_rate_delta: 0,
          required_evidence_miss_rate_delta: 0,
          newly_failing_case_ids: [],
          newly_passing_case_ids: [],
          newly_grounding_failing_case_ids: [],
          newly_forbidden_leak_case_ids: [],
          is_regression: false,
          total_cases: 2,
          passed_cases: 2,
          failed_cases: 0,
          grounding_sample_count: 0,
          low_sample_count: false,
          low_sample_caveat: null,
        });
      }
      if (path === "/api/evals/experiments" && !init?.method) {
        return jsonResponse({ items: createdExperiment ? [experiment] : [], next_cursor: null });
      }
      if (path === "/api/evals/datasets/dataset-1/experiments" && init?.method === "POST") {
        createdExperiment = true;
        return jsonResponse(experiment, 201);
      }
      return jsonResponse({ detail: `unexpected request ${path}` }, 404);
    });
    renderPage(fetchMock);

    expect(await screen.findByText("LangGraph vs Native")).toBeInTheDocument();
    expect(screen.getByText("对照实验只投影已有 EvalRun/EvalResult；RegressionDelta 仍保留 baseline/current 回归语义。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /选择 Native Harness Eval Run/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "配置对照实验" }));
    const dialog = await screen.findByRole("dialog", { name: "LangGraph vs Native" });
    expect(within(dialog).getByText("对照实验只投影已有 EvalRun/EvalResult；RegressionDelta 仍保留 baseline/current 回归语义。")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: /选择 Native Harness Eval Run/ }));
    await user.click(within(await screen.findByRole("listbox", { name: "选择 Native Harness Eval Run" })).getByText(/native-r/));
    await user.click(within(dialog).getByRole("button", { name: /选择 LangGraph Workflow Eval Run/ }));
    await user.click(within(await screen.findByRole("listbox", { name: "选择 LangGraph Workflow Eval Run" })).getByText(/langgrap/));
    await user.click(within(dialog).getByRole("button", { name: "创建对照实验" }));

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input) === "/api/evals/datasets/dataset-1/experiments" && init?.method === "POST",
      );
      expect(createCall).toBeDefined();
      expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
        name: "LangGraph vs Native Harness",
        metadata_json: {
          experiment_kind: "langgraph_vs_native_harness",
          regression_delta_replaced: false,
        },
        arms: [
          { name: "native", arm_type: "baseline", eval_run_id: "native-run-1" },
          { name: "langgraph", arm_type: "candidate", eval_run_id: "langgraph-run-1" },
        ],
      });
    });
    expect(await screen.findByText("native · native-r")).toBeInTheDocument();
    expect(screen.getByText("langgraph · langgrap")).toBeInTheDocument();
    expect(screen.getByText(/sha256:lan/)).toBeInTheDocument();
  });

  it("clears contrast experiment run selections when the active dataset changes", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/agents" && !init?.method) {
        return jsonResponse({
          items: [
            {
              id: "default",
              name: "默认智能体",
              description: "默认入口智能体",
              role: "executor",
              status: "ACTIVE",
              model_provider: "default",
              model_name: "default",
              system_prompt: "",
              tools_json: [],
              routing_tags: [],
              max_parallel_assignments: 1,
              capability_attachments: [],
              created_at: "2026-06-02T00:00:00Z",
              updated_at: "2026-06-02T00:00:00Z",
            },
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/evals/datasets" && !init?.method) {
        return jsonResponse({
          items: [
            {
              id: "dataset-1",
              organization_id: "dev-org",
              name: "LangGraph 数据集",
              description: "contrast dataset",
              status: "ACTIVE",
              baseline_run_id: "native-run-1",
              created_by: "dev-engineer",
              created_at: "2026-06-02T00:00:00Z",
              updated_at: "2026-06-02T00:00:00Z",
              case_count: 2,
            },
            {
              id: "dataset-2",
              organization_id: "dev-org",
              name: "空数据集",
              description: "no contrast runs",
              status: "ACTIVE",
              baseline_run_id: null,
              created_by: "dev-engineer",
              created_at: "2026-06-02T00:00:00Z",
              updated_at: "2026-06-02T00:00:00Z",
              case_count: 0,
            },
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/evals/datasets/dataset-1/cases" && !init?.method) {
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path === "/api/evals/datasets/dataset-2/cases" && !init?.method) {
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path === "/api/evals/runs" && !init?.method) {
        return jsonResponse({
          items: [
            evalRun("native-run-1", { capability_version_ids: ["native-capability-version"] }),
            evalRun("langgraph-run-1", { content_sha256_values: ["sha256:langgraph-workflow"] }),
            evalRun("other-dataset-run", {}, "dataset-2"),
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/evals/runs/native-run-1/regression" && !init?.method) {
        return jsonResponse({
          baseline_run_id: "native-run-1",
          current_run_id: "native-run-1",
          task_success_rate_delta: 0,
          tool_selection_accuracy_delta: 0,
          avg_latency_ms_delta: 0,
          grounding_pass_rate_delta: 0,
          citation_coverage_rate_delta: 0,
          unsupported_marker_rate_delta: 0,
          fallback_mismatch_rate_delta: 0,
          forbidden_evidence_leak_rate_delta: 0,
          required_evidence_miss_rate_delta: 0,
          newly_failing_case_ids: [],
          newly_passing_case_ids: [],
          newly_grounding_failing_case_ids: [],
          newly_forbidden_leak_case_ids: [],
          is_regression: false,
          total_cases: 2,
          passed_cases: 2,
          failed_cases: 0,
          grounding_sample_count: 0,
          low_sample_count: false,
          low_sample_caveat: null,
        });
      }
      if (path === "/api/evals/experiments" && !init?.method) {
        return jsonResponse({ items: [], next_cursor: null });
      }
      return jsonResponse({ detail: `unexpected request ${path}` }, 404);
    });
    renderPage(fetchMock);

    expect(await screen.findByText("LangGraph vs Native")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "配置对照实验" }));
    const firstDialog = await screen.findByRole("dialog", { name: "LangGraph vs Native" });
    await user.click(within(firstDialog).getByRole("button", { name: /选择 Native Harness Eval Run/ }));
    await user.click(within(await screen.findByRole("listbox", { name: "选择 Native Harness Eval Run" })).getByText(/native-r/));
    await user.click(within(firstDialog).getByRole("button", { name: /选择 LangGraph Workflow Eval Run/ }));
    await user.click(within(await screen.findByRole("listbox", { name: "选择 LangGraph Workflow Eval Run" })).getByText(/langgrap/));
    expect(within(firstDialog).getByRole("button", { name: "创建对照实验" })).toBeEnabled();
    await user.keyboard("{Escape}");

    await user.click(screen.getByRole("button", { name: /空数据集/ }));
    expect(screen.getAllByText("未选择")).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: "配置对照实验" }));
    const secondDialog = await screen.findByRole("dialog", { name: "LangGraph vs Native" });
    expect(within(secondDialog).getByRole("button", { name: "创建对照实验" })).toBeDisabled();
  });

  it("keeps the case queue actions compact when the agent menu opens", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/agents" && !init?.method) {
        return jsonResponse({
          items: [
            {
              id: "default",
              name: "Default Agent With A Long Display Name",
              description: "default",
              role: "executor",
              status: "ACTIVE",
              model_provider: "default",
              model_name: "default",
              system_prompt: "",
              tools_json: [],
              routing_tags: [],
              max_parallel_assignments: 1,
              capability_attachments: [],
              created_at: "2026-06-02T00:00:00Z",
              updated_at: "2026-06-02T00:00:00Z",
            },
            {
              id: "reviewer",
              name: "Reviewer Agent",
              description: "reviewer",
              role: "reviewer",
              status: "ACTIVE",
              model_provider: "default",
              model_name: "default",
              system_prompt: "",
              tools_json: [],
              routing_tags: [],
              max_parallel_assignments: 1,
              capability_attachments: [],
              created_at: "2026-06-02T00:00:00Z",
              updated_at: "2026-06-02T00:00:00Z",
            },
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/evals/datasets" && !init?.method) {
        return jsonResponse({
          items: [
            {
              id: "dataset-1",
              organization_id: "dev-org",
              name: "截图回归数据集",
              description: "layout dataset",
              status: "ACTIVE",
              baseline_run_id: null,
              created_by: "dev-engineer",
              created_at: "2026-06-02T00:00:00Z",
              updated_at: "2026-06-02T00:00:00Z",
              case_count: 0,
            },
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/evals/datasets/dataset-1/cases" && !init?.method) {
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path === "/api/evals/runs" && !init?.method) {
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path === "/api/evals/experiments" && !init?.method) {
        return jsonResponse({ items: [], next_cursor: null });
      }
      return jsonResponse({ detail: `unexpected request ${path}` }, 404);
    });
    renderPage(fetchMock);

    const runEvalButton = await screen.findByRole("button", { name: "运行评测" });
    expect(runEvalButton).toHaveClass("h-8", "whitespace-nowrap", "shrink-0");

    const agentTrigger = screen.getByRole("button", { name: /选择评测智能体/ });
    expect(agentTrigger).toHaveClass("h-8");
    expect(within(agentTrigger).queryByText("default · 活跃中")).not.toBeInTheDocument();

    await user.click(agentTrigger);
    const agentMenu = await screen.findByRole("listbox", { name: "选择评测智能体" });
    expect(within(agentMenu).getByText("default · 活跃中")).toBeInTheDocument();
    expect(agentMenu).toHaveClass("max-h-64");
    expect(agentMenu.className).toContain("w-[min(16rem,calc(100vw-3rem))]");
  });
});
