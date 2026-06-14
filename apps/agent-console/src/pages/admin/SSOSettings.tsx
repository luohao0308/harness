import { useState, useEffect } from "react";

import type { SAMLProvider } from "../../features/tasks/api";
import { listSAMLProviders } from "../../features/tasks/api";
import { SAMLProviderList } from "../../components/admin/SAMLProviderList";
import { SAMLProviderForm } from "../../components/admin/SAMLProviderForm";
import { ConfigDialog } from "../../components/ui/config-dialog";

export default function SSOSettings() {
  const [providers, setProviders] = useState<SAMLProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingProvider, setEditingProvider] = useState<SAMLProvider | null>(null);

  async function loadProviders() {
    setLoading(true);
    setError(null);
    try {
      const data = await listSAMLProviders();
      setProviders(data);
    } catch (error_) {
      setError(error_ instanceof Error ? error_.message : "Failed to load SAML providers");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadProviders();
  }, []);

  function handleAdd() {
    setEditingProvider(null);
    setIsFormOpen(true);
  }

  function handleEdit(provider: SAMLProvider) {
    setEditingProvider(provider);
    setIsFormOpen(true);
  }

  function handleFormSuccess() {
    setIsFormOpen(false);
    setEditingProvider(null);
    loadProviders();
  }

  function handleFormCancel() {
    setIsFormOpen(false);
    setEditingProvider(null);
  }

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-blue-600 border-r-transparent" />
          <p className="mt-3 text-sm text-slate-600">Loading SSO settings...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="rounded-lg border border-red-200 bg-red-50 px-6 py-4 text-center">
          <p className="text-sm text-red-800">{error}</p>
          <button
            onClick={loadProviders}
            className="mt-3 text-sm text-red-600 hover:text-red-700 underline"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-semibold text-slate-900">SSO Settings</h1>
          <p className="mt-1 text-sm text-slate-600">
            Configure SAML 2.0 Single Sign-On providers for your organization
          </p>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
          <SAMLProviderList
            providers={providers}
            onEdit={handleEdit}
            onAdd={handleAdd}
            onRefresh={loadProviders}
          />
        </div>
      </div>

      <ConfigDialog
        open={isFormOpen}
        title={editingProvider ? "Edit SAML Provider" : "Add SAML Provider"}
        description={
          editingProvider
            ? "Update the configuration for this SAML provider"
            : "Configure a new SAML 2.0 identity provider for SSO"
        }
        onClose={handleFormCancel}
      >
        <SAMLProviderForm
          provider={editingProvider}
          onSuccess={handleFormSuccess}
          onCancel={handleFormCancel}
        />
      </ConfigDialog>
    </div>
  );
}
