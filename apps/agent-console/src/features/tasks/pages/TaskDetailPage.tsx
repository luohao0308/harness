import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, ChevronRight, Download, Play, RotateCcw } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { useI18n } from "../../../lib/i18n";
import { enabledLabel } from "../../../lib/labels";
import { EventTimeline } from "../../events/components/EventTimeline";
import { useTaskEventStream } from "../../events/useTaskEventStream";
import { PolicyBadge } from "../../policies/components/PolicyBadge";
import { SandboxPanel } from "../../sandboxes/components/SandboxPanel";
import { SubagentPanel } from "../../subagents/components/SubagentPanel";
import {
  cancelTask,
  getTask,
  getTaskPlan,
  getTaskPlanDiff,
  getTaskResult,
  listTaskPlanVersions,
  listModelCalls,
  listTaskSubagentRecoveryBatches,
  listTaskEvents,
  listTaskSubagents,
  listToolCalls,
  recoverTaskSubagents,
  replayTask,
  resumeTask,
  resumeTaskSteps,
  startTask,
} from "../api";
import type { ToolCallFilters } from "../api";
import { ExecutionPlanPanel } from "../components/ExecutionPlanPanel";
import { ModelCallPanel } from "../components/ModelCallPanel";
import { ResourceUsageChart } from "../components/ResourceUsageChart";
import { TaskResultPanel } from "../components/TaskResultPanel";
import { TaskStatusBadge } from "../components/TaskStatusBadge";

