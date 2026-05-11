// Feature: agent-workspace-chat-v3-slash-history, Property P19
import { describe, it, expect } from "vitest";
import fc from "fast-check";

import type { ConversationNode } from "../../../stores/workspaceStore";
import {
  JUMP_TO_LATEST_THRESHOLD_PX,
  computeFollowDecision,
  contentSum,
  isCloseToBottom,
} from "../lib/autoScrollFollow";

/**
 * P19 — follow decision is gated by `autoFollow`.
 */
describe("Property P19: computeFollowDecision follows autoFollow", () => {
  it("returns shouldScroll=false when autoFollow=false, regardless of content sums", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 100_000 }),
        fc.integer({ min: 0, max: 100_000 }),
        (prev, next) => {
          const result = computeFollowDecision({
            autoFollow: false,
            prevContentSum: prev,
            nextContentSum: next,
          });
          expect(result.shouldScroll).toBe(false);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("returns shouldScroll=true when autoFollow=true", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 100_000 }),
        fc.integer({ min: 0, max: 100_000 }),
        (prev, next) => {
          const result = computeFollowDecision({
            autoFollow: true,
            prevContentSum: prev,
            nextContentSum: next,
          });
          expect(result.shouldScroll).toBe(true);
        },
      ),
      { numRuns: 200 },
    );
  });
});

describe("contentSum is a plain sum of content lengths", () => {
  function makeNode(content: string): ConversationNode {
    return {
      id: "n-" + content.slice(0, 2),
      parent_id: null,
      children_ids: [],
      role: "assistant",
      content,
      state: "done",
      metadata: {},
      tool_calls: [],
      artifacts: [],
      created_at: "2025-01-01T00:00:00.000Z",
    };
  }

  it("yields zero for empty path", () => {
    expect(contentSum([])).toBe(0);
  });

  it("adds content lengths across the path", () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ maxLength: 200 }), { maxLength: 8 }),
        (contents) => {
          const nodes = contents.map(makeNode);
          const expected = contents.reduce((acc, c) => acc + c.length, 0);
          expect(contentSum(nodes)).toBe(expected);
        },
      ),
      { numRuns: 100 },
    );
  });
});

describe("isCloseToBottom threshold", () => {
  it("matches the 200 px threshold", () => {
    expect(isCloseToBottom(1000, 800, 100)).toBe(true); // remaining 100
    expect(isCloseToBottom(1000, 700, 100)).toBe(true); // remaining 200 == threshold
    expect(isCloseToBottom(1000, 699, 100)).toBe(false); // remaining 201
    expect(JUMP_TO_LATEST_THRESHOLD_PX).toBe(200);
  });
});
