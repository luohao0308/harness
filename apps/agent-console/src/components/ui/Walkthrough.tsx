import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";

import { cn } from "../../lib/utils";
import { Button } from "./button";

export type WalkthroughStep = {
  title: string;
  body: string;
  targetLabel: string;
};

export function Walkthrough({
  storageKey,
  steps,
}: {
  storageKey: string;
  steps: WalkthroughStep[];
}) {
  const initiallyDismissed = useMemo(() => {
    if (typeof window === "undefined") return true;
    return window.localStorage.getItem(storageKey) === "done";
  }, [storageKey]);
  const [dismissed, setDismissed] = useState(initiallyDismissed);
  const [index, setIndex] = useState(0);

  if (dismissed || steps.length === 0) {
    return null;
  }

  const step = steps[index];
  const done = () => {
    window.localStorage.setItem(storageKey, "done");
    setDismissed(true);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-end bg-slate-950/20 p-4">
      <section
        aria-label="控制台导览"
        className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-4 shadow-none"
      >
        <div className="flex items-start gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-slate-900 text-xs font-semibold text-white">
            {index + 1}
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold text-slate-950">{step.title}</div>
            <div className="mt-1 text-xs leading-5 text-slate-600">{step.body}</div>
            <div className="mt-2 inline-flex rounded-md bg-slate-100 px-2 py-1 text-[11px] text-slate-600">
              {step.targetLabel}
            </div>
          </div>
          <button
            type="button"
            className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            aria-label="跳过导览"
            onClick={done}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="mt-4 flex items-center justify-between gap-2">
          <div className="flex gap-1">
            {steps.map((item, itemIndex) => (
              <span
                key={item.title}
                className={cn(
                  "h-1.5 w-5 rounded-full",
                  itemIndex === index ? "bg-slate-900" : "bg-slate-200",
                )}
              />
            ))}
          </div>
          <div className="flex gap-2">
            <Button
              variant="ghost"
              onClick={() => setIndex((value) => Math.max(0, value - 1))}
              disabled={index === 0}
              aria-label="上一步"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </Button>
            {index === steps.length - 1 ? (
              <Button variant="primary" onClick={done}>
                完成
              </Button>
            ) : (
              <Button onClick={() => setIndex((value) => Math.min(steps.length - 1, value + 1))}>
                下一步
                <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
