import type { ReactNode } from "react";
import { useEffect, useId } from "react";
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
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    if (!open) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose, open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-950/40 p-4 pt-[8vh] backdrop-blur-[2px]"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <Card
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        className={cn("w-full max-w-2xl overflow-hidden rounded-xl p-0 shadow-xl", className)}
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 bg-white px-6 py-5">
          <div className="min-w-0">
            <div id={titleId} className="text-lg font-medium text-slate-950">{title}</div>
            {description ? <div id={descriptionId} className="mt-1 text-xs leading-5 text-slate-500">{description}</div> : null}
          </div>
          <button
            type="button"
            aria-label={text("关闭", "Close")}
            onClick={onClose}
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 active:translate-y-px"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="px-6 py-5">{children}</div>
      </Card>
    </div>
  );
}
