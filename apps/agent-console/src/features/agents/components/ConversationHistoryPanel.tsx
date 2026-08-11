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
import { ChevronLeft, ChevronRight, FolderOpen, MessageSquarePlus, Settings2, ShieldCheck, Terminal, Trash2, Users } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

import { isDesktopRuntime } from "../../../lib/desktop-bridge";
import { useI18n } from "../../../lib/i18n";
import { cn } from "../../../lib/utils";
import type { ConversationSummary } from "../lib/conversationHistory";
import { sortConversationsByUpdatedAt } from "../lib/conversationHistory";
import { formatRelativeTime } from "../lib/relativeTime";

export type ConversationHistoryPanelProps = {
  collapsed: boolean;
  conversations: ConversationSummary[];
  currentConversationId: string;
  groupLabelForConversation?: (conversation: ConversationSummary) => string;
  onNewConversation: () => void;
  onSelectConversation: (id: string) => void;
  onDeleteConversation: (id: string) => void;
  onToggleCollapsed: () => void;
};

export function ConversationHistoryPanel({
  collapsed,
  conversations,
  currentConversationId,
  groupLabelForConversation,
  onNewConversation,
  onSelectConversation,
  onDeleteConversation,
  onToggleCollapsed,
}: ConversationHistoryPanelProps): JSX.Element {
  const { text, isChinese } = useI18n();
  const location = useLocation();
  const grouped = useMemo(
    () => groupConversations(
      sortConversationsByUpdatedAt(conversations),
      groupLabelForConversation ?? (() => text("当前智能体", "Current Agent")),
    ),
    [conversations, groupLabelForConversation, text],
  );
  const locale = isChinese ? "zh-CN" : "en";
  const nowMs = Date.now();
  const desktop = isDesktopRuntime();
  const desktopFilesPath = desktopPanelPath(location.pathname, location.search, "files");
  const desktopApprovalsPath = desktopPanelPath(location.pathname, location.search, "approvals");

  const toggleLabel = collapsed
    ? text("展开历史对话", "Expand history")
    : text("收起历史对话", "Collapse history");

  if (collapsed) {
    return (
      <aside
        aria-label={text("历史对话", "Conversation history")}
        className="flex w-12 shrink-0 flex-col items-center gap-2 border-r border-slate-200 bg-[#f7f7f8] py-3"
      >
        <button
          type="button"
          onClick={onToggleCollapsed}
          aria-label={toggleLabel}
          title={toggleLabel}
          className="rounded-lg p-2 text-slate-600 transition-colors hover:bg-slate-200/70 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
        >
          <ChevronRight aria-hidden="true" className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={onNewConversation}
          aria-label={text("新建对话", "New conversation")}
          title={text("新建对话", "New conversation")}
          className="rounded-lg p-2 text-slate-600 transition-colors hover:bg-slate-200/70 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
        >
          <MessageSquarePlus aria-hidden="true" className="h-4 w-4" />
        </button>
        {desktop ? (
          <div className="mt-auto flex flex-col gap-1">
            <DesktopUtilityLink to="/teams" label={text("团队", "Teams")} icon={<Users className="h-4 w-4" />} />
            <DesktopUtilityLink to="/terminal" label={text("终端", "Terminal")} icon={<Terminal className="h-4 w-4" />} />
            <DesktopUtilityLink to={desktopFilesPath} label={text("文件", "Files")} icon={<FolderOpen className="h-4 w-4" />} />
            <DesktopUtilityLink to={desktopApprovalsPath} label={text("审批", "Approvals")} icon={<ShieldCheck className="h-4 w-4" />} />
            <DesktopUtilityLink to="/desktop" label={text("设置", "Settings")} icon={<Settings2 className="h-4 w-4" />} />
          </div>
        ) : null}
      </aside>
    );
  }

  return (
    <aside
      aria-label={text("历史对话", "Conversation history")}
      className="flex w-[280px] shrink-0 flex-col border-r border-slate-200 bg-[#f7f7f8] max-md:absolute max-md:inset-y-0 max-md:left-0 max-md:z-30 max-md:shadow-none"
    >
      {desktop ? (
        <header className="px-3 pb-2 pt-3">
          <div className="flex h-8 items-center gap-2 px-1">
            <span className="flex h-6 w-6 items-center justify-center rounded-md bg-slate-900 font-mono text-xs font-semibold text-white">
              H
            </span>
            <span className="text-sm font-semibold text-slate-900">Harness</span>
            <button
              type="button"
              onClick={onToggleCollapsed}
              aria-label={toggleLabel}
              title={toggleLabel}
              className="ml-auto rounded-md p-1.5 text-slate-500 transition-colors hover:bg-slate-200/70 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
            >
              <ChevronLeft aria-hidden="true" className="h-4 w-4" />
            </button>
          </div>
          <button
            type="button"
            onClick={onNewConversation}
            aria-label={text("新建任务", "New task")}
            className="mt-3 flex h-9 w-full items-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-sm font-medium text-slate-800 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
          >
            <MessageSquarePlus aria-hidden="true" className="h-4 w-4" />
            <span>{text("新建任务", "New task")}</span>
          </button>
          <div className="px-1 pb-1 pt-5 text-xs font-medium text-slate-500">
            {text("任务", "Tasks")}
          </div>
        </header>
      ) : (
        <header className="flex items-center justify-between gap-2 px-2 py-3">
          <span className="px-2 text-sm font-semibold text-slate-900">
            {text("历史对话", "History")}
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={onNewConversation}
              aria-label={text("新建对话", "New conversation")}
              title={text("新建对话", "New conversation")}
              className="inline-flex h-9 items-center gap-2 rounded-lg px-2.5 text-sm text-slate-800 transition-colors hover:bg-slate-200/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
            >
              <MessageSquarePlus aria-hidden="true" className="h-4 w-4" />
              <span>{text("新聊天", "New chat")}</span>
            </button>
            <button
              type="button"
              onClick={onToggleCollapsed}
              aria-label={toggleLabel}
              title={toggleLabel}
              className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-200/70 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
            >
              <ChevronLeft aria-hidden="true" className="h-4 w-4" />
            </button>
          </div>
        </header>
      )}

      {conversations.length === 0 ? (
        <p className="px-3 py-6 text-center text-xs text-slate-500">
          {text("暂无历史对话", "No conversations yet")}
        </p>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
          {grouped.map((group) => (
            <section key={group.label} className="pt-3">
              <div className="px-2 pb-1.5 text-xs font-semibold text-slate-700">
                {group.label}
              </div>
              <ul className="flex flex-col gap-0.5">
                {group.conversations.map((c) => {
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
                          "group flex items-center gap-1 rounded-lg transition-colors",
                          active ? "bg-slate-200/80" : "hover:bg-slate-200/60",
                        )}
                      >
                        <button
                          type="button"
                          onClick={() => onSelectConversation(c.id)}
                          aria-current={active ? "page" : undefined}
                          title={updatedLabel}
                          className="flex min-w-0 flex-1 items-center rounded-lg px-2 py-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
                        >
                          <span className="truncate text-sm text-slate-800">{title}</span>
                        </button>
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            onDeleteConversation(c.id);
                          }}
                          aria-label={text("删除对话", "Delete conversation")}
                          title={text("删除对话", "Delete conversation")}
                          className="mr-1 rounded-md p-1 text-slate-400 opacity-0 transition-opacity hover:bg-white/70 hover:text-red-500 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 group-hover:opacity-100"
                        >
                          <Trash2 aria-hidden="true" className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      )}
      {desktop ? (
        <nav aria-label={text("桌面快捷入口", "Desktop shortcuts")} className="border-t border-slate-200 p-2">
          <DesktopUtilityLink to="/teams" label={text("团队", "Teams")} icon={<Users className="h-4 w-4" />} />
          <DesktopUtilityLink to="/terminal" label={text("终端", "Terminal")} icon={<Terminal className="h-4 w-4" />} />
          <DesktopUtilityLink to={desktopFilesPath} label={text("文件", "Files")} icon={<FolderOpen className="h-4 w-4" />} />
          <DesktopUtilityLink to={desktopApprovalsPath} label={text("审批", "Approvals")} icon={<ShieldCheck className="h-4 w-4" />} />
          <DesktopUtilityLink to="/desktop" label={text("设置", "Settings")} icon={<Settings2 className="h-4 w-4" />} />
        </nav>
      ) : null}
    </aside>
  );
}

function desktopPanelPath(pathname: string, search: string, panel: "files" | "approvals"): string {
  const workspacePath = /^\/agents\/[^/]+\/workspace$/.test(pathname)
    ? pathname
    : "/agents/default/workspace";
  const params = new URLSearchParams(search);
  params.set("desktop_panel", panel);
  return `${workspacePath}?${params.toString()}`;
}

function DesktopUtilityLink({
  to,
  label,
  icon,
}: {
  to: string;
  label: string;
  icon: JSX.Element;
}): JSX.Element {
  return (
    <Link
      to={to}
      aria-label={label}
      title={label}
      className="flex h-9 items-center gap-2 rounded-md px-2 text-sm text-slate-600 transition-colors hover:bg-slate-200/70 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
    >
      <span aria-hidden="true" className="shrink-0">{icon}</span>
      <span className="truncate">{label}</span>
    </Link>
  );
}

function groupConversations(
  conversations: ConversationSummary[],
  labelFor: (conversation: ConversationSummary) => string,
): Array<{ label: string; conversations: ConversationSummary[] }> {
  const groups: Array<{ label: string; conversations: ConversationSummary[] }> = [];
  const groupByLabel = new Map<string, { label: string; conversations: ConversationSummary[] }>();
  for (const conversation of conversations) {
    const rawLabel = labelFor(conversation).trim();
    const label = rawLabel.length > 0 ? rawLabel : "Agent";
    let group = groupByLabel.get(label);
    if (group === undefined) {
      group = { label, conversations: [] };
      groupByLabel.set(label, group);
      groups.push(group);
    }
    group.conversations.push(conversation);
  }
  return groups;
}
