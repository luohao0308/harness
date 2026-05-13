/**
 * Context truncation logic for the chat payload builder (Phase 4 / Req 14).
 *
 * Before sending messages to the API, this module trims the conversation to
 * fit within the configured `contextMaxTokens` budget. The store data is
 * never mutated — truncation applies only to the outgoing payload.
 *
 * Preservation rules (in priority order):
 *   1. System messages — always included.
 *   2. Pinned messages — always included.
 *   3. Most recent user/assistant pair — always included.
 *   4. Remaining messages — removed from oldest end until within budget.
 *
 * Token estimation: `content.length / 4` (rough char-to-token ratio).
 *
 * Edge case: if pinned messages alone exceed the budget, all pinned messages
 * are still included and `pinnedOverflow` is set to `true` so the UI can
 * surface a warning.
 */

import type { ConversationNode } from "../../../stores/workspaceStore";

export interface TruncationResult {
  /** Messages to include in the API payload. */
  messages: ConversationNode[];
  /** Number of messages excluded from the original set. */
  excludedCount: number;
  /** Whether pinned messages alone exceed the token budget. */
  pinnedOverflow: boolean;
}

/**
 * Estimate token count for a single node using `content.length / 4`.
 */
export function estimateTokens(node: ConversationNode): number {
  return Math.ceil(node.content.length / 4);
}

/**
 * Truncate messages for the API payload while preserving system messages,
 * pinned messages, and the most recent user/assistant pair.
 *
 * @param nodes - The full active path (ordered oldest → newest).
 * @param pinnedIds - Node IDs that are pinned by the user.
 * @param maxTokens - The configured context token budget.
 */
export function truncateForContext(
  nodes: ConversationNode[],
  pinnedIds: string[],
  maxTokens: number,
): TruncationResult {
  if (nodes.length === 0) {
    return { messages: [], excludedCount: 0, pinnedOverflow: false };
  }

  // Compute total tokens — if within budget, no truncation needed.
  const totalTokens = nodes.reduce((sum, n) => sum + estimateTokens(n), 0);
  if (totalTokens <= maxTokens) {
    return { messages: [...nodes], excludedCount: 0, pinnedOverflow: false };
  }

  const pinnedSet = new Set(pinnedIds);

  // Identify the most recent user/assistant pair (from the end).
  const recentPairIds = new Set<string>();
  let foundAssistant = false;
  let foundUser = false;
  for (let i = nodes.length - 1; i >= 0; i--) {
    const node = nodes[i];
    if (!foundAssistant && node.role === "assistant") {
      recentPairIds.add(node.id);
      foundAssistant = true;
    } else if (!foundUser && node.role === "user") {
      recentPairIds.add(node.id);
      foundUser = true;
    }
    if (foundAssistant && foundUser) break;
  }

  // Classify each node as "protected" or "removable".
  // Protected: system messages, pinned messages, most recent user/assistant pair.
  const isProtected = (node: ConversationNode): boolean => {
    if (node.role === "system") return true;
    if (pinnedSet.has(node.id)) return true;
    if (recentPairIds.has(node.id)) return true;
    return false;
  };

  // Calculate tokens for protected messages.
  let protectedTokens = 0;
  for (const node of nodes) {
    if (isProtected(node)) {
      protectedTokens += estimateTokens(node);
    }
  }

  // Check pinned overflow: if pinned + system + recent pair alone exceed budget.
  let pinnedOverflow = false;
  if (protectedTokens > maxTokens) {
    // Even protected messages exceed the budget. Check if pinned alone are the cause.
    let pinnedTokens = 0;
    for (const node of nodes) {
      if (pinnedSet.has(node.id)) {
        pinnedTokens += estimateTokens(node);
      }
    }
    if (pinnedTokens > maxTokens) {
      pinnedOverflow = true;
    }
    // Include all protected messages regardless — the API call proceeds.
    const result = nodes.filter((n) => isProtected(n));
    return {
      messages: result,
      excludedCount: nodes.length - result.length,
      pinnedOverflow,
    };
  }

  // We have room for some removable messages. Remove from oldest end until
  // within budget. Iterate from oldest (index 0) and skip removable messages
  // until we've freed enough tokens.
  let remainingBudget = maxTokens - protectedTokens;
  const removableNodes: Array<{ node: ConversationNode; tokens: number; index: number }> = [];

  for (let i = 0; i < nodes.length; i++) {
    const node = nodes[i];
    if (!isProtected(node)) {
      removableNodes.push({ node, tokens: estimateTokens(node), index: i });
    }
  }

  // Total removable tokens.
  const totalRemovableTokens = removableNodes.reduce((sum, r) => sum + r.tokens, 0);

  // If all removable messages fit within the remaining budget, include everything.
  if (totalRemovableTokens <= remainingBudget) {
    return { messages: [...nodes], excludedCount: 0, pinnedOverflow: false };
  }

  // Remove from oldest (start of removableNodes) until the remaining fit.
  const excludedIndices = new Set<number>();
  let tokensToRemove = totalRemovableTokens - remainingBudget;

  for (const removable of removableNodes) {
    if (tokensToRemove <= 0) break;
    excludedIndices.add(removable.index);
    tokensToRemove -= removable.tokens;
  }

  const result = nodes.filter((_, i) => !excludedIndices.has(i));
  return {
    messages: result,
    excludedCount: excludedIndices.size,
    pinnedOverflow: false,
  };
}
