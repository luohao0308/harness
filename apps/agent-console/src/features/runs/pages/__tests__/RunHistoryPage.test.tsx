import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RunHistoryPage } from "../RunHistoryPage";

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
    <MemoryRouter initialEntries={["/runs"]}>
      <QueryClientProvider client={queryClient}>
        <RunHistoryPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("RunHistoryPage", () => {
  it("uses a compact Workspace action in the run history toolbar", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/agents/runs" && !init?.method) {
        return jsonResponse({
          items: [
            {
              id: "run-1",
              title: "Cache evidence run",
              goal: "Verify context cache savings",
              status: "COMPLETED",
              model_provider: "deepseek",
              model_name: "deepseek-v4-flash",
              max_runtime_seconds: 600,
              max_subagents: 2,
              enable_sandbox: true,
              enable_network: false,
              created_at: "2026-05-25T10:00:00Z",
              updated_at: "2026-05-25T10:01:00Z",
              completed_at: "2026-05-25T10:01:00Z",
            },
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/observability/summary" && !init?.method) {
        return jsonResponse({
          tasks_by_status: [{ name: "RUNNING", count: 1 }],
          failed_task_total: 0,
        });
      }
      return jsonResponse({ detail: `unexpected request ${path}` }, 404);
    });

    renderPage(fetchMock);

    expect(await screen.findByText("Cache evidence run")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^工作台$/ })).toBeInTheDocument();
    expect(screen.queryByText("打开智能体工作台")).not.toBeInTheDocument();
  });
});
