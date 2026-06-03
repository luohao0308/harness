import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, KeyRound, Loader2, Trash2 } from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { EmptyState } from "../../../components/ui/EmptyState";
import { Input } from "../../../components/ui/input";
import { SkeletonTable } from "../../../components/ui/Skeleton";
import { Table, Td, Th } from "../../../components/ui/table";
import { formatShortDate } from "../../../lib/utils";
import { createApiKey, listApiKeys, revokeApiKey } from "../../tasks/api";

const defaultScopes = ["run:read", "run:create", "agent:read"];

export function ApiKeysPage() {
  const queryClient = useQueryClient();
  const apiKeys = useQuery({ queryKey: ["settings", "api-keys"], queryFn: listApiKeys });
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState(defaultScopes.join(", "));
  const [createdKey, setCreatedKey] = useState("");
  const [message, setMessage] = useState("");

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["settings", "api-keys"] });
  const create = useMutation({
    mutationFn: createApiKey,
    onSuccess: (response) => {
      setCreatedKey(response.key);
      setName("");
      setMessage("");
      void invalidate();
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : "创建 API key 失败"),
  });
  const revoke = useMutation({
    mutationFn: revokeApiKey,
    onSuccess: () => void invalidate(),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    create.mutate({
      name,
      scopes: scopes
        .split(",")
        .map((scope) => scope.trim())
        .filter(Boolean),
    });
  }

  return (
    <ConsoleShell title="API Keys">
      <div className="space-y-4 p-4">
        <section className="grid gap-3 lg:grid-cols-[360px_minmax(0,1fr)]">
          <Card className="p-3">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900">
              <KeyRound className="h-4 w-4" />
              创建 API Key
            </div>
            <form className="space-y-3" onSubmit={submit}>
              <label className="block text-xs font-medium text-slate-600">
                名称
                <Input
                  className="mt-1 w-full"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  required
                />
              </label>
              <label className="block text-xs font-medium text-slate-600">
                权限 scope
                <Input
                  className="mt-1 w-full font-mono text-xs"
                  value={scopes}
                  onChange={(event) => setScopes(event.target.value)}
                />
              </label>
              {message ? <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{message}</div> : null}
              <Button type="submit" variant="primary" className="w-full" disabled={create.isPending}>
                {create.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <KeyRound className="h-3.5 w-3.5" />}
                创建
              </Button>
            </form>
            {createdKey ? (
              <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3">
                <div className="text-xs font-medium text-amber-800">明文 key 仅显示一次</div>
                <div className="mt-2 break-all rounded bg-white p-2 font-mono text-[11px] text-slate-700">
                  {createdKey}
                </div>
                <Button
                  className="mt-2 w-full"
                  onClick={() => void navigator.clipboard?.writeText(createdKey)}
                >
                  <Copy className="h-3.5 w-3.5" />
                  复制
                </Button>
              </div>
            ) : null}
          </Card>

          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <KeyRound className="h-4 w-4" />
                当前组织密钥
              </div>
              <Badge tone="neutral">{apiKeys.data?.length ?? 0}</Badge>
            </CardHeader>
            {apiKeys.isLoading ? (
              <SkeletonTable rows={6} columns={5} />
            ) : apiKeys.data?.length ? (
              <Table>
                <thead className="bg-slate-50 text-slate-500">
                  <tr>
                    <Th>名称</Th>
                    <Th>前缀</Th>
                    <Th>权限</Th>
                    <Th>最近使用</Th>
                    <Th className="text-right">状态</Th>
                  </tr>
                </thead>
                <tbody>
                  {apiKeys.data.map((key) => (
                    <tr key={key.id} className="border-t border-slate-100">
                      <Td>
                        <div className="font-medium text-slate-900">{key.name}</div>
                        <div className="font-mono text-[11px] text-slate-500">{formatShortDate(key.created_at)}</div>
                      </Td>
                      <Td className="font-mono">{key.key_prefix}</Td>
                      <Td className="max-w-sm truncate font-mono text-[11px] text-slate-500">
                        {key.scope_json.join(", ") || "inherit"}
                      </Td>
                      <Td className="font-mono text-slate-500">{formatShortDate(key.last_used_at)}</Td>
                      <Td className="text-right">
                        {key.revoked_at ? (
                          <Badge tone="failed">revoked</Badge>
                        ) : (
                          <Button variant="ghost" disabled={revoke.isPending} onClick={() => revoke.mutate(key.id)}>
                            <Trash2 className="h-3.5 w-3.5" />
                            撤销
                          </Button>
                        )}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            ) : (
              <div className="p-3">
                <EmptyState
                  icon={<KeyRound className="h-5 w-5" />}
                  title="暂无 API key"
                  description="创建后可用于服务端集成，撤销后立即失效。"
                />
              </div>
            )}
          </Card>
        </section>
      </div>
    </ConsoleShell>
  );
}
