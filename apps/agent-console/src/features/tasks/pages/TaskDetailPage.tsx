import { useEffect, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Download, Play } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { EventTimeline } from "../../events/components/EventTimeline";
import { useTaskEventStream } from "../../events/useTaskEventStream";
import { SandboxPanel } from "../../sandboxes/components/SandboxPanel";
import { SubagentPanel } from "../../subagents/components/SubagentPanel";
import { getTask, listTaskEvents, startTask } from "../api";
import { ExecutionPlanPanel } from "../components/ExecutionPlanPanel";
import { TaskResultPanel } from "../components/TaskResultPanel";
import { TaskStatusBadge } from "../components/TaskStatusBadge";

export function TaskDetailPage({ focus }: { focus?: "events" | "subagents" }) {
  const { taskId } = useParams();
  const queryClient = useQueryClient();
  const taskQuery = useQuery({
    queryKey: ["task", taskId],
    queryFn: () => getTask(taskId!),
    enabled: Boolean(taskId),
  });
  const eventQuery = useQuery({
    queryKey: ["task-events", taskId],
    queryFn: () => listTaskEvents(taskId!),
    enabled: Boolean(taskId),
  });
  const stream = useTaskEventStream(taskId);
  const startMutation = useMutation({
    mutationFn: () => startTask(taskId!),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["task", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-events", taskId] });
    },
  });

  useEffect(() => {
    if (stream.events.length > 0) {
      queryClient.setQueryData(["task-events", taskId], { items: stream.events, next_cursor: null });
    }
  }, [queryClient, stream.events, taskId]);

  const task = taskQuery.data;
  const events = useMemo(() => {
    const combined = [...(eventQuery.data?.items ?? []), ...stream.events];
    return Array.from(new Map(combined.map((event) => [event.sequence, event])).values()).sort(
      (left, right) => left.sequence - right.sequence,
    );
  }, [eventQuery.data?.items, stream.events]);

  if (!task) {
    return (
      <ConsoleShell title="Tasks / Detail">
        <div className="p-6 text-sm text-slate-500">Loading task...</div>
      </ConsoleShell>
    );
  }

  return (
    <ConsoleShell title={`Tasks / ${task.id.slice(0, 8)}`}>
      <div className="border-b border-slate-200 bg-white px-6 py-5">
        <div className="mb-2 flex items-center gap-2 text-xs text-slate-500">
          <Link to="/tasks">Tasks</Link>
          <ChevronRight className="h-3 w-3" />
          <span className="font-mono">{task.id.slice(0, 8)}</span>
        </div>
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="truncate text-xl font-semibold tracking-tight text-slate-900">
                {task.title}
              </h1>
              <TaskStatusBadge status={task.status} />
              {task.enable_sandbox && <Badge tone="purple">sandbox enabled</Badge>}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-5 text-xs text-slate-500">
              <span>
                Model <span className="text-slate-800">{task.model_name}</span>
              </span>
              <span>
                Subagents <span className="font-mono text-slate-800">{task.max_subagents}</span>
              </span>
              <span>
                Runtime{" "}
                <span className="font-mono text-slate-800">{task.max_runtime_seconds}s</span>
              </span>
              <span>
                Network{" "}
                <span className={task.enable_network ? "text-amber-600" : "text-slate-800"}>
                  {task.enable_network ? "enabled" : "disabled"}
                </span>
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              onClick={() => startMutation.mutate()}
              disabled={startMutation.isPending || task.status !== "CREATED"}
            >
              <Play className="h-3.5 w-3.5" /> Start
            </Button>
            <Button variant="primary">
              <Download className="h-3.5 w-3.5" /> Export Audit
            </Button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4 p-4">
        <section className="col-span-3">
          <ExecutionPlanPanel events={events} />
        </section>
        <section className={focus === "events" ? "col-span-9" : "col-span-6"}>
          <EventTimeline events={events} connected={stream.connected} />
        </section>
        {focus !== "events" && (
          <section className="col-span-3 space-y-3">
            <SubagentPanel />
            <SandboxPanel enabled={task.enable_sandbox} />
            <Card>
              <CardHeader>
                <div className="text-[11px] tracking-widest text-slate-500">MODEL CALLS</div>
              </CardHeader>
              <div className="space-y-1 p-3 text-[11px]">
                <div className="flex justify-between">
                  <span className="text-slate-500">provider</span>
                  <span className="font-mono">{task.model_provider}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">model</span>
                  <span className="font-mono">{task.model_name}</span>
                </div>
              </div>
            </Card>
          </section>
        )}
      </div>
      <div className="px-4 pb-6">
        <TaskResultPanel task={task} />
      </div>
    </ConsoleShell>
  );
}
