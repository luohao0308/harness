/**
 * ContextUsageBar — 60×6px usage indicator rendered in `ComposerToolbar`
 * (Req 13.4, 13.5, 14.1, 14.2).
 *
 * Pure presentational, stateless component:
 *   - Shows `current/limit` tokens on the left (compact `k` formatting for
 *     values ≥ 1000).
 *   - Renders a 60px wide, 6px tall bar whose fill width is `ratio` clamped
 *     to `[0, 1]`.
 *   - Below 80% the fill uses `bg-slate-400`.
 *   - From 80% upward it switches to `bg-amber-500` (amber state).
 *   - From 95% upward it switches to `bg-red-500` (critical state).
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
  const isCritical = clamped >= 0.95;
  const isAmber = clamped >= 0.8;

  const barColor = isCritical ? "bg-red-500" : isAmber ? "bg-amber-500" : "bg-slate-400";
  const warningColor = isCritical ? "text-red-600" : "text-amber-600";

  return (
    <div
      className="flex items-center gap-2 text-xs text-slate-500"
      aria-label={text("上下文用量", "Context usage")}
      data-critical={isCritical || undefined}
      data-amber={(isAmber && !isCritical) || undefined}
    >
      <span>
        {formatK(current)}/{formatK(limit)}
      </span>
      <div className="h-1.5 w-[60px] overflow-hidden rounded-full bg-slate-200">
        <div
          className={cn("h-full transition-all", barColor)}
          style={{ width: `${clamped * 100}%` }}
        />
      </div>
      {isAmber && (
        <span className={cn("inline-flex items-center gap-1", warningColor)}>
          <AlertTriangle aria-hidden="true" className="h-3 w-3" />
          {isCritical
            ? text("上下文即将溢出", "Context critical")
            : text("可能需要裁剪上下文", "Context near limit")}
        </span>
      )}
    </div>
  );
}
