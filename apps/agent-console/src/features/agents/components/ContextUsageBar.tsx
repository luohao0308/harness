/**
 * ContextUsageBar — 60×6px usage indicator rendered in `ComposerToolbar`
 * (Req 13.4, 13.5, 14.2).
 *
 * Pure presentational, stateless component:
 *   - Shows `current/limit` tokens on the left (compact `k` formatting for
 *     values ≥ 1000).
 *   - Renders a 60px wide, 6px tall bar whose fill width is `ratio` clamped
 *     to `[0, 1]`.
 *   - Below 80% the fill uses `bg-slate-400`; from 80% upward it switches to
 *     `bg-amber-500` and an inline `AlertTriangle` + bilingual warning is
 *     appended to the right (Req 13.5).
 *   - All copy flows through `useI18n().text(zh, en)` (Req 14.2). Icon-only
 *     visuals carry `aria-hidden="true"` and the container owns an
 *     `aria-label` describing the widget.
 *
 * No hooks beyond `useI18n`; does not read the workspace store. The caller
 * (`ComposerToolbar`) passes freshly computed `{ ratio, current, limit }`
 * from `contextUsage.ts` on every render.
 */

import type { JSX } from "react";

import { AlertTriangle } from "lucide-react";

import { useI18n } from "../../../lib/i18n";
import { cn } from "../../../lib/utils";

export type ContextUsageBarProps = {
  /** Clamped to [0, 1] internally. */
  ratio: number;
  /** Current token count across the included context window turns. */
  current: number;
  /** Model context window limit. */
  limit: number;
};

function formatK(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}

export function ContextUsageBar({ ratio, current, limit }: ContextUsageBarProps): JSX.Element {
  const { text } = useI18n();
  const safeRatio = Number.isFinite(ratio) ? ratio : 0;
  const clamped = Math.max(0, Math.min(1, safeRatio));
  const nearLimit = clamped >= 0.8;

  return (
    <div
      className="flex items-center gap-2 text-xs text-slate-500"
      aria-label={text("上下文用量", "Context usage")}
    >
      <span>
        {formatK(current)}/{formatK(limit)}
      </span>
      <div className="h-1.5 w-[60px] overflow-hidden rounded-full bg-slate-200">
        <div
          className={cn("h-full transition-all", nearLimit ? "bg-amber-500" : "bg-slate-400")}
          style={{ width: `${clamped * 100}%` }}
        />
      </div>
      {nearLimit && (
        <span className="inline-flex items-center gap-1 text-amber-600">
          <AlertTriangle aria-hidden="true" className="h-3 w-3" />
          {text("可能需要裁剪上下文", "Context near limit")}
        </span>
      )}
    </div>
  );
}
