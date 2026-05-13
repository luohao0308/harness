/**
 * ContextUsageBar — compact usage indicator showing context size in KB.
 *
 * Displays current/limit with a progress bar:
 *   - Below 80%: slate fill
 *   - 80%–95%: amber fill + warning text
 *   - 95%+: red fill + critical text
 */

import type { JSX } from "react";

import { AlertTriangle } from "lucide-react";

import { useI18n } from "../../../lib/i18n";
import { cn } from "../../../lib/utils";

export type ContextUsageBarProps = {
  /** Clamped to [0, 1] internally. */
  ratio: number;
  /** Current context size in KB. */
  current: number;
  /** Context window limit in KB. */
  limit: number;
};

function formatKB(kb: number): string {
  return kb >= 1024 ? `${(kb / 1024).toFixed(1)}MB` : `${kb}KB`;
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
        {formatKB(current)}/{formatKB(limit)}
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
            : text("接近上下文上限", "Context near limit")}
        </span>
      )}
    </div>
  );
}
