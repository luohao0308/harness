// Feature: agent-workspace-chat-refine, Property 7: Active-path queries
import { describe, it, expect } from "vitest";
import fc from "fast-check";

import {
  canResume,
  findPrevUser,
  shouldShowRunSummary,
} from "../lib/activePathQueries";
import type {
  ConversationNode,
  ConversationRole,
  ConversationState,
} from "../../../stores/workspaceStore";

/**
 * Validates: Requirements 4.5, 4.6, 5.3, 5.5, 7.5, 8.2
 *
 * Property 7 — activePath query helpers:
 *   (a) findPrevUser returns the nearest user node at an index strictly
 *       less than the target's index, or undefined;
 *   (b) canResume is true iff there is any paused assistant node with a
 *       non-empty run_id in the path;
 *   (c) shouldShowRunSummary is true iff the node is an assistant/done
 *       with a non-empty run_id.
 */

const roleGen: fc.Arbitrary<ConversationRole> = fc.constantFrom(
  "user",
  "assistant",
  "system",
  "tool",
);

const stateGen: fc.Arbitrary<ConversationState> = fc.constantFrom(
  "draft",
  "streaming",
  "paused",
  "done",
  "error",
);

function makeNode(
  id: string,
  role: ConversationRole,
  state: ConversationState,
  runId: string | undefined,
): ConversationNode {
  return {
    id,
    parent_id: null,
    children_ids: [],
    role,
    content: "",
    state,
    run_id: runId,
    metadata: {},
    tool_calls: [],
    artifacts: [],
    created_at: new Date(0).toISOString(),
  };
}

const nodeSeedGen = fc.record({
  role: roleGen,
  state: stateGen,
  runId: fc.option(fc.string({ maxLength: 8 }), { nil: undefined }),
});

function buildPath(
  seeds: Array<{ role: ConversationRole; state: ConversationState; runId?: string }>,
): ConversationNode[] {
  return seeds.map((seed, index) =>
    makeNode(`n${index}`, seed.role, seed.state, seed.runId),
  );
}

describe("Property 7: Active-path queries", () => {
  it("findPrevUser returns the max-index user node preceding the target", () => {
    fc.assert(
      fc.property(
        fc.array(nodeSeedGen, { minLength: 1, maxLength: 10 }),
        fc.integer({ min: 0, max: 9 }),
        (seeds, rawIndex) => {
          const path = buildPath(seeds);
          const targetIndex = rawIndex % path.length;
          const target = path[targetIndex];

          const actual = findPrevUser(path, target.id);

          // Compute the reference answer by linear scan: the largest
          // index strictly less than `targetIndex` whose role is "user".
          let expected: ConversationNode | undefined;
          for (let i = targetIndex - 1; i >= 0; i -= 1) {
            if (path[i].role === "user") {
              expected = path[i];
              break;
            }
          }

          if (expected === undefined) {
            expect(actual).toBeUndefined();
          } else {
            expect(actual?.id).toBe(expected.id);
          }
        },
      ),
      { numRuns: 200 },
    );
  });

  it("findPrevUser returns undefined for unknown target ids", () => {
    fc.assert(
      fc.property(
        fc.array(nodeSeedGen, { maxLength: 6 }),
        fc.string({ minLength: 1, maxLength: 4 }),
        (seeds, stray) => {
          const path = buildPath(seeds);
          if (path.some((n) => n.id === stray)) return;
          expect(findPrevUser(path, stray)).toBeUndefined();
        },
      ),
      { numRuns: 100 },
    );
  });

  it("canResume detects any paused assistant node with a non-empty run_id", () => {
    fc.assert(
      fc.property(
        fc.array(nodeSeedGen, { maxLength: 10 }),
        (seeds) => {
          const path = buildPath(seeds);
          const expected = path.some(
            (node) =>
              node.role === "assistant" &&
              node.state === "paused" &&
              typeof node.run_id === "string" &&
              node.run_id.length > 0,
          );
          expect(canResume(path)).toBe(expected);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("shouldShowRunSummary truth table", () => {
    fc.assert(
      fc.property(nodeSeedGen, (seed) => {
        const node = makeNode("only", seed.role, seed.state, seed.runId);
        const expected =
          seed.role === "assistant" &&
          seed.state === "done" &&
          typeof seed.runId === "string" &&
          seed.runId.length > 0;
        expect(shouldShowRunSummary(node)).toBe(expected);
      }),
      { numRuns: 200 },
    );
  });
});
