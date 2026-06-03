import { FormEvent, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, FileText, Search } from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { EmptyState } from "../../../components/ui/EmptyState";
import { Input } from "../../../components/ui/input";
import { SkeletonTable } from "../../../components/ui/Skeleton";
import { Table, Td, Th } from "../../../components/ui/table";
import { formatShortDate } from "../../../lib/utils";
import { downloadAuditCsv, listAuditEvents } from "../../tasks/api";

export function AuditLogPage() {
  const [actorId, setActorId] = useState("");
  const [action, setAction] = useState("");
  const [resourceType, setResourceType] = useState("");
  const [filters, setFilters] = useState({ actor_id: "", action: "", resource_type: "" });
  const [downloadError, setDownloadError] = useState("");
  const audit = useQuery({
    queryKey: ["settings", "audit", filters],
    queryFn: () => listAuditEvents({ ...filters, limit: 100 }),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setFilters({
      actor_id: actorId,
      action,
      resource_type: resourceType,
    });
  }

  async function exportCsv() {
    setDownloadError("");
    try {
      const { blob, filename } = await downloadAuditCsv();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : "导出失败");
    }
  }

  return (
    <ConsoleShell title="审计日志">
      <div className="space-y-4 p-4">
        <Card className="p-3">
          <form className="grid gap-3 md:grid-cols-[1fr_1fr_1fr_auto_auto]" onSubmit={submit}>
            <Input
              value={actorId}
              onChange={(event) => setActorId(event.target.value)}
              placeholder="actor_id"
              className="font-mono text-xs"
            />
            <Input
              value={action}
              onChange={(event) => setAction(event.target.value)}
              placeholder="action"
              className="font-mono text-xs"
            />
            <Input
              value={resourceType}
              onChange={(event) => setResourceType(event.target.value)}
              placeholder="resource_type"
              className="font-mono text-xs"
            />
            <Button type="submit">
              <Search className="h-3.5 w-3.5" />
              过滤
            </Button>
            <Button type="button" onClick={() => void exportCsv()}>
              <Download className="h-3.5 w-3.5" />
              CSV
            </Button>
          </form>
          {downloadError ? <div className="mt-3 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{downloadError}</div> : null}
        </Card>

        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <FileText className="h-4 w-4" />
              管理操作
            </div>
            <Badge tone="neutral">{audit.data?.items.length ?? 0}</Badge>
          </CardHeader>
          {audit.isLoading ? (
            <SkeletonTable rows={8} columns={5} />
          ) : audit.data?.items.length ? (
            <Table>
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <Th>时间</Th>
                  <Th>操作</Th>
                  <Th>资源</Th>
                  <Th>Actor</Th>
                  <Th>Payload</Th>
                </tr>
              </thead>
              <tbody>
                {audit.data.items.map((event) => (
                  <tr key={event.id} className="border-t border-slate-100 align-top">
                    <Td className="font-mono text-slate-500">{formatShortDate(event.created_at)}</Td>
                    <Td className="font-mono text-slate-900">{event.action}</Td>
                    <Td>
                      <div className="font-mono text-[11px] text-slate-900">{event.resource_type}</div>
                      <div className="max-w-48 truncate font-mono text-[11px] text-slate-500">{event.resource_id}</div>
                    </Td>
                    <Td className="font-mono text-[11px] text-slate-500">{event.actor_id ?? "-"}</Td>
                    <Td>
                      <details>
                        <summary className="cursor-pointer text-xs text-slate-600">查看</summary>
                        <pre className="mt-2 max-h-40 max-w-xl overflow-auto rounded-md bg-slate-50 p-2 text-[11px] text-slate-600">
                          {JSON.stringify(event.payload_json, null, 2)}
                        </pre>
                      </details>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <div className="p-3">
              <EmptyState
                icon={<FileText className="h-5 w-5" />}
                title="暂无审计事件"
                description="用户、API key、retention、导出等管理操作会写入这里。"
              />
            </div>
          )}
        </Card>
      </div>
    </ConsoleShell>
  );
}
