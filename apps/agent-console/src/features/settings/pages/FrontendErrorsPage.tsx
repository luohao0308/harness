import { useQuery } from "@tanstack/react-query";
import { Bug, Users } from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge } from "../../../components/ui/badge";
import { Card, CardHeader } from "../../../components/ui/card";
import { EmptyState } from "../../../components/ui/EmptyState";
import { SkeletonTable } from "../../../components/ui/Skeleton";
import { Table, Td, Th } from "../../../components/ui/table";
import { formatShortDate } from "../../../lib/utils";
import { listFrontendErrors, summarizeFrontendErrors } from "../../tasks/api";

export function FrontendErrorsPage() {
  const errors = useQuery({
    queryKey: ["settings", "frontend-errors"],
    queryFn: () => listFrontendErrors(100),
    refetchInterval: 30_000,
  });
  const summary = useQuery({
    queryKey: ["settings", "frontend-errors", "summary"],
    queryFn: summarizeFrontendErrors,
    refetchInterval: 30_000,
  });

  return (
    <ConsoleShell title="前端错误">
      <div className="space-y-4 p-4">
        <section className="grid gap-3 md:grid-cols-3">
          <Card className="p-3">
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <Bug className="h-4 w-4" />
              最近错误
            </div>
            <div className="mt-2 font-mono text-2xl font-semibold text-slate-950">
              {errors.data?.items.length ?? 0}
            </div>
          </Card>
          <Card className="p-3">
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <Users className="h-4 w-4" />
              影响用户
            </div>
            <div className="mt-2 font-mono text-2xl font-semibold text-slate-950">
              {summary.data?.items.reduce((total, item) => Math.max(total, item.affected_users), 0) ?? 0}
            </div>
          </Card>
          <Card className="p-3">
            <div className="text-xs text-slate-500">最高频错误</div>
            <div className="mt-2 truncate text-sm font-semibold text-slate-950">
              {summary.data?.items[0]?.error_message ?? "暂无"}
            </div>
          </Card>
        </section>

        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-slate-900">错误频次</div>
            <Badge tone="neutral">{summary.data?.items.length ?? 0}</Badge>
          </CardHeader>
          {summary.isLoading ? (
            <SkeletonTable rows={4} columns={4} />
          ) : summary.data?.items.length ? (
            <Table>
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <Th>错误</Th>
                  <Th>次数</Th>
                  <Th>影响用户</Th>
                  <Th>最近出现</Th>
                </tr>
              </thead>
              <tbody>
                {summary.data.items.map((item) => (
                  <tr key={item.error_message} className="border-t border-slate-100">
                    <Td className="max-w-xl truncate">{item.error_message}</Td>
                    <Td className="font-mono">{item.count}</Td>
                    <Td className="font-mono">{item.affected_users}</Td>
                    <Td className="font-mono text-slate-500">
                      {item.last_seen_at ? formatShortDate(item.last_seen_at) : "-"}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <div className="p-3">
              <EmptyState
                icon={<Bug className="h-5 w-5" />}
                title="暂无前端错误"
                description="ErrorBoundary 和全局错误上报捕获到异常后会出现在这里。"
              />
            </div>
          )}
        </Card>

        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-slate-900">最近明细</div>
            <Badge tone="neutral">{errors.data?.items.length ?? 0}</Badge>
          </CardHeader>
          {errors.isLoading ? (
            <SkeletonTable rows={6} columns={4} />
          ) : errors.data?.items.length ? (
            <div className="divide-y divide-slate-100">
              {errors.data.items.map((item) => (
                <details key={item.id} className="px-3 py-3 text-xs">
                  <summary className="cursor-pointer">
                    <span className="font-medium text-slate-900">{item.error_message}</span>
                    <span className="ml-2 font-mono text-[10px] text-slate-400">
                      {formatShortDate(item.created_at)}
                    </span>
                  </summary>
                  <div className="mt-2 rounded-md bg-slate-50 p-3 text-slate-600">
                    <div className="truncate font-mono text-[11px]">{item.url}</div>
                    {item.stack ? (
                      <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words">
                        {item.stack}
                      </pre>
                    ) : null}
                  </div>
                </details>
              ))}
            </div>
          ) : (
            <div className="p-3">
              <EmptyState
                icon={<Bug className="h-5 w-5" />}
                title="暂无错误明细"
                description="当前没有收到前端崩溃或未处理 Promise 拒绝。"
              />
            </div>
          )}
        </Card>
      </div>
    </ConsoleShell>
  );
}
