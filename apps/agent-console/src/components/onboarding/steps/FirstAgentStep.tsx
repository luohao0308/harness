import { zodResolver } from "@hookform/resolvers/zod";
import { AlertCircle, Loader2 } from "lucide-react";
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
    formState: { errors },
  } = useForm<FirstAgentFormData>({
    resolver: zodResolver(firstAgentSchema),
    defaultValues: initialData,
  });

  const systemPromptValue = watch("systemPrompt", "");

  const handleFormSubmit = async (data: FirstAgentFormData) => {
    setIsSubmitting(true);
    setSubmitError(null);

    try {
      await onSubmit(data);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Failed to create agent");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-slate-900">Create Your First Agent</h2>
        <p className="mt-2 text-sm text-slate-600">
          Define your agent's identity and behavior with a name, description, and system prompt.
        </p>
      </div>

      <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-6">
        {/* Agent Name Field */}
        <div>
          <label htmlFor="name" className="block text-sm font-medium text-slate-700">
            Agent Name <span className="text-red-500">*</span>
          </label>
          <input
            id="name"
            type="text"
            {...register("name")}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            placeholder="e.g., Customer Support Agent"
          />
          {errors.name && (
            <p className="mt-1 text-sm text-red-600">{errors.name.message}</p>
          )}
        </div>

        {/* Description Field */}
        <div>
          <label htmlFor="description" className="block text-sm font-medium text-slate-700">
            Description <span className="text-red-500">*</span>
          </label>
          <textarea
            id="description"
            rows={3}
            {...register("description")}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            placeholder="Describe what this agent does..."
          />
          {errors.description && (
            <p className="mt-1 text-sm text-red-600">{errors.description.message}</p>
          )}
        </div>

        {/* System Prompt Field */}
        <div>
          <label htmlFor="systemPrompt" className="block text-sm font-medium text-slate-700">
            System Prompt <span className="text-red-500">*</span>
          </label>
          <textarea
            id="systemPrompt"
            rows={6}
            {...register("systemPrompt")}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            placeholder="You are a helpful assistant that..."
          />
          <div className="mt-1 flex items-center justify-between">
            <div>
              {errors.systemPrompt && (
                <p className="text-sm text-red-600">{errors.systemPrompt.message}</p>
              )}
            </div>
            <p className="text-xs text-slate-500">
              {systemPromptValue.length} / 2000 characters
            </p>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            The system prompt defines how your agent behaves and responds to requests.
          </p>
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
            Save Agent
          </button>
        </div>
      </form>
    </div>
  );
}
