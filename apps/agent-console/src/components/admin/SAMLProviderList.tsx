import { useState } from "react";
import { Trash2, Edit, Plus, TestTube2 } from "lucide-react";

import { deleteSAMLProvider, testSAMLConnection } from "../../features/tasks/api";
import type { SAMLProvider } from "../../features/tasks/api";
import { Button } from "../ui/button";
import { Table, Th, Td } from "../ui/table";

interface SAMLProviderListProps {
  providers: SAMLProvider[];
  onEdit: (provider: SAMLProvider) => void;
  onAdd: () => void;
  onRefresh: () => void;
}

export function SAMLProviderList({ providers, onEdit, onAdd, onRefresh }: SAMLProviderListProps) {
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, { status: string; message: string }>>({});

  async function handleDelete(providerId: string) {
    if (!confirm("Are you sure you want to delete this SAML provider?")) {
      return;
    }

    setDeletingId(providerId);
    try {
      await deleteSAMLProvider(providerId);
      onRefresh();
    } catch (error) {
      alert(error instanceof Error ? error.message : "Failed to delete provider");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleTestConnection(providerId: string) {
    setTestingId(providerId);
    setTestResults((prev) => ({
      ...prev,
      [providerId]: { status: "testing", message: "Testing connection..." },
    }));

    try {
      const result = await testSAMLConnection(providerId);
      setTestResults((prev) => ({
        ...prev,
        [providerId]: {
          status: result.status,
          message: result.status === "success" ? result.message : result.error ?? result.message,
        },
      }));
      onRefresh();
    } catch (error) {
      setTestResults((prev) => ({
        ...prev,
        [providerId]: {
          status: "failed",
          message: error instanceof Error ? error.message : "Connection test failed",
        },
      }));
    } finally {
      setTestingId(null);
    }
  }

  function formatDate(dateString: string) {
    return new Intl.DateTimeFormat("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(dateString));
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-900">SAML Providers</h2>
        <Button variant="primary" onClick={onAdd}>
          <Plus className="h-4 w-4" />
          Add Provider
        </Button>
      </div>

      {providers.length === 0 ? (
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-6 py-12 text-center">
          <p className="text-sm text-slate-600">No SAML providers configured</p>
          <Button variant="ghost" onClick={onAdd} className="mt-4">
            <Plus className="h-4 w-4" />
            Add your first provider
          </Button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          <Table>
            <thead className="border-b border-slate-200 bg-slate-50">
              <tr>
                <Th>Name</Th>
                <Th>Entity ID</Th>
                <Th>SSO URL</Th>
                <Th>Status</Th>
                <Th>Created</Th>
                <Th>Actions</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {providers.map((provider) => {
                const testResult = testResults[provider.id];
                return (
                  <tr key={provider.id} className="hover:bg-slate-50">
                    <Td className="font-medium text-slate-900">{provider.name}</Td>
                    <Td className="text-slate-600">{provider.entity_id}</Td>
                    <Td className="text-slate-600">
                      <span className="max-w-xs truncate block" title={provider.sso_url}>
                        {provider.sso_url}
                      </span>
                    </Td>
                    <Td>
                      <div className="space-y-1">
                        <span
                          className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                            provider.status === "active"
                              ? "bg-green-100 text-green-800"
                              : provider.status === "testing"
                                ? "bg-yellow-100 text-yellow-800"
                                : "bg-slate-100 text-slate-800"
                          }`}
                        >
                          {provider.status}
                        </span>
                        {testResult ? (
                          <div
                            className={`text-xs ${
                              testResult.status === "success"
                                ? "text-green-600"
                                : testResult.status === "failed"
                                  ? "text-red-600"
                                  : "text-slate-600"
                            }`}
                          >
                            {testResult.message}
                          </div>
                        ) : null}
                      </div>
                    </Td>
                    <Td className="text-slate-600">{formatDate(provider.created_at)}</Td>
                    <Td>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="ghost"
                          onClick={() => handleTestConnection(provider.id)}
                          disabled={testingId === provider.id}
                          title="Test Connection"
                        >
                          <TestTube2 className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          onClick={() => onEdit(provider)}
                          title="Edit"
                        >
                          <Edit className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          onClick={() => handleDelete(provider.id)}
                          disabled={deletingId === provider.id}
                          title="Delete"
                        >
                          <Trash2 className="h-4 w-4 text-red-600" />
                        </Button>
                      </div>
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        </div>
      )}
    </div>
  );
}
