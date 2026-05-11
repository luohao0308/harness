/**
 * Pure predicate governing `PlanApprovalPanel` visibility (Req 3.1 / 3.6 /
 * 3.7 and Property P4).
 *
 * All 7 preconditions must hold for `{ visible: true, planNode: tail }`; if
 * any fails the gate returns `{ visible: false, planNode: null }`. TOTAL:
 * any shape of input (empty array, missing metadata, missing role) is
 * handled without throwing.
 */

import type { ConversationNode } from "../../../stores/workspaceStore";

export type PlanApprovalGateInput = {
  activePath: ConversationNode[];
  activeStreamNodeId: string | null;
  dismissedPlanNodeIds: ReadonlyArray<string>;
};

export type PlanApprovalGateResult = {
  visible: boolean;
  planNode: ConversationNode | null;
};

const HIDDEN: PlanApprovalGateResult = { visible: false, planNode: null };

export function planApprovalGate(
  input: PlanApprovalGateInput,
): PlanApprovalGateResult {
  const { activePath, activeStreamNodeId, dismissedPlanNodeIds } = input;

  // Precondition 1: non-empty active path.
  if (!Array.isArray(activePath) || activePath.length === 0) {
    return HIDDEN;
  }

  // Precondition 2: tail exists.
  const tail = activePath[activePath.length - 1];
  if (!tail) {
    return HIDDEN;
  }

  // Precondition 3: assistant role.
  if (tail.role !== "assistant") {
    return HIDDEN;
  }

  // Precondition 4: done state.
  if (tail.state !== "done") {
    return HIDDEN;
  }

  // Precondition 5: workspace_mode ∈ {plan, markdown_plan}.
  const mode = tail.metadata?.workspace_mode;
  if (mode !== "plan" && mode !== "markdown_plan") {
    return HIDDEN;
  }

  // Precondition 6: no active stream.
  if (activeStreamNodeId !== null) {
    return HIDDEN;
  }

  // Precondition 7: tail not dismissed.
  if (
    Array.isArray(dismissedPlanNodeIds) &&
    dismissedPlanNodeIds.includes(tail.id)
  ) {
    return HIDDEN;
  }

  return { visible: true, planNode: tail };
}
