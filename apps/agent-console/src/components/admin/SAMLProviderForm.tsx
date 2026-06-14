import { useState, useEffect } from "react";
import { Upload, Link as LinkIcon, X } from "lucide-react";
import { z } from "zod";

import type { SAMLProvider, SAMLProviderCreatePayload, SAMLProviderUpdatePayload } from "../../features/tasks/api";
import { createSAMLProvider, updateSAMLProvider } from "../../features/tasks/api";
import { Button } from "../ui/button";
import { Input } from "../ui/input";

interface SAMLProviderFormProps {
  provider?: SAMLProvider | null;
  onSuccess: () => void;
  onCancel: () => void;
}

const samlProviderSchema = z.object({
  name: z.string().min(1, "Name is required"),
  entity_id: z.string().min(1, "Entity ID is required"),
  sso_url: z.string().url("Must be a valid URL"),
  idp_metadata_url: z.union([z.string().url("Must be a valid URL"), z.literal(""), z.null()]).optional(),
  idp_metadata_xml: z.union([z.string(), z.null()]).optional(),
});

type FormData = {
  name: string;
  entity_id: string;
  sso_url: string;
  idp_metadata_url: string;
  idp_metadata_xml: string;
};

type MetadataSource = "url" | "xml";

export function SAMLProviderForm({ provider, onSuccess, onCancel }: SAMLProviderFormProps) {
  const [formData, setFormData] = useState<FormData>({
    name: provider?.name ?? "",
    entity_id: provider?.entity_id ?? "",
    sso_url: provider?.sso_url ?? "",
    idp_metadata_url: provider?.idp_metadata_url ?? "",
    idp_metadata_xml: provider?.idp_metadata_xml ?? "",
  });
  const [metadataSource, setMetadataSource] = useState<MetadataSource>(
    provider?.idp_metadata_xml ? "xml" : "url",
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [xmlFile, setXmlFile] = useState<File | null>(null);

  useEffect(() => {
    if (provider) {
      setFormData({
        name: provider.name,
        entity_id: provider.entity_id,
        sso_url: provider.sso_url,
        idp_metadata_url: provider.idp_metadata_url ?? "",
        idp_metadata_xml: provider.idp_metadata_xml ?? "",
      });
      setMetadataSource(provider.idp_metadata_xml ? "xml" : "url");
    }
  }, [provider]);

  function handleChange(field: keyof FormData, value: string) {
    setFormData((prev) => ({
      ...prev,
      [field]: value,
    }));
    setErrors((prev) => ({
      ...prev,
      [field]: "",
    }));
  }

  async function handleFileUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    if (!file.name.endsWith(".xml")) {
      setErrors((prev) => ({
        ...prev,
        idp_metadata_xml: "File must be an XML file",
      }));
      return;
    }

    setXmlFile(file);

    try {
      const text = await file.text();
      setFormData((prev) => ({
        ...prev,
        idp_metadata_xml: text,
        idp_metadata_url: "",
      }));
      setErrors((prev) => ({
        ...prev,
        idp_metadata_xml: "",
      }));
    } catch (error) {
      setErrors((prev) => ({
        ...prev,
        idp_metadata_xml: error instanceof Error ? error.message : "Failed to read file",
      }));
    }
  }

  function removeFile() {
    setXmlFile(null);
    setFormData((prev) => ({
      ...prev,
      idp_metadata_xml: "",
    }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setErrors({});

    const payload: Record<string, unknown> = {
      name: formData.name,
      entity_id: formData.entity_id,
      sso_url: formData.sso_url,
    };

    if (metadataSource === "url" && formData.idp_metadata_url) {
      payload.idp_metadata_url = formData.idp_metadata_url;
      payload.idp_metadata_xml = null;
    } else if (metadataSource === "xml" && formData.idp_metadata_xml) {
      payload.idp_metadata_xml = formData.idp_metadata_xml;
      payload.idp_metadata_url = null;
    }

    try {
      samlProviderSchema.parse(payload);
    } catch (error) {
      if (error instanceof z.ZodError) {
        const fieldErrors: Record<string, string> = {};
        for (const issue of error.issues) {
          const field = issue.path[0] as string;
          fieldErrors[field] = issue.message;
        }
        setErrors(fieldErrors);
        return;
      }
    }

    setIsSubmitting(true);

    try {
      if (provider) {
        await updateSAMLProvider(provider.id, payload as SAMLProviderUpdatePayload);
      } else {
        await createSAMLProvider(payload as SAMLProviderCreatePayload);
      }
      onSuccess();
    } catch (error) {
      setErrors({
        _form: error instanceof Error ? error.message : "Failed to save provider",
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="space-y-4">
        <div>
          <label htmlFor="name" className="block text-sm font-medium text-slate-700 mb-1">
            Provider Name
          </label>
          <Input
            id="name"
            type="text"
            value={formData.name}
            onChange={(event) => handleChange("name", event.target.value)}
            placeholder="e.g., Okta, Azure AD"
          />
          {errors.name ? <p className="mt-1 text-xs text-red-600">{errors.name}</p> : null}
        </div>

        <div>
          <label htmlFor="entity_id" className="block text-sm font-medium text-slate-700 mb-1">
            Entity ID
          </label>
          <Input
            id="entity_id"
            type="text"
            value={formData.entity_id}
            onChange={(event) => handleChange("entity_id", event.target.value)}
            placeholder="e.g., https://app.example.com/saml/metadata"
          />
          {errors.entity_id ? <p className="mt-1 text-xs text-red-600">{errors.entity_id}</p> : null}
        </div>

        <div>
          <label htmlFor="sso_url" className="block text-sm font-medium text-slate-700 mb-1">
            SSO URL
          </label>
          <Input
            id="sso_url"
            type="text"
            value={formData.sso_url}
            onChange={(event) => handleChange("sso_url", event.target.value)}
            placeholder="e.g., https://idp.example.com/sso/saml"
          />
          {errors.sso_url ? <p className="mt-1 text-xs text-red-600">{errors.sso_url}</p> : null}
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-2">
            IdP Metadata
          </label>
          <div className="flex gap-4 mb-3">
            <button
              type="button"
              onClick={() => setMetadataSource("url")}
              className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm transition ${
                metadataSource === "url"
                  ? "bg-blue-100 text-blue-700 border border-blue-300"
                  : "bg-slate-100 text-slate-600 border border-slate-200 hover:bg-slate-200"
              }`}
            >
              <LinkIcon className="h-4 w-4" />
              Metadata URL
            </button>
            <button
              type="button"
              onClick={() => setMetadataSource("xml")}
              className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm transition ${
                metadataSource === "xml"
                  ? "bg-blue-100 text-blue-700 border border-blue-300"
                  : "bg-slate-100 text-slate-600 border border-slate-200 hover:bg-slate-200"
              }`}
            >
              <Upload className="h-4 w-4" />
              Upload XML
            </button>
          </div>

          {metadataSource === "url" ? (
            <div>
              <Input
                id="idp_metadata_url"
                type="text"
                value={formData.idp_metadata_url}
                onChange={(event) => handleChange("idp_metadata_url", event.target.value)}
                placeholder="e.g., https://idp.example.com/metadata.xml"
              />
              {errors.idp_metadata_url ? (
                <p className="mt-1 text-xs text-red-600">{errors.idp_metadata_url}</p>
              ) : null}
            </div>
          ) : (
            <div>
              <div className="flex items-center gap-3">
                <label
                  htmlFor="xml_file"
                  className="flex items-center gap-2 px-4 py-2 border border-slate-300 rounded-md cursor-pointer hover:bg-slate-50 transition text-sm text-slate-700"
                >
                  <Upload className="h-4 w-4" />
                  Choose XML File
                </label>
                <input
                  id="xml_file"
                  type="file"
                  accept=".xml"
                  onChange={handleFileUpload}
                  className="sr-only"
                />
                {xmlFile ? (
                  <div className="flex items-center gap-2 text-sm text-slate-600">
                    <span>{xmlFile.name}</span>
                    <button
                      type="button"
                      onClick={removeFile}
                      className="text-red-600 hover:text-red-700"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                ) : formData.idp_metadata_xml ? (
                  <span className="text-sm text-green-600">Metadata loaded</span>
                ) : null}
              </div>
              {errors.idp_metadata_xml ? (
                <p className="mt-1 text-xs text-red-600">{errors.idp_metadata_xml}</p>
              ) : null}
            </div>
          )}
        </div>
      </div>

      {errors._form ? (
        <div className="rounded-md bg-red-50 border border-red-200 p-3">
          <p className="text-sm text-red-800">{errors._form}</p>
        </div>
      ) : null}

      <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-200">
        <Button type="button" variant="secondary" onClick={onCancel} disabled={isSubmitting}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={isSubmitting}>
          {isSubmitting ? "Saving..." : provider ? "Update Provider" : "Create Provider"}
        </Button>
      </div>
    </form>
  );
}
