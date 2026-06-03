/**
 * L2 Mocked Browser Test: Team Mode smoke
 *
 * Proves Team Mode can create a team session, send user commands through
 * the leader entrypoint, display teammate columns, and keep desktop/mobile
 * layouts usable.
 */
import { expect, test, type Page, type Request, type Route } from "@playwright/test";

import type {
  AgentDefinition,
  AgentMessage,
  Team,
  TeamAgent,
  TeamMailboxMessage,
  TeamTask,
} from "../src/features/tasks/api";

const API_RE = /http:\/\/(?:127\.0\.0\.1|localhost):(?:8000|5173|5177|15174)\/api\/.*/;
const now = "2026-05-23T08:00:00.000Z";

type TeamState = {
  teams: Team[];
  nextId: number;
  lastCreateTeamPayload: Record<string, unknown> | null;
  lastAddAgentPayload: Record<string, unknown> | null;
  lastMessagePayload: Record<string, unknown> | null;
  lastTaskPayload: Record<string, unknown> | null;
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
    description: "团队模式队长",
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
    to_agent_slot_id: "leader",
    from_agent_slot_id: "product",
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
    session_id: "leader-session",
    agent_id: "default",
    role: "assistant",
    content: "团队模式已处理这条消息",
    metadata_json: {},
    created_at: now,
    ...overrides,
  };
}

function mirrorMailboxToSession(agent: TeamAgent, message: TeamMailboxMessage) {
  const sessionId = agent.session_id ?? agent.conversation_id ?? `${agent.slot_id}-session`;
  agent.session_id = sessionId;
  agent.conversation_id = agent.conversation_id ?? sessionId;
  agent.session_messages = [
    ...(agent.session_messages ?? []),
    agentMessage({
      id: `mailbox-${message.id}`,
      session_id: sessionId,
      agent_id: agent.agent_id,
      role: ["system", "idle_notification", "shutdown_request"].includes(message.type)
        ? "system"
        : "user",
      content: message.content,
      metadata_json: {
        team_id: message.team_id,
        mailbox_message_id: message.id,
        from_agent_slot_id: message.from_agent_slot_id,
        to_agent_slot_id: message.to_agent_slot_id,
        message_type: message.type,
        summary: message.summary,
        read: message.read,
      },
      created_at: message.created_at ?? now,
    }),
  ];
}

