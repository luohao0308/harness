/**
 * ComposerOptionsPopover — single `role="dialog"` popover that folds the
 * v3 composer chips (Context / Pinned / Tools / Model) into four sections
 * (v4 / Req 4.1–4.11, 8.2).
 *
 * Behaviour:
 *   - Renders as an absolutely-positioned card anchored above the
 *     `Composer_Options_Popover_Trigger`; `max-h-[70vh] overflow-y-auto`
 *     so narrow viewports can scroll (Req 4.10).
 *   - `role="dialog"` + `aria-modal="false"` (non-blocking) +
 *     `aria-labelledby` → the internal `<h2>` "选项 / Options" heading.
 *   - `open` effect captures `document.activeElement`, installs a Tab /
 *     Shift+Tab focus trap across the popover's focusables, and restores
 *     focus back to the anchor button on close (Req 4.4, 4.5, 8.2).
 *   - `Escape` closes the popover via `onClose` and the focus return above.
 *   - `mousedown` outside the popover AND outside the anchor button closes
 *     it (Req 4.2). The anchor intercept avoids the "click anchor again →
 *     open→close→open" race.
 *   - Section composition delegates to headless content primitives
 *     (`ContextPopoverContent`, `PinPopoverContent`, `ToolMentionChips`,
 *     `ModelPicker`) plus the new `ContextMaxTokensSlider` inside the
 *     Context section (Req 4.6 / Req 5.3).
 *   - Tool selection closes the popover after invoking `onInsertMention`
 *     so the textarea regains focus with the inserted mention (Req 4.6).
 *   - Pure presentational: no workspace-store reads; all state / callbacks
 *     are parent-owned (Req 4.12).
 */

import { useEffect, useRef, type JSX, type RefObject } from "react";
import { ChevronDown } from "lucide-react";

import type { ConversationNode } from "../../../stores/workspaceStore";
import type { ToolMetadata } from "../../tasks/api";
import { useI18n } from "../../../lib/i18n";
import { ContextMaxTokensSlider } from "./ContextMaxTokensSlider";
import { ContextPopoverContent } from "./ContextPopover";
import { PinPopoverContent } from "./PinPopover";
import { ModelPicker, type ModelOption } from "./ModelPicker";
import { ToolMentionChips } from "./ToolMentionChips";

export type ComposerOptionsPopoverProps = {
  open: boolean;
  onClose: () => void;
  anchorRef: RefObject<HTMLButtonElement | null>;

  /** Context section */
  contextWindowTurns: number;
  onContextWindowTurnsChange: (turns: number) => void;
  contextMaxTokens: number;
  onContextMaxTokensChange: (next: number) => void;

  /** Pinned section */
  pinnedNodes: ConversationNode[];
  onUnpin: (nodeId: string) => void;

  /** Tools section */
  tools: ToolMetadata[];
  onInsertMention: (toolName: string) => void;

  /** Model section */
  providers: ModelOption[];
  selectedProviderId: string | null;
  selectedModelId: string | null;
  onModelChange: (providerId: string, modelId: string) => void;
  modelLabelFallback: string;
  /** v3 monotonic trigger for popping the inner ModelPicker dropdown. */
  modelPickerOpenSeq?: number;
};

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

function collectFocusables(root: HTMLElement | null): HTMLElement[] {
  if (root === null) return [];
  return Array.from(
    root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
  ).filter(
    (el) => el.offsetParent !== null || el.getClientRects().length > 0,
  );
}

