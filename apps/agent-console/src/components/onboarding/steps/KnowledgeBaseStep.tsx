import { zodResolver } from "@hookform/resolvers/zod";
import { AlertCircle, Loader2, Upload, X } from "lucide-react";
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
    formState: { errors },
  } = useForm<KnowledgeBaseFormData>({
    resolver: zodResolver(knowledgeBaseSchema),
    defaultValues: initialData,
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
      setSubmitError(error instanceof Error ? error.message : "Failed to configure knowledge base");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-slate-900">Knowledge Base Setup</h2>
        <p className="mt-2 text-sm text-slate-600">
          Upload documents or provide URLs to build your agent's knowledge base.
        </p>
      </div>

      <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-6">
        {/* URL Input */}
        <div>
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
            className="mt-2 block w-full rounded-md border border-slate-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            placeholder="https://example.com/docs"
          />
          {errors.url && (
            <p className="mt-1 text-sm text-red-600">{errors.url.message}</p>
          )}
        </div>

        {/* File Upload */}
        <div>
          <label className="block text-sm font-medium text-slate-700">
            Upload Files
          </label>
          <p className="mt-1 text-xs text-slate-500">
            Upload PDFs, text files, or markdown documents
          </p>
          <div className="mt-2">
            <label
              htmlFor="file-upload"
              className="inline-flex cursor-pointer items-center rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
            >
              <Upload className="mr-2 h-4 w-4" />
              Choose Files
            </label>
            <input
              id="file-upload"
              type="file"
              multiple
              accept=".pdf,.txt,.md"
              onChange={handleFileChange}
              className="sr-only"
            />
          </div>

          {/* Uploaded Files List */}
          {uploadedFiles.length > 0 && (
            <div className="mt-4 space-y-2">
              {uploadedFiles.map((file, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between rounded-md border border-slate-200 bg-slate-50 px-3 py-2"
                >
                  <span className="text-sm text-slate-700">{file.name}</span>
                  <button
                    type="button"
                    onClick={() => handleRemoveFile(index)}
                    className="text-slate-400 hover:text-red-600"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
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
            Save Knowledge Base
          </button>
        </div>
      </form>
    </div>
  );
}
