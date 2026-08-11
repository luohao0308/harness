import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ExternalLink, KeyRound, Loader2 } from "lucide-react";
import { Navigate, useNavigate } from "react-router-dom";

import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import {
  getLocalRuntimeModelStatus,
  type LocalRuntimeModelStatus,
} from "../../tasks/api";
import {
  getDesktopLocalRuntimeApi,
  isLocalRuntimeProfile,
  isLocalWebExtension,
} from "../../../lib/local-runtime";

export function LocalRuntimeModelSetupPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const modelStatus = useQuery({
    queryKey: ["local-runtime", "model-status"],
    queryFn: getLocalRuntimeModelStatus,
    retry: false,
  });
  const desktopApi = getDesktopLocalRuntimeApi();
  const webExtension = isLocalWebExtension();

  const save = useMutation({
    mutationFn: async () => {
      if (!desktopApi?.setModelApiKey) {
        throw new Error("Model API keys can only be saved from Harness Desktop.");
      }
      const status = await desktopApi.setModelApiKey(apiKey.trim());
      await modelStatus.refetch();
      return status;
    },
    onSuccess: async (status) => {
      setApiKey("");
      queryClient.setQueryData(["local-runtime", "model-status"], status);
      await queryClient.invalidateQueries({ queryKey: ["local-runtime", "model-status"] });
      navigate("/agents/default/workspace", { replace: true });
    },
    onError: (saveError) => {
      setError(saveError instanceof Error ? saveError.message : "Unable to save model API key");
    },
  });

  if (!isLocalRuntimeProfile()) {
    return <Navigate to="/settings/models" replace />;
  }

  const status = modelStatus.data;
  const sessionOnly = status?.secret_storage === "session";

  function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!apiKey.trim()) {
      setError("Enter the model API key.");
      return;
    }
    save.mutate();
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-8">
      <section className="w-full max-w-md rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-slate-900 text-white">
              <KeyRound className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <h1 className="text-base font-semibold text-slate-950">Connect your model</h1>
              <p className="mt-0.5 text-xs text-slate-500">
                {status?.provider || "Default provider"} · {status?.model || "Shipped model"}
              </p>
            </div>
          </div>
          <ModelStateBadge status={status} loading={modelStatus.isLoading} />
        </div>

        {webExtension ? (
          <div className="mt-5 rounded-md border border-slate-200 bg-slate-50 p-3">
            <div className="flex gap-2 text-sm font-medium text-slate-800">
              <ExternalLink className="mt-0.5 h-4 w-4 shrink-0" />
              Open Harness Desktop to add or replace the API key.
            </div>
            <p className="mt-1.5 text-xs leading-5 text-slate-600">
              The Web Extension can inspect model status, but it never receives or writes model secrets.
            </p>
          </div>
        ) : (
          <form className="mt-5" onSubmit={submit}>
            <label className="text-xs font-medium text-slate-700" htmlFor="local-runtime-api-key">
              Model API key
            </label>
            <Input
              id="local-runtime-api-key"
              className="mt-1.5 w-full font-mono"
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="sk-..."
              disabled={save.isPending}
            />
            <p className="mt-2 text-xs leading-5 text-slate-500">
              The key is sent only to Desktop secure storage. It is never saved in browser storage or SQLite.
            </p>
            {sessionOnly ? (
              <div className="mt-3 flex gap-2 rounded-md border border-amber-200 bg-amber-50 p-2.5 text-xs text-amber-800">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                Secure storage is unavailable. This key lasts for this session and must be entered again after restart.
              </div>
            ) : null}
            {error ? <p className="mt-3 text-xs text-red-600" role="alert">{error}</p> : null}
            <Button
              className="mt-4 w-full"
              variant="primary"
              type="submit"
              disabled={save.isPending || modelStatus.isLoading}
            >
              {save.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
              {save.isPending ? "Checking connection..." : "Save and continue"}
            </Button>
          </form>
        )}

        {modelStatus.isError ? (
          <p className="mt-4 text-xs text-red-600" role="alert">
            {modelStatus.error instanceof Error ? modelStatus.error.message : "Unable to load model status"}
          </p>
        ) : null}
      </section>
    </main>
  );
}

function ModelStateBadge({
  status,
  loading,
}: {
  status: LocalRuntimeModelStatus | null | undefined;
  loading: boolean;
}) {
  if (loading) return <Badge tone="pending">Loading</Badge>;
  if (status?.state === "healthy") return <Badge tone="success">Healthy</Badge>;
  if (status?.state === "configured") return <Badge tone="info">Configured</Badge>;
  if (status?.state === "error") return <Badge tone="failed">Needs attention</Badge>;
  return <Badge tone="warning">Setup required</Badge>;
}