export function ComposerOptionsPopover({
  open,
  onClose,
  anchorRef,
  contextWindowTurns,
  onContextWindowTurnsChange,
  contextMaxTokens,
  onContextMaxTokensChange,
  pinnedNodes,
  onUnpin,
  tools,
  onInsertMention,
  providers,
  selectedProviderId,
  selectedModelId,
  onModelChange,
  modelLabelFallback,
  modelPickerOpenSeq,
}: ComposerOptionsPopoverProps): JSX.Element | null {
  const { text } = useI18n();
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Focus trap + ESC + outside click + focus return.
  useEffect(() => {
    if (!open) return;

    const container = containerRef.current;
    const previousFocus =
      typeof document !== "undefined"
        ? (document.activeElement as HTMLElement | null)
        : null;

    // Move initial focus to the element flagged `data-tabbable="first"`
    // (Req 4.4). Fallback to the first focusable.
    const firstFlagged =
      container?.querySelector<HTMLElement>('[data-tabbable="first"]') ?? null;
    if (firstFlagged !== null) {
      firstFlagged.focus();
    } else {
      const focusables = collectFocusables(container);
      focusables[0]?.focus();
    }

    const handleKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const focusables = collectFocusables(container);
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement;
      if (event.shiftKey) {
        if (active === first || !container?.contains(active)) {
          event.preventDefault();
          last.focus();
        }
      } else {
        if (active === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };

    const handlePointer = (event: MouseEvent | TouchEvent): void => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (container !== null && container.contains(target)) return;
      const anchor = anchorRef.current;
      if (anchor !== null && anchor.contains(target)) return;
      onClose();
    };

    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("mousedown", handlePointer);
    document.addEventListener("touchstart", handlePointer);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("mousedown", handlePointer);
      document.removeEventListener("touchstart", handlePointer);
      // Restore focus to the anchor button (Req 4.5).
      const anchor = anchorRef.current;
      if (anchor !== null) {
        anchor.focus();
      } else if (previousFocus !== null) {
        previousFocus.focus();
      }
    };
  }, [open, onClose, anchorRef]);

  if (!open) return null;

  const handleToolMention = (toolName: string): void => {
    onInsertMention(toolName);
    onClose();
  };

  const titleId = "composer-options-title";

  return (
    <div
      ref={containerRef}
      role="dialog"
      aria-modal="false"
      aria-labelledby={titleId}
      className="absolute bottom-full right-3 z-30 mb-2 w-[min(460px,calc(100vw-1.5rem))] max-h-[70vh] overflow-y-auto rounded-2xl border border-slate-200 bg-white p-4 shadow-xl"
    >
      <div className="flex items-center justify-between">
        <h2
          id={titleId}
          className="text-sm font-semibold text-slate-900"
        >
          {text("选项", "Options")}
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label={text("关闭", "Close")}
          className="inline-flex h-6 w-6 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
        >
          <ChevronDown aria-hidden="true" className="h-4 w-4 rotate-180" />
        </button>
      </div>

      <section className="mt-3 flex flex-col gap-2 border-t border-slate-100 pt-3">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          {text("上下文", "Context")}
        </h3>
        <ContextPopoverContent
          value={contextWindowTurns}
          onChange={onContextWindowTurnsChange}
          firstTabbable
        />
        <ContextMaxTokensSlider
          value={contextMaxTokens}
          onChange={onContextMaxTokensChange}
        />
      </section>

      <section className="mt-3 flex flex-col gap-2 border-t border-slate-100 pt-3">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          {text("已固定", "Pinned")}
        </h3>
        <PinPopoverContent pinnedNodes={pinnedNodes} onUnpin={onUnpin} />
      </section>

      <section className="mt-3 flex flex-col gap-2 border-t border-slate-100 pt-3">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          {text("工具", "Tools")}
        </h3>
        <ToolMentionChips
          tools={tools}
          onInsertMention={handleToolMention}
        />
      </section>

      <section className="mt-3 flex flex-col gap-2 border-t border-slate-100 pt-3">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          {text("模型", "Model")}
        </h3>
        <ModelPicker
          providers={providers}
          selectedProviderId={selectedProviderId}
          selectedModelId={selectedModelId}
          onModelChange={onModelChange}
          modelLabelFallback={modelLabelFallback}
          openRequestSeq={modelPickerOpenSeq}
        />
      </section>
    </div>
  );
}
