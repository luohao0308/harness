import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { GitBranch } from "lucide-react";
import { Link } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { formatShortDate } from "../../../lib/utils";
import { listTaskSubagents, listTasks } from "../../tasks/api";

function contextSummary(context: Record<string, unknown>) {
  const label = context.label;
  const goal = context.goal;
  if (typeof label === "string" && label.length > 0) return label;
  if (typeof goal === "string" && goal.length > 0) return goal;
  return "子 Agent 上下文";
}

export function SubagentsPage() {
  const tasksQuery = useQuery({ queryKey: ["tasks"], queryFn: listTasks });
  const tasks = tasksQuery.data?.items ?? [];
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const activeTaskId = selectedTaskId ?? tasks[0]?.id ?? null;
  const activeTask = useMemo(
    () => tasks.find((task) => task.id === activeTaskId) ?? null,
    [activeTaskId, tasks],
  );
  const subagentsQuery = useQuery({
    queryKey: ["task-subagents", activeTaskId],
    queryFn: () => listTaskSubagents(activeTaskId!),
    enabled: Boolean(activeTaskId),
  });
  const subagents = subagentsQuery.data?.items ?? [];

  return (
    <ConsoleShell title="子 Agent">
      <div className="mx-auto max-w-[1440px] p-6">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 text-lg font-semibold tracking-tight text-slate-900">
              <GitBranch className="h-4 w-4" /> 子 Agent 编排
            </div>
            <div className="mt-1 text-xs text-slate-500">
              选择任务后查看其派生出的异步子 Agent 状态、上下文与超时边界。
            </div>
          </div>
          {activeTask && (
            <Button>
              <Link to={`/tasks/${activeTask.id}/subagents`}>进入任务详情</Link>
            </Button>
          )}
        </div>

        <div className="grid grid-cols-12 gap-4">
          <Card className="col-span-4 overflow-hidden">
            <div className="border-b border-slate-100 px-3 py-2 text-xs font-semibold text-slate-900">
              最近任务
            </div>
            <div className="max-h-[640px] overflow-auto p-2">
              {tasksQuery.isLoading && <div className="p-3 text-xs text-slate-500">任务加载中...</div>}
              {!tasksQuery.isLoading && tasks.length === 0 && (
                <div className="p-3 text-xs text-slate-500">暂无任务。创建任务后会显示子 Agent 状态。</div>
              )}
              {tasks.map((task) => (
                <button
                  key={task.id}
                  onClick={() => setSelectedTaskId(task.id)}
                  className={
                    task.id === activeTaskId
                      ? "mb-1 w-full rounded-md border border-slate-300 bg-slate-100 px-3 py-2 text-left"
                      : "mb-1 w-full rounded-md border border-transparent px-3 py-2 text-left hover:bg-slate-50"
                  }
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="truncate text-sm text-slate-900">{task.title}</span>
                    <span className="font-mono text-[10px] text-slate-400">{task.id.slice(0, 8)}</span>
                  </div>
                  <div className="mt-1 truncate text-[11px] text-slate-500">{task.goal}</div>
                </button>
              ))}
            </div>
          </Card>

          <Card className="col-span-8 overflow-hidden">
            <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
              <div>
                <div className="text-xs font-semibold text-slate-900">
                  {activeTask ? activeTask.title : "子 Agent 列表"}
                </div>
                <div className="mt-0.5 text-[11px] text-slate-500">
                  {activeTask
                    ? `任务 ${activeTask.id.slice(0, 8)} · 上限 ${activeTask.max_subagents}`
                    : "未选择任务"}
                </div>
              </div>
              <span className="text-xs text-slate-500">
                {subagentsQuery.isLoading ? "加载中..." : `${subagents.length} 个子 Agent`}
              </span>
            </div>
            <Table>
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <Th>子 Agent</Th>
                  <Th>状态</Th>
                  <Th>开始时间</Th>
                  <Th>完成时间</Th>
                  <Th>超时时间</Th>
                </tr>
              </thead>
              <tbody>
                {subagents.map((subagent) => (
                  <tr key={subagent.id} className="border-t border-slate-100 hover:bg-slate-50/60">
                    <Td>
                      <div className="font-mono text-xs text-slate-900">{subagent.id.slice(0, 8)}</div>
                      <div className="mt-0.5 truncate text-[11px] text-slate-500">
                        {contextSummary(subagent.context_json)}
                      </div>
                    </Td>
                    <Td>
                      <Badge tone={statusTone(subagent.status)}>{subagent.status}</Badge>
                    </Td>
                    <Td className="font-mono text-slate-500">
                      {subagent.started_at ? formatShortDate(subagent.started_at) : "-"}
                    </Td>
                    <Td className="font-mono text-slate-500">
                      {subagent.completed_at ? formatShortDate(subagent.completed_at) : "-"}
                    </Td>
                    <Td className="font-mono text-slate-500">
                      {subagent.timeout_at ? formatShortDate(subagent.timeout_at) : "-"}
                    </Td>
                  </tr>
                ))}
                {!subagentsQuery.isLoading && activeTask && subagents.length === 0 && (
                  <tr>
                    <Td colSpan={5} className="py-12 text-center text-slate-500">
                      当前任务没有派生子 Agent。触发长耗时拆分任务后，这里会展示并发状态。
                    </Td>
                  </tr>
                )}
              </tbody>
            </Table>
          </Card>
        </div>
      </div>
    </ConsoleShell>
  );
}
