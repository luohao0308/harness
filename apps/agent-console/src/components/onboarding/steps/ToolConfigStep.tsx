import { zodResolver } from "@hookform/resolvers/zod";
import { AlertCircle, Loader2 } from "lucide-react";
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
      setSubmitError(error instanceof Error ? error.message : "Failed to save tool configuration");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-slate-900">Tool Configuration</h2>
        <p className="mt-2 text-sm text-slate-600">
          Select the tools your agent can use to perform tasks.
        </p>
      </div>

      <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-6">
        {/* Tools Selection */}
        <div>
          <label className="block text-sm font-medium text-slate-700">
            Available Tools <span className="text-red-500">*</span>
          </label>
          <p className="mt-1 text-xs text-slate-500">
            Select at least one tool for your agent
          </p>

          <div className="mt-4 space-y-3">
            {availableTools.map((tool) => {
              const isSelected = selectedTools.includes(tool.id);
              return (
                <label
                  key={tool.id}
                  className={`flex cursor-pointer items-start rounded-lg border p-4 transition-colors ${
                    isSelected
                      ? "border-blue-500 bg-blue-50"
                      : "border-slate-200 bg-white hover:bg-slate-50"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => handleToolToggle(tool.id)}
                    className="mt-1 h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-2 focus:ring-blue-500"
                    aria-label={tool.name}
                  />
                  <div className="ml-3 flex-1">
                    <div className="font-medium text-slate-900">{tool.name}</div>
                    <div className="mt-1 text-sm text-slate-600">{tool.description}</div>
                  </div>
                </label>
              );
            })}
          </div>

          {errors.tools && (
            <p className="mt-2 text-sm text-red-600">{errors.tools.message}</p>
          )}
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
            Save Tools
          </button>
        </div>
      </form>
    </div>
  );
}
