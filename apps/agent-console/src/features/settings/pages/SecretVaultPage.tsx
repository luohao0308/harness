import { FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DatabaseZap, KeyRound, Loader2, ShieldCheck, Trash2 } from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { EmptyState } from "../../../components/ui/EmptyState";
import { Input } from "../../../components/ui/input";
import { SkeletonTable } from "../../../components/ui/Skeleton";
import { Table, Td, Th } from "../../../components/ui/table";
import { formatShortDate } from "../../../lib/utils";
import { useAuth } from "../../auth/AuthProvider";
import {
  deleteStoredSecret,
  importEnvSecrets,
  listStoredSecrets,
  saveStoredSecret,
  type StoredSecret,
  type StoredSecretUpsertPayload,
} from "../../tasks/api";

const purposes: StoredSecretUpsertPayload["purpose"][] = [
  "model_provider",
  "knowledge_connector",
  "mcp_runtime",
  "web_research",
  "notification_channel",
];

const purposeLabels: Record<string, string> = {
  model_provider: "模型",
  knowledge_connector: "知识连接器",
  mcp_runtime: "MCP Runtime",
  web_research: "Web Research",
  notification_channel: "通知通道",
};

export function SecretVaultPage() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const secrets = useQuery({ queryKey: ["settings", "secrets"], queryFn: listStoredSecrets });
  const isAdmin = user?.role === "admin";
  const [scope, setScope] = useState<"user" | "org">("user");
  const [provider, setProvider] = useState("deepseek-pro");
  const [purpose, setPurpose] = useState<StoredSecretUpsertPayload["purpose"]>("model_provider");
  const [secretRef, setSecretRef] = useState("");
  const [secretValue, setSecretValue] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!isAdmin && scope === "org") {
      setScope("user");
    }
  }, [isAdmin, scope]);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["settings", "secrets"] });
  const saveMutation = useMutation({
    mutationFn: saveStoredSecret,
    onSuccess: () => {
      setSecretValue("");
      setMessage("密钥已保存");
      void invalidate();
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : "保存失败"),
  });
  const deleteMutation = useMutation({
    mutationFn: ({ id, scope }: { id: string; scope: string }) => deleteStoredSecret(id, scope),
    onSuccess: () => void invalidate(),
  });
  const importMutation = useMutation({
    mutationFn: importEnvSecrets,
    onSuccess: (response) => {
      setMessage(`已导入 ${response.imported.length} 个环境变量密钥`);
      void invalidate();
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : "导入失败"),
  });

  const grouped = useMemo(() => {
    const items = secrets.data?.items ?? [];
    return {
      user: items.filter((item) => item.scope === "user"),
      org: items.filter((item) => item.scope === "org"),
    };
  }, [secrets.data?.items]);

  function submit(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    saveMutation.mutate({
      scope,
      provider,
      purpose,
      secret_ref: secretRef.trim() || null,
      secret_value: secretValue,
    });
  }

  return (
    <ConsoleShell title="密钥库">
      <div className="space-y-4 p-4">
        <section className="grid gap-3 lg:grid-cols-[360px_minmax(0,1fr)]">
          <Card className="p-3">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900">
              <KeyRound className="h-4 w-4" />
              保存业务密钥
            </div>
            <form className="space-y-3" onSubmit={submit}>
              <div className={isAdmin ? "grid grid-cols-2 gap-2" : "grid gap-2"}>
                <button
                  type="button"
                  className={scopeButtonClass(scope === "user")}
                  onClick={() => setScope("user")}
                >
                  我的密钥
                </button>
                {isAdmin ? (
                  <button
                    type="button"
                    className={scopeButtonClass(scope === "org")}
                    onClick={() => setScope("org")}
                  >
                    组织共享
                  </button>
                ) : null}
              </div>
              <label className="block text-xs font-medium text-slate-600">
                Provider
                <Input className="mt-1 w-full font-mono text-xs" value={provider} onChange={(event) => setProvider(event.target.value)} required />
              </label>
              <label className="block text-xs font-medium text-slate-600">
                Purpose
                <select
                  className="mt-1 h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-xs"
                  value={purpose}
                  onChange={(event) => setPurpose(event.target.value as StoredSecretUpsertPayload["purpose"])}
                >
                  {purposes.map((item) => (
                    <option key={item} value={item}>
                      {purposeLabels[item]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-xs font-medium text-slate-600">
                Secret Ref
                <Input className="mt-1 w-full font-mono text-xs" value={secretRef} onChange={(event) => setSecretRef(event.target.value)} placeholder="secret://models/deepseek-pro/api-key" />
              </label>
              <label className="block text-xs font-medium text-slate-600">
                密钥值
                <Input className="mt-1 w-full font-mono text-xs" type="password" value={secretValue} onChange={(event) => setSecretValue(event.target.value)} required />
              </label>
              {message ? <div className="rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">{message}</div> : null}
              <Button type="submit" variant="primary" className="w-full" disabled={saveMutation.isPending}>
                {saveMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}
                加密保存
              </Button>
              {isAdmin ? (
                <Button type="button" className="w-full" disabled={importMutation.isPending} onClick={() => importMutation.mutate()}>
                  {importMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <DatabaseZap className="h-3.5 w-3.5" />}
                  导入环境变量
                </Button>
              ) : null}
            </form>
          </Card>

          <div className="space-y-3">
            <SecretTable
              title="我的密钥"
              items={grouped.user}
              loading={secrets.isLoading}
              deleting={deleteMutation.isPending}
              canDelete
              onDelete={(secret) => deleteMutation.mutate({ id: secret.id, scope: secret.scope })}
            />
            <SecretTable
              title="组织共享"
              items={grouped.org}
              loading={secrets.isLoading}
              deleting={deleteMutation.isPending}
              canDelete={isAdmin}
              onDelete={(secret) => deleteMutation.mutate({ id: secret.id, scope: secret.scope })}
            />
          </div>
        </section>
      </div>
    </ConsoleShell>
  );
}

function SecretTable({
  title,
  items,
  loading,
  deleting,
  canDelete,
  onDelete,
}: {
  title: string;
  items: StoredSecret[];
  loading: boolean;
  deleting: boolean;
  canDelete: boolean;
  onDelete: (secret: StoredSecret) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
          <KeyRound className="h-4 w-4" />
          {title}
        </div>
        <Badge tone="neutral">{items.length}</Badge>
      </CardHeader>
      {loading ? (
        <SkeletonTable rows={4} columns={5} />
      ) : items.length ? (
        <Table>
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <Th>Provider</Th>
              <Th>Purpose</Th>
              <Th>Ref</Th>
              <Th>更新</Th>
              <Th className="text-right">状态</Th>
            </tr>
          </thead>
          <tbody>
            {items.map((secret) => (
              <tr key={secret.id} className="border-t border-slate-100">
                <Td className="font-mono text-xs">{secret.provider}</Td>
                <Td>{purposeLabels[secret.purpose] ?? secret.purpose}</Td>
                <Td className="max-w-[260px] truncate font-mono text-[11px] text-slate-500">{secret.secret_ref ?? "-"}</Td>
                <Td className="font-mono text-slate-500">{formatShortDate(secret.updated_at)}</Td>
                <Td className="text-right">
                  <div className="inline-flex items-center gap-2">
                    <Badge tone={secret.configured ? "success" : "neutral"}>{sourceLabel(secret.source)}</Badge>
                    {canDelete ? (
                      <Button variant="ghost" disabled={deleting} onClick={() => onDelete(secret)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    ) : null}
                  </div>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      ) : (
        <div className="p-3">
          <EmptyState icon={<KeyRound className="h-5 w-5" />} title="暂无密钥" description="保存后只显示配置状态，密钥值不会回显。" />
        </div>
      )}
    </Card>
  );
}

function scopeButtonClass(active: boolean) {
  return [
    "h-8 rounded-md border text-xs font-medium",
    active ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white text-slate-600",
  ].join(" ");
}

function sourceLabel(source: string) {
  const labels: Record<string, string> = {
    stored_secret_user: "用户密钥",
    stored_secret_org: "组织密钥",
    stored_secret: "密钥库",
    db_user: "用户密钥",
    db_org: "组织密钥",
    db: "密钥库",
    env_legacy: "Env 兼容",
  };
  return labels[source] ?? source;
}
