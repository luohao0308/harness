import type { ReactNode } from "react";

import { cn } from "../../lib/utils";
import { NavigationButtons } from "./NavigationButtons";
import { StepIndicator } from "./StepIndicator";

export interface WizardStep {
  id: string;
  title: string;
  description?: string;
}

export interface WizardLayoutProps {
  steps: WizardStep[];
  currentStep: number;
  onNext?: () => void;
  onPrevious?: () => void;
  onSkip?: () => void;
  children: ReactNode;
  canGoNext?: boolean;
  canGoPrevious?: boolean;
  nextLabel?: string;
  previousLabel?: string;
  skipLabel?: string;
  className?: string;
}

export function WizardLayout({
  steps,
  currentStep,
  onNext,
  onPrevious,
  onSkip,
  children,
  canGoNext = true,
  canGoPrevious = true,
  nextLabel = "Next",
  previousLabel = "Previous",
  skipLabel = "Skip Setup",
  className,
}: WizardLayoutProps) {
  return (
    <div className={cn("flex min-h-screen flex-col bg-slate-50", className)}>
      {/* Header with Skip Setup link */}
      <header className="border-b border-slate-200 bg-white px-4 py-4 shadow-sm sm:px-6 lg:px-8">
        <div className="mx-auto flex max-w-4xl items-center justify-between">
          <h1 className="text-xl font-semibold text-slate-900">Setup Wizard</h1>
          {onSkip && (
            <button
              onClick={onSkip}
              className="text-sm text-slate-600 hover:text-slate-900 hover:underline focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
              type="button"
            >
              {skipLabel}
            </button>
          )}
        </div>
      </header>

      {/* Progress Indicator */}
      <div className="border-b border-slate-200 bg-white px-4 py-6 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-4xl">
          <StepIndicator steps={steps} currentStep={currentStep} />
        </div>
      </div>

      {/* Main Content */}
      <main className="flex-1 px-4 py-8 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-4xl">
          <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
            {children}
          </div>
        </div>
      </main>

      {/* Navigation Buttons */}
      <footer className="border-t border-slate-200 bg-white px-4 py-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-4xl">
          <NavigationButtons
            onNext={onNext}
            onPrevious={onPrevious}
            canGoNext={canGoNext}
            canGoPrevious={canGoPrevious}
            nextLabel={nextLabel}
            previousLabel={previousLabel}
            isFirstStep={currentStep === 0}
            isLastStep={currentStep === steps.length - 1}
          />
        </div>
      </footer>
    </div>
  );
}
