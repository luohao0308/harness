import { ArrowLeft, ArrowRight } from "lucide-react";

import { cn } from "../../lib/utils";

export interface NavigationButtonsProps {
  onNext?: () => void;
  onPrevious?: () => void;
  canGoNext?: boolean;
  canGoPrevious?: boolean;
  nextLabel?: string;
  previousLabel?: string;
  isFirstStep?: boolean;
  isLastStep?: boolean;
  isLoading?: boolean;
}

export function NavigationButtons({
  onNext,
  onPrevious,
  canGoNext = true,
  canGoPrevious = true,
  nextLabel = "Next",
  previousLabel = "Previous",
  isFirstStep = false,
  isLastStep = false,
  isLoading = false,
}: NavigationButtonsProps) {
  const finalNextLabel = isLastStep ? "Complete" : nextLabel;

  return (
    <div className="flex items-center justify-between">
      {/* Previous Button */}
      <button
        type="button"
        onClick={onPrevious}
        disabled={!canGoPrevious || isFirstStep || isLoading}
        className={cn(
          "inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-all duration-200 hover:bg-slate-50 hover:shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 active:scale-95",
          {
            "invisible": isFirstStep,
            "cursor-not-allowed opacity-50 hover:bg-white hover:shadow-none active:scale-100":
              !canGoPrevious && !isFirstStep,
          },
        )}
        aria-label={previousLabel}
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        {previousLabel}
      </button>

      {/* Next Button */}
      <button
        type="button"
        onClick={onNext}
        disabled={!canGoNext || isLoading}
        className={cn(
          "inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-all duration-200 hover:bg-blue-700 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 active:scale-95",
          {
            "cursor-not-allowed opacity-50 hover:bg-blue-600 hover:shadow-sm active:scale-100":
              !canGoNext || isLoading,
          },
        )}
        aria-label={finalNextLabel}
      >
        {finalNextLabel}
        <ArrowRight className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  );
}
