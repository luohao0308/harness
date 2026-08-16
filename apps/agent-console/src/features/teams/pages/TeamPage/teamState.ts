import type {
  AgentMessage,
  Team,
  TeamAgent,
  TeamEvent,
  TeamGoal,
  TeamMailboxMessage,
  TeamTask,
} from "../../../tasks/api";

import type { SettledWakeCutoffs, StreamingWake, TeamPageEnvelope } from "./types";

export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object");
}

export function isTeamAgent(value: unknown): value is TeamAgent {
  return Boolean(isRecord(value) && "slot_id" in value && "agent_name" in value);
}

export function isTeamMessage(value: unknown): value is TeamMailboxMessage {
  return Boolean(isRecord(value) && "to_agent_slot_id" in value && "content" in value);
}

export function isAgentMessage(value: unknown): value is AgentMessage {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.session_id === "string" &&
    typeof value.agent_id === "string" &&
    (value.role === "user" || value.role === "assistant" || value.role === "system") &&
    typeof value.content === "string" &&
    isRecord(value.metadata_json) &&
    typeof value.created_at === "string"
  );
}

export function isTeamTask(value: unknown): value is TeamTask {
  return Boolean(isRecord(value) && "subject" in value && "status" in value);
}

export function isTeamGoal(value: unknown): value is TeamGoal {
  return Boolean(isRecord(value) && "objective" in value && "status" in value && "version" in value);
}

export function isTerminalTeamGoalStatus(status: string) {
  return status === "completed" || status === "failed" || status === "blocked";
}

export function upsertById<T>(items: T[], item: T, idOf: (value: T) => string) {
  const next = [...items];
  const index = next.findIndex((candidate) => idOf(candidate) === idOf(item));
  if (index === -1) {
    next.push(item);
  } else {
    next[index] = item;
  }
  return next;
}

