import { create } from "zustand";

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
    cost_usd?: string;
    ttfb_ms?: number;
    duration_ms?: number;
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
  nodesById: Record<string, ConversationNode>;
  rootNodeId: string;
  activeLeafId: string;
  pinnedNodeIds: string[];
  contextWindowTurns: number;
  activeStream: WorkspaceStream | null;
  draftFromNodeId: string | null;
  draft: string;
  reset: () => void;
  setDraft: (draft: string) => void;
  setContextWindowTurns: (turns: number) => void;
  setActiveStream: (stream: WorkspaceStream | null) => void;
  appendNode: (node: Omit<ConversationNode, "id" | "children_ids" | "created_at">) => string;
  updateNode: (nodeId: string, patch: Partial<ConversationNode>) => void;
  appendContent: (nodeId: string, content: string) => void;
  appendArtifact: (nodeId: string, artifact: ConversationArtifact) => void;
  togglePinned: (nodeId: string) => void;
  startEdit: (nodeId: string) => void;
  activePath: () => ConversationNode[];
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

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  nodesById: { [rootNode.id]: rootNode },
  rootNodeId: rootNode.id,
  activeLeafId: rootNode.id,
  pinnedNodeIds: [],
  contextWindowTurns: 8,
  activeStream: null,
  draftFromNodeId: null,
  draft: "用 Agent Harness 的方式分析这个项目，并生成可执行 Plan。",
  reset: () =>
    set({
      nodesById: { [rootNode.id]: { ...rootNode, children_ids: [] } },
      activeLeafId: rootNode.id,
      pinnedNodeIds: [],
      activeStream: null,
      draftFromNodeId: null,
      draft: "",
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
}));
