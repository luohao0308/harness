/**
 * Conversation history primitives for Workspace v3 (Req 4, Property P15–P17).
 *
 * Pure module (no React imports). The store layer glues these primitives to
 * the `useWorkspaceStore` reducer and the page layer wires persistence.
 *
 * Exports:
 *   - `ConversationSummary` / `ConversationsSnapshot`
 *   - `CONVERSATIONS_SCHEMA_VERSION`
 *   - `sortConversationsByUpdatedAt(list)`  — stable descending sort by
 *     `updated_at`; equal timestamps keep input order (P15).
 *   - `computeConversationTitle(nodesById, fallback)` — first user message
 *     trimmed and sliced to 40 chars, else fallback.
 *   - `genesisConversation(now, idFactory)` — empty starter conversation
 *     matching the root-node schema from `workspaceStore`.
 *   - `legacyMigration(v2Snapshot, now, idFactory)` — produce a single
 *     `ConversationSummary` from a v2 `PersistedSnapshot`; streaming nodes
 *     are rewritten to `paused` to match Property P11 semantics.
 *   - `saveConversationsSnapshot` / `readConversationsSnapshot` /
 *     `clearConversationsSnapshot` — `localStorage` wrappers; share the same
 *     best-effort semantics as v2 `saveSnapshot`.
 *   - `generateConversationId()` — default id factory using
 *     `crypto.randomUUID()` when available, falling back to a Date-random
 *     composite otherwise.
 */

import type { ConversationNode } from "../../../stores/workspaceStore";
import type { ContextCompressionSummary } from "./contextCompression";
import type { PersistedSnapshot } from "./localPersistence";

export const CONVERSATIONS_SCHEMA_VERSION = 2 as const;

const DEFAULT_TITLE_ZH = "新对话";
const DEFAULT_TITLE_EN = "New conversation";
const IMPORTED_TITLE_EN = "Imported";

/** Same root node used by workspaceStore so rehydration is isomorphic. */
const ROOT_NODE_ID = "root";

export type ConversationSummary = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  nodesById: Record<string, ConversationNode>;
  rootNodeId: string;
  activeLeafId: string;
  pinnedNodeIds: string[];
  dismissedPlanNodeIds: string[];
  draft: string;
  contextWindowTurns: number;
  contextCompressions: Record<string, ContextCompressionSummary>;
};

export type ConversationsSnapshot = {
  version: typeof CONVERSATIONS_SCHEMA_VERSION;
  conversations: ConversationSummary[];
  currentConversationId: string;
};

/**
 * Decorated sort: attach original index so we can restore input order on
 * ties. Sorting by Date.parse is TOTAL (NaN timestamps fall back to 0).
 */
export function sortConversationsByUpdatedAt(
  list: ConversationSummary[],
): ConversationSummary[] {
  const decorated = list.map((c, i) => ({ c, i, ts: safeParseTime(c.updated_at) }));
  decorated.sort((a, b) => {
    if (b.ts !== a.ts) return b.ts - a.ts;
    return a.i - b.i; // stable: preserve input order for ties
  });
  return decorated.map((d) => d.c);
}

function safeParseTime(iso: string): number {
  if (typeof iso !== "string") return 0;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : 0;
}

/**
 * Pick a conversation title from `nodesById`:
 *   - First node with role === "user" in insertion order.
 *   - Trim + slice to 40 chars (code units; not grapheme-aware).
 *   - Fallback when no user node exists.
 */
export function computeConversationTitle(
  nodesById: Record<string, ConversationNode>,
  fallback: string,
): string {
  if (!isNodesRecord(nodesById)) return fallback;
  for (const node of Object.values(nodesById)) {
    if (node.role === "user") {
      const trimmed = node.content.trim();
      if (trimmed.length === 0) continue;
      return trimmed.slice(0, 40);
    }
  }
  return fallback;
}

function isNodesRecord(value: unknown): value is Record<string, ConversationNode> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Default id factory. Prefers `crypto.randomUUID()`; falls back to a
 * `Date.now() + Math.random()` composite so we still produce unique ids in
 * sandboxed environments without the Web Crypto API.
 */
