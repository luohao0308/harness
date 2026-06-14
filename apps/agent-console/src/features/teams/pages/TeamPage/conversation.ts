import type { ComposerAttachment } from "../../../agents/components/ChatComposer";
import {
  contextCompressionBranchKey,
  isCompressionSummaryUsable,
  type ContextCompressionSummary,
  uncoveredContextPath,
} from "../../../agents/lib/contextCompression";
import { estimateTextTokens } from "../../../agents/lib/contextTruncation";
import { normalizeWorkspaceMode, type WorkspaceMode } from "../../../agents/lib/types";
import type { UsageSummary } from "../../../agents/components/InspectorDrawer";
import type { ModelOption } from "../../../agents/components/ModelPicker";
import type {
  AgentMessage,
  ModelSettings,
  Team,
  TeamAgent,
  TeamMailboxMessage,
  ToolMetadata,
  WorkspaceContextCompressionResponse,
} from "../../../tasks/api";
import type { ConversationArtifact } from "../../../../stores/workspaceStore";

import {
  agentMessageFromMailbox,
  agentMessageNodeId,
  agentSessionMessages,
  agentWakeInProgress,
  hasCompletedWakeTurn,
  isRecord,
} from "./teamState";
import type {
  PendingSend,
  SettledWakeCutoffs,
  StreamingWake,
  TeamBranchGroup,
  TeamConversationEntry,
  TeamMessageEntry,
  TextFn,
} from "./types";
import { MAX_TEAM_ATTACHMENT_TEXT_BYTES } from "./types";

export function agentMessages(agent: TeamAgent, messages: TeamMailboxMessage[]) {
  return messages.filter(
    (message) => message.to_agent_slot_id === agent.slot_id || message.from_agent_slot_id === agent.slot_id,
  );
}

export function displayMessages(agent: TeamAgent, mailboxMessages: TeamMailboxMessage[]) {
  const messages = agentSessionMessages(agent);
  if (messages.length > 0) {
    return messages.map((message): TeamMessageEntry => ({ kind: "session", message }));
  }
  return mailboxMessages.map((message): TeamMessageEntry => ({ kind: "mailbox", message }));
}

