/**
 * ContextMaxTokensSlider — range + numeric input bound to
 * `useWorkspaceStore.contextMaxTokens` (v4 / Req 5.3, 8.3).
 *
 * - All write paths go through `clampContextMaxTokens` so the store never
 *   sees an out-of-range value; typing an invalid number (e.g. `123`)
 *   clamps to the nearest step on blur / input.
 * - `<input type="range">` supplies native `aria-valuemin` / `valuemax` /
 *   `valuenow` (Req 8.3) and left/right arrow-key increments.
 * - Bilingual via `useI18n().text`.
 */

import { useId, type JSX } from "react";

import { useI18n } from "../../../lib/i18n";
import {
  CONTEXT_MAX_TOKENS_MAX,
  CONTEXT_MAX_TOKENS_MIN,
  CONTEXT_MAX_TOKENS_STEP,
  clampContextMaxTokens,
} from "../lib/contextTokens";

export type ContextMaxTokensSliderProps = {
  /** Current store value; always finite. */
  value: number;
  /** Invoked with a sanitized value. Parent routes to `setContextMaxTokens`. */
  onChange: (next: number) => void;
};

function parseInput(raw: string): number | null {
  const n = Number(raw);
  if (!Number.isFinite(n)) return null;
  return n;
}

export function ContextMaxTokensSlider({
  value,
  onChange,
}: ContextMaxTokensSliderProps): JSX.Element {
  const { text } = useI18n();
  const rangeId = useId();
  const numberId = useId();

  const ariaLabel = text("上下文窗口大小 (标记)", "Context window size (tokens)");

  const apply = (candidate: number | null): void => {
    if (candidate === null) return;
    onChange(clampContextMaxTokens(candidate));
  };

  return (
    <div className="flex flex-col gap-1.5" data-tabbable-scope="context-max-tokens">
      <div className="flex items-center justify-between gap-2">
        <label
          htmlFor={rangeId}
          className="text-[11px] font-medium text-slate-700"
        >
          {ariaLabel}
        </label>
        <span className="font-mono text-[11px] text-slate-600">{formatTokenCount(value)}</span>
      </div>
      <div className="flex items-center gap-2">
        <input
          id={rangeId}
          type="range"
          min={CONTEXT_MAX_TOKENS_MIN}
          max={CONTEXT_MAX_TOKENS_MAX}
          step={CONTEXT_MAX_TOKENS_STEP}
          value={value}
          onChange={(event) => apply(parseInput(event.target.value))}
          aria-label={ariaLabel}
          className="h-1 flex-1 accent-slate-900"
        />
        <label htmlFor={numberId} className="sr-only">
          {ariaLabel}
        </label>
        <input
          id={numberId}
          type="number"
          min={CONTEXT_MAX_TOKENS_MIN}
          max={CONTEXT_MAX_TOKENS_MAX}
          step={CONTEXT_MAX_TOKENS_STEP}
          value={value}
          onChange={(event) => apply(parseInput(event.target.value))}
          aria-label={ariaLabel}
          className="h-7 w-[76px] rounded-md border border-slate-200 bg-white px-1.5 text-right font-mono text-[11px] text-slate-700 outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
        />
      </div>
      <p className="text-[10px] leading-4 text-slate-500">
        {text(
          "上下文窗口大小，超出时自动截断旧消息",
          "Context window size; older messages are truncated when exceeded",
        )}
      </p>
    </div>
  );
}

function formatTokenCount(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "0";
  if (value >= 1_000_000) return `${Number.parseFloat((value / 1_000_000).toFixed(1))}m`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}k`;
  return String(Math.round(value));
}
