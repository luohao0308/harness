import { create } from "zustand";

import type { ConversationErrorMeta } from "../features/agents/lib/sseErrors";
import {
  AUTO_COMPRESSION_RATIO_DEFAULT,
  CONTEXT_MAX_TOKENS_DEFAULT,
  clampAutoCompressionRatio,
  clampContextMaxTokens,
  saveAutoCompressionRatio,
  saveContextMaxTokens,
} from "../features/agents/lib/contextTokens";
import type { ContextCompressionSummary } from "../features/agents/lib/contextCompression";
import {
  CONVERSATIONS_SCHEMA_VERSION,
  computeConversationTitle,
  generateConversationId,
  genesisConversation,
  saveConversationsSnapshot,
  saveHistoryPanelCollapsed,
  sortConversationsByUpdatedAt,
  type ConversationSummary,
} from "../features/agents/lib/conversationHistory";

export type ConversationRole = "user" | "assistant" | "system" | "tool";
export type ConversationState = "draft" | "streaming" | "paused" | "done" | "error";

export type ConversationArtifact = {
  id: string;
  name: string;
  artifact_type: "code" | "json" | "diff" | "chart" | "text";
  status: string;
  content: unknown;
  run_id?: string;
};

export type ConversationNode = {
  id: string;
  parent_id: string | null;
  children_ids: string[];
  role: ConversationRole;
  content: string;
  state: ConversationState;
  run_id?: string;
  metadata: {
    input_tokens?: number;
    output_tokens?: number;
    cost_usd?: string | null;
    cost_unavailable?: boolean;
    ttfb_ms?: number;
    duration_ms?: number;
    model_call_id?: string | null;
    active_branch_id?: string | null;
    workspace_mode?: "chat" | "markdown_plan" | "plan" | "goal";
    knowledge_grounding?: string | null;
    orchestration?: Record<string, unknown>;
    error?: ConversationErrorMeta;
    // v2 additive (Design §Data Models → ConversationNode)
    streaming_diagnostic?: "possible_buffering";
  };
  tool_calls: Array<Record<string, unknown>>;
  artifacts: ConversationArtifact[];
  created_at: string;
};

type WorkspaceStream = {
  node_id: string;
  controller: AbortController;
  started_at: number;
};

type WorkspaceState = {
  // --- v1 fields (unchanged) ---
  nodesById: Record<string, ConversationNode>;
  rootNodeId: string;
  activeLeafId: string;
  pinnedNodeIds: string[];
  contextWindowTurns: number;
  activeStream: WorkspaceStream | null;
  draftFromNodeId: string | null;
  draft: string;
  // --- v2 additive fields (Req 3.5, 12.1–12.6, 15.3) ---
  dismissedPlanNodeIds: string[];
  _agentScope: string | null;
  // --- v3 additive fields (Req 4.*, 8.3) ---
  /**
   * Full list of conversations belonging to the currently-scoped agent.
   * Always contains at least one entry — an empty list would have no
   * `currentConversationId` target. Persisted via
   * `saveConversationsSnapshot`.
   */
  conversations: ConversationSummary[];
  /** Id of the active conversation; the runtime store fields mirror it. */
  currentConversationId: string;
  /** Left-side history panel collapsed state; persisted per-agent. */
  historyPanelCollapsed: boolean;
  // --- v4 additive fields (Req 5.*) ---
  /**
   * Model context window budget, tokens. Initial value is the v3-observable
   * 8192 (NOT passed through `clampContextMaxTokens` so the slider shows
   * the historical default); user-initiated updates via
   * `setContextMaxTokens` go through the clamp.
   */
  contextMaxTokens: number;
  autoCompressionRatio: number;
  contextCompressions: Record<string, ContextCompressionSummary>;
  // --- v5 additive fields (Run state persistence across navigation) ---
  /** Active Run id; survives route navigation so returning to Workspace shows the last Run. */
  activeRunId: string | null;
  // --- v1 actions (unchanged) ---
  reset: () => void;
  setDraft: (draft: string) => void;
  setContextWindowTurns: (turns: number) => void;
  setActiveStream: (stream: WorkspaceStream | null) => void;
  appendNode: (node: Omit<ConversationNode, "id" | "children_ids" | "created_at">) => string;
  removeLeafNode: (nodeId: string) => void;
  updateNode: (nodeId: string, patch: Partial<ConversationNode>) => void;
  appendContent: (nodeId: string, content: string) => void;
  appendArtifact: (nodeId: string, artifact: ConversationArtifact) => void;
  togglePinned: (nodeId: string) => void;
  startEdit: (nodeId: string) => void;
  setActiveLeafId: (nodeId: string) => void;
  getSiblings: (nodeId: string) => ConversationNode[];
  getBranchLeafId: (nodeId: string) => string | null;
  switchToBranch: (nodeId: string) => void;
  activePath: () => ConversationNode[];
  // --- v2 additive actions ---
  dismissPlanNode: (nodeId: string) => void;
  clearDismissedPlanNodes: () => void;
  setAgentScope: (agentId: string | null) => void;
  // --- v3 additive actions ---
  newConversation: () => string;
  setCurrentConversation: (id: string) => void;
  deleteConversation: (id: string) => void;
  renameConversation: (id: string, title: string) => void;
  setHistoryPanelCollapsed: (collapsed: boolean) => void;
  hydrateFromConversations: (snapshot: {
    conversations: ConversationSummary[];
    currentConversationId: string;
    historyPanelCollapsed?: boolean;
  }) => void;
  // --- v4 additive actions ---
  /** Route the value through `clampContextMaxTokens` before writing. */
  setContextMaxTokens: (value: number) => void;
  setAutoCompressionRatio: (value: number) => void;
  setContextCompression: (branchKey: string, summary: ContextCompressionSummary) => void;
  clearContextCompression: (branchKey: string) => void;
  // --- v5 additive actions ---
  setActiveRunId: (runId: string | null) => void;
};

