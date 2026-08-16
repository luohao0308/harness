import { zodResolver } from "@hookform/resolvers/zod";
import { AlertCircle, CheckCircle2, Loader2, Upload, X } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

const knowledgeBaseSchema = z.object({
  url: z.string().optional().refine(
    (val) => {
      if (!val || val.length === 0) return true;
      try {
        new URL(val);
        return true;
      } catch {
        return false;
      }
    },
    {
      message: "Invalid URL format",
    }
  ),
  files: z.array(z.instanceof(File)).optional(),
}).refine(
  (data) => {
    const hasUrl = data.url && data.url.length > 0;
    const hasFiles = data.files && data.files.length > 0;
    return hasUrl || hasFiles;
  },
  {
    message: "Please provide either a URL or upload at least one file",
    path: ["url"],
  }
);

type KnowledgeBaseFormData = z.infer<typeof knowledgeBaseSchema>;

export interface KnowledgeBaseStepProps {
  onSubmit: (data: KnowledgeBaseFormData) => void | Promise<void>;
  initialData?: Partial<KnowledgeBaseFormData>;
}

export function KnowledgeBaseStep({ onSubmit, initialData }: KnowledgeBaseStepProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors, touchedFields },
  } = useForm<KnowledgeBaseFormData>({
    resolver: zodResolver(knowledgeBaseSchema),
    defaultValues: initialData,
    mode: "onTouched",
  });

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    const newFiles = [...uploadedFiles, ...files];
    setUploadedFiles(newFiles);
    setValue("files", newFiles, { shouldValidate: true });
  };

  const handleRemoveFile = (index: number) => {
    const newFiles = uploadedFiles.filter((_, i) => i !== index);
    setUploadedFiles(newFiles);
    setValue("files", newFiles, { shouldValidate: true });
  };

  const handleFormSubmit = async (data: KnowledgeBaseFormData) => {
    setIsSubmitting(true);
    setSubmitError(null);

    try {
      await onSubmit(data);
    } catch (error) {
      setSubmitError(
        error instanceof Error
          ? error.message
          : "Failed to configure knowledge base. Please try again.",
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="animate-slide-up">
        <h2 className="text-2xl font-bold text-slate-900">Knowledge Base Setup</h2>
        <p className="mt-2 text-sm text-slate-600">
          Upload documents or provide URLs to build your agent's knowledge base.
        </p>
      </div>

      <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-6">
        {/* URL Input */}
        <div className="animate-slide-up" style={{ animationDelay: "50ms" }}>
          <label htmlFor="url" className="block text-sm font-medium text-slate-700">
            Add URL
          </label>
          <p className="mt-1 text-xs text-slate-500">
            Provide a URL to documentation or knowledge source
          </p>
          <input
            id="url"
            type="text"
            {...register("url")}
            className="mt-2 block w-full rounded-md border border-slate-300 px-3 py-2 shadow-sm transition-all duration-200 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-500"
            placeholder="https://example.com/docs"
            disabled={isSubmitting}
            aria-invalid={errors.url ? "true" : "false"}
            aria-describedby={errors.url ? "url-error" : undefined}
          />
          {errors.url ? (
            <p id="url-error" className="mt-1 flex items-center gap-1 text-sm text-red-600" role="alert">
              <AlertCircle className="h-4 w-4" aria-hidden="true" />
              {errors.url.message}
            </p>
          ) : touchedFields.url ? (
            <p className="mt-1 flex items-center gap-1 text-sm text-green-600">
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              Valid URL
            </p>
          ) : null}
        </div>

        {/* File Upload */}
        <div className="animate-slide-up" style={{ animationDelay: "100ms" }}>
          <label className="block text-sm font-medium text-slate-700">
            Upload Files
          </label>
          <p className="mt-1 text-xs text-slate-500">
            Upload PDFs, text files, or markdown documents
          </p>
          <div className="mt-2">
            <label
              htmlFor="file-upload"
              className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition-all duration-200 hover:bg-slate-50 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 active:scale-95"
            >
              <Upload className="h-4 w-4" aria-hidden="true" />
              Choose Files
            </label>
            <input
              id="file-upload"
              type="file"
              multiple
              accept=".pdf,.txt,.md"
              onChange={handleFileChange}
              className="sr-only"
              disabled={isSubmitting}
              aria-label="Upload files"
            />
          </div>

          {/* Uploaded Files List */}
          {uploadedFiles.length > 0 && (
            <div className="mt-4 space-y-2" role="list" aria-label="Uploaded files">
              {uploadedFiles.map((file, index) => (
                <div
                  key={index}
                  className="flex animate-slide-up items-center justify-between rounded-md border border-slate-200 bg-slate-50 px-3 py-2 transition-colors hover:bg-slate-100"
                  role="listitem"
                >
                  <span className="text-sm text-slate-700">{file.name}</span>
                  <button
                    type="button"
                    onClick={() => handleRemoveFile(index)}
                    className="rounded text-slate-400 transition-colors hover:text-red-600 focus:outline-none focus:ring-2 focus:ring-red-500"
                    aria-label={`Remove ${file.name}`}
                    disabled={isSubmitting}
                  >
                    <X className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
              ))}
            </div>
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
            aria-label="Save knowledge base"
          >
            {isSubmitting && (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            )}
            {isSubmitting ? "Saving..." : "Save Knowledge Base"}
          </button>
        </div>
      </form>
    </div>
  );
}
