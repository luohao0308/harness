import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DashboardPage } from "../DashboardPage";

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

function onboardingState(demoLoaded: boolean) {
  return {
    id: "onboarding-dev",
    organization_id: "dev-org",
    user_id: "dev-engineer",
    current_step: 4,
    completed: true,
    skipped: false,
    demo_loaded: demoLoaded,
    provider_json: {},
    agent_id: demoLoaded ? "demo-research-assistant" : null,
    demo_task_id: demoLoaded ? "demo-run-1" : null,
    created_at: "2026-05-31T00:00:00Z",
    updated_at: "2026-05-31T00:00:00Z",
    completed_at: "2026-05-31T00:00:00Z",
  };
}

function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <QueryClientProvider client={queryClient}>
        <DashboardPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DashboardPage Demo loading", () => {
  it("hides the unloaded banner after an existing Demo load succeeds", async () => {
    const user = userEvent.setup();
    let demoLoaded = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/onboarding/state" && method === "GET") {
        return jsonResponse(onboardingState(demoLoaded));
      }
      if (path === "/api/demo/load" && method === "POST") {
        demoLoaded = true;
        return jsonResponse({
          status: "already_loaded",
          agent_ids: ["demo-research-assistant"],
          knowledge_source_ids: ["demo-source-1"],
          dataset_id: "demo-dataset-1",
          task_id: "demo-run-1",
          specialist_ids: [],
          demo_loaded: true,
        });
      }
      if (path === "/api/agents" && method === "GET") {
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path === "/api/agents/runs" && method === "GET") {
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path === "/api/observability/summary" && method === "GET") {
        return jsonResponse({ tasks_by_status: [], failed_task_total: 0 });
      }
      if (path === "/api/observability/cost-rollup" && method === "GET") {
        return jsonResponse({ total_cost_usd: 0, total_runs: 0, items: [] });
      }
      if (path === "/api/observability/alert-events" && method === "GET") {
        return jsonResponse({ items: [], next_cursor: null });
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    renderPage(fetchMock);

    expect(await screen.findByText("Demo 数据未加载")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /一键加载 Demo/ }));

    await waitFor(() => {
      expect(screen.queryByText("Demo 数据未加载")).not.toBeInTheDocument();
    });
    expect(await screen.findByText("Demo 数据已存在")).toBeInTheDocument();
  });
});
