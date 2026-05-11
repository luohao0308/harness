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

  const ariaLabel = text("上下文最大 tokens", "Context max tokens");

  const apply = (candidate: number | null): void => {
    if (candidate === null) return;
    onChange(clampContextMaxTokens(candidate));
  };

  return (
    <div className="flex flex-col gap-2" data-tabbable-scope="context-max-tokens">
      <div className="flex items-center justify-between gap-3">
        <label
          htmlFor={rangeId}
          className="text-xs font-medium text-slate-700"
        >
          {ariaLabel}
        </label>
        <span className="font-mono text-xs text-slate-600">{value} tokens</span>
      </div>
      <div className="flex items-center gap-3">
        <input
          id={rangeId}
          type="range"
          min={CONTEXT_MAX_TOKENS_MIN}
          max={CONTEXT_MAX_TOKENS_MAX}
          step={CONTEXT_MAX_TOKENS_STEP}
          value={value}
          onChange={(event) => apply(parseInput(event.target.value))}
          aria-label={ariaLabel}
          className="flex-1"
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
          className="w-[96px] rounded-md border border-slate-200 bg-white px-2 py-1 text-right font-mono text-xs text-slate-700 outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
        />
      </div>
      <p className="text-[11px] text-slate-500">
        {text(
          "模型上下文最大长度，越大越耗 token",
          "Model context window; larger values consume more tokens per request",
        )}
      </p>
    </div>
  );
}
