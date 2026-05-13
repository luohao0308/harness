import { describe, expect, it } from "vitest";

import type { ConversationNode } from "../../../stores/workspaceStore";
import { planApprovalGate } from "../lib/planApprovalGate";

function assistant(mode: "chat" | "markdown_plan" | "plan"): ConversationNode {
  return {
    id: `assistant-${mode}`,
    parent_id: "user-1",
    children_ids: [],
    role: "assistant",
    content: "plan content",
    state: "done",
    metadata: { workspace_mode: mode },
    tool_calls: [],
    artifacts: [],
    created_at: "2026-05-14T00:00:00.000Z",
  };
}

describe("planApprovalGate", () => {
  it("shows approval for markdown planning output", () => {
    const result = planApprovalGate({
      activePath: [assistant("markdown_plan")],
      activeStreamNodeId: null,
      dismissedPlanNodeIds: [],
    });

    expect(result.visible).toBe(true);
  });

  it("does not re-open approval for Plan-Act run output", () => {
    const result = planApprovalGate({
      activePath: [assistant("plan")],
      activeStreamNodeId: null,
      dismissedPlanNodeIds: [],
    });

    expect(result.visible).toBe(false);
  });
});
