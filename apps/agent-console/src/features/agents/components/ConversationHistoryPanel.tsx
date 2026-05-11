/**
 * ConversationHistoryPanel — left rail listing all conversations for the
 * current agent (v3 / Req 4).
 *
 * Pure presentational — the parent (`AgentWorkspacePage`) owns the store
 * and wires every callback. Collapsed mode renders a narrow strip with a
 * single expand-button (so the panel can be re-opened).
 *
 * Accessibility:
 *   - Every entry is a real `<button>` with `aria-current="page"` on the
 *     active item.
 *   - Delete buttons are icon-only with bilingual `aria-label`.
 *   - Focus rings via `focus-visible` (Req 7.2).
 */

import type { JSX } from "react";
import { useMemo } from "react";
import { ChevronLeft, ChevronRight, MessageSquarePlus, Trash2 } from "lucide-react";

import { useI18n } from "../../../lib/i18n";
import { cn } from "../../../lib/utils";
import type { ConversationSummary } from "../lib/conversationHistory";
import { sortConversationsByUpdatedAt } from "../lib/conversationHistory";
import { formatRelativeTime } from "../lib/relativeTime";

export type ConversationHistoryPanelProps = {
  collapsed: boolean;
  conversations: ConversationSummary[];
  currentConversationId: string;
  onNewConversation: () => void;
  onSelectConversation: (id: string) => void;
  onDeleteConversation: (id: string) => void;
  onToggleCollapsed: () => void;
};

export function ConversationHistoryPanel({
  collapsed,
  conversations,
  currentConversationId,
  onNewConversation,
  onSelectConversation,
  onDeleteConversation,
  onToggleCollapsed,
}: ConversationHistoryPanelProps): JSX.Element {
  const { text, isChinese } = useI18n();
  const sorted = useMemo(
    () => sortConversationsByUpdatedAt(conversations),
    [conversations],
  );
  const locale = isChinese ? "zh-CN" : "en";
  const nowMs = Date.now();

  const toggleLabel = collapsed
    ? text("展开历史对话", "Expand history")
    : text("收起历史对话", "Collapse history");

  if (collapsed) {
    return (
      <aside
        aria-label={text("历史对话", "Conversation history")}
        className="flex w-10 shrink-0 flex-col items-center gap-2 border-r border-slate-200 bg-white py-2"
      >
        <button
          type="button"
          onClick={onToggleCollapsed}
          aria-label={toggleLabel}
          title={toggleLabel}
          className="rounded-full p-1.5 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
        >
          <ChevronRight aria-hidden="true" className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={onNewConversation}
          aria-label={text("新建对话", "New conversation")}
          title={text("新建对话", "New conversation")}
          className="rounded-full p-1.5 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
        >
          <MessageSquarePlus aria-hidden="true" className="h-4 w-4" />
        </button>
      </aside>
    );
  }

  return (
    <aside
      aria-label={text("历史对话", "Conversation history")}
      className="flex w-[260px] shrink-0 flex-col border-r border-slate-200 bg-white"
    >
      <header className="flex items-center justify-between gap-2 border-b border-slate-200 px-3 py-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          {text("历史对话", "History")}
        </span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onNewConversation}
            aria-label={text("新建对话", "New conversation")}
            title={text("新建对话", "New conversation")}
            className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
          >
            <MessageSquarePlus aria-hidden="true" className="h-3 w-3" />
            <span>{text("新建", "New")}</span>
          </button>
          <button
            type="button"
            onClick={onToggleCollapsed}
            aria-label={toggleLabel}
            title={toggleLabel}
            className="rounded-full p-1.5 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
          >
            <ChevronLeft aria-hidden="true" className="h-4 w-4" />
          </button>
        </div>
      </header>

      {sorted.length === 0 ? (
        <p className="px-3 py-6 text-center text-xs text-slate-500">
          {text("暂无历史对话", "No conversations yet")}
        </p>
      ) : (
        <ul className="flex flex-1 flex-col gap-0.5 overflow-y-auto p-2">
          {sorted.map((c) => {
            const active = c.id === currentConversationId;
            const updatedMs = Date.parse(c.updated_at);
            const title = c.title.length > 0
              ? c.title
              : text("新对话", "New conversation");
            const updatedLabel = Number.isFinite(updatedMs)
              ? formatRelativeTime(updatedMs, nowMs, locale)
              : "";
            return (
              <li key={c.id}>
                <div
                  className={cn(
                    "group flex items-center gap-1 rounded-xl transition-colors",
                    active
                      ? "bg-slate-100 ring-1 ring-slate-300"
                      : "hover:bg-slate-50",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => onSelectConversation(c.id)}
                    aria-current={active ? "page" : undefined}
                    className="flex min-w-0 flex-1 items-center justify-between gap-2 rounded-xl px-2 py-1.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
                  >
                    <span className="truncate text-xs text-slate-800">{title}</span>
                    <span className="shrink-0 text-[10px] text-slate-400">
                      {updatedLabel}
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      onDeleteConversation(c.id);
                    }}
                    aria-label={text("删除对话", "Delete conversation")}
                    title={text("删除对话", "Delete conversation")}
                    className="rounded-full p-1 text-slate-400 opacity-0 transition-opacity hover:text-red-500 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 group-hover:opacity-100"
                  >
                    <Trash2 aria-hidden="true" className="h-3.5 w-3.5" />
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
