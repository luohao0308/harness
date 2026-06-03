import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AlertRulesPage } from "../AlertRulesPage";
import { CostDashboardPage } from "../CostDashboardPage";
import { ObservabilityPage } from "../ObservabilityPage";
import { TraceExplorerPage } from "../TraceExplorerPage";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderRoute(path: string, element: ReactNode, fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path={path.split("?")[0]} element={element} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Observability v1 pages", () => {
  it("renders LangGraph execution-mode counts from the runtime architecture API", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.includes("/api/observability/summary")) {
        return jsonResponse({
          event_total: 0,
          task_total: 0,
          failed_task_total: 0,
          model_call_total: 0,
          tool_call_total: 0,
          sandbox_total: 0,
          token_optimization: {},
          tasks_by_status: [],
          subagents_by_status: [],
          agent_assignments_by_status: [],
          model_calls_by_status: [],
          tool_calls_by_status: [],
          sandboxes_by_status: [],
          warm_pool: { enabled: true, min_size: 0, max_size: 0, idle: 0, busy: 0, failed: 0, hit_total: 0, miss_total: 0 },
        });
      }
      if (path.includes("/api/observability/architecture")) {
        return jsonResponse({
          planner_executor: {
            enabled: true,
            planner: "planner",
            executor: "dag",
            react_engine: "harness",
            planner_prompt_version: "planner-v1",
            plan_total: 7,
            sync_step_total: 11,
            async_step_total: 13,
            langgraph_step_total: 42,
            status: "active",
          },
          event_sourcing: {
            enabled: true,
            event_total: 100,
            snapshot_total: 1,
            snapshot_frequency_events: 25,
            replay_enabled: true,
            resume_enabled: true,
            audit_log_enabled: true,
            time_travel_debugging_enabled: true,
            last_sequence: 99,
          },
          notes: ["langgraph_workflow is not a ToolRunner tool"],
        });
      }
      if (path.includes("/api/observability/grounding-quality")) {
        return jsonResponse({
          metrics: {
            grounding_pass_rate: 1,
            citation_coverage_rate: 1,
            forbidden_evidence_leak_rate: 0,
            fallback_mismatch_rate: 0,
            unsupported_marker_rate: 0,
            grounding_failure_total: 0,
          },
          items: [],
          next_cursor: null,
        });
      }
      if (path.includes("/api/observability/services/health")) {
        return jsonResponse({ services: [] });
      }
      if (path.includes("/api/observability/grafana/dashboards")) {
        return jsonResponse({ items: [] });
      }
      if (path.includes("/api/observability/exports/history")) {
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path.includes("/api/observability/exports")) {
        return jsonResponse({ items: [] });
      }
      if (path.includes("/api/subagents/recovery/global-summary")) {
        return jsonResponse({ organization_count: 0, batch_total: 0, recovered_total: 0, organizations: [] });
      }
      if (path.includes("/api/subagents/recovery/summary")) {
        return jsonResponse({
          batch_total: 0,
          task_total: 0,
          scanned_total: 0,
          recovered_total: 0,
          lock_skipped_total: 0,
          latest_completed_at: null,
          action_counts: {},
          tasks: [],
          recent_batches: [],
        });
      }
      if (path.includes("/api/observability/logs")) {
        return jsonResponse({ items: [], next_cursor: null });
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderRoute("/observability", <ObservabilityPage />, fetchMock);

    expect(await screen.findByText("Planner / Executor / LangGraph")).toBeInTheDocument();
    expect(screen.getByText("LangGraph 节点只统计执行模式，不把 workflow 作为 ToolRunner 工具计数。")).toBeInTheDocument();
    expect(await screen.findByText("42")).toBeInTheDocument();
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/api/observability/architecture"))).toBe(true);
    });
  });

  it("renders cost dashboard kpis and top breakdown", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.includes("/api/observability/alert-events")) {
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path.includes("/api/observability/cost-rollup")) {
        return jsonResponse({
          window: "7d",
          group_by: "agent",
          generated_at: "2026-05-29T00:00:00Z",
          total_cost_usd: 0.004,
          total_tokens: 1500,
          total_runs: 1,
          average_run_cost_usd: 0.004,
          breakdown: [
            { key: "default", label: "default", cost_usd: 0.004, tokens_in: 1000, tokens_out: 500, run_count: 1, share: 1 },
          ],
          series: [
            { bucket_start: "2026-05-29T00:00:00Z", key: "default", label: "default", cost_usd: 0.004, tokens: 1500, run_count: 1 },
          ],
        });
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderRoute("/observability/cost", <CostDashboardPage />, fetchMock);

    expect(await screen.findByText("总 Token")).toBeInTheDocument();
    expect((await screen.findAllByText("default")).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("1,500").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("$0.004000").length).toBeGreaterThanOrEqual(1);
  });

  it("renders trace list, gantt rows, and selected span attributes", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.includes("/api/observability/alert-events")) {
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path.endsWith("/api/observability/traces?limit=80")) {
        return jsonResponse({
          items: [
            { trace_id: "trace-1", task_id: "run-1", root_name: "POST /api/run", start_time: "2026-05-29T00:00:00Z", duration_ms: 100, span_count: 2, status: "OK", source: "local_otel" },
          ],
          next_cursor: null,
        });
      }
      if (path.endsWith("/api/observability/traces/trace-1")) {
        return jsonResponse({
          trace_id: "trace-1",
          source: "local_otel",
          spans: [
            { trace_id: "trace-1", span_id: "root", parent_span_id: null, name: "POST /api/run", service: "api-server", start_time: "2026-05-29T00:00:00Z", end_time: "2026-05-29T00:00:00Z", duration_ms: 100, kind: "server", status: "OK", task_id: "run-1", agent_run_id: null, attributes: { task_id: "run-1" }, source: "local_otel" },
            { trace_id: "trace-1", span_id: "model", parent_span_id: "root", name: "model_call", service: "api-server", start_time: "2026-05-29T00:00:00Z", end_time: "2026-05-29T00:00:00Z", duration_ms: 80, kind: "client", status: "OK", task_id: "run-1", agent_run_id: null, attributes: { model_name: "deepseek" }, source: "local_otel" },
          ],
          service_nodes: [],
          service_edges: [],
        });
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderRoute("/observability/trace", <TraceExplorerPage />, fetchMock);

    expect(await screen.findByText("POST /api/run")).toBeInTheDocument();
    expect(await screen.findByText("model_call")).toBeInTheDocument();
    expect(screen.getByText("Span 属性")).toBeInTheDocument();
    expect(screen.getByText(/task_id/)).toBeInTheDocument();
  });

  it("renders alert rules and opens the edit dialog", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.includes("/api/observability/alert-rules") && !path.includes("evaluate")) {
        return jsonResponse({
          items: [
            { id: "rule-1", organization_id: "dev-org", name: "budget", metric: "subagent_budget_exceeded_count", comparator: ">", threshold: 1, window_seconds: 300, enabled: true, severity: "warning", notification_channels_json: ["in_app"], created_at: "2026-05-29T00:00:00Z", updated_at: "2026-05-29T00:00:00Z" },
          ],
          next_cursor: null,
        });
      }
      if (path.includes("/api/observability/alert-events")) {
        return jsonResponse({ items: [], next_cursor: null });
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderRoute("/observability/alerts", <AlertRulesPage />, fetchMock);

    expect(await screen.findByText("budget")).toBeInTheDocument();
    await user.click(screen.getByLabelText("编辑"));
    expect(screen.getByRole("dialog", { name: "编辑告警规则" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("subagent_budget_exceeded_count")).toBeInTheDocument();
  });
});
