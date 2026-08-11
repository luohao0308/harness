// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";

import {
  getWorkspaceScopeId,
  legacyWorkspaceStorageKey,
  resetWorkspaceScopeCache,
  workspaceScopedStorageKey,
} from "../workspaceScope";

describe("workspaceScope", () => {
  beforeEach(() => {
    resetWorkspaceScopeCache();
    window.sessionStorage.clear();
    window.localStorage.clear();
    window.name = "";
    Object.defineProperty(window, "opener", {
      value: null,
      configurable: true,
    });
  });

  it("reuses the stored scope inside the same window", () => {
    const first = getWorkspaceScopeId();
    const second = getWorkspaceScopeId();
    expect(second).toBe(first);
    expect(window.sessionStorage.getItem("harness.workspace.scope-id")).toBe(first);
    expect(window.name).toBe(`harness-workspace-scope:${first}`);
  });

  it("keeps scoped keys separate from legacy shared keys", () => {
    const scopeId = getWorkspaceScopeId();
    expect(workspaceScopedStorageKey(scopeId, "v3", "default", "conversations")).toContain(
      scopeId,
    );
    expect(legacyWorkspaceStorageKey("v3", "default", "conversations")).toBe(
      "harness.workspace.v3.default.conversations",
    );
  });
});
