// Feature: agent-workspace-chat-v3-slash-history, Properties P15/P16/P17
import { describe, it, expect } from "vitest";
import fc from "fast-check";

import type { ConversationNode } from "../../../stores/workspaceStore";
import {
  computeConversationTitle,
  genesisConversation,
  legacyMigration,
  sortConversationsByUpdatedAt,
  type ConversationSummary,
} from "../lib/conversationHistory";
import type { PersistedSnapshot } from "../lib/localPersistence";

const baseNode: ConversationNode = {
  id: "root",
  parent_id: null,
  children_ids: [],
  role: "system",
  content: "root",
  state: "done",
  metadata: {},
  tool_calls: [],
  artifacts: [],
  created_at: "2025-01-01T00:00:00.000Z",
};

function summaryArb(): fc.Arbitrary<ConversationSummary> {
  return fc
    .record({
      id: fc.uuid(),
      title: fc.string({ maxLength: 40 }),
      // Pick a base within a safe Date range so offset addition cannot overflow.
      baseMs: fc.integer({ min: 0, max: 2_000_000_000_000 }),
      offset: fc.integer({ min: 0, max: 10 }),
    })
    .map(({ id, title, baseMs, offset }) => {
      const created = new Date(baseMs).toISOString();
      const updated = new Date(baseMs + offset * 1000).toISOString();
      return {
        id,
        title,
        created_at: created,
        updated_at: updated,
        nodesById: { root: baseNode },
        rootNodeId: "root",
        activeLeafId: "root",
        pinnedNodeIds: [],
        dismissedPlanNodeIds: [],
        draft: "",
        contextWindowTurns: 8,
      };
    });
}

describe("Property P15: sortConversationsByUpdatedAt is stable and descending", () => {
  it("result is sorted descending by updated_at", () => {
    fc.assert(
      fc.property(fc.array(summaryArb(), { minLength: 0, maxLength: 12 }), (list) => {
        const sorted = sortConversationsByUpdatedAt(list);
        for (let i = 1; i < sorted.length; i += 1) {
          const prev = Date.parse(sorted[i - 1].updated_at);
          const cur = Date.parse(sorted[i].updated_at);
          expect(prev).toBeGreaterThanOrEqual(cur);
        }
      }),
      { numRuns: 100 },
    );
  });

  it("ties preserve input relative order", () => {
    const now = "2025-05-09T10:00:00.000Z";
    const a: ConversationSummary = {
      ...genesisConversation(now, () => "a"),
      id: "a",
      updated_at: now,
    };
    const b: ConversationSummary = { ...a, id: "b", updated_at: now };
    const c: ConversationSummary = { ...a, id: "c", updated_at: now };
    const sorted = sortConversationsByUpdatedAt([a, b, c]);
    expect(sorted.map((s) => s.id)).toEqual(["a", "b", "c"]);
  });

  it("pure: does not mutate the input array", () => {
    fc.assert(
      fc.property(fc.array(summaryArb(), { minLength: 0, maxLength: 6 }), (list) => {
        const before = list.map((c) => c.id);
        sortConversationsByUpdatedAt(list);
        const after = list.map((c) => c.id);
        expect(after).toEqual(before);
      }),
      { numRuns: 50 },
    );
  });
});

