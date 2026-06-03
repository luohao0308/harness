import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type JSX,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Bot,
  Brain,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  ExternalLink,
  FlaskConical,
  GitBranch,
  GripVertical,
  ListChecks,
  Loader2,
  Maximize2,
  Paperclip,
  Pencil,
  PlugZap,
  Plus,
  Target,
  Trash2,
  UsersRound,
  Wrench,
  X,
} from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card } from "../../../components/ui/card";
import { ConfigDialog } from "../../../components/ui/config-dialog";
import { useConfirmDialog } from "../../../components/ui/confirm-dialog";
import { feedbackErrorMessage, notifyFeedback } from "../../../components/ui/feedback-toast";
import { Input } from "../../../components/ui/input";
import { MenuSelect } from "../../../components/ui/menu-select";
import { useI18n } from "../../../lib/i18n";
import { statusLabel } from "../../../lib/labels";
import { cn } from "../../../lib/utils";
import type { ConversationArtifact, ConversationNode } from "../../../stores/workspaceStore";
import { ChatMessageBubble } from "../../agents/components/ChatMessageBubble";
import { BranchSwitcher } from "../../agents/components/BranchSwitcher";
import { ChatComposer, type ComposerAttachment } from "../../agents/components/ChatComposer";
import { ContextMaxTokensSlider } from "../../agents/components/ContextMaxTokensSlider";
import { ContextRing } from "../../agents/components/ContextRing";
import { ContextSummaryManager } from "../../agents/components/ContextSummaryManager";
import { InspectorDrawer } from "../../agents/components/InspectorDrawer";
import type { UsageSummary } from "../../agents/components/InspectorDrawer";
import { copyText } from "../../agents/lib/clipboard";
import { stripThinkBlocks } from "../../agents/lib/copyText";
import { AUTO_COMPRESSION_RATIO_DEFAULT, CONTEXT_MAX_TOKENS_DEFAULT } from "../../agents/lib/contextTokens";
import { estimateTextTokens } from "../../agents/lib/contextTruncation";
import {
  COMPRESSION_PROMPT_VERSION,
  SUMMARY_SCHEMA_VERSION,
  contextCompressionBranchKey,
  isCompressionSummaryUsable,
  normalizeModelId,
  selectBestCompressionSummary,
  serializeContextNode,
  uncoveredContextPath,
  type ContextCompressionSummary,
} from "../../agents/lib/contextCompression";
import type { SlashCommand } from "../../agents/lib/slashCommands";
import type { InspectorSection, WorkspaceMode } from "../../agents/lib/types";
import {
  addTeamAgent,
  cancelWakeTeamAgent,
  compressAgentWorkspaceContext,
  getTeam,
  getModelSettings,
  getToolRegistry,
  listAgents,
  listTeams,
  renameTeamAgent,
  removeTeamAgent,
  sendTeamMessage,
  streamTeamEvents,
  streamWakeTeamAgent,
  updateTeamAgent,
  wakeTeamAgent,
  type AgentDefinition,
  type AgentMessage,
  type ModelSettings,
  type Team,
  type TeamAgent,
  type TeamEvent,
  type TeamMailboxMessage,
  type TeamTask,
  type TeamWakeStreamEvent,
  type ToolMetadata,
  type WorkspaceContextCompressionResponse,
} from "../../tasks/api";
import { modelOptionDisplay, type ModelOption } from "../../agents/components/ModelPicker";
import {
  teamAgentStatusLabel,
  teamAgentStatusTone,
  teamTaskStatusLabel,
  teamTaskStatusTone,
} from "../lib/teamLabels";
import { TeamRail, TeamRailMobileStrip } from "../components/TeamRail";
import { TeamCreateModal } from "./TeamCreateModal";

type TeamComposerState = { draft: string; target?: string; mode?: WorkspaceMode };
type TeamComposerStateUpdater =
  | TeamComposerState
  | ((current: TeamComposerState) => TeamComposerState);
type ComposerState = Record<string, TeamComposerState>;
type TeamBottomPanel = "settings" | "model" | "mcp" | null;
type TextFn = (zh: string, en: string) => string;
type TeamModelChangeHandler = (slotId: string, providerId: string, modelId: string) => void;
const MAX_TEAM_ATTACHMENT_TEXT_BYTES = 120_000;

type TeamPageEnvelope = { items: Team[]; next_cursor: string | null };
type TeamMessageEntry = { kind: "session"; message: AgentMessage } | { kind: "mailbox"; message: TeamMailboxMessage };
type TeamConversationEntry = {
  node: ConversationNode;
  target: string;
  runStatus?: string;
  runCreatedAt?: string;
};
type TeamContextCompressions = Record<string, Record<string, ContextCompressionSummary>>;
type TeamBranchGroup = {
  anchorUserId: string;
  anchorContent: string;
  branchNodeIds: string[];
  hiddenUserNodeIds: string[];
  activeNodeId: string;
};
type TeamBranchGroupsBySlot = Record<string, Record<string, TeamBranchGroup>>;
type PendingSend = {
  id: string;
  key: string;
  sourceSlotId: string;
  target: string;
  content: string;
  files: string[];
  mode: WorkspaceMode;
  recipientSlotIds: string[];
};
type StreamingWake = {
  slotId: string;
  content: string;
  error?: string;
};

type SettledWakeCutoffs = Record<string, number>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object");
}

function isTeamAgent(value: unknown): value is TeamAgent {
  return Boolean(isRecord(value) && "slot_id" in value && "agent_name" in value);
}

function isTeamMessage(value: unknown): value is TeamMailboxMessage {
  return Boolean(isRecord(value) && "to_agent_slot_id" in value && "content" in value);
}

