/**
 * ComposerToolbar — row above the textarea. v4 collapses Context / Pinned /
 * Tools / Model into a single `Options` trigger (Req 4.1) and keeps
 * `ContextUsageBar`, `ExportMenu` and the `Clear conversation` trash icon
 * visible inline (Req 4.7 / 4.8).
 *
 * Pure presentational — every piece of state is owned by the parent
 * (`ChatSurface` / `AgentWorkspacePage`) and the component never imports
 * `useWorkspaceStore`. The Options popover itself is rendered by
 * `ChatSurface`; this file only owns the trigger button + the secondary
 * right-side cluster.
 *
 * Layout (desktop ≥ `sm`):
 *   [Options ⌄]                               [Usage bar] [Export ⌄] [🗑]
 * On narrow screens `flex-wrap` allows the right-side cluster to fall to a
 * second row while keeping each row thin so the overall toolbar stays
 * compact.
 *
 * `onClearConversation` is fired directly; the parent owns the confirmation
 * and final interaction feedback flow (Req 12.5).
 */

import { useRef, useState, type JSX, type RefObject } from "react";
import { ChevronDown, Download, SlidersHorizontal, Trash2 } from "lucide-react";

import { useI18n } from "../../../lib/i18n";
import { cn } from "../../../lib/utils";
import { useOutsideClick } from "../hooks/useOutsideClick";
import { ContextUsageBar } from "./ContextUsageBar";

export type ComposerToolbarProps = {
  /**
   * Whether the Options popover is currently open. Parent (`ChatSurface`)
   * owns the state and renders the popover itself; the toolbar only wires
   * the trigger button's visual / aria state.
   */
  optionsOpen: boolean;
  onOptionsToggle: () => void;
  /**
   * Ref on the Options trigger button. Parent reads this to compute the
   * popover's anchor / outside-click exclusion (Req 4.5).
   */
  optionsTriggerRef: RefObject<HTMLButtonElement | null>;

  // Context usage bar (Req 13.4 / 13.5)
  usageRatio: number;
  usageLimit: number;
  usageCurrent: number;

  // Export / Clear (Req 12.5 / 13.3)
  onExport: (format: "markdown" | "json") => void;
  onClearConversation: () => void;
};

type ExportMenuProps = {
  onExport: (format: "markdown" | "json") => void;
};

function ExportMenu({ onExport }: ExportMenuProps): JSX.Element {
  const { text } = useI18n();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useOutsideClick(containerRef, () => setOpen(false), open);

  const handleSelect = (format: "markdown" | "json"): void => {
    onExport(format);
    setOpen(false);
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={text("导出对话", "Export conversation")}
        className={cn(
          "inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-700 transition-colors hover:bg-slate-50",
        )}
      >
        <Download aria-hidden="true" className="h-3 w-3 shrink-0" />
        <span>{text("导出", "Export")}</span>
        <ChevronDown aria-hidden="true" className="h-3 w-3 shrink-0" />
      </button>
      {open && (
        <div
          role="menu"
          aria-label={text("导出对话", "Export conversation")}
          className="absolute bottom-full right-0 z-30 mb-2 w-[160px] rounded-2xl border border-slate-200 bg-white p-1 shadow-lg"
        >
          <button
            type="button"
            role="menuitem"
            onClick={() => handleSelect("markdown")}
            className="flex w-full flex-col items-start rounded-xl px-2 py-1.5 text-left text-xs text-slate-700 transition-colors hover:bg-slate-50"
          >
            <span>Markdown</span>
            <span className="text-[10px] text-slate-400">轻量标记文本</span>
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => handleSelect("json")}
            className="flex w-full flex-col items-start rounded-xl px-2 py-1.5 text-left text-xs text-slate-700 transition-colors hover:bg-slate-50"
          >
            <span>JSON</span>
            <span className="text-[10px] text-slate-400">结构化数据</span>
          </button>
        </div>
      )}
    </div>
  );
}

export function ComposerToolbar({
  optionsOpen,
  onOptionsToggle,
  optionsTriggerRef,
  usageRatio,
  usageLimit,
  usageCurrent,
  onExport,
  onClearConversation,
}: ComposerToolbarProps): JSX.Element {
  const { text } = useI18n();
  const optionsLabel = text("选项", "Options");

  return (
    <div className="flex flex-wrap items-center gap-2 px-1 py-1">
      <button
        ref={optionsTriggerRef}
        type="button"
        onClick={onOptionsToggle}
        aria-haspopup="dialog"
        aria-expanded={optionsOpen}
        aria-label={optionsLabel}
        className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600 transition-colors hover:bg-slate-50"
      >
        <SlidersHorizontal aria-hidden="true" className="h-3 w-3" />
        <span>{optionsLabel}</span>
        <ChevronDown aria-hidden="true" className="h-3 w-3" />
      </button>
      <div className="ml-auto flex items-center gap-2">
        <ContextUsageBar ratio={usageRatio} current={usageCurrent} limit={usageLimit} />
        <ExportMenu onExport={onExport} />
        <button
          type="button"
          onClick={onClearConversation}
          aria-label={text("清空对话", "Clear conversation")}
          className="rounded-full border border-slate-200 bg-white p-1.5 text-slate-400 transition-colors hover:text-red-500"
        >
          <Trash2 aria-hidden="true" className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
