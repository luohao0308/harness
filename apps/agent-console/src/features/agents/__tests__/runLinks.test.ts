import { describe, expect, it } from "vitest";

import {
  readWorkspaceReturnTarget,
  runDetailPath,
  saveWorkspaceReturnTarget,
  workspaceReturnPath,
} from "../lib/runLinks";

describe("run detail return links", () => {
  it("keeps the originating workspace conversation in Run Detail links", () => {
    expect(
      runDetailPath("run/1", {
        agentId: "support/agent",
        conversationId: "conv-42",
      }),
    ).toBe(
      "/runs/run%2F1?return_to=%2Fagents%2Fsupport%252Fagent%2Fworkspace%3Fconversation_id%3Dconv-42&conversation_id=conv-42",
    );
  });

  it("adds fragments after the return query string", () => {
    expect(
      runDetailPath("run-1", { agentId: "default", conversationId: "conv-42" }, "approvals"),
    ).toBe(
      "/runs/run-1?return_to=%2Fagents%2Fdefault%2Fworkspace%3Fconversation_id%3Dconv-42&conversation_id=conv-42#approvals",
    );
  });

  it("omits empty conversation ids from workspace paths", () => {
    expect(workspaceReturnPath({ agentId: "default", conversationId: "   " })).toBe(
      "/agents/default/workspace",
    );
  });

  it("persists the source workspace target for same-run refresh fallback", () => {
    saveWorkspaceReturnTarget(
      { agentId: "support-agent", conversationId: "conv-42" },
      "run-1",
    );

    expect(readWorkspaceReturnTarget("run-1")).toEqual({
      agentId: "support-agent",
      conversationId: "conv-42",
    });
    expect(readWorkspaceReturnTarget("run-2")).toBeNull();
  });
});
