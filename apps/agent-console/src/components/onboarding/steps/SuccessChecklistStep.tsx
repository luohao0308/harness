import { CheckCircle2, ExternalLink, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

export interface ChecklistItem {
  id: string;
  label: string;
  completed: boolean;
}

export interface SuccessChecklistStepProps {
  onContinue: () => void;
  onViewDocs: () => void;
}

async function fetchChecklistStatus(): Promise<ChecklistItem[]> {
  // Mock API call - replace with actual backend API
  // For demo purposes, simulate progressive completion
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve([
        { id: "system_requirements", label: "System requirements validated", completed: true },
        { id: "configuration", label: "Configuration complete", completed: true },
        { id: "database", label: "Database initialized", completed: true },
        { id: "first_agent", label: "First agent created", completed: true },
        { id: "setup", label: "Setup successful", completed: true },
      ]);
    }, 500);
  });
}

export function SuccessChecklistStep({ onContinue, onViewDocs }: SuccessChecklistStepProps) {
  const [items, setItems] = useState<ChecklistItem[]>([
    { id: "system_requirements", label: "System requirements validated", completed: false },
    { id: "configuration", label: "Configuration complete", completed: false },
    { id: "database", label: "Database initialized", completed: false },
    { id: "first_agent", label: "First agent created", completed: false },
    { id: "setup", label: "Setup successful", completed: false },
  ]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function loadStatus() {
      try {
        setIsLoading(true);
        const status = await fetchChecklistStatus();
        if (mounted) {
          setItems(status);
          setError(null);
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : "Failed to load checklist status");
        }
      } finally {
        if (mounted) {
          setIsLoading(false);
        }
      }
    }

    loadStatus();

    return () => {
      mounted = false;
    };
  }, []);

  const completedCount = items.filter((item) => item.completed).length;
  const totalCount = items.length;
  const allComplete = completedCount === totalCount;
  const progressPercent = Math.round((completedCount / totalCount) * 100);

  return (
    <div className="space-y-8">
      {/* Hero Section */}
      <div className="animate-slide-up text-center">
        <div className="mb-6 flex justify-center">
          <div className="animate-pulse-subtle rounded-full bg-green-100 p-6 transition-transform duration-300 hover:scale-110">
            <CheckCircle2 className="h-16 w-16 text-green-600" aria-hidden="true" />
          </div>
        </div>
        <h1 className="mb-4 text-3xl font-bold text-slate-900 sm:text-4xl">
          Setup Complete!
        </h1>
        <p className="mx-auto max-w-2xl text-lg text-slate-600">
          Your Agent Console is ready. Here's what we've configured for you.
        </p>
      </div>

      {/* Progress Summary */}
      <div className="animate-slide-up rounded-lg border border-slate-200 bg-white p-6 shadow-sm" style={{ animationDelay: "100ms" }}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">Setup Progress</h2>
          <span className="text-sm font-medium text-slate-600" aria-live="polite">
            {completedCount} / {totalCount} complete
          </span>
        </div>

        {/* Progress Bar */}
        <div className="mb-6 h-2 w-full overflow-hidden rounded-full bg-slate-200">
          <div
            className="h-full bg-green-600 transition-all duration-500 ease-out"
            style={{ width: `${progressPercent}%` }}
            role="progressbar"
            aria-valuenow={progressPercent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Setup progress"
          />
        </div>

        {/* Error Message */}
        {error && (
          <div className="mb-4 animate-slide-up rounded-md border border-red-200 bg-red-50 p-4" role="alert">
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {/* Checklist Items */}
        <div className="space-y-3">
          {items.map((item, index) => (
            <div
              key={item.id}
              className="animate-slide-up flex items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 p-4 transition-all duration-300 hover:shadow-sm"
              style={{ animationDelay: `${150 + index * 50}ms` }}
            >
              {isLoading ? (
                <Loader2 className="h-5 w-5 animate-spin text-blue-600" aria-hidden="true" />
              ) : item.completed ? (
                <CheckCircle2 className="h-5 w-5 flex-shrink-0 animate-fade-in text-green-600" aria-hidden="true" />
              ) : (
                <Loader2 className="h-5 w-5 flex-shrink-0 animate-spin text-blue-600" aria-hidden="true" />
              )}
              <span
                className={`text-sm font-medium transition-colors duration-200 ${
                  item.completed ? "text-slate-900" : "text-slate-600"
                }`}
              >
                {item.label}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
        <button
          onClick={onContinue}
          disabled={!allComplete || isLoading}
          className="w-full rounded-lg bg-blue-600 px-8 py-3 text-base font-medium text-white shadow-sm transition-all duration-200 hover:bg-blue-700 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-blue-600 disabled:hover:shadow-sm disabled:active:scale-100 sm:w-auto"
          type="button"
          aria-label="Continue to dashboard"
        >
          Continue to Dashboard
        </button>

        <button
          onClick={onViewDocs}
          className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-8 py-3 text-base font-medium text-slate-700 shadow-sm transition-all duration-200 hover:bg-slate-50 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 active:scale-95 sm:w-auto"
          type="button"
          aria-label="View documentation"
        >
          View Documentation
          <ExternalLink className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      {/* Help Text */}
      {!allComplete && !isLoading && (
        <div className="animate-slide-up rounded-lg border border-blue-200 bg-blue-50 p-4 text-center">
          <p className="text-sm text-blue-800">
            Please wait while we complete the setup process. This usually takes a few moments.
          </p>
        </div>
      )}
    </div>
  );
}
