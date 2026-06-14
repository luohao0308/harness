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
}: NavigationButtonsProps) {
  const finalNextLabel = isLastStep ? "Complete" : nextLabel;

  return (
    <div className="flex items-center justify-between">
      {/* Previous Button */}
      <button
        type="button"
        onClick={onPrevious}
        disabled={!canGoPrevious || isFirstStep}
        className={cn(
          "rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2",
          {
            "invisible": isFirstStep,
            "cursor-not-allowed opacity-50": !canGoPrevious && !isFirstStep,
          },
        )}
      >
        {previousLabel}
      </button>

      {/* Next Button */}
      <button
        type="button"
        onClick={onNext}
        disabled={!canGoNext}
        className={cn(
          "rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2",
          {
            "cursor-not-allowed opacity-50": !canGoNext,
          },
        )}
      >
        {finalNextLabel}
      </button>
    </div>
  );
}
