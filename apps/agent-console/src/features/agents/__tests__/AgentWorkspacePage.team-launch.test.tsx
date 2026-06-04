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
      if (path === "/api/agents/local-agent/connections" && method === "GET") {
        return jsonResponse({ items: [] });
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

  it("sends through a local Agent binding inside the Workspace chat surface", async () => {
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
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path === "/api/agents/local-agent/connections" && method === "GET") {
        return jsonResponse({
          items: [
            {
              id: "conn-local-1",
              agent_id: "default",
              owner_user_id: "dev-user",
              display_name: "hao Local",
              adapter_kind: "hao",
              protocol_version: "local-agent-v1",
              bridge_version: "0.1.0",
              status: "online",
              workspace_root: ".../agent_workspace/harness",
              capabilities_json: { supports_resume: true, supports_streaming: true },
              risk_capabilities_json: ["shell"],
              last_seen_at: now,
              revoked_at: null,
              created_at: now,
              updated_at: now,
            },
          ],
        });
      }
      if (
        path === "/api/agents/local-agent/connections/conn-local-1/bindings" &&
        method === "GET"
      ) {
        return jsonResponse({ items: [] });
      }
      if (
        path === "/api/agents/local-agent/connections/conn-local-1/bindings" &&
        method === "POST"
      ) {
        return jsonResponse(
          {
            id: "binding-1",
            connection_id: "conn-local-1",
            agent_id: "default",
            agent_session_id: "session-1",
            adapter_session_id: null,
            resume_mode: "native_resume",
            status: "active",
            created_at: now,
            updated_at: now,
          },
          201,
        );
      }
      if (path === "/api/agents/sessions/session-1/messages" && method === "GET") {
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path === "/api/agents/local-agent/bindings/binding-1/messages" && method === "POST") {
        return jsonResponse(
          {
            bridge_task_id: "bridge-task-1",
            run_id: "run-local-1",
            agent_session_id: "session-1",
            user_message_id: "message-user-1",
            status: "pending",
          },
          202,
        );
      }
      if (path === "/api/agents/runs/run-local-1/workspace" && method === "GET") {
        return jsonResponse({
          run: { id: "run-local-1", status: "RUNNING", created_at: now },
          events: [],
          model_calls: [],
          tool_calls: [],
          approvals: [],
        });
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    renderPage(fetchMock);

    await user.click(await screen.findByLabelText("本地 Agent"));
    await screen.findByText("Session session-1");

    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "继续检查本地项目");
    await user.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => {
      const sendCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/agents/local-agent/bindings/binding-1/messages" &&
          init?.method === "POST",
      );
      expect(JSON.parse(String(sendCall?.[1]?.body))).toMatchObject({
        content: "继续检查本地项目",
      });
    });
    expect(await screen.findByText("等待本地 Agent 响应...")).toBeInTheDocument();
  });
});
