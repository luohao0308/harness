import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Database, Download, Loader2, Play, Trash2 } from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { EmptyState } from "../../../components/ui/EmptyState";
import { Input } from "../../../components/ui/input";
import { SkeletonTable } from "../../../components/ui/Skeleton";
import { Table, Td, Th } from "../../../components/ui/table";
import { formatShortDate } from "../../../lib/utils";
import { useAuth } from "../../auth/AuthProvider";
import {
  createOrganizationExport,
  deleteOrganization,
  listOrganizationExports,
  listRetentionPolicies,
  listRetentionRuns,
  previewOrganizationDeletion,
  runRetentionNow,
  updateRetentionPolicy,
  type RetentionPolicy,
} from "../../tasks/api";

export function DataManagementPage() {
  const queryClient = useQueryClient();
  const { currentOrganization } = useAuth();
  const orgId = currentOrganization?.id ?? "";
  const policies = useQuery({
    queryKey: ["settings", "retention", "policies"],
    queryFn: listRetentionPolicies,
  });
  const runs = useQuery({
    queryKey: ["settings", "retention", "runs"],
    queryFn: listRetentionRuns,
  });
  const exportsQuery = useQuery({
    queryKey: ["settings", "data-exports", orgId],
    queryFn: () => listOrganizationExports(orgId),
    enabled: Boolean(orgId),
  });
  const [policyDrafts, setPolicyDrafts] = useState<Record<string, { retention_days: string; delete_after_days: string; enabled: boolean }>>({});
  const [deleteInput, setDeleteInput] = useState("");
  const [deleteMessage, setDeleteMessage] = useState("");

  const refreshRetention = () => {
    void queryClient.invalidateQueries({ queryKey: ["settings", "retention"] });
    void queryClient.invalidateQueries({ queryKey: ["settings", "data-exports", orgId] });
  };
  const updatePolicy = useMutation({
    mutationFn: ({ policy, draft }: { policy: RetentionPolicy; draft: { retention_days: string; delete_after_days: string; enabled: boolean } }) =>
      updateRetentionPolicy(policy.id, {
        retention_days: draft.retention_days ? Number(draft.retention_days) : undefined,
        delete_after_days: draft.delete_after_days ? Number(draft.delete_after_days) : undefined,
        enabled: draft.enabled,
      }),
    onSuccess: refreshRetention,
  });
  const runRetention = useMutation({
    mutationFn: runRetentionNow,
    onSuccess: refreshRetention,
  });
  const exportOrg = useMutation({
    mutationFn: () => createOrganizationExport(orgId),
    onSuccess: refreshRetention,
  });
  const dryRunDelete = useMutation({
    mutationFn: () => previewOrganizationDeletion(orgId),
  });
  const confirmDelete = useMutation({
    mutationFn: () => deleteOrganization(orgId, deleteInput),
    onSuccess: (response) => {
      setDeleteMessage(`删除完成：${Object.values(response.deleted_counts_json).reduce((sum, value) => sum + value, 0)} 行`);
      void queryClient.invalidateQueries();
    },
    onError: (error) => setDeleteMessage(error instanceof Error ? error.message : "删除失败"),
  });

  const exportSize = useMemo(
    () => (exportsQuery.data?.items ?? []).reduce((sum, item) => sum + item.size_bytes, 0),
    [exportsQuery.data?.items],
  );

  return (
    <ConsoleShell title="数据生命周期">
      <div className="space-y-4 p-4">
        <section className="grid gap-3 md:grid-cols-3">
          <Card className="p-3">
            <div className="text-xs text-slate-500">Retention policy</div>
            <div className="mt-2 font-mono text-2xl font-semibold text-slate-950">{policies.data?.items.length ?? 0}</div>
          </Card>
          <Card className="p-3">
            <div className="text-xs text-slate-500">最近 retention run</div>
            <div className="mt-2 font-mono text-2xl font-semibold text-slate-950">{runs.data?.items.length ?? 0}</div>
          </Card>
          <Card className="p-3">
            <div className="text-xs text-slate-500">导出文件大小</div>
            <div className="mt-2 font-mono text-2xl font-semibold text-slate-950">{Math.round(exportSize / 1024)} KB</div>
          </Card>
        </section>

        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Archive className="h-4 w-4" />
              Retention Policies
            </div>
            <Button onClick={() => runRetention.mutate()} disabled={runRetention.isPending}>
              {runRetention.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
              手动运行
            </Button>
          </CardHeader>
          {policies.isLoading ? (
            <SkeletonTable rows={8} columns={6} />
          ) : policies.data?.items.length ? (
            <Table>
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <Th>实体</Th>
                  <Th>动作</Th>
                  <Th>保留天数</Th>
                  <Th>归档清理</Th>
                  <Th>启用</Th>
                  <Th className="text-right">操作</Th>
                </tr>
              </thead>
              <tbody>
                {policies.data.items.map((policy) => {
                  const draft = policyDrafts[policy.id] ?? {
                    retention_days: String(policy.retention_days ?? ""),
                    delete_after_days: String(policy.delete_after_days ?? ""),
                    enabled: policy.enabled,
                  };
                  const immutable = policy.action === "keep";
                  return (
                    <tr key={policy.id} className="border-t border-slate-100">
                      <Td>
                        <div className="font-mono text-slate-900">{policy.entity_type}</div>
                        <div className="text-[11px] text-slate-500">{policy.organization_id ? "org override" : "system default"}</div>
                      </Td>
                      <Td><Badge tone={policy.action === "delete" ? "failed" : policy.action === "archive" ? "warning" : "success"}>{policy.action}</Badge></Td>
                      <Td>
                        <Input
                          className="w-24 font-mono text-xs"
                          type="number"
                          min={1}
                          disabled={immutable}
                          value={draft.retention_days}
                          onChange={(event) => setPolicyDrafts((current) => ({
                            ...current,
                            [policy.id]: { ...draft, retention_days: event.target.value },
                          }))}
                        />
                      </Td>
                      <Td>
                        <Input
                          className="w-24 font-mono text-xs"
                          type="number"
                          min={1}
                          disabled={immutable}
                          value={draft.delete_after_days}
                          onChange={(event) => setPolicyDrafts((current) => ({
                            ...current,
                            [policy.id]: { ...draft, delete_after_days: event.target.value },
                          }))}
                        />
                      </Td>
                      <Td>
                        <input
                          type="checkbox"
                          checked={draft.enabled}
                          onChange={(event) => setPolicyDrafts((current) => ({
                            ...current,
                            [policy.id]: { ...draft, enabled: event.target.checked },
                          }))}
                          className="h-4 w-4"
                        />
                      </Td>
                      <Td className="text-right">
                        <Button
                          disabled={updatePolicy.isPending || immutable}
                          onClick={() => updatePolicy.mutate({ policy, draft })}
                        >
                          保存
                        </Button>
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          ) : (
            <div className="p-3">
              <EmptyState
                icon={<Archive className="h-5 w-5" />}
                title="暂无 retention policy"
                description="系统默认策略应由 migration seed 创建。"
              />
            </div>
          )}
        </Card>

        <section className="grid gap-3 xl:grid-cols-2">
          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Download className="h-4 w-4" />
                数据导出
              </div>
              <Button onClick={() => exportOrg.mutate()} disabled={!orgId || exportOrg.isPending}>
                {exportOrg.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                导出全部数据
              </Button>
            </CardHeader>
            {exportsQuery.isLoading ? (
              <SkeletonTable rows={4} columns={4} />
            ) : exportsQuery.data?.items.length ? (
              <Table>
                <thead className="bg-slate-50 text-slate-500">
                  <tr>
                    <Th>ID</Th>
                    <Th>状态</Th>
                    <Th>文件</Th>
                    <Th>SHA256</Th>
                    <Th>时间</Th>
                  </tr>
                </thead>
                <tbody>
                  {exportsQuery.data.items.map((item) => (
                    <tr key={item.id} className="border-t border-slate-100">
                      <Td className="max-w-44 break-all font-mono text-[11px] text-slate-600">{item.id}</Td>
                      <Td><Badge tone={statusTone(item.status.toUpperCase())}>{item.status}</Badge></Td>
                      <Td className="max-w-48 truncate font-mono text-[11px] text-slate-600">{item.file_path ?? "-"}</Td>
                      <Td className="max-w-48 truncate font-mono text-[11px] text-slate-500">{item.file_sha256 ?? "-"}</Td>
                      <Td className="font-mono text-slate-500">{formatShortDate(item.completed_at ?? item.requested_at)}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            ) : (
              <div className="p-3">
                <EmptyState
                  icon={<Download className="h-5 w-5" />}
                  title="暂无导出"
                  description="导出会生成本地 JSON 包、哈希和过期时间。"
                />
              </div>
            )}
          </Card>

          <Card className="p-3">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-red-700">
              <Trash2 className="h-4 w-4" />
              删除组织
            </div>
            <Button variant="danger" disabled={!orgId || dryRunDelete.isPending} onClick={() => dryRunDelete.mutate()}>
              {dryRunDelete.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Database className="h-3.5 w-3.5" />}
              生成 dry-run
            </Button>
            {dryRunDelete.data ? (
              <form
                className="mt-3 space-y-3"
                onSubmit={(event: FormEvent) => {
                  event.preventDefault();
                  setDeleteMessage("");
                  confirmDelete.mutate();
                }}
              >
                <div className="rounded-md bg-slate-50 p-3">
                  <div className="text-xs font-medium text-slate-700">影响行数</div>
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    {Object.entries(dryRunDelete.data.counts).map(([table, count]) => (
                      <div key={table} className="rounded-md bg-white p-2">
                        <div className="truncate font-mono text-[11px] text-slate-500">{table}</div>
                        <div className="font-mono text-lg font-semibold text-slate-950">{count}</div>
                      </div>
                    ))}
                  </div>
                </div>
                <label className="block text-xs font-medium text-slate-600">
                  输入组织名称确认：{dryRunDelete.data.confirmation_name}
                  <Input
                    className="mt-1 w-full"
                    value={deleteInput}
                    onChange={(event) => setDeleteInput(event.target.value)}
                  />
                </label>
                <Button
                  type="submit"
                  variant="danger"
                  disabled={confirmDelete.isPending || deleteInput !== dryRunDelete.data.confirmation_name}
                >
                  {confirmDelete.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                  确认删除
                </Button>
              </form>
            ) : null}
            {deleteMessage ? <div className="mt-3 rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-700">{deleteMessage}</div> : null}
          </Card>
        </section>

        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Play className="h-4 w-4" />
              最近运行
            </div>
            <Badge tone="neutral">{runs.data?.items.length ?? 0}</Badge>
          </CardHeader>
          {runs.isLoading ? (
            <SkeletonTable rows={4} columns={5} />
          ) : runs.data?.items.length ? (
            <Table>
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <Th>实体</Th>
                  <Th>动作</Th>
                  <Th>删除</Th>
                  <Th>归档</Th>
                  <Th>完成</Th>
                </tr>
              </thead>
              <tbody>
                {runs.data.items.map((run) => (
                  <tr key={run.id} className="border-t border-slate-100">
                    <Td className="font-mono">{run.entity_type}</Td>
                    <Td>{run.action}</Td>
                    <Td className="font-mono">{run.deleted_count}</Td>
                    <Td className="font-mono">{run.archived_count}</Td>
                    <Td className="font-mono text-slate-500">{formatShortDate(run.finished_at)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <div className="p-3">
              <EmptyState
                icon={<Play className="h-5 w-5" />}
                title="暂无运行记录"
                description="手动运行或计划任务执行后会写入 retention_runs。"
              />
            </div>
          )}
        </Card>
      </div>
    </ConsoleShell>
  );
}
