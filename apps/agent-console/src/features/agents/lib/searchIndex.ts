/**
 * Simple in-memory case-insensitive substring search over `nodesById`
 * (Req 13.1) powering the `Search_Overlay` Cmd/Ctrl+K palette.
 *
 * The implementation is intentionally naive (linear scan + single
 * `indexOf`) because the workspace in-memory graph for a single agent
 * stays under a few hundred nodes. The function is TOTAL — any shape of
 * `ConversationNode` (including missing `content` / unparseable
 * `created_at`) is handled without throwing.
 *
 * Contract:
 *
 * - `query.trim() === ""` → returns `[]`.
 * - Skip nodes whose `role === "system"`; system content is not part of
 *   the visible conversation and MUST not appear in search results.
 * - For each remaining node, locate the FIRST occurrence of the query via
 *   `content.toLowerCase().indexOf(query.toLowerCase())`. A node
 *   contributes at most one `SearchHit`.
 * - `snippet` is a ±40 character window around the match boundary.
 * - Results are ordered by `role` ascending (string comparison) and then
 *   by `created_at` descending (newest first). Unparseable timestamps are
 *   treated as epoch 0 so they sort to the end of their role group.
 */

import type { ConversationNode, ConversationRole } from "../../../stores/workspaceStore";

export type SearchHit = {
  nodeId: string;
  role: ConversationRole;
  /** ±40 char window around the first match within `node.content`. */
  snippet: string;
  /** Absolute start index of the match within `node.content`. */
  matchStart: number;
  /** Exclusive end index = `matchStart + query.length`. */
  matchEnd: number;
};

const SNIPPET_WINDOW = 40;

function parseCreatedAt(value: unknown): number {
  if (typeof value !== "string" || value.length === 0) return 0;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : 0;
}

export function searchIndex(
  nodesById: Record<string, ConversationNode>,
  query: string,
): SearchHit[] {
  if (query.trim() === "") return [];
  if (!nodesById || typeof nodesById !== "object") return [];

  const needle = query.toLowerCase();
  const queryLength = query.length;
  const hits: SearchHit[] = [];

  for (const node of Object.values(nodesById)) {
    if (!node || node.role === "system") continue;

    const content = typeof node.content === "string" ? node.content : "";
    if (content.length === 0) continue;

    const idx = content.toLowerCase().indexOf(needle);
    if (idx < 0) continue;

    const matchEnd = idx + queryLength;
    const snippetStart = Math.max(0, idx - SNIPPET_WINDOW);
    const snippetEnd = Math.min(content.length, matchEnd + SNIPPET_WINDOW);

    hits.push({
      nodeId: node.id,
      role: node.role,
      snippet: content.slice(snippetStart, snippetEnd),
      matchStart: idx,
      matchEnd,
    });
  }

  hits.sort((a, b) => {
    if (a.role < b.role) return -1;
    if (a.role > b.role) return 1;
    const aTime = parseCreatedAt(nodesById[a.nodeId]?.created_at);
    const bTime = parseCreatedAt(nodesById[b.nodeId]?.created_at);
    return bTime - aTime;
  });

  return hits;
}