function teamTask(overrides: Partial<TeamTask>): TeamTask {
  const id = overrides.id ?? "task-1";
  return {
    id,
    team_id: "team-1",
    subject: "实现多列 UI",
    description: "复刻 AionUi 的横向多代理列",
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
  });
  return {
    id: "team-1",
    organization_id: "dev-org",
    name: "Aion 协作团队",
    status: "ACTIVE",
    workspace: "/tmp/harness-team",
    workspace_mode: "shared",
    leader_slot_id: "leader",
    created_by: "dev-user",
    agents: [leader, product],
    messages: [teamMessage({})],
    tasks: [teamTask({})],
    unread_counts: { product: 1 },
    team_tools: [
      "team_send_message",
      "team_task_create",
      "team_task_update",
      "team_members",
      "team_spawn_agent",
      "team_shutdown_agent",
    ],
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function createdTeamFixture(payload: Record<string, unknown>): Team {
  const name = typeof payload.name === "string" && payload.name.trim().length > 0
    ? payload.name.trim()
    : "Aion 协作团队";
  const leaderName = typeof payload.leader_name === "string" && payload.leader_name.trim().length > 0
    ? payload.leader_name.trim()
    : "队长";
  const leaderAgentId = typeof payload.leader_agent_id === "string" && payload.leader_agent_id.trim().length > 0
    ? payload.leader_agent_id.trim()
    : "default";

  return {
    id: "team-created",
    organization_id: "dev-org",
    name,
    status: "ACTIVE",
    workspace: "/tmp/harness-team-created",
    workspace_mode: "shared",
    leader_slot_id: "leader",
    created_by: "dev-user",
    agents: [
      teamAgent({
        id: "created-leader-agent",
      team_id: "team-created",
      slot_id: "leader",
      role: "leader",
      agent_id: leaderAgentId,
      agent_name: leaderName,
      session_id: "created-leader-session",
      conversation_id: "created-leader-session",
    }),
    ],
    messages: [],
    tasks: [],
    unread_counts: {},
    team_tools: [
      "team_send_message",
      "team_task_create",
      "team_task_update",
      "team_members",
      "team_spawn_agent",
      "team_shutdown_agent",
    ],
    created_at: now,
    updated_at: now,
  };
}

function stateFixture(): TeamState {
  return {
    teams: [teamFixture()],
    nextId: 10,
    lastCreateTeamPayload: null,
    lastAddAgentPayload: null,
    lastMessagePayload: null,
    lastTaskPayload: null,
  };
}

function parseBody<T>(request: Request): T {
  return (request.postDataJSON() ?? {}) as T;
}

function routeTeamApis(state: TeamState) {
  return async (route: Route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    if (path === "/api/agents" && method === "GET") {
      await json(route, { items: [agentDefinition()], next_cursor: null });
      return;
    }

    if (path === "/api/tools/registry" && method === "GET") {
      if (url.searchParams.get("agent_id") !== "default") {
        await json(route, { detail: "missing expected agent_id=default" }, 400);
        return;
      }
      await json(route, { items: [], categories: [], sources: [] });
      return;
    }

    if (path === "/api/teams" && method === "GET") {
      await json(route, { items: clone(state.teams), next_cursor: null });
      return;
    }

    if (path === "/api/teams" && method === "POST") {
      const payload = parseBody<Record<string, unknown>>(route.request());
      state.lastCreateTeamPayload = payload;
      const team = createdTeamFixture(payload);
      state.teams.unshift(team);
      await json(route, team, 201);
      return;
    }

    const teamMatch = path.match(/^\/api\/teams\/([^/]+)$/);
    if (teamMatch && method === "GET") {
      const team = state.teams.find((candidate) => candidate.id === teamMatch[1]);
      await json(route, team ?? { detail: "not found" }, team ? 200 : 404);
      return;
    }

    const streamMatch = path.match(/^\/api\/teams\/([^/]+)\/stream$/);
    if (streamMatch && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream; charset=utf-8",
        body: "",
      });
      return;
    }

    const tasksMatch = path.match(/^\/api\/teams\/([^/]+)\/tasks$/);
    if (tasksMatch && method === "GET") {
      const team = state.teams.find((candidate) => candidate.id === tasksMatch[1]);
      await json(route, team?.tasks ?? [], team ? 200 : 404);
      return;
    }
    if (tasksMatch && method === "POST") {
      const team = state.teams.find((candidate) => candidate.id === tasksMatch[1]);
      if (!team) {
        await json(route, { detail: "not found" }, 404);
        return;
      }
      const payload = parseBody<{ subject: string; description?: string; owner_slot_id?: string | null }>(route.request());
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
      await json(route, task, 201);
      return;
    }

    const taskPatchMatch = path.match(/^\/api\/teams\/([^/]+)\/tasks\/([^/]+)$/);
    if (taskPatchMatch && method === "PATCH") {
      const team = state.teams.find((candidate) => candidate.id === taskPatchMatch[1]);
      const task = team?.tasks.find((candidate) => candidate.id === taskPatchMatch[2]);
      if (!team || !task) {
        await json(route, { detail: "not found" }, 404);
        return;
      }
      const payload = parseBody<Partial<TeamTask>>(route.request());
      Object.assign(task, payload, { updated_at: now });
      await json(route, task);
      return;
    }

    const agentsMatch = path.match(/^\/api\/teams\/([^/]+)\/agents$/);
    if (agentsMatch && method === "POST") {
      const team = state.teams.find((candidate) => candidate.id === agentsMatch[1]);
      if (!team) {
        await json(route, { detail: "not found" }, 404);
        return;
      }
      const payload = parseBody<{ agent_id?: string; agent_name: string; role?: string }>(route.request());
      state.lastAddAgentPayload = payload;
      const slotId = `teammate-${state.nextId++}`;
      const agent = teamAgent({
        id: `${slotId}-agent`,
        team_id: team.id,
        slot_id: slotId,
        agent_id: payload.agent_id ?? "default",
        role: "teammate",
        agent_name: payload.agent_name,
        status: "idle",
        session_id: `${slotId}-session`,
        conversation_id: `${slotId}-session`,
      });
      team.agents.push(agent);
      team.updated_at = now;
      await json(route, agent, 201);
      return;
    }

    const messageMatch = path.match(/^\/api\/teams\/([^/]+)\/messages$/);
    if (messageMatch && method === "POST") {
      const team = state.teams.find((candidate) => candidate.id === messageMatch[1]);
      if (!team) {
        await json(route, { detail: "not found" }, 404);
        return;
      }
      const payload = parseBody<{ target: string; content: string; from_agent_slot_id?: string; type?: string }>(route.request());
      state.lastMessagePayload = payload;
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
          team_id: team.id,
          to_agent_slot_id: slotId,
          from_agent_slot_id: payload.from_agent_slot_id ?? "user",
          type: payload.type ?? "message",
          content: payload.content,
          summary: null,
          read: false,
          files_json: [],
          metadata_json: {},
          created_at: now,
        }),
      );
      team.messages.push(...messages);
      recipients.forEach((slotId) => {
        team.unread_counts[slotId] = (team.unread_counts[slotId] ?? 0) + 1;
        const agent = team.agents.find((candidate) => candidate.slot_id === slotId);
        const message = messages.find((candidate) => candidate.to_agent_slot_id === slotId);
        if (agent && message) {
          mirrorMailboxToSession(agent, message);
        }
      });
      team.updated_at = now;
      await json(route, messages[0], 201);
      return;
    }

    const wakeStreamMatch = path.match(/^\/api\/teams\/([^/]+)\/agents\/([^/]+)\/wake\/stream$/);
    if (wakeStreamMatch && method === "POST") {
      const team = state.teams.find((candidate) => candidate.id === wakeStreamMatch[1]);
      const agent = team?.agents.find((candidate) => candidate.slot_id === wakeStreamMatch[2]);
      if (!team || !agent) {
        await json(route, { detail: "not found" }, 404);
        return;
      }
      agent.status = "idle";
      agent.updated_at = now;
      const message = agentMessage({
        id: `assistant-${state.nextId++}`,
        session_id: agent.session_id ?? `${agent.slot_id}-session`,
        agent_id: agent.agent_id,
        role: "assistant",
        content: `回复 ${agent.agent_name}`,
        metadata_json: { event: "team_agent_model_response" },
      });
      agent.session_messages = [...(agent.session_messages ?? []), message];
      team.updated_at = now;
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream; charset=utf-8",
        body: [
          `event: status\ndata: ${JSON.stringify({ agent: { ...agent, status: "active", session_messages: [] } })}\n\n`,
          `event: delta\ndata: ${JSON.stringify({ slot_id: agent.slot_id, content: "回复" })}\n\n`,
          `event: done\ndata: ${JSON.stringify({ agent: { ...agent, session_messages: [] }, message })}\n\n`,
        ].join(""),
      });
      return;
    }

    const wakeMatch = path.match(/^\/api\/teams\/([^/]+)\/agents\/([^/]+)\/wake$/);
    if (wakeMatch && method === "POST") {
      const team = state.teams.find((candidate) => candidate.id === wakeMatch[1]);
      const agent = team?.agents.find((candidate) => candidate.slot_id === wakeMatch[2]);
      if (!team || !agent) {
        await json(route, { detail: "not found" }, 404);
        return;
      }
      agent.status = "idle";
      agent.updated_at = now;
      await json(route, agent);
      return;
    }

    const removeMatch = path.match(/^\/api\/teams\/([^/]+)\/agents\/([^/]+)$/);
    if (removeMatch && method === "DELETE") {
      const team = state.teams.find((candidate) => candidate.id === removeMatch[1]);
      const agent = team?.agents.find((candidate) => candidate.slot_id === removeMatch[2]);
      if (!team || !agent) {
        await json(route, { detail: "not found" }, 404);
        return;
      }
      agent.status = "completed";
      team.updated_at = now;
      await json(route, agent);
      return;
    }

    if (path.match(/^\/api\/teams\/[^/]+\/events$/) && method === "GET") {
      await json(route, []);
      return;
    }

    await json(route, { detail: `unexpected ${method} ${path}` }, 404);
  };
}

