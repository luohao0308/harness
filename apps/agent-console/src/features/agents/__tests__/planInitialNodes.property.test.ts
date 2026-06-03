// Feature: agent-workspace-chat-refine, Property 4: Initial node structure
import { describe, it, expect } from "vitest";
import fc from "fast-check";

import { planInitialNodes } from "../lib/chatEventReducer";
import type { WorkspaceMode } from "../lib/types";

/**
 * Validates: Requirements 3.1, 6.4
 *
 * Property 4 — for any draft string and any WorkspaceMode:
 *   user.role       === "user"
 *   user.state      === "done"
 *   user.content    === draft
 *   user.parent_id  === null
 *
 *   assistant.role                       === "assistant"
 *   assistant.state                      === "streaming"
 *   assistant.content                    === ""
 *   assistant.metadata.workspace_mode    === mode
 */
const modeGen: fc.Arbitrary<WorkspaceMode> = fc.constantFrom(
  "chat",
  "codex_plan",
  "plan",
  "goal",
);

describe("Property 4: Initial node structure", () => {
  it("produces a matched user/assistant pair for any draft and mode", () => {
    fc.assert(
      fc.property(fc.string(), modeGen, (draft, mode) => {
        const [user, assistant] = planInitialNodes(draft, mode);

        expect(user.role).toBe("user");
        expect(user.state).toBe("done");
        expect(user.content).toBe(draft);
        expect(user.parent_id).toBeNull();
        expect(user.tool_calls).toEqual([]);
        expect(user.artifacts).toEqual([]);

        expect(assistant.role).toBe("assistant");
        expect(assistant.state).toBe("streaming");
        expect(assistant.content).toBe("");
        expect(assistant.metadata.workspace_mode).toBe(mode);
        expect(assistant.tool_calls).toEqual([]);
        expect(assistant.artifacts).toEqual([]);
      }),
      { numRuns: 200 },
    );
  });
});
