/**
 * Group-by-role aggregation (v4 / Req 7.3, Property P24).
 *
 * Renders the current `Active_Path` into a flat list of groups where each
 * group contains a contiguous run of nodes sharing the same `role`. Error
 * nodes (`state === "error"`) always occupy their own singleton group so
 * the bubble keeps a distinct visual boundary (Req 7.3.3).
 *
 * Pure: no DOM, no store access, no imports beyond types.
 *
 * Invariants (verified by P24):
 *   - `groupByRole(path).flatMap(g => g.nodes)` === `path` (order-preserving).
 *   - For every group `g` and every node `n ∈ g.nodes`, `n.role === g.role`.
 *   - Any `n` with `state === "error"` is alone in its group.
 *   - `groupByRole([])` returns `[]`.
 */

import type {
  ConversationNode,
  ConversationRole,
} from "../../../stores/workspaceStore";

export type ConversationNodeGroup = {
  role: ConversationRole;
  nodes: ConversationNode[];
};

export function groupByRole(
  activePath: ConversationNode[],
): ConversationNodeGroup[] {
  const groups: ConversationNodeGroup[] = [];
  let current: ConversationNodeGroup | null = null;

  for (const node of activePath) {
    const isError = node.state === "error";
    const lastNode =
      current !== null && current.nodes.length > 0
        ? current.nodes[current.nodes.length - 1]
        : null;
    const lastIsError = lastNode !== null && lastNode.state === "error";
    const canExtend =
      current !== null &&
      current.role === node.role &&
      !isError &&
      !lastIsError;

    if (canExtend && current !== null) {
      current.nodes.push(node);
    } else {
      current = { role: node.role, nodes: [node] };
      groups.push(current);
    }

    if (isError) {
      // Force the next iteration to open a fresh group.
      current = null;
    }
  }

  return groups;
}
