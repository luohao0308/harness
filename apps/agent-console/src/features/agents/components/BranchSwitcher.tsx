/**
 * BranchSwitcher — inline branch navigation control (Phase 4 / Req 16.3–16.6).
 *
 * Displayed when a conversation node has siblings (its parent has multiple
 * children). Shows "Branch N of M" with left/right arrows to navigate between
 * sibling branches.
 *
 * Pure presentational: receives all data and callbacks via props. The parent
 * (`ChatMessageList` or `ChatSurface`) is responsible for computing siblings
 * from `useWorkspaceStore.getSiblings` and wiring `switchToBranch`.
 */

import type { JSX } from "react";

import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "../../../components/ui/button";
import { useI18n } from "../../../lib/i18n";
import { cn } from "../../../lib/utils";

export type BranchSwitcherProps = {
  /** 1-based index of the current branch among siblings. */
  currentIndex: number;
  /** Total number of sibling branches. */
  totalBranches: number;
  /** Called with the sibling node id to switch to. */
  onPrevious: () => void;
  /** Called with the sibling node id to switch to. */
  onNext: () => void;
  /** Optional className for the container. */
  className?: string;
};

export function BranchSwitcher({
  currentIndex,
  totalBranches,
  onPrevious,
  onNext,
  className,
}: BranchSwitcherProps): JSX.Element | null {
  const { text } = useI18n();

  // Only render when there are multiple branches.
  if (totalBranches <= 1) return null;

  const hasPrevious = currentIndex > 1;
  const hasNext = currentIndex < totalBranches;

  return (
    <div
      className={cn(
        "inline-flex items-center gap-0.5 rounded-full border border-slate-200 bg-white px-1 py-0.5 text-[11px] text-slate-600 shadow-sm",
        className,
      )}
      aria-label={text(
        `分支 ${currentIndex}/${totalBranches}`,
        `Branch ${currentIndex} of ${totalBranches}`,
      )}
    >
      <Button
        type="button"
        variant="ghost"
        onClick={onPrevious}
        disabled={!hasPrevious}
        aria-label={text("上一个分支", "Previous branch")}
        className="h-5 w-5 p-0 disabled:opacity-30"
      >
        <ChevronLeft aria-hidden="true" className="h-3 w-3" />
      </Button>
      <span className="min-w-[3ch] text-center tabular-nums">
        {currentIndex}/{totalBranches}
      </span>
      <Button
        type="button"
        variant="ghost"
        onClick={onNext}
        disabled={!hasNext}
        aria-label={text("下一个分支", "Next branch")}
        className="h-5 w-5 p-0 disabled:opacity-30"
      >
        <ChevronRight aria-hidden="true" className="h-3 w-3" />
      </Button>
    </div>
  );
}
