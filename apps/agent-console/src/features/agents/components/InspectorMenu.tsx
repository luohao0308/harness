/**
 * InspectorMenu — dropdown that merges the v2 Inspector header buttons into
 * a single entry point (v3 / Req 6.2).
 */

import type { JSX } from "react";
import { useRef, useState } from "react";
import { Boxes, ChevronDown, PanelRight, Wrench } from "lucide-react";

import { Button } from "../../../components/ui/button";
import { useI18n } from "../../../lib/i18n";
import { cn } from "../../../lib/utils";
import { useOutsideClick } from "../hooks/useOutsideClick";
import type { InspectorSection } from "../lib/types";

export type InspectorMenuProps = {
  onOpenInspector: (section: InspectorSection) => void;
};

export function InspectorMenu({ onOpenInspector }: InspectorMenuProps): JSX.Element {
  const { text } = useI18n();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  useOutsideClick(containerRef, () => setOpen(false), open);

  const rootLabel = text("检查器", "Inspector");
  const artifactsLabel = text("产物", "Artifacts");
  const runtimeLabel = text("运行时", "Runtime");

  const handleSelect = (section: InspectorSection): void => {
    onOpenInspector(section);
    setOpen(false);
  };

  return (
    <div ref={containerRef} className="relative">
      <Button
        type="button"
        variant="ghost"
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={rootLabel}
        title={rootLabel}
        className={cn("px-2")}
      >
        <PanelRight aria-hidden="true" className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">{rootLabel}</span>
        <ChevronDown aria-hidden="true" className="h-3 w-3" />
      </Button>
      {open && (
        <div
          role="menu"
          aria-label={rootLabel}
          className="absolute right-0 top-full z-30 mt-1 w-[180px] rounded-2xl border border-slate-200 bg-white p-1 shadow-lg"
        >
          <button
            type="button"
            role="menuitem"
            onClick={() => handleSelect("artifacts")}
            className="flex w-full items-center gap-2 rounded-xl px-2 py-1.5 text-left text-xs text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
          >
            <Boxes aria-hidden="true" className="h-3.5 w-3.5" />
            <span>{artifactsLabel}</span>
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => handleSelect("runtime")}
            className="flex w-full items-center gap-2 rounded-xl px-2 py-1.5 text-left text-xs text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
          >
            <Wrench aria-hidden="true" className="h-3.5 w-3.5" />
            <span>{runtimeLabel}</span>
          </button>
        </div>
      )}
    </div>
  );
}
