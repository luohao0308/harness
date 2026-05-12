/**
 * Pure derivations used by `AgentWorkspacePage` to keep the page shell
 * ≤ 120 lines (Task 15). None of these helpers reach into React or
 * `useWorkspaceStore`; they take primitive snapshots so they are trivial
 * to memoise on the caller side.
 */

import type {
  AgentDefinition,
  AgentRunWorkspace,
  ModelSettings,
} from "../../tasks/api";
import type { ConversationNode } from "../../../stores/workspaceStore";
import type { UsageSummary } from "../components/InspectorDrawer";

/**
 * Build the ordered `Active_Path` from store primitives. Matches the
 * behaviour of `useWorkspaceStore.activePath()` but in a form that can be
 * memoised against the store's scalar selectors (the method returns a fresh
 * array on every call and defeats `useMemo`).
 */
export function buildActivePath(
  nodesById: Record<string, ConversationNode>,
  activeLeafId: string,
  rootNodeId: string,
): ConversationNode[] {
  const path: ConversationNode[] = [];
  let current: string | null = activeLeafId;
  while (current) {
    const node: ConversationNode | undefined = nodesById[current];
    if (!node) break;
    if (node.id !== rootNodeId) path.push(node);
    current = node.parent_id;
  }
  return path.reverse();
}

/**
 * Format the model label shown in compact Workspace chips.
 * Falls back to the global model-settings defaults when the agent was
 * defined with the sentinel `model_provider === "default"` (Req 8.5).
 */
export function deriveModelLabel(
  agent: AgentDefinition | undefined,
  settings: ModelSettings | undefined,
): string {
  if (agent && agent.model_provider !== "default") {
    return agent.model_name;
  }
  const model = settings?.default_model ?? agent?.model_name ?? "default";
  return model;
}

/**
 * Summarise token / cost / duration for the compact composer metadata row.
 * `modelCalls` and `toolCalls` come from the lazy workspace query; they are 0
 * until run workspace data is loaded (Req 10.5).
 */
export function summarizeUsage(
  path: ConversationNode[],
  workspace: AgentRunWorkspace | undefined,
): UsageSummary {
  let inputTokens = 0;
  let outputTokens = 0;
  let durationMs = 0;
  let costUsd: string = "-";
  for (const node of path) {
    inputTokens += node.metadata.input_tokens ?? 0;
    outputTokens += node.metadata.output_tokens ?? 0;
    durationMs = Math.max(durationMs, node.metadata.duration_ms ?? 0);
    const cost = node.metadata.cost_usd;
    if (typeof cost === "string" && cost.length > 0) costUsd = cost;
  }
  return {
    inputTokens,
    outputTokens,
    costUsd,
    durationMs,
    modelCalls: workspace?.model_calls.length ?? 0,
    toolCalls: workspace?.tool_calls.length ?? 0,
  };
}
