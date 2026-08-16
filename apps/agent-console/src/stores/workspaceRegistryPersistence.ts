import {
  getWorkspaceScopeId,
  legacyWorkspaceStorageKey,
  workspaceScopedStorageKey,
} from "../features/agents/lib/workspaceScope";
import type { WorkspaceRegistryEntry } from "./workspaceStore";
import { getWorkspacePersistenceStorage } from "../lib/workspace-persistence-storage";

export type WorkspaceRegistrySnapshot = {
  activeWorkspaceId: string;
  workspaceRegistry: Record<string, WorkspaceRegistryEntry>;
};

const WORKSPACE_REGISTRY_SCHEMA_VERSION = 1;

function storageKey(): string {
  return workspaceScopedStorageKey(getWorkspaceScopeId(), "v1", "registry");
}

function legacyStorageKey(): string {
  return legacyWorkspaceStorageKey("v1", "registry");
}

export function saveWorkspaceRegistrySnapshot(snapshot: WorkspaceRegistrySnapshot): boolean {
  const storage = getWorkspacePersistenceStorage();
  if (!storage) return false;
  try {
    const serialized = JSON.stringify({
      version: WORKSPACE_REGISTRY_SCHEMA_VERSION,
      ...snapshot,
    });
    storage.setItem(storageKey(), serialized);
    return true;
  } catch {
    return false;
  }
}

export function readWorkspaceRegistrySnapshot(): WorkspaceRegistrySnapshot | null {
  const storage = getWorkspacePersistenceStorage();
  if (!storage) return null;
  try {
    let raw = storage.getItem(storageKey());
    let usedLegacyKey = false;
    if (raw === null) {
      raw = storage.getItem(legacyStorageKey());
      usedLegacyKey = raw !== null;
    }
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return null;
    const candidate = parsed as {
      version?: unknown;
      activeWorkspaceId?: unknown;
      workspaceRegistry?: unknown;
    };
    if (candidate.version !== WORKSPACE_REGISTRY_SCHEMA_VERSION) return null;
    if (typeof candidate.activeWorkspaceId !== "string" || candidate.activeWorkspaceId.trim() === "") {
      return null;
    }
    if (
      typeof candidate.workspaceRegistry !== "object" ||
      candidate.workspaceRegistry === null ||
      Array.isArray(candidate.workspaceRegistry)
    ) {
      return null;
    }
    const workspaceRegistry = candidate.workspaceRegistry as Record<string, WorkspaceRegistryEntry>;
    if (usedLegacyKey) {
      try {
        storage.setItem(storageKey(), raw);
        storage.removeItem(legacyStorageKey());
      } catch {
        /* ignore migration failures */
      }
    }
    return {
      activeWorkspaceId: candidate.activeWorkspaceId.trim(),
      workspaceRegistry,
    };
  } catch {
    return null;
  }
}

export function clearWorkspaceRegistrySnapshot(): void {
  const storage = getWorkspacePersistenceStorage();
  if (!storage) return;
  try {
    storage.removeItem(storageKey());
    storage.removeItem(legacyStorageKey());
  } catch {
    /* ignore */
  }
}
