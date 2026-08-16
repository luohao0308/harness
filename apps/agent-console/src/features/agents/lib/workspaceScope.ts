const WORKSPACE_SCOPE_STORAGE_KEY = "harness.workspace.scope-id";
const WORKSPACE_SCOPE_WINDOW_NAME_PREFIX = "harness-workspace-scope:";

let inMemoryWorkspaceScopeId: string | null = null;

function randomWorkspaceScopeId(): string {
  const cryptoApi = typeof crypto !== "undefined" ? crypto : null;
  if (cryptoApi && typeof cryptoApi.randomUUID === "function") {
    return `scope-${cryptoApi.randomUUID()}`;
  }
  return `scope-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function getWorkspaceScopeId(): string {
  if (inMemoryWorkspaceScopeId !== null) return inMemoryWorkspaceScopeId;
  if (typeof window !== "undefined" && window.desktopApi?.storage) {
    inMemoryWorkspaceScopeId = "desktop";
    return inMemoryWorkspaceScopeId;
  }
  if (typeof window === "undefined" || typeof sessionStorage === "undefined") {
    inMemoryWorkspaceScopeId = randomWorkspaceScopeId();
    return inMemoryWorkspaceScopeId;
  }

  try {
    const existingWindowName = typeof window.name === "string" ? window.name.trim() : "";
    if (existingWindowName.startsWith(WORKSPACE_SCOPE_WINDOW_NAME_PREFIX)) {
      const scopeId = existingWindowName.slice(WORKSPACE_SCOPE_WINDOW_NAME_PREFIX.length).trim();
      if (scopeId) {
        window.sessionStorage.setItem(WORKSPACE_SCOPE_STORAGE_KEY, scopeId);
        inMemoryWorkspaceScopeId = scopeId;
        return scopeId;
      }
    }

    const stored = window.sessionStorage.getItem(WORKSPACE_SCOPE_STORAGE_KEY);
    const clonedFromOpener = window.opener !== null;
    if (stored && stored.trim() && !clonedFromOpener) {
      const scopeId = stored.trim();
      window.name = `${WORKSPACE_SCOPE_WINDOW_NAME_PREFIX}${scopeId}`;
      inMemoryWorkspaceScopeId = scopeId;
      return scopeId;
    }

    const generated = randomWorkspaceScopeId();
    window.sessionStorage.setItem(WORKSPACE_SCOPE_STORAGE_KEY, generated);
    window.name = `${WORKSPACE_SCOPE_WINDOW_NAME_PREFIX}${generated}`;
    inMemoryWorkspaceScopeId = generated;
    return generated;
  } catch {
    inMemoryWorkspaceScopeId = randomWorkspaceScopeId();
    return inMemoryWorkspaceScopeId;
  }
}

export function resetWorkspaceScopeCache(): void {
  inMemoryWorkspaceScopeId = null;
}

export function workspaceScopedStorageKey(scopeId: string, ...parts: string[]): string {
  return ["harness.workspace", scopeId, ...parts].join(".");
}

export function legacyWorkspaceStorageKey(...parts: string[]): string {
  return ["harness.workspace", ...parts].join(".");
}

export function workspaceInstanceId(agentId: string): string {
  return `${getWorkspaceScopeId()}::${agentId}`;
}
