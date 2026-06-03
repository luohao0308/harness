import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  AgentDefinition,
  AgentMessage,
  Team,
  TeamAgent,
  TeamEvent,
  TeamMailboxMessage,
  TeamMessageMode,
  TeamTask,
} from "../../tasks/api";
import { TeamListPage } from "../pages/TeamListPage";
import { applyTeamEventToTeam, TeamPage } from "../pages/TeamPage";

const apiBaseUrl = "http://127.0.0.1:8000";
const now = "2026-05-23T08:00:00Z";

type TeamState = {
  teams: Team[];
  nextId: number;
  lastAddAgentPayload: Record<string, unknown> | null;
  lastAgentUpdatePayload: Record<string, unknown> | null;
  lastMessagePayload: Record<string, unknown> | null;
  lastTaskPayload: Record<string, unknown> | null;
  streamBody?: string;
  streamChunks?: string[];
  streamDelayMs?: number;
  streamKeepOpen?: boolean;
  wakeStreamBody?: string;
  wakeStreamChunks?: string[];
  wakeStreamDelayMs?: number;
  wakeStreamKeepOpen?: boolean;
};

function clone<T>(payload: T): T {
  return JSON.parse(JSON.stringify(payload)) as T;
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function agentDefinition(): AgentDefinition {
  return {
    id: "default",
    name: "默认智能体",
    description: "默认入口智能体",
    role: "planner",
    status: "ACTIVE",
    model_provider: "default",
    model_name: "default",
    system_prompt: "Coordinate with team tools.",
    tools_json: ["team_send_message", "team_task_create"],
    routing_tags: ["team"],
    max_parallel_assignments: 2,
    created_at: now,
    updated_at: now,
  };
}

function teamAgent(overrides: Partial<TeamAgent>): TeamAgent {
  const slotId = overrides.slot_id ?? "leader";
  return {
    id: `${slotId}-agent`,
    team_id: "team-1",
    slot_id: slotId,
    agent_id: "default",
    role: "teammate",
    agent_name: slotId,
    status: "idle",
    model_provider: "default",
    model_name: "default",
    conversation_id: null,
    session_id: null,
    session_messages: [],
    metadata_json: {},
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function teamMessage(overrides: Partial<TeamMailboxMessage>): TeamMailboxMessage {
  const id = overrides.id ?? "message-1";
  return {
    id,
    team_id: "team-1",
    to_agent_slot_id: "product",
    from_agent_slot_id: "leader",
    type: "message",
    content: "请整理交互状态",
    summary: null,
    read: false,
    files_json: [],
    metadata_json: {},
    created_at: now,
    ...overrides,
  };
}

function agentMessage(overrides: Partial<AgentMessage>): AgentMessage {
  const id = overrides.id ?? "agent-message-1";
  return {
    id,
    session_id: "product-session",
    agent_id: "default",
    role: "user",
    content: "会话视图中的团队消息",
    metadata_json: {},
    created_at: now,
    ...overrides,
  };
}

function teamTask(overrides: Partial<TeamTask>): TeamTask {
  const id = overrides.id ?? "task-1";
  return {
    id,
    team_id: "team-1",
    subject: "实现多列 UI",
    description: "重建 Team Mode 的横向多代理列",
    owner_slot_id: "product",
    status: "in_progress",
    blocked_by_json: [],
    blocks_json: [],
    metadata_json: {},
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function teamEvent(overrides: Partial<TeamEvent>): TeamEvent {
  return {
    id: "event-1",
    team_id: "team-1",
    sequence: 1,
    event_type: "TEAM_MESSAGE_CREATED",
    payload_json: {},
    actor_type: "system",
    actor_id: null,
    created_at: now,
    ...overrides,
  };
}

function teamFixture(overrides: Partial<Team> = {}): Team {
  const leader = teamAgent({
    id: "leader-agent",
    slot_id: "leader",
    role: "leader",
    agent_name: "队长",
  });
    const product = teamAgent({
      id: "product-agent",
      slot_id: "product",
      role: "teammate",
      agent_name: "产品经理",
      session_id: "product-session",
      conversation_id: "product-session",
      session_messages: [
        agentMessage({ id: "product-user-turn", role: "user", content: "请设计团队窗口" }),
        agentMessage({
          id: "product-assistant-turn",
          role: "assistant",
          content: "会话视图中的团队消息",
          metadata_json: {
            source_run_id: "run-team-1",
            run_status: "COMPLETED",
            usage: { prompt_tokens: 10, completion_tokens: 20 },
            tool_results: [{ tool: "team_members", ok: true, result: "队长, 产品经理" }],
          },
        }),
      ],
    });
  const ui = teamAgent({
    id: "ui-agent",
    slot_id: "ui",
    role: "teammate",
    agent_name: "UI",
  });
  const task = teamTask({});
  const message = teamMessage({});
  return {
    id: "team-1",
    organization_id: "dev-org",
    name: "Team Mode 协作团队",
    status: "ACTIVE",
    workspace: "/tmp/harness-team",
    workspace_mode: "shared",
    leader_slot_id: "leader",
    created_by: "dev-user",
    agents: [leader, product, ui],
    messages: [message],
    tasks: [task],
    unread_counts: { product: 1 },
    team_tools: ["team_send_message", "team_task_create", "team_task_update", "team_members"],
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function stateFixture(): TeamState {
  return {
    teams: [teamFixture()],
    nextId: 10,
    lastAddAgentPayload: null,
    lastAgentUpdatePayload: null,
    lastMessagePayload: null,
    lastTaskPayload: null,
    streamBody: undefined,
    streamChunks: undefined,
    streamDelayMs: undefined,
    streamKeepOpen: undefined,
    wakeStreamBody: undefined,
    wakeStreamChunks: undefined,
    wakeStreamDelayMs: undefined,
    wakeStreamKeepOpen: undefined,
  };
}

function parseBody<T>(init?: RequestInit): T {
  return JSON.parse(String(init?.body ?? "{}")) as T;
}

function requestPath(input: RequestInfo | URL): string {
  const requestUrl = String(input);
  return new URL(requestUrl.startsWith("http") ? requestUrl : `${apiBaseUrl}${requestUrl}`).pathname;
}

function sseFrame(event: string, payload: Record<string, unknown>) {
  return `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`;
}

function streamResponse(frames: string | string[], signal?: AbortSignal, delayMs = 100) {
  return new Response(
    new ReadableStream({
      async start(controller) {
        const abort = () => controller.error(new DOMException("aborted", "AbortError"));
        if (signal?.aborted) {
          abort();
          return;
        }
        signal?.addEventListener("abort", abort, { once: true });
        const chunks = Array.isArray(frames) ? frames : [frames];
        try {
          for (const chunk of chunks) {
            if (signal?.aborted) return;
            controller.enqueue(new TextEncoder().encode(chunk));
            if (chunks.length > 1) {
              await new Promise((resolve) => setTimeout(resolve, delayMs));
            }
          }
          if (!signal?.aborted) controller.close();
        } finally {
          signal?.removeEventListener("abort", abort);
        }
      },
    }),
    {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    },
  );
}

function hangingStreamResponse(frames: string | string[], signal?: AbortSignal, delayMs = 100) {
  return new Response(
    new ReadableStream({
      async start(controller) {
        const abort = () => controller.error(new DOMException("aborted", "AbortError"));
        if (signal?.aborted) {
          abort();
          return;
        }
        signal?.addEventListener("abort", abort, { once: true });
        const chunks = Array.isArray(frames) ? frames : [frames];
        try {
          for (const chunk of chunks) {
            if (signal?.aborted) return;
            controller.enqueue(new TextEncoder().encode(chunk));
            if (chunks.length > 1) {
              await new Promise((resolve) => setTimeout(resolve, delayMs));
            }
          }
        } finally {
          signal?.removeEventListener("abort", abort);
        }
      },
      cancel() {
        return undefined;
      },
    }),
    {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    },
  );
}

function routeTeamApis(state: TeamState) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = requestPath(input);
    const method = init?.method ?? "GET";

    if (path === "/api/agents" && method === "GET") {
      return jsonResponse({ items: [agentDefinition()], next_cursor: null });
    }

    if (path === "/api/settings/models" && method === "GET") {
      return jsonResponse({
        default_provider: "default",
        default_model: "default",
        providers: [
          { name: "default", label: "Default", model: "default" },
          { name: "deepseek-pro", label: "DeepSeek Pro", model: "deepseek-v4-pro" },
        ],
        rate_limits: {},
        health: {},
        circuit_breaker: {},
      });
    }

    if (path === "/api/tools/registry" && method === "GET") {
      return jsonResponse({ items: [], categories: [], sources: [] });
    }

    const compressionMatch = path.match(/^\/api\/agents\/([^/]+)\/context\/compress$/);
    if (compressionMatch && method === "POST") {
      const payload = parseBody<{
        messages?: Array<{ id: string; content: string }>;
        model_provider?: string | null;
        model_name?: string | null;
      }>(init);
      const covered = (payload.messages ?? []).find((message) => message.content.trim().length > 0);
      return jsonResponse({
        status: "ok",
        cache_status: "recomputed",
        summary: "team compressed summary",
        coverage_node_ids: covered ? [covered.id] : [],
        coverage_path_hash: "d".repeat(64),
        last_covered_node_id: covered?.id ?? null,
        summary_schema_version: "workspace-context-summary-v1",
        compression_prompt_version: "workspace-context-compression-v1",
        compressor_provider: payload.model_provider ?? "default",
        compressor_model: payload.model_name ?? "default",
        estimated_original_tokens: 24,
        estimated_summary_tokens: 4,
        estimated_uncovered_tokens: 0,
        created_at: now,
        updated_at: now,
        error: null,
      });
    }

    if (path === "/api/teams" && method === "GET") {
      return jsonResponse({ items: clone(state.teams), next_cursor: null });
    }

    if (path === "/api/teams" && method === "POST") {
      const payload = parseBody<{
        name: string;
        workspace?: string;
        leader_agent_id?: string;
        leader_name?: string;
        workspace_mode: "shared" | "isolated";
        seed_messages?: AgentMessage[];
      }>(init);
      const team = teamFixture({
        id: "team-created",
        name: payload.name,
        workspace: payload.workspace ?? "",
        workspace_mode: payload.workspace_mode,
        agents: [
          teamAgent({
            id: "created-leader-agent",
            team_id: "team-created",
            slot_id: "leader",
            role: "leader",
            agent_name: payload.leader_name ?? "队长",
            session_id: "created-leader-session",
            conversation_id: "created-leader-session",
            session_messages:
              payload.seed_messages?.map((message, index) =>
                agentMessage({
                  id: `seed-${index}`,
                  session_id: "created-leader-session",
                  role: message.role,
                  content: message.content,
                  metadata_json: message.metadata_json ?? {},
                  created_at: message.created_at ?? now,
                }),
              ) ?? [],
          }),
        ],
        messages: [],
        tasks: [],
        unread_counts: {},
      });
      state.teams.unshift(team);
      return jsonResponse(clone(team), 201);
    }

    const teamMatch = path.match(/^\/api\/teams\/([^/]+)$/);
    if (teamMatch && method === "GET") {
      const team = state.teams.find((candidate) => candidate.id === teamMatch[1]);
      return team ? jsonResponse(clone(team)) : jsonResponse({ detail: "not found" }, 404);
    }

    const streamMatch = path.match(/^\/api\/teams\/([^/]+)\/stream$/);
    if (streamMatch && method === "GET") {
      if (state.streamChunks !== undefined) {
        const responseFactory = state.streamKeepOpen ? hangingStreamResponse : streamResponse;
        return responseFactory(state.streamChunks, init?.signal as AbortSignal | undefined, state.streamDelayMs);
      }
      return new Response(state.streamBody ?? "", { status: 200, headers: { "Content-Type": "text/event-stream" } });
    }

    const wakeStreamMatch = path.match(/^\/api\/teams\/([^/]+)\/agents\/([^/]+)\/wake\/stream$/);
    if (wakeStreamMatch && method === "POST") {
      const signal = init?.signal as AbortSignal | undefined;
      const team = state.teams.find((candidate) => candidate.id === wakeStreamMatch[1]);
      const agent = team?.agents.find((candidate) => candidate.slot_id === wakeStreamMatch[2]);
      if (
        team &&
        agent &&
        state.wakeStreamChunks === undefined &&
        state.wakeStreamBody === undefined
      ) {
        const finalMessage = agentMessage({
          id: `assistant-${state.nextId++}`,
          session_id: agent.session_id ?? `${agent.slot_id}-session`,
          role: "assistant",
          content: "流式最终回复",
          metadata_json: { event: "team_agent_model_response" },
        });
        agent.status = "idle";
        agent.session_messages.push(finalMessage);
        state.wakeStreamChunks = state.wakeStreamChunks ?? [
          sseFrame("status", { agent: { ...agent, status: "active", session_messages: [] } }),
          sseFrame("delta", { slot_id: agent.slot_id, content: "流式" }),
          sseFrame("delta", { slot_id: agent.slot_id, content: "回复中" }),
          sseFrame("done", { agent: { ...agent, session_messages: [] }, message: finalMessage }),
        ];
      }
      const responseFactory = state.wakeStreamKeepOpen ? hangingStreamResponse : streamResponse;
      const response = responseFactory(
        state.wakeStreamChunks ?? state.wakeStreamBody ?? "",
        signal,
        state.wakeStreamDelayMs,
      );
      if (signal?.aborted) {
        return Promise.reject(new DOMException("aborted", "AbortError"));
      }
      return response;
    }

    const cancelWakeMatch = path.match(/^\/api\/teams\/([^/]+)\/agents\/([^/]+)\/wake\/cancel$/);
    if (cancelWakeMatch && method === "POST") {
      const team = state.teams.find((candidate) => candidate.id === cancelWakeMatch[1]);
      const agent = team?.agents.find((candidate) => candidate.slot_id === cancelWakeMatch[2]);
      if (!team || !agent) return jsonResponse({ detail: "not found" }, 404);
      agent.status = "idle";
      agent.metadata_json = {
        ...agent.metadata_json,
        wake: {
          ...(agent.metadata_json.wake && typeof agent.metadata_json.wake === "object" ? agent.metadata_json.wake : {}),
          in_progress: false,
          interrupt_reason: "user_cancelled",
        },
      };
      return jsonResponse(clone(agent));
    }

    const tasksMatch = path.match(/^\/api\/teams\/([^/]+)\/tasks$/);
    if (tasksMatch && method === "GET") {
      const team = state.teams.find((candidate) => candidate.id === tasksMatch[1]);
      return team ? jsonResponse(clone(team.tasks)) : jsonResponse({ detail: "not found" }, 404);
    }
    if (tasksMatch && method === "POST") {
      const team = state.teams.find((candidate) => candidate.id === tasksMatch[1]);
      if (!team) return jsonResponse({ detail: "not found" }, 404);
      const payload = parseBody<{ subject: string; description?: string; owner_slot_id?: string | null }>(init);
      state.lastTaskPayload = payload;
      const task = teamTask({
        id: `task-${state.nextId++}`,
        subject: payload.subject,
        description: payload.description ?? "",
        owner_slot_id: payload.owner_slot_id ?? null,
        status: "pending",
      });
      team.tasks.push(task);
      team.updated_at = now;
      return jsonResponse(clone(task), 201);
    }

    const taskPatchMatch = path.match(/^\/api\/teams\/([^/]+)\/tasks\/([^/]+)$/);
    if (taskPatchMatch && method === "PATCH") {
      const team = state.teams.find((candidate) => candidate.id === taskPatchMatch[1]);
      const task = team?.tasks.find((candidate) => candidate.id === taskPatchMatch[2]);
      if (!team || !task) return jsonResponse({ detail: "not found" }, 404);
      const payload = parseBody<Partial<TeamTask>>(init);
      Object.assign(task, payload, { updated_at: now });
      return jsonResponse(clone(task));
    }

    const agentsMatch = path.match(/^\/api\/teams\/([^/]+)\/agents$/);
    if (agentsMatch && method === "POST") {
      const team = state.teams.find((candidate) => candidate.id === agentsMatch[1]);
      if (!team) return jsonResponse({ detail: "not found" }, 404);
      const payload = parseBody<{ agent_id?: string; agent_name: string; role?: string }>(init);
      state.lastAddAgentPayload = payload;
      const slotId = `teammate-${state.nextId++}`;
      const agent = teamAgent({
        id: `${slotId}-agent`,
        team_id: team.id,
        slot_id: slotId,
        agent_id: payload.agent_id ?? "default",
        role: "teammate",
        agent_name: payload.agent_name,
        status: "pending",
      });
      team.agents.push(agent);
      return jsonResponse(clone(agent), 201);
    }

    const messageMatch = path.match(/^\/api\/teams\/([^/]+)\/messages$/);
    if (messageMatch && method === "POST") {
      const team = state.teams.find((candidate) => candidate.id === messageMatch[1]);
      if (!team) return jsonResponse({ detail: "not found" }, 404);
      const payload = parseBody<{
        target: string;
        content: string;
        from_agent_slot_id?: string;
        type?: string;
        mode?: TeamMessageMode;
      }>(init);
      state.lastMessagePayload = payload;
      const workspaceMode = payload.mode ?? "chat";
      const recipients =
        payload.target === "team"
          ? team.agents
              .filter(
                (agent) =>
                  agent.status !== "completed" && agent.slot_id !== (payload.from_agent_slot_id ?? "user"),
              )
              .map((agent) => agent.slot_id)
          : [payload.target === "leader" ? team.leader_slot_id : payload.target];
      const messages = recipients.map((slotId) =>
        teamMessage({
          id: `message-${state.nextId++}`,
          to_agent_slot_id: slotId,
          from_agent_slot_id: payload.from_agent_slot_id ?? "user",
          type: payload.type ?? "message",
          content: payload.content,
          metadata_json: { workspace_mode: workspaceMode },
          created_at: now,
        }),
      );
      team.messages.push(...messages);
      messages.forEach((message) => {
        const recipient = team.agents.find((agent) => agent.slot_id === message.to_agent_slot_id);
        if (!recipient) return;
        recipient.session_messages.push(
          agentMessage({
            id: `session-${message.id}`,
            session_id: recipient.session_id ?? `${recipient.slot_id}-session`,
            agent_id: recipient.agent_id,
            role: "user",
            content: message.content,
            metadata_json: {
              team_id: message.team_id,
              mailbox_message_id: message.id,
              from_agent_slot_id: message.from_agent_slot_id,
              to_agent_slot_id: message.to_agent_slot_id,
              message_type: message.type,
              workspace_mode: workspaceMode,
            },
            created_at: message.created_at ?? now,
          }),
        );
      });
      recipients.forEach((slotId) => {
        team.unread_counts[slotId] = (team.unread_counts[slotId] ?? 0) + 1;
      });
      return jsonResponse(clone(messages[0]), 201);
    }

    const wakeMatch = path.match(/^\/api\/teams\/([^/]+)\/agents\/([^/]+)\/wake$/);
    if (wakeMatch && method === "POST") {
      const team = state.teams.find((candidate) => candidate.id === wakeMatch[1]);
      const agent = team?.agents.find((candidate) => candidate.slot_id === wakeMatch[2]);
      if (!team || !agent) return jsonResponse({ detail: "not found" }, 404);
      agent.status = "active";
      agent.updated_at = now;
      agent.session_messages.push(
        agentMessage({
          id: `assistant-${state.nextId++}`,
          session_id: agent.session_id ?? `${agent.slot_id}-session`,
          role: "assistant",
          content: `回复 ${agent.agent_name}`,
          metadata_json: { event: "team_agent_model_response" },
        }),
      );
      agent.status = "idle";
      return jsonResponse(clone(agent));
    }

    const removeMatch = path.match(/^\/api\/teams\/([^/]+)\/agents\/([^/]+)$/);
    if (removeMatch && method === "PATCH") {
      const team = state.teams.find((candidate) => candidate.id === removeMatch[1]);
      const agent = team?.agents.find((candidate) => candidate.slot_id === removeMatch[2]);
      if (!team || !agent) return jsonResponse({ detail: "not found" }, 404);
      const payload = parseBody<{
        agent_name?: string;
        model_provider?: string;
        model_name?: string;
      }>(init);
      state.lastAgentUpdatePayload = payload;
      if (payload.agent_name !== undefined) agent.agent_name = payload.agent_name;
      if (payload.model_provider !== undefined) agent.model_provider = payload.model_provider;
      if (payload.model_name !== undefined) agent.model_name = payload.model_name;
      agent.updated_at = now;
      return jsonResponse(clone(agent));
    }
    if (removeMatch && method === "DELETE") {
      const team = state.teams.find((candidate) => candidate.id === removeMatch[1]);
      const agent = team?.agents.find((candidate) => candidate.slot_id === removeMatch[2]);
      if (!team || !agent) return jsonResponse({ detail: "not found" }, 404);
      agent.status = "completed";
      return jsonResponse(clone(agent));
    }

    return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
  });
}

function renderWithClient(ui: React.ReactElement, fetchMock: ReturnType<typeof vi.fn>, initialEntries: string[]) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  Object.defineProperty(document.documentElement, "clientWidth", {
    configurable: true,
    value: 390,
  });
  Object.defineProperty(document.documentElement, "scrollWidth", {
    configurable: true,
    value: 390,
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Team pages", () => {
  it("projects SSE events into the local Team cache", () => {
    const initial = teamFixture();
    const crashedProduct = {
      ...initial.agents.find((agent) => agent.slot_id === "product")!,
      status: "failed" as const,
      metadata_json: { wake: { last_error: "process exited" } },
    };
    const testament = teamMessage({
      id: "crash-message",
      to_agent_slot_id: "leader",
      from_agent_slot_id: "product",
      content: '[System] Member "产品经理" (default) crashed. Error: process exited.',
      summary: "产品经理 crashed",
      read: false,
    });

    const afterCrash = applyTeamEventToTeam(
      initial,
      teamEvent({
        event_type: "TEAM_AGENT_CRASHED",
        payload_json: { agent: crashedProduct },
      }),
    );
    expect(afterCrash?.agents.find((agent) => agent.slot_id === "product")?.status).toBe("failed");

    const spawnedAgent = teamAgent({
      id: "research-agent",
      slot_id: "research-agent",
      role: "teammate",
      agent_name: "研究智能体",
      session_id: "research-session",
      conversation_id: "research-session",
    });
    const spawnWelcome = teamMessage({
      id: "spawn-welcome",
      to_agent_slot_id: "research-agent",
      from_agent_slot_id: "leader",
      type: "system",
      content: '系统已将“研究智能体”加入团队。',
    });
    const afterSpawn = applyTeamEventToTeam(
      afterCrash!,
      teamEvent({
        sequence: 2,
        event_type: "TEAM_AGENT_SPAWNED",
        payload_json: { agent: spawnedAgent, message: spawnWelcome },
      }),
    );
    expect(afterSpawn?.agents.some((agent) => agent.slot_id === "research-agent")).toBe(true);
    expect(afterSpawn?.messages.some((message) => message.id === "spawn-welcome")).toBe(true);

    const afterMessage = applyTeamEventToTeam(
      afterSpawn!,
      teamEvent({
        sequence: 3,
        event_type: "TEAM_MESSAGE_CREATED",
        payload_json: { message: testament, target: "leader" },
      }),
    );
    expect(afterMessage?.messages.some((message) => message.id === testament.id)).toBe(true);
    expect(afterMessage?.unread_counts.leader).toBe(1);

    const assistantTurn = agentMessage({
      id: "assistant-turn-1",
      role: "assistant",
      content: "我已收到团队邮箱内容，会按产品视角继续处理。",
      metadata_json: { event: "team_agent_model_response" },
    });
    const afterSessionMessage = applyTeamEventToTeam(
      afterMessage!,
      teamEvent({
        sequence: 3,
        event_type: "TEAM_AGENT_SESSION_MESSAGE",
        payload_json: { slot_id: "product", messages: [assistantTurn] },
      }),
    );
    expect(
      afterSessionMessage?.agents
        .find((agent) => agent.slot_id === "product")
        ?.session_messages.some((message) => message.id === assistantTurn.id),
    ).toBe(true);

    const staleActive = applyTeamEventToTeam(
      {
        ...afterSessionMessage!,
        agents: afterSessionMessage!.agents.map((agent) =>
          agent.slot_id === "product"
            ? { ...agent, status: "idle" as const, updated_at: "2026-05-23T08:00:02Z" }
            : agent,
        ),
      },
      teamEvent({
        sequence: 4,
        event_type: "TEAM_AGENT_STATUS",
        payload_json: {
          agent: {
            ...afterSessionMessage!.agents.find((agent) => agent.slot_id === "product")!,
            status: "active",
            updated_at: "2026-05-23T08:00:01Z",
            session_messages: [],
          },
        },
      }),
    );
    expect(staleActive?.agents.find((agent) => agent.slot_id === "product")?.status).toBe("idle");

    const afterRead = applyTeamEventToTeam(
      afterSessionMessage!,
      teamEvent({
        sequence: 5,
        event_type: "TEAM_MAILBOX_READ",
        payload_json: { slot_id: "leader", message_ids: [testament.id] },
      }),
    );
    expect(afterRead?.messages.find((message) => message.id === testament.id)?.read).toBe(true);
    expect(afterRead?.unread_counts.leader).toBeUndefined();

    const updatedTask = { ...initial.tasks[0], status: "completed" as const };
    const afterTask = applyTeamEventToTeam(
      afterRead!,
      teamEvent({
        sequence: 6,
        event_type: "TEAM_TASK_UPDATED",
        payload_json: { task: updatedTask },
      }),
    );
    expect(afterTask?.tasks.find((task) => task.id === updatedTask.id)?.status).toBe("completed");
  });

  it("renders teams and creates a Team Session after selecting a leader", async () => {
    const user = userEvent.setup();
    const state = stateFixture();
    const fetchMock = routeTeamApis(state);

    renderWithClient(
      <Routes>
        <Route path="/teams" element={<TeamListPage />} />
        <Route path="/teams/:teamId" element={<div>打开团队详情</div>} />
      </Routes>,
      fetchMock,
      ["/teams"],
    );

    expect(await screen.findByText("团队模式")).toBeInTheDocument();
    expect((await screen.findAllByText("Team Mode 协作团队")).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: /创建团队/ }));

    const dialog = await screen.findByRole("dialog", { name: "创建团队" });
    expect(within(dialog).getByLabelText("团队名称")).toHaveValue("Team Mode 协作团队 2");
    const createButton = within(dialog).getByRole("button", { name: /创建团队/ });
    expect(await within(dialog).findByText("default · default/default")).toBeInTheDocument();
    expect(createButton).toBeEnabled();

    await user.clear(within(dialog).getByLabelText("团队名称"));
    await user.type(within(dialog).getByLabelText("团队名称"), "验证团队");
    await user.clear(within(dialog).getByLabelText("工作区"));
    await user.type(within(dialog).getByLabelText("工作区"), "/tmp/harness-team");
    await user.click(createButton);

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input) === "/api/teams" && init?.method === "POST",
      );
      expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
        name: "验证团队",
        workspace: "/tmp/harness-team",
        workspace_mode: "shared",
        leader_agent_id: "default",
      });
    });
    expect(await screen.findByText("打开团队详情")).toBeInTheDocument();
  });

  it("renders columns, creates members, and supports direct mailbox messages", async () => {
    const user = userEvent.setup();
    const state = stateFixture();
    const fetchMock = routeTeamApis(state);

    renderWithClient(
      <Routes>
        <Route path="/teams/:teamId" element={<TeamPage />} />
        <Route path="/teams" element={<div>团队列表</div>} />
      </Routes>,
      fetchMock,
      ["/teams/team-1"],
    );

    expect((await screen.findAllByText("Team Mode 协作团队")).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /Team Mode 协作团队/ })).toBeInTheDocument();
    expect(screen.getByRole("tablist", { name: "代理切换" })).toBeInTheDocument();
    expect(screen.getByTestId("team-tab-bar")).toBeInTheDocument();
    const productTab = await screen.findByRole("tab", { name: /产品经理/ });
    (Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>).mockClear();
    await user.click(productTab);
    await waitFor(() => {
      expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
    });

    const productColumn = (await screen.findAllByRole("region", { name: /产品经理 成员 列/ }))[0];
    await waitFor(() => {
      expect(productColumn).toHaveClass("opacity-60");
    });
    expect(within(productColumn).getByText("请设计团队窗口")).toBeInTheDocument();
    expect(within(productColumn).getByText("会话视图中的团队消息")).toBeInTheDocument();
    expect(within(productColumn).getAllByRole("button", { name: "固定消息" }).length).toBeGreaterThan(0);
    expect(within(productColumn).getAllByRole("button", { name: "复制" }).length).toBeGreaterThan(0);
    expect(within(productColumn).getByRole("button", { name: "编辑" })).toBeInTheDocument();
    expect(within(productColumn).getByRole("button", { name: "重新生成" })).toBeInTheDocument();
    expect(within(productColumn).getAllByRole("button", { name: "分支" }).length).toBeGreaterThan(0);
    expect(within(productColumn).getByRole("link", { name: "查看运行详情" })).toHaveAttribute(
      "href",
      "/runs/run-team-1",
    );
    expect(within(productColumn).getByRole("link", { name: "打开评测中心" })).toHaveAttribute(
      "href",
      "/evals?run=run-team-1",
    );
    await user.click(within(productColumn).getAllByRole("button", { name: "分支" })[0]);
    await waitFor(() => {
      expect(state.lastMessagePayload).toMatchObject({
        target: "product",
        content: "请设计团队窗口",
      });
    });
    expect(await within(productColumn).findByLabelText("分支 2/2")).toBeInTheDocument();
    expect(within(productColumn).getByText("2/2")).toBeInTheDocument();
    expect(within(productColumn).getAllByText("请设计团队窗口")).toHaveLength(1);
    await user.click(within(productColumn).getByRole("button", { name: "上一个分支" }));
    expect(await within(productColumn).findByLabelText("分支 1/2")).toBeInTheDocument();
    expect(within(productColumn).getByText("1/2")).toBeInTheDocument();
    await user.click(within(productColumn).getByRole("button", { name: "下一个分支" }));
    expect(await within(productColumn).findByLabelText("分支 2/2")).toBeInTheDocument();
    expect(within(productColumn).getByText("2/2")).toBeInTheDocument();
    expect(screen.getByLabelText("代理会话列")).toBeInTheDocument();
    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(document.documentElement.clientWidth);
    await user.click(screen.getByRole("button", { name: "添加成员" }));
    const addMemberDialog = await screen.findByRole("dialog", { name: "添加成员" });
    expect(await within(addMemberDialog).findByText("default · default/default")).toBeInTheDocument();
    await user.type(within(addMemberDialog).getByLabelText("成员名称"), "测试工程师");
    await user.click(within(addMemberDialog).getByRole("button", { name: "添加成员" }));
    await waitFor(() => {
      expect(state.lastAddAgentPayload).toMatchObject({
        agent_id: "default",
        agent_name: "测试工程师",
        role: "teammate",
      });
    });
    expect(await screen.findByText("团队成员已添加")).toBeInTheDocument();
    expect(await screen.findByRole("tab", { name: /测试工程师/ })).toBeInTheDocument();
    const addedEngineer = state.teams[0].agents.find((agent) => agent.agent_name === "测试工程师");
    expect(addedEngineer?.slot_id).toBeTruthy();
    await user.click(await screen.findByRole("tab", { name: /产品经理/ }));
    expect(within(productColumn).getByRole("button", { name: "移除成员" })).toBeInTheDocument();

    await user.dblClick(productTab);
    const renameInput = await screen.findByLabelText("代理名称");
    await user.clear(renameInput);
    await user.type(renameInput, "产品负责人{Enter}");
    await waitFor(() => {
      const renameCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input) === "/api/teams/team-1/agents/product" && init?.method === "PATCH",
      );
      expect(JSON.parse(String(renameCall?.[1]?.body))).toMatchObject({ agent_name: "产品负责人" });
    });
    expect(await screen.findByText("成员名称已更新")).toBeInTheDocument();
    expect(await screen.findByRole("tab", { name: /产品负责人/ })).toBeInTheDocument();

    const uiTab = await screen.findByRole("tab", { name: /UI/ });
    fireEvent.dragStart(uiTab, { dataTransfer: { effectAllowed: "move" } });
    fireEvent.dragOver(await screen.findByRole("tab", { name: /产品负责人/ }), {
      dataTransfer: { dropEffect: "move" },
    });
    fireEvent.drop(await screen.findByRole("tab", { name: /产品负责人/ }), {
      dataTransfer: { dropEffect: "move" },
    });

    await user.click(screen.getByRole("button", { name: "任务板" }));
    const taskBoard = await screen.findByRole("dialog", { name: "团队任务板" });
    expect(within(taskBoard).getByText("实现多列 UI")).toBeInTheDocument();
    expect(within(taskBoard).getByText(/负责人 · 产品负责人/)).toBeInTheDocument();
    await user.click(within(taskBoard).getByRole("button", { name: "关闭任务板" }));

    expect(within(productColumn).queryByRole("button", { name: /发送目标/ })).not.toBeInTheDocument();
    await user.type(within(productColumn).getByRole("textbox"), "直接同步 UI 状态{Enter}");
    await waitFor(() => {
      expect(state.lastMessagePayload).toMatchObject({
        target: "product",
        content: "直接同步 UI 状态",
        from_agent_slot_id: "user",
        type: "message",
      });
    });

    const directProductSendCalls = fetchMock.mock.calls.filter(
      ([input, init]) =>
        requestPath(input) === "/api/teams/team-1/messages" &&
        init?.method === "POST" &&
        JSON.parse(String(init.body)).content === "直接同步 UI 状态",
    );
    expect(directProductSendCalls).toHaveLength(1);
    await waitFor(() => {
      expect(within(productColumn).getAllByText("直接同步 UI 状态")).toHaveLength(1);
    });

    const leaderColumn = (await screen.findAllByRole("region", { name: /队长 队长 列/ }))[0];
    await user.click(await screen.findByRole("tab", { name: /队长/ }));
    await user.type(within(leaderColumn).getByRole("textbox"), "Ask 产品负责人 to sync UI 状态");
    await user.click(within(leaderColumn).getByRole("button", { name: "发送" }));

    await waitFor(() => {
      expect(state.lastMessagePayload).toMatchObject({
        target: "leader",
        content: "Ask 产品负责人 to sync UI 状态",
        from_agent_slot_id: "user",
        type: "message",
      });
    });
    expect(await within(leaderColumn).findByText("Ask 产品负责人 to sync UI 状态")).toBeInTheDocument();

    await user.click(within(productColumn).getByRole("button", { name: "切换全屏列" }));
    await waitFor(() => {
      expect(screen.queryByRole("region", { name: /队长 队长 列/ })).not.toBeInTheDocument();
    });
    const fullscreenColumns = within(screen.getByLabelText("代理会话列"));
    expect(fullscreenColumns.queryByRole("region", { name: /UI 成员 列/ })).not.toBeInTheDocument();
    expect(fullscreenColumns.getByRole("region", { name: /产品负责人 成员 列/ })).toBeInTheDocument();

    expect(await within(productColumn).findByText("实现多列 UI")).toBeInTheDocument();
  }, 15000);

  it("supports team goal mode, plan mode, and model selection from the composer", async () => {
    const user = userEvent.setup();
    const state = stateFixture();
    const fetchMock = routeTeamApis(state);

    renderWithClient(
      <Routes>
        <Route path="/teams/:teamId" element={<TeamPage />} />
      </Routes>,
      fetchMock,
      ["/teams/team-1"],
    );

    const productColumn = (await screen.findAllByRole("region", { name: /产品经理 成员 列/ }))[0];
    const textbox = within(productColumn).getByRole("textbox");

    expect(within(productColumn).queryByRole("button", { name: "追踪目标模式" })).not.toBeInTheDocument();
    await user.type(textbox, "/goal");
    await user.keyboard("{Enter}");
    await waitFor(() => {
      expect(textbox).toHaveAttribute("placeholder", expect.stringContaining("追求目标"));
    });
    await user.click(within(productColumn).getByRole("button", { name: "打开输入设置" }));
    expect(within(productColumn).getByRole("switch", { name: "追踪目标模式" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await user.click(within(productColumn).getByRole("switch", { name: "追踪目标模式" }));
    await waitFor(() => {
      expect(textbox).not.toHaveAttribute("placeholder", expect.stringContaining("追求目标"));
    });
    await user.type(textbox, "/plan{Enter}");
    await waitFor(() => {
      expect(textbox).toHaveAttribute("placeholder", expect.stringContaining("规划目标"));
    });
    await user.type(textbox, "slash plan 团队目标{Enter}");
    await waitFor(() => {
      expect(state.lastMessagePayload).toMatchObject({
        target: "product",
        content: "slash plan 团队目标",
        mode: "markdown_plan",
      });
    });

    await waitFor(() => {
      expect(within(productColumn).queryByRole("button", { name: "停止生成" })).not.toBeInTheDocument();
    });
    await user.type(textbox, "/chat{Enter}");
    await waitFor(() => {
      expect(textbox).toHaveAttribute("placeholder", expect.stringContaining("发送消息"));
    });
    await user.type(textbox, "/Harness Agent{Enter}");
    await waitFor(() => {
      expect(textbox).toHaveAttribute("placeholder", expect.stringContaining("规划目标"));
    });
    await user.type(textbox, "slash Harness Agent 团队目标{Enter}");
    await waitFor(() => {
      expect(state.lastMessagePayload).toMatchObject({
        target: "product",
        content: "slash Harness Agent 团队目标",
        mode: "markdown_plan",
      });
    });

    await waitFor(() => {
      expect(within(productColumn).queryByRole("button", { name: "停止生成" })).not.toBeInTheDocument();
    });
    await user.type(textbox, "/chat{Enter}");
    await waitFor(() => {
      expect(textbox).toHaveAttribute("placeholder", expect.stringContaining("发送消息"));
    });
    await user.type(textbox, "/run{Enter}");
    await waitFor(() => {
      expect(textbox).toHaveAttribute("placeholder", expect.stringContaining("执行目标"));
    });
    await user.type(textbox, "slash run 团队目标{Enter}");
    await waitFor(() => {
      expect(state.lastMessagePayload).toMatchObject({
        target: "product",
        content: "slash run 团队目标",
        mode: "plan",
      });
    });

    await waitFor(() => {
      expect(within(productColumn).queryByRole("button", { name: "停止生成" })).not.toBeInTheDocument();
    });
    await user.type(textbox, "/chat{Enter}");
    await waitFor(() => {
      expect(textbox).toHaveAttribute("placeholder", expect.stringContaining("发送消息"));
    });
    await user.click(within(productColumn).getByRole("button", { name: "打开输入设置" }));
    await user.click(within(productColumn).getByRole("switch", { name: "追踪目标模式" }));
    await waitFor(() => {
      expect(textbox).toHaveAttribute("placeholder", expect.stringContaining("追求目标"));
    });
    await user.type(textbox, "追求团队目标{Enter}");
    await waitFor(() => {
      expect(state.lastMessagePayload).toMatchObject({
        target: "product",
        content: "追求团队目标",
        mode: "goal",
      });
    });
    const goalMessage = state.teams[0].messages.find((message) => message.content === "追求团队目标");
    expect(goalMessage?.metadata_json.workspace_mode).toBe("goal");
    const goalMirror = state.teams[0].agents
      .find((agent) => agent.slot_id === "product")
      ?.session_messages.find((message) => message.content === "追求团队目标");
    expect(goalMirror?.metadata_json.workspace_mode).toBe("goal");

    await waitFor(() => {
      expect(within(productColumn).queryByRole("button", { name: "停止生成" })).not.toBeInTheDocument();
    });
    await user.click(within(productColumn).getByRole("button", { name: "打开输入设置" }));
    await user.click(within(productColumn).getByRole("switch", { name: "计划模式" }));
    await waitFor(() => {
      expect(textbox).toHaveAttribute("placeholder", expect.stringContaining("规划目标"));
    });
    await user.type(textbox, "规划团队目标{Enter}");
    await waitFor(() => {
      expect(state.lastMessagePayload).toMatchObject({
        target: "product",
        content: "规划团队目标",
        mode: "markdown_plan",
      });
    });

    await waitFor(() => {
      expect(within(productColumn).queryByRole("button", { name: "停止生成" })).not.toBeInTheDocument();
    });
    await user.type(textbox, "/model{Enter}");
    await user.click(await screen.findByRole("option", { name: /DeepSeek Pro/ }));
    await waitFor(() => {
      expect(state.lastAgentUpdatePayload).toMatchObject({
        model_provider: "deepseek-pro",
        model_name: "deepseek-v4-pro",
      });
    });
    expect(await within(productColumn).findByText("deepseek-pro / deepseek-v4-pro")).toBeInTheDocument();

  }, 15000);

  it("compresses a Team column context from slash command and usage ring", async () => {
    const user = userEvent.setup();
    const state = stateFixture();
    const fetchMock = routeTeamApis(state);

    renderWithClient(
      <Routes>
        <Route path="/teams/:teamId" element={<TeamPage />} />
      </Routes>,
      fetchMock,
      ["/teams/team-1"],
    );

    const productColumn = (await screen.findAllByRole("region", { name: /产品经理 成员 列/ }))[0];
    const textbox = within(productColumn).getByRole("textbox");

    await user.type(textbox, "/compress{Enter}");
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.filter(
          ([input, init]) =>
            requestPath(input) === "/api/agents/default/context/compress" &&
            init?.method === "POST",
        ),
      ).toHaveLength(1);
    });
    const slashPayload = JSON.parse(
      String(
        fetchMock.mock.calls.find(
          ([input, init]) =>
            requestPath(input) === "/api/agents/default/context/compress" &&
            init?.method === "POST",
        )?.[1]?.body,
      ),
    ) as { messages: Array<{ content: string }>; pinned_node_ids: string[] };
    expect(slashPayload.messages.map((message) => message.content)).toContain("请设计团队窗口");
    expect(slashPayload.messages.map((message) => message.content)).toContain("会话视图中的团队消息");
    expect(slashPayload.pinned_node_ids).toEqual([]);
    expect(await within(productColumn).findByLabelText("上下文摘要")).toBeInTheDocument();
    expect(await within(productColumn).findByText("1 条已摘要")).toBeInTheDocument();
    expect(await within(productColumn).findByText("team compressed summary")).toBeInTheDocument();

    await user.click(
      within(productColumn).getByRole("button", {
        name: /点击压缩上下文/,
      }),
    );
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.filter(
          ([input, init]) =>
            requestPath(input) === "/api/agents/default/context/compress" &&
            init?.method === "POST",
        ),
      ).toHaveLength(2);
    });
  });

  it("renders seed-imported workspace history in a new Team leader session", async () => {
    const state = stateFixture();
    const fetchMock = routeTeamApis(state);

    renderWithClient(
      <Routes>
        <Route
          path="/seed"
          element={
            <Link
              to="/teams/team-created"
              onClick={() => {
                const payload = {
                  name: "Seeded Team",
                  workspace_mode: "shared",
                  leader_agent_id: "default",
                  leader_name: "队长",
                  seed_messages: [
                    {
                      role: "user",
                      content: "当前智能体页面的问题",
                      created_at: now,
                      metadata_json: { workspace_node_id: "node-1" },
                    },
                    {
                      role: "assistant",
                      content: "当前智能体页面的回答",
                      created_at: now,
                      metadata_json: { source_run_id: "run-seeded-1" },
                    },
                  ],
                };
                state.teams.unshift(
                  teamFixture({
                    id: "team-created",
                    name: payload.name,
                    agents: [
                      teamAgent({
                        id: "created-leader-agent",
                        team_id: "team-created",
                        slot_id: "leader",
                        role: "leader",
                        agent_name: "队长",
                        session_id: "created-leader-session",
                        conversation_id: "created-leader-session",
                        session_messages: payload.seed_messages.map((message, index) =>
                          agentMessage({
                            id: `seed-${index}`,
                            session_id: "created-leader-session",
                            role: message.role as AgentMessage["role"],
                            content: message.content,
                            metadata_json: message.metadata_json,
                            created_at: message.created_at,
                          }),
                        ),
                      }),
                    ],
                    messages: [],
                    tasks: [],
                    unread_counts: {},
                  }),
                );
              }}
            >
              seed team
            </Link>
          }
        />
        <Route path="/teams/:teamId" element={<TeamPage />} />
      </Routes>,
      fetchMock,
      ["/seed"],
    );

    await userEvent.click(screen.getByRole("link", { name: "seed team" }));

    expect((await screen.findAllByText("当前智能体页面的问题")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("当前智能体页面的回答")).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "查看运行详情" })[0]).toHaveAttribute(
      "href",
      "/runs/run-seeded-1",
    );
  });

  it("merges stream status and mailbox events into visible agent columns", async () => {
    const crashedProduct = {
      ...teamAgent({
        id: "product-agent",
        slot_id: "product",
        role: "teammate",
        agent_name: "产品经理",
      }),
      status: "failed" as const,
    };
    const testament = teamMessage({
      id: "crash-message",
      to_agent_slot_id: "leader",
      from_agent_slot_id: "product",
      content:
        '[System] Member "产品经理" (default) crashed. Error: process exited. The member slot is preserved and can be recovered if needed.',
      summary: "产品经理 crashed",
      read: false,
      created_at: now,
    });
    const assistantTurn = agentMessage({
      id: "product-assistant-turn",
      role: "assistant",
      content: "我已收到团队邮箱内容，会按产品视角继续处理。",
      metadata_json: { event: "team_agent_model_response" },
      created_at: now,
    });
    const state = stateFixture();
    state.streamBody = [
      `id: 2\ndata: ${JSON.stringify(
        teamEvent({
          sequence: 2,
          event_type: "TEAM_AGENT_CRASHED",
          payload_json: { agent: crashedProduct },
        }),
      )}\n\n`,
      `id: 3\ndata: ${JSON.stringify(
        teamEvent({
          sequence: 3,
          event_type: "TEAM_MESSAGE_CREATED",
          payload_json: { message: testament, target: "leader" },
        }),
      )}\n\n`,
      `id: 4\ndata: ${JSON.stringify(
        teamEvent({
          sequence: 4,
          event_type: "TEAM_AGENT_SESSION_MESSAGE",
          payload_json: { slot_id: "product", messages: [assistantTurn] },
        }),
      )}\n\n`,
    ].join("");
    const fetchMock = routeTeamApis(state);

    renderWithClient(
      <Routes>
        <Route path="/teams/:teamId" element={<TeamPage />} />
      </Routes>,
      fetchMock,
      ["/teams/team-1"],
    );

    const productTab = await screen.findByRole("tab", { name: /产品经理/ });
    await waitFor(() => {
      expect(within(productTab).getByText("失败")).toBeInTheDocument();
    });
    const leaderColumn = (await screen.findAllByRole("region", { name: /队长 队长 列/ }))[0];
    expect(await within(leaderColumn).findByText(/Member "产品经理".*crashed/)).toBeInTheDocument();
    const productColumn = (await screen.findAllByRole("region", { name: /产品经理 成员 列/ }))[0];
    expect(await within(productColumn).findByText("我已收到团队邮箱内容，会按产品视角继续处理。")).toBeInTheDocument();
    const directTeamFetches = fetchMock.mock.calls.filter(
      ([input, init]) => requestPath(input) === "/api/teams/team-1" && (init?.method ?? "GET") === "GET",
    );
    expect(directTeamFetches).toHaveLength(1);
  });

  it("shows a streaming placeholder while an agent is active", async () => {
    const state = stateFixture();
    state.teams = [
      teamFixture({
        agents: [
          teamAgent({
            id: "leader-agent",
            slot_id: "leader",
            role: "leader",
            agent_name: "队长",
          }),
          teamAgent({
            id: "product-agent",
            slot_id: "product",
            role: "teammate",
            agent_name: "产品经理",
            status: "active",
            session_id: "product-session",
            conversation_id: "product-session",
            metadata_json: { wake: { in_progress: true } },
            session_messages: [agentMessage({ id: "product-user-turn", role: "user", content: "请设计团队窗口" })],
          }),
        ],
        messages: [],
      }),
    ];
    const fetchMock = routeTeamApis(state);

    renderWithClient(
      <Routes>
        <Route path="/teams/:teamId" element={<TeamPage />} />
      </Routes>,
      fetchMock,
      ["/teams/team-1"],
    );

    const productColumn = await screen.findByRole("region", { name: /产品经理 成员 列/ });
    expect(await within(productColumn).findByText("正在生成...")).toBeInTheDocument();
  });

  it("replaces the wake stream placeholder with the final assistant message", async () => {
    const user = userEvent.setup();
    const state = stateFixture();
    const team = state.teams[0];
    const product = team.agents.find((agent) => agent.slot_id === "product")!;
    const finalAgent = { ...product, status: "idle" as const, session_messages: [] };
    const finalMessage = agentMessage({
      id: "stream-final-message",
      session_id: product.session_id ?? "product-session",
      role: "assistant",
      content: "流式最终回复",
      metadata_json: { event: "team_agent_model_response" },
    });
    product.session_messages.push(finalMessage);
    state.wakeStreamChunks = [
      sseFrame("status", { agent: { ...product, status: "active", session_messages: [] } }),
      sseFrame("delta", { slot_id: "product", content: "流式" }),
      sseFrame("delta", { slot_id: "product", content: "回复中" }),
      sseFrame("done", { agent: finalAgent, message: finalMessage }),
    ];
    const fetchMock = routeTeamApis(state);

    renderWithClient(
      <Routes>
        <Route path="/teams/:teamId" element={<TeamPage />} />
      </Routes>,
      fetchMock,
      ["/teams/team-1"],
    );

    const productColumn = await screen.findByRole("region", { name: /产品经理 成员 列/ });
    await user.type(within(productColumn).getByRole("textbox"), "触发流式回复{Enter}");

    expect(await within(productColumn).findByText("流式回复中")).toBeInTheDocument();
    expect(await within(productColumn).findByText("流式最终回复")).toBeInTheDocument();
    await waitFor(() => {
      expect(within(productColumn).queryByText("正在生成...")).not.toBeInTheDocument();
    });
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          requestPath(input) === "/api/teams/team-1/agents/product/wake/stream" &&
          init?.method === "POST",
      ),
    ).toBe(true);
  });

  it("does not get stuck generating after a completed wake stream receives an older active event", async () => {
    const user = userEvent.setup();
    const state = stateFixture();
    const team = state.teams[0];
    const product = team.agents.find((agent) => agent.slot_id === "product")!;
    const finalAgent = {
      ...product,
      status: "idle" as const,
      updated_at: "2026-05-23T08:00:02Z",
      session_messages: [],
    };
    const finalMessage = agentMessage({
      id: "stream-final-message",
      session_id: product.session_id ?? "product-session",
      role: "assistant",
      content: "流式最终回复",
      metadata_json: { event: "team_agent_model_response" },
      created_at: "2026-05-23T08:00:02Z",
    });
    product.session_messages.push(finalMessage);
    state.wakeStreamChunks = [
      sseFrame("status", {
        agent: {
          ...product,
          status: "active",
          updated_at: "2026-05-23T08:00:01Z",
          session_messages: [],
        },
      }),
      sseFrame("delta", { slot_id: "product", content: "流式" }),
      sseFrame("done", { agent: finalAgent, message: finalMessage }),
    ];
    state.streamBody = [
      `id: 10\ndata: ${JSON.stringify(
        teamEvent({
          sequence: 10,
          event_type: "TEAM_AGENT_STATUS",
          payload_json: {
            agent: {
              ...product,
              status: "active",
              updated_at: "2026-05-23T08:00:01Z",
              session_messages: [],
            },
          },
        }),
      )}\n\n`,
    ].join("");
    const fetchMock = routeTeamApis(state);

    renderWithClient(
      <Routes>
        <Route path="/teams/:teamId" element={<TeamPage />} />
      </Routes>,
      fetchMock,
      ["/teams/team-1"],
    );

    const productColumn = await screen.findByRole("region", { name: /产品经理 成员 列/ });
    await user.type(within(productColumn).getByRole("textbox"), "触发流式回复{Enter}");

    expect(await within(productColumn).findByText("流式最终回复")).toBeInTheDocument();
    await waitFor(() => {
      expect(within(productColumn).queryByText("正在生成...")).not.toBeInTheDocument();
      expect(within(productColumn).queryByText("协作中")).not.toBeInTheDocument();
    });
  });

  it("clears generating after done even when the done agent still reports active wake state", async () => {
    const user = userEvent.setup();
    const state = stateFixture();
    const team = state.teams[0];
    const product = team.agents.find((agent) => agent.slot_id === "product")!;
    const finalAgent = {
      ...product,
      status: "active" as const,
      updated_at: null,
      metadata_json: { wake: { in_progress: true } },
      session_messages: [],
    };
    const finalMessage = agentMessage({
      id: "stream-final-active-agent-message",
      session_id: product.session_id ?? "product-session",
      role: "assistant",
      content: "回复已经正常结束",
      metadata_json: { event: "team_agent_model_response" },
      created_at: "2026-05-23T08:00:02Z",
    });
    product.session_messages.push(finalMessage);
    state.wakeStreamChunks = [
      sseFrame("status", {
        agent: {
          ...product,
          status: "active",
          metadata_json: { wake: { in_progress: true } },
          session_messages: [],
        },
      }),
      sseFrame("delta", { slot_id: "product", content: "回复已经" }),
      sseFrame("done", { agent: finalAgent, message: finalMessage }),
    ];
    const fetchMock = routeTeamApis(state);

    renderWithClient(
      <Routes>
        <Route path="/teams/:teamId" element={<TeamPage />} />
      </Routes>,
      fetchMock,
      ["/teams/team-1"],
    );

    const productColumn = await screen.findByRole("region", { name: /产品经理 成员 列/ });
    await user.type(within(productColumn).getByRole("textbox"), "触发异常终止状态{Enter}");

    expect(await within(productColumn).findByText("回复已经正常结束")).toBeInTheDocument();
    await waitFor(() => {
      expect(within(productColumn).queryByText("正在生成...")).not.toBeInTheDocument();
      expect(within(productColumn).queryByText("协作中")).not.toBeInTheDocument();
      expect(within(productColumn).queryByRole("button", { name: "停止生成" })).not.toBeInTheDocument();
    });
  });

  it("clears generating as soon as a done wake event arrives even if the HTTP stream stays open", async () => {
    const user = userEvent.setup();
    const state = stateFixture();
    const team = state.teams[0];
    const product = team.agents.find((agent) => agent.slot_id === "product")!;
    const finalAgent = {
      ...product,
      status: "idle" as const,
      updated_at: "2026-05-23T08:00:02Z",
      session_messages: [],
    };
    const finalMessage = agentMessage({
      id: "stream-final-open-message",
      session_id: product.session_id ?? "product-session",
      role: "assistant",
      content: "连接未关闭但回复已完成",
      metadata_json: { event: "team_agent_model_response" },
      created_at: "2026-05-23T08:00:02Z",
    });
    product.session_messages.push(finalMessage);
    state.wakeStreamKeepOpen = true;
    state.wakeStreamChunks = [
      sseFrame("status", {
        agent: {
          ...product,
          status: "active",
          metadata_json: { wake: { in_progress: true } },
          session_messages: [],
        },
      }),
      sseFrame("delta", { slot_id: "product", content: "连接未关闭" }),
      sseFrame("done", { agent: finalAgent, message: finalMessage }),
    ];
    const fetchMock = routeTeamApis(state);

    renderWithClient(
      <Routes>
        <Route path="/teams/:teamId" element={<TeamPage />} />
      </Routes>,
      fetchMock,
      ["/teams/team-1"],
    );

    const productColumn = await screen.findByRole("region", { name: /产品经理 成员 列/ });
    await user.type(within(productColumn).getByRole("textbox"), "触发保持连接的完成流{Enter}");

    expect(await within(productColumn).findByText("连接未关闭但回复已完成")).toBeInTheDocument();
    await waitFor(() => {
      expect(within(productColumn).queryByText("正在生成...")).not.toBeInTheDocument();
      expect(within(productColumn).queryByText("协作中")).not.toBeInTheDocument();
      expect(within(productColumn).queryByRole("button", { name: "停止生成" })).not.toBeInTheDocument();
    });
  });

  it("clears generating when the team event stream delivers the final assistant turn first", async () => {
    const user = userEvent.setup();
    const state = stateFixture();
    const team = state.teams[0];
    const product = team.agents.find((agent) => agent.slot_id === "product")!;
    const finalMessage = agentMessage({
      id: "team-event-final-message",
      session_id: product.session_id ?? "product-session",
      role: "assistant",
      content: "团队事件最终回复",
      metadata_json: { event: "team_agent_model_response" },
      created_at: "2026-05-23T08:00:03Z",
    });
    state.streamChunks = [
      ": heartbeat\n\n",
      `id: 20\ndata: ${JSON.stringify(
        teamEvent({
          sequence: 20,
          event_type: "TEAM_AGENT_SESSION_MESSAGE",
          created_at: "2026-05-23T08:00:03Z",
          payload_json: { slot_id: "product", messages: [finalMessage] },
        }),
      )}\n\n`,
    ];
    state.streamDelayMs = 1000;
    state.wakeStreamKeepOpen = true;
    state.wakeStreamChunks = [
      sseFrame("status", {
        agent: {
          ...product,
          status: "active",
          metadata_json: { wake: { in_progress: true, started_at: "2026-05-23T08:00:01Z" } },
          session_messages: [],
        },
      }),
    ];
    const fetchMock = routeTeamApis(state);

    renderWithClient(
      <Routes>
        <Route path="/teams/:teamId" element={<TeamPage />} />
      </Routes>,
      fetchMock,
      ["/teams/team-1"],
    );

    const productColumn = await screen.findByRole("region", { name: /产品经理 成员 列/ });
    await user.type(within(productColumn).getByRole("textbox"), "触发团队事件完成{Enter}");

    expect(await within(productColumn).findByText("正在生成...")).toBeInTheDocument();
    expect(await within(productColumn).findByText("团队事件最终回复")).toBeInTheDocument();
    await waitFor(() => {
      expect(within(productColumn).queryByText("正在生成...")).not.toBeInTheDocument();
      expect(within(productColumn).queryByText("协作中")).not.toBeInTheDocument();
      expect(within(productColumn).queryByRole("button", { name: "停止生成" })).not.toBeInTheDocument();
    });
  });

  it("shows a newly spawned teammate from the team event stream as a visible agent column", async () => {
    const state = stateFixture();
    const spawnedAgent = teamAgent({
      id: "creative-agent",
      team_id: "team-1",
      slot_id: "creative-planner",
      role: "teammate",
      agent_name: "创意策划",
      status: "pending",
      session_id: "creative-session",
      conversation_id: "creative-session",
    });
    const spawnWelcome = teamMessage({
      id: "creative-welcome",
      to_agent_slot_id: "creative-planner",
      from_agent_slot_id: "leader",
      type: "system",
      content: 'You have been spawned as "创意策划" and added to the team.',
    });
    state.streamChunks = [
      ": heartbeat\n\n",
      `id: 30\ndata: ${JSON.stringify(
        teamEvent({
          sequence: 30,
          event_type: "TEAM_AGENT_SPAWNED",
          payload_json: { agent: spawnedAgent, message: spawnWelcome },
        }),
      )}\n\n`,
    ];
    const fetchMock = routeTeamApis(state);

    renderWithClient(
      <Routes>
        <Route path="/teams/:teamId" element={<TeamPage />} />
      </Routes>,
      fetchMock,
      ["/teams/team-1"],
    );

    expect(await screen.findByRole("tab", { name: /创意策划/ })).toBeInTheDocument();
    expect(await screen.findByRole("region", { name: /创意策划 成员 列/ })).toBeInTheDocument();
  });

  it("clears the generating state when a wake stream closes without a final done frame", async () => {
    const user = userEvent.setup();
    const state = stateFixture();
    const team = state.teams[0];
    const product = team.agents.find((agent) => agent.slot_id === "product")!;
    state.wakeStreamChunks = [
      sseFrame("status", {
        agent: {
          ...product,
          status: "active",
          metadata_json: { wake: { in_progress: true } },
          session_messages: [],
        },
      }),
      sseFrame("delta", { slot_id: "product", content: "正常回复完成" }),
    ];
    const fetchMock = routeTeamApis(state);

    renderWithClient(
      <Routes>
        <Route path="/teams/:teamId" element={<TeamPage />} />
      </Routes>,
      fetchMock,
      ["/teams/team-1"],
    );

    const productColumn = await screen.findByRole("region", { name: /产品经理 成员 列/ });
    await user.type(within(productColumn).getByRole("textbox"), "触发没有 done 的流{Enter}");

    expect(await within(productColumn).findByText("正常回复完成")).toBeInTheDocument();
    await waitFor(() => {
      expect(within(productColumn).queryByText("正在生成...")).not.toBeInTheDocument();
      expect(within(productColumn).queryByText("协作中")).not.toBeInTheDocument();
      expect(within(productColumn).queryByRole("button", { name: "停止生成" })).not.toBeInTheDocument();
    });
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          requestPath(input) === "/api/teams/team-1/agents/product/wake/stream" &&
          init?.method === "POST",
      ),
    ).toBe(true);
  });

  it("does not show generating for an active agent whose wake state is already settled", async () => {
    const state = stateFixture();
    state.teams = [
      teamFixture({
        agents: [
          teamAgent({
            id: "leader-agent",
            slot_id: "leader",
            role: "leader",
            agent_name: "队长",
          }),
          teamAgent({
            id: "product-agent",
            slot_id: "product",
            role: "teammate",
            agent_name: "产品经理",
            status: "active",
            session_id: "product-session",
            conversation_id: "product-session",
            metadata_json: { wake: { in_progress: false, last_woke_at: "2026-05-23T08:00:02Z" } },
            session_messages: [
              agentMessage({ id: "product-user-turn", role: "user", content: "请设计团队窗口" }),
              agentMessage({
                id: "product-assistant-turn",
                role: "assistant",
                content: "正常回复已经完成",
                metadata_json: { event: "team_agent_model_response" },
                created_at: "2026-05-23T08:00:02Z",
              }),
            ],
          }),
        ],
        messages: [],
      }),
    ];
    const fetchMock = routeTeamApis(state);

    renderWithClient(
      <Routes>
        <Route path="/teams/:teamId" element={<TeamPage />} />
      </Routes>,
      fetchMock,
      ["/teams/team-1"],
    );

    const productTab = await screen.findByRole("tab", { name: /产品经理/ });
    const productColumn = await screen.findByRole("region", { name: /产品经理 成员 列/ });
    expect(await within(productColumn).findByText("正常回复已经完成")).toBeInTheDocument();
    expect(within(productColumn).queryByText("正在生成...")).not.toBeInTheDocument();
    expect(within(productColumn).queryByText("协作中")).not.toBeInTheDocument();
    expect(within(productTab).getByText("待命")).toBeInTheDocument();
  });

  it("does not show generating for stale active agents without wake state", async () => {
    const state = stateFixture();
    state.teams = [
      teamFixture({
        agents: [
          teamAgent({
            id: "leader-agent",
            slot_id: "leader",
            role: "leader",
            agent_name: "队长",
          }),
          teamAgent({
            id: "product-agent",
            slot_id: "product",
            role: "teammate",
            agent_name: "产品经理",
            status: "active",
            session_id: "product-session",
            conversation_id: "product-session",
            metadata_json: {},
            session_messages: [
              agentMessage({ id: "product-user-turn", role: "user", content: "请设计团队窗口" }),
              agentMessage({
                id: "product-assistant-turn",
                role: "assistant",
                content: "回复已经结束但后端旧状态还是 active",
                metadata_json: { event: "team_agent_model_response" },
                created_at: "2026-05-23T08:00:02Z",
              }),
            ],
          }),
        ],
        messages: [],
      }),
    ];
    const fetchMock = routeTeamApis(state);

    renderWithClient(
      <Routes>
        <Route path="/teams/:teamId" element={<TeamPage />} />
      </Routes>,
      fetchMock,
      ["/teams/team-1"],
    );

    const productTab = await screen.findByRole("tab", { name: /产品经理/ });
    const productColumn = await screen.findByRole("region", { name: /产品经理 成员 列/ });
    expect(await within(productColumn).findByText("回复已经结束但后端旧状态还是 active")).toBeInTheDocument();
    expect(within(productColumn).queryByText("正在生成...")).not.toBeInTheDocument();
    expect(within(productColumn).queryByText("协作中")).not.toBeInTheDocument();
    expect(within(productTab).getByText("待命")).toBeInTheDocument();
  });

  it("does not stay generating when an old wake flag remains after the assistant reply", async () => {
    const state = stateFixture();
    state.teams = [
      teamFixture({
        agents: [
          teamAgent({
            id: "leader-agent",
            slot_id: "leader",
            role: "leader",
            agent_name: "队长",
          }),
          teamAgent({
            id: "product-agent",
            slot_id: "product",
            role: "teammate",
            agent_name: "产品经理",
            status: "active",
            session_id: "product-session",
            conversation_id: "product-session",
            metadata_json: { wake: { in_progress: true } },
            session_messages: [
              agentMessage({ id: "product-user-turn", role: "user", content: "请设计团队窗口" }),
              agentMessage({
                id: "product-assistant-turn",
                role: "assistant",
                content: "回复完成但旧 wake 还在",
                metadata_json: { event: "team_agent_model_response" },
                created_at: "2026-05-23T08:00:02Z",
              }),
            ],
          }),
        ],
        messages: [],
      }),
    ];
    const fetchMock = routeTeamApis(state);

    renderWithClient(
      <Routes>
        <Route path="/teams/:teamId" element={<TeamPage />} />
      </Routes>,
      fetchMock,
      ["/teams/team-1"],
    );

    const productTab = await screen.findByRole("tab", { name: /产品经理/ });
    const productColumn = await screen.findByRole("region", { name: /产品经理 成员 列/ });
    expect(await within(productColumn).findByText("回复完成但旧 wake 还在")).toBeInTheDocument();
    expect(within(productColumn).queryByText("正在生成...")).not.toBeInTheDocument();
    expect(within(productColumn).queryByText("协作中")).not.toBeInTheDocument();
    expect(within(productColumn).queryByRole("button", { name: "停止生成" })).not.toBeInTheDocument();
    expect(within(productTab).getByText("待命")).toBeInTheDocument();
  });

  it("stops an in-flight wake stream and clears the generating state", async () => {
    const user = userEvent.setup();
    const state = stateFixture();
    state.wakeStreamChunks = [
      sseFrame("status", {
        agent: {
          ...state.teams[0].agents.find((agent) => agent.slot_id === "product")!,
          status: "active",
          metadata_json: { wake: { in_progress: true } },
          session_messages: [],
        },
      }),
      sseFrame("delta", { slot_id: "product", content: "生成中" }),
      sseFrame("delta", { slot_id: "product", content: "后续内容" }),
    ];
    state.wakeStreamDelayMs = 60_000;
    const fetchMock = routeTeamApis(state);

    renderWithClient(
      <Routes>
        <Route path="/teams/:teamId" element={<TeamPage />} />
      </Routes>,
      fetchMock,
      ["/teams/team-1"],
    );

    const productColumn = await screen.findByRole("region", { name: /产品经理 成员 列/ });
    await user.type(within(productColumn).getByRole("textbox"), "触发流式回复{Enter}");

    expect(await within(productColumn).findByText("正在生成...")).toBeInTheDocument();
    const stopButton = await within(productColumn).findByRole("button", { name: "停止生成" });
    expect(within(productColumn).getAllByRole("button", { name: "停止生成" })).toHaveLength(1);
    expect(within(screen.getByTestId("team-composer-product")).getByRole("button", { name: "停止生成" })).toBe(
      stopButton,
    );
    await user.click(stopButton);

    await waitFor(() => {
      expect(within(productColumn).queryByText("正在生成...")).not.toBeInTheDocument();
      expect(within(productColumn).queryByText("协作中")).not.toBeInTheDocument();
      expect(within(productColumn).queryByRole("button", { name: "停止生成" })).not.toBeInTheDocument();
    });
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          requestPath(input) === "/api/teams/team-1/agents/product/wake/cancel" &&
          init?.method === "POST",
      ),
    ).toBe(true);
    expect(
      fetchMock.mock.calls.filter(
        ([input, init]) =>
          requestPath(input) === "/api/teams/team-1/agents/product/wake" &&
          init?.method === "POST",
      ),
    ).toHaveLength(0);
  });
});
