import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, Filter, MoreHorizontal } from "lucide-react";
import { Link } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Dot } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { enabledLabel } from "../../../lib/labels";
import { formatShortDate } from "../../../lib/utils";
import { listTasks } from "../api";
import { TaskStatusBadge } from "../components/TaskStatusBadge";

const statCards = [
  ["运行任务", "12", "较 1 小时前 +3", "running"],
  ["今日失败", "4", "失败率 0.6%", "failed"],
  ["平均耗时", "6m 12s", "p95 18m", "neutral"],
  ["WarmPool 命中率", "94.2%", "目标 >= 90%", "success"],
] as const;

export function TaskListPage() {
  const tasksQuery = useQuery({ queryKey: ["tasks"], queryFn: listTasks });
  const tasks = tasksQuery.data?.items ?? [];

  return (
    <ConsoleShell title="任务">
      <div className="mx-auto max-w-[1440px] p-6">
        <div className="mb-5 grid grid-cols-4 gap-3">
          {statCards.map(([title, value, subtitle, tone]) => (
            <Card key={title} className="p-4">
              <div className="text-[11px] tracking-wide text-slate-500">{title}</div>
              <div className="mt-1 flex items-baseline gap-2">
                <div className="text-[22px] tracking-tight text-slate-900">{value}</div>
                <Dot tone={tone} />
              </div>
              <div className="mt-1 text-[11px] text-slate-500">{subtitle}</div>
            </Card>
          ))}
        </div>

        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs">
            {["状态：全部", "负责人：全部", "模型：全部", "创建：24h", "沙箱：已启用"].map(
              (filter) => (
                <Button key={filter} className="gap-1.5">
                  <Filter className="h-3 w-3" /> {filter}
                </Button>
              ),
            )}
          </div>
          <span className="text-xs text-slate-500">
            {tasksQuery.isLoading ? "任务加载中..." : `当前显示 ${tasks.length} 个任务`}
          </span>
        </div>

        <Card className="overflow-hidden">
          <Table>
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <Th>任务名称</Th>
                <Th>状态</Th>
                <Th>模型</Th>
                <Th>沙箱</Th>
                <Th>网络</Th>
                <Th>创建时间</Th>
                <Th>更新时间</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => (
                <tr key={task.id} className="border-t border-slate-100 hover:bg-slate-50/60">
                  <Td>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] text-slate-400">
                        {task.id.slice(0, 8)}
                      </span>
                      <Link to={`/tasks/${task.id}`} className="text-slate-900 hover:underline">
                        {task.title}
                      </Link>
                    </div>
                    <div className="mt-0.5 truncate text-[11px] text-slate-500">{task.goal}</div>
                  </Td>
                  <Td>
                    <TaskStatusBadge status={task.status} />
                  </Td>
                  <Td className="font-mono text-slate-600">{task.model_name}</Td>
                  <Td className="text-slate-600">{enabledLabel(task.enable_sandbox)}</Td>
                  <Td className={task.enable_network ? "text-amber-600" : "text-slate-500"}>
                    {enabledLabel(task.enable_network)}
                  </Td>
                  <Td className="font-mono text-slate-500">{formatShortDate(task.created_at)}</Td>
                  <Td className="font-mono text-slate-500">{formatShortDate(task.updated_at)}</Td>
                  <Td className="text-right">
                    <div className="inline-flex items-center gap-1 text-slate-400">
                      <Link to={`/tasks/${task.id}`} className="hover:text-slate-700">
                        <ArrowUpRight className="h-3.5 w-3.5" />
                      </Link>
                      <button className="hover:text-slate-700" aria-label="更多操作">
                        <MoreHorizontal className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </Td>
                </tr>
              ))}
              {!tasksQuery.isLoading && tasks.length === 0 && (
                <tr>
                  <Td colSpan={8} className="py-12 text-center text-slate-500">
                    暂无任务。创建任务后将在这里看到事件流。
                  </Td>
                </tr>
              )}
            </tbody>
          </Table>
          <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/40 px-3 py-2 text-[11px] text-slate-500">
            <span>通过查询缓存失效自动刷新</span>
            <div className="flex gap-1">
              <Button>上一页</Button>
              <Button>下一页</Button>
            </div>
          </div>
        </Card>
      </div>
    </ConsoleShell>
  );
}