describe("Property P16: snapshot preservation after switch A→B→A", () => {
  it("switching via reducer preserves the original conversation's runtime fields", () => {
    // Simulate the reducer loop without pulling in the full store:
    //   1. Start with currentConversationId = a.id, runtime = a snapshot.
    //   2. Switch to b — we write runtime back to conversations[a] and load b.
    //   3. Switch to a — we write runtime back to conversations[b] and load a.
    //   4. Assert the reloaded a matches the original.
    const t0 = "2025-05-09T10:00:00.000Z";
    const t1 = "2025-05-09T11:00:00.000Z";
    const a = {
      ...genesisConversation(t0, () => "a"),
      id: "a",
      draft: "original A draft",
      contextWindowTurns: 5,
      pinnedNodeIds: ["node-1"],
    };
    const b = {
      ...genesisConversation(t1, () => "b"),
      id: "b",
      draft: "B draft",
      contextWindowTurns: 12,
    };

    // Runtime snapshot corresponds to A.
    let runtime = {
      nodesById: a.nodesById,
      rootNodeId: a.rootNodeId,
      activeLeafId: a.activeLeafId,
      pinnedNodeIds: a.pinnedNodeIds,
      dismissedPlanNodeIds: a.dismissedPlanNodeIds,
      draft: a.draft,
      contextWindowTurns: a.contextWindowTurns,
    };
    let conversations: ConversationSummary[] = [a, b];
    let current = a.id;

    const mergeRuntime = (): void => {
      const now = new Date().toISOString();
      conversations = conversations.map((c) =>
        c.id === current
          ? {
              ...c,
              nodesById: runtime.nodesById,
              rootNodeId: runtime.rootNodeId,
              activeLeafId: runtime.activeLeafId,
              pinnedNodeIds: runtime.pinnedNodeIds,
              dismissedPlanNodeIds: runtime.dismissedPlanNodeIds,
              draft: runtime.draft,
              contextWindowTurns: runtime.contextWindowTurns,
              updated_at: now,
            }
          : c,
      );
    };

    const loadConversation = (id: string): void => {
      const target = conversations.find((c) => c.id === id);
      if (!target) throw new Error(`missing ${id}`);
      runtime = {
        nodesById: target.nodesById,
        rootNodeId: target.rootNodeId,
        activeLeafId: target.activeLeafId,
        pinnedNodeIds: target.pinnedNodeIds,
        dismissedPlanNodeIds: target.dismissedPlanNodeIds,
        draft: target.draft,
        contextWindowTurns: target.contextWindowTurns,
      };
      current = id;
    };

    // Switch A → B
    mergeRuntime();
    loadConversation("b");
    // Modify while on B to make sure A isn't accidentally overwritten.
    runtime.draft = "B was edited";
    // Switch B → A
    mergeRuntime();
    loadConversation("a");

    expect(runtime.draft).toBe("original A draft");
    expect(runtime.contextWindowTurns).toBe(5);
    expect(runtime.pinnedNodeIds).toEqual(["node-1"]);
  });
});

describe("Property P17: legacyMigration is deterministic", () => {
  it("produces a single ConversationSummary with identical runtime fields", () => {
    const v2: PersistedSnapshot = {
      version: 1,
      nodesById: {
        root: baseNode,
        "u-1": {
          ...baseNode,
          id: "u-1",
          parent_id: "root",
          role: "user",
          content: "Hello world",
          state: "done",
        },
      },
      rootNodeId: "root",
      activeLeafId: "u-1",
      pinnedNodeIds: ["u-1"],
      contextWindowTurns: 10,
      draft: "drafted",
      dismissedPlanNodeIds: [],
    };
    const migrated = legacyMigration(v2, "2025-05-09T10:00:00.000Z", () => "fixed-id");
    expect(migrated.id).toBe("fixed-id");
    expect(migrated.title).toBe("Hello world");
    expect(migrated.rootNodeId).toBe("root");
    expect(migrated.activeLeafId).toBe("u-1");
    expect(migrated.pinnedNodeIds).toEqual(["u-1"]);
    expect(migrated.draft).toBe("drafted");
    expect(migrated.contextWindowTurns).toBe(10);
    expect(migrated.nodesById["u-1"].state).toBe("done");
  });

  it("rewrites streaming nodes to paused (P11 compat)", () => {
    const v2: PersistedSnapshot = {
      version: 1,
      nodesById: {
        root: baseNode,
        "a-1": {
          ...baseNode,
          id: "a-1",
          role: "assistant",
          state: "streaming",
          content: "half",
        },
      },
      rootNodeId: "root",
      activeLeafId: "a-1",
      pinnedNodeIds: [],
      contextWindowTurns: 8,
      draft: "",
      dismissedPlanNodeIds: [],
    };
    const migrated = legacyMigration(v2, "2025-05-09T10:00:00.000Z", () => "fixed-id");
    expect(migrated.nodesById["a-1"].state).toBe("paused");
  });

  it("falls back to 'Imported' when there is no user message", () => {
    const v2: PersistedSnapshot = {
      version: 1,
      nodesById: { root: baseNode },
      rootNodeId: "root",
      activeLeafId: "root",
      pinnedNodeIds: [],
      contextWindowTurns: 8,
      draft: "",
      dismissedPlanNodeIds: [],
    };
    const migrated = legacyMigration(v2, "2025-05-09T10:00:00.000Z", () => "fixed-id");
    expect(migrated.title).toBe("Imported");
  });
});

describe("computeConversationTitle: first user message ≤ 40 chars", () => {
  it("returns the fallback when there is no user message", () => {
    const result = computeConversationTitle({ root: baseNode }, "FALLBACK");
    expect(result).toBe("FALLBACK");
  });

  it("truncates long user content to 40 characters", () => {
    const long = "a".repeat(100);
    const user: ConversationNode = {
      ...baseNode,
      id: "u",
      role: "user",
      content: long,
    };
    const result = computeConversationTitle({ root: baseNode, u: user }, "FALLBACK");
    expect(result.length).toBe(40);
  });
});
