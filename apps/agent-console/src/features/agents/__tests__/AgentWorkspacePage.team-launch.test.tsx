import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useWorkspaceStore } from "../../../stores/workspaceStore";
import { AgentWorkspacePage } from "../pages/AgentWorkspacePage";

const apiBaseUrl = "http://127.0.0.1:8000";
const now = "2026-05-24T00:00:00Z";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function requestPath(input: RequestInfo | URL): string {
  const url = String(input);
  return new URL(url.startsWith("http") ? url : `${apiBaseUrl}${url}`).pathname;
}

function agent() {
  return {
    id: "default",
    name: "Default Agent",
    description: "Default entry agent",
    role: "planner",
    status: "ACTIVE",
    model_provider: "default",
    model_name: "default",
    system_prompt: "Plan with evidence",
    tools_json: [],
    routing_tags: ["default"],
    max_parallel_assignments: 2,
    created_at: now,
    updated_at: now,
  };
}

function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/agents/default/workspace"]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/agents/:agentId/workspace" element={<AgentWorkspacePage />} />
          <Route path="/teams/:teamId" element={<div>Team opened</div>} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.unstubAllGlobals();
  useWorkspaceStore.getState().reset();
  window.localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("AgentWorkspacePage Team launcher", () => {
  it("uses the next available team name before navigating to Team Mode", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents/default" && method === "GET") return jsonResponse(agent());
      if (path === "/api/settings/models" && method === "GET") {
        return jsonResponse({
          default_provider: "default",
          default_model: "default",
          providers: [{ name: "default", label: "Default", model: "default" }],
          rate_limits: {},
          health: {},
          circuit_breaker: {},
        });
      }
      if (path === "/api/tools/registry" && method === "GET") {
        return jsonResponse({ items: [], categories: [], sources: [] });
      }
      if (path === "/api/teams" && method === "GET") {
        return jsonResponse({
          items: [
            { id: "team-existing-1", name: "Default Agent 团队" },
            { id: "team-existing-2", name: "Default Agent 团队 2" },
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/teams" && method === "POST") {
        return jsonResponse({ id: "team-created", name: "Default Agent 团队 3" }, 201);
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    renderPage(fetchMock);

    await user.click(await screen.findByRole("button", { name: "新开团队模式" }));

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input) === "/api/teams" && init?.method === "POST",
      );
      expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
        name: "Default Agent 团队 3",
        leader_agent_id: "default",
        leader_name: "Default Agent",
        workspace_mode: "shared",
      });
    });
    expect(await screen.findByText("Team opened")).toBeInTheDocument();
  });
});
