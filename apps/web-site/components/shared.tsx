import { ReactNode } from "react";

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "success" | "running" | "failed" | "warning" | "purple" | "info" | "pending";
}) {
  const tones: Record<string, string> = {
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
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded border text-[11px] tracking-wide ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function Dot({ tone = "neutral" }: { tone?: string }) {
  const tones: Record<string, string> = {
    neutral: "bg-slate-400",
    success: "bg-emerald-500",
    running: "bg-blue-500",
    failed: "bg-red-500",
    warning: "bg-amber-500",
    purple: "bg-violet-500",
    info: "bg-cyan-500",
    pending: "bg-slate-300",
  };
  return <span className={`inline-block w-1.5 h-1.5 rounded-full ${tones[tone]}`} />;
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="px-1.5 py-0.5 rounded border border-slate-200 bg-slate-50 text-[10px] text-slate-500 font-mono">
      {children}
    </kbd>
  );
}

export function statusTone(status: string): any {
  const map: Record<string, string> = {
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
    TIMEOUT: "warning",
  };
  return map[status] || "neutral";
}
