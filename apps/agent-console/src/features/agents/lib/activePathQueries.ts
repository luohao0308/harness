import type { ConversationNode } from "../../../stores/workspaceStore";

/**
 * Query helpers over Active_Path. All pure functions. Property 7.
 * Related Requirements: 4.5, 4.6, 5.2, 5.3, 5.4, 5.5, 7.5.
 */

/**
 * Returns the user node with the greatest index < index(t) in `activePath`
 * such that node.role === "user"; or undefined.
 * Used by retry (Req 4.6) and resume (Req 5.4).
 *
 * Semantics:
 *   - If `targetNodeId` is not present in `activePath`, return undefined.
 *   - If `targetNodeId` is the first element, return undefined.
 *   - Otherwise scan indices [targetIndex - 1 .. 0] for the first node whose
 *     role is "user"; return undefined if none exists.
 */
export function findPrevUser(
  activePath: ConversationNode[],
  targetNodeId: string,
): ConversationNode | undefined {
  const targetIndex = activePath.findIndex((node) => node.id === targetNodeId);
  if (targetIndex <= 0) return undefined;
  for (let i = targetIndex - 1; i >= 0; i -= 1) {
    const candidate = activePath[i];
    if (candidate.role === "user") return candidate;
  }
  return undefined;
}

/**
 * True iff there exists at least one node n ∈ activePath with
 *   n.role === "assistant" &&
 *   n.state === "paused" &&
 *   typeof n.run_id === "string" &&
 *   n.run_id.length > 0.
 * Req 5.3, 5.5.
 */
export function canResume(activePath: ConversationNode[]): boolean {
  return activePath.some(
    (node) =>
      node.role === "assistant" &&
      node.state === "paused" &&
      typeof node.run_id === "string" &&
      node.run_id.length > 0,
  );
}

/**
 * True iff node.role === "assistant" && node.state === "done" &&
 *         typeof node.run_id === "string" && node.run_id.length > 0.
 * Req 7.5 (RunSummary card gating).
 */
export function shouldShowRunSummary(node: ConversationNode): boolean {
  return (
    node.role === "assistant" &&
    node.state === "done" &&
    typeof node.run_id === "string" &&
    node.run_id.length > 0
  );
}
