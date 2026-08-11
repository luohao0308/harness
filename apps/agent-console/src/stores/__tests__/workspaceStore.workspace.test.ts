// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";

import { useWorkspaceStore } from "../workspaceStore";
import { resetWorkspaceScopeCache } from "../../features/agents/lib/workspaceScope";

describe("workspace store workspace registry", () => {
  beforeEach(() => {
    resetWorkspaceScopeCache();
    window.sessionStorage.clear();
    window.localStorage.clear();
    Object.defineProperty(window, "opener", {
      value: null,
      configurable: true,
    });
    useWorkspaceStore.getState().reset();
  });

  it("registers and switches independent workspace config state", () => {
    const store = useWorkspaceStore.getState();
    store.registerWorkspace("ws-a", "default");
    store.registerWorkspace("ws-b", "default");

    store.updateWorkspaceConfig("ws-a", {
      contextMaxTokens: 16000,
      autoCompressionRatio: 0.4,
      historyPanelCollapsed: true,
    });

    store.updateWorkspaceConfig("ws-b", {
      contextMaxTokens: 32000,
      autoCompressionRatio: 0.9,
      historyPanelCollapsed: false,
    });

    store.switchWorkspace("ws-a");
    expect(useWorkspaceStore.getState().contextMaxTokens).toBe(16000);
    expect(useWorkspaceStore.getState().autoCompressionRatio).toBe(0.4);
    expect(useWorkspaceStore.getState().historyPanelCollapsed).toBe(true);

    store.switchWorkspace("ws-b");
    expect(useWorkspaceStore.getState().contextMaxTokens).toBe(32000);
    expect(useWorkspaceStore.getState().autoCompressionRatio).toBe(0.9);
    expect(useWorkspaceStore.getState().historyPanelCollapsed).toBe(false);
  });

  it("keeps the active workspace config in sync when updated", () => {
    const store = useWorkspaceStore.getState();
    store.registerWorkspace("ws-active", "default");
    store.switchWorkspace("ws-active");

    store.updateWorkspaceConfig("ws-active", {
      contextMaxTokens: 64000,
      autoCompressionRatio: 0.25,
      historyPanelCollapsed: true,
    });

    expect(useWorkspaceStore.getState().contextMaxTokens).toBe(64000);
    expect(useWorkspaceStore.getState().autoCompressionRatio).toBe(0.25);
    expect(useWorkspaceStore.getState().historyPanelCollapsed).toBe(true);
  });

  it("resets only the conversation runtime and keeps the workspace registry intact", () => {
    const store = useWorkspaceStore.getState();
    store.registerWorkspace("ws-keep", "default");
    store.updateWorkspaceConfig("ws-keep", {
      contextMaxTokens: 64000,
      autoCompressionRatio: 0.65,
      historyPanelCollapsed: true,
    });
    store.switchWorkspace("ws-keep");

    store.resetConversationRuntime();

    expect(useWorkspaceStore.getState().activeWorkspaceId).toBe("ws-keep");
    expect(useWorkspaceStore.getState().workspaceRegistry["ws-keep"].config.contextMaxTokens).toBe(
      64000,
    );
    expect(
      useWorkspaceStore.getState().workspaceRegistry["ws-keep"].config.historyPanelCollapsed,
    ).toBe(true);
    expect(useWorkspaceStore.getState().rootNodeId).toBe("root");
    expect(useWorkspaceStore.getState().activeLeafId).toBe("root");
    expect(useWorkspaceStore.getState().contextMaxTokens).toBe(64000);
  });

  it("keeps workspace configs isolated across window scopes for the same agent", () => {
    const originalName = window.name;
    window.name = "harness-workspace-scope:scope-a";
    resetWorkspaceScopeCache();

    const store = useWorkspaceStore.getState();
    store.registerWorkspace("scope-a::default", "default");
    store.switchWorkspace("scope-a::default");
    store.updateWorkspaceConfig("scope-a::default", {
      contextMaxTokens: 16000,
      autoCompressionRatio: 0.5,
      historyPanelCollapsed: true,
    });

    window.name = "harness-workspace-scope:scope-b";
    resetWorkspaceScopeCache();
    store.registerWorkspace("scope-b::default", "default");
    store.switchWorkspace("scope-b::default");

    expect(useWorkspaceStore.getState().contextMaxTokens).toBe(258000);
    expect(useWorkspaceStore.getState().autoCompressionRatio).toBe(0.8);
    expect(useWorkspaceStore.getState().historyPanelCollapsed).toBe(false);

    window.name = originalName;
  });
});
