/**
 * Unit tests for context truncation logic (Phase 4 / Task 4.7).
 *
 * Validates:
 *   - Messages truncated from oldest when exceeding limit
 *   - Pinned messages always preserved regardless of position
 *   - System messages always preserved
 *   - Most recent user/assistant pair always preserved
 *   - No truncation when within limit
 *   - Pinned overflow detected when pinned alone exceed budget
 *   - excludedCount correctly reported
 *   - Token estimation uses content.length / 4
 */

import { describe, expect, it } from "vitest";

import type { ConversationNode } from "../../../stores/workspaceStore";
import { estimateTokens, truncateForContext } from "../lib/contextTruncation";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeNode(overrides: Partial<ConversationNode> & { id: string }): ConversationNode {
  return {
    parent_id: null,
    children_ids: [],
    role: "user",
    content: "",
    state: "done",
    metadata: {},
    tool_calls: [],
    artifacts: [],
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

/**
 * Create a string of exactly `tokenCount * 4` characters so that
 * `estimateTokens` returns `tokenCount`.
 */
function contentForTokens(tokenCount: number): string {
  return "x".repeat(tokenCount * 4);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("estimateTokens", () => {
  it("uses content.length / 4 (ceiling)", () => {
    const node = makeNode({ id: "a", content: "hello world!" }); // 12 chars → ceil(12/4) = 3
    expect(estimateTokens(node)).toBe(3);
  });

  it("returns 0 for empty content", () => {
    const node = makeNode({ id: "a", content: "" });
    expect(estimateTokens(node)).toBe(0);
  });

  it("rounds up for non-divisible lengths", () => {
    const node = makeNode({ id: "a", content: "ab" }); // 2 chars → ceil(2/4) = 1
    expect(estimateTokens(node)).toBe(1);
  });
});

describe("truncateForContext", () => {
  describe("no truncation when within limit", () => {
    it("returns all messages when total tokens are within budget", () => {
      const nodes = [
        makeNode({ id: "1", role: "user", content: contentForTokens(10) }),
        makeNode({ id: "2", role: "assistant", content: contentForTokens(10) }),
        makeNode({ id: "3", role: "user", content: contentForTokens(10) }),
        makeNode({ id: "4", role: "assistant", content: contentForTokens(10) }),
      ];
      const result = truncateForContext(nodes, [], 100);
      expect(result.messages).toHaveLength(4);
      expect(result.excludedCount).toBe(0);
      expect(result.pinnedOverflow).toBe(false);
    });

    it("returns empty array for empty input", () => {
      const result = truncateForContext([], [], 100);
      expect(result.messages).toHaveLength(0);
      expect(result.excludedCount).toBe(0);
      expect(result.pinnedOverflow).toBe(false);
    });
  });

  describe("messages truncated from oldest when exceeding limit", () => {
    it("removes oldest non-protected messages first", () => {
      const nodes = [
        makeNode({ id: "1", role: "user", content: contentForTokens(20) }),
        makeNode({ id: "2", role: "assistant", content: contentForTokens(20) }),
        makeNode({ id: "3", role: "user", content: contentForTokens(20) }),
        makeNode({ id: "4", role: "assistant", content: contentForTokens(20) }),
      ];
      // Budget = 50 tokens. Total = 80. Recent pair = nodes 3+4 (40 tokens).
      // Removable = nodes 1+2 (40 tokens). Need to remove 30 tokens worth.
      // Node 1 (20 tokens) removed first, then node 2 (20 tokens) removed.
      const result = truncateForContext(nodes, [], 50);
      expect(result.messages.map((m) => m.id)).toEqual(["3", "4"]);
      expect(result.excludedCount).toBe(2);
      expect(result.pinnedOverflow).toBe(false);
    });

    it("removes only enough messages to fit within budget", () => {
      const nodes = [
        makeNode({ id: "1", role: "user", content: contentForTokens(10) }),
        makeNode({ id: "2", role: "assistant", content: contentForTokens(10) }),
        makeNode({ id: "3", role: "user", content: contentForTokens(10) }),
        makeNode({ id: "4", role: "assistant", content: contentForTokens(10) }),
        makeNode({ id: "5", role: "user", content: contentForTokens(10) }),
        makeNode({ id: "6", role: "assistant", content: contentForTokens(10) }),
      ];
      // Total = 60. Budget = 45. Recent pair = 5+6 (20 tokens protected).
      // Removable = 1,2,3,4 (40 tokens). Need to remove 60-45=15 tokens.
      // Remove node 1 (10 tokens) → still need 5 more → remove node 2 (10 tokens).
      const result = truncateForContext(nodes, [], 45);
      expect(result.messages.map((m) => m.id)).toEqual(["3", "4", "5", "6"]);
      expect(result.excludedCount).toBe(2);
    });
  });

  describe("pinned messages always preserved regardless of position", () => {
    it("preserves a pinned message in the middle even when truncating", () => {
      const nodes = [
        makeNode({ id: "1", role: "user", content: contentForTokens(20) }),
        makeNode({ id: "2", role: "assistant", content: contentForTokens(20) }),
        makeNode({ id: "3", role: "user", content: contentForTokens(20) }),
        makeNode({ id: "4", role: "assistant", content: contentForTokens(20) }),
      ];
      // Budget = 50. Pinned = ["2"]. Protected = system + pinned(2) + recent pair(3,4).
      // Protected tokens = 20+20+20 = 60. Removable = node 1 (20 tokens).
      // Total = 80. Protected alone = 60 > 50? Yes → all protected included.
      // Actually let's use a bigger budget to test the simpler case.
      const result = truncateForContext(nodes, ["2"], 65);
      // Protected: node 2 (pinned, 20), node 3 (recent user, 20), node 4 (recent assistant, 20) = 60
      // Removable: node 1 (20). Total removable = 20. Budget remaining = 65-60 = 5.
      // Need to remove 20-5 = 15 tokens → remove node 1.
      expect(result.messages.map((m) => m.id)).toEqual(["2", "3", "4"]);
      expect(result.excludedCount).toBe(1);
    });

    it("preserves pinned message at the oldest position", () => {
      const nodes = [
        makeNode({ id: "1", role: "user", content: contentForTokens(10) }),
        makeNode({ id: "2", role: "assistant", content: contentForTokens(10) }),
        makeNode({ id: "3", role: "user", content: contentForTokens(10) }),
        makeNode({ id: "4", role: "assistant", content: contentForTokens(10) }),
      ];
      // Pin node 1. Budget = 25. Protected = node 1 (pinned) + node 3,4 (recent pair) = 30.
      // Protected > budget → include all protected, excludedCount = 1 (node 2).
      const result = truncateForContext(nodes, ["1"], 25);
      expect(result.messages.map((m) => m.id)).toContain("1");
      expect(result.messages.map((m) => m.id)).toContain("3");
      expect(result.messages.map((m) => m.id)).toContain("4");
      expect(result.messages.map((m) => m.id)).not.toContain("2");
    });
  });

  describe("system messages always preserved", () => {
    it("keeps system messages even when truncating heavily", () => {
      const nodes = [
        makeNode({ id: "sys", role: "system", content: contentForTokens(5) }),
        makeNode({ id: "1", role: "user", content: contentForTokens(20) }),
        makeNode({ id: "2", role: "assistant", content: contentForTokens(20) }),
        makeNode({ id: "3", role: "user", content: contentForTokens(20) }),
        makeNode({ id: "4", role: "assistant", content: contentForTokens(20) }),
      ];
      // Budget = 30. Protected = sys(5) + recent pair 3+4(40) = 45 > 30.
      // All protected included regardless.
      const result = truncateForContext(nodes, [], 30);
      expect(result.messages.map((m) => m.id)).toContain("sys");
    });
  });

  describe("most recent user/assistant pair always preserved", () => {
    it("preserves the last user and last assistant even with tight budget", () => {
      const nodes = [
        makeNode({ id: "1", role: "user", content: contentForTokens(100) }),
        makeNode({ id: "2", role: "assistant", content: contentForTokens(100) }),
        makeNode({ id: "3", role: "user", content: contentForTokens(100) }),
        makeNode({ id: "4", role: "assistant", content: contentForTokens(100) }),
      ];
      // Budget = 10. Way too small. Protected = recent pair (3+4) = 200 tokens.
      // Protected > budget → include all protected.
      const result = truncateForContext(nodes, [], 10);
      expect(result.messages.map((m) => m.id)).toContain("3");
      expect(result.messages.map((m) => m.id)).toContain("4");
    });

    it("identifies the most recent user even if it comes before the last assistant", () => {
      const nodes = [
        makeNode({ id: "1", role: "user", content: contentForTokens(10) }),
        makeNode({ id: "2", role: "assistant", content: contentForTokens(10) }),
        makeNode({ id: "3", role: "user", content: contentForTokens(10) }),
        makeNode({ id: "4", role: "assistant", content: contentForTokens(10) }),
        makeNode({ id: "5", role: "user", content: contentForTokens(10) }),
      ];
      // Last assistant = 4, last user = 5. Both should be preserved.
      const result = truncateForContext(nodes, [], 25);
      expect(result.messages.map((m) => m.id)).toContain("4");
      expect(result.messages.map((m) => m.id)).toContain("5");
    });
  });

  describe("pinned overflow detected when pinned alone exceed budget", () => {
    it("sets pinnedOverflow=true when pinned tokens exceed maxTokens", () => {
      const nodes = [
        makeNode({ id: "1", role: "user", content: contentForTokens(50) }),
        makeNode({ id: "2", role: "assistant", content: contentForTokens(50) }),
        makeNode({ id: "3", role: "user", content: contentForTokens(10) }),
        makeNode({ id: "4", role: "assistant", content: contentForTokens(10) }),
      ];
      // Pin nodes 1 and 2 (100 tokens total pinned). Budget = 30.
      // Protected = pinned(1,2) + recent pair(3,4) = 120 > 30.
      // Pinned alone = 100 > 30 → pinnedOverflow = true.
      const result = truncateForContext(nodes, ["1", "2"], 30);
      expect(result.pinnedOverflow).toBe(true);
      // All protected messages still included.
      expect(result.messages.map((m) => m.id)).toContain("1");
      expect(result.messages.map((m) => m.id)).toContain("2");
      expect(result.messages.map((m) => m.id)).toContain("3");
      expect(result.messages.map((m) => m.id)).toContain("4");
    });

    it("sets pinnedOverflow=false when pinned fit but total protected exceeds", () => {
      const nodes = [
        makeNode({ id: "1", role: "user", content: contentForTokens(10) }),
        makeNode({ id: "2", role: "assistant", content: contentForTokens(50) }),
        makeNode({ id: "3", role: "user", content: contentForTokens(50) }),
        makeNode({ id: "4", role: "assistant", content: contentForTokens(50) }),
      ];
      // Pin node 1 (10 tokens). Budget = 80.
      // Protected = pinned(1, 10) + recent pair(3+4, 100) = 110 > 80.
      // Pinned alone = 10 < 80 → pinnedOverflow = false.
      const result = truncateForContext(nodes, ["1"], 80);
      expect(result.pinnedOverflow).toBe(false);
      // All protected still included.
      expect(result.messages.map((m) => m.id)).toContain("1");
    });
  });

  describe("excludedCount correctly reported", () => {
    it("reports the exact number of excluded messages", () => {
      const nodes = [
        makeNode({ id: "1", role: "user", content: contentForTokens(10) }),
        makeNode({ id: "2", role: "assistant", content: contentForTokens(10) }),
        makeNode({ id: "3", role: "user", content: contentForTokens(10) }),
        makeNode({ id: "4", role: "assistant", content: contentForTokens(10) }),
        makeNode({ id: "5", role: "user", content: contentForTokens(10) }),
        makeNode({ id: "6", role: "assistant", content: contentForTokens(10) }),
      ];
      // Total = 60. Budget = 35. Protected = recent pair(5+6) = 20.
      // Removable = 1,2,3,4 (40 tokens). Remaining budget = 35-20 = 15.
      // Need to remove 40-15 = 25 tokens. Remove 1(10), 2(10), 3(10) = 30 removed.
      const result = truncateForContext(nodes, [], 35);
      expect(result.excludedCount).toBe(3);
      expect(result.messages).toHaveLength(3);
    });

    it("reports 0 when no truncation needed", () => {
      const nodes = [
        makeNode({ id: "1", role: "user", content: contentForTokens(5) }),
        makeNode({ id: "2", role: "assistant", content: contentForTokens(5) }),
      ];
      const result = truncateForContext(nodes, [], 100);
      expect(result.excludedCount).toBe(0);
    });
  });

  describe("token estimation uses content.length / 4", () => {
    it("a 400-char message estimates to 100 tokens", () => {
      const node = makeNode({ id: "1", role: "user", content: "a".repeat(400) });
      expect(estimateTokens(node)).toBe(100);
    });

    it("a 401-char message estimates to 101 tokens (ceiling)", () => {
      const node = makeNode({ id: "1", role: "user", content: "a".repeat(401) });
      expect(estimateTokens(node)).toBe(101);
    });

    it("truncation respects the token estimation", () => {
      // 2 messages of 200 chars each = 50 tokens each = 100 total.
      // Budget = 60 tokens. Recent pair protected (both). No truncation needed.
      const nodes = [
        makeNode({ id: "1", role: "user", content: "a".repeat(200) }),
        makeNode({ id: "2", role: "assistant", content: "a".repeat(200) }),
      ];
      const result = truncateForContext(nodes, [], 60);
      // 50+50=100 > 60, but both are the recent pair → protected.
      // Protected > budget → include all.
      expect(result.messages).toHaveLength(2);
    });
  });

  describe("edge cases", () => {
    it("handles conversation with only system messages", () => {
      const nodes = [
        makeNode({ id: "sys1", role: "system", content: contentForTokens(10) }),
        makeNode({ id: "sys2", role: "system", content: contentForTokens(10) }),
      ];
      const result = truncateForContext(nodes, [], 5);
      // System messages are always protected.
      expect(result.messages).toHaveLength(2);
      expect(result.messages.map((m) => m.id)).toEqual(["sys1", "sys2"]);
    });

    it("handles a single message", () => {
      const nodes = [
        makeNode({ id: "1", role: "user", content: contentForTokens(10) }),
      ];
      const result = truncateForContext(nodes, [], 5);
      // Single user message is the "most recent user" → protected.
      expect(result.messages).toHaveLength(1);
    });

    it("preserves message order after truncation", () => {
      const nodes = [
        makeNode({ id: "1", role: "user", content: contentForTokens(10) }),
        makeNode({ id: "2", role: "assistant", content: contentForTokens(10) }),
        makeNode({ id: "3", role: "user", content: contentForTokens(10) }),
        makeNode({ id: "4", role: "assistant", content: contentForTokens(10) }),
        makeNode({ id: "5", role: "user", content: contentForTokens(10) }),
        makeNode({ id: "6", role: "assistant", content: contentForTokens(10) }),
      ];
      // Pin node 3. Budget = 35. Protected = pinned(3) + recent pair(5,6) = 30.
      // Removable = 1,2,4 (30 tokens). Remaining budget = 35-30 = 5.
      // Need to remove 30-5 = 25 tokens. Remove 1(10), 2(10), 4(10).
      const result = truncateForContext(nodes, ["3"], 35);
      // Remaining should be in original order: 3, 5, 6
      const ids = result.messages.map((m) => m.id);
      expect(ids).toEqual(["3", "5", "6"]);
    });
  });
});
