import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AlertRulesPage } from "../AlertRulesPage";
import { CostDashboardPage } from "../CostDashboardPage";
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
