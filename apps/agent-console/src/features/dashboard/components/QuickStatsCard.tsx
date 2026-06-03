import type { ReactNode } from "react";

import { Card } from "../../../components/ui/card";
import { cn } from "../../../lib/utils";

export function QuickStatsCard({
  icon,
  label,
  value,
  trend,
  tone = "slate",
}: {
  icon: ReactNode;
  label: string;
  value: string | number;
  trend: string;
  tone?: "slate" | "emerald" | "amber" | "cyan";
}) {
  return (
    <Card className="p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs text-slate-500">{label}</div>
          <div className="mt-2 font-mono text-2xl font-semibold text-slate-950">{value}</div>
        </div>
        <div
          className={cn(
            "flex h-9 w-9 items-center justify-center rounded-md",
            tone === "emerald" && "bg-emerald-50 text-emerald-700",
            tone === "amber" && "bg-amber-50 text-amber-700",
            tone === "cyan" && "bg-cyan-50 text-cyan-700",
            tone === "slate" && "bg-slate-100 text-slate-600",
          )}
        >
          {icon}
        </div>
      </div>
      <div className="mt-3 flex h-6 items-end gap-1">
        {[35, 58, 42, 70, 62, 78, 66].map((height, index) => (
          <span
            key={index}
            className="w-full rounded-sm bg-slate-200"
            style={{ height: `${height}%` }}
          />
        ))}
      </div>
      <div className="mt-2 text-[11px] text-slate-500">{trend}</div>
    </Card>
  );
}