async function json(route: Route, payload: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}

async function fulfillTeamApis(page: Page, state: TeamState): Promise<void> {
  await page.route(API_RE, routeTeamApis(state));
}

async function hasNoHorizontalOverflow(page: Page): Promise<boolean> {
  return page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
  );
}

test.describe("Team Mode browser smoke", () => {
  test("creates a team, sends through the leader, and opens extra columns on desktop", async ({ page }) => {
    test.setTimeout(45_000);
    const state = stateFixture();
    await fulfillTeamApis(page, state);
    await page.setViewportSize({ width: 1440, height: 900 });

    await page.goto("/teams");
    await expect(page.getByText("团队模式")).toBeVisible();
    await expect(page.getByText("Aion 协作团队").first()).toBeVisible();
    await expect(page.getByText("队长").first()).toBeVisible();
    expect(await hasNoHorizontalOverflow(page)).toBe(true);

    await page.getByRole("button", { name: /创建团队/ }).click();
    const createDialog = page.getByRole("dialog", { name: "创建团队" });
    await createDialog.getByLabel("团队名称").fill("协作验证团队");
    await expect(createDialog.getByText("default · default/default")).toBeVisible();
    await createDialog.getByLabel("工作区").fill("/tmp/harness-team-created");
    await createDialog.getByRole("button", { name: /创建团队/ }).click();
    await page.waitForURL(/\/teams\/team-created$/);

    await expect.poll(() => state.lastCreateTeamPayload).toMatchObject({
      name: "协作验证团队",
      workspace: "/tmp/harness-team-created",
      workspace_mode: "shared",
      leader_agent_id: "default",
    });
    await expect(page.getByText("团队创建成功")).toBeVisible();

    const leaderColumn = page.getByRole("region", { name: /队长 队长 列/ });
    await expect(leaderColumn).toBeVisible();
    await leaderColumn.getByRole("textbox").fill("同步队长状态");
    await leaderColumn.getByRole("button", { name: "发送", exact: true }).click();

    await expect.poll(() => state.lastMessagePayload).toMatchObject({
      target: "leader",
      content: "同步队长状态",
      from_agent_slot_id: "user",
      type: "message",
    });
    await expect(
      leaderColumn.getByText("同步队长状态"),
    ).toBeVisible();
    await page.getByRole("button", { name: "添加成员" }).click();
    const addMemberDialog = page.getByRole("dialog", { name: "添加成员" });
    await expect(addMemberDialog.getByText("已选择")).toBeVisible();
    await expect(addMemberDialog.getByRole("button", { name: /智能体定义/ })).toContainText("默认智能体");
    await addMemberDialog.getByLabel("成员名称").fill("浏览器测试工程师");
    await addMemberDialog.getByRole("button", { name: "添加成员" }).click();
    await expect.poll(() => state.lastAddAgentPayload).toMatchObject({
      agent_id: "default",
      agent_name: "浏览器测试工程师",
      role: "teammate",
    });
    await expect(page.getByText("团队成员已添加")).toBeVisible();
    await expect(page.getByRole("tab", { name: /浏览器测试工程师/ })).toBeVisible();

    const team = state.teams.find((candidate) => candidate.id === "team-created");
    if (!team) throw new Error("created team missing");
    for (const name of ["产品经理", "设计", "研发", "测试"]) {
      const slotId = `mock-${name}`;
      team.agents.push(
        teamAgent({
          id: `${slotId}-agent`,
          team_id: team.id,
          slot_id: slotId,
          role: "teammate",
          agent_name: name,
        }),
      );
    }
    team.tasks.push(
      teamTask({
        id: "created-task-1",
        team_id: team.id,
        owner_slot_id: "mock-产品经理",
      }),
    );
    team.updated_at = now;
    await page.reload();
    await page.waitForURL(/\/teams\/team-created$/);

    const productColumn = page.getByRole("region", { name: /产品经理 成员 列/ });
    await expect(productColumn).toBeVisible();
    await page.getByRole("button", { name: "任务板" }).click();
    const taskBoard = page.getByRole("dialog", { name: "团队任务板" });
    await expect(taskBoard.getByText("实现多列 UI")).toBeVisible();
    await expect(taskBoard.getByText(/负责人 ·/)).toBeVisible();
    await taskBoard.getByRole("button", { name: "关闭任务板" }).click();

    await expect(productColumn.getByRole("button", { name: /发送目标/ })).toHaveCount(0);
    await productColumn.getByRole("textbox").fill("直发产品经理邮箱");
    const messageCountBeforeDirectSend = state.teams.reduce((count, item) => count + item.messages.length, 0);
    await Promise.all([
      productColumn.getByRole("button", { name: "发送", exact: true }).click(),
      productColumn.getByRole("button", { name: "发送", exact: true }).click().catch(() => undefined),
    ]);
    await expect.poll(() => state.lastMessagePayload).toMatchObject({
      target: "mock-产品经理",
      content: "直发产品经理邮箱",
      from_agent_slot_id: "user",
      type: "message",
    });
    expect(
      state.teams.reduce((count, item) => count + item.messages.length, 0) - messageCountBeforeDirectSend,
    ).toBe(1);
    await expect(page.getByRole("tab")).toHaveCount(6);
    await expect(page.getByRole("tablist", { name: "代理切换" })).toBeVisible();

    const columns = page.getByRole("group", { name: "代理会话列" });
    const metrics = await columns.evaluate((node) => ({
      scrollWidth: node.scrollWidth,
      clientWidth: node.clientWidth,
      visibleColumns: [...node.querySelectorAll('[role="region"]')].filter((element) => {
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && rect.left < window.innerWidth && rect.right > 0;
      }).length,
    }));
    expect(metrics.scrollWidth).toBeGreaterThan(metrics.clientWidth);
    expect(metrics.visibleColumns).toBeGreaterThanOrEqual(4);
    expect(await hasNoHorizontalOverflow(page)).toBe(true);

    await productColumn.getByRole("button", { name: "切换全屏列" }).click();
    await expect(productColumn).toBeVisible();
    await expect(leaderColumn).not.toBeVisible();
    await expect(page.getByRole("region", { name: /设计 成员 列/ })).not.toBeVisible();
    expect(await hasNoHorizontalOverflow(page)).toBe(true);
    await productColumn.getByRole("button", { name: "切换全屏列" }).click();
    await expect(leaderColumn).toBeVisible();

    await productColumn.locator("summary").click();
    await expect(productColumn.getByText("实现多列 UI")).toBeVisible();
  });

  test("keeps the mobile layout single-column and sendable without overflow", async ({ page }) => {
    const state = stateFixture();
    await fulfillTeamApis(page, state);
    await page.setViewportSize({ width: 390, height: 844 });

    await page.goto("/teams/team-1");
    await expect(page.getByText("Aion 协作团队").first()).toBeVisible();
    await expect(page.getByRole("tab", { name: /产品经理/ })).toBeVisible();

    await page.getByRole("tab", { name: /产品经理/ }).click();
    const productColumn = page.getByRole("region", { name: /产品经理 成员 列/ });
    await expect(productColumn).toBeVisible();
    expect(await hasNoHorizontalOverflow(page)).toBe(true);

    await page.getByRole("tab", { name: /队长/ }).click();
    const leaderColumn = page.getByRole("region", { name: /队长 队长 列/ });
    await leaderColumn.getByRole("textbox").fill("移动端验证");
    await leaderColumn.getByRole("button", { name: "发送", exact: true }).click();

    await expect.poll(() => state.lastMessagePayload).toMatchObject({
      target: "leader",
      content: "移动端验证",
      from_agent_slot_id: "user",
      type: "message",
    });
    await expect(leaderColumn.getByText("移动端验证")).toBeVisible();
    expect(await hasNoHorizontalOverflow(page)).toBe(true);
  });
});
