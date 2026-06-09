import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
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

function sseFrame(event: string, payload: Record<string, unknown>): string {
  return `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`;
}

function streamResponse(frames: string): Response {
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(frames));
        controller.close();
      },
    }),
    {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    },
  );
}

function localAgentSseMessage(
  eventType: string,
  payloadJson: Record<string, unknown>,
  overrides: Partial<Record<string, unknown>> = {},
): MessageEvent<string> {
  return new MessageEvent<string>("message", {
    data: JSON.stringify({
      id: `${eventType}-event`,
      task_id: "task-event",
      agent_run_id: null,
      sequence: 1,
      event_type: eventType,
      payload_json: payloadJson,
      actor_type: "system",
      actor_id: null,
      trace_id: null,
      created_at: now,
      ...overrides,
    }),
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((innerResolve, innerReject) => {
    resolve = innerResolve;
    reject = innerReject;
  });
  return { promise, resolve, reject };
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

function researcherAgent() {
  return {
    ...agent(),
    id: "researcher",
    name: "Research Agent",
    role: "researcher",
    routing_tags: ["research"],
  };
}

function agentsPage() {
  return { items: [agent(), researcherAgent()], next_cursor: null };
}

function localConnection(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "conn-local-1",
    agent_id: "default",
    owner_user_id: "dev-user",
    onboarding_confirmed: true,
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
    ...overrides,
  };
}

function localBinding(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "binding-1",
    connection_id: "conn-local-1",
    agent_id: "default",
    agent_session_id: "session-1",
    adapter_session_id: null,
    resume_mode: "native_resume",
    status: "active",
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const renderResult = render(
    <MemoryRouter initialEntries={["/agents/default/workspace"]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/agents/:agentId/workspace" element={<AgentWorkspacePage />} />
          <Route path="/teams/:teamId" element={<div>Team opened</div>} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
  return { ...renderResult, queryClient };
}

async function chooseWorkspaceTarget(
  user: ReturnType<typeof userEvent.setup>,
  optionName: RegExp,
) {
  await user.click(
    await screen.findByRole("button", {
      name: /切换智能体或本地 Agent：/,
    }),
  );
  await user.click(await screen.findByRole("option", { name: optionName }));
}

beforeEach(() => {
  vi.unstubAllGlobals();
  useWorkspaceStore.getState().reset();
  window.localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("AgentWorkspacePage Team launcher", () => {
  it("uses the next available team name before navigating to Team Mode", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents" && method === "GET") return jsonResponse(agentsPage());
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
    const eventSources: Array<{
      url: string;
      onmessage: ((event: MessageEvent<string>) => void) | null;
      close: () => void;
    }> = [];
    class FakeEventSource {
      onopen: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent<string>) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      url: string;

      constructor(url: string | URL) {
        this.url = String(url);
        eventSources.push(this);
      }

      close = vi.fn();
    }
    vi.stubGlobal("EventSource", FakeEventSource);
    let localSessionMessages: Array<Record<string, unknown>> = [];
    let localBindingTasks: Array<Record<string, unknown>> = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents" && method === "GET") return jsonResponse(agentsPage());
      if (path === "/api/agents/default" && method === "GET") return jsonResponse(agent());
      if (path === "/api/settings/models" && method === "GET") {
        return jsonResponse({
          default_provider: "default",
          default_model: "default",
          providers: [
            { name: "default", label: "Default", model: "default" },
            { name: "anthropic", label: "Anthropic", model: "claude-sonnet-4" },
          ],
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
            localConnection({
              capabilities_json: {
                supports_resume: true,
                supports_streaming: true,
                model_provider: "anthropic",
                model_name: "claude-sonnet-4",
              },
            }),
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
        return jsonResponse({ items: localSessionMessages, next_cursor: null });
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
      if (path === "/api/agents/local-agent/bindings/binding-1/tasks" && method === "GET") {
        return jsonResponse({ items: localBindingTasks });
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

    const { queryClient } = renderPage(fetchMock);

    await user.click(await screen.findByRole("button", { name: "启用本地 Agent" }));
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.map(
          ([input, init]) => `${init?.method ?? "GET"} ${requestPath(input)}`,
        ),
      ).toContain("POST /api/agents/local-agent/connections/conn-local-1/bindings");
    });
    await screen.findByText("Session session-1");
    expect(await screen.findByRole("button", { name: /claude-sonnet-4/ })).toBeInTheDocument();

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
        model_provider: "anthropic",
        model_name: "claude-sonnet-4",
      });
    });
    expect(await screen.findByText("等待本地 Agent 响应...")).toBeInTheDocument();
    await waitFor(() => expect(eventSources.length).toBe(1));
    expect(new URL(eventSources[0].url, apiBaseUrl).pathname).toBe(
      "/api/tasks/run-local-1/events/stream",
    );

    act(() => {
      eventSources[0].onmessage?.({
        data: JSON.stringify({
          id: "event-approval-1",
          task_id: "run-local-1",
          agent_run_id: null,
          sequence: 1,
          event_type: "TOOL_APPROVAL_REQUESTED",
          payload_json: {
            bridge_task_id: "bridge-task-1",
            approval_id: "approval-read-desktop",
            tool_name: "read_file",
            reason: "local filesystem reads require Harness approval in V3",
          },
          actor_type: "local_agent",
          actor_id: "conn-local-1",
          trace_id: null,
          created_at: now,
        }),
        lastEventId: "1",
      } as MessageEvent<string>);
    });

    expect(
      await screen.findByText(/本地 Agent 请求本地工具 read_file，正在等待 审批 approval/),
    ).toBeInTheDocument();
    localBindingTasks = [
      {
        id: "bridge-task-1",
        binding_id: "binding-1",
        connection_id: "conn-local-1",
        agent_session_id: "session-1",
        user_message_id: "message-user-1",
        client_message_id: "local-final",
        run_id: "run-local-1",
        status: "running",
        error_message: null,
        created_at: now,
        updated_at: now,
      },
    ];
    await act(async () => {
      await queryClient.refetchQueries({
        queryKey: ["local-agent-binding-tasks", "binding-1"],
      });
    });
    expect(
      await screen.findByText(/本地 Agent 请求本地工具 read_file，正在等待 审批 approval/),
    ).toBeInTheDocument();
    expect(screen.queryByText("本地 Agent 正在处理，完成后会同步到这里。")).not.toBeInTheDocument();

    act(() => {
      eventSources[0].onmessage?.({
        data: JSON.stringify({
          id: "event-delta-1",
          task_id: "run-local-1",
          agent_run_id: null,
          sequence: 2,
          event_type: "LOCAL_AGENT_DELTA_RECEIVED",
          payload_json: {
            bridge_task_id: "bridge-task-1",
            content: "流式输出片段",
          },
          actor_type: "local_agent",
          actor_id: "conn-local-1",
          trace_id: null,
          created_at: now,
        }),
        lastEventId: "2",
      } as MessageEvent<string>);
    });

    expect(await screen.findByText("流式输出片段")).toBeInTheDocument();

    localSessionMessages = [
      {
        id: "message-user-1",
        session_id: "session-1",
        agent_id: "default",
        role: "user",
        content: "继续检查本地项目",
        metadata_json: {
          source: "local_agent",
          connection_id: "conn-local-1",
          binding_id: "binding-1",
          agent_session_id: "session-1",
          client_message_id: "local-final",
        },
        created_at: now,
      },
      {
        id: "message-assistant-1",
        session_id: "session-1",
        agent_id: "default",
        role: "assistant",
        content: "最终本地回答",
        metadata_json: {
          source: "local_agent",
          connection_id: "conn-local-1",
          binding_id: "binding-1",
          agent_session_id: "session-1",
          bridge_task_id: "bridge-task-1",
        },
        created_at: now,
      },
    ];
    localBindingTasks = [];
    act(() => {
      eventSources[0].onmessage?.({
        data: JSON.stringify({
          id: "event-completed-1",
          task_id: "run-local-1",
          agent_run_id: null,
          sequence: 2,
          event_type: "LOCAL_AGENT_MESSAGE_COMPLETED",
          payload_json: {
            bridge_task_id: "bridge-task-1",
          },
          actor_type: "local_agent",
          actor_id: "conn-local-1",
          trace_id: null,
          created_at: now,
        }),
        lastEventId: "2",
      } as MessageEvent<string>);
    });

    expect(await screen.findByText("最终本地回答")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("流式输出片段")).not.toBeInTheDocument());
    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "下一条");
    expect(screen.getByRole("button", { name: "发送" })).toBeEnabled();
  });

  it("does not freeze a local Agent pending placeholder when completion arrives before hydration", async () => {
    const user = userEvent.setup();
    const eventSources: Array<{
      url: string;
      onmessage: ((event: MessageEvent<string>) => void) | null;
      close: () => void;
    }> = [];
    class FakeEventSource {
      onopen: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent<string>) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      url: string;

      constructor(url: string | URL) {
        this.url = String(url);
        eventSources.push(this);
      }

      close = vi.fn();
    }
    vi.stubGlobal("EventSource", FakeEventSource);
    let localSessionMessages: Array<Record<string, unknown>> = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents" && method === "GET") return jsonResponse(agentsPage());
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
        return jsonResponse({ items: [localConnection()] });
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
        return jsonResponse(localBinding(), 201);
      }
      if (path === "/api/agents/sessions/session-1/messages" && method === "GET") {
        return jsonResponse({ items: localSessionMessages, next_cursor: null });
      }
      if (path === "/api/agents/local-agent/bindings/binding-1/messages" && method === "POST") {
        return jsonResponse(
          {
            bridge_task_id: "bridge-task-no-delta",
            run_id: "run-local-no-delta",
            agent_session_id: "session-1",
            user_message_id: "message-user-no-delta",
            status: "pending",
          },
          202,
        );
      }
      if (path === "/api/agents/local-agent/bindings/binding-1/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/agents/runs/run-local-no-delta/workspace" && method === "GET") {
        return jsonResponse({
          run: { id: "run-local-no-delta", status: "RUNNING", created_at: now },
          events: [],
          model_calls: [],
          tool_calls: [],
          approvals: [],
        });
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    const { queryClient } = renderPage(fetchMock);

    await chooseWorkspaceTarget(user, /hao Local/);
    await screen.findByText("Session session-1");
    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "只回复 OK");
    await user.click(screen.getByRole("button", { name: "发送" }));
    expect(await screen.findByText("等待本地 Agent 响应...")).toBeInTheDocument();
    await waitFor(() => expect(eventSources.length).toBe(1));

    act(() => {
      eventSources[0].onmessage?.({
        data: JSON.stringify({
          id: "event-completed-no-delta",
          task_id: "run-local-no-delta",
          agent_run_id: null,
          sequence: 1,
          event_type: "LOCAL_AGENT_MESSAGE_COMPLETED",
          payload_json: {
            bridge_task_id: "bridge-task-no-delta",
          },
          actor_type: "local_agent",
          actor_id: "conn-local-1",
          trace_id: null,
          created_at: now,
        }),
        lastEventId: "1",
      } as MessageEvent<string>);
    });

    expect(await screen.findByText("等待本地 Agent 响应...")).toBeInTheDocument();
    localSessionMessages = [
      {
        id: "message-user-no-delta",
        session_id: "session-1",
        agent_id: "default",
        role: "user",
        content: "只回复 OK",
        metadata_json: {
          source: "local_agent",
          connection_id: "conn-local-1",
          binding_id: "binding-1",
          agent_session_id: "session-1",
          client_message_id: "local-no-delta",
        },
        created_at: now,
      },
      {
        id: "message-assistant-no-delta",
        session_id: "session-1",
        agent_id: "default",
        role: "assistant",
        content: "OK",
        metadata_json: {
          source: "local_agent",
          connection_id: "conn-local-1",
          binding_id: "binding-1",
          agent_session_id: "session-1",
          bridge_task_id: "bridge-task-no-delta",
        },
        created_at: now,
      },
    ];
    await act(async () => {
      await queryClient.refetchQueries({
        queryKey: ["agent-session-messages", "session-1"],
      });
    });

    expect(await screen.findByText("OK")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("等待本地 Agent 响应...")).not.toBeInTheDocument());
  });

  it("keeps a manually selected composer model across local connection polling", async () => {
    const user = userEvent.setup();
    class FakeEventSource {
      onmessage: ((event: MessageEvent<string>) => void) | null = null;
      url: string;

      constructor(url: string | URL) {
        this.url = String(url);
      }

      close = vi.fn();
    }
    vi.stubGlobal("EventSource", FakeEventSource);
    let sentBody: Record<string, unknown> | null = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents" && method === "GET") return jsonResponse(agentsPage());
      if (path === "/api/agents/default" && method === "GET") return jsonResponse(agent());
      if (path === "/api/settings/models" && method === "GET") {
        return jsonResponse({
          default_provider: "default",
          default_model: "default",
          providers: [
            { name: "default", label: "Default", model: "default" },
            { name: "anthropic", label: "Anthropic", model: "claude-sonnet-4" },
          ],
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
            localConnection({
              capabilities_json: {
                supports_resume: true,
                supports_streaming: true,
                model_provider: "anthropic",
                model_name: "claude-sonnet-4",
              },
            }),
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
        return jsonResponse(localBinding(), 201);
      }
      if (path === "/api/agents/sessions/session-1/messages" && method === "GET") {
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path === "/api/agents/local-agent/bindings/binding-1/messages" && method === "POST") {
        sentBody = JSON.parse(String(init?.body));
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
      if (path === "/api/agents/local-agent/bindings/binding-1/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    const { queryClient } = renderPage(fetchMock);

    await chooseWorkspaceTarget(user, /hao Local/);
    await screen.findByText("Session session-1");
    await user.click(await screen.findByRole("button", { name: /claude-sonnet-4/ }));
    await user.click(await screen.findByRole("option", { name: /Default/ }));

    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: ["local-agent-connections"] });
    });

    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "使用手动模型");
    await user.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => {
      expect(sentBody).toMatchObject({
        content: "使用手动模型",
        model_provider: "default",
        model_name: "default",
      });
    });
  });

  it("closes the local Agent SSE stream when local mode is disabled", async () => {
    const user = userEvent.setup();
    const eventSources: Array<{
      url: string;
      onmessage: ((event: MessageEvent<string>) => void) | null;
      close: ReturnType<typeof vi.fn>;
    }> = [];
    class FakeEventSource {
      onmessage: ((event: MessageEvent<string>) => void) | null = null;
      url: string;

      constructor(url: string | URL) {
        this.url = String(url);
        eventSources.push(this);
      }

      close = vi.fn();
    }
    vi.stubGlobal("EventSource", FakeEventSource);
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents" && method === "GET") return jsonResponse(agentsPage());
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
        return jsonResponse({ items: [localConnection()] });
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
        return jsonResponse(localBinding(), 201);
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
      if (path === "/api/agents/local-agent/bindings/binding-1/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
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

    const { queryClient } = renderPage(fetchMock);

    await chooseWorkspaceTarget(user, /hao Local/);
    await screen.findByText("Session session-1");
    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "触发本地流");
    await user.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => expect(eventSources.length).toBe(1));

    await user.click(screen.getByRole("button", { name: "关闭本地 Agent" }));

    expect(eventSources[0].close).toHaveBeenCalledTimes(1);
  });

  it("shows local send failures without a dead generic Retry action", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents" && method === "GET") return jsonResponse(agentsPage());
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
        return jsonResponse({ items: [localConnection()] });
      }
      if (
        path === "/api/agents/local-agent/connections/conn-local-1/bindings" &&
        method === "GET"
      ) {
        return jsonResponse({ items: [localBinding()] });
      }
      if (path === "/api/agents/sessions/session-1/messages" && method === "GET") {
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path === "/api/agents/local-agent/bindings/binding-1/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/agents/local-agent/bindings/binding-1/messages" && method === "POST") {
        return jsonResponse({ detail: "bridge offline" }, 500);
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    renderPage(fetchMock);

    await chooseWorkspaceTarget(user, /hao Local/);
    await screen.findByText("Session session-1");

    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "本地发送失败");
    await user.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText(/bridge offline|HTTP 500/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /重试|Retry/ })).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          requestPath(input) === "/api/agents/default/runs/chat/stream" &&
          init?.method === "POST",
      ),
    ).toBe(false);
  });

  it("keeps an in-progress local Agent draft when message polling hydrates the conversation", async () => {
    const user = userEvent.setup();
    let messageListReads = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents" && method === "GET") return jsonResponse(agentsPage());
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
              onboarding_confirmed: true,
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
        messageListReads += 1;
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path === "/api/agents/local-agent/bindings/binding-1/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    const { queryClient } = renderPage(fetchMock);

    await chooseWorkspaceTarget(user, /hao Local/);
    await screen.findByText("Session session-1");
    await waitFor(() => expect(messageListReads).toBeGreaterThan(0));

    const composer = screen.getByPlaceholderText("直接与智能体对话");
    await user.type(composer, "这段输入不要被轮询清掉");
    expect(composer).toHaveValue("这段输入不要被轮询清掉");

    await act(async () => {
      await queryClient.refetchQueries({
        queryKey: ["agent-session-messages", "session-1"],
      });
    });

    await waitFor(() => expect(messageListReads).toBeGreaterThan(1));
    expect(composer).toHaveValue("这段输入不要被轮询清掉");
  });

  it("keeps the selected history conversation when local Agent polling refreshes", async () => {
    const user = userEvent.setup();
    let bindingPostCount = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents" && method === "GET") return jsonResponse(agentsPage());
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
        return jsonResponse({ items: [localConnection()] });
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
        bindingPostCount += 1;
        if (bindingPostCount === 1) {
          return jsonResponse(localBinding(), 201);
        }
        return jsonResponse(
          localBinding({
            id: "binding-2",
            connection_id: "conn-local-1",
            agent_session_id: "session-2",
          }),
          201,
        );
      }
      if (path === "/api/agents/sessions/session-1/messages" && method === "GET") {
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path === "/api/agents/sessions/session-2/messages" && method === "GET") {
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path === "/api/agents/local-agent/bindings/binding-1/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/agents/local-agent/bindings/binding-2/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    const { queryClient } = renderPage(fetchMock);

    await chooseWorkspaceTarget(user, /hao Local/);
    await screen.findByText("Session session-1");
    await waitFor(() => {
      expect(
        useWorkspaceStore
          .getState()
          .conversations.some((conversation) => conversation.id === "local-agent:binding-1"),
      ).toBe(true);
    });
    expect(useWorkspaceStore.getState().currentConversationId).toBe("local-agent:binding-1");

    await user.click(screen.getByRole("button", { name: "新建对话" }));
    await waitFor(() => {
      expect(useWorkspaceStore.getState().currentConversationId).toBe("local-agent:binding-2");
    });
    const selectedConversationId = useWorkspaceStore.getState().currentConversationId;

    await act(async () => {
      queryClient.setQueryData(["agent-session-messages", "session-1"], {
        items: [
          {
            id: "message-user-polled",
            session_id: "session-1",
            agent_id: "default",
            role: "user",
            content: "轮询同步的新消息",
            metadata_json: {
              source: "local_agent",
              connection_id: "conn-local-1",
              binding_id: "binding-1",
              agent_session_id: "session-1",
              client_message_id: "local-polled",
            },
            created_at: "2026-05-24T00:00:02Z",
          },
        ],
        next_cursor: null,
      });
    });

    await waitFor(() => {
      expect(useWorkspaceStore.getState().currentConversationId).toBe(selectedConversationId);
    });
  });

  it("defaults to the stable hao local connection when API heartbeat order changes", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents" && method === "GET") return jsonResponse(agentsPage());
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
            localConnection({
              id: "conn-hao-old",
              display_name: "hao Local",
              adapter_kind: "hao",
              status: "offline",
              updated_at: "2026-05-24T00:00:30Z",
              created_at: "2026-05-23T00:00:01Z",
            }),
            localConnection({
              id: "conn-codex",
              display_name: "Codex CLI",
              adapter_kind: "codex",
              updated_at: "2026-05-24T00:00:30Z",
              created_at: "2026-05-24T00:00:01Z",
            }),
            localConnection({
              id: "conn-hao",
              display_name: "hao Local",
              adapter_kind: "hao",
              status: "busy",
              updated_at: "2026-05-24T00:00:01Z",
              created_at: "2026-05-24T00:00:02Z",
            }),
          ],
        });
      }
      if (path === "/api/agents/local-agent/connections/conn-hao/bindings" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/agents/local-agent/connections/conn-hao/bindings" && method === "POST") {
        return jsonResponse(
              localBinding({
                id: "binding-hao",
                connection_id: "conn-hao",
                agent_session_id: "session-hao",
              }),
          201,
        );
      }
      if (path === "/api/agents/sessions/session-hao/messages" && method === "GET") {
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path === "/api/agents/local-agent/bindings/binding-hao/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    renderPage(fetchMock);

    await screen.findByRole("button", {
      name: /切换智能体或本地 Agent：Default Agent/,
    });
    await user.click(await screen.findByRole("button", { name: "启用本地 Agent" }));
    await screen.findByText(/^Session session-/);

    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          requestPath(input) === "/api/agents/local-agent/connections/conn-hao/bindings" &&
          init?.method === "POST",
      ),
    ).toBe(true);
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          requestPath(input) === "/api/agents/local-agent/connections/conn-codex/bindings" &&
          init?.method === "POST",
      ),
    ).toBe(false);
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          requestPath(input) === "/api/agents/local-agent/connections/conn-hao-old/bindings" &&
          init?.method === "POST",
      ),
    ).toBe(false);
  });

  it("does not treat pending-confirmation local connections as Workspace targets", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents" && method === "GET") return jsonResponse(agentsPage());
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
            localConnection({
              id: "conn-codex-pending",
              display_name: "Codex Pending",
              adapter_kind: "codex",
              status: "pending_confirmation",
              onboarding_confirmed: true,
            }),
            localConnection({
              id: "conn-hao",
              display_name: "hao Local",
              adapter_kind: "hao",
              status: "online",
              onboarding_confirmed: true,
            }),
          ],
        });
      }
      if (path === "/api/agents/local-agent/connections/conn-hao/bindings" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/agents/local-agent/connections/conn-hao/bindings" && method === "POST") {
        return jsonResponse(
              localBinding({
                id: "binding-hao",
                connection_id: "conn-hao",
                agent_session_id: "session-hao",
              }),
          201,
        );
      }
      if (path === "/api/agents/sessions/session-hao/messages" && method === "GET") {
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path === "/api/agents/local-agent/bindings/binding-hao/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    renderPage(fetchMock);

    await user.click(await screen.findByRole("button", { name: "启用本地 Agent" }));
    await screen.findByText(/^Session session-/);

    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          requestPath(input) === "/api/agents/local-agent/connections/conn-hao/bindings" &&
          init?.method === "POST",
      ),
    ).toBe(true);
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          requestPath(input) === "/api/agents/local-agent/connections/conn-codex-pending/bindings" &&
          init?.method === "POST",
      ),
    ).toBe(false);
    await user.click(
      await screen.findByRole("button", {
        name: /切换智能体或本地 Agent：hao Local/,
      }),
    );
    expect(screen.queryByRole("option", { name: /Codex Pending/ })).not.toBeInTheDocument();
  });

  it("isolates local Agent history and submit context when switching Claude Code to hao", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents" && method === "GET") return jsonResponse(agentsPage());
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
            localConnection({
              id: "conn-hao",
              display_name: "hao Local",
              adapter_kind: "hao",
              created_at: "2026-05-24T00:00:01Z",
            }),
            localConnection({
              id: "conn-claude",
              display_name: "Claude Code",
              adapter_kind: "claude_code",
              created_at: "2026-05-24T00:00:02Z",
            }),
          ],
        });
      }
      if (
        path === "/api/agents/local-agent/connections/conn-claude/bindings" &&
        method === "GET"
      ) {
        return jsonResponse({
          items: [
              localBinding({
                id: "binding-claude",
                connection_id: "conn-claude",
                agent_session_id: "session-claude",
              }),
          ],
        });
      }
      if (path === "/api/agents/sessions/session-claude/messages" && method === "GET") {
        return jsonResponse({
          items: [
            {
              id: "message-claude-user",
              session_id: "session-claude",
              agent_id: "default",
              role: "user",
              content: "CLAUDE_SECRET_CONTEXT",
              metadata_json: {
                source: "local_agent",
                connection_id: "conn-claude",
                binding_id: "binding-claude",
                agent_session_id: "session-claude",
                client_message_id: "client-claude-1",
              },
              created_at: "2026-05-24T00:00:02Z",
            },
            {
              id: "message-claude-assistant",
              session_id: "session-claude",
              agent_id: "default",
              role: "assistant",
              content: "Claude previous answer",
              metadata_json: {
                source: "local_agent",
                connection_id: "conn-claude",
                binding_id: "binding-claude",
                agent_session_id: "session-claude",
                bridge_task_id: "bridge-task-claude-1",
                input_tokens: 777,
                output_tokens: 333,
              },
              created_at: "2026-05-24T00:00:03Z",
            },
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/local-agent/bindings/binding-claude/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/agents/local-agent/bindings/binding-claude/messages" && method === "POST") {
        return jsonResponse(
          {
            bridge_task_id: "bridge-task-claude-2",
            run_id: "run-claude-2",
            agent_session_id: "session-claude",
            user_message_id: "message-claude-2",
            status: "pending",
          },
          202,
        );
      }
      if (path === "/api/agents/local-agent/connections/conn-hao/bindings" && method === "GET") {
        return jsonResponse({
          items: [
              localBinding({
                id: "binding-hao",
                connection_id: "conn-hao",
                agent_session_id: "session-hao",
              }),
          ],
        });
      }
      if (path === "/api/agents/sessions/session-hao/messages" && method === "GET") {
        return jsonResponse({
          items: [
            {
              id: "message-hao-user",
              session_id: "session-hao",
              agent_id: "default",
              role: "user",
              content: "HAO_ONLY_CONTEXT",
              metadata_json: {
                source: "local_agent",
                connection_id: "conn-hao",
                binding_id: "binding-hao",
                agent_session_id: "session-hao",
                client_message_id: "client-hao-1",
              },
              created_at: "2026-05-24T00:00:04Z",
            },
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/local-agent/bindings/binding-hao/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/agents/local-agent/bindings/binding-hao/messages" && method === "POST") {
        return jsonResponse(
          {
            bridge_task_id: "bridge-task-hao-2",
            run_id: "run-hao-2",
            agent_session_id: "session-hao",
            user_message_id: "message-hao-2",
            status: "pending",
          },
          202,
        );
      }
      if (path === "/api/agents/runs/run-claude-2/workspace" && method === "GET") {
        return jsonResponse({
          run: { id: "run-claude-2", status: "RUNNING", created_at: now },
          events: [],
          model_calls: [],
          tool_calls: [],
          approvals: [],
        });
      }
      if (path === "/api/agents/runs/run-hao-2/workspace" && method === "GET") {
        return jsonResponse({
          run: { id: "run-hao-2", status: "RUNNING", created_at: now },
          events: [],
          model_calls: [],
          tool_calls: [],
          approvals: [],
        });
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    renderPage(fetchMock);

    await chooseWorkspaceTarget(user, /Claude Code/);
    await waitFor(() => {
      expect(screen.getAllByText("CLAUDE_SECRET_CONTEXT").length).toBeGreaterThan(0);
    });
    expect(useWorkspaceStore.getState().currentConversationId).toBe("local-agent:binding-claude");

    await chooseWorkspaceTarget(user, /hao Local/);
    await waitFor(() => {
      const state = useWorkspaceStore.getState();
      expect(state.currentConversationId).toBe("local-agent:binding-hao");
      expect(state.activePath().map((node) => node.content)).toEqual(["HAO_ONLY_CONTEXT"]);
    });
    expect(within(screen.getByRole("group", { name: "user-messages" })).getByText("HAO_ONLY_CONTEXT")).toBeInTheDocument();
    expect(
      within(screen.getByRole("group", { name: "user-messages" })).queryByText("CLAUDE_SECRET_CONTEXT"),
    ).not.toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "hao new question");
    await user.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => {
      const sendCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/agents/local-agent/bindings/binding-hao/messages" &&
          init?.method === "POST",
      );
      const body = JSON.parse(String(sendCall?.[1]?.body));
      expect(body).toMatchObject({
        content: "hao new question",
        active_leaf_id: "local-msg:message-hao-user",
        active_branch_id: "local-msg:message-hao-user",
      });
      expect(JSON.stringify(body.messages)).toContain("HAO_ONLY_CONTEXT");
      expect(JSON.stringify(body.messages)).not.toContain("CLAUDE_SECRET_CONTEXT");
      expect(JSON.stringify(body.messages)).not.toContain("binding-claude");
      expect(JSON.stringify(body.messages)).not.toContain("conn-claude");
    });
    const haoPendingAssistant = useWorkspaceStore
      .getState()
      .activePath()
      .find((node) => node.role === "assistant" && node.metadata.orchestration?.binding_id === "binding-hao");
    expect(haoPendingAssistant?.metadata.input_tokens).toBeGreaterThan(
      Math.ceil("hao new question".length / 4),
    );
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          requestPath(input) === "/api/agents/local-agent/bindings/binding-claude/messages" &&
          init?.method === "POST",
      ),
    ).toBe(false);

    await chooseWorkspaceTarget(user, /Claude Code/);
    await waitFor(() => {
      const state = useWorkspaceStore.getState();
      expect(state.currentConversationId).toBe("local-agent:binding-claude");
      expect(state.activePath().map((node) => node.content)).toEqual([
        "CLAUDE_SECRET_CONTEXT",
        "Claude previous answer",
      ]);
    });
    expect(within(screen.getByRole("group", { name: "user-messages" })).getByText("CLAUDE_SECRET_CONTEXT")).toBeInTheDocument();
    expect(screen.getByText("777 输入")).toBeInTheDocument();
    expect(screen.getByText("333 输出")).toBeInTheDocument();
    expect(
      within(screen.getByRole("group", { name: "user-messages" })).queryByText("HAO_ONLY_CONTEXT"),
    ).not.toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "claude followup");
    await user.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => {
      const sendCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/agents/local-agent/bindings/binding-claude/messages" &&
          init?.method === "POST",
      );
      const body = JSON.parse(String(sendCall?.[1]?.body));
      expect(body).toMatchObject({
        content: "claude followup",
        active_leaf_id: "local-msg:message-claude-assistant",
        active_branch_id: "local-msg:message-claude-assistant",
      });
      expect(JSON.stringify(body.messages)).toContain("CLAUDE_SECRET_CONTEXT");
      expect(JSON.stringify(body.messages)).not.toContain("HAO_ONLY_CONTEXT");
      expect(JSON.stringify(body.messages)).not.toContain("binding-hao");
      expect(JSON.stringify(body.messages)).not.toContain("conn-hao");
    });
  });

  it("ignores stale local Agent send responses after switching local connections", async () => {
    const user = userEvent.setup();
    const firstSend = deferred<Response>();
    const eventSources: Array<{ url: string; close: () => void }> = [];
    class FakeEventSource {
      url: string;

      constructor(url: string | URL) {
        this.url = String(url);
        eventSources.push(this);
      }

      close = vi.fn();
    }
    vi.stubGlobal("EventSource", FakeEventSource);
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents" && method === "GET") return jsonResponse(agentsPage());
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
            localConnection({
              id: "conn-local-a",
              display_name: "Local A",
              created_at: "2026-05-24T00:00:01Z",
            }),
            localConnection({
              id: "conn-local-b",
              display_name: "Local B",
              created_at: "2026-05-24T00:00:02Z",
            }),
          ],
        });
      }
      if (
        path === "/api/agents/local-agent/connections/conn-local-a/bindings" &&
        method === "GET"
      ) {
        return jsonResponse({
          items: [
            localBinding({
              id: "binding-a",
              connection_id: "conn-local-a",
              agent_session_id: "session-a",
            }),
          ],
        });
      }
      if (
        path === "/api/agents/local-agent/connections/conn-local-b/bindings" &&
        method === "GET"
      ) {
        return jsonResponse({
          items: [
            localBinding({
              id: "binding-b",
              connection_id: "conn-local-b",
              agent_session_id: "session-b",
            }),
          ],
        });
      }
      if (path === "/api/agents/sessions/session-a/messages" && method === "GET") {
        return jsonResponse({
          items: [
            {
              id: "message-a-user",
              session_id: "session-a",
              agent_id: "default",
              role: "user",
              content: "A_CONTEXT",
              metadata_json: {
                source: "local_agent",
                connection_id: "conn-local-a",
                binding_id: "binding-a",
                agent_session_id: "session-a",
              },
              created_at: now,
            },
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/sessions/session-b/messages" && method === "GET") {
        return jsonResponse({
          items: [
            {
              id: "message-b-user",
              session_id: "session-b",
              agent_id: "default",
              role: "user",
              content: "B_CONTEXT",
              metadata_json: {
                source: "local_agent",
                connection_id: "conn-local-b",
                binding_id: "binding-b",
                agent_session_id: "session-b",
              },
              created_at: now,
            },
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/local-agent/bindings/binding-a/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/agents/local-agent/bindings/binding-b/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/agents/local-agent/bindings/binding-a/messages" && method === "POST") {
        return firstSend.promise;
      }
      if (path === "/api/agents/runs/run-a-late/workspace" && method === "GET") {
        return jsonResponse({
          run: { id: "run-a-late", status: "RUNNING", created_at: now },
          events: [],
          model_calls: [],
          tool_calls: [],
          approvals: [],
        });
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    renderPage(fetchMock);

    await chooseWorkspaceTarget(user, /Local A/);
    await waitFor(() => {
      expect(useWorkspaceStore.getState().currentConversationId).toBe("local-agent:binding-a");
    });
    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "slow local a");
    await user.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            requestPath(input) === "/api/agents/local-agent/bindings/binding-a/messages" &&
            init?.method === "POST",
        ),
      ).toBe(true);
    });

    await chooseWorkspaceTarget(user, /Local B/);
    await waitFor(() => {
      const state = useWorkspaceStore.getState();
      expect(state.currentConversationId).toBe("local-agent:binding-b");
      expect(state.activePath().map((node) => node.content)).toEqual(["B_CONTEXT"]);
    });

    await act(async () => {
      firstSend.resolve(
        jsonResponse(
          {
            bridge_task_id: "bridge-task-a-late",
            run_id: "run-a-late",
            agent_session_id: "session-a",
            user_message_id: "message-a-late",
            status: "pending",
          },
          202,
        ),
      );
      await firstSend.promise;
    });

    await waitFor(() => {
      const state = useWorkspaceStore.getState();
      expect(state.currentConversationId).toBe("local-agent:binding-b");
      expect(state.activeRunId).not.toBe("run-a-late");
      expect(state.activePath().map((node) => node.content)).toEqual(["B_CONTEXT"]);
    });
    expect(eventSources).toHaveLength(0);
  });

  it("ignores stale local Agent SSE events after switching local connections", async () => {
    const user = userEvent.setup();
    const eventSources: Array<{
      url: string;
      onmessage: ((event: MessageEvent<string>) => void) | null;
      close: ReturnType<typeof vi.fn>;
    }> = [];
    class FakeEventSource {
      onopen: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent<string>) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      url: string;
      close = vi.fn();

      constructor(url: string | URL) {
        this.url = String(url);
        eventSources.push(this);
      }
    }
    vi.stubGlobal("EventSource", FakeEventSource);
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents" && method === "GET") return jsonResponse(agentsPage());
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
            localConnection({
              id: "conn-local-a",
              display_name: "Local A",
              created_at: "2026-05-24T00:00:01Z",
            }),
            localConnection({
              id: "conn-local-b",
              display_name: "Local B",
              created_at: "2026-05-24T00:00:02Z",
            }),
          ],
        });
      }
      if (
        path === "/api/agents/local-agent/connections/conn-local-a/bindings" &&
        method === "GET"
      ) {
        return jsonResponse({
          items: [
            localBinding({
              id: "binding-a",
              connection_id: "conn-local-a",
              agent_session_id: "session-a",
            }),
          ],
        });
      }
      if (
        path === "/api/agents/local-agent/connections/conn-local-b/bindings" &&
        method === "GET"
      ) {
        return jsonResponse({
          items: [
            localBinding({
              id: "binding-b",
              connection_id: "conn-local-b",
              agent_session_id: "session-b",
            }),
          ],
        });
      }
      if (path === "/api/agents/sessions/session-a/messages" && method === "GET") {
        return jsonResponse({
          items: [
            {
              id: "message-a-user",
              session_id: "session-a",
              agent_id: "default",
              role: "user",
              content: "A_CONTEXT",
              metadata_json: {
                source: "local_agent",
                connection_id: "conn-local-a",
                binding_id: "binding-a",
                agent_session_id: "session-a",
              },
              created_at: now,
            },
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/sessions/session-b/messages" && method === "GET") {
        return jsonResponse({
          items: [
            {
              id: "message-b-user",
              session_id: "session-b",
              agent_id: "default",
              role: "user",
              content: "B_CONTEXT",
              metadata_json: {
                source: "local_agent",
                connection_id: "conn-local-b",
                binding_id: "binding-b",
                agent_session_id: "session-b",
              },
              created_at: now,
            },
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/local-agent/bindings/binding-a/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/agents/local-agent/bindings/binding-b/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/agents/local-agent/bindings/binding-a/messages" && method === "POST") {
        return jsonResponse(
          {
            bridge_task_id: "bridge-task-a",
            run_id: "run-a",
            agent_session_id: "session-a",
            user_message_id: "message-a-sent",
            status: "pending",
          },
          202,
        );
      }
      if (path === "/api/agents/local-agent/bindings/binding-b/messages" && method === "POST") {
        return jsonResponse(
          {
            bridge_task_id: "bridge-task-b",
            run_id: "run-b",
            agent_session_id: "session-b",
            user_message_id: "message-b-sent",
            status: "pending",
          },
          202,
        );
      }
      if (path === "/api/agents/runs/run-a/workspace" && method === "GET") {
        return jsonResponse({
          run: { id: "run-a", status: "RUNNING", created_at: now },
          events: [],
          model_calls: [],
          tool_calls: [],
          approvals: [],
        });
      }
      if (path === "/api/agents/runs/run-b/workspace" && method === "GET") {
        return jsonResponse({
          run: { id: "run-b", status: "RUNNING", created_at: now },
          events: [],
          model_calls: [],
          tool_calls: [],
          approvals: [],
        });
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    renderPage(fetchMock);

    await chooseWorkspaceTarget(user, /Local A/);
    await waitFor(() => {
      expect(useWorkspaceStore.getState().currentConversationId).toBe("local-agent:binding-a");
    });
    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "ask local a");
    await user.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => expect(eventSources).toHaveLength(1));
    const staleAStream = eventSources[0];

    await chooseWorkspaceTarget(user, /Local B/);
    await waitFor(() => {
      const state = useWorkspaceStore.getState();
      expect(state.currentConversationId).toBe("local-agent:binding-b");
      expect(state.activePath().map((node) => node.content)).toEqual(["B_CONTEXT"]);
    });
    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "ask local b");
    await user.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => expect(eventSources).toHaveLength(2));
    const activeBStream = eventSources[1];

    act(() => {
      staleAStream.onmessage?.(
        localAgentSseMessage(
          "LOCAL_AGENT_MESSAGE_COMPLETED",
          { bridge_task_id: "bridge-task-a" },
          { agent_run_id: "run-a" },
        ),
      );
    });

    await waitFor(() => {
      const state = useWorkspaceStore.getState();
      expect(state.currentConversationId).toBe("local-agent:binding-b");
      expect(state.activeRunId).toBe("run-b");
      expect(state.activePath().map((node) => node.content)).toEqual([
        "B_CONTEXT",
        "ask local b",
        "等待本地 Agent 响应...",
      ]);
    });
    expect(activeBStream.close).not.toHaveBeenCalled();
  });

  it("shows failed local Agent tasks as errors without keeping submit locked", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents" && method === "GET") return jsonResponse(agentsPage());
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
            localConnection({
              id: "conn-codex",
              display_name: "Codex CLI",
              adapter_kind: "codex",
            }),
          ],
        });
      }
      if (
        path === "/api/agents/local-agent/connections/conn-codex/bindings" &&
        method === "GET"
      ) {
        return jsonResponse({
          items: [
            localBinding({
              id: "binding-codex",
              connection_id: "conn-codex",
              agent_session_id: "session-codex",
            }),
          ],
        });
      }
      if (path === "/api/agents/sessions/session-codex/messages" && method === "GET") {
        return jsonResponse({
          items: [
            {
              id: "message-user-codex",
              session_id: "session-codex",
              agent_id: "default",
              role: "user",
              content: "你好",
              metadata_json: {
                source: "local_agent",
                connection_id: "conn-codex",
                binding_id: "binding-codex",
                agent_session_id: "session-codex",
                client_message_id: "client-codex-1",
              },
              created_at: "2026-05-24T00:00:02Z",
            },
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/local-agent/bindings/binding-codex/tasks" && method === "GET") {
        return jsonResponse({
          items: [
            {
              id: "bridge-task-codex",
              connection_id: "conn-codex",
              binding_id: "binding-codex",
              agent_session_id: "session-codex",
              run_id: "run-codex-failed",
              user_message_id: "message-user-codex",
              client_message_id: "client-codex-1",
              status: "failed",
              error_message: "Not inside a trusted directory",
              created_at: "2026-05-24T00:00:03Z",
              updated_at: "2026-05-24T00:00:04Z",
            },
          ],
        });
      }
      if (path === "/api/agents/local-agent/bindings/binding-codex/messages" && method === "POST") {
        return jsonResponse(
          {
            bridge_task_id: "bridge-task-codex-2",
            run_id: "run-codex-2",
            agent_session_id: "session-codex",
            user_message_id: "message-user-codex-2",
            status: "pending",
          },
          202,
        );
      }
      if (path === "/api/agents/runs/run-codex-2/workspace" && method === "GET") {
        return jsonResponse({
          run: { id: "run-codex-2", status: "RUNNING", created_at: now },
          events: [],
          model_calls: [],
          tool_calls: [],
          approvals: [],
        });
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    renderPage(fetchMock);

    await chooseWorkspaceTarget(user, /Codex CLI/);
    expect(await screen.findByText("Not inside a trusted directory")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /重试|Retry/ })).not.toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "再试一次");
    await user.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => {
      const sendCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/agents/local-agent/bindings/binding-codex/messages" &&
          init?.method === "POST",
      );
      expect(JSON.parse(String(sendCall?.[1]?.body))).toMatchObject({
        content: "再试一次",
      });
    });
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          requestPath(input) === "/api/agents/default/runs/chat/stream" &&
          init?.method === "POST",
      ),
    ).toBe(false);
  });

  it("turns the current optimistic local Agent bubble into an error when polling sees the same failed bridge task without SSE", async () => {
    const user = userEvent.setup();
    let localMessageSent = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents" && method === "GET") return jsonResponse(agentsPage());
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
        return jsonResponse({ items: [localConnection()] });
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
        return jsonResponse(localBinding(), 201);
      }
      if (path === "/api/agents/sessions/session-1/messages" && method === "GET") {
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path === "/api/agents/local-agent/bindings/binding-1/messages" && method === "POST") {
        localMessageSent = true;
        return jsonResponse(
          {
            bridge_task_id: "bridge-task-failed-after-send",
            run_id: "run-local-failed-after-send",
            agent_session_id: "session-1",
            user_message_id: "message-user-failed-after-send",
            status: "pending",
          },
          202,
        );
      }
      if (path === "/api/agents/local-agent/bindings/binding-1/tasks" && method === "GET") {
        if (!localMessageSent) return jsonResponse({ items: [] });
        return jsonResponse({
          items: [
            {
              id: "bridge-task-failed-after-send",
              connection_id: "conn-local-1",
              binding_id: "binding-1",
              agent_session_id: "session-1",
              run_id: "run-local-failed-after-send",
              user_message_id: "message-user-failed-after-send",
              client_message_id: "client-message-failed-after-send",
              status: "failed",
              error_message: "Adapter process exited before replying",
              created_at: "2026-05-24T00:00:03Z",
              updated_at: "2026-05-24T00:00:04Z",
            },
          ],
        });
      }
      if (path === "/api/agents/runs/run-local-failed-after-send/workspace" && method === "GET") {
        return jsonResponse({
          run: { id: "run-local-failed-after-send", status: "FAILED", created_at: now },
          events: [],
          model_calls: [],
          tool_calls: [],
          approvals: [],
        });
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    const { queryClient } = renderPage(fetchMock);

    await chooseWorkspaceTarget(user, /hao Local/);
    await screen.findByText("Session session-1");
    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "会失败");
    await user.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            requestPath(input) === "/api/agents/local-agent/bindings/binding-1/messages" &&
            init?.method === "POST",
        ),
      ).toBe(true);
    });
    await act(async () => {
      await queryClient.refetchQueries({
        queryKey: ["local-agent-binding-tasks", "binding-1"],
      });
    });

    expect(await screen.findByText("Adapter process exited before replying")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /重试|Retry/ })).not.toBeInTheDocument();
    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "继续");
    expect(screen.getByRole("button", { name: "发送" })).not.toBeDisabled();
  });

  it("switches Agents from the top-left Workspace header", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents" && method === "GET") return jsonResponse(agentsPage());
      if (path === "/api/agents/default" && method === "GET") return jsonResponse(agent());
      if (path === "/api/agents/researcher" && method === "GET") {
        return jsonResponse(researcherAgent());
      }
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
        return jsonResponse({ items: [], next_cursor: null });
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    renderPage(fetchMock);

    await user.click(
      await screen.findByRole("button", {
        name: /切换智能体或本地 Agent：Default Agent/,
      }),
    );
    await user.click(await screen.findByRole("option", { name: /Research Agent/ }));

    expect(
      await screen.findByRole("button", {
        name: /切换智能体或本地 Agent：Research Agent/,
      }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([input]) => requestPath(input) === "/api/agents/researcher"),
      ).toBe(true);
    });
  });

  it("labels Claude Code permission bridge and surfaces local-tool approval pending state", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents" && method === "GET") return jsonResponse(agentsPage());
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
              id: "conn-claude-v6",
              agent_id: "default",
              owner_user_id: "dev-user",
              onboarding_confirmed: true,
              display_name: "Claude Code",
              adapter_kind: "claude_code",
              protocol_version: "local-agent-v1",
              bridge_version: "0.1.0",
              status: "online",
              workspace_root: ".../agent_workspace/harness",
              capabilities_json: {
                permission_bridge: "harness_local_tool_request_v1",
                permission_bridge_execution: "harness_owned_executor",
                sdk_native_tool_execution_enabled: false,
                supports_resume: false,
                supports_streaming: true,
              },
              risk_capabilities_json: ["host_write_approval_required"],
              last_seen_at: now,
              revoked_at: null,
              created_at: now,
              updated_at: now,
            },
          ],
        });
      }
      if (
        path === "/api/agents/local-agent/connections/conn-claude-v6/bindings" &&
        method === "GET"
      ) {
        return jsonResponse({ items: [] });
      }
      if (
        path === "/api/agents/local-agent/connections/conn-claude-v6/bindings" &&
        method === "POST"
      ) {
        return jsonResponse(
          {
            id: "binding-v6",
            connection_id: "conn-claude-v6",
            agent_id: "default",
            agent_session_id: "session-v6",
            adapter_session_id: null,
            resume_mode: "context_replay_new_session",
            status: "active",
            created_at: now,
            updated_at: now,
          },
          201,
        );
      }
      if (path === "/api/agents/sessions/session-v6/messages" && method === "GET") {
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path === "/api/agents/local-agent/bindings/binding-v6/messages" && method === "POST") {
        return jsonResponse(
          {
            bridge_task_id: "bridge-task-v6",
            run_id: "run-v6",
            agent_session_id: "session-v6",
            user_message_id: "message-user-v6",
            status: "pending",
          },
          202,
        );
      }
      if (path === "/api/agents/local-agent/bindings/binding-v6/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/agents/runs/run-v6/workspace" && method === "GET") {
        return jsonResponse({
          run: { id: "run-v6", status: "WAITING_APPROVAL", created_at: now },
          events: [],
          model_calls: [],
          tool_calls: [],
          approvals: [
            {
              id: "approval-v6",
              task_id: "run-v6",
              tool_call_id: "tool-v6",
              organization_id: "dev-org",
              requested_by: "dev-user",
              decided_by: null,
              status: "PENDING",
              risk_level: "high",
              reason: "local host side-effect tools require Harness approval",
              request_json: {},
              decision_json: {},
              created_at: now,
              decided_at: null,
            },
          ],
        });
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    renderPage(fetchMock);

    await user.click(
      await screen.findByRole("button", {
        name: /切换智能体或本地 Agent：Default Agent/,
      }),
    );
    expect(
      await screen.findByRole("option", {
        name: /Claude Code.*权限桥/,
      }),
    ).toBeInTheDocument();
    await user.click(await screen.findByRole("option", { name: /Claude Code.*权限桥/ }));
    expect(
      await screen.findByRole("button", {
        name: /切换智能体或本地 Agent：Claude Code/,
      }),
    ).toBeInTheDocument();
    await screen.findByText("Session session-v6");

    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "写入一份本地文件");
    await user.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => {
      const sendCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/agents/local-agent/bindings/binding-v6/messages" &&
          init?.method === "POST",
      );
      expect(JSON.parse(String(sendCall?.[1]?.body))).toMatchObject({
        content: "写入一份本地文件",
      });
    });
    expect((await screen.findAllByText(/等待 Claude Code 本地工具审批/)).length).toBeGreaterThan(0);
    const approvalLink = screen
      .getAllByRole("link", { name: "运行详情" })
      .find((link) => link.getAttribute("href") === "/runs/run-v6#approvals");
    expect(approvalLink).toBeDefined();
  });

  it("does not let stale local Agent pending state block cloud Agent submit after switching back", async () => {
    const user = userEvent.setup();
    let localMessageSent = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents" && method === "GET") return jsonResponse(agentsPage());
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
        return jsonResponse({ items: [localConnection()] });
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
        return jsonResponse(localBinding(), 201);
      }
      if (path === "/api/agents/sessions/session-1/messages" && method === "GET") {
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path === "/api/agents/local-agent/bindings/binding-1/messages" && method === "POST") {
        localMessageSent = true;
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
      if (path === "/api/agents/local-agent/bindings/binding-1/tasks" && method === "GET") {
        if (!localMessageSent) return jsonResponse({ items: [] });
        return jsonResponse({
          items: [
            {
              id: "bridge-task-1",
              connection_id: "conn-local-1",
              binding_id: "binding-1",
              agent_session_id: "session-1",
              run_id: "run-local-1",
              user_message_id: "message-user-1",
              client_message_id: "client-message-1",
              status: "pending",
              created_at: now,
              updated_at: now,
            },
          ],
        });
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
      if (path === "/api/agents/default/runs/chat/stream" && method === "POST") {
        return streamResponse(
          [
            sseFrame("run_created", {
              run_id: "run-cloud-1",
              status: "RUNNING",
              step_count: 0,
              message: "started",
            }),
            sseFrame("done", {
              run_id: "run-cloud-1",
              active_branch_id: "branch",
              status: "COMPLETED",
              step_count: 0,
              message: "done",
            }),
          ].join(""),
        );
      }
      if (path === "/api/agents/runs/run-cloud-1/workspace" && method === "GET") {
        return jsonResponse({
          run: { id: "run-cloud-1", status: "COMPLETED", created_at: now },
          events: [],
          model_calls: [],
          tool_calls: [],
          approvals: [],
        });
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    renderPage(fetchMock);

    await chooseWorkspaceTarget(user, /hao Local/);
    await screen.findByText("Session session-1");
    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "本地先执行");
    await user.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            requestPath(input) === "/api/agents/local-agent/bindings/binding-1/messages" &&
            init?.method === "POST",
        ),
      ).toBe(true);
    });

    await chooseWorkspaceTarget(user, /Default Agent/);
    expect(
      await screen.findByRole("button", {
        name: /切换智能体或本地 Agent：Default Agent/,
      }),
    ).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "云端继续");
    await user.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => {
      expect(useWorkspaceStore.getState().currentConversationId).not.toMatch(/^local-agent:/);
      const cloudCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/agents/default/runs/chat/stream" &&
          init?.method === "POST",
      );
      const body = JSON.parse(String(cloudCall?.[1]?.body));
      expect(body).toMatchObject({
        goal: "云端继续",
      });
      expect(JSON.stringify(body.messages)).not.toContain("本地先执行");
      expect(JSON.stringify(body.messages)).not.toContain("binding-1");
      expect(JSON.stringify(body.messages)).not.toContain("conn-local-1");
    });
  });

  it("blocks sending to the previous local binding while a new local Agent conversation is being created", async () => {
    const user = userEvent.setup();
    let bindingPostCount = 0;
    let binding2Created = false;
    const secondBinding = deferred<Response>();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents" && method === "GET") return jsonResponse(agentsPage());
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
        return jsonResponse({ items: [localConnection()] });
      }
      if (
        path === "/api/agents/local-agent/connections/conn-local-1/bindings" &&
        method === "GET"
      ) {
        return jsonResponse({
          items: binding2Created
            ? [
                localBinding({
                  id: "binding-2",
                  connection_id: "conn-local-1",
                  agent_session_id: "session-2",
                }),
                localBinding(),
              ]
            : [localBinding()],
        });
      }
      if (
        path === "/api/agents/local-agent/connections/conn-local-1/bindings" &&
        method === "POST"
      ) {
        bindingPostCount += 1;
        return secondBinding.promise;
      }
      if (path === "/api/agents/sessions/session-1/messages" && method === "GET") {
        return jsonResponse({
          items: [
            {
              id: "message-old-user",
              session_id: "session-1",
              agent_id: "default",
              role: "user",
              content: "OLD_LOCAL_CONTEXT",
              metadata_json: {
                source: "local_agent",
                connection_id: "conn-local-1",
                binding_id: "binding-1",
                agent_session_id: "session-1",
                client_message_id: "client-old",
              },
              created_at: now,
            },
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/sessions/session-2/messages" && method === "GET") {
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path === "/api/agents/local-agent/bindings/binding-1/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/agents/local-agent/bindings/binding-2/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/agents/local-agent/bindings/binding-1/messages" && method === "POST") {
        return jsonResponse({ detail: "old binding must not receive the new message" }, 500);
      }
      if (path === "/api/agents/local-agent/bindings/binding-2/messages" && method === "POST") {
        return jsonResponse(
          {
            bridge_task_id: "bridge-task-2",
            run_id: "run-local-2",
            agent_session_id: "session-2",
            user_message_id: "message-user-2",
            status: "pending",
          },
          202,
        );
      }
      if (path === "/api/agents/runs/run-local-2/workspace" && method === "GET") {
        return jsonResponse({
          run: { id: "run-local-2", status: "RUNNING", created_at: now },
          events: [],
          model_calls: [],
          tool_calls: [],
          approvals: [],
        });
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    renderPage(fetchMock);

    await chooseWorkspaceTarget(user, /hao Local/);
    await waitFor(() => {
      expect(useWorkspaceStore.getState().currentConversationId).toBe("local-agent:binding-1");
    });
    expect((await screen.findAllByText("OLD_LOCAL_CONTEXT")).length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "新建对话" }));
    await waitFor(() => {
      expect(bindingPostCount).toBe(1);
    });
    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "fresh local question");
    expect(screen.getByRole("button", { name: "发送" })).toBeDisabled();
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          requestPath(input) === "/api/agents/local-agent/bindings/binding-1/messages" &&
          init?.method === "POST",
      ),
    ).toBe(false);

    await act(async () => {
      binding2Created = true;
      secondBinding.resolve(
        jsonResponse(
          localBinding({
            id: "binding-2",
            connection_id: "conn-local-1",
            agent_session_id: "session-2",
          }),
          201,
        ),
      );
      await secondBinding.promise;
    });
    await waitFor(() => {
      expect(useWorkspaceStore.getState().currentConversationId).toBe("local-agent:binding-2");
    });
    await user.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => {
      const sendCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/agents/local-agent/bindings/binding-2/messages" &&
          init?.method === "POST",
      );
      const body = JSON.parse(String(sendCall?.[1]?.body));
      expect(body).toMatchObject({
        content: "fresh local question",
        workspace_context_provided: true,
      });
      expect(JSON.stringify(body.messages)).not.toContain("OLD_LOCAL_CONTEXT");
      expect(JSON.stringify(body.messages)).not.toContain("binding-1");
    });
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          requestPath(input) === "/api/agents/local-agent/bindings/binding-1/messages" &&
          init?.method === "POST",
      ),
    ).toBe(false);
  });

  it("ignores stale local Agent binding responses after switching local connections", async () => {
    const user = userEvent.setup();
    const firstBinding = deferred<Response>();
    const secondBinding = deferred<Response>();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents" && method === "GET") return jsonResponse(agentsPage());
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
            localConnection({ id: "conn-local-a", display_name: "Local A" }),
            localConnection({ id: "conn-local-b", display_name: "Local B" }),
          ],
        });
      }
      if (
        path === "/api/agents/local-agent/connections/conn-local-a/bindings" &&
        method === "GET"
      ) {
        return jsonResponse({ items: [] });
      }
      if (
        path === "/api/agents/local-agent/connections/conn-local-b/bindings" &&
        method === "GET"
      ) {
        return jsonResponse({ items: [] });
      }
      if (
        path === "/api/agents/local-agent/connections/conn-local-a/bindings" &&
        method === "POST"
      ) {
        return firstBinding.promise;
      }
      if (
        path === "/api/agents/local-agent/connections/conn-local-b/bindings" &&
        method === "POST"
      ) {
        return secondBinding.promise;
      }
      if (path === "/api/agents/sessions/session-b/messages" && method === "GET") {
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path === "/api/agents/local-agent/bindings/binding-b/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/agents/local-agent/bindings/binding-b/messages" && method === "POST") {
        return jsonResponse(
          {
            bridge_task_id: "bridge-task-b",
            run_id: "run-local-b",
            agent_session_id: "session-b",
            user_message_id: "message-user-b",
            status: "pending",
          },
          202,
        );
      }
      if (path === "/api/agents/runs/run-local-b/workspace" && method === "GET") {
        return jsonResponse({
          run: { id: "run-local-b", status: "RUNNING", created_at: now },
          events: [],
          model_calls: [],
          tool_calls: [],
          approvals: [],
        });
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    renderPage(fetchMock);

    await screen.findByRole("button", {
      name: /切换智能体或本地 Agent：Default Agent/,
    });
    await user.click(await screen.findByRole("button", { name: "启用本地 Agent" }));
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            requestPath(input) ===
              "/api/agents/local-agent/connections/conn-local-a/bindings" &&
            init?.method === "POST",
        ),
      ).toBe(true);
    });

    await chooseWorkspaceTarget(user, /Local B/);
    await act(async () => {
      firstBinding.resolve(
        jsonResponse(
          localBinding({
            id: "binding-a",
            connection_id: "conn-local-a",
            agent_session_id: "session-a",
          }),
          201,
        ),
      );
    });

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            requestPath(input) ===
              "/api/agents/local-agent/connections/conn-local-b/bindings" &&
            init?.method === "POST",
        ),
      ).toBe(true);
    });
    expect(screen.queryByText("Session session-a")).not.toBeInTheDocument();

    await act(async () => {
      secondBinding.resolve(
        jsonResponse(
          localBinding({
            id: "binding-b",
            connection_id: "conn-local-b",
            agent_session_id: "session-b",
          }),
          201,
        ),
      );
    });
    await screen.findByText("Session session-b");

    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "发给第二个本地连接");
    await user.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => {
      const sendCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/agents/local-agent/bindings/binding-b/messages" &&
          init?.method === "POST",
      );
      expect(JSON.parse(String(sendCall?.[1]?.body))).toMatchObject({
        content: "发给第二个本地连接",
      });
    });
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          requestPath(input) === "/api/agents/local-agent/bindings/binding-a/messages" &&
          init?.method === "POST",
      ),
    ).toBe(false);
  });

  it("keeps Claude Code and hao local conversations isolated when switching targets", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents" && method === "GET") return jsonResponse(agentsPage());
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
            localConnection({
              id: "conn-hao",
              display_name: "hao Local",
              adapter_kind: "hao",
            }),
            localConnection({
              id: "conn-claude",
              display_name: "Claude Code",
              adapter_kind: "claude_code",
              capabilities_json: {
                supports_resume: false,
                supports_streaming: true,
                permission_bridge: "harness_local_tool_request_v1",
                permission_bridge_execution: "harness_owned_executor",
                sdk_native_tool_execution_enabled: false,
              },
            }),
          ],
        });
      }
      if (
        path === "/api/agents/local-agent/connections/conn-hao/bindings" &&
        method === "GET"
      ) {
        return jsonResponse({
          items: [
            localBinding({
              id: "binding-hao",
              connection_id: "conn-hao",
              agent_session_id: "session-h",
              updated_at: "2026-05-24T00:01:00Z",
            }),
          ],
        });
      }
      if (
        path === "/api/agents/local-agent/connections/conn-claude/bindings" &&
        method === "GET"
      ) {
        return jsonResponse({
          items: [
            localBinding({
              id: "binding-claude",
              connection_id: "conn-claude",
              agent_session_id: "session-c",
              resume_mode: "context_replay_new_session",
              updated_at: "2026-05-24T00:02:00Z",
            }),
          ],
        });
      }
      if (
        path === "/api/agents/local-agent/connections/conn-hao/bindings" &&
        method === "POST"
      ) {
        return jsonResponse({ detail: "hao binding should be reused" }, 500);
      }
      if (
        path === "/api/agents/local-agent/connections/conn-claude/bindings" &&
        method === "POST"
      ) {
        return jsonResponse({ detail: "claude binding should be reused" }, 500);
      }
      if (path === "/api/agents/sessions/session-h/messages" && method === "GET") {
        return jsonResponse({
          items: [
            {
              id: "hao-user-1",
              session_id: "session-h",
              agent_id: "default",
              role: "user",
              content: "HAO_CONTEXT",
              metadata_json: {
                source: "local_agent",
                connection_id: "conn-hao",
                binding_id: "binding-hao",
                agent_session_id: "session-h",
              },
              created_at: "2026-05-24T00:01:00Z",
            },
            {
              id: "hao-assistant-1",
              session_id: "session-h",
              agent_id: "default",
              role: "assistant",
              content: "HAO_REPLY",
              metadata_json: {
                source: "local_agent",
                connection_id: "conn-hao",
                binding_id: "binding-hao",
                agent_session_id: "session-h",
              },
              created_at: "2026-05-24T00:01:10Z",
            },
            {
              id: "hao-stale-source-only",
              session_id: "session-h",
              agent_id: "default",
              role: "user",
              content: "STALE_SOURCE_ONLY_HAO_CONTEXT",
              metadata_json: {
                source: "local_agent",
              },
              created_at: "2026-05-24T00:01:20Z",
            },
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/sessions/session-c/messages" && method === "GET") {
        return jsonResponse({
          items: [
            {
              id: "claude-user-1",
              session_id: "session-c",
              agent_id: "default",
              role: "user",
              content: "CLAUDE_CONTEXT",
              metadata_json: {
                source: "local_agent",
                connection_id: "conn-claude",
                binding_id: "binding-claude",
                agent_session_id: "session-c",
              },
              created_at: "2026-05-24T00:02:00Z",
            },
            {
              id: "claude-assistant-1",
              session_id: "session-c",
              agent_id: "default",
              role: "assistant",
              content: "CLAUDE_REPLY",
              metadata_json: {
                source: "local_agent",
                connection_id: "conn-claude",
                binding_id: "binding-claude",
                agent_session_id: "session-c",
              },
              created_at: "2026-05-24T00:02:10Z",
            },
            {
              id: "claude-stale-source-only",
              session_id: "session-c",
              agent_id: "default",
              role: "user",
              content: "STALE_SOURCE_ONLY_CLAUDE_CONTEXT",
              metadata_json: {
                source: "local_agent",
              },
              created_at: "2026-05-24T00:02:20Z",
            },
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/local-agent/bindings/binding-hao/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/agents/local-agent/bindings/binding-claude/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/agents/local-agent/bindings/binding-hao/messages" && method === "POST") {
        return jsonResponse(
          {
            bridge_task_id: "bridge-task-hao",
            run_id: "run-hao",
            agent_session_id: "session-h",
            user_message_id: "hao-user-2",
            status: "pending",
          },
          202,
        );
      }
      if (
        path === "/api/agents/local-agent/bindings/binding-claude/messages" &&
        method === "POST"
      ) {
        return jsonResponse(
          {
            bridge_task_id: "bridge-task-claude",
            run_id: "run-claude",
            agent_session_id: "session-c",
            user_message_id: "claude-user-2",
            status: "pending",
          },
          202,
        );
      }
      if (
        (path === "/api/agents/runs/run-hao/workspace" ||
          path === "/api/agents/runs/run-claude/workspace") &&
        method === "GET"
      ) {
        return jsonResponse({
          run: {
            id: path.includes("run-hao") ? "run-hao" : "run-claude",
            status: "RUNNING",
            created_at: now,
          },
          events: [],
          model_calls: [],
          tool_calls: [],
          approvals: [],
        });
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    renderPage(fetchMock);

    await chooseWorkspaceTarget(user, /Claude Code/);
    await screen.findByText("Session session-c");
    await waitFor(() => {
      const activeText = useWorkspaceStore
        .getState()
        .activePath()
        .map((node) => node.content)
        .join("\n");
      expect(activeText).toContain("CLAUDE_CONTEXT");
      expect(activeText).not.toContain("HAO_CONTEXT");
      expect(activeText).not.toContain("STALE_SOURCE_ONLY_CLAUDE_CONTEXT");
      expect(activeText).not.toContain("STALE_SOURCE_ONLY_HAO_CONTEXT");
    });

    await chooseWorkspaceTarget(user, /hao Local/);
    await screen.findByText("Session session-h");
    await waitFor(() => {
      const activeText = useWorkspaceStore
        .getState()
        .activePath()
        .map((node) => node.content)
        .join("\n");
      expect(activeText).toContain("HAO_CONTEXT");
      expect(activeText).not.toContain("CLAUDE_CONTEXT");
      expect(activeText).not.toContain("STALE_SOURCE_ONLY_HAO_CONTEXT");
      expect(activeText).not.toContain("STALE_SOURCE_ONLY_CLAUDE_CONTEXT");
    });

    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "hao follow-up");
    await user.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => {
      const haoSend = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/agents/local-agent/bindings/binding-hao/messages" &&
          init?.method === "POST",
      );
      const body = JSON.parse(String(haoSend?.[1]?.body));
      expect(body).toMatchObject({ content: "hao follow-up" });
      expect(JSON.stringify(body.messages)).toContain("HAO_CONTEXT");
      expect(JSON.stringify(body.messages)).not.toContain("CLAUDE_CONTEXT");
      expect(JSON.stringify(body.messages)).not.toContain("STALE_SOURCE_ONLY_HAO_CONTEXT");
      expect(JSON.stringify(body.messages)).not.toContain("STALE_SOURCE_ONLY_CLAUDE_CONTEXT");
    });

    await chooseWorkspaceTarget(user, /Claude Code/);
    await screen.findByText("Session session-c");
    await waitFor(() => {
      const activeText = useWorkspaceStore
        .getState()
        .activePath()
        .map((node) => node.content)
        .join("\n");
      expect(activeText).toContain("CLAUDE_CONTEXT");
      expect(activeText).not.toContain("HAO_CONTEXT");
      expect(activeText).not.toContain("STALE_SOURCE_ONLY_CLAUDE_CONTEXT");
      expect(activeText).not.toContain("STALE_SOURCE_ONLY_HAO_CONTEXT");
    });

    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "claude follow-up");
    await user.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => {
      const claudeSend = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/agents/local-agent/bindings/binding-claude/messages" &&
          init?.method === "POST",
      );
      const body = JSON.parse(String(claudeSend?.[1]?.body));
      expect(body).toMatchObject({ content: "claude follow-up" });
      expect(JSON.stringify(body.messages)).toContain("CLAUDE_CONTEXT");
      expect(JSON.stringify(body.messages)).not.toContain("HAO_CONTEXT");
      expect(JSON.stringify(body.messages)).not.toContain("STALE_SOURCE_ONLY_CLAUDE_CONTEXT");
      expect(JSON.stringify(body.messages)).not.toContain("STALE_SOURCE_ONLY_HAO_CONTEXT");
    });

    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          requestPath(input).endsWith("/connections/conn-hao/bindings") &&
          init?.method === "POST",
      ),
    ).toBe(false);
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          requestPath(input).endsWith("/connections/conn-claude/bindings") &&
          init?.method === "POST",
      ),
    ).toBe(false);
  });

  it("restores the exact local binding from persisted history when cache is cold", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(
      "harness.workspace.v3.default.conversations",
      JSON.stringify({
        version: 2,
        currentConversationId: "local-agent:binding-hao-old",
        conversations: [
          {
            id: "local-agent:binding-hao-old",
            title: "Old hao thread",
            created_at: "2026-05-24T00:00:00Z",
            updated_at: "2026-05-24T00:01:00Z",
            rootNodeId: "root",
            activeLeafId: "old-user",
            pinnedNodeIds: [],
            dismissedPlanNodeIds: [],
            draft: "",
            contextWindowTurns: 8,
            contextCompressions: {},
            nodesById: {
              root: {
                id: "root",
                parent_id: null,
                children_ids: ["old-user"],
                role: "system",
                content: "Agent Workspace Pro root",
                state: "done",
                metadata: {
                  orchestration: {
                    source: "local_agent",
                    connection_id: "conn-hao",
                    binding_id: "binding-hao-old",
                    agent_session_id: "session-h-old",
                  },
                },
                tool_calls: [],
                artifacts: [],
                created_at: "2026-05-24T00:00:00Z",
              },
              "old-user": {
                id: "old-user",
                parent_id: "root",
                children_ids: [],
                role: "user",
                content: "PERSISTED_OLD_HAO_CONTEXT",
                state: "done",
                metadata: {
                  orchestration: {
                    source: "local_agent",
                    connection_id: "conn-hao",
                    binding_id: "binding-hao-old",
                    agent_session_id: "session-h-old",
                  },
                },
                tool_calls: [],
                artifacts: [],
                created_at: "2026-05-24T00:00:10Z",
              },
            },
          },
        ],
      }),
    );
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents" && method === "GET") return jsonResponse(agentsPage());
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
            localConnection({
              id: "conn-hao",
              display_name: "hao Local",
              adapter_kind: "hao",
            }),
          ],
        });
      }
      if (
        path === "/api/agents/local-agent/connections/conn-hao/bindings" &&
        method === "GET"
      ) {
        return jsonResponse({
          items: [
            localBinding({
              id: "binding-hao-new",
              connection_id: "conn-hao",
              agent_session_id: "session-h-new",
              updated_at: "2026-05-24T00:03:00Z",
            }),
            localBinding({
              id: "binding-hao-old",
              connection_id: "conn-hao",
              agent_session_id: "session-h-old",
              updated_at: "2026-05-24T00:01:00Z",
            }),
          ],
        });
      }
      if (
        path === "/api/agents/local-agent/connections/conn-hao/bindings" &&
        method === "POST"
      ) {
        return jsonResponse({ detail: "cold-cache restore must not create a new binding" }, 500);
      }
      if (path === "/api/agents/sessions/session-h-old/messages" && method === "GET") {
        return jsonResponse({
          items: [
            {
              id: "old-user-message",
              session_id: "session-h-old",
              agent_id: "default",
              role: "user",
              content: "OLD_HAO_CONTEXT_FROM_SERVER",
              metadata_json: {
                source: "local_agent",
                connection_id: "conn-hao",
                binding_id: "binding-hao-old",
                agent_session_id: "session-h-old",
              },
              created_at: "2026-05-24T00:01:00Z",
            },
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/sessions/session-h-new/messages" && method === "GET") {
        return jsonResponse({
          items: [
            {
              id: "new-user-message",
              session_id: "session-h-new",
              agent_id: "default",
              role: "user",
              content: "WRONG_NEW_HAO_CONTEXT",
              metadata_json: {
                source: "local_agent",
                connection_id: "conn-hao",
                binding_id: "binding-hao-new",
                agent_session_id: "session-h-new",
              },
              created_at: "2026-05-24T00:03:00Z",
            },
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/local-agent/bindings/binding-hao-old/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/agents/local-agent/bindings/binding-hao-new/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/agents/local-agent/bindings/binding-hao-old/messages" && method === "POST") {
        return jsonResponse(
          {
            bridge_task_id: "bridge-task-hao-old",
            run_id: "run-hao-old",
            agent_session_id: "session-h-old",
            user_message_id: "old-user-followup",
            status: "pending",
          },
          202,
        );
      }
      if (path === "/api/agents/local-agent/bindings/binding-hao-new/messages" && method === "POST") {
        return jsonResponse({ detail: "wrong binding received the send" }, 500);
      }
      if (path === "/api/agents/runs/run-hao-old/workspace" && method === "GET") {
        return jsonResponse({
          run: { id: "run-hao-old", status: "RUNNING", created_at: now },
          events: [],
          model_calls: [],
          tool_calls: [],
          approvals: [],
        });
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    renderPage(fetchMock);

    await waitFor(() => {
      expect(
        useWorkspaceStore
          .getState()
          .conversations.some((conversation) => conversation.id === "local-agent:binding-hao-old"),
      ).toBe(true);
    });
    await chooseWorkspaceTarget(user, /hao Local/);
    await waitFor(() => {
      expect(useWorkspaceStore.getState().currentConversationId).toBe(
        "local-agent:binding-hao-old",
      );
      const activeText = useWorkspaceStore
        .getState()
        .activePath()
        .map((node) => node.content)
        .join("\n");
      expect(activeText).toContain("OLD_HAO_CONTEXT_FROM_SERVER");
      expect(activeText).not.toContain("WRONG_NEW_HAO_CONTEXT");
    });

    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "resume old hao");
    await user.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => {
      const oldSend = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/agents/local-agent/bindings/binding-hao-old/messages" &&
          init?.method === "POST",
      );
      const body = JSON.parse(String(oldSend?.[1]?.body));
      expect(body).toMatchObject({
        content: "resume old hao",
        active_leaf_id: "local-msg:old-user-message",
        active_branch_id: "local-msg:old-user-message",
      });
      expect(JSON.stringify(body.messages)).toContain("OLD_HAO_CONTEXT_FROM_SERVER");
      expect(JSON.stringify(body.messages)).not.toContain("WRONG_NEW_HAO_CONTEXT");
      expect(JSON.stringify(body.messages)).not.toContain("binding-hao-new");
      expect(JSON.stringify(body.messages)).not.toContain("session-h-new");
    });
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          requestPath(input) === "/api/agents/local-agent/bindings/binding-hao-new/messages" &&
          init?.method === "POST",
      ),
    ).toBe(false);
  });

  it("blocks local sends while target binding and messages are still switching", async () => {
    const user = userEvent.setup();
    const haoBindings = deferred<Response>();
    const haoMessages = deferred<Response>();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/agents" && method === "GET") return jsonResponse(agentsPage());
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
            localConnection({
              id: "conn-hao",
              display_name: "hao Local",
              adapter_kind: "hao",
            }),
            localConnection({
              id: "conn-claude",
              display_name: "Claude Code",
              adapter_kind: "claude_code",
              capabilities_json: {
                supports_resume: false,
                supports_streaming: true,
                permission_bridge: "harness_local_tool_request_v1",
                permission_bridge_execution: "harness_owned_executor",
                sdk_native_tool_execution_enabled: false,
              },
            }),
          ],
        });
      }
      if (
        path === "/api/agents/local-agent/connections/conn-claude/bindings" &&
        method === "GET"
      ) {
        return jsonResponse({
          items: [
            localBinding({
              id: "binding-claude",
              connection_id: "conn-claude",
              agent_session_id: "session-c",
              updated_at: "2026-05-24T00:02:00Z",
            }),
          ],
        });
      }
      if (path === "/api/agents/sessions/session-c/messages" && method === "GET") {
        return jsonResponse({
          items: [
            {
              id: "claude-user-1",
              session_id: "session-c",
              agent_id: "default",
              role: "user",
              content: "CLAUDE_CONTEXT",
              metadata_json: {
                source: "local_agent",
                connection_id: "conn-claude",
                binding_id: "binding-claude",
                agent_session_id: "session-c",
              },
              created_at: "2026-05-24T00:02:00Z",
            },
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/local-agent/bindings/binding-claude/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      if (
        path === "/api/agents/local-agent/connections/conn-hao/bindings" &&
        method === "GET"
      ) {
        return haoBindings.promise;
      }
      if (path === "/api/agents/sessions/session-h/messages" && method === "GET") {
        return haoMessages.promise;
      }
      if (path === "/api/agents/local-agent/bindings/binding-hao/tasks" && method === "GET") {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/agents/local-agent/bindings/binding-hao/messages" && method === "POST") {
        return jsonResponse(
          {
            bridge_task_id: "bridge-task-hao",
            run_id: "run-hao",
            agent_session_id: "session-h",
            user_message_id: "hao-user-2",
            status: "pending",
          },
          202,
        );
      }
      if (path === "/api/agents/runs/run-hao/workspace" && method === "GET") {
        return jsonResponse({
          run: { id: "run-hao", status: "RUNNING", created_at: now },
          events: [],
          model_calls: [],
          tool_calls: [],
          approvals: [],
        });
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    renderPage(fetchMock);

    await chooseWorkspaceTarget(user, /Claude Code/);
    await screen.findByText("Session session-c");
    await waitFor(() => {
      expect(
        useWorkspaceStore
          .getState()
          .activePath()
          .map((node) => node.content)
          .join("\n"),
      ).toContain("CLAUDE_CONTEXT");
    });

    await chooseWorkspaceTarget(user, /hao Local/);
    await screen.findByText("正在恢复 hao Local 的本地会话...");
    expect(useWorkspaceStore.getState().currentConversationId).toBe(
      "local-agent-pending:conn-hao",
    );

    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "hao during switch");
    const sendButton = screen.getByRole("button", { name: "发送" });
    expect(sendButton).toBeDisabled();
    await user.click(sendButton);
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          requestPath(input) === "/api/agents/local-agent/bindings/binding-hao/messages" &&
          init?.method === "POST",
      ),
    ).toBe(false);

    await act(async () => {
      haoBindings.resolve(
        jsonResponse({
          items: [
            localBinding({
              id: "binding-hao",
              connection_id: "conn-hao",
              agent_session_id: "session-h",
              updated_at: "2026-05-24T00:03:00Z",
            }),
          ],
        }),
      );
    });
    expect(screen.getByRole("button", { name: "发送" })).toBeDisabled();

    await act(async () => {
      haoMessages.resolve(
        jsonResponse({
          items: [
            {
              id: "hao-user-1",
              session_id: "session-h",
              agent_id: "default",
              role: "user",
              content: "HAO_CONTEXT",
              metadata_json: {
                source: "local_agent",
                connection_id: "conn-hao",
                binding_id: "binding-hao",
                agent_session_id: "session-h",
              },
              created_at: "2026-05-24T00:03:00Z",
            },
          ],
          next_cursor: null,
        }),
      );
    });

    await screen.findByText("Session session-h");
    await waitFor(() => {
      const activeText = useWorkspaceStore
        .getState()
        .activePath()
        .map((node) => node.content)
        .join("\n");
      expect(activeText).toContain("HAO_CONTEXT");
      expect(activeText).not.toContain("CLAUDE_CONTEXT");
    });

    await user.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => {
      const haoSend = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/agents/local-agent/bindings/binding-hao/messages" &&
          init?.method === "POST",
      );
      const body = JSON.parse(String(haoSend?.[1]?.body));
      expect(body).toMatchObject({ content: "hao during switch" });
      expect(JSON.stringify(body.messages)).toContain("HAO_CONTEXT");
      expect(JSON.stringify(body.messages)).not.toContain("CLAUDE_CONTEXT");
      expect(JSON.stringify(body.messages)).not.toContain("binding-claude");
      expect(JSON.stringify(body.messages)).not.toContain("conn-claude");
    });
  });
});
