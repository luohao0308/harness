import { zodResolver } from "@hookform/resolvers/zod";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

const firstAgentSchema = z.object({
  name: z.string().min(3, "Agent name must be at least 3 characters").max(50, "Agent name must be less than 50 characters"),
  description: z.string().min(10, "Description must be at least 10 characters").max(200, "Description must be less than 200 characters"),
  systemPrompt: z.string().min(20, "System prompt must be at least 20 characters").max(2000, "System prompt must be less than 2000 characters"),
});

type FirstAgentFormData = z.infer<typeof firstAgentSchema>;

export interface FirstAgentStepProps {
  onSubmit: (data: FirstAgentFormData) => void | Promise<void>;
  initialData?: Partial<FirstAgentFormData>;
}

export function FirstAgentStep({ onSubmit, initialData }: FirstAgentStepProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, touchedFields },
  } = useForm<FirstAgentFormData>({
    resolver: zodResolver(firstAgentSchema),
    defaultValues: initialData,
    mode: "onTouched",
  });

  const systemPromptValue = watch("systemPrompt", "");
  const descriptionValue = watch("description", "");

  const handleFormSubmit = async (data: FirstAgentFormData) => {
    setIsSubmitting(true);
    setSubmitError(null);

    try {
      await onSubmit(data);
    } catch (error) {
      setSubmitError(
        error instanceof Error
          ? error.message
          : "Failed to create agent. Please check your inputs and try again.",
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const getCharacterCountColor = (current: number, max: number) => {
    const percentage = (current / max) * 100;
    if (percentage >= 90) return "text-red-600";
    if (percentage >= 75) return "text-amber-600";
    return "text-slate-500";
  };

  return (
    <div className="space-y-6">
      <div className="animate-slide-up">
        <h2 className="text-2xl font-bold text-slate-900">Create Your First Agent</h2>
        <p className="mt-2 text-sm text-slate-600">
          Define your agent's identity and behavior with a name, description, and system prompt.
        </p>
      </div>

      <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-6">
        {/* Agent Name Field */}
        <div className="animate-slide-up" style={{ animationDelay: "50ms" }}>
          <label htmlFor="name" className="block text-sm font-medium text-slate-700">
            Agent Name <span className="text-red-500" aria-label="required">*</span>
          </label>
          <input
            id="name"
            type="text"
            {...register("name")}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 shadow-sm transition-all duration-200 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-500"
            placeholder="e.g., Customer Support Agent"
            disabled={isSubmitting}
            aria-invalid={errors.name ? "true" : "false"}
            aria-describedby={errors.name ? "name-error" : undefined}
          />
          {errors.name ? (
            <p id="name-error" className="mt-1 flex items-center gap-1 text-sm text-red-600" role="alert">
              <AlertCircle className="h-4 w-4" aria-hidden="true" />
              {errors.name.message}
            </p>
          ) : touchedFields.name ? (
            <p className="mt-1 flex items-center gap-1 text-sm text-green-600">
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              Looks good
            </p>
          ) : null}
        </div>

        {/* Description Field */}
        <div className="animate-slide-up" style={{ animationDelay: "100ms" }}>
          <label htmlFor="description" className="block text-sm font-medium text-slate-700">
            Description <span className="text-red-500" aria-label="required">*</span>
          </label>
          <textarea
            id="description"
            rows={3}
            {...register("description")}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 shadow-sm transition-all duration-200 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-500"
            placeholder="Describe what this agent does..."
            disabled={isSubmitting}
            aria-invalid={errors.description ? "true" : "false"}
            aria-describedby={errors.description ? "description-error description-count" : "description-count"}
          />
          <div className="mt-1 flex items-start justify-between gap-2">
            <div className="flex-1">
              {errors.description && (
                <p id="description-error" className="flex items-center gap-1 text-sm text-red-600" role="alert">
                  <AlertCircle className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                  {errors.description.message}
                </p>
              )}
            </div>
            <p
              id="description-count"
              className={`text-xs ${getCharacterCountColor(descriptionValue.length, 200)}`}
              aria-live="polite"
            >
              {descriptionValue.length} / 200
            </p>
          </div>
        </div>

        {/* System Prompt Field */}
        <div className="animate-slide-up" style={{ animationDelay: "150ms" }}>
          <label htmlFor="systemPrompt" className="block text-sm font-medium text-slate-700">
            System Prompt <span className="text-red-500" aria-label="required">*</span>
          </label>
          <textarea
            id="systemPrompt"
            rows={6}
            {...register("systemPrompt")}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-sm shadow-sm transition-all duration-200 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-500"
            placeholder="You are a helpful assistant that..."
            disabled={isSubmitting}
            aria-invalid={errors.systemPrompt ? "true" : "false"}
            aria-describedby={errors.systemPrompt ? "systemPrompt-error systemPrompt-count systemPrompt-help" : "systemPrompt-count systemPrompt-help"}
          />
          <div className="mt-1 flex items-start justify-between gap-2">
            <div className="flex-1">
              {errors.systemPrompt && (
                <p id="systemPrompt-error" className="flex items-center gap-1 text-sm text-red-600" role="alert">
                  <AlertCircle className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                  {errors.systemPrompt.message}
                </p>
              )}
              <p id="systemPrompt-help" className="mt-1 text-xs text-slate-500">
                The system prompt defines how your agent behaves and responds to requests.
              </p>
            </div>
            <p
              id="systemPrompt-count"
              className={`text-xs ${getCharacterCountColor(systemPromptValue.length, 2000)}`}
              aria-live="polite"
            >
              {systemPromptValue.length} / 2000
            </p>
          </div>
        </div>

        {/* Submit Error */}
        {submitError && (
          <div className="animate-slide-up rounded-md border border-red-200 bg-red-50 p-4" role="alert">
            <div className="flex">
              <AlertCircle className="h-5 w-5 flex-shrink-0 text-red-400" aria-hidden="true" />
              <div className="ml-3">
                <h3 className="text-sm font-medium text-red-800">Agent Creation Error</h3>
                <p className="mt-1 text-sm text-red-700">{submitError}</p>
              </div>
            </div>
          </div>
        )}

        {/* Submit Button */}
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={isSubmitting}
            className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-all duration-200 hover:bg-blue-700 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-blue-600 disabled:hover:shadow-sm disabled:active:scale-100"
            aria-label="Save agent"
          >
            {isSubmitting && (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            )}
            {isSubmitting ? "Creating Agent..." : "Save Agent"}
          </button>
        </div>
      </form>
    </div>
  );
}