const rootNode: ConversationNode = {
  id: "root",
  parent_id: null,
  children_ids: [],
  role: "system",
  content: "Agent Workspace Pro root",
  state: "done",
  metadata: {},
  tool_calls: [],
  artifacts: [],
  created_at: new Date().toISOString(),
};

function nodeId() {
  return `node-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function createNode(input: Omit<ConversationNode, "id" | "children_ids" | "created_at">) {
  return {
    ...input,
    id: nodeId(),
    children_ids: [],
    created_at: new Date().toISOString(),
  };
}

// The initial genesis conversation is created lazily to guarantee a fresh
// `created_at` / `updated_at` pair and a fresh id per module instance.
const initialGenesis = genesisConversation(new Date().toISOString());

/**
 * Internal reducer: given the current runtime state (nodesById / etc.) and
 * the persisted `conversations` list, write the runtime state back to the
 * current `ConversationSummary` (updating `updated_at` and deriving title
 * from the first user message when the title is still the default). Pure
 * function so it's easy to reason about and unit test.
 */
function mergeRuntimeIntoConversations(
  state: Pick<
    WorkspaceState,
    | "conversations"
    | "currentConversationId"
    | "nodesById"
    | "rootNodeId"
    | "activeLeafId"
    | "pinnedNodeIds"
    | "dismissedPlanNodeIds"
    | "draft"
    | "contextWindowTurns"
    | "contextCompressions"
  >,
  now: string,
): ConversationSummary[] {
  return state.conversations.map((c) =>
    c.id === state.currentConversationId
      ? {
          ...c,
          nodesById: state.nodesById,
          rootNodeId: state.rootNodeId,
          activeLeafId: state.activeLeafId,
          pinnedNodeIds: state.pinnedNodeIds,
          dismissedPlanNodeIds: state.dismissedPlanNodeIds,
          draft: state.draft,
          contextWindowTurns: state.contextWindowTurns,
          contextCompressions: state.contextCompressions,
          updated_at: now,
          title: computeConversationTitle(state.nodesById, c.title),
        }
      : c,
  );
}

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  nodesById: initialGenesis.nodesById,
  rootNodeId: initialGenesis.rootNodeId,
  activeLeafId: initialGenesis.activeLeafId,
  pinnedNodeIds: [],
  contextWindowTurns: 8,
  activeStream: null,
  draftFromNodeId: null,
  draft: "",
  dismissedPlanNodeIds: [],
  _agentScope: null,
  conversations: [initialGenesis],
  currentConversationId: initialGenesis.id,
  historyPanelCollapsed: false,
  // v4 — see field doc for why we bypass `clampContextMaxTokens` here.
  contextMaxTokens: CONTEXT_MAX_TOKENS_DEFAULT,
  autoCompressionRatio: AUTO_COMPRESSION_RATIO_DEFAULT,
  contextCompressions: initialGenesis.contextCompressions,
  // v5 — persists across navigation
  activeRunId: null,
  reset: () =>
    set({
      nodesById: { [rootNode.id]: { ...rootNode, children_ids: [] } },
      activeLeafId: rootNode.id,
      pinnedNodeIds: [],
      activeStream: null,
      draftFromNodeId: null,
      draft: "",
      dismissedPlanNodeIds: [],
      contextMaxTokens: CONTEXT_MAX_TOKENS_DEFAULT,
      autoCompressionRatio: AUTO_COMPRESSION_RATIO_DEFAULT,
      contextCompressions: {},
    }),
  setDraft: (draft) => set({ draft }),
  setContextWindowTurns: (turns) => set({ contextWindowTurns: turns }),
  setActiveStream: (stream) => set({ activeStream: stream }),
  appendNode: (input) => {
    const parentId = input.parent_id ?? get().activeLeafId;
    const node = createNode({ ...input, parent_id: parentId });
    set((state) => {
      const parent = state.nodesById[parentId];
      return {
        nodesById: {
          ...state.nodesById,
          [parentId]: parent
            ? { ...parent, children_ids: [...parent.children_ids, node.id] }
            : state.nodesById[parentId],
          [node.id]: node,
        },
        activeLeafId: node.id,
      };
    });
    return node.id;
  },
  removeLeafNode: (nodeIdToRemove) =>
    set((state) => {
      const node = state.nodesById[nodeIdToRemove];
      if (!node || node.children_ids.length > 0 || node.id === state.rootNodeId) return state;
      const nextNodesById = { ...state.nodesById };
      delete nextNodesById[nodeIdToRemove];
      const parentId = node.parent_id;
      if (parentId !== null) {
        const parent = nextNodesById[parentId];
        if (parent) {
          nextNodesById[parentId] = {
            ...parent,
            children_ids: parent.children_ids.filter((id) => id !== nodeIdToRemove),
          };
        }
      }
      return {
        nodesById: nextNodesById,
        activeLeafId:
          state.activeLeafId === nodeIdToRemove
            ? parentId ?? state.rootNodeId
            : state.activeLeafId,
        pinnedNodeIds: state.pinnedNodeIds.filter((id) => id !== nodeIdToRemove),
        dismissedPlanNodeIds: state.dismissedPlanNodeIds.filter((id) => id !== nodeIdToRemove),
      };
    }),
  updateNode: (nodeIdToUpdate, patch) =>
    set((state) => ({
      nodesById: {
        ...state.nodesById,
        [nodeIdToUpdate]: { ...state.nodesById[nodeIdToUpdate], ...patch },
      },
    })),
  appendContent: (nodeIdToUpdate, content) =>
    set((state) => {
      const node = state.nodesById[nodeIdToUpdate];
      return {
        nodesById: {
          ...state.nodesById,
          [nodeIdToUpdate]: { ...node, content: node.content + content },
        },
      };
    }),
  appendArtifact: (nodeIdToUpdate, artifact) =>
    set((state) => {
      const node = state.nodesById[nodeIdToUpdate];
      return {
        nodesById: {
          ...state.nodesById,
          [nodeIdToUpdate]: { ...node, artifacts: [...node.artifacts, artifact] },
        },
      };
    }),
  togglePinned: (nodeIdToToggle) =>
    set((state) => ({
      pinnedNodeIds: state.pinnedNodeIds.includes(nodeIdToToggle)
        ? state.pinnedNodeIds.filter((id) => id !== nodeIdToToggle)
        : [...state.pinnedNodeIds, nodeIdToToggle],
    })),
  startEdit: (nodeIdToEdit) => {
    const node = get().nodesById[nodeIdToEdit];
    if (!node) return;
    set({
      draftFromNodeId: nodeIdToEdit,
      draft: node.content,
      activeLeafId: node.parent_id ?? get().rootNodeId,
    });
  },
  setActiveLeafId: (nodeIdToActivate) => {
    const leafId = get().getBranchLeafId(nodeIdToActivate);
    if (!leafId) return;
    set({ activeLeafId: leafId, draftFromNodeId: null });
  },
  getSiblings: (nodeIdToInspect) => {
    const state = get();
    const node = state.nodesById[nodeIdToInspect];
    if (!node?.parent_id) return [];
    const parent = state.nodesById[node.parent_id];
    if (!parent) return [];
    return parent.children_ids
      .map((id) => state.nodesById[id])
      .filter((candidate): candidate is ConversationNode => Boolean(candidate));
  },
  getBranchLeafId: (nodeIdToInspect) => {
    const state = get();
    let current = state.nodesById[nodeIdToInspect];
    if (!current) return null;
    while (current.children_ids.length > 0) {
      const nextId = current.children_ids[current.children_ids.length - 1];
      const next = state.nodesById[nextId];
      if (!next) break;
      current = next;
    }
    return current.id;
  },
  switchToBranch: (nodeIdToActivate) => {
    get().setActiveLeafId(nodeIdToActivate);
  },
  activePath: () => {
    const state = get();
    const path: ConversationNode[] = [];
    let current: string | null = state.activeLeafId;
    while (current) {
      const node: ConversationNode | undefined = state.nodesById[current];
      if (!node) break;
      if (node.id !== state.rootNodeId) path.push(node);
      current = node.parent_id;
    }
    return path.reverse();
  },
  dismissPlanNode: (nodeIdToDismiss) =>
    set((state) =>
      state.dismissedPlanNodeIds.includes(nodeIdToDismiss)
        ? state
        : { dismissedPlanNodeIds: [...state.dismissedPlanNodeIds, nodeIdToDismiss] },
    ),
  clearDismissedPlanNodes: () => set({ dismissedPlanNodeIds: [] }),
  setAgentScope: (agentId) => set({ _agentScope: agentId }),
  // ─── v3: conversation history actions ────────────────────────────────
  newConversation: () => {
    const now = new Date().toISOString();
    const state = get();
    // Flush current runtime into the outgoing conversation so switching
    // away and back preserves its data (Property P16).
    const merged = mergeRuntimeIntoConversations(state, now);
    const fresh = genesisConversation(now, generateConversationId);
    set({
      conversations: [...merged, fresh],
      currentConversationId: fresh.id,
      nodesById: fresh.nodesById,
      rootNodeId: fresh.rootNodeId,
      activeLeafId: fresh.activeLeafId,
      pinnedNodeIds: fresh.pinnedNodeIds,
      dismissedPlanNodeIds: fresh.dismissedPlanNodeIds,
      draft: fresh.draft,
      contextWindowTurns: fresh.contextWindowTurns,
      contextCompressions: fresh.contextCompressions,
      activeStream: null,
      draftFromNodeId: null,
    });
    return fresh.id;
  },
  setCurrentConversation: (id) => {
    const state = get();
    if (id === state.currentConversationId) return;
    const now = new Date().toISOString();
    const merged = mergeRuntimeIntoConversations(state, now);
    const target = merged.find((c) => c.id === id);
    if (target === undefined) return;
    set({
      conversations: merged,
      currentConversationId: target.id,
      nodesById: target.nodesById,
      rootNodeId: target.rootNodeId,
      activeLeafId: target.activeLeafId,
      pinnedNodeIds: target.pinnedNodeIds,
      dismissedPlanNodeIds: target.dismissedPlanNodeIds,
      draft: target.draft,
      contextWindowTurns: target.contextWindowTurns,
      contextCompressions: target.contextCompressions,
      activeStream: null,
      draftFromNodeId: null,
    });
  },
  deleteConversation: (id) => {
    const state = get();
    const remaining = state.conversations.filter((c) => c.id !== id);
    const now = new Date().toISOString();
    const isDeletingCurrent = state.currentConversationId === id;

    if (!isDeletingCurrent) {
      set({ conversations: remaining });
      return;
    }

    if (remaining.length === 0) {
      // Always keep at least one conversation (Req 4.6).
      const fresh = genesisConversation(now, generateConversationId);
      set({
        conversations: [fresh],
        currentConversationId: fresh.id,
        nodesById: fresh.nodesById,
        rootNodeId: fresh.rootNodeId,
        activeLeafId: fresh.activeLeafId,
        pinnedNodeIds: fresh.pinnedNodeIds,
        dismissedPlanNodeIds: fresh.dismissedPlanNodeIds,
        draft: fresh.draft,
        contextWindowTurns: fresh.contextWindowTurns,
        contextCompressions: fresh.contextCompressions,
        activeStream: null,
        draftFromNodeId: null,
      });
      return;
    }

    const sorted = sortConversationsByUpdatedAt(remaining);
    const next = sorted[0];
    set({
      conversations: remaining,
      currentConversationId: next.id,
      nodesById: next.nodesById,
      rootNodeId: next.rootNodeId,
      activeLeafId: next.activeLeafId,
      pinnedNodeIds: next.pinnedNodeIds,
      dismissedPlanNodeIds: next.dismissedPlanNodeIds,
      draft: next.draft,
      contextWindowTurns: next.contextWindowTurns,
      contextCompressions: next.contextCompressions,
      activeStream: null,
      draftFromNodeId: null,
    });
  },
  renameConversation: (id, title) =>
    set((state) => ({
      conversations: state.conversations.map((c) =>
        c.id === id ? { ...c, title, updated_at: new Date().toISOString() } : c,
      ),
    })),
  setHistoryPanelCollapsed: (collapsed) => set({ historyPanelCollapsed: collapsed }),
  setContextMaxTokens: (value) =>
    set({ contextMaxTokens: clampContextMaxTokens(value) }),
  setAutoCompressionRatio: (value) =>
    set({ autoCompressionRatio: clampAutoCompressionRatio(value) }),
  setContextCompression: (branchKey, summary) =>
    set((state) => ({
      contextCompressions: {
        ...state.contextCompressions,
        [branchKey]: summary,
      },
    })),
  clearContextCompression: (branchKey) =>
    set((state) => {
      const next = { ...state.contextCompressions };
      delete next[branchKey];
      return { contextCompressions: next };
    }),
  setActiveRunId: (runId) => set({ activeRunId: runId }),
  hydrateFromConversations: (snapshot) => {
    if (snapshot.conversations.length === 0) return;
    const target =
      snapshot.conversations.find((c) => c.id === snapshot.currentConversationId) ??
      snapshot.conversations[0];
    set({
      conversations: snapshot.conversations,
      currentConversationId: target.id,
      nodesById: target.nodesById,
      rootNodeId: target.rootNodeId,
      activeLeafId: target.activeLeafId,
      pinnedNodeIds: target.pinnedNodeIds,
      dismissedPlanNodeIds: target.dismissedPlanNodeIds,
      draft: target.draft,
      contextWindowTurns: target.contextWindowTurns,
      contextCompressions: target.contextCompressions ?? {},
      historyPanelCollapsed:
        snapshot.historyPanelCollapsed ?? get().historyPanelCollapsed,
      activeStream: null,
      draftFromNodeId: null,
    });
  },
}));

// ---------------------------------------------------------------------------
// v3 persistence: 300 ms debounced `conversations` snapshot write-through.
// ---------------------------------------------------------------------------

let saveTimer: ReturnType<typeof setTimeout> | null = null;
let lastCollapsedWritten: boolean | null = null;
let lastContextMaxTokensWritten: number | null = null;
let lastAutoCompressionRatioWritten: number | null = null;

useWorkspaceStore.subscribe((state) => {
  const scope = state._agentScope;
  if (scope === null) return;

  // Non-debounced: history panel collapsed state is a 1-byte toggle.
  if (lastCollapsedWritten !== state.historyPanelCollapsed) {
    lastCollapsedWritten = state.historyPanelCollapsed;
    saveHistoryPanelCollapsed(scope, state.historyPanelCollapsed);
  }

  if (saveTimer !== null) clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    saveTimer = null;
    const now = new Date().toISOString();
    const merged = mergeRuntimeIntoConversations(state, now);
    saveConversationsSnapshot(scope, {
      version: CONVERSATIONS_SCHEMA_VERSION,
      conversations: merged,
      currentConversationId: state.currentConversationId,
    });
    if (lastContextMaxTokensWritten !== state.contextMaxTokens) {
      lastContextMaxTokensWritten = state.contextMaxTokens;
      saveContextMaxTokens(scope, state.contextMaxTokens);
    }
    if (lastAutoCompressionRatioWritten !== state.autoCompressionRatio) {
      lastAutoCompressionRatioWritten = state.autoCompressionRatio;
      saveAutoCompressionRatio(scope, state.autoCompressionRatio);
    }
  }, 300);
});
