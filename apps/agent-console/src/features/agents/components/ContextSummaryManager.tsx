import type { JSX } from "react";
import { RefreshCw, Trash2 } from "lucide-react";

import type { ContextCompressionSummary } from "../lib/contextCompression";

type ContextSummaryManagerProps = {
  summary: ContextCompressionSummary | null;
  onRecompress: () => void;
  onClear: () => void;
  text: (zh: string, en: string) => string;
};

export function ContextSummaryManager({
  summary,
  onRecompress,
  onClear,
  text,
}: ContextSummaryManagerProps): JSX.Element | null {
  if (summary === null) return null;

  const isPending = summary.status === "pending";
  const label =
    summary.status === "error"
      ? text("摘要失败", "Summary failed")
      : isPending
        ? text("摘要中", "Summarizing")
        : text(
            `${summary.coverageNodeIds.length} 条已摘要`,
            `${summary.coverageNodeIds.length} summarized`,
          );
  const preview = summary.error || summary.summary || text("正在生成摘要", "Creating summary");

  return (
    <div
      className="group relative inline-flex h-8 items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-700"
      aria-label={text("上下文摘要", "Context summary")}
    >
      <span className="max-w-[8rem] truncate">{label}</span>
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          onRecompress();
        }}
        disabled={isPending}
        aria-label={text("重新压缩上下文", "Recompress context")}
        title={text("重新压缩上下文", "Recompress context")}
        className="inline-flex h-5 w-5 items-center justify-center rounded text-slate-500 hover:bg-slate-100 disabled:opacity-50"
      >
        <RefreshCw aria-hidden="true" className={`h-3.5 w-3.5 ${isPending ? "animate-spin" : ""}`} />
      </button>
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          onClear();
        }}
        disabled={isPending}
        aria-label={text("清除上下文摘要", "Clear context summary")}
        title={text("清除上下文摘要", "Clear context summary")}
        className="inline-flex h-5 w-5 items-center justify-center rounded text-slate-500 hover:bg-slate-100 disabled:opacity-50"
      >
        <Trash2 aria-hidden="true" className="h-3.5 w-3.5" />
      </button>
      <div className="pointer-events-none absolute right-0 top-full z-40 mt-1.5 hidden w-64 rounded-md border border-slate-200 bg-white p-2 text-left text-[11px] leading-4 text-slate-600 shadow-none group-hover:block group-focus-within:block">
        <div className="mb-1 font-medium text-slate-900">
          {text("上下文摘要", "Context summary")}
        </div>
        <div className="line-clamp-5 whitespace-pre-wrap">{preview}</div>
        <div className="mt-1 font-mono text-[10px] text-slate-500">
          {formatTokenCount(summary.estimatedOriginalTokens)} →{" "}
          {formatTokenCount(summary.estimatedSummaryTokens)}
        </div>
      </div>
    </div>
  );
}

function formatTokenCount(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "0";
  if (value >= 1_000_000) return `${Number.parseFloat((value / 1_000_000).toFixed(1))}m`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}k`;
  return String(Math.round(value));
}
