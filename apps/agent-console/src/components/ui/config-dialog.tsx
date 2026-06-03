import type { ReactNode } from "react";
import { X } from "lucide-react";

import { useI18n } from "../../lib/i18n";
import { cn } from "../../lib/utils";
import { Card } from "./card";

type ConfigDialogProps = {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
  className?: string;
};

export function ConfigDialog({
  open,
  title,
  description,
  onClose,
  children,
  className,
}: ConfigDialogProps) {
  const { text } = useI18n();

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-950/30 p-4 pt-[8vh]">
      <Card
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn("w-full max-w-2xl overflow-hidden rounded-xl p-0 shadow-xl", className)}
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 bg-white px-6 py-5">
          <div className="min-w-0">
            <div className="text-lg font-medium text-slate-950">{title}</div>
            {description ? <div className="mt-1 text-xs leading-5 text-slate-500">{description}</div> : null}
          </div>
          <button
            type="button"
            aria-label={text("关闭", "Close")}
            onClick={onClose}
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-900"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="px-6 py-5">{children}</div>
      </Card>
    </div>
  );
}
