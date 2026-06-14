import { Check } from "lucide-react";

import { cn } from "../../lib/utils";
import type { WizardStep } from "./WizardLayout";

export interface StepIndicatorProps {
  steps: WizardStep[];
  currentStep: number;
}

export function StepIndicator({ steps, currentStep }: StepIndicatorProps) {
  return (
    <nav aria-label="Progress">
      {/* Mobile: Compact view */}
      <div className="sm:hidden">
        <p className="text-sm font-medium text-slate-900">
          Step {currentStep + 1} of {steps.length}
        </p>
        <p className="mt-1 text-sm text-slate-600">{steps[currentStep]?.title}</p>
      </div>

      {/* Desktop: Full step list */}
      <ol className="hidden sm:flex sm:items-center sm:space-x-4">
        {steps.map((step, index) => {
          const isCompleted = index < currentStep;
          const isCurrent = index === currentStep;
          const isUpcoming = index > currentStep;

          return (
            <li key={step.id} className="flex flex-1 items-center">
              <div className="flex w-full items-center">
                {/* Step circle */}
                <div
                  className={cn(
                    "flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full border-2 transition-colors",
                    {
                      "border-blue-600 bg-blue-600": isCompleted,
                      "border-blue-600 bg-white": isCurrent,
                      "border-slate-300 bg-white": isUpcoming,
                    },
                  )}
                >
                  {isCompleted ? (
                    <Check className="h-5 w-5 text-white" aria-hidden="true" />
                  ) : (
                    <span
                      className={cn("text-sm font-medium", {
                        "text-blue-600": isCurrent,
                        "text-slate-500": isUpcoming,
                      })}
                    >
                      {index + 1}
                    </span>
                  )}
                </div>

                {/* Step label */}
                <div className="ml-3 flex-1">
                  <p
                    className={cn("text-sm font-medium", {
                      "text-blue-600": isCurrent,
                      "text-slate-900": isCompleted,
                      "text-slate-500": isUpcoming,
                    })}
                  >
                    {step.title}
                  </p>
                  {step.description && (
                    <p className="text-xs text-slate-500">{step.description}</p>
                  )}
                </div>

                {/* Connector line */}
                {index < steps.length - 1 && (
                  <div
                    className={cn("ml-4 h-0.5 flex-1 transition-colors", {
                      "bg-blue-600": isCompleted,
                      "bg-slate-300": !isCompleted,
                    })}
                    aria-hidden="true"
                  />
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
