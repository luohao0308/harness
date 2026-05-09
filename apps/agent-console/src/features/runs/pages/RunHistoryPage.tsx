import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, Bot, Clock, GitBranch, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { useI18n } from "../../../lib/i18n";
import { formatShortDate } from "../../../lib/utils";
import { getObservabilitySummary, listRuns, type Task } from "../../tasks/api";

export function RunHistoryPage() {
  const { text } = useI18n();
  const runs = useQuery({ queryKey: ["agent-runs"], queryFn: listRuns });
  const summary = useQuery({ queryKey: ["observability-summary"], queryFn: getObservabilitySummary });
  const items = runs.data?.items ?? [];
  const running =
    summary.data?.tasks_by_status.find((item) => item.name === "RUNNING")?.count ?? 0;
  const failed = summary.data?.failed_task_total ?? 0;

  return (
    <ConsoleShell title={text("Agent Run 历史", "Agent Runs")}>
      <div className="space-y-4 p-4">
        <section className="grid grid-cols-12 gap-4">
          <Card className="col-span-8 p-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-950">
                  <GitBranch className="h-4 w-4" />
                  {text("Agent Run 审计历史", "Agent Run Audit History")}
                </div>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
                  {text(
                    "这里只展示 Agent Workspace 产生的运行记录。底层 tasks 表保留为兼容存储，产品语义统一为 Agent Run。",
                    "This page shows runs produced by Agent Workspace. The tasks table remains only as compatibility storage; product language is Agent Run.",
                  )}
                </p>
              </div>
              <Link to="/agents/default/workspace">
                <Button variant="primary">
                  <Bot className="h-3.5 w-3.5" />
                  {text("打开 Agent Workspace", "Open Agent Workspace")}
                </Button>
              </Link>
            </div>
          </Card>
          <MetricCard label={text("运行中", "Running")} value={String(running)} icon={<Clock className="h-4 w-4" />} />
          <MetricCard label={text("失败", "Failed")} value={String(failed)} icon={<ShieldCheck className="h-4 w-4" />} />
        </section>

        <Card className="overflow-hidden">
          <CardHeader>
            <div className="text-sm font-semibold text-slate-900">
              {text("Run 列表", "Run List")}
            </div>
            <div className="text-xs text-slate-500">
              {runs.isLoading
                ? text("加载中...", "Loading...")
                : text(`${items.length} 个 Run`, `${items.length} runs`)}
            </div>
          </CardHeader>
          <Table>
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <Th>Run</Th>
                <Th>{text("状态", "Status")}</Th>
                <Th>{text("模型", "Model")}</Th>
                <Th>{text("Harness", "Harness")}</Th>
                <Th>{text("更新时间", "Updated")}</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {items.map((run) => (
                <RunRow key={run.id} run={run} />
              ))}
              {!runs.isLoading && items.length === 0 && (
                <tr>
                  <Td colSpan={6} className="py-12 text-center text-slate-500">
                    {text(
                      "暂无 Agent Run。请从 Agent Workspace 输入目标并生成 Plan。",
                      "No Agent Runs yet. Start from Agent Workspace and generate a Plan.",
                    )}
                  </Td>
                </tr>
              )}
            </tbody>
          </Table>
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
        <Badge tone={statusTone(run.status)}>{run.status}</Badge>
      </Td>
      <Td className="font-mono text-slate-600">
        {run.model_provider}/{run.model_name}
      </Td>
      <Td>
        <div className="flex flex-wrap gap-1">
          {run.enable_sandbox && <Badge tone="warning">Sandbox</Badge>}
          {run.enable_network && <Badge tone="info">Network</Badge>}
          <Badge tone="purple">Subagents {run.max_subagents}</Badge>
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

function MetricCard({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
}) {
  return (
    <Card className="col-span-2 p-4">
      <div className="flex items-center justify-between text-slate-500">
        <span className="text-xs">{label}</span>
        {icon}
      </div>
      <div className="mt-2 font-mono text-2xl text-slate-950">{value}</div>
    </Card>
  );
}
