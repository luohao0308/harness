import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { ArrowUpRight, Bot, History } from "lucide-react";
import { Link } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { EmptyState } from "../../../components/ui/EmptyState";
import { SkeletonTable } from "../../../components/ui/Skeleton";
import { Table, Td, Th } from "../../../components/ui/table";
import { TermHint } from "../../../components/ui/term";
import { VirtualList } from "../../../components/ui/VirtualList";
import { useI18n } from "../../../lib/i18n";
import { statusLabel } from "../../../lib/labels";
import { formatShortDate } from "../../../lib/utils";
import { getObservabilitySummary, listRunsPage, type Task } from "../../tasks/api";

export function RunHistoryPage() {
  const { text } = useI18n();
  const runs = useInfiniteQuery({
    queryKey: ["agent-runs", "cursor"],
    queryFn: ({ pageParam }) => listRunsPage({ cursor: pageParam, limit: 50 }),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor,
  });
  const summary = useQuery({ queryKey: ["observability-summary"], queryFn: getObservabilitySummary });
  const items = runs.data?.pages.flatMap((page) => page.items) ?? [];
  const running =
    summary.data?.tasks_by_status.find((item) => item.name === "RUNNING")?.count ?? 0;
  const failed = summary.data?.failed_task_total ?? 0;

  return (
    <ConsoleShell title={text("智能体运行历史", "Agent Runs")}>
      <div className="space-y-4 p-4">
        <section className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-slate-200 bg-white px-4 py-3 shadow-sm">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-slate-100 text-slate-600">
              <History className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <div className="text-sm font-semibold text-slate-950">
                {text("运行历史", "Run History")}
              </div>
              <div className="mt-0.5 flex flex-wrap gap-3 text-xs text-slate-500">
                <span>{text(`${items.length} 个运行`, `${items.length} runs`)}</span>
                <span>{text(`运行中 ${running}`, `${running} running`)}</span>
                <span>{text(`失败 ${failed}`, `${failed} failed`)}</span>
              </div>
            </div>
          </div>
          <Link to="/agents/default/workspace">
            <Button variant="primary">
              <Bot className="h-3.5 w-3.5" />
              {text("工作台", "Workspace")}
            </Button>
          </Link>
        </section>

        <Card className="overflow-hidden">
          <CardHeader>
            <div className="text-sm font-semibold text-slate-900">
              {text("运行列表", "Run List")}
            </div>
            <div className="flex items-center gap-2 text-xs text-slate-500">
              {runs.isLoading ? <span>{text("加载中...", "Loading...")}</span> : null}
              {runs.hasNextPage ? (
                <button
                  type="button"
                  className="rounded-md border border-slate-200 px-2 py-1 text-slate-600 hover:bg-slate-50"
                  onClick={() => runs.fetchNextPage()}
                  disabled={runs.isFetchingNextPage}
                >
                  {runs.isFetchingNextPage ? text("加载中", "Loading") : text("加载更多", "Load more")}
                </button>
              ) : null}
            </div>
          </CardHeader>
          {runs.isLoading ? (
            <SkeletonTable rows={7} columns={6} />
          ) : items.length === 0 ? (
            <div className="p-3">
              <EmptyState
                icon={<History className="h-5 w-5" />}
                title={text("暂无智能体运行", "No Agent Runs yet")}
                description={text(
                  "从智能体工作台输入目标并生成计划后，运行历史会在这里按更新时间展示。",
                  "Start from Agent Workspace and generate a Plan to populate run history.",
                )}
                actions={[
                  {
                    label: text("打开工作台", "Open Workspace"),
                    href: "/agents/default/workspace",
                    primary: true,
                  },
                ]}
              />
            </div>
          ) : (
            <div className="min-w-[860px]" role="region" aria-label={text("运行列表", "Run List")}>
              <Table className="table-fixed">
                <thead className="bg-slate-50 text-slate-500">
                  <tr>
                    <Th className="w-[34%]">运行</Th>
                    <Th className="w-[12%]">{text("状态", "Status")}</Th>
                    <Th className="w-[18%]">{text("模型", "Model")}</Th>
                    <Th>
                      <TermHint description="智能体运行平台">运行平台</TermHint>
                    </Th>
                    <Th className="w-[14%]">{text("更新时间", "Updated")}</Th>
                    <Th className="w-12" />
                  </tr>
                </thead>
              </Table>
              <VirtualList
                items={items}
                estimateSize={64}
                height={Math.min(620, Math.max(260, items.length * 64))}
                renderItem={(run) => (
                  <Table className="table-fixed">
                    <tbody>
                      <RunRow run={run} />
                    </tbody>
                  </Table>
                )}
              />
            </div>
          )}
        </Card>
      </div>
    </ConsoleShell>
  );
}

function RunRow({ run }: { run: Task }) {
  return (
    <tr className="border-t border-slate-100 hover:bg-slate-50/60">
      <Td>
        <Link to={`/runs/${run.id}`} className="font-medium text-slate-950 hover:underline">
          {run.title}
        </Link>
        <div className="mt-1 flex items-center gap-2">
          <span className="font-mono text-[10px] text-slate-400">{run.id.slice(0, 8)}</span>
          <span className="truncate text-[11px] text-slate-500">{run.goal}</span>
        </div>
      </Td>
      <Td>
        <Badge tone={statusTone(run.status)}>{statusLabel(run.status)}</Badge>
      </Td>
      <Td className="font-mono text-slate-600">
        {run.model_provider}/{run.model_name}
      </Td>
      <Td>
        <div className="flex flex-wrap gap-1">
          {run.enable_sandbox && <Badge tone="warning">沙箱</Badge>}
          {run.enable_network && <Badge tone="info">网络</Badge>}
          <Badge tone="purple">子代理{run.max_subagents}</Badge>
        </div>
      </Td>
      <Td className="font-mono text-slate-500">{formatShortDate(run.updated_at)}</Td>
      <Td className="text-right">
        <Link to={`/runs/${run.id}`} className="inline-flex text-slate-400 hover:text-slate-800">
          <ArrowUpRight className="h-4 w-4" />
        </Link>
      </Td>
    </tr>
  );
}