export function TaskDetailPage({ focus }: { focus?: "events" | "subagents" }) {
  const { text } = useI18n();
  const { taskId } = useParams();
  const queryClient = useQueryClient();
  const [toolCallFilters, setToolCallFilters] = useState<ToolCallFilters>({ limit: 100 });
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
  const resultQuery = useQuery({
    queryKey: ["task-result", taskId],
    queryFn: () => getTaskResult(taskId!),
    enabled: Boolean(taskId),
  });
  const planQuery = useQuery({
    queryKey: ["task-plan", taskId],
    queryFn: () => getTaskPlan(taskId!),
    enabled: Boolean(taskId) && taskQuery.data?.status !== "CREATED",
    retry: false,
  });
  const planVersionsQuery = useQuery({
    queryKey: ["task-plan-versions", taskId],
    queryFn: () => listTaskPlanVersions(taskId!),
    enabled: Boolean(taskId) && taskQuery.data?.status !== "CREATED",
    retry: false,
  });
  const planVersions = planVersionsQuery.data?.items ?? [];
  const latestPlanVersion = planVersions[0]?.version;
  const previousPlanVersion = planVersions[1]?.version;
  const planDiffQuery = useQuery({
    queryKey: ["task-plan-diff", taskId, previousPlanVersion, latestPlanVersion],
    queryFn: () => getTaskPlanDiff(taskId!, previousPlanVersion!, latestPlanVersion!),
    enabled: Boolean(taskId) && Boolean(previousPlanVersion) && Boolean(latestPlanVersion),
    retry: false,
  });
  const modelCallsQuery = useQuery({
    queryKey: ["model-calls", taskId],
    queryFn: () => listModelCalls(taskId!),
    enabled: Boolean(taskId),
  });
  const subagentsQuery = useQuery({
    queryKey: ["task-subagents", taskId],
    queryFn: () => listTaskSubagents(taskId!),
    enabled: Boolean(taskId),
  });
  const recoveryBatchesQuery = useQuery({
    queryKey: ["task-subagent-recovery-batches", taskId],
    queryFn: () => listTaskSubagentRecoveryBatches(taskId!),
    enabled: Boolean(taskId),
  });
  const toolCallsQuery = useQuery({
    queryKey: ["tool-calls", taskId, toolCallFilters],
    queryFn: () => listToolCalls(taskId!, toolCallFilters),
    enabled: Boolean(taskId),
  });
  const recoverSubagentsMutation = useMutation({
    mutationFn: () => recoverTaskSubagents(taskId!),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["task-subagents", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-events", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-result", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-subagent-recovery-batches", taskId] });
    },
  });
  const stream = useTaskEventStream(taskId);
  const startMutation = useMutation({
    mutationFn: () => startTask(taskId!),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["task", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-events", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-plan", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-plan-versions", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-plan-diff", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-result", taskId] });
    },
  });
  const cancelMutation = useMutation({
    mutationFn: () => cancelTask(taskId!),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["task", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-events", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-result", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-plan", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-plan-versions", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-plan-diff", taskId] });
    },
  });
  const resumeMutation = useMutation({
    mutationFn: () => resumeTask(taskId!),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["task", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-events", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-result", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-plan", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-plan-versions", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-plan-diff", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["model-calls", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["tool-calls", taskId] });
    },
  });
  const resumeStepsMutation = useMutation({
    mutationFn: (stepKey: string) => resumeTaskSteps(taskId!, [stepKey]),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["task", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-events", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-result", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-plan", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-plan-versions", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-plan-diff", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-subagents", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["model-calls", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["tool-calls", taskId] });
    },
  });
  const replayMutation = useMutation({
    mutationFn: () => replayTask(taskId!, events.at(-1)?.sequence),
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
      <ConsoleShell title={text("任务 / 详情", "Tasks / Detail")}>
        <div className="p-6 text-sm text-slate-500">{text("任务加载中...", "Loading task...")}</div>
      </ConsoleShell>
    );
  }

  return (
    <ConsoleShell title={`${text("任务", "Task")} / ${task.id.slice(0, 8)}`}>
      <div className="border-b border-slate-200 bg-white px-6 py-5">
        <div className="mb-2 flex items-center gap-2 text-xs text-slate-500">
          <Link to="/tasks">{text("任务", "Tasks")}</Link>
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
              {task.enable_sandbox && <Badge tone="purple">{text("沙箱已启用", "Sandbox enabled")}</Badge>}
              <PolicyBadge requiresSandbox={task.enable_sandbox} />
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-5 text-xs text-slate-500">
              <span>
                {text("模型", "Model")} <span className="text-slate-800">{task.model_name}</span>
              </span>
              <span>
                {text("子 Agent", "Subagents")} <span className="font-mono text-slate-800">{task.max_subagents}</span>
              </span>
              <span>
                {text("运行上限", "Runtime limit")}{" "}
                <span className="font-mono text-slate-800">{task.max_runtime_seconds}s</span>
              </span>
              <span>
                {text("网络", "Network")}{" "}
                <span className={task.enable_network ? "text-amber-600" : "text-slate-800"}>
                  {enabledLabel(task.enable_network)}
                </span>
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              onClick={() => startMutation.mutate()}
              disabled={startMutation.isPending || task.status !== "CREATED"}
            >
              <Play className="h-3.5 w-3.5" /> {text("启动", "Start")}
            </Button>
            <Button
              onClick={() => cancelMutation.mutate()}
              disabled={cancelMutation.isPending || !["CREATED", "RUNNING", "FAILED"].includes(task.status)}
              variant="danger"
            >
              <Ban className="h-3.5 w-3.5" /> {text("取消", "Cancel")}
            </Button>
            <Button
              onClick={() => resumeMutation.mutate()}
              disabled={resumeMutation.isPending || !["FAILED", "CANCELLED"].includes(task.status)}
            >
              <RotateCcw className="h-3.5 w-3.5" /> {text("恢复", "Resume")}
            </Button>
            <Button variant="primary">
              <Download className="h-3.5 w-3.5" /> {text("导出审计", "Export Audit")}
            </Button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4 p-4">
        <section className="col-span-3">
          <ExecutionPlanPanel
            events={events}
            plan={planQuery.data}
            planVersions={planVersions}
            planDiff={planDiffQuery.data}
            subagents={subagentsQuery.data?.items ?? []}
            canResumeSteps={["FAILED", "CANCELLED"].includes(task.status)}
            resumingStepKey={
              resumeStepsMutation.isPending ? (resumeStepsMutation.variables ?? null) : null
            }
            onResumeFromStep={(stepKey) => resumeStepsMutation.mutate(stepKey)}
          />
        </section>
        <section className={focus === "events" ? "col-span-9" : "col-span-6"}>
          <EventTimeline
            events={events}
            connected={stream.connected}
            subagents={subagentsQuery.data?.items ?? []}
          />
          <div className="mt-3 rounded-md border border-slate-200 bg-white p-3 text-xs">
            <div className="mb-2 flex items-center justify-between">
              <span className="font-semibold text-slate-900">{text("重放调试", "Replay Debug")}</span>
              <Button onClick={() => replayMutation.mutate()} disabled={replayMutation.isPending}>
                <RotateCcw className="h-3.5 w-3.5" /> {text("重放当前序号", "Replay Current Sequence")}
              </Button>
            </div>
            <div className="text-slate-500">
              {replayMutation.data?.state_summary ??
                text("将当前最后事件序号作为重放输入。", "Uses the current last event sequence as replay input.")}
            </div>
            {replayMutation.data?.diagnosis && (
              <div className="mt-1 text-slate-500">{replayMutation.data.diagnosis}</div>
            )}
          </div>
        </section>
        {focus !== "events" && (
          <section className="col-span-3 space-y-3">
            <SubagentPanel
              subagents={subagentsQuery.data?.items ?? []}
              maxSubagents={task.max_subagents}
              loading={subagentsQuery.isLoading}
              recovering={recoverSubagentsMutation.isPending}
              recoveryBatch={recoverSubagentsMutation.data ?? recoveryBatchesQuery.data?.items[0]}
              recoveryBatches={recoveryBatchesQuery.data?.items ?? []}
              onRecover={() => recoverSubagentsMutation.mutate()}
            />
            <SandboxPanel enabled={task.enable_sandbox} />
            <ModelCallPanel
              modelCalls={modelCallsQuery.data?.items ?? []}
              toolCalls={toolCallsQuery.data?.items ?? []}
              toolCallFilters={toolCallFilters}
              onToolCallFiltersChange={setToolCallFilters}
            />
            <ResourceUsageChart
              modelCallCount={modelCallsQuery.data?.items.length ?? 0}
              toolCallCount={toolCallsQuery.data?.items.length ?? 0}
            />
          </section>
        )}
      </div>
      <div className="px-4 pb-6">
        <TaskResultPanel task={task} result={resultQuery.data} />
      </div>
    </ConsoleShell>
  );
}
