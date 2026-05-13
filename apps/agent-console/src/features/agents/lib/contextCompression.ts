import type { AgentChatStreamMessage } from "../../tasks/api";
import type { ConversationNode } from "../../../stores/workspaceStore";

export const SUMMARY_SCHEMA_VERSION = "workspace-context-summary-v1";
export const COMPRESSION_PROMPT_VERSION = "workspace-context-compression-v1";

export type ContextCompressionStatus =
  | "idle"
  | "pending"
  | "ready"
  | "stale"
  | "error";

export type ContextCompressionCacheStatus =
  | "accepted"
  | "recomputed"
  | "stale_rejected"
  | "error";

export type ContextCompressionSummary = {
  branchKey: string;
  summary: string;
  coverageNodeIds: string[];
  coveragePathHash: string;
  lastCoveredNodeId: string | null;
  summarySchemaVersion: string;
  compressionPromptVersion: string;
  compressorProvider: string;
  compressorModel: string;
  estimatedOriginalTokens: number;
  estimatedSummaryTokens: number;
  estimatedUncoveredTokens: number;
  status: ContextCompressionStatus;
  cacheStatus?: ContextCompressionCacheStatus;
  error?: string | null;
  createdAt: string;
  updatedAt: string;
};

export function contextCompressionBranchKey(
  conversationId: string,
  activeLeafId: string,
): string {
  return `${conversationId}:${activeLeafId}`;
}

export function normalizeModelId(value: string | null | undefined): string {
  return (value ?? "default").trim().toLowerCase();
}

export function isEligibleContextNode(node: ConversationNode): boolean {
  return (
    (node.role === "user" || node.role === "assistant" || node.role === "system") &&
    node.content.trim().length > 0
  );
}

export function serializeContextNode(node: ConversationNode): AgentChatStreamMessage {
  return {
    id: node.id,
    parent_id: node.parent_id,
    children_ids: node.children_ids,
    role: node.role,
    content: node.content,
    state: node.state,
    run_id: node.run_id,
    metadata: node.metadata,
    tool_calls: node.tool_calls,
    artifacts: node.artifacts,
    created_at: node.created_at,
  };
}

export function isCompressionSummaryUsable(input: {
  summary: ContextCompressionSummary | null | undefined;
  branchKey: string;
  activePath: ConversationNode[];
  pinnedNodeIds: string[];
  providerId: string | null | undefined;
  modelId: string | null | undefined;
}): boolean {
  const { summary } = input;
  if (summary === null || summary === undefined) return false;
  if (summary.status !== "ready") return false;
  if (summary.summary.trim().length === 0) return false;
  if (summary.branchKey !== input.branchKey) {
    const activeIds = new Set(input.activePath.map((node) => node.id));
    if (summary.lastCoveredNodeId === null || !activeIds.has(summary.lastCoveredNodeId)) {
      return false;
    }
  }
  if (summary.summarySchemaVersion !== SUMMARY_SCHEMA_VERSION) return false;
  if (summary.compressionPromptVersion !== COMPRESSION_PROMPT_VERSION) return false;
  if (summary.compressorProvider !== normalizeModelId(input.providerId)) return false;
  if (summary.compressorModel !== normalizeModelId(input.modelId)) return false;

  const activeIds = new Set(input.activePath.map((node) => node.id));
  const pinned = new Set(input.pinnedNodeIds);
  for (const nodeId of summary.coverageNodeIds) {
    if (!activeIds.has(nodeId)) return false;
    if (pinned.has(nodeId)) return false;
  }
  return true;
}

export function selectBestCompressionSummary(input: {
  summaries: Record<string, ContextCompressionSummary>;
  branchKey: string;
  activePath: ConversationNode[];
  pinnedNodeIds: string[];
  providerId: string | null | undefined;
  modelId: string | null | undefined;
}): ContextCompressionSummary | null {
  const exact = input.summaries[input.branchKey];
  if (
    isCompressionSummaryUsable({
      summary: exact,
      branchKey: input.branchKey,
      activePath: input.activePath,
      pinnedNodeIds: input.pinnedNodeIds,
      providerId: input.providerId,
      modelId: input.modelId,
    })
  ) {
    return exact;
  }

  const usable = Object.values(input.summaries).filter((summary) =>
    isCompressionSummaryUsable({
      summary,
      branchKey: input.branchKey,
      activePath: input.activePath,
      pinnedNodeIds: input.pinnedNodeIds,
      providerId: input.providerId,
      modelId: input.modelId,
    }),
  );
  usable.sort((a, b) => {
    if (b.coverageNodeIds.length !== a.coverageNodeIds.length) {
      return b.coverageNodeIds.length - a.coverageNodeIds.length;
    }
    return Date.parse(b.updatedAt) - Date.parse(a.updatedAt);
  });
  return usable[0] ?? null;
}

export function uncoveredContextPath(input: {
  activePath: ConversationNode[];
  pinnedNodeIds: string[];
  summary: ContextCompressionSummary | null | undefined;
}): ConversationNode[] {
  const coverage = new Set(input.summary?.coverageNodeIds ?? []);
  const pinned = new Set(input.pinnedNodeIds);
  return input.activePath.filter((node) => pinned.has(node.id) || !coverage.has(node.id));
}
