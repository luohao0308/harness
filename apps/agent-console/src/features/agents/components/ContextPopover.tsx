/**
 * ContextPopover — chip + popover that edits
 * `useWorkspaceStore.contextWindowTurns` (Req 6.1, 6.2, 6.7, 6.8, 14.2).
 *
 * - The trigger chip shows "上下文 {value}" / "Context {value}" and toggles
 *   the popover open state.
 * - While open the popover renders a 320px-wide card 4px above the chip
 *   (`bottom-full mb-2`) containing a numeric label, a `<input type="range">`
 *   (2..20) and a bilingual hint.
 * - `useOutsideClick(popoverRef, close, open)` collapses the popover on
 *   outside mousedown / touchstart / Escape (Req 6.1 / 14.4).
 *
 * Stateless except for local UI state — `value` and `onChange` are owned by
 * the parent (`ComposerToolbar`), which in turn reads/writes
 * `useWorkspaceStore.contextWindowTurns`. The component MUST NOT import the
 * store directly (Req 15.3 ownership separation).
 */

import { useRef, useState, type JSX } from "react";

import { useI18n } from "../../../lib/i18n";
import { Button } from "../../../components/ui/button";
import { useOutsideClick } from "../hooks/useOutsideClick";

export type ContextPopoverProps = {
  /** Bound to `useWorkspaceStore.contextWindowTurns`. Range: 2..20. */
  value: number;
  onChange: (turns: number) => void;
};

/**
 * Headless presentation of the popover contents (v4 / Req 4.6).
 * `ComposerOptionsPopover` embeds this inside its Context section without
 * wrapping it in a second popover shell. The default export below
 * (`ContextPopover`) keeps the v3 chip + dropdown flow intact for any
 * callers still using it outside the Options popover.
 */
export type ContextPopoverContentProps = ContextPopoverProps & {
  /**
   * Optional attribute — the first tabbable inside `ComposerOptionsPopover`
   * carries `data-tabbable="first"` so the focus-trap effect can land
   * initial focus here without querying the DOM for specific IDs.
   */
  firstTabbable?: boolean;
};

export function ContextPopoverContent({
  value,
  onChange,
  firstTabbable = false,
}: ContextPopoverContentProps): JSX.Element {
  const { text } = useI18n();
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <span className="text-xs font-medium text-slate-700">
          {text("上下文轮数", "Context turns")}
        </span>
        <span className="font-mono text-xl text-slate-900">{value}</span>
      </div>
      <input
        type="range"
        min={2}
        max={20}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        aria-label={text("上下文轮数滑杆", "Context turns slider")}
        data-tabbable={firstTabbable ? "first" : undefined}
      />
      <p className="text-[11px] text-slate-500">
        {text(
          "影响发送给模型的历史消息数量",
          "How many past turns ship with each request",
        )}
      </p>
    </div>
  );
}

export function ContextPopover({ value, onChange }: ContextPopoverProps): JSX.Element {
  const { text } = useI18n();
  const [open, setOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  useOutsideClick(popoverRef, () => setOpen(false), open);

  const label = text(`上下文 ${value}`, `Context ${value}`);

  return (
    <div ref={popoverRef} className="relative inline-block">
      <Button
        type="button"
        variant="secondary"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={text("上下文轮数", "Context turns")}
      >
        {label}
      </Button>
      {open && (
        <div
          role="dialog"
          aria-label={text("上下文轮数", "Context turns")}
          className="absolute bottom-full left-0 z-20 mb-2 w-[320px] rounded-2xl border border-slate-200 bg-white p-3 shadow-none"
        >
          <div className="flex items-baseline justify-between">
            <span className="text-xs font-medium text-slate-700">
              {text("上下文轮数", "Context turns")}
            </span>
            <span className="font-mono text-xl text-slate-900">{value}</span>
          </div>
          <input
            type="range"
            min={2}
            max={20}
            value={value}
            onChange={(event) => onChange(Number(event.target.value))}
            className="mt-2 w-full"
            aria-label={text("上下文轮数滑杆", "Context turns slider")}
          />
          <p className="mt-2 text-[11px] text-slate-500">
            {text(
              "影响发送给模型的历史消息数量",
              "How many past turns ship with each request",
            )}
          </p>
        </div>
      )}
    </div>
  );
}
