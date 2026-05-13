import { describe, expect, it } from "vitest";

import type { ConversationNode } from "../../../stores/workspaceStore";
import { buildActivePath, isNodeVisibleInPath } from "../pages/agentWorkspaceDerive";

function node(
  id: string,
  parent_id: string | null,
  children_ids: string[],
): ConversationNode {
  return {
    id,
    parent_id,
    children_ids,
    role: id.startsWith("assistant") ? "assistant" : "user",
    content: id,
    state: "done",
    metadata: {},
    tool_calls: [],
    artifacts: [],
    created_at: "2026-05-14T00:00:00.000Z",
  };
}

describe("Agent workspace search jump derivations", () => {
  it("detects active-path hits so search can scroll without truncating visible history", () => {
    const root = node("root", null, ["user-1"]);
    const user1 = node("user-1", "root", ["assistant-1"]);
    const assistant1 = node("assistant-1", "user-1", ["user-2"]);
    const user2 = node("user-2", "assistant-1", ["assistant-2"]);
    const assistant2 = node("assistant-2", "user-2", []);
    const path = buildActivePath(
      {
        root,
        "user-1": user1,
        "assistant-1": assistant1,
        "user-2": user2,
        "assistant-2": assistant2,
      },
      "assistant-2",
      "root",
    );

    expect(isNodeVisibleInPath(path, "assistant-1")).toBe(true);
    expect(path.map((item) => item.id)).toEqual([
      "user-1",
      "assistant-1",
      "user-2",
      "assistant-2",
    ]);
  });
});
