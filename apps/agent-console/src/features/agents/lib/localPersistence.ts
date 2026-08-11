/**
 * localStorage-backed persistence partitioned by `agentId` (Req 12 / P11).
 *
 * Behaviour summary (design.md §Persistence architecture, §Error Handling
 * → "Persistence failure"):
 * - Storage key: `harness.workspace.v2.${agentId}` (Req 12.1).
 * - `saveSnapshot` is TOTAL and best-effort: any write failure (quota,
 *   disabled storage, …) flips a module-local `skipWrites` flag, emits a
 *   single `console.warn`, and returns `false` so the caller keeps running
 *   in memory-only mode (Req 12.3).
 * - `loadSnapshot` is TOTAL and defensive: unparseable JSON, missing
 *   version, or mismatched schema all result in `null` (Req 12.4); any
 *   restored node whose `state === "streaming"` is rewritten to
 *   `"paused"` so streaming state never leaks across a refresh
 *   (Req 12.6 / Property P11).
 * - `clearSnapshot` swallows errors; callers treat it as fire-and-forget.
 */

import type { ConversationNode } from "../../../stores/workspaceStore";

import { getWorkspaceScopeId, legacyWorkspaceStorageKey, workspaceScopedStorageKey } from "./workspaceScope";
import { getWorkspacePersistenceStorage } from "../../../lib/workspace-persistence-storage";

export const PERSISTED_SCHEMA_VERSION = 1;

export type PersistedSnapshot = {
  version: 1;
  nodesById: Record<string, ConversationNode>;
  rootNodeId: string;
  activeLeafId: string;
  pinnedNodeIds: string[];
  contextWindowTurns: number;
  draft: string;
  dismissedPlanNodeIds: string[];
};

/**
 * Once a write to `localStorage` has failed, remember it and stop trying.
 * Further attempts would only emit identical warnings and burn cycles.
 * The flag is intentionally module-local (one tab == one process).
 */
let skipWrites = false;

function storageKey(agentId: string): string {
  return workspaceScopedStorageKey(getWorkspaceScopeId(), "v2", agentId);
}

function legacyStorageKey(agentId: string): string {
  return legacyWorkspaceStorageKey("v2", agentId);
}

export function saveSnapshot(
  agentId: string,
  snapshot: PersistedSnapshot,
): boolean {
  if (skipWrites) return false;
  const storage = getWorkspacePersistenceStorage();
  if (!storage) return false;
  try {
    storage.setItem(storageKey(agentId), JSON.stringify(snapshot));
    return true;
  } catch (err) {
    skipWrites = true;
    console.warn("[workspace] localStorage disabled", err);
    return false;
  }
}

function rewriteStreamingNodes(
  nodesById: Record<string, ConversationNode>,
): Record<string, ConversationNode> {
  const out: Record<string, ConversationNode> = {};
  for (const [id, node] of Object.entries(nodesById)) {
    out[id] =
      node.state === "streaming" ? { ...node, state: "paused" } : node;
  }
  return out;
}

function isStringArray(value: unknown): value is string[] {
  return (
    Array.isArray(value) && value.every((entry) => typeof entry === "string")
  );
}

function isNodesRecord(
  value: unknown,
): value is Record<string, ConversationNode> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }
  // Shallow structural check only; deeper validation is deliberately
  // avoided so we can restore future additive ConversationNode fields.
  for (const entry of Object.values(value)) {
    if (typeof entry !== "object" || entry === null) return false;
  }
  return true;
}

export function loadSnapshot(agentId: string): PersistedSnapshot | null {
  const storage = getWorkspacePersistenceStorage();
  if (!storage) return null;
  let raw: string | null;
  let usedLegacyKey = false;
  try {
    raw = storage.getItem(storageKey(agentId));
    if (raw === null) {
      raw = storage.getItem(legacyStorageKey(agentId));
      usedLegacyKey = raw !== null;
    }
  } catch {
    return null;
  }
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw) as unknown;
    if (typeof parsed !== "object" || parsed === null) return null;

    const candidate = parsed as {
      version?: unknown;
      nodesById?: unknown;
      rootNodeId?: unknown;
      activeLeafId?: unknown;
      pinnedNodeIds?: unknown;
      contextWindowTurns?: unknown;
      draft?: unknown;
      dismissedPlanNodeIds?: unknown;
    };

    if (candidate.version !== PERSISTED_SCHEMA_VERSION) return null;
    if (!isNodesRecord(candidate.nodesById)) return null;
    if (typeof candidate.rootNodeId !== "string") return null;
    if (typeof candidate.activeLeafId !== "string") return null;
    if (!isStringArray(candidate.pinnedNodeIds)) return null;
    if (typeof candidate.contextWindowTurns !== "number") return null;
    if (typeof candidate.draft !== "string") return null;
    if (!isStringArray(candidate.dismissedPlanNodeIds)) return null;

    if (usedLegacyKey) {
      try {
        storage.setItem(storageKey(agentId), raw);
        storage.removeItem(legacyStorageKey(agentId));
      } catch {
        /* ignore migration failures */
      }
    }

    return {
      version: PERSISTED_SCHEMA_VERSION,
      nodesById: rewriteStreamingNodes(candidate.nodesById),
      rootNodeId: candidate.rootNodeId,
      activeLeafId: candidate.activeLeafId,
      pinnedNodeIds: candidate.pinnedNodeIds,
      contextWindowTurns: candidate.contextWindowTurns,
      draft: candidate.draft,
      dismissedPlanNodeIds: candidate.dismissedPlanNodeIds,
    };
  } catch {
    return null;
  }
}

export function clearSnapshot(agentId: string): void {
  const storage = getWorkspacePersistenceStorage();
  if (!storage) return;
  try {
    storage.removeItem(storageKey(agentId));
    storage.removeItem(legacyStorageKey(agentId));
  } catch {
    /* ignore — persistence already disabled or storage missing */
  }
}
