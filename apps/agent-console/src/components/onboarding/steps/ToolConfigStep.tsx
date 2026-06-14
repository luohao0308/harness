import { zodResolver } from "@hookform/resolvers/zod";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

const toolConfigSchema = z.object({
  tools: z.array(z.string()).min(1, "Select at least one tool"),
});

type ToolConfigFormData = z.infer<typeof toolConfigSchema>;

export interface ToolConfigStepProps {
  onSubmit: (data: ToolConfigFormData) => void | Promise<void>;
  initialData?: Partial<ToolConfigFormData>;
}

interface Tool {
  id: string;
  name: string;
  description: string;
}

const availableTools: Tool[] = [
  {
    id: "web-search",
    name: "Web Search",
    description: "Search the web for current information and research",
  },
  {
    id: "code-execution",
    name: "Code Execution",
    description: "Execute code snippets in a sandboxed environment",
  },
  {
    id: "file-operations",
    name: "File Operations",
    description: "Read, write, and manage files in the workspace",
  },
  {
    id: "api-calls",
    name: "API Calls",
    description: "Make HTTP requests to external APIs",
  },
  {
    id: "database-query",
    name: "Database Query",
    description: "Query and interact with connected databases",
  },
];

export function ToolConfigStep({ onSubmit, initialData }: ToolConfigStepProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [selectedTools, setSelectedTools] = useState<string[]>(initialData?.tools || []);

  const {
    handleSubmit,
    setValue,
    formState: { errors },
  } = useForm<ToolConfigFormData>({
    resolver: zodResolver(toolConfigSchema),
    defaultValues: {
      tools: initialData?.tools || [],
    },
  });

  const handleToolToggle = (toolId: string) => {
    const newSelectedTools = selectedTools.includes(toolId)
      ? selectedTools.filter((id) => id !== toolId)
      : [...selectedTools, toolId];

    setSelectedTools(newSelectedTools);
    setValue("tools", newSelectedTools, { shouldValidate: true });
  };

  const handleFormSubmit = async (data: ToolConfigFormData) => {
    setIsSubmitting(true);
    setSubmitError(null);

    try {
      await onSubmit(data);
    } catch (error) {
      setSubmitError(
        error instanceof Error
          ? error.message
          : "Failed to save tool configuration. Please try again.",
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="animate-slide-up">
        <h2 className="text-2xl font-bold text-slate-900">Tool Configuration</h2>
        <p className="mt-2 text-sm text-slate-600">
          Select the tools your agent can use to perform tasks.
        </p>
      </div>

      <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-6">
        {/* Tools Selection */}
        <div className="animate-slide-up" style={{ animationDelay: "50ms" }}>
          <label className="block text-sm font-medium text-slate-700">
            Available Tools <span className="text-red-500" aria-label="required">*</span>
          </label>
          <p className="mt-1 text-xs text-slate-500">
            Select at least one tool for your agent
          </p>

          <div className="mt-4 space-y-3" role="group" aria-label="Available tools">
            {availableTools.map((tool, index) => {
              const isSelected = selectedTools.includes(tool.id);
              return (
                <label
                  key={tool.id}
                  className={`flex cursor-pointer items-start rounded-lg border p-4 transition-all duration-200 ${
                    isSelected
                      ? "border-blue-500 bg-blue-50 shadow-sm"
                      : "border-slate-200 bg-white hover:border-blue-200 hover:bg-slate-50 hover:shadow-sm"
                  }`}
                  style={{ animationDelay: `${100 + index * 50}ms` }}
                >
                  <div className="flex h-5 items-center">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => handleToolToggle(tool.id)}
                      className="h-4 w-4 rounded border-slate-300 text-blue-600 transition-colors focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                      disabled={isSubmitting}
                      aria-label={tool.name}
                    />
                  </div>
                  <div className="ml-3 flex-1">
                    <div className="font-medium text-slate-900">{tool.name}</div>
                    <div className="mt-1 text-sm text-slate-600">{tool.description}</div>
                  </div>
                  {isSelected && (
                    <CheckCircle2 className="ml-2 h-5 w-5 flex-shrink-0 animate-fade-in text-blue-600" aria-hidden="true" />
                  )}
                </label>
              );
            })}
          </div>

          {errors.tools && (
            <p className="mt-2 flex items-center gap-1 text-sm text-red-600" role="alert">
              <AlertCircle className="h-4 w-4" aria-hidden="true" />
              {errors.tools.message}
            </p>
          )}
        </div>

        {/* Selection Summary */}
        {selectedTools.length > 0 && (
          <div className="animate-slide-up rounded-lg border border-blue-200 bg-blue-50 p-4">
            <p className="text-sm text-blue-800">
              <span className="font-medium">{selectedTools.length}</span> tool{selectedTools.length !== 1 ? 's' : ''} selected
            </p>
          </div>
        )}

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
            aria-label="Save tools"
          >
            {isSubmitting && (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            )}
            {isSubmitting ? "Saving..." : "Save Tools"}
          </button>
        </div>
      </form>
    </div>
  );
}