function isAgentMessage(value: unknown): value is AgentMessage {
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

function isTeamTask(value: unknown): value is TeamTask {
  return Boolean(isRecord(value) && "subject" in value && "status" in value);
}

function upsertById<T>(items: T[], item: T, idOf: (value: T) => string) {
  const next = [...items];
  const index = next.findIndex((candidate) => idOf(candidate) === idOf(item));
  if (index === -1) {
    next.push(item);
  } else {
    next[index] = item;
  }
  return next;
}

function timestampMs(value: string | null | undefined) {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function latestAssistantMessageMs(agent: TeamAgent) {
  return agentSessionMessages(agent).reduce<number | null>((latest, message) => {
    if (message.role !== "assistant") return latest;
    const createdAt = timestampMs(message.created_at);
    if (createdAt === null) return latest;
    return Math.max(latest ?? 0, createdAt);
  }, null);
}

function latestSessionRole(agent: TeamAgent) {
  const messages = agentSessionMessages(agent);
  return messages[messages.length - 1]?.role ?? null;
}

function hasTerminalAssistantTurn(agent: TeamAgent) {
  return latestSessionRole(agent) === "assistant";
}

function assistantSettledWithoutWakeStartMs(agent: TeamAgent) {
  const wake = isRecord(agent.metadata_json?.wake) ? agent.metadata_json.wake : null;
  if (wake?.in_progress !== true) return null;
  if (typeof wake.started_at === "string" && timestampMs(wake.started_at) !== null) return null;
  return hasTerminalAssistantTurn(agent) ? latestAssistantMessageMs(agent) : null;
}

function assistantAfterWakeStartMs(agent: TeamAgent) {
  const wake = isRecord(agent.metadata_json?.wake) ? agent.metadata_json.wake : null;
  if (typeof wake?.started_at !== "string") return null;
  const startedAt = timestampMs(wake.started_at);
  if (startedAt === null) return null;
  const assistantAt = latestAssistantMessageMs(agent);
  return assistantAt !== null && assistantAt >= startedAt ? assistantAt : null;
}

function assistantSettledWakeCutoffMs(agent: TeamAgent) {
  const wake = isRecord(agent.metadata_json?.wake) ? agent.metadata_json.wake : null;
  if (wake?.in_progress !== true) return null;
  return assistantAfterWakeStartMs(agent) ?? assistantSettledWithoutWakeStartMs(agent);
}

function hasCompletedWakeTurn(
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

function isStaleAgentUpdate(existing: TeamAgent | undefined, incoming: TeamAgent) {
  if (!existing) return false;
  const existingMs = timestampMs(existing.updated_at);
  const incomingMs = timestampMs(incoming.updated_at);
  if (existingMs === null || incomingMs === null) return false;
  if (incomingMs < existingMs) return true;
  return incomingMs === existingMs && incoming.status === "active" && existing.status !== "active";
}

function mergeTeamAgent(agents: TeamAgent[], incoming: TeamAgent) {
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

function normalizeSettledAgent(agent: TeamAgent, settledWakeCutoffs: SettledWakeCutoffs) {
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

function settledWakeAgent(agent: TeamAgent) {
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

function isSettledWakeSnapshot(agent: TeamAgent, settledWakeCutoffs: SettledWakeCutoffs) {
  const cutoff = settledWakeCutoffs[agent.slot_id];
  if (!cutoff) return false;
  const updatedAt = timestampMs(agent.updated_at);
  return updatedAt === null || updatedAt <= cutoff;
}

function agentWakeInProgress(agent: TeamAgent, settledWakeCutoffs: SettledWakeCutoffs = {}) {
  if (isSettledWakeSnapshot(agent, settledWakeCutoffs)) return false;
  const wake = isRecord(agent.metadata_json?.wake) ? agent.metadata_json.wake : null;
  return agent.status === "active" && wake?.in_progress === true;
}

function displayAgentStatus(
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

function normalizeSettledTeam(team: Team | null, settledWakeCutoffs: SettledWakeCutoffs) {
  if (!team) return team;
  let changed = false;
  const agents = team.agents.map((agent) => {
    const next = normalizeSettledAgent(agent, settledWakeCutoffs);
    if (next !== agent) changed = true;
    return next;
  });
  return changed ? { ...team, agents } : team;
}

function unreadCounts(messages: TeamMailboxMessage[]) {
  return messages.reduce<Record<string, number>>((counts, message) => {
    if (!message.read) {
      counts[message.to_agent_slot_id] = (counts[message.to_agent_slot_id] ?? 0) + 1;
    }
    return counts;
  }, {});
}

function agentMessageFromMailbox(agent: TeamAgent, message: TeamMailboxMessage): AgentMessage {
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

function agentSessionMessages(agent: TeamAgent) {
  return Array.isArray(agent.session_messages) ? agent.session_messages : [];
}

function agentMessageMailboxId(message: AgentMessage) {
  const metadata = isRecord(message.metadata_json) ? message.metadata_json : null;
  const mailboxMessageId = metadata?.mailbox_message_id;
  return typeof mailboxMessageId === "string" && mailboxMessageId.length > 0
    ? mailboxMessageId
    : null;
}

function agentMessageStableKey(message: AgentMessage) {
  const mailboxMessageId = agentMessageMailboxId(message);
  return mailboxMessageId ? `mailbox:${mailboxMessageId}` : `message:${message.id}`;
}

function agentMessageNodeId(message: AgentMessage) {
  const mailboxMessageId = agentMessageMailboxId(message);
  return mailboxMessageId ? `mailbox-${mailboxMessageId}` : message.id;
}

function appendMailboxToRecipientSession(team: Team, message: TeamMailboxMessage) {
  return team.agents.map((agent) => {
    if (agent.slot_id !== message.to_agent_slot_id) return agent;
    const mirrored = agentMessageFromMailbox(agent, message);
    return {
      ...agent,
      session_messages: upsertById(agentSessionMessages(agent), mirrored, agentMessageStableKey),
    };
  });
}

function appendSessionMessagesToAgent(team: Team, payload: Record<string, unknown>) {
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

function appendSessionMessageToAgent(team: Team, slotId: string, message: AgentMessage) {
  return team.agents.map((agent) => {
    if (agent.slot_id !== slotId) return agent;
    return {
      ...agent,
      session_messages: upsertById(agentSessionMessages(agent), message, agentMessageStableKey),
    };
  });
}

function completedWakeSlotIdFromTeamEvent(event: TeamEvent) {
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
    default:
      return null;
  }
}

function applyTeamEventToTeamPage(page: TeamPageEnvelope | undefined, event: TeamEvent) {
  if (!page) return page;
  return {
    ...page,
    items: page.items.map((team) => {
      if (team.id !== event.team_id) return team;
      return applyTeamEventToTeam(team, event) ?? team;
    }),
  };
}

function agentMessages(agent: TeamAgent, messages: TeamMailboxMessage[]) {
  return messages.filter(
    (message) => message.to_agent_slot_id === agent.slot_id || message.from_agent_slot_id === agent.slot_id,
  );
}

function displayMessages(agent: TeamAgent, mailboxMessages: TeamMailboxMessage[]) {
  const messages = agentSessionMessages(agent);
  if (messages.length > 0) {
    return messages.map((message): TeamMessageEntry => ({ kind: "session", message }));
  }
  return mailboxMessages.map((message): TeamMessageEntry => ({ kind: "mailbox", message }));
}

function teamConversationEntries(team: Team, agent: TeamAgent, mailboxMessages: TeamMailboxMessage[]) {
  const rawEntries = displayMessages(agent, mailboxMessages);
  const rootId = `team-${team.id}-${agent.slot_id}-root`;
  const byId = new Map<string, TeamConversationEntry>();
  const entries = rawEntries.map((entry, index): TeamConversationEntry => {
    const id = entry.kind === "session" ? agentMessageNodeId(entry.message) : `mailbox-${entry.message.id}`;
    const previous = rawEntries[index - 1];
    const previousId =
      previous === undefined
        ? rootId
        : previous.kind === "session"
          ? agentMessageNodeId(previous.message)
          : `mailbox-${previous.message.id}`;
    const message = entry.kind === "session" ? entry.message : agentMessageFromMailbox(agent, entry.message);
    const metadata = message.metadata_json ?? {};
    const runId = readString(metadata, "run_id") ?? readString(metadata, "source_run_id");
    const usage = readRecord(metadata, "usage");
    const item: TeamConversationEntry = {
      node: {
        id,
        parent_id: previousId,
        children_ids: [],
        role: message.role,
        content: message.content,
        state: "done",
        run_id: runId ?? undefined,
        metadata: {
          input_tokens:
            readNumber(metadata, "input_tokens") ??
            readNumber(usage, "input_tokens") ??
            readNumber(usage, "prompt_tokens"),
          output_tokens:
            readNumber(metadata, "output_tokens") ??
            readNumber(usage, "output_tokens") ??
            readNumber(usage, "completion_tokens"),
          cost_usd: readString(metadata, "cost_usd") ?? readString(usage, "cost_usd"),
          duration_ms: readNumber(metadata, "duration_ms") ?? readNumber(usage, "duration_ms"),
          model_call_id: readString(metadata, "model_call_id") ?? readString(usage, "model_call_id"),
          workspace_mode: readWorkspaceMode(metadata),
          knowledge_grounding: readString(metadata, "knowledge_grounding"),
        },
        tool_calls: teamToolCalls(metadata),
        artifacts: teamArtifacts(metadata, runId),
        created_at: message.created_at ?? new Date().toISOString(),
      },
      target: targetForTeamMessage(agent, metadata),
      runStatus: readString(metadata, "run_status") ?? readString(metadata, "source_run_status") ?? undefined,
      runCreatedAt: readString(metadata, "run_created_at") ?? undefined,
    };
    byId.set(id, item);
    return item;
  });
  for (let index = 0; index < entries.length - 1; index += 1) {
    entries[index].node.children_ids = [entries[index + 1].node.id];
  }
  for (const entry of entries) {
    const parentId = entry.node.parent_id;
    if (parentId && parentId !== rootId) {
      const parent = byId.get(parentId);
      if (parent && !parent.node.children_ids.includes(entry.node.id)) {
        parent.node.children_ids = [...parent.node.children_ids, entry.node.id];
      }
    }
  }
  return entries;
}

function streamingEntry(team: Team, agent: TeamAgent, wake?: StreamingWake): TeamConversationEntry {
  return {
    node: {
      id: `team-${team.id}-${agent.slot_id}-streaming`,
      parent_id: null,
      children_ids: [],
      role: "assistant",
      content: wake?.content ?? "",
      state: wake?.error ? "error" : "streaming",
      metadata: wake?.error
        ? {
            workspace_mode: "chat",
            error: {
              kind: "server",
              detail: wake.error,
              happened_at: new Date().toISOString(),
            },
          }
        : { workspace_mode: "chat" },
      tool_calls: [],
      artifacts: [],
      created_at: agent.updated_at ?? new Date().toISOString(),
    },
    target: defaultComposerTarget(agent),
  };
}

function teamComposerPlaceholder(mode: WorkspaceMode, text: TextFn) {
  switch (mode) {
    case "codex_plan":
      return text("发送规划目标...", "Send a planning goal...");
    case "plan":
      return text("发送执行目标...", "Send an execution goal...");
    case "goal":
      return text("发送追求目标...", "Send a goal to pursue...");
    case "chat":
    default:
      return text("发送消息...", "Message...");
  }
}

function teamPendingSendKey(
  slotId: string,
  target: string,
  mode: WorkspaceMode,
  content: string,
  files: string[],
) {
  return `${slotId}:${target}:${mode}:${content}:${files.join(",")}`;
}

function teamConversationEntriesWithPending(
  team: Team,
  agent: TeamAgent,
  mailboxMessages: TeamMailboxMessage[],
  pendingSends: PendingSend[],
  pendingWakeSlotIds: string[],
  streamingWakes: StreamingWake[],
  settledWakeCutoffs: SettledWakeCutoffs = {},
) {
  const entries = teamConversationEntries(team, agent, mailboxMessages);
  const streamingWake = streamingWakes.find((wake) => wake.slotId === agent.slot_id);
  const completedWakeTurn = hasCompletedWakeTurn(agent, pendingWakeSlotIds, streamingWakes);
  const hasLocalWake =
    !completedWakeTurn &&
    (Boolean(streamingWake && !streamingWake.error) || pendingWakeSlotIds.includes(agent.slot_id));
  const shouldShowStreaming =
    !completedWakeTurn &&
    (hasLocalWake ||
      agentWakeInProgress(agent, settledWakeCutoffs) ||
      pendingSends.some((send) => send.recipientSlotIds.includes(agent.slot_id)));
  if (!shouldShowStreaming) return entries;
  const lastEntry = entries[entries.length - 1];
  if (lastEntry?.node.role === "assistant" && lastEntry.node.state === "streaming") {
    return entries;
  }
  const pending = streamingEntry(team, agent, streamingWake);
  pending.node.parent_id = lastEntry?.node.id ?? `team-${team.id}-${agent.slot_id}-root`;
  if (lastEntry) {
    lastEntry.node.children_ids = [...new Set([...lastEntry.node.children_ids, pending.node.id])];
  }
  return [...entries, pending];
}

function recipientSlotIdsForTarget(team: Team, target: string, sender = "user") {
  if (target === "leader") return [team.leader_slot_id];
  if (target === "team" || target === "*") {
    return team.agents
      .filter((agent) => agent.status !== "completed" && agent.slot_id !== sender)
      .map((agent) => agent.slot_id);
  }
  return team.agents.some((agent) => agent.slot_id === target) ? [target] : [];
}

function readRecord(source: Record<string, unknown> | null | undefined, key: string): Record<string, unknown> | null {
  const value = source?.[key];
  return isRecord(value) ? value : null;
}

function readString(source: Record<string, unknown> | null | undefined, key: string): string | null {
  const value = source?.[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

function readWorkspaceMode(source: Record<string, unknown> | null | undefined): WorkspaceMode {
  const mode = readString(source, "workspace_mode");
  if (mode === "chat" || mode === "codex_plan" || mode === "plan" || mode === "goal") return mode;
  return "chat";
}

function readNumber(source: Record<string, unknown> | null | undefined, key: string): number | undefined {
  const value = source?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function targetForTeamMessage(agent: TeamAgent, metadata: Record<string, unknown>) {
  const target = readString(metadata, "to_agent_slot_id");
  if (target) return target;
  return defaultComposerTarget(agent);
}

function teamToolCalls(metadata: Record<string, unknown>): Array<Record<string, unknown>> {
  const direct = metadata.tool_calls;
  if (Array.isArray(direct)) {
    return direct.filter(isRecord);
  }
  const results = metadata.tool_results;
  if (!Array.isArray(results)) return [];
  return results.filter(isRecord).map((result, index) => ({
    tool_call_id: readString(result, "tool_call_id") ?? `team-tool-${index}`,
    tool_name: readString(result, "tool") ?? readString(result, "tool_name") ?? "team_tool",
    status: result.ok === false ? "failed" : "completed",
    output_summary: readString(result, "result"),
  }));
}

function teamArtifacts(metadata: Record<string, unknown>, runId: string | null): ConversationArtifact[] {
  const artifacts = metadata.artifacts;
  if (!Array.isArray(artifacts)) return [];
  return artifacts.filter(isRecord).map((artifact, index) => ({
    id: readString(artifact, "id") ?? `team-artifact-${index}`,
    name: readString(artifact, "name") ?? `artifact-${index + 1}`,
    artifact_type: artifactType(readString(artifact, "artifact_type")),
    status: readString(artifact, "status") ?? "ready",
    content: artifact.content ?? artifact,
    run_id: readString(artifact, "run_id") ?? runId ?? undefined,
  }));
}

function artifactType(value: string | null): ConversationArtifact["artifact_type"] {
  if (value === "code" || value === "json" || value === "diff" || value === "chart" || value === "text") {
    return value;
  }
  return "text";
}

function activeAgent(team: Team | undefined, activeSlotId: string, fallback = "leader") {
  return team?.agents.find((agent) => agent.slot_id === activeSlotId) ?? team?.agents[0] ?? team?.agents.find((agent) => agent.slot_id === fallback) ?? null;
}

function orderedTeamAgents(agents: TeamAgent[], orderedSlotIds: string[]) {
  const leader = agents.find((agent) => agent.role === "leader");
  const teammates = agents.filter((agent) => agent.role !== "leader");
  const orderIndex = new Map(orderedSlotIds.map((slotId, index) => [slotId, index]));
  const orderedTeammates = [...teammates].sort((left, right) => {
    const leftIndex = orderIndex.get(left.slot_id) ?? Number.MAX_SAFE_INTEGER;
    const rightIndex = orderIndex.get(right.slot_id) ?? Number.MAX_SAFE_INTEGER;
    if (leftIndex !== rightIndex) return leftIndex - rightIndex;
    return String(left.created_at ?? "").localeCompare(String(right.created_at ?? ""));
  });
  return leader ? [leader, ...orderedTeammates] : orderedTeammates;
}

function summarizeTeamUsage(entries: TeamConversationEntry[]): UsageSummary {
  return entries.reduce<UsageSummary>(
    (usage, entry) => {
      usage.inputTokens += entry.node.metadata.input_tokens ?? 0;
      usage.outputTokens += entry.node.metadata.output_tokens ?? 0;
      usage.durationMs = Math.max(usage.durationMs, entry.node.metadata.duration_ms ?? 0);
      const cost = entry.node.metadata.cost_usd;
      if (typeof cost === "string" && cost.length > 0) usage.costUsd = cost;
      if (entry.node.metadata.model_call_id) usage.modelCalls += 1;
      usage.toolCalls += entry.node.tool_calls.length;
      return usage;
    },
    {
      inputTokens: 0,
      outputTokens: 0,
      costUsd: "-",
      durationMs: 0,
      modelCalls: 0,
      toolCalls: 0,
    },
  );
}

function teamContextTokenEstimate(entries: TeamConversationEntry[], draft: string) {
  return entries.reduce((sum, entry) => {
    const metered =
      (entry.node.metadata.input_tokens ?? 0) + (entry.node.metadata.output_tokens ?? 0);
    return sum + Math.max(metered, estimateTextTokens(entry.node.content));
  }, estimateTextTokens(draft));
}

function teamCompressionKey(team: Team, agent: TeamAgent, entries: TeamConversationEntry[]) {
  const activeLeafId = entries[entries.length - 1]?.node.id ?? `team-${team.id}-${agent.slot_id}-root`;
  return contextCompressionBranchKey(`team:${team.id}:${agent.slot_id}`, activeLeafId);
}

function teamEffectiveContextTokenEstimate(input: {
  entries: TeamConversationEntry[];
  draft: string;
  summary: ContextCompressionSummary | null;
  branchKey: string;
  pinnedNodeIds: string[];
  providerId: string | null | undefined;
  modelId: string | null | undefined;
}) {
  const activePath = input.entries.map((entry) => entry.node);
  if (
    !isCompressionSummaryUsable({
      summary: input.summary,
      branchKey: input.branchKey,
      activePath,
      pinnedNodeIds: input.pinnedNodeIds,
      providerId: input.providerId,
      modelId: input.modelId,
    })
  ) {
    return teamContextTokenEstimate(input.entries, input.draft);
  }
  const uncovered = uncoveredContextPath({
    activePath,
    pinnedNodeIds: input.pinnedNodeIds,
    summary: input.summary,
  });
  const uncoveredTokens = uncovered.reduce((sum, node) => {
    const metered = (node.metadata.input_tokens ?? 0) + (node.metadata.output_tokens ?? 0);
    return sum + Math.max(metered, estimateTextTokens(node.content));
  }, 0);
  const summaryTokens = Math.max(
    input.summary?.estimatedSummaryTokens ?? 0,
    estimateTextTokens(input.summary?.summary ?? ""),
  );
  return summaryTokens + uncoveredTokens + estimateTextTokens(input.draft);
}

function workspaceCompressionSummary(
  branchKey: string,
  response: WorkspaceContextCompressionResponse,
): ContextCompressionSummary {
  return {
    branchKey,
    summary: response.summary,
    coverageNodeIds: response.coverage_node_ids,
    coveragePathHash: response.coverage_path_hash,
    lastCoveredNodeId: response.last_covered_node_id,
    summarySchemaVersion: response.summary_schema_version,
    compressionPromptVersion: response.compression_prompt_version,
    compressorProvider: response.compressor_provider,
    compressorModel: response.compressor_model,
    estimatedOriginalTokens: response.estimated_original_tokens,
    estimatedSummaryTokens: response.estimated_summary_tokens,
    estimatedUncoveredTokens: response.estimated_uncovered_tokens,
    status: response.status === "provider_error" ? "error" : "ready",
    cacheStatus: response.cache_status,
    error: response.error ?? null,
    createdAt: response.created_at,
    updatedAt: response.updated_at,
  };
}

function deriveTeamModelOptions(settings: ModelSettings | undefined): ModelOption[] {
  if (settings === undefined) return [];
  const out: ModelOption[] = [];
  for (const raw of settings.providers) {
    if (typeof raw !== "object" || raw === null) continue;
    const record = raw as Record<string, unknown>;
    const name = record.name;
    if (typeof name !== "string" || name.length === 0) continue;
    const label = typeof record.label === "string" && record.label.length > 0 ? record.label : name;
    const model = typeof record.model === "string" && record.model.length > 0 ? record.model : "default";
    out.push({
      providerId: name,
      providerLabel: label,
      modelId: model,
      modelLabel: model,
    });
  }
  return out;
}

export function TeamPage() {
  const { text } = useI18n();
  const { confirm, confirmDialog } = useConfirmDialog();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { teamId = "" } = useParams();
  const [activeSlotId, setActiveSlotId] = useState("leader");
  const [fullscreenSlotId, setFullscreenSlotId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [addMemberOpen, setAddMemberOpen] = useState(false);
  const [newMemberName, setNewMemberName] = useState("");
  const [newMemberAgentId, setNewMemberAgentId] = useState<string | null>(null);
  const [composerState, setComposerState] = useState<ComposerState>({});
  const [pendingSends, setPendingSends] = useState<PendingSend[]>([]);
  const [pendingWakeSlotIds, setPendingWakeSlotIds] = useState<string[]>([]);
  const [streamingWakes, setStreamingWakes] = useState<StreamingWake[]>([]);
  const [settledWakeCutoffs, setSettledWakeCutoffs] = useState<SettledWakeCutoffs>({});
  const [orderedSlotIds, setOrderedSlotIds] = useState<string[]>([]);
  const [editingSlotId, setEditingSlotId] = useState<string | null>(null);
  const [editingAgentName, setEditingAgentName] = useState("");
  const [dragSourceSlotId, setDragSourceSlotId] = useState<string | null>(null);
  const [dragOverSlotId, setDragOverSlotId] = useState<string | null>(null);
  const [flashingSlotId, setFlashingSlotId] = useState<string | null>(null);
  const [taskBoardOpen, setTaskBoardOpen] = useState(false);
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [pinnedMessageIds, setPinnedMessageIds] = useState<string[]>([]);
  const [attachmentsBySlotId, setAttachmentsBySlotId] = useState<Record<string, ComposerAttachment[]>>({});
  const [bottomPanelBySlotId, setBottomPanelBySlotId] = useState<Record<string, TeamBottomPanel>>({});
  const [contextMaxTokens, setContextMaxTokens] = useState(CONTEXT_MAX_TOKENS_DEFAULT);
  const [autoCompressionRatio, setAutoCompressionRatio] = useState(AUTO_COMPRESSION_RATIO_DEFAULT);
  const [contextCompressionsBySlotId, setContextCompressionsBySlotId] = useState<TeamContextCompressions>({});
  const [branchGroupsBySlotId, setBranchGroupsBySlotId] = useState<TeamBranchGroupsBySlot>({});
  const [teamInspector, setTeamInspector] = useState<{
    section: InspectorSection;
    node: ConversationNode;
  } | null>(null);
  const [isNarrowColumns, setIsNarrowColumns] = useState(false);
  const scrollRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const columnsContainerRef = useRef<HTMLDivElement | null>(null);
  const flashTimerRef = useRef<number | null>(null);
  const pendingSendKeysRef = useRef<Set<string>>(new Set());
  const wakeControllersRef = useRef<Record<string, AbortController>>({});
  const userCancelledWakeSlotIdsRef = useRef<Set<string>>(new Set());
  const failedWakeStreamSlotIdsRef = useRef<Set<string>>(new Set());
  const terminalWakeSlotIdsRef = useRef<Set<string>>(new Set());
  const followUpWakeRef = useRef<(slotIds: string[]) => void>(() => undefined);
  const teamFileInputsRef = useRef<Record<string, HTMLInputElement | null>>({});
  const compressionInFlightRef = useRef<Set<string>>(new Set());
  const [columnOverflow, setColumnOverflow] = useState({ left: false, right: false });

  const teamQuery = useQuery({
    queryKey: ["teams", teamId],
    queryFn: () => getTeam(teamId),
    enabled: Boolean(teamId),
    refetchInterval: 4000,
  });
  const teamsQuery = useQuery({
    queryKey: ["teams"],
    queryFn: listTeams,
    refetchInterval: 8000,
  });
  const agentsQuery = useQuery({
    queryKey: ["agents"],
    queryFn: listAgents,
    enabled: addMemberOpen,
  });
  const streamReadyTeamId = teamQuery.data?.id;

  useEffect(() => {
    if (!teamId || !streamReadyTeamId) return;
    const controller = new AbortController();
    void streamTeamEvents(
      teamId,
      (event) => {
        let applied = false;
        queryClient.setQueryData<Team>(["teams", teamId], (current) => {
          if (!current) return current;
          const next = applyTeamEventToTeam(current, event);
          if (!next) return current;
          applied = true;
          return next;
        });
        queryClient.setQueryData<TeamPageEnvelope>(["teams"], (current) => {
          const next = applyTeamEventToTeamPage(current, event);
          return next ?? current;
        });
        if (!applied) {
          void queryClient.invalidateQueries({ queryKey: ["teams", teamId] });
          void queryClient.invalidateQueries({ queryKey: ["teams"] });
        }
        if (event.event_type === "TEAM_AGENT_SPAWNED") {
          const agent = event.payload_json.agent;
          if (isTeamAgent(agent)) {
            setActiveSlotId(agent.slot_id);
          }
        }
        const completedWakeSlotId = completedWakeSlotIdFromTeamEvent(event);
        if (completedWakeSlotId) {
          terminalWakeSlotIdsRef.current.add(completedWakeSlotId);
          wakeControllersRef.current[completedWakeSlotId]?.abort();
          const cutoffMs = timestampMs(event.created_at) ?? Date.now();
          setSettledWakeCutoffs((current) => ({
            ...current,
            [completedWakeSlotId]: Math.max(current[completedWakeSlotId] ?? 0, cutoffMs),
          }));
          setPendingWakeSlotIds((current) =>
            current.filter((candidate) => candidate !== completedWakeSlotId),
          );
          setStreamingWakes((current) => current.filter((wake) => wake.slotId !== completedWakeSlotId));
        }
      },
      controller.signal,
    ).catch(() => undefined);
    return () => controller.abort();
  }, [queryClient, streamReadyTeamId, teamId]);

  const team = useMemo(
    () => normalizeSettledTeam(teamQuery.data ?? null, settledWakeCutoffs),
    [settledWakeCutoffs, teamQuery.data],
  );
  const teams = teamsQuery.data?.items ?? [];
  const agents = useMemo(() => team?.agents ?? [], [team?.agents]);
  const toolAgentIds = useMemo(
    () => Array.from(new Set(agents.map((agent) => agent.agent_id).filter(Boolean))).sort(),
    [agents],
  );
  const settingsQuery = useQuery({ queryKey: ["settings", "models"], queryFn: getModelSettings });
  const toolsQuery = useQuery({
    queryKey: ["tools", "registry", "team", toolAgentIds],
    queryFn: async () =>
      Promise.all(
        toolAgentIds.map(async (agentId) => ({
          agentId,
          registry: await getToolRegistry(agentId),
        })),
      ),
    enabled: toolAgentIds.length > 0,
  });
  const agentDefinitions = agentsQuery.data?.items ?? [];
  const toolsByAgentId = useMemo(() => {
    const next = new Map<string, ToolMetadata[]>();
    for (const entry of toolsQuery.data ?? []) {
      next.set(entry.agentId, entry.registry.items);
    }
    return next;
  }, [toolsQuery.data]);
  const modelOptions = useMemo(() => deriveTeamModelOptions(settingsQuery.data), [settingsQuery.data]);
  const messages = team?.messages ?? [];
  const tasks = team?.tasks ?? [];
  const leader = agents.find((agent) => agent.role === "leader") ?? agents[0] ?? null;
  const selectedAgent = activeAgent(team ?? undefined, activeSlotId);
  const leaderSlotId = team?.leader_slot_id ?? leader?.slot_id ?? "leader";
  const activeTeam = team ?? teams.find((item) => item.id === teamId) ?? null;
  const orderStorageKey = teamId ? `harness-team-agent-order-${teamId}` : "";
  const orderedAgents = useMemo(() => orderedTeamAgents(agents, orderedSlotIds), [agents, orderedSlotIds]);
  const openTaskCount = tasks.filter((task) => task.status !== "completed" && task.status !== "deleted").length;
  const selectedNewMemberAgent =
    agentDefinitions.find((agent) => agent.id === newMemberAgentId) ?? agentDefinitions[0] ?? null;
  const addMemberError = agentsQuery.error instanceof Error ? agentsQuery.error.message : null;

  useEffect(() => {
    if (!leaderSlotId) return;
    setActiveSlotId((current) => (agents.some((agent) => agent.slot_id === current) ? current : leaderSlotId));
  }, [agents, leaderSlotId]);

  useEffect(() => {
    if (!addMemberOpen || newMemberAgentId || agentDefinitions.length === 0) return;
    setNewMemberAgentId(agentDefinitions.find((agent) => agent.id === "default")?.id ?? agentDefinitions[0].id);
  }, [addMemberOpen, agentDefinitions, newMemberAgentId]);

  useEffect(() => {
    if (!orderStorageKey) return;
    try {
      const stored = window.localStorage.getItem(orderStorageKey);
      if (stored) {
        const parsed = JSON.parse(stored) as unknown;
        if (Array.isArray(parsed)) {
          setOrderedSlotIds(parsed.filter((value): value is string => typeof value === "string"));
        }
      }
    } catch {
      setOrderedSlotIds([]);
    }
  }, [orderStorageKey]);

  useEffect(() => {
    const teammateIds = agents.filter((agent) => agent.role !== "leader").map((agent) => agent.slot_id);
    setOrderedSlotIds((current) => {
      const next = current.filter((slotId) => teammateIds.includes(slotId));
      for (const slotId of teammateIds) {
        if (!next.includes(slotId)) next.push(slotId);
      }
      return next.join("\n") === current.join("\n") ? current : next;
    });
  }, [agents]);

  useEffect(() => {
    if (!orderStorageKey) return;
    window.localStorage.setItem(orderStorageKey, JSON.stringify(orderedSlotIds));
  }, [orderStorageKey, orderedSlotIds]);

  useEffect(() => {
    if (!activeSlotId) return;
    const node = scrollRefs.current[activeSlotId];
    if (node) {
      node.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "start" });
      if (flashTimerRef.current) {
        window.clearTimeout(flashTimerRef.current);
      }
      setFlashingSlotId(activeSlotId);
      flashTimerRef.current = window.setTimeout(() => {
        setFlashingSlotId((current) => (current === activeSlotId ? null : current));
        flashTimerRef.current = null;
      }, 320);
    }
  }, [activeSlotId]);

  useEffect(
    () => () => {
      if (flashTimerRef.current) {
        window.clearTimeout(flashTimerRef.current);
      }
      for (const controller of Object.values(wakeControllersRef.current)) {
        controller.abort();
      }
    },
    [],
  );

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(max-width: 767px)");
    const apply = (): void => setIsNarrowColumns(query.matches);
    apply();
    query.addEventListener("change", apply);
    return () => query.removeEventListener("change", apply);
  }, []);

  const updateColumnOverflow = useCallback(() => {
    const node = columnsContainerRef.current;
    if (!node) {
      setColumnOverflow({ left: false, right: false });
      return;
    }
    const hasOverflow = node.scrollWidth > node.clientWidth + 1;
    setColumnOverflow({
      left: hasOverflow && node.scrollLeft > 10,
      right: hasOverflow && node.scrollLeft + node.clientWidth < node.scrollWidth - 10,
    });
  }, []);

  useEffect(() => {
    const node = columnsContainerRef.current;
    if (!node) return;
    node.addEventListener("scroll", updateColumnOverflow, { passive: true });
    window.addEventListener("resize", updateColumnOverflow);
    const observer =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(updateColumnOverflow);
    observer?.observe(node);
    requestAnimationFrame(updateColumnOverflow);
    return () => {
      node.removeEventListener("scroll", updateColumnOverflow);
      window.removeEventListener("resize", updateColumnOverflow);
      observer?.disconnect();
    };
  }, [agents.length, fullscreenSlotId, isNarrowColumns, updateColumnOverflow]);

  const scrollColumns = useCallback(
    (direction: "left" | "right") => {
      const node = columnsContainerRef.current;
      if (!node) return;
      node.scrollBy({ left: direction === "left" ? -420 : 420, behavior: "smooth" });
      window.setTimeout(updateColumnOverflow, 260);
    },
    [updateColumnOverflow],
  );

  const renameAgentMutation = useMutation({
    mutationFn: (payload: { slotId: string; agentName: string }) =>
      renameTeamAgent(teamId, payload.slotId, payload.agentName),
    onSuccess: async (_agent, payload) => {
      setEditingSlotId(null);
      setEditingAgentName("");
      notifyFeedback({
        tone: "success",
        title: "成员名称已更新",
        description: `已将团队成员更新为 ${payload.agentName}。`,
      });
      await queryClient.invalidateQueries({ queryKey: ["teams", teamId] });
      await queryClient.invalidateQueries({ queryKey: ["teams"] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: "成员名称更新失败",
        description: feedbackErrorMessage(error, "请检查成员名称是否为空，或稍后重试。"),
      });
    },
  });

  const updateAgentMutation = useMutation({
    mutationFn: (payload: { slotId: string; modelProvider: string; modelName: string }) =>
      updateTeamAgent(teamId, payload.slotId, {
        model_provider: payload.modelProvider,
        model_name: payload.modelName,
      }),
    onSuccess: async (agent) => {
      setComposerBottomPanel(agent.slot_id, null);
      notifyFeedback({
        tone: "success",
        title: "成员模型已切换",
        description: `${agent.agent_name} 现在使用 ${agent.model_provider}/${agent.model_name}。`,
      });
      queryClient.setQueryData<Team>(["teams", teamId], (current) =>
        current ? { ...current, agents: mergeTeamAgent(current.agents, agent) } : current,
      );
      await queryClient.invalidateQueries({ queryKey: ["teams", teamId] });
      await queryClient.invalidateQueries({ queryKey: ["teams"] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: "成员模型切换失败",
        description: feedbackErrorMessage(error, "请检查模型配置或稍后重试。"),
      });
    },
  });

  const removeAgentMutation = useMutation({
    mutationFn: (slotId: string) => removeTeamAgent(teamId, slotId),
    onSuccess: async (_agent, slotId) => {
      setFullscreenSlotId((current) => (current === slotId ? null : current));
      setActiveSlotId((current) => (current === slotId ? leaderSlotId : current));
      notifyFeedback({
        tone: "warning",
        title: "团队成员已移除",
        description: "该成员已从当前团队中移除。",
      });
      await queryClient.invalidateQueries({ queryKey: ["teams", teamId] });
      await queryClient.invalidateQueries({ queryKey: ["teams"] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: "移除团队成员失败",
        description: feedbackErrorMessage(error, "请检查该成员是否仍在运行，或稍后重试。"),
      });
    },
  });

  const confirmRemoveAgent = useCallback(
    async (agentName: string, status: string) => {
      if (status !== "active") return true;
      return confirm({
        title: "移除团队成员",
        description: `成员 ${agentName} 当前仍在运行中。移除后会中断该成员的当前团队协作。`,
        confirmText: "确认移除",
        variant: "danger",
      });
    },
    [confirm],
  );

  const addAgentMutation = useMutation({
    mutationFn: (payload: { agentId: string; agentName: string }) =>
      addTeamAgent(teamId, {
        agent_id: payload.agentId,
        agent_name: payload.agentName,
        role: "teammate",
      }),
    onSuccess: async (agent) => {
      setAddMemberOpen(false);
      setNewMemberName("");
      setNewMemberAgentId(null);
      setActiveSlotId(agent.slot_id);
      notifyFeedback({
        tone: "success",
        title: "团队成员已添加",
        description: `${agent.agent_name} 已加入当前团队。`,
      });
      await queryClient.invalidateQueries({ queryKey: ["teams", teamId] });
      await queryClient.invalidateQueries({ queryKey: ["teams"] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: "团队成员添加失败",
        description: feedbackErrorMessage(error, "请检查成员名称、智能体定义或稍后重试。"),
      });
    },
  });

  const applyWakeStreamEvent = useCallback(
    (event: TeamWakeStreamEvent) => {
      if (event.type === "delta") {
        setStreamingWakes((current) => {
          const existing = current.find((wake) => wake.slotId === event.slot_id);
          if (!existing) {
            return [...current, { slotId: event.slot_id, content: event.content }];
          }
          return current.map((wake) =>
            wake.slotId === event.slot_id
              ? { ...wake, content: `${wake.content}${event.content}` }
              : wake,
          );
        });
        return;
      }
      if (event.type === "status" || event.type === "done") {
        queryClient.setQueryData<Team>(["teams", teamId], (current) => {
          if (!current) return current;
          const incomingAgent = event.type === "done" ? settledWakeAgent(event.agent) : event.agent;
          const agents = event.type === "done" && event.message
            ? appendSessionMessageToAgent(current, incomingAgent.slot_id, event.message)
            : current.agents;
          return {
            ...current,
            agents: mergeTeamAgent(agents, incomingAgent),
          };
        });
      }
      if (event.type === "done") {
        terminalWakeSlotIdsRef.current.add(event.agent.slot_id);
        failedWakeStreamSlotIdsRef.current.delete(event.agent.slot_id);
        setSettledWakeCutoffs((current) => ({
          ...current,
          [event.agent.slot_id]: Math.max(
            current[event.agent.slot_id] ?? 0,
            timestampMs(event.agent.updated_at) ?? Date.now(),
          ),
        }));
        setStreamingWakes((current) => current.filter((wake) => wake.slotId !== event.agent.slot_id));
        setPendingWakeSlotIds((current) => current.filter((candidate) => candidate !== event.agent.slot_id));
        if (event.follow_up_slot_ids?.length) {
          followUpWakeRef.current(event.follow_up_slot_ids);
        }
        void queryClient.invalidateQueries({ queryKey: ["teams", teamId] });
        void queryClient.invalidateQueries({ queryKey: ["teams"] });
      }
      if (event.type === "error") {
        const slotId = event.agent?.slot_id ?? event.slot_id;
        if (!slotId) return;
        terminalWakeSlotIdsRef.current.add(slotId);
        failedWakeStreamSlotIdsRef.current.add(slotId);
        setPendingWakeSlotIds((current) => current.filter((candidate) => candidate !== slotId));
        setStreamingWakes((current) => {
          const existing = current.find((wake) => wake.slotId === slotId);
          if (!existing) return [...current, { slotId, content: "", error: event.message }];
          return current.map((wake) => wake.slotId === slotId ? { ...wake, error: event.message } : wake);
        });
        if (event.agent) {
          queryClient.setQueryData<Team>(["teams", teamId], (current) => {
            if (!current) return current;
            return {
              ...current,
              agents: mergeTeamAgent(current.agents, {
                ...event.agent!,
                metadata_json: {
                  ...event.agent!.metadata_json,
                  wake: {
                    ...(isRecord(event.agent!.metadata_json?.wake) ? event.agent!.metadata_json.wake : {}),
                    in_progress: false,
                  },
                },
              }),
            };
          });
        }
      }
    },
    [queryClient, teamId],
  );

  const settleWakeLocally = useCallback(
    (slotId: string, agentPatch?: TeamAgent) => {
      const nowMs = timestampMs(agentPatch?.updated_at) ?? Date.now();
      setSettledWakeCutoffs((current) => ({
        ...current,
        [slotId]: Math.max(current[slotId] ?? 0, nowMs),
      }));
      setPendingWakeSlotIds((current) => current.filter((candidate) => candidate !== slotId));
      setStreamingWakes((current) => current.filter((wake) => wake.slotId !== slotId || wake.error));
      queryClient.setQueryData<Team>(["teams", teamId], (current) => {
        if (!current) return current;
        const existing = current.agents.find((agent) => agent.slot_id === slotId);
        const settledAgent = agentPatch ?? existing;
        if (!settledAgent) return current;
        return {
          ...current,
          agents: mergeTeamAgent(current.agents, {
            ...settledAgent,
            status: "idle",
            metadata_json: {
              ...settledAgent.metadata_json,
              wake: {
                ...(isRecord(settledAgent.metadata_json?.wake) ? settledAgent.metadata_json.wake : {}),
                in_progress: false,
              },
            },
          }),
        };
      });
    },
    [queryClient, teamId],
  );

  const triggerWake = useCallback(
    (slotIds: string[]) => {
      const uniqueSlotIds = [...new Set(slotIds)].filter(Boolean);
      for (const slotId of uniqueSlotIds) {
        if (wakeControllersRef.current[slotId]) continue;
        failedWakeStreamSlotIdsRef.current.delete(slotId);
        terminalWakeSlotIdsRef.current.delete(slotId);
        setSettledWakeCutoffs((current) => {
          if (!(slotId in current)) return current;
          const next = { ...current };
          delete next[slotId];
          return next;
        });
        const controller = new AbortController();
        wakeControllersRef.current[slotId] = controller;
        setPendingWakeSlotIds((current) => (current.includes(slotId) ? current : [...current, slotId]));
        setStreamingWakes((current) =>
          current.some((wake) => wake.slotId === slotId)
            ? current
            : [...current, { slotId, content: "" }],
        );
        streamWakeTeamAgent(teamId, slotId, applyWakeStreamEvent, controller.signal)
          .then(() => {
            if (!failedWakeStreamSlotIdsRef.current.has(slotId)) {
              settleWakeLocally(slotId);
            }
            void queryClient.invalidateQueries({ queryKey: ["teams", teamId] });
          })
          .catch(() => {
            if (terminalWakeSlotIdsRef.current.has(slotId)) return;
            if (controller.signal.aborted) {
              if (userCancelledWakeSlotIdsRef.current.has(slotId)) {
                settleWakeLocally(slotId);
              }
              return;
            }
            return wakeTeamAgent(teamId, slotId).then(() => {
              void queryClient.invalidateQueries({ queryKey: ["teams", teamId] });
            }).catch(() => undefined);
          })
          .finally(() => {
            userCancelledWakeSlotIdsRef.current.delete(slotId);
            failedWakeStreamSlotIdsRef.current.delete(slotId);
            terminalWakeSlotIdsRef.current.delete(slotId);
            delete wakeControllersRef.current[slotId];
            setPendingWakeSlotIds((current) => current.filter((candidate) => candidate !== slotId));
            setStreamingWakes((current) => current.filter((wake) => wake.slotId !== slotId || wake.error));
          });
      }
    },
    [applyWakeStreamEvent, queryClient, settleWakeLocally, teamId],
  );

  useEffect(() => {
    followUpWakeRef.current = triggerWake;
  }, [triggerWake]);

  const stopWake = useCallback(
    (slotId: string) => {
      userCancelledWakeSlotIdsRef.current.add(slotId);
      wakeControllersRef.current[slotId]?.abort();
      settleWakeLocally(slotId);
      cancelWakeTeamAgent(teamId, slotId)
        .then((agent) => {
          settleWakeLocally(slotId, agent);
          void queryClient.invalidateQueries({ queryKey: ["teams", teamId] });
        })
        .catch(() => undefined);
    },
    [queryClient, settleWakeLocally, teamId],
  );

  const sendMutation = useMutation({
    mutationFn: (payload: PendingSend) =>
      sendTeamMessage(teamId, {
        target: payload.target,
        content: payload.content,
        from_agent_slot_id: "user",
        type: "message",
        files: payload.files,
        mode: payload.mode,
      }),
    onSuccess: async (_message, variables) => {
      triggerWake(variables.recipientSlotIds);
      await queryClient.invalidateQueries({ queryKey: ["teams", teamId] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("团队消息发送失败", "Team message send failed"),
        description: feedbackErrorMessage(
          error,
          text("请检查当前团队状态、目标成员或稍后重试。", "Check the team state, recipient, or retry."),
        ),
      });
    },
    onSettled: (_message, _error, variables) => {
      if (!variables) return;
      pendingSendKeysRef.current.delete(variables.key);
      setPendingSends((current) => current.filter((send) => send.id !== variables.id));
    },
  });

  const selectedComposer = composerState[activeSlotId] ?? {
    draft: "",
  };

  const updateComposer = useCallback((slotId: string, next: TeamComposerStateUpdater) => {
    setComposerState((current) => {
      const previous = current[slotId] ?? { draft: "" };
      const resolved = typeof next === "function" ? next(previous) : next;
      return { ...current, [slotId]: resolved };
    });
  }, []);

  const sendFromComposer = useCallback(
    (
      agent: TeamAgent,
      content: string,
      target: string,
      attachments: ComposerAttachment[] = [],
      mode: WorkspaceMode = "chat",
    ) => {
      const trimmed = content.trim();
      if (!trimmed || !activeTeam) return;
      const recipientSlotIds = recipientSlotIdsForTarget(activeTeam, target);
      if (recipientSlotIds.length === 0) return;
      const files = attachments.map((attachment) => attachment.name);
      const key = teamPendingSendKey(agent.slot_id, target, mode, trimmed, files);
      const duplicate =
        pendingSendKeysRef.current.has(key) ||
        pendingSends.some(
          (send) =>
            send.sourceSlotId === agent.slot_id &&
            send.target === target &&
            send.content === trimmed &&
            send.mode === mode &&
            send.files.join("\n") === files.join("\n"),
        );
      if (duplicate) return;
      pendingSendKeysRef.current.add(key);
      const pendingSend: PendingSend = {
        id: `${key}:${Date.now()}`,
        key,
        sourceSlotId: agent.slot_id,
        target,
        content: trimmed,
        files,
        mode,
        recipientSlotIds,
      };
      setPendingSends((current) => [...current, pendingSend]);
      setComposerState((current) => ({
        ...current,
        [agent.slot_id]: { ...(current[agent.slot_id] ?? {}), draft: "", mode },
      }));
      setAttachmentsBySlotId((current) => ({ ...current, [agent.slot_id]: [] }));
      sendMutation.mutate(pendingSend);
    },
    [activeTeam, pendingSends, sendMutation],
  );

  const sendFromMessageAction = useCallback(
    (sourceSlotId: string, content: string, target: string) => {
      const trimmed = content.trim();
      const sourceAgent = agents.find((agent) => agent.slot_id === sourceSlotId);
      if (!trimmed || !sourceAgent) return;
      sendFromComposer(sourceAgent, trimmed, target);
    },
    [agents, sendFromComposer],
  );

  const branchFromAssistant = useCallback(
    (agent: TeamAgent, entries: TeamConversationEntry[], assistantNodeId: string) => {
      const previousUser = previousUserEntry(entries, assistantNodeId);
      if (!previousUser) return;
      const originalAssistant = entries.find((entry) => entry.node.id === assistantNodeId);
      if (!originalAssistant) return;
      const branchKey = previousUser.node.id;
      setBranchGroupsBySlotId((current) => {
        const slotGroups = current[agent.slot_id] ?? {};
        const existing = slotGroups[branchKey];
        const branchNodeIds = Array.from(
          new Set([...(existing?.branchNodeIds ?? []), originalAssistant.node.id]),
        );
        return {
          ...current,
          [agent.slot_id]: {
            ...slotGroups,
            [branchKey]: {
              anchorUserId: previousUser.node.id,
              anchorContent: previousUser.node.content,
              branchNodeIds,
              hiddenUserNodeIds: existing?.hiddenUserNodeIds ?? [],
              activeNodeId: originalAssistant.node.id,
            },
          },
        };
      });
      sendFromComposer(agent, previousUser.node.content, previousUser.target);
    },
    [sendFromComposer],
  );

  useEffect(() => {
    if (!team) return;
    setBranchGroupsBySlotId((current) => {
      let changed = false;
      const next: TeamBranchGroupsBySlot = { ...current };
      for (const agent of team.agents) {
        const slotGroups = current[agent.slot_id];
        if (!slotGroups) continue;
        const entries = teamConversationEntriesWithPending(
          team,
          agent,
          agentMessages(agent, messages),
          pendingSends,
          pendingWakeSlotIds,
          streamingWakes,
          settledWakeCutoffs,
        );
        const byId = new Map(entries.map((entry) => [entry.node.id, entry]));
        let nextSlotGroups = slotGroups;
        for (const [anchorUserId, group] of Object.entries(slotGroups)) {
          const visibleBranchNodeIds = group.branchNodeIds.filter((nodeId) => byId.has(nodeId));
          let workingGroup = group;
          if (
            visibleBranchNodeIds.length !== group.branchNodeIds.length ||
            !visibleBranchNodeIds.includes(group.activeNodeId)
          ) {
            workingGroup = {
              ...group,
              branchNodeIds: visibleBranchNodeIds,
              activeNodeId: visibleBranchNodeIds.includes(group.activeNodeId)
                ? group.activeNodeId
                : visibleBranchNodeIds[visibleBranchNodeIds.length - 1] ?? group.activeNodeId,
            };
            nextSlotGroups = {
              ...nextSlotGroups,
              [anchorUserId]: workingGroup,
            };
            changed = true;
          }
          const lastAssistant = findLastAssistantEntry(entries);
          const pendingBranch =
            lastAssistant &&
            !workingGroup.branchNodeIds.includes(lastAssistant.node.id) &&
            previousUserEntry(entries, lastAssistant.node.id)?.node.content === workingGroup.anchorContent;
          if (!pendingBranch) continue;
          const nextBranchNodeIds = [...workingGroup.branchNodeIds, lastAssistant.node.id];
          const hiddenUserNodeIds = new Set(workingGroup.hiddenUserNodeIds);
          const previousUser = previousUserEntry(entries, lastAssistant.node.id);
          if (previousUser && previousUser.node.id !== workingGroup.anchorUserId) {
            hiddenUserNodeIds.add(previousUser.node.id);
          }
          nextSlotGroups = {
            ...nextSlotGroups,
            [anchorUserId]: {
              ...workingGroup,
              branchNodeIds: nextBranchNodeIds,
              hiddenUserNodeIds: [...hiddenUserNodeIds].filter((nodeId) => byId.has(nodeId)),
              activeNodeId: lastAssistant.node.id,
            },
          };
          changed = true;
        }
        if (nextSlotGroups !== slotGroups) next[agent.slot_id] = nextSlotGroups;
      }
      return changed ? next : current;
    });
  }, [
    messages,
    pendingSends,
    pendingWakeSlotIds,
    settledWakeCutoffs,
    streamingWakes,
    team,
  ]);

  const switchTeamBranch = useCallback((slotId: string, anchorUserId: string, nodeId: string) => {
    setBranchGroupsBySlotId((current) => {
      const slotGroups = current[slotId];
      const group = slotGroups?.[anchorUserId];
      if (!slotGroups || !group || !group.branchNodeIds.includes(nodeId)) return current;
      return {
        ...current,
        [slotId]: {
          ...slotGroups,
          [anchorUserId]: { ...group, activeNodeId: nodeId },
        },
      };
    });
  }, []);

  const addComposerFiles = useCallback((slotId: string) => {
    teamFileInputsRef.current[slotId]?.click();
  }, []);

  const handleComposerFilesSelected = useCallback((slotId: string, event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.currentTarget.files ?? []);
    if (files.length === 0) return;
    setAttachmentsBySlotId((current) => {
      const existing = current[slotId] ?? [];
      const existingKeys = new Set(existing.map(attachmentKey));
      const next = [...existing];
      for (const file of files) {
        if (next.length >= 12) break;
        const attachment = fileToComposerAttachment(file);
        const key = attachmentKey(attachment);
        if (existingKeys.has(key)) continue;
        next.push(attachment);
        existingKeys.add(key);
      }
      return { ...current, [slotId]: next };
    });
    event.currentTarget.value = "";
  }, []);

  const removeComposerAttachment = useCallback((slotId: string, attachmentId: string) => {
    setAttachmentsBySlotId((current) => ({
      ...current,
      [slotId]: (current[slotId] ?? []).filter((attachment) => attachment.id !== attachmentId),
    }));
  }, []);

  const setComposerBottomPanel = useCallback((slotId: string, panel: TeamBottomPanel) => {
    setBottomPanelBySlotId((current) => ({ ...current, [slotId]: panel }));
  }, []);

  const setTeamContextCompression = useCallback(
    (slotId: string, branchKey: string, summary: ContextCompressionSummary) => {
      setContextCompressionsBySlotId((current) => ({
        ...current,
        [slotId]: {
          ...(current[slotId] ?? {}),
          [branchKey]: summary,
        },
      }));
    },
    [],
  );

  const clearTeamContextCompression = useCallback((slotId: string, branchKey: string) => {
    setContextCompressionsBySlotId((current) => {
      const slotSummaries = current[slotId];
      if (!slotSummaries || !(branchKey in slotSummaries)) return current;
      const { [branchKey]: _removed, ...nextSlotSummaries } = slotSummaries;
      if (Object.keys(nextSlotSummaries).length === 0) {
        const { [slotId]: _removedSlot, ...next } = current;
        return next;
      }
      return { ...current, [slotId]: nextSlotSummaries };
    });
  }, []);

  const compressTeamContext = useCallback(
    async (
      agent: TeamAgent,
      entries: TeamConversationEntry[],
      reason: "manual" | "background" | "pre_send" = "manual",
    ): Promise<ContextCompressionSummary | null> => {
      if (!team) return null;
      const branchKey = teamCompressionKey(team, agent, entries);
      if (compressionInFlightRef.current.has(branchKey)) {
        if (reason === "manual") {
          notifyFeedback({
            tone: "info",
            title: text("上下文仍在压缩", "Context compression is still running"),
            description: text(
              `“${agent.agent_name}”当前已经在生成摘要，请稍候再试。`,
              `${agent.agent_name} is already generating a summary. Please wait a moment.`,
            ),
          });
        }
        return null;
      }
      const activePath = entries.map((entry) => entry.node);
      const eligible = activePath.filter(
        (node) =>
          (node.role === "user" || node.role === "assistant" || node.role === "system") &&
          !pinnedMessageIds.includes(node.id) &&
          node.content.trim().length > 0,
      );
      if (eligible.length === 0) {
        if (reason === "manual") {
          notifyFeedback({
            tone: "warning",
            title: text("暂无可压缩内容", "Nothing to compress yet"),
            description: text(
              `“${agent.agent_name}”至少需要一段未固定的对话内容后，才能生成摘要。`,
              `${agent.agent_name} needs some unpinned conversation content before a summary can be generated.`,
            ),
          });
        }
        return null;
      }

      const slotSummaries = contextCompressionsBySlotId[agent.slot_id] ?? {};
      const selectedProviderId = agent.model_provider || modelOptions[0]?.providerId || null;
      const selectedModelId = agent.model_name || modelOptions[0]?.modelId || null;
      const existing = reason === "manual" ? null : slotSummaries[branchKey] ?? null;
      const now = new Date().toISOString();
      compressionInFlightRef.current.add(branchKey);
      setTeamContextCompression(agent.slot_id, branchKey, {
        ...(existing ?? {
          branchKey,
          summary: "",
          coverageNodeIds: [],
          coveragePathHash: "",
          lastCoveredNodeId: null,
          summarySchemaVersion: SUMMARY_SCHEMA_VERSION,
          compressionPromptVersion: COMPRESSION_PROMPT_VERSION,
          compressorProvider: normalizeModelId(selectedProviderId),
          compressorModel: normalizeModelId(selectedModelId),
          estimatedOriginalTokens: 0,
          estimatedSummaryTokens: 0,
          estimatedUncoveredTokens: 0,
          cacheStatus: undefined,
          error: null,
          createdAt: now,
        }),
        status: "pending",
        updatedAt: now,
      });

      try {
        const response = await compressAgentWorkspaceContext(agent.agent_id, {
          model_provider: selectedProviderId,
          model_name: selectedModelId,
          messages: activePath.map(serializeContextNode),
          pinned_node_ids: pinnedMessageIds,
          existing_summary: existing?.summary ?? null,
          prior_coverage_node_ids: existing?.coverageNodeIds ?? [],
          prior_coverage_path_hash: existing?.coveragePathHash ?? null,
          summary_schema_version: SUMMARY_SCHEMA_VERSION,
          compression_prompt_version: COMPRESSION_PROMPT_VERSION,
          compressor_provider: existing?.compressorProvider ?? selectedProviderId,
          compressor_model: existing?.compressorModel ?? selectedModelId,
        });
        const summary = workspaceCompressionSummary(branchKey, response);
        setTeamContextCompression(agent.slot_id, branchKey, summary);
        if (reason === "manual") {
          notifyFeedback({
            tone: "success",
            title: text("上下文已压缩", "Context compressed"),
            description: text(
              `已为“${agent.agent_name}”的 ${response.coverage_node_ids.length} 条消息生成摘要，预计从 ${Math.round(
                response.estimated_original_tokens,
              )} 标记压缩到 ${Math.round(response.estimated_summary_tokens)} 标记。`,
              `Summarized ${response.coverage_node_ids.length} messages for ${agent.agent_name}, reducing the estimated prompt from ${Math.round(
                response.estimated_original_tokens,
              )} to ${Math.round(response.estimated_summary_tokens)} tokens.`,
            ),
          });
        }
        return summary;
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        const failedAt = new Date().toISOString();
        setTeamContextCompression(agent.slot_id, branchKey, {
          ...(existing ?? {
            branchKey,
            summary: "",
            coverageNodeIds: [],
            coveragePathHash: "",
            lastCoveredNodeId: null,
            summarySchemaVersion: SUMMARY_SCHEMA_VERSION,
            compressionPromptVersion: COMPRESSION_PROMPT_VERSION,
            compressorProvider: normalizeModelId(selectedProviderId),
            compressorModel: normalizeModelId(selectedModelId),
            estimatedOriginalTokens: 0,
            estimatedSummaryTokens: 0,
            estimatedUncoveredTokens: 0,
            createdAt: failedAt,
          }),
          status: "error",
          cacheStatus: "error",
          error: message,
          updatedAt: failedAt,
        });
        if (reason === "manual") {
          notifyFeedback({
            tone: "error",
            title: text("上下文压缩失败", "Context compression failed"),
            description: message || text("请稍后重试。", "Please try again shortly."),
          });
        }
        return null;
      } finally {
        compressionInFlightRef.current.delete(branchKey);
      }
    },
    [
      contextCompressionsBySlotId,
      modelOptions,
      pinnedMessageIds,
      setTeamContextCompression,
      team,
      text,
    ],
  );

  const handleTeamModelChange = useCallback<TeamModelChangeHandler>(
    (slotId, providerId, modelId) => {
      updateAgentMutation.mutate({ slotId, modelProvider: providerId, modelName: modelId });
    },
    [updateAgentMutation],
  );

  const submitNewMember = useCallback(() => {
    if (!selectedNewMemberAgent) return;
    const trimmed = newMemberName.trim();
    addAgentMutation.mutate({
      agentId: selectedNewMemberAgent.id,
      agentName: trimmed || selectedNewMemberAgent.name,
    });
  }, [addAgentMutation, newMemberName, selectedNewMemberAgent]);

  const togglePinnedMessage = useCallback((nodeId: string) => {
    setPinnedMessageIds((current) =>
      current.includes(nodeId)
        ? current.filter((candidate) => candidate !== nodeId)
        : [...current, nodeId],
    );
  }, []);

  const startEditingAgent = useCallback((agent: TeamAgent) => {
    setEditingSlotId(agent.slot_id);
    setEditingAgentName(agent.agent_name);
  }, []);

  const commitEditingAgent = useCallback(() => {
    if (!editingSlotId) return;
    const trimmed = editingAgentName.trim();
    const current = agents.find((agent) => agent.slot_id === editingSlotId);
    if (!trimmed || trimmed === current?.agent_name) {
      setEditingSlotId(null);
      setEditingAgentName("");
      return;
    }
    renameAgentMutation.mutate({ slotId: editingSlotId, agentName: trimmed });
  }, [agents, editingAgentName, editingSlotId, renameAgentMutation]);

  const dropAgentTab = useCallback(
    (targetSlotId: string) => {
      if (!dragSourceSlotId || dragSourceSlotId === targetSlotId) {
        setDragSourceSlotId(null);
        setDragOverSlotId(null);
        return;
      }
      const targetAgent = agents.find((agent) => agent.slot_id === targetSlotId);
      if (!targetAgent || targetAgent.role === "leader") {
        setDragSourceSlotId(null);
        setDragOverSlotId(null);
        return;
      }
      setOrderedSlotIds((current) => {
        const teammateIds = agents.filter((agent) => agent.role !== "leader").map((agent) => agent.slot_id);
        const next = current.filter((slotId) => teammateIds.includes(slotId));
        for (const slotId of teammateIds) {
          if (!next.includes(slotId)) next.push(slotId);
        }
        const fromIndex = next.indexOf(dragSourceSlotId);
        const toIndex = next.indexOf(targetSlotId);
        if (fromIndex === -1 || toIndex === -1) return current;
        const [moved] = next.splice(fromIndex, 1);
        next.splice(toIndex, 0, moved);
        return next;
      });
      setActiveSlotId(dragSourceSlotId);
      setDragSourceSlotId(null);
      setDragOverSlotId(null);
    },
    [agents, dragSourceSlotId],
  );

  const composerSharedProps = useMemo(
    () => ({
      modelOptions,
      contextMaxTokens,
      autoCompressionRatio,
      onContextMaxTokensChange: setContextMaxTokens,
      onAutoCompressionRatioChange: setAutoCompressionRatio,
      onClearContextCompression: clearTeamContextCompression,
      addComposerFiles,
      handleComposerFilesSelected,
      removeComposerAttachment,
      setComposerBottomPanel,
      onModelChange: handleTeamModelChange,
    }),
    [
      addComposerFiles,
      autoCompressionRatio,
      contextMaxTokens,
      clearTeamContextCompression,
      handleComposerFilesSelected,
      handleTeamModelChange,
      modelOptions,
      removeComposerAttachment,
      setComposerBottomPanel,
    ],
  );

  if (teamQuery.isLoading && !team) {
    return (
      <ConsoleShell title={text("团队", "Teams")}>
        <div className="flex min-h-full items-center justify-center text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin" />
        </div>
      </ConsoleShell>
    );
  }

  if (!activeTeam) {
    return (
      <ConsoleShell title={text("团队", "Teams")}>
        <div className="flex min-h-full items-center justify-center">
          <Card className="p-6 text-center">
            <div className="text-sm font-semibold text-slate-900">{text("团队不存在", "Team not found")}</div>
            <Button className="mt-4" onClick={() => navigate("/teams")}>
              <ArrowLeft className="h-3.5 w-3.5" />
              {text("返回团队列表", "Back to teams")}
            </Button>
          </Card>
        </div>
      </ConsoleShell>
    );
  }

  return (
    <ConsoleShell title={activeTeam.name}>
      <div className="flex h-[100vh] min-h-0 overflow-hidden bg-white">
        <TeamRail teams={teams} activeTeamId={teamId} onCreate={() => setCreateOpen(true)} />

        <main className="flex min-w-0 flex-1 flex-col">
          <TeamRailMobileStrip teams={teams} activeTeamId={teamId} />
          <header className="relative z-30 shrink-0 border-b border-slate-200 bg-white/95 px-3 py-2 backdrop-blur sm:px-4">
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex min-w-[220px] flex-1 items-center gap-2">
                <Link
                  to="/teams"
                  className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
                  aria-label={text("返回团队列表", "Back to teams")}
                  title={text("返回团队列表", "Back to teams")}
                >
                  <ArrowLeft aria-hidden="true" className="h-4 w-4" />
                </Link>
                <div className="min-w-0">
                  <span className="inline-flex min-w-0 items-center gap-1.5 text-sm font-semibold text-slate-900">
                    <UsersRound aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-500" />
                    <span className="truncate">{activeTeam.name}</span>
                    <Badge tone={activeTeam.status === "ACTIVE" ? "success" : "neutral"}>
                      {statusLabel(activeTeam.status)}
                    </Badge>
                  </span>
                  <div className="hidden text-[11px] leading-4 text-slate-500 sm:block">
                    {text("团队模式工作台", "Team Mode workspace")}
                    <span className="mx-1 text-slate-300">·</span>
                    {activeTeam.workspace_mode}
                    <span className="mx-1 text-slate-300">·</span>
                    {agents.length} {text("名成员", "members")}
                  </div>
                </div>
              </div>

              <div className="flex min-w-0 flex-wrap items-center justify-end gap-1.5">
                <span
                  className="inline-flex h-8 max-w-[12rem] items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2 text-xs font-medium text-slate-700"
                  aria-label={text(
                    `团队工具: ${activeTeam.team_tools.length} 个可用`,
                    `Team tools: ${activeTeam.team_tools.length} available`,
                  )}
                  title={activeTeam.team_tools.join(", ")}
                >
                  <Wrench aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-slate-500" />
                  <span className="min-w-0 truncate">
                    {activeTeam.team_tools[0] ?? text("无工具", "No tools")}
                    {activeTeam.team_tools.length > 1 ? ` +${activeTeam.team_tools.length - 1}` : ""}
                  </span>
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setAddMemberOpen(true)}
                  aria-label={text("添加成员", "Add member")}
                  title={text("添加成员", "Add member")}
                  className="h-8 px-2"
                >
                  <Plus aria-hidden="true" className="h-3.5 w-3.5" />
                  <span className="hidden lg:inline">{text("添加成员", "Add member")}</span>
                </Button>
                <div className="relative">
                  <Button
                    type="button"
                    variant={taskBoardOpen ? "secondary" : "ghost"}
                    aria-label={text("任务板", "Task board")}
                    aria-expanded={taskBoardOpen}
                    onClick={() => setTaskBoardOpen((open) => !open)}
                    className="h-8 px-2"
                  >
                    <ClipboardList aria-hidden="true" className="h-3.5 w-3.5" />
                    <span className="hidden lg:inline">{text("任务板", "Tasks")}</span>
                    <Badge tone={openTaskCount > 0 ? "info" : "neutral"} className="px-1.5">
                      {openTaskCount}
                    </Badge>
                  </Button>
                  {taskBoardOpen ? (
                    <TeamTaskBoard
                      team={activeTeam}
                      agents={orderedAgents}
                      tasks={tasks}
                      text={text}
                      onClose={() => setTaskBoardOpen(false)}
                    />
                  ) : null}
                </div>
              </div>
            </div>
          </header>

          <div className="flex h-10 min-h-10 items-center gap-2 border-b border-slate-200 bg-white px-0">
            <div
              role="tablist"
              data-testid="team-tab-bar"
              aria-label={text("代理切换", "Agent switcher")}
              className="flex h-full min-w-0 flex-1 items-center overflow-x-auto [scrollbar-width:none]"
            >
              {orderedAgents.map((agent) => {
                const unreadCount = activeTeam.unread_counts[agent.slot_id] ?? 0;
                const assignedTaskCount =
                  agent.role === "leader"
                    ? tasks.length
                    : tasks.filter((task) => task.owner_slot_id === agent.slot_id).length;
                const status = displayAgentStatus(agent, pendingWakeSlotIds, streamingWakes, settledWakeCutoffs);
                const isActive = activeSlotId === agent.slot_id;
                const isEditing = editingSlotId === agent.slot_id;
                return (
                  <div
                    key={agent.slot_id}
                    role="tab"
                    tabIndex={0}
                    aria-selected={isActive}
                    draggable={agent.role !== "leader" && !isEditing}
                    onClick={() => {
                      if (!isEditing) setActiveSlotId(agent.slot_id);
                    }}
                    onKeyDown={(event) => {
                      if (isEditing) return;
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setActiveSlotId(agent.slot_id);
                      }
                    }}
                    onDoubleClick={() => startEditingAgent(agent)}
                    onDragStart={(event) => {
                      if (agent.role === "leader") return;
                      event.dataTransfer.effectAllowed = "move";
                      setDragSourceSlotId(agent.slot_id);
                    }}
                    onDragOver={(event) => {
                      if (!dragSourceSlotId || agent.role === "leader") return;
                      event.preventDefault();
                      event.dataTransfer.dropEffect = "move";
                      setDragOverSlotId(agent.slot_id);
                    }}
                    onDrop={(event) => {
                      event.preventDefault();
                      dropAgentTab(agent.slot_id);
                    }}
                    onDragEnd={() => {
                      setDragSourceSlotId(null);
                      setDragOverSlotId(null);
                    }}
                    className={cn(
                      "group inline-flex h-full max-w-60 shrink-0 cursor-pointer items-center gap-1.5 border-r border-slate-200 px-3 text-xs transition-all",
                      isActive
                        ? agent.role === "leader"
                          ? "border-t-2 border-t-slate-900 bg-slate-100 text-slate-950"
                          : "border-t-2 border-t-slate-900 bg-slate-100 text-slate-950"
                        : "border-t-2 border-t-transparent bg-white text-slate-600 hover:bg-slate-50 hover:text-slate-900",
                      status === "active" ? "animate-pulse" : "",
                      dragOverSlotId === agent.slot_id ? "border-l-4 border-l-slate-900" : "",
                    )}
                  >
                    {agent.role !== "leader" ? (
                      <GripVertical className="h-3 w-3 shrink-0 text-slate-300 opacity-0 transition-opacity group-hover:opacity-100" aria-hidden="true" />
                    ) : null}
                    {isEditing ? (
                      <Input
                        autoFocus
                        value={editingAgentName}
                        onClick={(event) => event.stopPropagation()}
                        onChange={(event) => setEditingAgentName(event.target.value)}
                        onBlur={commitEditingAgent}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") {
                            event.preventDefault();
                            commitEditingAgent();
                          }
                          if (event.key === "Escape") {
                            setEditingSlotId(null);
                            setEditingAgentName("");
                          }
                        }}
                        aria-label={text("代理名称", "Agent name")}
                        className="h-6 w-28 border-0 bg-transparent px-0 text-xs focus:ring-0"
                      />
                    ) : (
                      <span className="max-w-28 truncate">{agent.agent_name}</span>
                    )}
                    <Badge tone={teamAgentStatusTone(status)} className="px-1.5">
                      {teamAgentStatusLabel(status)}
                    </Badge>
                    {assignedTaskCount > 0 ? (
                      <Badge tone="info" className="px-1.5">
                        {assignedTaskCount}
                      </Badge>
                    ) : null}
                    {unreadCount > 0 ? (
                      <Badge tone="warning" className="px-1.5">
                        {unreadCount}
                      </Badge>
                    ) : null}
                    {!isEditing ? (
                      <Pencil className="h-3 w-3 shrink-0 text-slate-300 opacity-0 transition-opacity group-hover:opacity-100" aria-hidden="true" />
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="relative flex min-h-0 flex-1">
            <div className="min-w-0 flex-1">
              {!isNarrowColumns ? (
              <div className="relative h-full min-h-0">
                <div
                  ref={columnsContainerRef}
                  role="group"
                  aria-label={text("代理会话列", "Agent columns")}
                  className={cn(
                    "flex h-full min-h-0 w-full snap-x snap-proximity overflow-x-auto overflow-y-hidden bg-slate-50/40 [scrollbar-width:none]",
                    (fullscreenSlotId ? 1 : orderedAgents.length) <= 2 ? "justify-start" : "",
                  )}
                >
	                  {(fullscreenSlotId ? orderedAgents.filter((agent) => agent.slot_id === fullscreenSlotId) : orderedAgents).map((agent) => {
	                    const visibleCount = fullscreenSlotId ? 1 : orderedAgents.length;
	                    const agentComposer = composerState[agent.slot_id] ?? { draft: "" };
	                    const selectedTarget = defaultComposerTarget(agent);
	                    const selectedMode = agentComposer.mode ?? "chat";
	                    const selectedFiles = (attachmentsBySlotId[agent.slot_id] ?? []).map(
	                      (attachment) => attachment.name,
	                    );
	                    return (
	                      <AgentColumn
                        key={agent.slot_id}
                        team={activeTeam}
                        agent={agent}
                        text={text}
                        tasks={tasks}
                        messages={agentMessages(agent, messages)}
                        pendingSends={pendingSends}
                        pendingWakeSlotIds={pendingWakeSlotIds}
                        streamingWakes={streamingWakes}
                        settledWakeCutoffs={settledWakeCutoffs}
                        composer={agentComposer}
                        attachments={attachmentsBySlotId[agent.slot_id] ?? []}
                        bottomPanel={bottomPanelBySlotId[agent.slot_id] ?? null}
                        tools={toolsByAgentId.get(agent.agent_id) ?? []}
	                        isSending={pendingSends.some(
	                          (send) =>
	                            send.sourceSlotId === agent.slot_id &&
	                            send.target === selectedTarget &&
	                            send.content === agentComposer.draft.trim() &&
	                            send.mode === selectedMode &&
	                            send.files.join("\n") === selectedFiles.join("\n"),
	                        )}
                        editingMessageId={editingMessageId}
                        pinnedMessageIds={pinnedMessageIds}
                        branchGroups={branchGroupsBySlotId[agent.slot_id] ?? {}}
                        contextCompressions={contextCompressionsBySlotId[agent.slot_id] ?? {}}
                        onCompressContext={compressTeamContext}
                        visibleColumnCount={visibleCount}
                        fullscreen={fullscreenSlotId === agent.slot_id}
                        onComposerChange={(next) => updateComposer(agent.slot_id, next)}
	                        onSend={(content, target, mode) =>
	                          sendFromComposer(agent, content, target, attachmentsBySlotId[agent.slot_id] ?? [], mode)
	                        }
                        onMessageActionSend={(content, target) => sendFromMessageAction(agent.slot_id, content, target)}
                        onBranchMessage={(nodeId, entries) => branchFromAssistant(agent, entries, nodeId)}
                        onSwitchBranch={(anchorUserId, nodeId) => switchTeamBranch(agent.slot_id, anchorUserId, nodeId)}
                        onStartMessageEdit={setEditingMessageId}
                        onCancelMessageEdit={() => setEditingMessageId(null)}
                        onTogglePin={togglePinnedMessage}
                        onOpenMessageInspector={(section, node) => setTeamInspector({ section, node })}
                        onStopWake={() => stopWake(agent.slot_id)}
                        onFullscreen={() =>
                          setFullscreenSlotId((current) => (current === agent.slot_id ? null : agent.slot_id))
                        }
                        onRemove={async () => {
                          if (agent.role === "leader") return;
                          if (!(await confirmRemoveAgent(agent.agent_name, agent.status))) return;
                          removeAgentMutation.mutate(agent.slot_id);
                        }}
                        onFocus={() => setActiveSlotId(agent.slot_id)}
                        isFlashing={flashingSlotId === agent.slot_id}
                        setScrollRef={(node) => {
                          scrollRefs.current[agent.slot_id] = node;
                        }}
                        fileInputRef={(node: HTMLInputElement | null) => {
                          teamFileInputsRef.current[agent.slot_id] = node;
                        }}
                        {...composerSharedProps}
                      />
                    );
                  })}
                </div>
                {columnOverflow.left ? (
                  <button
                    type="button"
                    aria-label={text("向左滚动代理列", "Scroll agent columns left")}
                    onClick={() => scrollColumns("left")}
                    className="absolute left-2 top-1/2 inline-flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-md border border-slate-200 bg-white/95 text-slate-600 shadow-panel hover:bg-slate-50 hover:text-slate-950"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>
                ) : null}
                {columnOverflow.right ? (
                  <button
                    type="button"
                    aria-label={text("向右滚动代理列", "Scroll agent columns right")}
                    onClick={() => scrollColumns("right")}
                    className="absolute right-2 top-1/2 inline-flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-md border border-slate-200 bg-white/95 text-slate-600 shadow-panel hover:bg-slate-50 hover:text-slate-950"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </button>
                ) : null}
              </div>
              ) : null}

              {isNarrowColumns ? (
              <div className="flex min-h-0 flex-1">
                {selectedAgent ? (
                  <AgentColumn
                    team={activeTeam}
                    agent={selectedAgent}
                    text={text}
                    tasks={tasks}
                    messages={agentMessages(selectedAgent, messages)}
                    pendingSends={pendingSends}
                    pendingWakeSlotIds={pendingWakeSlotIds}
                    streamingWakes={streamingWakes}
                    settledWakeCutoffs={settledWakeCutoffs}
                    composer={selectedComposer}
                    attachments={attachmentsBySlotId[selectedAgent.slot_id] ?? []}
                    bottomPanel={bottomPanelBySlotId[selectedAgent.slot_id] ?? null}
                    tools={toolsByAgentId.get(selectedAgent.agent_id) ?? []}
	                    isSending={pendingSends.some((send) => {
	                      const selectedTarget = defaultComposerTarget(selectedAgent);
	                      const selectedMode = selectedComposer.mode ?? "chat";
	                      const files = (attachmentsBySlotId[selectedAgent.slot_id] ?? []).map(
	                        (attachment) => attachment.name,
	                      );
	                      return (
	                        send.key ===
	                          teamPendingSendKey(
	                            selectedAgent.slot_id,
	                            selectedTarget,
	                            selectedMode,
	                            selectedComposer.draft.trim(),
	                            files,
	                          ) ||
	                        (send.sourceSlotId === selectedAgent.slot_id &&
	                          send.target === selectedTarget &&
	                          send.content === selectedComposer.draft.trim() &&
	                          send.mode === selectedMode &&
	                          send.files.join("\n") === files.join("\n"))
	                      );
	                    })}
                    editingMessageId={editingMessageId}
                    pinnedMessageIds={pinnedMessageIds}
                    branchGroups={branchGroupsBySlotId[selectedAgent.slot_id] ?? {}}
                    contextCompressions={contextCompressionsBySlotId[selectedAgent.slot_id] ?? {}}
                    onCompressContext={compressTeamContext}
                    onComposerChange={(next) => updateComposer(selectedAgent.slot_id, next)}
	                    onSend={(content, target, mode) =>
	                      sendFromComposer(
	                        selectedAgent,
	                        content,
	                        target,
	                        attachmentsBySlotId[selectedAgent.slot_id] ?? [],
	                        mode,
	                      )
	                    }
                    onMessageActionSend={(content, target) => sendFromMessageAction(selectedAgent.slot_id, content, target)}
                    onBranchMessage={(nodeId, entries) => branchFromAssistant(selectedAgent, entries, nodeId)}
                    onSwitchBranch={(anchorUserId, nodeId) =>
                      switchTeamBranch(selectedAgent.slot_id, anchorUserId, nodeId)
                    }
                    onStartMessageEdit={setEditingMessageId}
                    onCancelMessageEdit={() => setEditingMessageId(null)}
                    onTogglePin={togglePinnedMessage}
                    onOpenMessageInspector={(section, node) => setTeamInspector({ section, node })}
                    onStopWake={() => stopWake(selectedAgent.slot_id)}
                    onFullscreen={() => setFullscreenSlotId(selectedAgent.slot_id)}
                    onRemove={async () => {
                      if (selectedAgent.role === "leader") return;
                      if (!(await confirmRemoveAgent(selectedAgent.agent_name, selectedAgent.status))) return;
                      removeAgentMutation.mutate(selectedAgent.slot_id);
                    }}
                    onFocus={() => setActiveSlotId(selectedAgent.slot_id)}
                    isFlashing={flashingSlotId === selectedAgent.slot_id}
                    setScrollRef={(node) => {
                      scrollRefs.current[selectedAgent.slot_id] = node;
                    }}
                    fileInputRef={(node: HTMLInputElement | null) => {
                      teamFileInputsRef.current[selectedAgent.slot_id] = node;
                    }}
                    {...composerSharedProps}
                  />
                ) : null}
              </div>
              ) : null}
            </div>
          </div>
        </main>
      </div>
      <TeamCreateModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(team) => navigate(`/teams/${team.id}`)}
      />
      <TeamAddMemberModal
        open={addMemberOpen}
        agents={agentDefinitions}
        selectedAgentId={selectedNewMemberAgent?.id ?? newMemberAgentId ?? ""}
        memberName={newMemberName}
        loading={agentsQuery.isLoading}
        errorMessage={addMemberError ?? (addAgentMutation.error instanceof Error ? addAgentMutation.error.message : null)}
        submitting={addAgentMutation.isPending}
        text={text}
        onClose={() => {
          setAddMemberOpen(false);
          setNewMemberName("");
          setNewMemberAgentId(null);
        }}
        onAgentChange={setNewMemberAgentId}
        onMemberNameChange={setNewMemberName}
        onSubmit={submitNewMember}
      />
      <InspectorDrawer
        section={teamInspector?.section ?? null}
        activeRunId={teamInspector?.node.run_id ?? null}
        pendingApprovalCount={0}
        artifacts={teamInspector?.node.artifacts ?? []}
        onClose={() => setTeamInspector(null)}
      />
      {confirmDialog}
    </ConsoleShell>
  );
}

function defaultComposerTarget(agent: TeamAgent) {
  return agent.role === "leader" ? "leader" : agent.slot_id;
}

function TeamTaskBoard({
  team,
  agents,
  tasks,
  text,
  onClose,
}: {
  team: Team;
  agents: TeamAgent[];
  tasks: TeamTask[];
  text: TextFn;
  onClose: () => void;
}) {
  const agentNames = new Map(agents.map((agent) => [agent.slot_id, agent.agent_name]));
  const statuses: TeamTask["status"][] = ["pending", "in_progress", "completed"];
  const visibleTasks = tasks.filter((task) => task.status !== "deleted");

  return (
    <div
      role="dialog"
      aria-label={text("团队任务板", "Team task board")}
      className="absolute right-1 top-full z-40 mt-2 w-[min(360px,calc(100vw-1rem))] overflow-hidden rounded-lg border border-slate-200 bg-white text-left shadow-xl"
    >
      <div className="flex items-center justify-between gap-2 border-b border-slate-200 px-3 py-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 text-sm font-semibold text-slate-950">
            <ClipboardList className="h-4 w-4" />
            <span>{text("任务板", "Task board")}</span>
            <Badge tone="neutral">{visibleTasks.length}</Badge>
          </div>
          <div className="mt-0.5 truncate text-[11px] text-slate-500">{team.name}</div>
        </div>
        <button
          type="button"
          aria-label={text("关闭任务板", "Close task board")}
          onClick={onClose}
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-950"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="max-h-[64vh] overflow-auto px-3 py-2">
        {visibleTasks.length === 0 ? (
          <div className="rounded-md border border-dashed border-slate-200 bg-slate-50/60 px-3 py-6 text-center text-xs text-slate-500">
            {text("暂无团队任务", "No team tasks yet")}
          </div>
        ) : (
          <div className="space-y-3">
            {statuses.map((status) => {
              const scopedTasks = visibleTasks.filter((task) => task.status === status);
              if (scopedTasks.length === 0) return null;
              return (
                <section key={status} aria-label={teamTaskStatusLabel(status)}>
                  <div className="mb-1.5 flex items-center justify-between">
                    <div className="text-[11px] font-semibold uppercase text-slate-500">
                      {teamTaskStatusLabel(status)}
                    </div>
                    <Badge tone={teamTaskStatusTone(status)}>{scopedTasks.length}</Badge>
                  </div>
                  <div className="overflow-hidden rounded-md border border-slate-200 bg-white">
                    {scopedTasks.map((task, index) => (
                      <div
                        key={task.id}
                        className={cn(
                          "px-3 py-2",
                          index > 0 ? "border-t border-slate-100" : "",
                        )}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="truncate text-xs font-medium text-slate-900">{task.subject}</div>
                            <div className="mt-0.5 line-clamp-2 text-[11px] leading-4 text-slate-500">
                              {task.description || text("无描述", "No description")}
                            </div>
                          </div>
                          <Badge tone={teamTaskStatusTone(task.status)}>
                            {teamTaskStatusLabel(task.status)}
                          </Badge>
                        </div>
                        <div className="mt-1.5 flex items-center justify-between gap-2 text-[11px] text-slate-400">
                          <span className="truncate">
                            {text("负责人", "Owner")} ·{" "}
                            {task.owner_slot_id
                              ? agentNames.get(task.owner_slot_id) ?? task.owner_slot_id
                              : text("队长", "Leader")}
                          </span>
                          {task.blocked_by_json.length > 0 ? (
                            <span>{text("依赖", "Deps")} {task.blocked_by_json.length}</span>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function TeamAddMemberModal({
  open,
  agents,
  selectedAgentId,
  memberName,
  loading,
  errorMessage,
  submitting,
  text,
  onClose,
  onAgentChange,
  onMemberNameChange,
  onSubmit,
}: {
  open: boolean;
  agents: AgentDefinition[];
  selectedAgentId: string;
  memberName: string;
  loading: boolean;
  errorMessage: string | null;
  submitting: boolean;
  text: TextFn;
  onClose: () => void;
  onAgentChange: (agentId: string) => void;
  onMemberNameChange: (name: string) => void;
  onSubmit: () => void;
}) {
  const selectedAgent = agents.find((agent) => agent.id === selectedAgentId) ?? agents[0] ?? null;
  const agentOptions = agents.map((agent) => ({
    value: agent.id,
    label: agent.name,
    description: agent.description,
    meta: `${agent.model_provider}/${agent.model_name}`,
    leading: <Bot className="h-3.5 w-3.5" />,
  }));
  const canSubmit = Boolean(selectedAgent) && !submitting;

  return (
    <ConfigDialog
      open={open}
      title={text("添加成员", "Add member")}
      description={text("选择一个智能体定义加入当前团队。", "Choose an agent definition to join this team.")}
      onClose={onClose}
      className="max-w-lg"
    >
        <div className="space-y-4">
          <div className="space-y-1.5 text-xs font-medium text-slate-600">
            <div className="flex items-center justify-between gap-2">
              <span>{text("智能体定义", "Agent definition")}</span>
              <Badge tone={selectedAgent ? "success" : errorMessage ? "failed" : "neutral"}>
                {loading
                  ? text("加载中", "Loading")
                  : selectedAgent
                    ? text("已选择", "Selected")
                    : text("请选择", "Select")}
              </Badge>
            </div>
            {agents.length === 0 ? (
              <div className="flex items-center justify-center rounded-md border border-dashed border-slate-200 bg-slate-50/70 px-4 py-5 text-xs text-slate-500">
                {loading
                  ? text("正在加载智能体...", "Loading agents...")
                  : text("没有可用的智能体", "No supported agents installed")}
              </div>
            ) : (
              <MenuSelect
                ariaLabel={text("智能体定义", "Agent definition")}
                value={selectedAgentId}
                onChange={onAgentChange}
                placeholder={text("选择智能体", "Select agent")}
                options={agentOptions}
                buttonClassName="rounded-md border-slate-200 px-3 py-2 shadow-none"
                menuClassName="max-h-72"
              />
            )}
          </div>
          <label className="flex flex-col gap-1.5 text-xs font-medium text-slate-600">
            {text("成员名称", "Member name")}
            <Input
              value={memberName}
              onChange={(event) => onMemberNameChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && canSubmit) {
                  event.preventDefault();
                  onSubmit();
                }
              }}
              placeholder={selectedAgent?.name ?? text("例如：前端工程师", "Example: Frontend engineer")}
            />
          </label>
          {selectedAgent ? (
            <div className="rounded-md border border-slate-100 bg-slate-50/70 p-3 text-xs text-slate-500">
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-1.5 font-medium text-slate-700">
                  <Bot className="h-3.5 w-3.5" />
                  <span className="truncate">{selectedAgent.name}</span>
                </div>
                <Badge tone="success">{statusLabel(selectedAgent.status)}</Badge>
              </div>
              <div className="mt-2 truncate font-mono text-[11px] text-slate-600">
                {selectedAgent.id} · {selectedAgent.model_provider}/{selectedAgent.model_name}
              </div>
            </div>
          ) : null}
          {errorMessage ? <div className="text-xs text-red-600">{errorMessage}</div> : null}
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-200 pt-5">
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            {text("取消", "Cancel")}
          </Button>
          <Button onClick={onSubmit} disabled={!canSubmit}>
            <Plus className="h-3.5 w-3.5" />
            {submitting ? text("添加中", "Adding") : text("添加成员", "Add member")}
          </Button>
        </div>
    </ConfigDialog>
  );
}

type AgentColumnProps = {
  team: Team;
  agent: TeamAgent;
  text: TextFn;
  tasks: TeamTask[];
  messages: TeamMailboxMessage[];
  pendingSends: PendingSend[];
  pendingWakeSlotIds: string[];
  streamingWakes: StreamingWake[];
  settledWakeCutoffs: SettledWakeCutoffs;
  composer: TeamComposerState;
  attachments: ComposerAttachment[];
  bottomPanel: TeamBottomPanel;
  tools: ToolMetadata[];
  modelOptions: ModelOption[];
  contextMaxTokens: number;
  autoCompressionRatio: number;
  onContextMaxTokensChange: (value: number) => void;
  onAutoCompressionRatioChange: (value: number) => void;
  onClearContextCompression: (slotId: string, branchKey: string) => void;
  addComposerFiles: (slotId: string) => void;
  handleComposerFilesSelected: (slotId: string, event: ChangeEvent<HTMLInputElement>) => void;
  removeComposerAttachment: (slotId: string, attachmentId: string) => void;
  setComposerBottomPanel: (slotId: string, panel: TeamBottomPanel) => void;
  onModelChange: TeamModelChangeHandler;
  fileInputRef: (node: HTMLInputElement | null) => void;
  isSending: boolean;
  editingMessageId: string | null;
  pinnedMessageIds: string[];
  branchGroups: Record<string, TeamBranchGroup>;
  contextCompressions: Record<string, ContextCompressionSummary>;
  onCompressContext: (
    agent: TeamAgent,
    entries: TeamConversationEntry[],
    reason?: "manual" | "background" | "pre_send",
  ) => Promise<ContextCompressionSummary | null>;
  onComposerChange: (value: TeamComposerStateUpdater) => void;
  onSend: (content: string, target: string, mode: WorkspaceMode) => void;
  onMessageActionSend: (content: string, target: string) => void;
  onBranchMessage: (nodeId: string, entries: TeamConversationEntry[]) => void;
  onSwitchBranch: (anchorUserId: string, nodeId: string) => void;
  onStartMessageEdit: (nodeId: string) => void;
  onCancelMessageEdit: () => void;
  onTogglePin: (nodeId: string) => void;
  onOpenMessageInspector: (section: InspectorSection, node: ConversationNode) => void;
  onStopWake: () => void;
  onFullscreen: () => void;
  onRemove: () => void;
  onFocus: () => void;
  isFlashing?: boolean;
  setScrollRef: (node: HTMLDivElement | null) => void;
  visibleColumnCount?: number;
  fullscreen?: boolean;
};

function AgentColumn({
  team,
  agent,
  text,
  tasks,
  messages,
  pendingSends,
  pendingWakeSlotIds,
  streamingWakes,
  settledWakeCutoffs,
  composer,
  attachments,
  bottomPanel,
  tools,
  modelOptions,
  contextMaxTokens,
  autoCompressionRatio,
  onContextMaxTokensChange,
  onAutoCompressionRatioChange,
  onClearContextCompression,
  addComposerFiles,
  handleComposerFilesSelected,
  removeComposerAttachment,
  setComposerBottomPanel,
  onModelChange,
  fileInputRef,
  isSending,
  editingMessageId,
  pinnedMessageIds,
  branchGroups,
  contextCompressions,
  onCompressContext,
  onComposerChange,
  onSend,
  onMessageActionSend,
  onBranchMessage,
  onSwitchBranch,
  onStartMessageEdit,
  onCancelMessageEdit,
  onTogglePin,
  onOpenMessageInspector,
  onStopWake,
  onFullscreen,
  onRemove,
  onFocus,
  isFlashing,
  setScrollRef,
  visibleColumnCount,
  fullscreen = false,
}: AgentColumnProps) {
  const isLeader = agent.role === "leader";
  const roleLabel = isLeader ? text("队长", "Leader") : text("成员", "Teammate");
  const taskScope = tasks.filter((task) => isLeader || task.owner_slot_id === agent.slot_id);
  const selectedTarget = defaultComposerTarget(agent);
  const selectedMode = composer.mode ?? "chat";
  const status = displayAgentStatus(agent, pendingWakeSlotIds, streamingWakes, settledWakeCutoffs);
  const visibleEntries = teamConversationEntriesWithPending(
    team,
    agent,
    messages,
    pendingSends,
    pendingWakeSlotIds,
    streamingWakes,
    settledWakeCutoffs,
  );
  const branchVisibleEntries = useMemo(
    () => applyTeamBranchGroups(visibleEntries, branchGroups),
    [branchGroups, visibleEntries],
  );
  const lastAssistantId = findLastAssistantNodeId(branchVisibleEntries);
  const canStopWake = status === "active";
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const rawContextUsageCurrent = useMemo(
    () => teamContextTokenEstimate(visibleEntries, composer.draft),
    [composer.draft, visibleEntries],
  );
  const compressionBranchKey = useMemo(
    () => teamCompressionKey(team, agent, visibleEntries),
    [agent, team, visibleEntries],
  );
  const activeCompression = useMemo(
    () =>
      selectBestCompressionSummary({
        summaries: contextCompressions,
        branchKey: compressionBranchKey,
        activePath: visibleEntries.map((entry) => entry.node),
        pinnedNodeIds: pinnedMessageIds,
        providerId: agent.model_provider || modelOptions[0]?.providerId || null,
        modelId: agent.model_name || modelOptions[0]?.modelId || null,
      }) ?? contextCompressions[compressionBranchKey] ?? null,
    [agent.model_name, agent.model_provider, compressionBranchKey, contextCompressions, modelOptions, pinnedMessageIds, visibleEntries],
  );
  const contextUsageCurrent = useMemo(
    () =>
      teamEffectiveContextTokenEstimate({
        entries: visibleEntries,
        draft: composer.draft,
        summary: activeCompression,
        branchKey: compressionBranchKey,
        pinnedNodeIds: pinnedMessageIds,
        providerId: agent.model_provider || modelOptions[0]?.providerId || null,
        modelId: agent.model_name || modelOptions[0]?.modelId || null,
      }),
    [
      activeCompression,
      agent.model_name,
      agent.model_provider,
      compressionBranchKey,
      composer.draft,
      modelOptions,
      pinnedMessageIds,
      visibleEntries,
    ],
  );
  const contextUsageRatio = contextMaxTokens > 0 ? contextUsageCurrent / contextMaxTokens : 0;
  const usageSummary = useMemo(() => summarizeTeamUsage(visibleEntries), [visibleEntries]);
  const modelLabel = agent.model_name || modelOptions[0]?.modelLabel || text("默认模型", "default");
  const selectedModelId = agent.model_name || modelOptions[0]?.modelId || null;
  const selectedProviderId = agent.model_provider || modelOptions[0]?.providerId || null;
  const messageListSignature = useMemo(
    () => visibleEntries.map((entry) => `${entry.node.id}:${entry.node.content.length}`).join("|"),
    [visibleEntries],
  );
  const streamSignature = useMemo(
    () =>
      visibleEntries
        .map((entry) => `${entry.node.id}:${entry.node.state}:${entry.node.content.length}`)
        .join("|"),
    [visibleEntries],
  );
  const scrollConversationToBottom = useCallback((behavior: ScrollBehavior) => {
    const node = scrollerRef.current;
    if (!node) return;
    if (typeof node.scrollTo === "function") {
      node.scrollTo({ top: node.scrollHeight, behavior });
      return;
    }
    node.scrollTop = node.scrollHeight;
  }, []);
  useLayoutEffect(() => {
    scrollConversationToBottom("auto");
  }, [agent.slot_id, messageListSignature, scrollConversationToBottom]);

  useEffect(() => {
    scrollConversationToBottom("smooth");
  }, [scrollConversationToBottom, streamSignature]);

  const handleInsertMention = useCallback(
    (toolName: string) => {
      onComposerChange((current) => {
        const separator =
          current.draft.length === 0 || current.draft.endsWith(" ") || current.draft.endsWith("\n") ? "" : " ";
        return { ...current, draft: `${current.draft}${separator}@${toolName} ` };
      });
      window.requestAnimationFrame(() => composerRef.current?.focus());
    },
    [onComposerChange],
  );
  const handleCompressContext = useCallback(() => {
    if (canStopWake) return;
    setComposerBottomPanel(agent.slot_id, null);
    void onCompressContext(agent, visibleEntries, "manual");
  }, [agent, canStopWake, onCompressContext, setComposerBottomPanel, visibleEntries]);
  const backgroundCompressionKeyRef = useRef<string | null>(null);
  useEffect(() => {
    if (canStopWake) return;
    if (contextUsageRatio < autoCompressionRatio) return;
    const last = visibleEntries[visibleEntries.length - 1];
    if (!last || last.node.role !== "assistant" || last.node.state !== "done") return;
    const key = `${compressionBranchKey}:${last.node.id}:${Math.round(contextUsageCurrent)}`;
    if (backgroundCompressionKeyRef.current === key) return;
    backgroundCompressionKeyRef.current = key;
    void onCompressContext(agent, visibleEntries, "background");
  }, [
    agent,
    autoCompressionRatio,
    canStopWake,
    compressionBranchKey,
    contextUsageCurrent,
    contextUsageRatio,
    onCompressContext,
    visibleEntries,
  ]);
  const handleSlashDispatch = useCallback(
    (cmd: SlashCommand, args: string) => {
      switch (cmd.name) {
        case "pin":
          if (lastAssistantId) onTogglePin(lastAssistantId);
          onComposerChange((current) => ({ ...current, draft: "" }));
          return;
        case "clear":
        case "search":
        case "help":
          onComposerChange((current) => ({ ...current, draft: "" }));
          return;
        case "chat":
          onComposerChange((current) => ({ ...current, draft: "", mode: "chat" }));
          return;
        case "plan":
          onComposerChange((current) => ({ ...current, draft: "", mode: "codex_plan" }));
          return;
        case "run":
          onComposerChange((current) => ({ ...current, draft: "", mode: "plan" }));
          return;
        case "goal":
          onComposerChange((current) => ({ ...current, draft: "", mode: "goal" }));
          return;
        case "compress":
          setComposerBottomPanel(agent.slot_id, null);
          onComposerChange((current) => ({ ...current, draft: "" }));
          void onCompressContext(agent, visibleEntries, "manual");
          return;
        case "model":
          setComposerBottomPanel(agent.slot_id, "model");
          onComposerChange((current) => ({ ...current, draft: "" }));
          return;
        case "mcp": {
          const mcpCount = tools.filter(isMcpTool).length;
          setComposerBottomPanel(agent.slot_id, "mcp");
          onComposerChange((current) => ({ ...current, draft: "" }));
          notifyFeedback({
            tone: mcpCount > 0 ? "success" : "info",
            title: mcpCount > 0 ? text("MCP 列表已打开", "MCP list opened") : text("暂无可用 MCP", "No MCP tools available"),
            description:
              mcpCount > 0
                ? text(
                    `当前团队列有 ${mcpCount} 个可用 MCP。点击条目可插入 @工具名。`,
                    `This team column has ${mcpCount} available MCP tools. Select one to insert its @mention.`,
                  )
                : text(
                    "已打开 MCP 列表。可以先到 MCP / 技能商店安装并挂载能力。",
                    "The MCP list is open. Install and attach capabilities from the MCP / Skill marketplace first.",
                  ),
          });
          return;
        }
        case "tool": {
          const name = args.replace(/^@/, "").split(/\s+/)[0] ?? "";
          if (name) {
            onComposerChange((current) => ({ ...current, draft: `@${name} ` }));
            window.requestAnimationFrame(() => composerRef.current?.focus());
          }
          return;
        }
        default: {
          const exhaustive: never = cmd.name;
          void exhaustive;
        }
      }
    },
    [
      agent,
      lastAssistantId,
      onCompressContext,
      onComposerChange,
      onTogglePin,
      setComposerBottomPanel,
      text,
      tools,
      visibleEntries,
    ],
  );
  const submitComposer = () => {
    if (!composer.draft.trim() || isSending) return;
    onSend(composer.draft.trim(), selectedTarget, selectedMode);
  };
  const columnStyle =
    fullscreen
      ? { flex: "1 1 100%", minWidth: "min(100%, 400px)" }
      : visibleColumnCount && visibleColumnCount <= 2
        ? { flex: "1 1 320px", minWidth: "min(320px, 100%)" }
        : { flex: "1 0 clamp(288px, 21vw, 304px)", minWidth: "min(288px, 100%)" };

  return (
    <div
      ref={setScrollRef}
      role="region"
      aria-label={`${agent.agent_name} ${roleLabel} ${text("列", "column")}`}
      className={cn(
        "flex h-full min-w-0 snap-start flex-col overflow-hidden border-r border-slate-200 transition-opacity duration-150",
        isLeader ? "border-l-4 border-l-slate-900 bg-slate-50/70" : "bg-white",
        isFlashing ? "opacity-60" : "opacity-100",
      )}
      style={columnStyle}
      onClick={onFocus}
    >
      <div
        className={cn(
          "flex min-h-14 shrink-0 items-center justify-between gap-3 border-b border-slate-200 px-3 py-2.5",
          isLeader ? "bg-slate-50" : "bg-white",
        )}
      >
        <div className="flex min-w-0 items-center gap-2">
          <div
            aria-hidden="true"
            className={cn(
              "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-white",
              isLeader ? "bg-slate-950" : "bg-slate-700",
            )}
          >
            {isLeader ? <UsersRound className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <div className="truncate text-[14px] font-semibold text-slate-950">{agent.agent_name}</div>
              {isLeader ? <Badge tone="running">{text("队长", "Leader")}</Badge> : null}
              <Badge tone={teamAgentStatusTone(status)}>{teamAgentStatusLabel(status)}</Badge>
            </div>
            <div className="mt-0.5 truncate font-mono text-[11px] text-slate-400">
              {agent.model_provider} / {agent.model_name}
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <ContextSummaryManager
            summary={activeCompression}
            onRecompress={() => {
              handleCompressContext();
            }}
            onClear={() => {
              onClearContextCompression(agent.slot_id, activeCompression?.branchKey ?? compressionBranchKey);
              notifyFeedback({
                tone: "info",
                title: text("摘要已清除", "Context summary cleared"),
                description: text(
                  `“${agent.agent_name}”后续发送将重新携带原始上下文内容。`,
                  `${agent.agent_name} will use the original conversation context on the next send.`,
                ),
              });
            }}
            text={text}
          />
          {!isLeader ? (
            <button
              type="button"
              aria-label={text("移除成员", "Remove teammate")}
              title={text("移除成员", "Remove teammate")}
              onClick={(event) => {
                event.stopPropagation();
                onRemove();
              }}
              className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-transparent text-slate-400 hover:border-red-100 hover:bg-red-50 hover:text-red-600"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          ) : null}
          <button
            type="button"
            aria-label={text("切换全屏列", "Toggle full-screen column")}
            title={text("切换全屏列", "Toggle full-screen column")}
            onClick={onFullscreen}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 text-slate-500 hover:bg-slate-50 hover:text-slate-900"
          >
            <Maximize2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <div ref={scrollerRef} className="min-h-0 flex-1 overflow-auto bg-white px-3 py-3">
        <div className="space-y-3">
          {branchVisibleEntries.length > 0 ? (
            branchVisibleEntries.map((entry) => (
              <TeamChatMessage
                key={entry.node.id}
                entry={entry}
                entries={visibleEntries}
                branchGroups={branchGroups}
                editingMessageId={editingMessageId}
                pinnedMessageIds={pinnedMessageIds}
                canRegenerate={entry.node.id === lastAssistantId && entry.node.state !== "streaming"}
                onStartEdit={onStartMessageEdit}
                onCancelEdit={onCancelMessageEdit}
                onSaveEdit={(nodeId, newContent) => {
                  const current = branchVisibleEntries.find((candidate) => candidate.node.id === nodeId);
                  if (!current) return;
                  onCancelMessageEdit();
                  onMessageActionSend(newContent, current.target);
                }}
                onCopy={async (nodeId) => {
                  const current = branchVisibleEntries.find((candidate) => candidate.node.id === nodeId);
                  const copied = await copyText(stripThinkBlocks(current?.node.content ?? ""));
                  if (!copied) {
                    notifyFeedback({
                      tone: "error",
                      title: text("复制失败", "Copy failed"),
                      description: text(
                        "当前浏览器未允许写入剪贴板，请检查权限后重试。",
                        "The browser could not write to the clipboard. Check permissions and retry.",
                      ),
                    });
                  }
                  return copied;
                }}
                onRegenerate={(nodeId) => {
                  const previousUser = previousUserContent(branchVisibleEntries, nodeId);
                  if (!previousUser) return;
                  onMessageActionSend(previousUser.content, previousUser.target);
                }}
                onTogglePin={onTogglePin}
                onOpenInspector={onOpenMessageInspector}
                onBranch={onBranchMessage}
                onSwitchBranch={onSwitchBranch}
              />
            ))
          ) : (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-white px-4 py-5 text-center text-xs text-slate-400 shadow-sm">
              {team.name} {isLeader ? text("队长", "Leader") : agent.agent_name}
            </div>
          )}
        </div>

        <details className="mt-3 rounded-2xl border border-slate-200 bg-white px-3 py-2.5 shadow-sm">
          <summary className="cursor-pointer text-xs font-semibold text-slate-700">
            {text("查看步骤", "View steps")} ·{" "}
            {text(`${taskScope.length} 项任务`, `${taskScope.length} tasks`)}
          </summary>
          <div className="mt-3 space-y-2">
            {taskScope.length > 0 ? (
              taskScope.map((task) => (
                <div key={task.id} className="rounded-md border border-slate-200 bg-white px-2.5 py-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate text-xs font-medium text-slate-900">{task.subject}</div>
                      <div className="mt-0.5 text-[11px] text-slate-500">{task.description || "-"}</div>
                    </div>
                    <Badge tone={teamTaskStatusTone(task.status)}>{teamTaskStatusLabel(task.status)}</Badge>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-[11px] text-slate-400">{text("暂无步骤", "No steps yet")}</div>
            )}
          </div>
        </details>

      </div>

      <div
        className="shrink-0 border-t border-slate-200 bg-white px-3 pb-4 pt-5"
        data-testid={`team-composer-${agent.slot_id}`}
      >
        <div className="relative mx-auto w-full max-w-3xl">
          <TeamBottomPopover
            open={bottomPanel !== null}
            onClose={() => setComposerBottomPanel(agent.slot_id, null)}
            align={bottomPanel === "model" ? "right" : "left"}
            title={
              bottomPanel === "model"
                ? text("切换模型", "Switch model")
                : bottomPanel === "mcp"
                  ? text("可用 MCP", "Available MCP")
                : text("输入设置", "Composer settings")
            }
          >
            {bottomPanel === "model" ? (
              <TeamModelPanel
                providers={modelOptions}
                selectedProviderId={selectedProviderId}
                selectedModelId={selectedModelId}
                modelLabelFallback={modelLabel}
                onModelChange={(providerId, modelId) => onModelChange(agent.slot_id, providerId, modelId)}
                text={text}
              />
            ) : (
              <TeamComposerSettingsPanel
                workspaceMode={selectedMode}
                onWorkspaceModeChange={(mode) => onComposerChange((current) => ({ ...current, mode }))}
                attachmentNames={attachments.map((attachment) => attachment.name)}
                onAddFiles={() => addComposerFiles(agent.slot_id)}
                tools={tools}
                onInsertMention={handleInsertMention}
                text={text}
                contextMaxTokens={contextMaxTokens}
                onContextMaxTokensChange={onContextMaxTokensChange}
                autoCompressionRatio={autoCompressionRatio}
                onAutoCompressionRatioChange={onAutoCompressionRatioChange}
                pluginsInitiallyOpen={bottomPanel === "mcp"}
              />
            )}
          </TeamBottomPopover>
          <ChatComposer
            ref={composerRef}
            containerClassName="px-0 sm:px-0 lg:px-0"
            draft={composer.draft}
            onDraftChange={(draft) => onComposerChange((current) => ({ ...current, draft }))}
            onSubmit={submitComposer}
            onPause={onStopWake}
            isStreaming={canStopWake}
            mode={selectedMode}
            onChangeMode={(mode) => onComposerChange((current) => ({ ...current, mode }))}
            placeholder={teamComposerPlaceholder(selectedMode, text)}
            optionsOpen={bottomPanel !== null}
            onOptionsToggle={() =>
              setComposerBottomPanel(
                agent.slot_id,
                bottomPanel === "settings" || bottomPanel === "mcp" ? null : "settings",
              )
            }
            goalModeToggleVisible={false}
            metadata={<TeamComposerMetadataRow usage={usageSummary} text={text} />}
            bottomCenter={
              <div className="flex min-w-0 flex-1 items-center justify-end gap-1.5">
                <ContextRing
                  ratio={contextUsageRatio}
                  currentTokens={contextUsageCurrent}
                  rawTokens={rawContextUsageCurrent}
                  limitTokens={contextMaxTokens}
                  onCompress={handleCompressContext}
                  disabled={canStopWake}
                  status={activeCompression?.status ?? "idle"}
                />
                <button
                  type="button"
                  onClick={() =>
                    setComposerBottomPanel(agent.slot_id, bottomPanel === "model" ? null : "model")
                  }
                  className="inline-flex h-8 min-w-0 max-w-[8rem] items-center gap-1 rounded-md px-2 text-xs text-slate-600 transition-colors hover:bg-slate-100"
                  aria-label={text(`切换模型：${modelLabel}`, `Switch model: ${modelLabel}`)}
                  title={modelLabel}
                >
                  <Brain aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{modelLabel}</span>
                </button>
              </div>
            }
            attachments={attachments}
            onRemoveAttachment={(attachmentId) => removeComposerAttachment(agent.slot_id, attachmentId)}
            isEditLocked={isSending}
            onSlashDispatch={handleSlashDispatch}
          />
          <input
            ref={fileInputRef}
            type="file"
            multiple
            aria-label={text("添加照片和文件", "Add photos and files")}
            className="hidden"
            onChange={(event) => handleComposerFilesSelected(agent.slot_id, event)}
          />
        </div>
      </div>
    </div>
  );
}

function TeamChatMessage({
  entry,
  entries,
  branchGroups,
  editingMessageId,
  pinnedMessageIds,
  canRegenerate,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onCopy,
  onRegenerate,
  onTogglePin,
  onOpenInspector,
  onBranch,
  onSwitchBranch,
}: {
  entry: TeamConversationEntry;
  entries: TeamConversationEntry[];
  branchGroups: Record<string, TeamBranchGroup>;
  editingMessageId: string | null;
  pinnedMessageIds: string[];
  canRegenerate: boolean;
  onStartEdit: (nodeId: string) => void;
  onCancelEdit: () => void;
  onSaveEdit: (nodeId: string, newContent: string) => void;
  onCopy: (nodeId: string) => Promise<boolean>;
  onRegenerate: (nodeId: string) => void;
  onTogglePin: (nodeId: string) => void;
  onOpenInspector: (section: InspectorSection, node: ConversationNode) => void;
  onBranch: (nodeId: string, entries: TeamConversationEntry[]) => void;
  onSwitchBranch: (anchorUserId: string, nodeId: string) => void;
}) {
  const branchGroup = Object.values(branchGroups).find((group) =>
    group.branchNodeIds.includes(entry.node.id),
  );
  const branchIndex =
    branchGroup?.branchNodeIds.findIndex((nodeId) => nodeId === entry.node.id) ?? -1;
  return (
    <div data-conversation-node-id={entry.node.id} className="space-y-1">
      <ChatMessageBubble
        node={entry.node}
        onOpenInspector={(section) => onOpenInspector(section, entry.node)}
        editingNodeId={editingMessageId}
        onStartEdit={onStartEdit}
        onCancelEdit={onCancelEdit}
        onSaveEdit={onSaveEdit}
        canRegenerate={canRegenerate}
        isStreaming={false}
        onCopy={onCopy}
        onRegenerate={onRegenerate}
        isPinned={pinnedMessageIds.includes(entry.node.id)}
        onTogglePin={onTogglePin}
        onBranch={entry.node.role === "assistant" ? () => onBranch(entry.node.id, entries) : undefined}
      />
      {branchGroup && branchIndex >= 0 ? (
        <div className="ml-11 flex justify-start">
          <BranchSwitcher
            currentIndex={branchIndex + 1}
            totalBranches={branchGroup.branchNodeIds.length}
            onPrevious={() => {
              const previous = branchGroup.branchNodeIds[branchIndex - 1];
              if (previous) onSwitchBranch(branchGroup.anchorUserId, previous);
            }}
            onNext={() => {
              const next = branchGroup.branchNodeIds[branchIndex + 1];
              if (next) onSwitchBranch(branchGroup.anchorUserId, next);
            }}
          />
        </div>
      ) : null}
      {entry.node.run_id ? (
        <TeamMessageRunLinks
          runId={entry.node.run_id}
          runStatus={entry.runStatus}
          runCreatedAt={entry.runCreatedAt}
        />
      ) : null}
    </div>
  );
}

function TeamBottomPopover({
  open,
  onClose,
  align,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  align: "left" | "right";
  title: string;
  children: JSX.Element;
}) {
  const { text } = useI18n();
  const popoverRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;

    const isInsideAnyTeamPopover = (target: EventTarget | null) => {
      if (!(target instanceof Node)) return false;
      const element = target instanceof Element ? target : target.parentElement;
      return Boolean(element?.closest("[data-team-bottom-popover]"));
    };
    const handlePointer = (event: MouseEvent | TouchEvent) => {
      const element = popoverRef.current;
      const target = event.target;
      if (target instanceof Node && element?.contains(target)) return;
      if (isInsideAnyTeamPopover(target)) return;
      onClose();
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };

    document.addEventListener("mousedown", handlePointer);
    document.addEventListener("touchstart", handlePointer);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointer);
      document.removeEventListener("touchstart", handlePointer);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose, open]);

  if (!open) return null;

  return (
    <div
      ref={popoverRef}
      data-team-bottom-popover
      role="dialog"
      aria-modal="false"
      aria-label={title}
      className={cn(
        "absolute bottom-[58px] z-30 w-[min(280px,calc(100vw-2rem))] rounded-2xl border border-slate-200 bg-white p-2 shadow-xl",
        align === "right" ? "right-4" : "left-4",
      )}
    >
      <div className="mb-2 flex items-center justify-between gap-2 border-b border-slate-100 px-1 pb-2">
        <div className="text-xs font-semibold text-slate-900">{title}</div>
        <button
          type="button"
          aria-label={text("关闭弹层", "Close panel")}
          onClick={onClose}
          className="inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
        >
          <X aria-hidden="true" className="h-4 w-4" />
        </button>
      </div>
      {children}
    </div>
  );
}

function TeamComposerSettingsPanel({
  workspaceMode,
  onWorkspaceModeChange,
  attachmentNames,
  onAddFiles,
  tools,
  onInsertMention,
  text,
  contextMaxTokens,
  onContextMaxTokensChange,
  autoCompressionRatio,
  onAutoCompressionRatioChange,
  pluginsInitiallyOpen,
}: {
  workspaceMode: WorkspaceMode;
  onWorkspaceModeChange: (mode: WorkspaceMode) => void;
  attachmentNames: string[];
  onAddFiles: () => void;
  tools: ToolMetadata[];
  onInsertMention: (toolName: string) => void;
  text: TextFn;
  contextMaxTokens: number;
  onContextMaxTokensChange: (value: number) => void;
  autoCompressionRatio: number;
  onAutoCompressionRatioChange: (value: number) => void;
  pluginsInitiallyOpen?: boolean;
}) {
  const [pluginsOpen, setPluginsOpen] = useState(pluginsInitiallyOpen ?? false);
  const mcpTools = tools.filter(isMcpTool);

  useEffect(() => {
    if (pluginsInitiallyOpen) setPluginsOpen(true);
  }, [pluginsInitiallyOpen]);

  return (
    <div className="flex flex-col text-xs text-slate-800">
      <div className="border-b border-slate-100 px-2 py-1.5">
        <ContextMaxTokensSlider value={contextMaxTokens} onChange={onContextMaxTokensChange} />
        <TeamAutoCompressionControl
          value={autoCompressionRatio}
          onChange={onAutoCompressionRatioChange}
          text={text}
        />
      </div>
      <TeamToolActionRow
        icon={<Paperclip aria-hidden="true" className="h-3.5 w-3.5" />}
        label={
          attachmentNames.length > 0
            ? text(
                `添加照片和文件 (${attachmentNames.length})`,
                `Add photos and files (${attachmentNames.length})`,
              )
            : text("添加照片和文件", "Add photos and files")
        }
        onClick={onAddFiles}
      />
      <TeamToolToggleRow
        icon={<ListChecks aria-hidden="true" className="h-3.5 w-3.5" />}
        label={text("计划模式", "Plan mode")}
        checked={workspaceMode === "codex_plan"}
        onChange={(checked) => onWorkspaceModeChange(checked ? "codex_plan" : "chat")}
      />
      <TeamToolToggleRow
        icon={<Target aria-hidden="true" className="h-3.5 w-3.5" />}
        label={text("追踪目标模式", "Goal pursuit mode")}
        checked={workspaceMode === "goal"}
        onChange={(checked) => onWorkspaceModeChange(checked ? "goal" : "chat")}
      />
      <TeamToolActionRow
        icon={<PlugZap aria-hidden="true" className="h-3.5 w-3.5" />}
        label={text("插件 / MCP", "Plugins / MCP")}
        trailing={
          <ChevronRight
            aria-hidden="true"
            className={cn("h-4 w-4 text-slate-400 transition-transform", pluginsOpen ? "rotate-90" : "")}
          />
        }
        onClick={() => setPluginsOpen((open) => !open)}
      />
      {pluginsOpen ? (
        <div className="ml-4 mt-0.5 max-h-24 min-w-0 overflow-y-auto border-l border-slate-200 pl-1.5 pr-0.5">
          {mcpTools.length === 0 ? (
            <p className="px-2 py-1.5 text-xs text-slate-500">
              {text("暂无外部协议功能。", "No MCP capabilities")}
            </p>
          ) : (
            mcpTools.map((tool) => (
              <button
                key={`${tool.source ?? "tool"}:${tool.name}`}
                type="button"
                onClick={() => onInsertMention(tool.name)}
                className="block min-w-0 w-full rounded-md px-1.5 py-1 text-left text-[11px] text-slate-600 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
              >
                <span className="block truncate font-mono">@{tool.name}</span>
                <span className="block truncate text-[11px] text-slate-500">
                  {formatMcpCapability(tool)}
                </span>
              </button>
            ))
          )}
        </div>
      ) : null}
    </div>
  );
}

function TeamAutoCompressionControl({
  value,
  onChange,
  text,
}: {
  value: number;
  onChange: (next: number) => void;
  text: TextFn;
}) {
  const pct = Math.round(value * 100);
  return (
    <div className="mt-2 flex flex-col gap-1.5">
      <div className="flex items-center justify-between gap-2">
        <label className="text-[11px] font-medium text-slate-700">
          {text("自动压缩阈值", "Auto compression threshold")}
        </label>
        <span className="font-mono text-[11px] text-slate-600">{pct}%</span>
      </div>
      <input
        type="range"
        min={0.5}
        max={0.95}
        step={0.05}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        aria-label={text("自动压缩阈值", "Auto compression threshold")}
        className="h-1 accent-slate-900"
      />
    </div>
  );
}

function TeamModelPanel({
  providers,
  selectedProviderId,
  selectedModelId,
  modelLabelFallback,
  onModelChange,
  text,
}: {
  providers: ModelOption[];
  selectedProviderId: string | null;
  selectedModelId: string | null;
  modelLabelFallback: string;
  onModelChange: (providerId: string, modelId: string) => void;
  text: TextFn;
}) {
  if (providers.length === 0) {
    return (
      <div className="rounded-md border border-amber-200 bg-amber-50 p-1.5 text-xs text-amber-800">
        {text("模型设置不可用", "Model settings unavailable")} · {modelLabelFallback}
      </div>
    );
  }

  return (
    <div
      role="listbox"
      aria-label={text("切换模型", "Switch model")}
      className="flex max-h-48 flex-col gap-1 overflow-y-auto"
    >
      {providers.map((option) => {
        const selected =
          option.providerId === selectedProviderId && option.modelId === selectedModelId;
        return (
          <button
            key={`${option.providerId}:${option.modelId}`}
            type="button"
            role="option"
            aria-selected={selected}
            onClick={() => onModelChange(option.providerId, option.modelId)}
            className={cn(
              "flex w-full items-start gap-2.5 rounded-xl px-2.5 py-2.5 text-left text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400",
              selected
                ? "bg-slate-900 font-medium text-white"
                : "text-slate-700 hover:bg-slate-50",
            )}
          >
            <span
              className={cn(
                "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg",
                selected ? "bg-white/10 text-white" : "bg-slate-100 text-slate-600",
              )}
            >
              <Brain className="h-4 w-4" />
            </span>
            <TeamModelOptionText option={option} selected={selected} />
          </button>
        );
      })}
    </div>
  );
}

function TeamModelOptionText({
  option,
  selected,
}: {
  option: ModelOption;
  selected: boolean;
}) {
  const display = modelOptionDisplay(option);

  return (
    <span className="min-w-0 flex-1">
      <span className="block truncate text-sm font-semibold">{display.title}</span>
      <span className={cn("block truncate text-[11px] leading-4", selected ? "text-slate-300" : "text-slate-500")}>
        {display.subtitle}
      </span>
    </span>
  );
}

function TeamToolToggleRow({
  icon,
  label,
  checked,
  onChange,
}: {
  icon: JSX.Element;
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex h-7 items-center gap-2 rounded-md px-1.5 transition-colors hover:bg-slate-50">
      <span className="flex h-4 w-4 shrink-0 items-center justify-center text-slate-500">{icon}</span>
      <span className="min-w-0 flex-1 truncate">{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative inline-flex h-5 w-8 shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400",
          checked ? "bg-slate-900" : "bg-slate-200",
        )}
      >
        <span
          className={cn(
            "h-4 w-4 rounded-full bg-white shadow transition-transform",
            checked ? "translate-x-[14px]" : "translate-x-[2px]",
          )}
        />
      </button>
    </div>
  );
}

function TeamToolActionRow({
  icon,
  label,
  trailing = null,
  onClick,
}: {
  icon: JSX.Element;
  label: ReactNode;
  trailing?: JSX.Element | null;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex min-h-7 w-full items-center gap-2 rounded-md px-1.5 text-left transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
    >
      <span className="flex h-4 w-4 shrink-0 items-center justify-center text-slate-500">{icon}</span>
      <span className="min-w-0 flex-1 truncate leading-4">{label}</span>
      {trailing ? (
        <span className="ml-auto flex h-4 w-4 shrink-0 items-center justify-center text-slate-400">
          {trailing}
        </span>
      ) : null}
    </button>
  );
}

function TeamComposerMetadataRow({ usage, text }: { usage: UsageSummary; text: TextFn }) {
  const items = [
    [text("输入", "In"), formatMetricNumber(usage.inputTokens)],
    [text("输出", "Out"), formatMetricNumber(usage.outputTokens)],
    [text("花费", "Cost"), usage.costUsd],
    [text("耗时", "Time"), formatDuration(usage.durationMs)],
    [text("模型", "Models"), formatMetricNumber(usage.modelCalls)],
    [text("工具", "Tools"), formatMetricNumber(usage.toolCalls)],
  ];

  return (
    <div
      className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] leading-4 text-slate-500"
      aria-label={text("运行元数据", "Run metadata")}
    >
      {items.map(([label, value]) => (
        <span key={label} className="inline-flex min-w-0 items-baseline gap-1">
          <span>{label}</span>
          <span className="font-mono text-slate-700">{value}</span>
        </span>
      ))}
    </div>
  );
}

function TeamMessageRunLinks({
  runId,
  runStatus,
  runCreatedAt,
}: {
  runId: string;
  runStatus?: string;
  runCreatedAt?: string;
}) {
  const { text } = useI18n();
  const createdAt = runCreatedAt ? new Date(runCreatedAt) : null;
  const createdLabel =
    createdAt && Number.isFinite(createdAt.getTime())
      ? createdAt.toLocaleString()
      : null;
  return (
    <div className="ml-11 flex flex-wrap items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] text-slate-600 shadow-sm">
      <GitBranch aria-hidden="true" className="h-3.5 w-3.5 text-slate-500" />
      <span className="font-mono text-slate-800">运行 {runId.slice(0, 8)}</span>
      {runStatus ? <Badge tone="info">{statusLabel(runStatus)}</Badge> : null}
      {createdLabel ? <span className="hidden text-slate-400 sm:inline">{createdLabel}</span> : null}
      <div className="ml-auto flex items-center gap-1">
        <Link
          to={`/runs/${runId}`}
          aria-label={text("查看运行详情", "Open run detail")}
          className="inline-flex h-7 items-center gap-1 rounded-md px-2 font-medium text-slate-700 hover:bg-slate-100"
        >
          <ExternalLink aria-hidden="true" className="h-3 w-3" />
          <span>{text("运行", "Run")}</span>
        </Link>
        <Link
          to={`/evals?run=${encodeURIComponent(runId)}`}
          aria-label={text("打开评测中心", "Open Eval Harness")}
          className="inline-flex h-7 items-center gap-1 rounded-md px-2 font-medium text-slate-700 hover:bg-slate-100"
        >
          <FlaskConical aria-hidden="true" className="h-3 w-3" />
          <span>{text("评测", "Eval")}</span>
        </Link>
      </div>
    </div>
  );
}

function findLastAssistantNodeId(entries: TeamConversationEntry[]) {
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const node = entries[index].node;
    if (node.role === "assistant") return node.id;
  }
  return null;
}

function findLastAssistantEntry(entries: TeamConversationEntry[]) {
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const entry = entries[index];
    if (entry.node.role === "assistant") return entry;
  }
  return null;
}

function previousUserContent(entries: TeamConversationEntry[], nodeId: string) {
  const index = entries.findIndex((entry) => entry.node.id === nodeId);
  if (index < 0) return null;
  for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
    const entry = entries[cursor];
    if (entry.node.role === "user" && entry.node.content.trim()) {
      return { content: entry.node.content, target: entry.target };
    }
  }
  return null;
}

function previousUserEntry(entries: TeamConversationEntry[], nodeId: string) {
  const index = entries.findIndex((entry) => entry.node.id === nodeId);
  if (index < 0) return null;
  for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
    const entry = entries[cursor];
    if (entry.node.role === "user" && entry.node.content.trim()) {
      return entry;
    }
  }
  return null;
}

function applyTeamBranchGroups(
  entries: TeamConversationEntry[],
  groups: Record<string, TeamBranchGroup>,
) {
  const visibleIds = new Set(entries.map((entry) => entry.node.id));
  const duplicateAnchorUserIds = new Set<string>();
  for (const group of Object.values(groups)) {
    if (group.branchNodeIds.length <= 1) continue;
    for (const entry of entries) {
      if (
        entry.node.role === "user" &&
        entry.node.id !== group.anchorUserId &&
        entry.node.content === group.anchorContent
      ) {
        duplicateAnchorUserIds.add(entry.node.id);
      }
    }
  }
  const hiddenUserNodeIds = new Set(
    Object.values(groups).flatMap((group) => group.hiddenUserNodeIds),
  );
  const activeBranchIds = new Set(
    Object.values(groups)
      .filter((group) => visibleIds.has(group.activeNodeId))
      .map((group) => group.activeNodeId),
  );
  return entries.filter((entry) => {
    if (duplicateAnchorUserIds.has(entry.node.id)) return false;
    if (hiddenUserNodeIds.has(entry.node.id)) return false;
    if (entry.node.role !== "assistant") return true;
    const inBranchGroup = Object.values(groups).some((group) => group.branchNodeIds.includes(entry.node.id));
    return !inBranchGroup || activeBranchIds.has(entry.node.id);
  });
}

function isMcpTool(tool: ToolMetadata) {
  return tool.source === "mcp" || tool.mcp_server !== null || tool.mcp_method !== null;
}

function formatMcpCapability(tool: ToolMetadata) {
  if (tool.mcp_server !== null && tool.mcp_method !== null) {
    return `${tool.mcp_server}.${tool.mcp_method}`;
  }
  if (tool.mcp_server !== null) return tool.mcp_server;
  if (tool.mcp_method !== null) return tool.mcp_method;
  return tool.description || tool.category;
}

function fileToComposerAttachment(file: File): ComposerAttachment {
  const isImage = file.type.startsWith("image/");
  return {
    id: makeAttachmentId(file),
    name: file.name,
    mimeType: file.type,
    previewUrl: isImage ? URL.createObjectURL(file) : null,
    sizeBytes: file.size,
    kind: isImage ? "image" : "file",
    contentText: null,
    contentStatus: isReadableTextFile(file) && file.size <= MAX_TEAM_ATTACHMENT_TEXT_BYTES ? "ready" : "unsupported",
    truncated: file.size > MAX_TEAM_ATTACHMENT_TEXT_BYTES,
  };
}

function isReadableTextFile(file: File) {
  if (file.type.startsWith("text/")) return true;
  const mime = file.type.toLowerCase();
  if (
    [
      "application/json",
      "application/xml",
      "application/yaml",
      "application/x-yaml",
      "application/javascript",
      "application/typescript",
    ].includes(mime)
  ) {
    return true;
  }
  return /\.(txt|md|markdown|csv|tsv|json|jsonl|yaml|yml|xml|log|ini|env|py|js|ts|tsx|jsx|css|html)$/i.test(
    file.name,
  );
}

function attachmentKey(attachment: ComposerAttachment) {
  return `${attachment.name}:${attachment.sizeBytes}:${attachment.mimeType}`;
}

function makeAttachmentId(file: File) {
  const random =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2);
  return `${file.name}:${file.size}:${file.lastModified}:${random}`;
}

function formatMetricNumber(value: number) {
  return new Intl.NumberFormat("en", { notation: "compact" }).format(value);
}

function formatTokenCount(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "0";
  if (value >= 1_000_000) return `${Number.parseFloat((value / 1_000_000).toFixed(1))}m`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}k`;
  return String(Math.round(value));
}

function formatDuration(durationMs: number) {
  if (!Number.isFinite(durationMs) || durationMs <= 0) return "0ms";
  if (durationMs < 1000) return `${Math.round(durationMs)}ms`;
  return `${(durationMs / 1000).toFixed(1)}s`;
}
