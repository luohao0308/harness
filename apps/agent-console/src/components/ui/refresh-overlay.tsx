import type { ReactNode } from "react";
import { Loader2 } from "lucide-react";

import { cn } from "../../lib/utils";

type RefreshOverlayProps = {
  refreshing: boolean;
  label?: string;
  children: ReactNode;
  className?: string;
};

export function RefreshOverlay({
  refreshing,
  label = "刷新中",
  children,
  className,
}: RefreshOverlayProps) {
  return (
    <div className={cn("relative", className)} aria-busy={refreshing || undefined}>
      {children}
      {refreshing ? (
        <div className="absolute inset-0 z-10 flex items-center justify-center rounded-md border border-slate-200/70 bg-white/75">
          <div className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            {label}
          </div>
        </div>
      ) : null}
    </div>
  );
}