export function teamConversationEntries(team: Team, agent: TeamAgent, mailboxMessages: TeamMailboxMessage[]) {
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

export function streamingEntry(
  team: Team,
  agent: TeamAgent,
  wake?: StreamingWake,
  pendingSend?: PendingSend,
): TeamConversationEntry {
  return {
    node: {
      id: pendingSend?.branchAssistantId ?? wake?.branchAssistantId ?? `team-${team.id}-${agent.slot_id}-streaming`,
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

export function teamComposerPlaceholder(mode: WorkspaceMode, text: TextFn) {
  switch (mode) {
    case "markdown_plan":
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

export function teamPendingSendKey(
  slotId: string,
  target: string,
  mode: WorkspaceMode,
  content: string,
  files: string[],
) {
  return `${slotId}:${target}:${mode}:${content}:${files.join(",")}`;
}

export function teamConversationEntriesWithPending(
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
  const pendingSend =
    pendingSends.find((send) => send.recipientSlotIds.includes(agent.slot_id) && send.branchAssistantId) ??
    pendingSends.find((send) => send.recipientSlotIds.includes(agent.slot_id));
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
  const pending = streamingEntry(team, agent, streamingWake, pendingSend);
  const parent =
    pendingSend?.anchorUserId || streamingWake?.anchorUserId
      ? entries.find((entry) => entry.node.id === (pendingSend?.anchorUserId ?? streamingWake?.anchorUserId))
      : lastEntry;
  pending.node.parent_id = parent?.node.id ?? `team-${team.id}-${agent.slot_id}-root`;
  if (parent) {
    parent.node.children_ids = [...new Set([...parent.node.children_ids, pending.node.id])];
  }
  return [...entries, pending];
}

export function recipientSlotIdsForTarget(team: Team, target: string, sender = "user") {
  if (target === "leader") return [team.leader_slot_id];
  if (target === "team" || target === "*") {
    return team.agents
      .filter((agent) => agent.status !== "completed" && agent.slot_id !== sender)
      .map((agent) => agent.slot_id);
  }
  return team.agents.some((agent) => agent.slot_id === target) ? [target] : [];
}

export function readRecord(source: Record<string, unknown> | null | undefined, key: string): Record<string, unknown> | null {
  const value = source?.[key];
  return isRecord(value) ? value : null;
}

export function readString(source: Record<string, unknown> | null | undefined, key: string): string | null {
  const value = source?.[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function readWorkspaceMode(source: Record<string, unknown> | null | undefined): WorkspaceMode {
  return normalizeWorkspaceMode(readString(source, "workspace_mode"));
}

export function readNumber(source: Record<string, unknown> | null | undefined, key: string): number | undefined {
  const value = source?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

export function targetForTeamMessage(agent: TeamAgent, metadata: Record<string, unknown>) {
  const target = readString(metadata, "to_agent_slot_id");
  if (target) return target;
  return defaultComposerTarget(agent);
}

export function teamToolCalls(metadata: Record<string, unknown>): Array<Record<string, unknown>> {
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

export function teamArtifacts(metadata: Record<string, unknown>, runId: string | null): ConversationArtifact[] {
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

export function artifactType(value: string | null): ConversationArtifact["artifact_type"] {
  if (value === "code" || value === "json" || value === "diff" || value === "chart" || value === "text") {
    return value;
  }
  return "text";
}

export function activeAgent(team: Team | undefined, activeSlotId: string, fallback = "leader") {
  return team?.agents.find((agent) => agent.slot_id === activeSlotId) ?? team?.agents[0] ?? team?.agents.find((agent) => agent.slot_id === fallback) ?? null;
}

export function orderedTeamAgents(agents: TeamAgent[], orderedSlotIds: string[]) {
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

export function summarizeTeamUsage(entries: TeamConversationEntry[]): UsageSummary {
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

export function teamContextTokenEstimate(entries: TeamConversationEntry[], draft: string) {
  return entries.reduce((sum, entry) => {
    const metered =
      (entry.node.metadata.input_tokens ?? 0) + (entry.node.metadata.output_tokens ?? 0);
    return sum + Math.max(metered, estimateTextTokens(entry.node.content));
  }, estimateTextTokens(draft));
}

export function teamCompressionKey(team: Team, agent: TeamAgent, entries: TeamConversationEntry[]) {
  const activeLeafId = entries[entries.length - 1]?.node.id ?? `team-${team.id}-${agent.slot_id}-root`;
  return contextCompressionBranchKey(`team:${team.id}:${agent.slot_id}`, activeLeafId);
}

export function teamEffectiveContextTokenEstimate(input: {
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

export function workspaceCompressionSummary(
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

export function deriveTeamModelOptions(settings: ModelSettings | undefined): ModelOption[] {
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

export function defaultComposerTarget(agent: TeamAgent) {
  return agent.role === "leader" ? "leader" : agent.slot_id;
}

export function findLastAssistantNodeId(entries: TeamConversationEntry[]) {
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const node = entries[index].node;
    if (node.role === "assistant") return node.id;
  }
  return null;
}

export function findLastAssistantEntry(entries: TeamConversationEntry[]) {
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const entry = entries[index];
    if (entry.node.role === "assistant") return entry;
  }
  return null;
}

export function previousUserContent(entries: TeamConversationEntry[], nodeId: string) {
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

export function previousUserEntry(entries: TeamConversationEntry[], nodeId: string) {
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

export function applyTeamBranchGroups(
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

export function isMcpTool(tool: ToolMetadata) {
  return tool.source === "mcp" || tool.mcp_server !== null || tool.mcp_method !== null;
}

export function formatMcpCapability(tool: ToolMetadata) {
  if (tool.mcp_server !== null && tool.mcp_method !== null) {
    return `${tool.mcp_server}.${tool.mcp_method}`;
  }
  if (tool.mcp_server !== null) return tool.mcp_server;
  if (tool.mcp_method !== null) return tool.mcp_method;
  return tool.description || tool.category;
}

export function fileToComposerAttachment(file: File): ComposerAttachment {
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

export function isReadableTextFile(file: File) {
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

export function attachmentKey(attachment: ComposerAttachment) {
  return `${attachment.name}:${attachment.sizeBytes}:${attachment.mimeType}`;
}

export function makeAttachmentId(file: File) {
  const random =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2);
  return `${file.name}:${file.size}:${file.lastModified}:${random}`;
}

export function formatMetricNumber(value: number) {
  return new Intl.NumberFormat("en", { notation: "compact" }).format(value);
}

export function formatTokenCount(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "0";
  if (value >= 1_000_000) return `${Number.parseFloat((value / 1_000_000).toFixed(1))}m`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}k`;
  return String(Math.round(value));
}

export function formatDuration(durationMs: number) {
  if (!Number.isFinite(durationMs) || durationMs <= 0) return "0ms";
  if (durationMs < 1000) return `${Math.round(durationMs)}ms`;
  return `${(durationMs / 1000).toFixed(1)}s`;
}
