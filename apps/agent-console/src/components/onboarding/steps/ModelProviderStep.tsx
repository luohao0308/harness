import { zodResolver } from "@hookform/resolvers/zod";
import { AlertCircle, Loader2 } from "lucide-react";
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

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ModelProviderFormData>({
    resolver: zodResolver(modelProviderSchema),
    defaultValues: initialData,
  });

  const handleFormSubmit = async (data: ModelProviderFormData) => {
    setIsSubmitting(true);
    setSubmitError(null);

    try {
      await onSubmit(data);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Failed to save configuration");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-slate-900">Model Provider Configuration</h2>
        <p className="mt-2 text-sm text-slate-600">
          Configure your AI model provider to power your agents.
        </p>
      </div>

      <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-6">
        {/* API Key Field */}
        <div>
          <label htmlFor="apiKey" className="block text-sm font-medium text-slate-700">
            API Key <span className="text-red-500">*</span>
          </label>
          <input
            id="apiKey"
            type="password"
            {...register("apiKey")}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            placeholder="sk-..."
          />
          {errors.apiKey && (
            <p className="mt-1 text-sm text-red-600">{errors.apiKey.message}</p>
          )}
        </div>

        {/* Base URL Field */}
        <div>
          <label htmlFor="baseUrl" className="block text-sm font-medium text-slate-700">
            Base URL <span className="text-red-500">*</span>
          </label>
          <input
            id="baseUrl"
            type="url"
            {...register("baseUrl")}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            placeholder="https://api.openai.com/v1"
          />
          {errors.baseUrl && (
            <p className="mt-1 text-sm text-red-600">{errors.baseUrl.message}</p>
          )}
        </div>

        {/* Model Selection Field */}
        <div>
          <label htmlFor="model" className="block text-sm font-medium text-slate-700">
            Model <span className="text-red-500">*</span>
          </label>
          <select
            id="model"
            {...register("model")}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option value="">Select a model...</option>
            {availableModels.map((model) => (
              <option key={model.value} value={model.value}>
                {model.label}
              </option>
            ))}
          </select>
          {errors.model && <p className="mt-1 text-sm text-red-600">{errors.model.message}</p>}
        </div>

        {/* Submit Error */}
        {submitError && (
          <div className="rounded-md bg-red-50 p-4">
            <div className="flex">
              <AlertCircle className="h-5 w-5 text-red-400" />
              <div className="ml-3">
                <h3 className="text-sm font-medium text-red-800">Error</h3>
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
            className="inline-flex items-center rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Save Configuration
          </button>
        </div>
      </form>
    </div>
  );
}
