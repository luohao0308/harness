import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, Filter, MoreHorizontal } from "lucide-react";
import { Link } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Dot } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { formatShortDate } from "../../../lib/utils";
import { listTasks } from "../api";
import { TaskStatusBadge } from "../components/TaskStatusBadge";

const statCards = [
  ["Running tasks", "12", "+3 vs 1h", "running"],
  ["Failed today", "4", "0.6% rate", "failed"],
  ["Avg duration", "6m 12s", "p95 18m", "neutral"],
  ["WarmPool hit rate", "94.2%", "target >= 90%", "success"],
] as const;

export function TaskListPage() {
  const tasksQuery = useQuery({ queryKey: ["tasks"], queryFn: listTasks });
  const tasks = tasksQuery.data?.items ?? [];

  return (
    <ConsoleShell title="Tasks">
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
            {["Status: any", "Owner: any", "Model: any", "Created: 24h", "Sandbox: enabled"].map(
              (filter) => (
                <Button key={filter} className="gap-1.5">
                  <Filter className="h-3 w-3" /> {filter}
                </Button>
              ),
            )}
          </div>
          <span className="text-xs text-slate-500">
            {tasksQuery.isLoading ? "Loading tasks..." : `Showing ${tasks.length} tasks`}
          </span>
        </div>

        <Card className="overflow-hidden">
          <Table>
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <Th>Task Name</Th>
                <Th>Status</Th>
                <Th>Model</Th>
                <Th>Sandbox</Th>
                <Th>Network</Th>
                <Th>Created</Th>
                <Th>Updated</Th>
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
                  <Td className="text-slate-600">{task.enable_sandbox ? "enabled" : "-"}</Td>
                  <Td className={task.enable_network ? "text-amber-600" : "text-slate-500"}>
                    {task.enable_network ? "enabled" : "disabled"}
                  </Td>
                  <Td className="font-mono text-slate-500">{formatShortDate(task.created_at)}</Td>
                  <Td className="font-mono text-slate-500">{formatShortDate(task.updated_at)}</Td>
                  <Td className="text-right">
                    <div className="inline-flex items-center gap-1 text-slate-400">
                      <Link to={`/tasks/${task.id}`} className="hover:text-slate-700">
                        <ArrowUpRight className="h-3.5 w-3.5" />
                      </Link>
                      <button className="hover:text-slate-700" aria-label="More actions">
                        <MoreHorizontal className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </Td>
                </tr>
              ))}
              {!tasksQuery.isLoading && tasks.length === 0 && (
                <tr>
                  <Td colSpan={8} className="py-12 text-center text-slate-500">
                    No tasks yet. Create one to see the event stream.
                  </Td>
                </tr>
              )}
            </tbody>
          </Table>
          <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/40 px-3 py-2 text-[11px] text-slate-500">
            <span>auto-refresh via query invalidation</span>
            <div className="flex gap-1">
              <Button>Prev</Button>
              <Button>Next</Button>
            </div>
          </div>
        </Card>
      </div>
    </ConsoleShell>
  );
}
