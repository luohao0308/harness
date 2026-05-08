import type { ReactNode } from "react";

import { cn } from "../../lib/utils";

export type BadgeTone =
  | "neutral"
  | "success"
  | "running"
  | "failed"
  | "warning"
  | "purple"
  | "info"
  | "pending";

export function statusTone(status: string): BadgeTone {
  const map: Record<string, BadgeTone> = {
    RUNNING: "running",
    COMPLETED: "success",
    SUCCESS: "success",
    FAILED: "failed",
    CANCELLED: "neutral",
    CREATED: "neutral",
    PLANNING: "info",
    WAITING_SUBAGENTS: "warning",
    WAITING_SUBAGENT: "warning",
    PENDING: "pending",
    QUEUED: "warning",
    TIMEOUT: "warning",
    PLAN_GENERATED: "success",
    PLAN_REQUESTED: "info",
    STEP_STARTED: "running",
    STEP_COMPLETED: "success",
    TASK_CREATED: "neutral",
    TASK_COMPLETED: "success",
  };
  return map[status] ?? "neutral";
}

export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: BadgeTone;
  className?: string;
}) {
  const tones: Record<BadgeTone, string> = {
    neutral: "bg-slate-100 text-slate-700 border-slate-200",
    success: "bg-emerald-50 text-emerald-700 border-emerald-200",
    running: "bg-blue-50 text-blue-700 border-blue-200",
    failed: "bg-red-50 text-red-700 border-red-200",
    warning: "bg-amber-50 text-amber-700 border-amber-200",
    purple: "bg-violet-50 text-violet-700 border-violet-200",
    info: "bg-cyan-50 text-cyan-700 border-cyan-200",
    pending: "bg-slate-50 text-slate-500 border-slate-200",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-[11px] tracking-wide",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Dot({ tone = "neutral" }: { tone?: BadgeTone }) {
  const tones: Record<BadgeTone, string> = {
    neutral: "bg-slate-400",
    success: "bg-emerald-500",
    running: "bg-blue-500",
    failed: "bg-red-500",
    warning: "bg-amber-500",
    purple: "bg-violet-500",
    info: "bg-cyan-500",
    pending: "bg-slate-300",
  };
  return <span className={cn("inline-block h-1.5 w-1.5 rounded-full", tones[tone])} />;
}