export function generateConversationId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `conv-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * Build the initial empty conversation. Mirrors the root node shape used by
 * `useWorkspaceStore` so `hydrateFromConversations` can set state without
 * extra transformations.
 */
export function genesisConversation(
  now: string,
  idFactory: () => string = generateConversationId,
): ConversationSummary {
  const rootNode: ConversationNode = {
    id: ROOT_NODE_ID,
    parent_id: null,
    children_ids: [],
    role: "system",
    content: "Agent Workspace Pro root",
    state: "done",
    metadata: {},
    tool_calls: [],
    artifacts: [],
    created_at: now,
  };
  return {
    id: idFactory(),
    title: DEFAULT_TITLE_EN,
    created_at: now,
    updated_at: now,
    nodesById: { [ROOT_NODE_ID]: rootNode },
    rootNodeId: ROOT_NODE_ID,
    activeLeafId: ROOT_NODE_ID,
    pinnedNodeIds: [],
    dismissedPlanNodeIds: [],
    draft: "",
    contextWindowTurns: 8,
    contextCompressions: {},
  };
}

/**
 * Localised version of `genesisConversation` that picks the right default
 * title text for the current locale. Useful when the caller knows whether
 * the UI is currently showing zh or en.
 */
export function genesisConversationLocalized(
  now: string,
  locale: "zh-CN" | "en",
  idFactory: () => string = generateConversationId,
): ConversationSummary {
  const base = genesisConversation(now, idFactory);
  return {
    ...base,
    title: locale === "zh-CN" ? DEFAULT_TITLE_ZH : DEFAULT_TITLE_EN,
  };
}

/**
 * Translate a v2 snapshot into a single v3 `ConversationSummary`. Streaming
 * nodes are rewritten to `paused` to honour Property P11. Falls back to
 * `"Imported"` / `"Imported"` title if no user message exists.
 */
export function legacyMigration(
  v2: PersistedSnapshot,
  now: string,
  idFactory: () => string = generateConversationId,
): ConversationSummary {
  const rewritten = rewriteStreamingNodes(v2.nodesById);
  const title = computeConversationTitle(rewritten, IMPORTED_TITLE_EN);
  return {
    id: idFactory(),
    title,
    created_at: now,
    updated_at: now,
    nodesById: rewritten,
    rootNodeId: v2.rootNodeId,
    activeLeafId: v2.activeLeafId,
    pinnedNodeIds: [...v2.pinnedNodeIds],
    dismissedPlanNodeIds: [...v2.dismissedPlanNodeIds],
    draft: v2.draft,
    contextWindowTurns: v2.contextWindowTurns,
    contextCompressions: {},
  };
}

function rewriteStreamingNodes(
  nodesById: Record<string, ConversationNode>,
): Record<string, ConversationNode> {
  const out: Record<string, ConversationNode> = {};
  for (const [id, node] of Object.entries(nodesById)) {
    out[id] = node.state === "streaming" ? { ...node, state: "paused" } : node;
  }
  return out;
}

// ---------------------------------------------------------------------------
// localStorage integration
// ---------------------------------------------------------------------------

let skipWrites = false;

function storageKey(agentId: string): string {
  return `harness.workspace.v3.${agentId}.conversations`;
}

function hasLocalStorage(): boolean {
  return typeof localStorage !== "undefined";
}

export function saveConversationsSnapshot(
  agentId: string,
  snapshot: ConversationsSnapshot,
): boolean {
  if (skipWrites) return false;
  if (!hasLocalStorage()) return false;
  try {
    localStorage.setItem(storageKey(agentId), JSON.stringify(snapshot));
    return true;
  } catch (err) {
    skipWrites = true;
    console.warn("[workspace] v3 localStorage disabled", err);
    return false;
  }
}

export function readConversationsSnapshot(
  agentId: string,
): ConversationsSnapshot | null {
  if (!hasLocalStorage()) return null;
  let raw: string | null;
  try {
    raw = localStorage.getItem(storageKey(agentId));
  } catch {
    return null;
  }
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw) as unknown;
    if (typeof parsed !== "object" || parsed === null) return null;
    const candidate = parsed as {
      version?: unknown;
      conversations?: unknown;
      currentConversationId?: unknown;
    };
    if (candidate.version !== CONVERSATIONS_SCHEMA_VERSION) return null;
    if (!Array.isArray(candidate.conversations)) return null;
    if (typeof candidate.currentConversationId !== "string") return null;

    const conversations: ConversationSummary[] = [];
    for (const entry of candidate.conversations) {
      const summary = coerceConversationSummary(entry);
      if (summary === null) continue;
      conversations.push({
        ...summary,
        nodesById: rewriteStreamingNodes(summary.nodesById),
      });
    }
    if (conversations.length === 0) return null;

    // If the persisted `currentConversationId` is no longer present (e.g. the
    // user deleted it via devtools), fall back to the most recent entry.
    const hasCurrent = conversations.some(
      (c) => c.id === candidate.currentConversationId,
    );
    const current = hasCurrent
      ? (candidate.currentConversationId as string)
      : sortConversationsByUpdatedAt(conversations)[0].id;

    return {
      version: CONVERSATIONS_SCHEMA_VERSION,
      conversations,
      currentConversationId: current,
    };
  } catch {
    return null;
  }
}

export function clearConversationsSnapshot(agentId: string): void {
  if (!hasLocalStorage()) return;
  try {
    localStorage.removeItem(storageKey(agentId));
  } catch {
    /* ignore */
  }
}

function coerceConversationSummary(value: unknown): ConversationSummary | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  const c = value as {
    id?: unknown;
    title?: unknown;
    created_at?: unknown;
    updated_at?: unknown;
    nodesById?: unknown;
    rootNodeId?: unknown;
    activeLeafId?: unknown;
    pinnedNodeIds?: unknown;
    dismissedPlanNodeIds?: unknown;
    draft?: unknown;
    contextWindowTurns?: unknown;
    contextCompressions?: unknown;
  };
  if (typeof c.id !== "string" || c.id.length === 0) return null;
  if (typeof c.title !== "string") return null;
  if (typeof c.created_at !== "string") return null;
  if (typeof c.updated_at !== "string") return null;
  if (!isNodesRecord(c.nodesById)) return null;
  if (typeof c.rootNodeId !== "string") return null;
  if (typeof c.activeLeafId !== "string") return null;
  if (!isStringArray(c.pinnedNodeIds)) return null;
  if (!isStringArray(c.dismissedPlanNodeIds)) return null;
  if (typeof c.draft !== "string") return null;
  if (typeof c.contextWindowTurns !== "number") return null;
  return {
    id: c.id,
    title: c.title,
    created_at: c.created_at,
    updated_at: c.updated_at,
    nodesById: c.nodesById as Record<string, ConversationNode>,
    rootNodeId: c.rootNodeId,
    activeLeafId: c.activeLeafId,
    pinnedNodeIds: c.pinnedNodeIds,
    dismissedPlanNodeIds: c.dismissedPlanNodeIds,
    draft: c.draft,
    contextWindowTurns: c.contextWindowTurns,
    contextCompressions: isCompressionRecord(c.contextCompressions)
      ? c.contextCompressions
      : {},
  };
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((v) => typeof v === "string");
}

function isCompressionRecord(
  value: unknown,
): value is Record<string, ContextCompressionSummary> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// ---------------------------------------------------------------------------
// History panel collapsed persistence (separate small key)
// ---------------------------------------------------------------------------

function historyCollapsedKey(agentId: string): string {
  return `harness.workspace.v3.${agentId}.historyPanelCollapsed`;
}

export function saveHistoryPanelCollapsed(agentId: string, collapsed: boolean): void {
  if (!hasLocalStorage()) return;
  try {
    localStorage.setItem(historyCollapsedKey(agentId), collapsed ? "1" : "0");
  } catch {
    /* ignore */
  }
}

export function readHistoryPanelCollapsed(agentId: string): boolean | null {
  if (!hasLocalStorage()) return null;
  try {
    const raw = localStorage.getItem(historyCollapsedKey(agentId));
    if (raw === null) return null;
    return raw === "1";
  } catch {
    return null;
  }
}
