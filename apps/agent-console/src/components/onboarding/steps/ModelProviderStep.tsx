import { zodResolver } from "@hookform/resolvers/zod";
import { AlertCircle, CheckCircle2, Eye, EyeOff, Loader2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

const modelProviderSchema = z.object({
  apiKey: z.string().min(1, "API key is required"),
  baseUrl: z.string().url("Base URL must be a valid URL"),
  model: z.string().min(1, "Model selection is required"),
});

type ModelProviderFormData = z.infer<typeof modelProviderSchema>;

export interface ModelProviderStepProps {
  onSubmit: (data: ModelProviderFormData) => void | Promise<void>;
  initialData?: Partial<ModelProviderFormData>;
}

const availableModels = [
  { value: "gpt-4", label: "GPT-4" },
  { value: "gpt-3.5-turbo", label: "GPT-3.5 Turbo" },
  { value: "claude-3-opus", label: "Claude 3 Opus" },
  { value: "claude-3-sonnet", label: "Claude 3 Sonnet" },
];

export function ModelProviderStep({ onSubmit, initialData }: ModelProviderStepProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [showApiKey, setShowApiKey] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, touchedFields },
  } = useForm<ModelProviderFormData>({
    resolver: zodResolver(modelProviderSchema),
    defaultValues: initialData,
    mode: "onTouched",
  });

  const handleFormSubmit = async (data: ModelProviderFormData) => {
    setIsSubmitting(true);
    setSubmitError(null);

    try {
      await onSubmit(data);
    } catch (error) {
      setSubmitError(
        error instanceof Error
          ? error.message
          : "Failed to save configuration. Please check your settings and try again.",
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="animate-slide-up">
        <h2 className="text-2xl font-bold text-slate-900">Model Provider Configuration</h2>
        <p className="mt-2 text-sm text-slate-600">
          Configure your AI model provider to power your agents.
        </p>
      </div>

      <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-6">
        {/* API Key Field */}
        <div className="animate-slide-up" style={{ animationDelay: "50ms" }}>
          <label htmlFor="apiKey" className="block text-sm font-medium text-slate-700">
            API Key <span className="text-red-500" aria-label="required">*</span>
          </label>
          <div className="relative mt-1">
            <input
              id="apiKey"
              type={showApiKey ? "text" : "password"}
              {...register("apiKey")}
              className="block w-full rounded-md border border-slate-300 px-3 py-2 pr-10 shadow-sm transition-all duration-200 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-500"
              placeholder="sk-..."
              disabled={isSubmitting}
              aria-invalid={errors.apiKey ? "true" : "false"}
              aria-describedby={errors.apiKey ? "apiKey-error" : undefined}
            />
            <button
              type="button"
              onClick={() => setShowApiKey(!showApiKey)}
              className="absolute inset-y-0 right-0 flex items-center pr-3 text-slate-400 transition-colors hover:text-slate-600 focus:outline-none"
              aria-label={showApiKey ? "Hide API key" : "Show API key"}
            >
              {showApiKey ? (
                <EyeOff className="h-5 w-5" aria-hidden="true" />
              ) : (
                <Eye className="h-5 w-5" aria-hidden="true" />
              )}
            </button>
          </div>
          {errors.apiKey ? (
            <p id="apiKey-error" className="mt-1 flex items-center gap-1 text-sm text-red-600" role="alert">
              <AlertCircle className="h-4 w-4" aria-hidden="true" />
              {errors.apiKey.message}
            </p>
          ) : touchedFields.apiKey ? (
            <p className="mt-1 flex items-center gap-1 text-sm text-green-600">
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              Looks good
            </p>
          ) : null}
        </div>

        {/* Base URL Field */}
        <div className="animate-slide-up" style={{ animationDelay: "100ms" }}>
          <label htmlFor="baseUrl" className="block text-sm font-medium text-slate-700">
            Base URL <span className="text-red-500" aria-label="required">*</span>
          </label>
          <input
            id="baseUrl"
            type="url"
            {...register("baseUrl")}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 shadow-sm transition-all duration-200 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-500"
            placeholder="https://api.openai.com/v1"
            disabled={isSubmitting}
            aria-invalid={errors.baseUrl ? "true" : "false"}
            aria-describedby={errors.baseUrl ? "baseUrl-error" : undefined}
          />
          {errors.baseUrl ? (
            <p id="baseUrl-error" className="mt-1 flex items-center gap-1 text-sm text-red-600" role="alert">
              <AlertCircle className="h-4 w-4" aria-hidden="true" />
              {errors.baseUrl.message}
            </p>
          ) : touchedFields.baseUrl ? (
            <p className="mt-1 flex items-center gap-1 text-sm text-green-600">
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              Valid URL format
            </p>
          ) : null}
        </div>

        {/* Model Selection Field */}
        <div className="animate-slide-up" style={{ animationDelay: "150ms" }}>
          <label htmlFor="model" className="block text-sm font-medium text-slate-700">
            Model <span className="text-red-500" aria-label="required">*</span>
          </label>
          <select
            id="model"
            {...register("model")}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 shadow-sm transition-all duration-200 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-500"
            disabled={isSubmitting}
            aria-invalid={errors.model ? "true" : "false"}
            aria-describedby={errors.model ? "model-error" : undefined}
          >
            <option value="">Select a model...</option>
            {availableModels.map((model) => (
              <option key={model.value} value={model.value}>
                {model.label}
              </option>
            ))}
          </select>
          {errors.model && (
            <p id="model-error" className="mt-1 flex items-center gap-1 text-sm text-red-600" role="alert">
              <AlertCircle className="h-4 w-4" aria-hidden="true" />
              {errors.model.message}
            </p>
          )}
        </div>

        {/* Submit Error */}
        {submitError && (
          <div className="animate-slide-up rounded-md border border-red-200 bg-red-50 p-4" role="alert">
            <div className="flex">
              <AlertCircle className="h-5 w-5 flex-shrink-0 text-red-400" aria-hidden="true" />
              <div className="ml-3">
                <h3 className="text-sm font-medium text-red-800">Configuration Error</h3>
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
            aria-label="Save configuration"
          >
            {isSubmitting && (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            )}
            {isSubmitting ? "Saving..." : "Save Configuration"}
          </button>
        </div>
      </form>
    </div>
  );
}
