// Feature: agent-workspace-chat-v4-refine, Property P24
import { describe, expect, it } from "vitest";
import fc from "fast-check";

import type {
  ConversationNode,
  ConversationRole,
  ConversationState,
} from "../../../stores/workspaceStore";
import { groupByRole } from "../lib/groupByRole";

const roleArb: fc.Arbitrary<ConversationRole> = fc.constantFrom(
  "user",
  "assistant",
  "system",
  "tool",
);

const stateArb: fc.Arbitrary<ConversationState> = fc.constantFrom(
  "draft",
  "streaming",
  "done",
  "paused",
  "error",
);

const nodeArb: fc.Arbitrary<ConversationNode> = fc
  .record({
    id: fc.string({ minLength: 1, maxLength: 8 }),
    role: roleArb,
    content: fc.string({ maxLength: 24 }),
    state: stateArb,
  })
  .map(
    ({ id, role, content, state }) =>
      ({
        id,
        parent_id: null,
        children_ids: [],
        role,
        content,
        state,
        metadata: {},
        tool_calls: [],
        artifacts: [],
        created_at: "2026-01-01T00:00:00.000Z",
      }) satisfies ConversationNode,
  );

/**
 * P24 — `groupByRole` preserves order, groups consecutive same-role nodes,
 * isolates error nodes, and is TOTAL. Validates Req 7.3.1 / 7.3.2 / 7.3.3 /
 * 12.5.
 */
describe("Property P24: Group-by-role totality & equivalence", () => {
  it("flatMap(nodes) deep-equals the input path (order-preserving)", () => {
    fc.assert(
      fc.property(fc.array(nodeArb, { maxLength: 50 }), (path) => {
        const groups = groupByRole(path);
        const flattened = groups.flatMap((g) => g.nodes);
        expect(flattened.length).toBe(path.length);
        for (let i = 0; i < path.length; i += 1) {
          // Reference equality (same object, same order).
          expect(flattened[i]).toBe(path[i]);
        }
      }),
      { numRuns: 200 },
    );
  });

  it("every node inside a group shares that group's role", () => {
    fc.assert(
      fc.property(fc.array(nodeArb, { maxLength: 50 }), (path) => {
        for (const group of groupByRole(path)) {
          expect(group.nodes.length).toBeGreaterThanOrEqual(1);
          for (const node of group.nodes) {
            expect(node.role).toBe(group.role);
          }
        }
      }),
      { numRuns: 200 },
    );
  });

  it("error nodes occupy singleton groups", () => {
    fc.assert(
      fc.property(fc.array(nodeArb, { maxLength: 50 }), (path) => {
        const groups = groupByRole(path);
        for (const group of groups) {
          const hasError = group.nodes.some((n) => n.state === "error");
          if (hasError) {
            expect(group.nodes.length).toBe(1);
            expect(group.nodes[0].state).toBe("error");
          }
        }
      }),
      { numRuns: 200 },
    );
  });

  it("empty input → empty output", () => {
    expect(groupByRole([])).toEqual([]);
  });

  it("never throws", () => {
    fc.assert(
      fc.property(fc.array(nodeArb, { maxLength: 50 }), (path) => {
        expect(() => groupByRole(path)).not.toThrow();
      }),
      { numRuns: 200 },
    );
  });
});
