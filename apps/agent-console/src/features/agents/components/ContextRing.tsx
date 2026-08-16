/**
 * ContextRing — circular progress indicator for context usage.
 *
 * Renders a 24×24px SVG ring that fills based on the usage ratio.
 * Colors: slate < 80%, amber 80-95%, red ≥ 95%.
 * Shows percentage on hover via title attribute.
 */

import type { JSX } from "react";

import { useI18n } from "../../../lib/i18n";

export type ContextRingProps = {
  /** Usage ratio clamped to [0, 1]. */
  ratio: number;
  /** Current context estimate in tokens. */
  currentTokens: number;
  /** Raw uncompressed context estimate in tokens. */
  rawTokens?: number;
  /** Context budget in tokens. */
  limitTokens: number;
  /** Optional click action for compressing the context budget. */
  onCompress?: () => void;
  disabled?: boolean;
  status?: "idle" | "pending" | "ready" | "stale" | "error";
};

export function ContextRing({
  ratio,
  currentTokens,
  rawTokens,
  limitTokens,
  onCompress,
  disabled = false,
  status = "idle",
}: ContextRingProps): JSX.Element {
  const { text } = useI18n();
  const clamped = Math.max(0, Math.min(1, Number.isFinite(ratio) ? ratio : 0));
  const pct = currentTokens > 0 ? Math.max(1, Math.round(clamped * 100)) : 0;
  const isPending = status === "pending";
  const isCritical = clamped >= 0.95;
  const isAmber = clamped >= 0.8;
  const hasCompressionSavings =
    typeof rawTokens === "number" && rawTokens > currentTokens;

  const strokeColor = isPending ? "#0f172a" : isCritical ? "#ef4444" : isAmber ? "#f59e0b" : "#94a3b8";
  const radius = 9;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - clamped);
  const progressDashArray = isPending
    ? `${circumference * 0.36} ${circumference}`
    : String(circumference);
  const progressDashOffset = isPending ? 0 : dashOffset;

  const usageLabel = text(
    `背景信息窗口：${pct}% 已用，预计发送 ${formatTokenCount(currentTokens)} 标记，共 ${formatTokenCount(limitTokens)}`,
    `Context window: ${pct}% used, ${formatTokenCount(currentTokens)} estimated prompt tokens of ${formatTokenCount(limitTokens)}`,
  );
  const compressLabel =
    onCompress === undefined
      ? ""
      : text(
          isPending ? "。正在压缩上下文" : "。点击压缩上下文",
          isPending ? ". Compressing context" : ". Click to compress context",
        );
  const label = `${usageLabel}${compressLabel}`;

  return (
    <button
      type="button"
      onClick={onCompress}
      disabled={disabled || status === "pending"}
      className="group relative inline-flex h-5 w-5 items-center justify-center rounded-full bg-white text-slate-600 transition-colors hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 disabled:cursor-not-allowed disabled:opacity-70"
      title={label}
      aria-label={label}
    >
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        className={isPending ? "animate-spin rotate-[-90deg]" : "rotate-[-90deg]"}
        data-status={status}
      >
        {/* Background circle */}
        <circle
          cx="12"
          cy="12"
          r={radius}
          fill="none"
          stroke="#e2e8f0"
          strokeWidth="2.5"
        />
        {/* Progress arc */}
        <circle
          cx="12"
          cy="12"
          r={radius}
          fill="none"
          stroke={strokeColor}
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeDasharray={progressDashArray}
          strokeDashoffset={progressDashOffset}
          className="transition-all duration-300"
        />
      </svg>
      <span
        className={
          isPending
            ? "absolute h-1.5 w-1.5 rounded-full bg-slate-900 shadow-[0_0_0_3px_rgba(15,23,42,0.12)]"
            : "absolute text-[7px] font-medium text-slate-600"
        }
      >
        {isPending ? <span className="sr-only">{text("压缩中", "Compressing")}</span> : pct}
      </span>
      <div className="pointer-events-none absolute bottom-full right-0 z-40 mb-1.5 hidden w-32 rounded-md border border-slate-200 bg-white px-2 py-1.5 text-center text-[10px] text-slate-600 shadow-none group-hover:block group-focus-visible:block">
        <div>
          {text("上下文", "Context")}
        </div>
        <div className="mt-0.5 text-sm font-semibold leading-4 text-slate-950">
          {text(`${pct}% 已用`, `${pct}% used`)}
        </div>
        <div className="mt-0.5 whitespace-nowrap font-medium text-slate-700">
          {text(
            `${formatTokenCount(currentTokens)} / ${formatTokenCount(limitTokens)} 标记`,
            `${formatTokenCount(currentTokens)} / ${formatTokenCount(limitTokens)} tokens`,
          )}
        </div>
        {hasCompressionSavings && (
          <div className="mt-0.5 whitespace-nowrap text-[9px] text-slate-500">
            {text(
              `原始 ${formatTokenCount(rawTokens)}，已按摘要折算`,
              `Raw ${formatTokenCount(rawTokens)}, after summary`,
            )}
          </div>
        )}
        {onCompress !== undefined && (
          <div className="mt-0.5 whitespace-nowrap text-[9px] text-slate-500">
            {text(
              status === "pending" ? "压缩中" : "点击压缩上下文",
              status === "pending" ? "Compressing" : "Click to compress",
            )}
          </div>
        )}
      </div>
    </button>
  );
}

function formatTokenCount(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "0";
  if (value >= 1_000_000) return `${Number.parseFloat((value / 1_000_000).toFixed(1))}m`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}k`;
  return String(Math.round(value));
}
