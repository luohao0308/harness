// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";

import type { ConversationNode } from "../../../../stores/workspaceStore";
import { readWorkspaceRegistrySnapshot, saveWorkspaceRegistrySnapshot } from "../../../../stores/workspaceRegistryPersistence";
import {
  readAutoCompressionRatio,
  readContextMaxTokens,
  saveAutoCompressionRatio,
  saveContextMaxTokens,
} from "../contextTokens";
import {
  clearConversationsSnapshot,
  genesisConversation,
  readConversationsSnapshot,
  saveConversationsSnapshot,
} from "../conversationHistory";
import { loadSnapshot, saveSnapshot } from "../localPersistence";
import {
  getWorkspaceScopeId,
  legacyWorkspaceStorageKey,
  resetWorkspaceScopeCache,
  workspaceScopedStorageKey,
} from "../workspaceScope";

const rootNode: ConversationNode = {
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

beforeEach(() => {
  delete window.desktopApi;
  resetWorkspaceScopeCache();
  window.sessionStorage.clear();
  window.localStorage.clear();
  window.name = "";
  Object.defineProperty(window, "opener", {
    value: null,
    configurable: true,
  });
});

describe("workspace persistence migration", () => {
  it("writes workspace registry only to the scoped key and migrates legacy reads", () => {
    window.name = "harness-workspace-scope:scope-a";
    const scopeId = getWorkspaceScopeId();
    const snapshot = {
      activeWorkspaceId: "scope-a::default",
      workspaceRegistry: {
        "scope-a::default": {
          agentId: "default",
          config: {
            contextMaxTokens: 16000,
            autoCompressionRatio: 0.5,
            historyPanelCollapsed: true,
            localFileRootPath: null,
          },
        },
      },
    };

    expect(saveWorkspaceRegistrySnapshot(snapshot)).toBe(true);
    expect(
      window.localStorage.getItem(workspaceScopedStorageKey(scopeId, "v1", "registry")),
    ).toBeTruthy();
    expect(window.localStorage.getItem(legacyWorkspaceStorageKey("v1", "registry"))).toBeNull();

    window.localStorage.clear();
    window.localStorage.setItem(legacyWorkspaceStorageKey("v1", "registry"), JSON.stringify({
      version: 1,
      ...snapshot,
    }));
    const restored = readWorkspaceRegistrySnapshot();
    expect(restored?.activeWorkspaceId).toBe("scope-a::default");
    expect(window.localStorage.getItem(workspaceScopedStorageKey(scopeId, "v1", "registry"))).toBeTruthy();
    expect(window.localStorage.getItem(legacyWorkspaceStorageKey("v1", "registry"))).toBeNull();
  });

  it("writes conversation snapshots only to the scoped key and migrates legacy reads", () => {
    window.name = "harness-workspace-scope:scope-a";
    const scopeId = getWorkspaceScopeId();
    const snapshot = {
      version: 2 as const,
      conversations: [genesisConversation("2025-05-09T00:00:00.000Z", () => "conv-a")],
      currentConversationId: "conv-a",
    };

    expect(saveConversationsSnapshot("default", snapshot)).toBe(true);
    expect(
      window.localStorage.getItem(workspaceScopedStorageKey(scopeId, "v3", "default", "conversations")),
    ).toBeTruthy();
    expect(
      window.localStorage.getItem(legacyWorkspaceStorageKey("v3", "default", "conversations")),
    ).toBeNull();

    window.localStorage.clear();
    window.localStorage.setItem(
      legacyWorkspaceStorageKey("v3", "default", "conversations"),
      JSON.stringify(snapshot),
    );
    const restored = readConversationsSnapshot("default");
    expect(restored?.currentConversationId).toBe("conv-a");
    expect(
      window.localStorage.getItem(workspaceScopedStorageKey(scopeId, "v3", "default", "conversations")),
    ).toBeTruthy();
    expect(
      window.localStorage.getItem(legacyWorkspaceStorageKey("v3", "default", "conversations")),
    ).toBeNull();
  });

  it("writes token budget settings only to the scoped key and migrates legacy reads", () => {
    window.name = "harness-workspace-scope:scope-a";
    const scopeId = getWorkspaceScopeId();

    expect(saveContextMaxTokens("default", 16000)).toBe(true);
    expect(saveAutoCompressionRatio("default", 0.6)).toBe(true);
    expect(
      window.localStorage.getItem(workspaceScopedStorageKey(scopeId, "v5", "default", "contextMaxTokens")),
    ).toBe("16000");
    expect(
      window.localStorage.getItem(workspaceScopedStorageKey(scopeId, "v5", "default", "autoCompressionRatio")),
    ).toBe("0.6");

    window.localStorage.clear();
    window.localStorage.setItem(legacyWorkspaceStorageKey("v5", "default", "contextMaxTokens"), "16000");
    window.localStorage.setItem(legacyWorkspaceStorageKey("v5", "default", "autoCompressionRatio"), "0.6");
    expect(readContextMaxTokens("default")).toBe(16000);
    expect(readAutoCompressionRatio("default")).toBe(0.6);
    expect(
      window.localStorage.getItem(workspaceScopedStorageKey(scopeId, "v5", "default", "contextMaxTokens")),
    ).toBe("16000");
    expect(
      window.localStorage.getItem(workspaceScopedStorageKey(scopeId, "v5", "default", "autoCompressionRatio")),
    ).toBe("0.6");
    expect(window.localStorage.getItem(legacyWorkspaceStorageKey("v5", "default", "contextMaxTokens"))).toBeNull();
    expect(window.localStorage.getItem(legacyWorkspaceStorageKey("v5", "default", "autoCompressionRatio"))).toBeNull();
  });

  it("writes v2 snapshots only to the scoped key and migrates legacy reads", () => {
    window.name = "harness-workspace-scope:scope-a";
    const scopeId = getWorkspaceScopeId();
    const snapshot = {
      version: 1 as const,
      nodesById: {
        root: rootNode,
      },
      rootNodeId: "root",
      activeLeafId: "root",
      pinnedNodeIds: [],
      contextWindowTurns: 8,
      draft: "",
      dismissedPlanNodeIds: [],
    };

    expect(saveSnapshot("default", snapshot)).toBe(true);
    expect(window.localStorage.getItem(workspaceScopedStorageKey(scopeId, "v2", "default"))).toBeTruthy();
    expect(window.localStorage.getItem(legacyWorkspaceStorageKey("v2", "default"))).toBeNull();

    window.localStorage.clear();
    window.localStorage.setItem(legacyWorkspaceStorageKey("v2", "default"), JSON.stringify(snapshot));
    expect(loadSnapshot("default")?.rootNodeId).toBe("root");
    expect(window.localStorage.getItem(workspaceScopedStorageKey(scopeId, "v2", "default"))).toBeTruthy();
    expect(window.localStorage.getItem(legacyWorkspaceStorageKey("v2", "default"))).toBeNull();
  });

  it("persists workspace registry file-root config through the scoped registry snapshot", () => {
    window.name = "harness-workspace-scope:scope-a";
    const scopeId = getWorkspaceScopeId();
    const snapshot = {
      activeWorkspaceId: "default",
      workspaceRegistry: {
        default: {
          agentId: "default",
          config: {
            contextMaxTokens: 16000,
            autoCompressionRatio: 0.75,
            historyPanelCollapsed: false,
            localFileRootPath: "/workspace/default",
          },
        },
      },
    };

    expect(saveWorkspaceRegistrySnapshot(snapshot)).toBe(true);
    expect(
      window.localStorage.getItem(workspaceScopedStorageKey(scopeId, "v1", "registry")),
    ).toContain("/workspace/default");

    window.localStorage.clear();
    window.localStorage.setItem(
      legacyWorkspaceStorageKey("v1", "registry"),
      JSON.stringify({ version: 1, ...snapshot }),
    );
    const restored = readWorkspaceRegistrySnapshot();
    expect(restored?.workspaceRegistry.default.config.localFileRootPath).toBe("/workspace/default");
  });

  it("uses the stable desktop profile bridge instead of origin-scoped localStorage", () => {
    const values = new Map<string, string>();
    window.desktopApi = {
      storage: {
        getItem: (key) => values.get(key) ?? null,
        setItem: (key, value) => {
          values.set(key, value);
          return true;
        },
        removeItem: (key) => values.delete(key),
      },
    };
    resetWorkspaceScopeCache();
    const snapshot = {
      activeWorkspaceId: "default",
      workspaceRegistry: {
        default: {
          agentId: "default",
          config: {
            contextMaxTokens: 16000,
            autoCompressionRatio: 0.75,
            historyPanelCollapsed: false,
            localFileRootPath: "/workspace/default",
          },
        },
      },
    };

    expect(getWorkspaceScopeId()).toBe("desktop");
    expect(saveWorkspaceRegistrySnapshot(snapshot)).toBe(true);
    expect(values.get("harness.workspace.desktop.v1.registry")).toContain("/workspace/default");
    expect(window.localStorage.length).toBe(0);
    expect(readWorkspaceRegistrySnapshot()?.workspaceRegistry.default.config.localFileRootPath).toBe(
      "/workspace/default",
    );
  });
});