export function timestampMs(value: string | null | undefined) {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function latestAssistantMessageMs(agent: TeamAgent) {
  return agentSessionMessages(agent).reduce<number | null>((latest, message) => {
    if (message.role !== "assistant") return latest;
    const createdAt = timestampMs(message.created_at);
    if (createdAt === null) return latest;
    return Math.max(latest ?? 0, createdAt);
  }, null);
}

export function latestSessionRole(agent: TeamAgent) {
  const messages = agentSessionMessages(agent);
  return messages[messages.length - 1]?.role ?? null;
}

export function hasTerminalAssistantTurn(agent: TeamAgent) {
  return latestSessionRole(agent) === "assistant";
}

export function assistantSettledWithoutWakeStartMs(agent: TeamAgent) {
  const wake = isRecord(agent.metadata_json?.wake) ? agent.metadata_json.wake : null;
  if (wake?.in_progress !== true) return null;
  if (typeof wake.started_at === "string" && timestampMs(wake.started_at) !== null) return null;
  return hasTerminalAssistantTurn(agent) ? latestAssistantMessageMs(agent) : null;
}

export function assistantAfterWakeStartMs(agent: TeamAgent) {
  const wake = isRecord(agent.metadata_json?.wake) ? agent.metadata_json.wake : null;
  if (typeof wake?.started_at !== "string") return null;
  const startedAt = timestampMs(wake.started_at);
  if (startedAt === null) return null;
  const assistantAt = latestAssistantMessageMs(agent);
  return assistantAt !== null && assistantAt >= startedAt ? assistantAt : null;
}

export function assistantSettledWakeCutoffMs(agent: TeamAgent) {
  const wake = isRecord(agent.metadata_json?.wake) ? agent.metadata_json.wake : null;
  if (wake?.in_progress !== true) return null;
  return assistantAfterWakeStartMs(agent) ?? assistantSettledWithoutWakeStartMs(agent);
}

export function hasCompletedWakeTurn(
  agent: TeamAgent,
  pendingWakeSlotIds: string[] = [],
  streamingWakes: StreamingWake[] = [],
) {
  if (assistantAfterWakeStartMs(agent) !== null) return true;
  if (
    pendingWakeSlotIds.includes(agent.slot_id) ||
    streamingWakes.some((wake) => wake.slotId === agent.slot_id && !wake.error)
  ) {
    return false;
  }
  return assistantSettledWithoutWakeStartMs(agent) !== null;
}

export function isStaleAgentUpdate(existing: TeamAgent | undefined, incoming: TeamAgent) {
  if (!existing) return false;
  const existingMs = timestampMs(existing.updated_at);
  const incomingMs = timestampMs(incoming.updated_at);
  if (existingMs === null || incomingMs === null) return false;
  if (incomingMs < existingMs) return true;
  return incomingMs === existingMs && incoming.status === "active" && existing.status !== "active";
}

export function mergeTeamAgent(agents: TeamAgent[], incoming: TeamAgent) {
  const existing = agents.find((agent) => agent.slot_id === incoming.slot_id);
  if (isStaleAgentUpdate(existing, incoming)) {
    return agents;
  }
  const incomingMessages = Array.isArray(incoming.session_messages)
    ? incoming.session_messages
    : undefined;
  const existingMessages = existing?.session_messages ?? [];
  const sessionMessages =
    incomingMessages && incomingMessages.length > 0
      ? incomingMessages.reduce(
          (messages, message) => upsertById(messages, message, agentMessageStableKey),
          existingMessages,
        )
      : existingMessages;
  return upsertById(
    agents,
    {
      ...existing,
      ...incoming,
      session_messages: sessionMessages,
    },
    (agent) => agent.slot_id,
  );
}

export function normalizeSettledAgent(agent: TeamAgent, settledWakeCutoffs: SettledWakeCutoffs) {
  const wake = isRecord(agent.metadata_json?.wake) ? agent.metadata_json.wake : null;
  const assistantCutoff = assistantSettledWakeCutoffMs(agent);
  if (assistantCutoff !== null && agent.status === "active") {
    return {
      ...agent,
      status: "idle" as const,
      metadata_json: {
        ...agent.metadata_json,
        wake: {
          ...(isRecord(agent.metadata_json?.wake) ? agent.metadata_json.wake : {}),
          in_progress: false,
        },
      },
    };
  }
  if (agent.status === "active" && wake?.in_progress !== true) {
    return { ...agent, status: "idle" as const };
  }
  const cutoff = settledWakeCutoffs[agent.slot_id];
  if (!cutoff || agent.status !== "active") return agent;
  const updatedAt = timestampMs(agent.updated_at);
  if (updatedAt === null || updatedAt > cutoff) return agent;
  return {
    ...agent,
    status: "idle" as const,
    metadata_json: {
      ...agent.metadata_json,
      wake: {
        ...(isRecord(agent.metadata_json?.wake) ? agent.metadata_json.wake : {}),
        in_progress: false,
      },
    },
  };
}

export function settledWakeAgent(agent: TeamAgent) {
  return {
    ...agent,
    status: "idle" as const,
    metadata_json: {
      ...agent.metadata_json,
      wake: {
        ...(isRecord(agent.metadata_json?.wake) ? agent.metadata_json.wake : {}),
        in_progress: false,
      },
    },
  };
}

export function isSettledWakeSnapshot(agent: TeamAgent, settledWakeCutoffs: SettledWakeCutoffs) {
  const cutoff = settledWakeCutoffs[agent.slot_id];
  if (!cutoff) return false;
  const updatedAt = timestampMs(agent.updated_at);
  return updatedAt === null || updatedAt <= cutoff;
}

export function agentWakeInProgress(agent: TeamAgent, settledWakeCutoffs: SettledWakeCutoffs = {}) {
  if (isSettledWakeSnapshot(agent, settledWakeCutoffs)) return false;
  const wake = isRecord(agent.metadata_json?.wake) ? agent.metadata_json.wake : null;
  return agent.status === "active" && wake?.in_progress === true;
}

export function displayAgentStatus(
  agent: TeamAgent,
  pendingWakeSlotIds: string[],
  streamingWakes: StreamingWake[],
  settledWakeCutoffs: SettledWakeCutoffs = {},
) {
  const completedWakeTurn = hasCompletedWakeTurn(agent, pendingWakeSlotIds, streamingWakes);
  const hasLocalWake =
    !completedWakeTurn &&
    (pendingWakeSlotIds.includes(agent.slot_id) ||
      streamingWakes.some((wake) => wake.slotId === agent.slot_id && !wake.error));
  if (hasLocalWake) return "active";
  if (completedWakeTurn) return agent.status === "active" ? "idle" : agent.status;
  if (
    !completedWakeTurn &&
    agentWakeInProgress(agent, settledWakeCutoffs)
  ) {
    return "active";
  }
  return agent.status === "active" && !agentWakeInProgress(agent, settledWakeCutoffs) ? "idle" : agent.status;
}

export function normalizeSettledTeam(team: Team | null, settledWakeCutoffs: SettledWakeCutoffs) {
  if (!team) return team;
  let changed = false;
  const agents = team.agents.map((agent) => {
    const next = normalizeSettledAgent(agent, settledWakeCutoffs);
    if (next !== agent) changed = true;
    return next;
  });
  return changed ? { ...team, agents } : team;
}

export function unreadCounts(messages: TeamMailboxMessage[]) {
  return messages.reduce<Record<string, number>>((counts, message) => {
    if (!message.read) {
      counts[message.to_agent_slot_id] = (counts[message.to_agent_slot_id] ?? 0) + 1;
    }
    return counts;
  }, {});
}

export function agentMessageFromMailbox(agent: TeamAgent, message: TeamMailboxMessage): AgentMessage {
  const role = message.type === "idle_notification" || message.type === "shutdown_request" || message.type === "system"
    ? "system"
    : "user";
  return {
    id: `mailbox-${message.id}`,
    session_id: agent.session_id ?? agent.conversation_id ?? "",
    agent_id: agent.agent_id,
    role,
    content: message.content,
    metadata_json: {
      ...(isRecord(message.metadata_json) ? message.metadata_json : {}),
      team_id: message.team_id,
      mailbox_message_id: message.id,
      from_agent_slot_id: message.from_agent_slot_id,
      to_agent_slot_id: message.to_agent_slot_id,
      message_type: message.type,
      summary: message.summary,
      read: message.read,
    },
    created_at: message.created_at ?? new Date().toISOString(),
  };
}

export function agentSessionMessages(agent: TeamAgent) {
  return Array.isArray(agent.session_messages) ? agent.session_messages : [];
}

export function agentMessageMailboxId(message: AgentMessage) {
  const metadata = isRecord(message.metadata_json) ? message.metadata_json : null;
  const mailboxMessageId = metadata?.mailbox_message_id;
  return typeof mailboxMessageId === "string" && mailboxMessageId.length > 0
    ? mailboxMessageId
    : null;
}

export function agentMessageStableKey(message: AgentMessage) {
  const mailboxMessageId = agentMessageMailboxId(message);
  return mailboxMessageId ? `mailbox:${mailboxMessageId}` : `message:${message.id}`;
}

export function agentMessageNodeId(message: AgentMessage) {
  const mailboxMessageId = agentMessageMailboxId(message);
  return mailboxMessageId ? `mailbox-${mailboxMessageId}` : message.id;
}

export function appendMailboxToRecipientSession(team: Team, message: TeamMailboxMessage) {
  return team.agents.map((agent) => {
    if (agent.slot_id !== message.to_agent_slot_id) return agent;
    const mirrored = agentMessageFromMailbox(agent, message);
    return {
      ...agent,
      session_messages: upsertById(agentSessionMessages(agent), mirrored, agentMessageStableKey),
    };
  });
}

export function appendSessionMessagesToAgent(team: Team, payload: Record<string, unknown>) {
  const slotId = typeof payload.slot_id === "string" ? payload.slot_id : null;
  const rawMessages = Array.isArray(payload.messages) ? payload.messages : [];
  if (!slotId || rawMessages.length === 0) return null;
  const newSessionMessages = rawMessages.filter(isAgentMessage);
  if (newSessionMessages.length === 0) return null;
  return team.agents.map((agent) => {
    if (agent.slot_id !== slotId) return agent;
    return {
      ...agent,
      session_messages: newSessionMessages.reduce(
        (messages, message) => upsertById(messages, message, agentMessageStableKey),
        agentSessionMessages(agent),
      ),
    };
  });
}

export function appendSessionMessageToAgent(team: Team, slotId: string, message: AgentMessage) {
  return team.agents.map((agent) => {
    if (agent.slot_id !== slotId) return agent;
    return {
      ...agent,
      session_messages: upsertById(agentSessionMessages(agent), message, agentMessageStableKey),
    };
  });
}

export function completedWakeSlotIdFromTeamEvent(event: TeamEvent) {
  if (event.event_type !== "TEAM_AGENT_SESSION_MESSAGE") return null;
  const slotId = typeof event.payload_json.slot_id === "string" ? event.payload_json.slot_id : null;
  const messages = Array.isArray(event.payload_json.messages) ? event.payload_json.messages : [];
  if (!slotId) return null;
  return messages.some((message) => isAgentMessage(message) && message.role === "assistant")
    ? slotId
    : null;
}

export function applyTeamEventToTeam(team: Team, event: TeamEvent): Team | null {
  const payload = event.payload_json;
  switch (event.event_type) {
    case "TEAM_RENAMED": {
      const name = typeof payload.name === "string" ? payload.name : team.name;
      return { ...team, name, updated_at: event.created_at ?? team.updated_at };
    }
    case "TEAM_ARCHIVED":
      return { ...team, status: "ARCHIVED", updated_at: event.created_at ?? team.updated_at };
    case "TEAM_AGENT_SPAWNED":
    case "TEAM_AGENT_STATUS":
    case "TEAM_AGENT_WAKE":
    case "TEAM_AGENT_INACTIVITY_TIMEOUT":
    case "TEAM_AGENT_CRASHED": {
      const agent = payload.agent;
      if (!isTeamAgent(agent)) return null;
      const messages = isTeamMessage(payload.message)
        ? upsertById(team.messages, payload.message, (message) => message.id)
        : team.messages;
      return {
        ...team,
        agents: mergeTeamAgent(team.agents, agent),
        messages,
        unread_counts: unreadCounts(messages),
        updated_at: event.created_at ?? team.updated_at,
      };
    }
    case "TEAM_AGENT_RENAMED": {
      const slotId = typeof payload.slot_id === "string" ? payload.slot_id : "";
      const newName = typeof payload.new_name === "string" ? payload.new_name : "";
      if (!slotId || !newName) return null;
      return {
        ...team,
        agents: team.agents.map((agent) =>
          agent.slot_id === slotId ? { ...agent, agent_name: newName } : agent,
        ),
        updated_at: event.created_at ?? team.updated_at,
      };
    }
    case "TEAM_AGENT_REMOVED": {
      const agent = payload.agent;
      if (!isTeamAgent(agent)) return null;
      return {
        ...team,
        agents: team.agents.filter((candidate) => candidate.slot_id !== agent.slot_id),
        updated_at: event.created_at ?? team.updated_at,
      };
    }
    case "TEAM_MESSAGE_CREATED": {
      const message = payload.message;
      if (!isTeamMessage(message)) return null;
      const messages = upsertById(team.messages, message, (candidate) => candidate.id);
      return {
        ...team,
        agents: appendMailboxToRecipientSession(team, message),
        messages,
        unread_counts: unreadCounts(messages),
        updated_at: event.created_at ?? team.updated_at,
      };
    }
    case "TEAM_AGENT_SESSION_MESSAGE": {
      const agents = appendSessionMessagesToAgent(team, payload);
      if (!agents) return null;
      return { ...team, agents, updated_at: event.created_at ?? team.updated_at };
    }
    case "TEAM_MAILBOX_READ": {
      const messageIds = Array.isArray(payload.message_ids)
        ? payload.message_ids.filter((value): value is string => typeof value === "string")
        : [];
      if (messageIds.length === 0) return null;
      const readIds = new Set(messageIds);
      const messages = team.messages.map((message) =>
        readIds.has(message.id) ? { ...message, read: true } : message,
      );
      return {
        ...team,
        messages,
        unread_counts: unreadCounts(messages),
        updated_at: event.created_at ?? team.updated_at,
      };
    }
    case "TEAM_TASK_CREATED":
    case "TEAM_TASK_UPDATED": {
      const task = payload.task;
      if (!isTeamTask(task)) return null;
      const tasks =
        task.status === "deleted"
          ? team.tasks.filter((candidate) => candidate.id !== task.id)
          : upsertById(team.tasks, task, (candidate) => candidate.id);
      return { ...team, tasks, updated_at: event.created_at ?? team.updated_at };
    }
    case "TEAM_GOAL_CREATED":
    case "TEAM_GOAL_STARTED":
    case "TEAM_GOAL_PROGRESS": {
      const goal = payload.goal;
      if (!isTeamGoal(goal)) return null;
      const current = team.active_goal;
      if (current && current.id === goal.id && current.version > goal.version) {
        return team;
      }
      return {
        ...team,
        active_goal: isTerminalTeamGoalStatus(goal.status) ? null : goal,
        updated_at: event.created_at ?? team.updated_at,
      };
    }
    case "TEAM_GOAL_BLOCKED":
    case "TEAM_GOAL_COMPLETED":
    case "TEAM_GOAL_FAILED": {
      const goal = payload.goal;
      if (isTeamGoal(goal)) {
        return {
          ...team,
          active_goal: isTerminalTeamGoalStatus(goal.status) ? null : goal,
          updated_at: event.created_at ?? team.updated_at,
        };
      }
      return team.active_goal
        ? { ...team, active_goal: null, updated_at: event.created_at ?? team.updated_at }
        : team;
    }
    default:
      return null;
  }
}

export function applyTeamEventToTeamPage(page: TeamPageEnvelope | undefined, event: TeamEvent) {
  if (!page) return page;
  return {
    ...page,
    items: page.items.map((team) => {
      if (team.id !== event.team_id) return team;
      return applyTeamEventToTeam(team, event) ?? team;
    }),
  };
}
