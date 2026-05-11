/**
 * SearchOverlay — Cmd+K-triggered conversation search portal (Req 13.1).
 *
 * Satisfies:
 *   - Req 13.1: full-screen case-insensitive substring search across every
 *     non-system `ConversationNode` in the active agent graph.
 *   - Req 14.2: `role="dialog"` + `aria-modal="true"` with focused input on
 *     open so the overlay is keyboard accessible.
 *   - Req 14.4: outside click and Escape both close the overlay (delegated
 *     to `useOutsideClick`, which also covers Req 6.1 / 14.4 symmetry).
 *
 * Design reference: design.md §New components → `SearchOverlay` and
 *   §Architecture → "Search / Shortcut / Export overlays".
 */

import type { ChangeEvent, JSX } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { useI18n } from "../../../lib/i18n";
import type { ConversationNode } from "../../../stores/workspaceStore";
import { useOutsideClick } from "../hooks/useOutsideClick";
import { searchIndex } from "../lib/searchIndex";

const MAX_HITS = 20;

export type SearchOverlayProps = {
  open: boolean;
  onClose: () => void;
  nodesById: Record<string, ConversationNode>;
  /** Parent: `setActiveLeafId(leafIdOf(nodeId))` + scroll + highlight. */
  onJumpToNode: (nodeId: string) => void;
};

export function SearchOverlay({
  open,
  onClose,
  nodesById,
  onJumpToNode,
}: SearchOverlayProps): JSX.Element | null {
  const { text } = useI18n();
  const dialogRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");

  // Shared Esc + outside-click close semantics (Req 14.4 / 6.1).
  useOutsideClick(dialogRef, onClose, open);

  // Reset the input every time the overlay is re-opened so the user starts
  // from an empty query, and auto-focus the input for immediate typing.
  useEffect(() => {
    if (open === false) return;
    setQuery("");
    // Focus after paint so React has mounted the `<input>` in the portal.
    const id = window.requestAnimationFrame(() => {
      inputRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(id);
  }, [open]);

  const hits = useMemo(() => searchIndex(nodesById, query), [nodesById, query]);

  if (open === false) return null;
  if (typeof document === "undefined") return null;

  const visibleHits = hits.slice(0, MAX_HITS);
  const trimmed = query.trim();

  const handleChange = (event: ChangeEvent<HTMLInputElement>): void => {
    setQuery(event.target.value);
  };

  const handleHitClick = (nodeId: string): void => {
    onJumpToNode(nodeId);
    onClose();
  };

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label={text("搜索会话", "Search conversation")}
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 pt-[10vh]"
      onClick={onClose}
    >
      <div
        ref={dialogRef}
        onClick={(event) => event.stopPropagation()}
        className="w-[640px] max-w-[90vw] rounded-2xl bg-white shadow-xl p-4"
      >
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={handleChange}
          placeholder={text("搜索消息…", "Search messages…")}
          aria-label={text("搜索输入框", "Search input")}
          className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-slate-400"
        />

        <div className="mt-3 max-h-[50vh] overflow-y-auto">
          {trimmed.length === 0 ? (
            <p className="px-2 py-6 text-center text-xs text-slate-500">
              {text("输入关键词开始搜索", "Type a keyword to start searching")}
            </p>
          ) : visibleHits.length === 0 ? (
            <p className="px-2 py-6 text-center text-xs text-slate-500">
              {text("没有匹配的消息", "No matching messages")}
            </p>
          ) : (
            <ul className="space-y-1">
              {visibleHits.map((hit) => (
                <li key={hit.nodeId}>
                  <button
                    type="button"
                    onClick={() => handleHitClick(hit.nodeId)}
                    className="flex w-full items-start gap-2 rounded-lg px-2 py-2 text-left hover:bg-slate-50 focus:bg-slate-50 focus:outline-none"
                  >
                    <span className="shrink-0 rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[11px] uppercase tracking-wide text-slate-600">
                      {hit.role}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-xs text-slate-700">
                      {hit.snippet}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
