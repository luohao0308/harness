import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Ban,
  BrainCircuit,
  CheckCircle2,
  ChevronRight,
  Download,
  FlaskConical,
  GitBranch,
  Play,
  RotateCcw,
  Save,
  XCircle,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { useI18n } from "../../../lib/i18n";
import { enabledLabel } from "../../../lib/labels";
import { EventTimeline } from "../../events/components/EventTimeline";
import { useTaskEventStream } from "../../events/useTaskEventStream";
import { PolicyBadge } from "../../policies/components/PolicyBadge";
import { SandboxPanel } from "../../sandboxes/components/SandboxPanel";
import { SubagentPanel } from "../../subagents/components/SubagentPanel";
import {
  approveToolApproval,
  cancelTask,
  createEvalCaseFromRun,
  createEvalDataset,
  createEvalRun,
  getTaskContext,
  getTask,
  getTaskPlan,
  getTaskPlanDiff,
  getTaskResult,
  listTaskPlanVersions,
  listModelCalls,
  listTaskSubagentRecoveryBatches,
  listTaskEvents,
  listTaskToolApprovals,
  listAgentRunAssignments,
  listAgentRunHandoffs,
  listEvalDatasets,
  listEvalRuns,
  listTaskSubagents,
  listToolCalls,
  recoverTaskSubagents,
  rejectToolApproval,
  replayTask,
  resumeTask,
  resumeTaskSteps,
  routeTaskContext,
  startTask,
} from "../api";
import type {
  AgentAssignment,
  AgentEvent,
  AgentHandoff,
  EvalDataset,
  EvalRun,
  RunContext,
  ToolApproval,
  ToolCall,
  ToolCallFilters,
} from "../api";
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
  const [replaySequence, setReplaySequence] = useState("");
  const [selectedEvalDatasetId, setSelectedEvalDatasetId] = useState<string | null>(null);
  const [evalDatasetName, setEvalDatasetName] = useState("Regression Dataset");
  const [expectedStatus, setExpectedStatus] = useState("COMPLETED");
  const [approvalReason, setApprovalReason] = useState("Approved from Run Console");
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
  const contextQuery = useQuery({
    queryKey: ["task-context", taskId],
    queryFn: () => getTaskContext(taskId!),
    enabled: Boolean(taskId),
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
  const toolApprovalsQuery = useQuery({
    queryKey: ["tool-approvals", taskId],
    queryFn: () => listTaskToolApprovals(taskId!),
    enabled: Boolean(taskId),
  });
  const assignmentsQuery = useQuery({
    queryKey: ["agent-run-assignments", taskId],
    queryFn: () => listAgentRunAssignments(taskId!),
    enabled: Boolean(taskId),
  });
  const handoffsQuery = useQuery({
    queryKey: ["agent-run-handoffs", taskId],
    queryFn: () => listAgentRunHandoffs(taskId!),
    enabled: Boolean(taskId),
  });
  const evalDatasetsQuery = useQuery({
    queryKey: ["eval-datasets"],
    queryFn: listEvalDatasets,
  });
  const evalRunsQuery = useQuery({
    queryKey: ["eval-runs"],
    queryFn: listEvalRuns,
  });
  const activeAssignmentPolling = (assignmentsQuery.data ?? []).some((assignment) =>
    ["QUEUED", "RUNNING"].includes(assignment.status),
  );
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
    mutationFn: () =>
      replayTask(
        taskId!,
        replaySequence.trim() ? Number(replaySequence.trim()) : events.at(-1)?.sequence,
      ),
  });
  const routeContextMutation = useMutation({
    mutationFn: () => routeTaskContext(taskId!),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["task-context", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-events", taskId] });
    },
  });
  const createEvalDatasetMutation = useMutation({
    mutationFn: () => createEvalDataset({ name: evalDatasetName, description: "Saved from Run Detail" }),
    onSuccess: async (dataset) => {
      setSelectedEvalDatasetId(dataset.id);
      await queryClient.invalidateQueries({ queryKey: ["eval-datasets"] });
    },
  });
  const saveEvalCaseMutation = useMutation({
    mutationFn: () =>
      createEvalCaseFromRun(currentEvalDatasetId(evalDatasetsQuery.data?.items, selectedEvalDatasetId), taskId!, {
        expected_json: { status: expectedStatus },
        tags_json: ["run-detail", "regression"],
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["eval-datasets"] });
      await queryClient.invalidateQueries({ queryKey: ["task-events", taskId] });
    },
  });
  const runEvalMutation = useMutation({
    mutationFn: () =>
      createEvalRun(currentEvalDatasetId(evalDatasetsQuery.data?.items, selectedEvalDatasetId), {
        agent_id: "default",
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["eval-runs"] });
      await queryClient.invalidateQueries({ queryKey: ["task-events", taskId] });
    },
  });
  const approveToolApprovalMutation = useMutation({
    mutationFn: (approvalId: string) => approveToolApproval(taskId!, approvalId, approvalReason),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["tool-approvals", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["tool-calls", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-events", taskId] });
    },
  });
  const rejectToolApprovalMutation = useMutation({
    mutationFn: (approvalId: string) => rejectToolApproval(taskId!, approvalId, approvalReason),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["tool-approvals", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["tool-calls", taskId] });
      await queryClient.invalidateQueries({ queryKey: ["task-events", taskId] });
    },
  });

  useEffect(() => {
    if (stream.events.length > 0) {
      queryClient.setQueryData(["task-events", taskId], { items: stream.events, next_cursor: null });
    }
  }, [queryClient, stream.events, taskId]);

  useEffect(() => {
    if (!activeAssignmentPolling || !taskId) {
      return;
    }
    const intervalId = window.setInterval(() => {
      void queryClient.invalidateQueries({ queryKey: ["agent-run-assignments", taskId] });
      void queryClient.invalidateQueries({ queryKey: ["agent-run-handoffs", taskId] });
      void queryClient.invalidateQueries({ queryKey: ["task-events", taskId] });
      void queryClient.invalidateQueries({ queryKey: ["tool-calls", taskId] });
    }, 2000);
    return () => window.clearInterval(intervalId);
  }, [activeAssignmentPolling, queryClient, taskId]);

  const task = taskQuery.data;
  const events = useMemo(() => {
    const combined = [...(eventQuery.data?.items ?? []), ...stream.events];
    return Array.from(new Map(combined.map((event) => [event.sequence, event])).values()).sort(
      (left, right) => left.sequence - right.sequence,
    );
  }, [eventQuery.data?.items, stream.events]);
  const evalDatasets = evalDatasetsQuery.data?.items ?? [];
  const activeEvalDatasetId = selectedEvalDatasetId ?? evalDatasets[0]?.id ?? null;
  const latestEvalRun = runEvalMutation.data ?? evalRunsQuery.data?.items[0] ?? null;
  const guardrailEvents = useMemo(
    () =>
      events.filter(
        (event) =>
          event.event_type.includes("POLICY") ||
          event.event_type.includes("DENIED") ||
          event.event_type.includes("GUARDRAIL"),
      ),
    [events],
  );
  const deniedToolCalls = (toolCallsQuery.data?.items ?? []).filter((toolCall) =>
    ["DENIED", "BLOCKED"].includes(toolCall.status),
  );

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
                text("输入事件序号做时间旅行调试；留空时重放当前最后事件。", "Enter a sequence for time-travel debugging; blank replays the latest event.")}
            </div>
            <div className="mt-3 flex items-center gap-2">
              <Input
                value={replaySequence}
                onChange={(event) => setReplaySequence(event.target.value)}
                className="h-8 w-36 font-mono text-xs"
                inputMode="numeric"
                placeholder={text("事件序号", "Sequence")}
              />
              <span className="text-[11px] text-slate-500">
                {text("最后序号", "Last sequence")}{" "}
                <span className="font-mono">{events.at(-1)?.sequence ?? "--"}</span>
              </span>
            </div>
            {replayMutation.data?.diagnosis && (
              <div className="mt-1 text-slate-500">{replayMutation.data.diagnosis}</div>
            )}
            {replayMutation.data?.failure_point && (
              <pre className="mt-2 max-h-40 overflow-auto rounded border border-red-100 bg-red-50 p-2 font-mono text-[11px] text-red-800">
                {JSON.stringify(replayMutation.data.failure_point, null, 2)}
              </pre>
            )}
          </div>
        </section>
        {focus !== "events" && (
          <section className="col-span-3 space-y-3">
            <EvalRunPanel
              datasets={evalDatasets}
              selectedDatasetId={activeEvalDatasetId}
              datasetName={evalDatasetName}
              expectedStatus={expectedStatus}
              latestEvalRun={latestEvalRun}
              creatingDataset={createEvalDatasetMutation.isPending}
              savingCase={saveEvalCaseMutation.isPending}
              runningEval={runEvalMutation.isPending}
              onSelectDataset={setSelectedEvalDatasetId}
              onDatasetNameChange={setEvalDatasetName}
              onExpectedStatusChange={setExpectedStatus}
              onCreateDataset={() => createEvalDatasetMutation.mutate()}
              onSaveCase={() => saveEvalCaseMutation.mutate()}
              onRunEval={() => runEvalMutation.mutate()}
            />
            <GuardrailPanel
              events={guardrailEvents}
              deniedToolCalls={deniedToolCalls}
              approvals={toolApprovalsQuery.data?.items ?? []}
              approvalReason={approvalReason}
              decidingApprovalId={
                approveToolApprovalMutation.isPending
                  ? approveToolApprovalMutation.variables
                  : rejectToolApprovalMutation.isPending
                    ? rejectToolApprovalMutation.variables
                    : null
              }
              onApprovalReasonChange={setApprovalReason}
              onApprove={(approvalId) => approveToolApprovalMutation.mutate(approvalId)}
              onReject={(approvalId) => rejectToolApprovalMutation.mutate(approvalId)}
            />
            <ContextRouterPanel
              context={routeContextMutation.data ?? contextQuery.data ?? null}
              routing={routeContextMutation.isPending}
              onRoute={() => routeContextMutation.mutate()}
            />
            <SubagentPanel
              subagents={subagentsQuery.data?.items ?? []}
              maxSubagents={task.max_subagents}
              loading={subagentsQuery.isLoading}
              recovering={recoverSubagentsMutation.isPending}
              recoveryBatch={recoverSubagentsMutation.data ?? recoveryBatchesQuery.data?.items[0]}
              recoveryBatches={recoveryBatchesQuery.data?.items ?? []}
              onRecover={() => recoverSubagentsMutation.mutate()}
            />
            <AgentOrchestrationPanel
              assignments={assignmentsQuery.data ?? []}
              handoffs={handoffsQuery.data ?? []}
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

function AgentOrchestrationPanel({
  assignments,
  handoffs,
}: {
  assignments: AgentAssignment[];
  handoffs: AgentHandoff[];
}) {
  const { text } = useI18n();
  const assignmentsById = new Map(assignments.map((assignment) => [assignment.id, assignment]));
  const reducerAssignment = findReducerAssignment(assignments, handoffs);
  const branchAssignments = assignments.filter((assignment) => assignment.id !== reducerAssignment?.id);
  const activeCount = assignments.filter((assignment) =>
    ["QUEUED", "RUNNING"].includes(assignment.status),
  ).length;
  const successCount = assignments.filter((assignment) => assignment.status === "SUCCESS").length;
  const failedCount = assignments.filter((assignment) => assignment.status === "FAILED").length;
  const slowestAssignment = slowestCompletedAssignment(assignments);
  const slowestTiming = slowestAssignment ? assignmentTiming(slowestAssignment) : null;
  const reducedSummary =
    typeof reducerAssignment?.output_json.reduced_summary === "string"
      ? reducerAssignment.output_json.reduced_summary
      : null;
  return (
    <div className="rounded-md border border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
        <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
          <GitBranch className="h-4 w-4" /> {text("多 Agent 编排", "Multi-agent")}
        </div>
        <div className="flex items-center gap-2 font-mono text-[11px] text-slate-500">
          <span>{text("节点", "nodes")} {assignments.length}</span>
          <span>{text("边", "edges")} {handoffs.length}</span>
        </div>
      </div>
      {assignments.length === 0 ? (
        <div className="p-3 text-xs text-slate-500">
          {text("该 Run 暂无 Agent assignments。", "No Agent assignments for this Run.")}
        </div>
      ) : (
        <div className="space-y-3 p-3">
          <div className="grid grid-cols-4 gap-2 text-xs">
            <TopologyMetric label={text("Assignments", "Assignments")} value={assignments.length} />
            <TopologyMetric label={text("运行中", "Active")} value={activeCount} />
            <TopologyMetric label={text("成功", "Success")} value={successCount} />
            <TopologyMetric label={text("失败", "Failed")} value={failedCount} />
          </div>
          {slowestAssignment && slowestTiming && (
            <div className="rounded border border-amber-100 bg-amber-50 px-3 py-2 text-[11px] text-amber-800">
              <span className="font-semibold">{text("瓶颈分支", "Bottleneck branch")}</span>
              <span className="ml-2 font-mono">{slowestAssignment.agent_id}</span>
              <span className="ml-2">
                {text("总耗时", "total")} {formatDuration(slowestTiming.totalMs)}
              </span>
            </div>
          )}

          <div className="grid grid-cols-[0.8fr_1.2fr_0.9fr] items-stretch gap-3">
            <TopologyStage title={text("入口", "Entry")}>
              <div className="rounded border border-cyan-100 bg-cyan-50 px-3 py-2">
                <div className="font-mono text-xs font-semibold text-cyan-900">
                  {assignments[0]?.agent_id ?? "default"}
                </div>
                <div className="mt-1 text-[11px] text-cyan-700">
                  {text("Router 创建 fan-out 分支", "Router created fan-out branches")}
                </div>
              </div>
            </TopologyStage>

            <TopologyStage title={text("并行分支", "Parallel Branches")}>
              <div className="grid gap-2">
                {(branchAssignments.length > 0 ? branchAssignments : assignments).map((assignment) => (
                  <AssignmentNode key={assignment.id} assignment={assignment} />
                ))}
              </div>
            </TopologyStage>

            <TopologyStage title={text("Reducer", "Reducer")}>
              {reducerAssignment ? (
                <AssignmentNode assignment={reducerAssignment} highlight />
              ) : (
                <div className="rounded border border-slate-100 bg-slate-50 p-2 text-xs text-slate-500">
                  {text("等待 reducer assignment", "Waiting for reducer assignment")}
                </div>
              )}
            </TopologyStage>
          </div>

          {handoffs.length > 0 && (
            <div className="rounded border border-slate-100 bg-slate-50 p-2">
              <div className="mb-2 text-[11px] font-semibold text-slate-700">
                {text("Handoff 边", "Handoff Edges")}
              </div>
              <div className="grid gap-1">
                {handoffs.map((handoff) => {
                  const fromAgent = handoff.from_assignment_id
                    ? assignmentsById.get(handoff.from_assignment_id)?.agent_id
                    : "entry";
                  const toAgent = assignmentsById.get(handoff.to_assignment_id)?.agent_id ?? "unknown";
                  return (
                    <div
                      key={handoff.id}
                      className="grid grid-cols-[1fr_auto_1fr_auto] items-center gap-2 font-mono text-[11px] text-slate-500"
                    >
                      <span className="truncate">{fromAgent}</span>
                      <ChevronRight className="h-3 w-3 shrink-0 text-slate-400" />
                      <span className="truncate">{toAgent}</span>
                      <Badge tone="neutral">{handoff.handoff_type}</Badge>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {reducedSummary && (
            <div className="rounded border border-emerald-100 bg-emerald-50 px-3 py-2 text-[11px] leading-4 text-emerald-800">
              <div className="mb-1 font-semibold">{text("Reducer 输出", "Reducer Output")}</div>
              {reducedSummary}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function EvalRunPanel({
  datasets,
  selectedDatasetId,
  datasetName,
  expectedStatus,
  latestEvalRun,
  creatingDataset,
  savingCase,
  runningEval,
  onSelectDataset,
  onDatasetNameChange,
  onExpectedStatusChange,
  onCreateDataset,
  onSaveCase,
  onRunEval,
}: {
  datasets: EvalDataset[];
  selectedDatasetId: string | null;
  datasetName: string;
  expectedStatus: string;
  latestEvalRun: EvalRun | null;
  creatingDataset: boolean;
  savingCase: boolean;
  runningEval: boolean;
  onSelectDataset: (datasetId: string | null) => void;
  onDatasetNameChange: (value: string) => void;
  onExpectedStatusChange: (value: string) => void;
  onCreateDataset: () => void;
  onSaveCase: () => void;
  onRunEval: () => void;
}) {
  const { text } = useI18n();
  const selectedDataset = datasets.find((dataset) => dataset.id === selectedDatasetId) ?? null;
  const canSaveCase = Boolean(selectedDatasetId);
  const canRunEval = Boolean(selectedDatasetId && selectedDataset && selectedDataset.case_count > 0);
  return (
    <div className="rounded-md border border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
        <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
          <FlaskConical className="h-4 w-4" /> {text("Eval 回归", "Eval Regression")}
        </div>
        {latestEvalRun && <Badge tone={statusTone(latestEvalRun.status)}>{latestEvalRun.status}</Badge>}
      </div>
      <div className="space-y-3 p-3 text-xs">
        <div className="grid grid-cols-[1fr_auto] gap-2">
          <Input
            value={datasetName}
            onChange={(event) => onDatasetNameChange(event.target.value)}
            className="h-8 text-xs"
          />
          <Button onClick={onCreateDataset} disabled={creatingDataset || !datasetName.trim()}>
            {text("新建", "New")}
          </Button>
        </div>
        <select
          className="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-xs outline-none"
          value={selectedDatasetId ?? ""}
          onChange={(event) => onSelectDataset(event.target.value || null)}
        >
          <option value="">{text("选择 Eval Dataset", "Select Eval Dataset")}</option>
          {datasets.map((dataset) => (
            <option key={dataset.id} value={dataset.id}>
              {dataset.name} ({dataset.case_count})
            </option>
          ))}
        </select>
        <div className="grid grid-cols-[1fr_auto] gap-2">
          <Input
            value={expectedStatus}
            onChange={(event) => onExpectedStatusChange(event.target.value)}
            className="h-8 font-mono text-xs"
          />
          <Button onClick={onSaveCase} disabled={!canSaveCase || savingCase} className="gap-1.5">
            <Save className="h-3.5 w-3.5" />
            {text("保存 Case", "Save Case")}
          </Button>
        </div>
        <Button
          variant="primary"
          onClick={onRunEval}
          disabled={!canRunEval || runningEval}
          className="w-full gap-1.5"
        >
          <Play className="h-3.5 w-3.5" />
          {text("运行 Dataset Eval", "Run Dataset Eval")}
        </Button>
        {latestEvalRun && (
          <div className="grid grid-cols-2 gap-2">
            <EvalMetric label="success" value={latestEvalRun.metrics_json.task_success_rate} />
            <EvalMetric label="policy" value={latestEvalRun.metrics_json.policy_violation_rate} />
            <EvalMetric label="cases" value={latestEvalRun.metrics_json.case_total} />
            <EvalMetric label="passed" value={latestEvalRun.metrics_json.passed_total} />
          </div>
        )}
        <Link to="/evals" className="block text-[11px] text-blue-600 hover:text-blue-800">
          {text("打开完整 Eval Harness", "Open full Eval Harness")}
        </Link>
      </div>
    </div>
  );
}

function currentEvalDatasetId(datasets: EvalDataset[] | undefined, selectedDatasetId: string | null) {
  return selectedDatasetId ?? datasets?.[0]?.id ?? "";
}

function EvalMetric({ label, value }: { label: string; value: unknown }) {
  const displayValue =
    typeof value === "number" || typeof value === "string" ? String(value) : "--";
  return (
    <div className="rounded border border-slate-100 bg-slate-50 px-2 py-1.5">
      <div className="text-[10px] uppercase text-slate-500">{label}</div>
      <div className="mt-0.5 font-mono text-sm font-semibold text-slate-900">
        {displayValue}
      </div>
    </div>
  );
}

function ContextRouterPanel({
  context,
  routing,
  onRoute,
}: {
  context: RunContext | null;
  routing: boolean;
  onRoute: () => void;
}) {
  const { text } = useI18n();
  const routingDecision = context?.model_routing ?? {};
  const compression = context?.context_compression ?? {};
  const workingMemory = context?.working_memory ?? {};
  const artifactMemory = context?.artifact_memory ?? {};
  const ragContext = context?.rag_context ?? {};
  const selectedModel = [
    valueText(routingDecision.selected_provider),
    valueText(routingDecision.selected_model),
  ]
    .filter((value) => value !== "--")
    .join("/");
  return (
    <div className="rounded-md border border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
        <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
          <BrainCircuit className="h-4 w-4" /> {text("Context Router", "Context Router")}
        </div>
        <Button onClick={onRoute} disabled={routing} className="h-7 gap-1.5">
          <RotateCcw className="h-3.5 w-3.5" />
          {text("刷新路由", "Route")}
        </Button>
      </div>
      {!context ? (
        <div className="p-3 text-xs text-slate-500">
          {text("正在读取 Run 上下文。", "Loading run context.")}
        </div>
      ) : (
        <div className="space-y-3 p-3 text-xs">
          <div className="rounded border border-cyan-100 bg-cyan-50 px-3 py-2">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="font-mono text-xs font-semibold text-cyan-900">
                  {selectedModel || "--"}
                </div>
                <div className="mt-1 text-[11px] text-cyan-700">
                  {valueText(routingDecision.reasoning)}
                </div>
              </div>
              <Badge tone="info">{valueText(routingDecision.task_type)}</Badge>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2">
            <ContextMetric label="events" value={compression.original_event_count} />
            <ContextMetric label="kept" value={compression.retained_event_count} />
            <ContextMetric label="tools" value={compression.tool_call_count} />
          </div>

          <div className="grid gap-2">
            <MemoryRow label={text("工作记忆", "Working")} value={valueText(workingMemory.plan_summary ?? workingMemory.goal)} />
            <MemoryRow
              label={text("产物记忆", "Artifacts")}
              value={`${numberText(artifactMemory.tool_artifact_count)} tool / ${numberText(
                artifactMemory.subagent_artifact_count,
              )} subagent`}
            />
            <MemoryRow
              label={text("RAG 上下文", "RAG")}
              value={`${numberText(ragContext.retrieval_count)} retrievals`}
            />
          </div>

          <div className="rounded border border-slate-100 bg-slate-50 p-2">
            <div className="mb-1 text-[11px] font-semibold text-slate-700">
              {text("压缩策略", "Compression")}
            </div>
            <div className="text-[11px] leading-4 text-slate-600">
              {valueText(compression.compression_strategy)}
            </div>
            <div className="mt-1 font-mono text-[10px] text-slate-500">
              seq {sequenceText(compression.retained_sequences)}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ContextMetric({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="rounded border border-slate-100 bg-slate-50 px-2 py-1.5">
      <div className="text-[10px] uppercase text-slate-500">{label}</div>
      <div className="mt-0.5 font-mono text-sm font-semibold text-slate-900">
        {numberText(value)}
      </div>
    </div>
  );
}

function MemoryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-slate-100 bg-white px-2 py-1.5">
      <div className="text-[10px] uppercase text-slate-500">{label}</div>
      <div className="mt-0.5 line-clamp-2 text-[11px] leading-4 text-slate-700">{value}</div>
    </div>
  );
}

function GuardrailPanel({
  events,
  deniedToolCalls,
  approvals,
  approvalReason,
  decidingApprovalId,
  onApprovalReasonChange,
  onApprove,
  onReject,
}: {
  events: AgentEvent[];
  deniedToolCalls: ToolCall[];
  approvals: ToolApproval[];
  approvalReason: string;
  decidingApprovalId: string | null;
  onApprovalReasonChange: (value: string) => void;
  onApprove: (approvalId: string) => void;
  onReject: (approvalId: string) => void;
}) {
  const { text } = useI18n();
  const pendingApprovals = approvals.filter((approval) => approval.status === "PENDING");
  const total = events.length + deniedToolCalls.length + approvals.length;
  return (
    <div className="rounded-md border border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
        <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
          <AlertTriangle className="h-4 w-4" /> {text("Guardrails", "Guardrails")}
        </div>
        <Badge tone={total > 0 ? "warning" : "success"}>{total}</Badge>
      </div>
      {pendingApprovals.length > 0 && (
        <div className="space-y-2 border-b border-slate-100 p-3">
          <Input
            value={approvalReason}
            onChange={(event) => onApprovalReasonChange(event.target.value)}
            className="h-8 text-xs"
          />
          {pendingApprovals.map((approval) => (
            <div key={approval.id} className="rounded border border-amber-200 bg-amber-50 p-2 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono font-semibold text-amber-900">
                  {String(approval.request_json.tool_name ?? approval.tool_call_id)}
                </span>
                <Badge tone="warning">{approval.risk_level}</Badge>
              </div>
              <div className="mt-1 text-[11px] text-amber-800">{approval.reason}</div>
              <div className="mt-2 flex gap-2">
                <Button
                  onClick={() => onApprove(approval.id)}
                  disabled={decidingApprovalId === approval.id}
                  className="h-7 gap-1.5"
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  {text("批准", "Approve")}
                </Button>
                <Button
                  variant="danger"
                  onClick={() => onReject(approval.id)}
                  disabled={decidingApprovalId === approval.id}
                  className="h-7 gap-1.5"
                >
                  <XCircle className="h-3.5 w-3.5" />
                  {text("拒绝", "Reject")}
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
      {total === 0 ? (
        <div className="p-3 text-xs text-slate-500">
          {text("当前 Run 没有策略阻断或拒绝记录。", "No policy blocks or denials for this Run.")}
        </div>
      ) : (
        <div className="space-y-2 p-3">
          {approvals
            .filter((approval) => approval.status !== "PENDING")
            .slice(-4)
            .map((approval) => (
              <div key={approval.id} className="rounded border border-slate-100 bg-slate-50 p-2 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-slate-900">
                    {String(approval.request_json.tool_name ?? approval.tool_call_id)}
                  </span>
                  <Badge tone={approval.status === "APPROVED" ? "success" : "failed"}>
                    {approval.status}
                  </Badge>
                </div>
                <div className="mt-1 text-[11px] text-slate-600">
                  {String(approval.decision_json.reason ?? approval.reason)}
                </div>
              </div>
            ))}
          {events.slice(-4).map((event) => (
            <div key={event.id} className="rounded border border-amber-100 bg-amber-50 p-2 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-amber-900">{event.event_type}</span>
                <span className="font-mono text-[10px] text-amber-700">#{event.sequence}</span>
              </div>
              <div className="mt-1 truncate text-[11px] text-amber-800">
                {JSON.stringify(event.payload_json)}
              </div>
            </div>
          ))}
          {deniedToolCalls.slice(-4).map((toolCall) => (
            <div key={toolCall.id} className="rounded border border-red-100 bg-red-50 p-2 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-red-900">{toolCall.tool_name}</span>
                <Badge tone="failed">{toolCall.status}</Badge>
              </div>
              <div className="mt-1 truncate text-[11px] text-red-800">
                {toolCall.error_message ?? JSON.stringify(toolCall.input_json ?? {})}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TopologyMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded border border-slate-100 bg-slate-50 px-2 py-1.5">
      <div className="text-slate-500">{label}</div>
      <div className="mt-0.5 font-mono text-sm font-semibold text-slate-900">{value}</div>
    </div>
  );
}

function TopologyStage({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded border border-slate-100 bg-white p-2">
      <div className="mb-2 text-[11px] font-semibold text-slate-700">{title}</div>
      {children}
    </div>
  );
}

function AssignmentNode({
  assignment,
  compact = false,
  highlight = false,
}: {
  assignment: AgentAssignment;
  compact?: boolean;
  highlight?: boolean;
}) {
  const summary =
    typeof assignment.output_json.summary === "string"
      ? assignment.output_json.summary
      : null;
  const allowedTools = Array.isArray(assignment.output_json.allowed_tools)
    ? assignment.output_json.allowed_tools
    : [];
  const timing = assignmentTiming(assignment);
  return (
    <div
      className={[
        "rounded border px-2 py-2",
        highlight ? "border-emerald-100 bg-emerald-50" : "border-slate-100 bg-slate-50",
      ].join(" ")}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-mono text-xs font-semibold text-slate-900">
            {assignment.agent_id}
          </div>
          <div className="text-[11px] text-slate-500">{assignment.role}</div>
        </div>
        <Badge tone={statusTone(assignment.status)}>{assignment.status}</Badge>
      </div>
      <div className="mt-2 grid grid-cols-3 gap-1 text-[10px] text-slate-500">
        <TimingValue label="queue" value={timing.queueMs} />
        <TimingValue label="run" value={timing.runMs} />
        <TimingValue label="total" value={timing.totalMs} />
      </div>
      {!compact && allowedTools.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {allowedTools.slice(0, 5).map((tool) => (
            <span
              key={String(tool)}
              className="rounded border border-slate-200 bg-white px-1.5 py-0.5 font-mono text-[10px] text-slate-500"
            >
              {String(tool)}
            </span>
          ))}
        </div>
      )}
      {!compact && summary && (
        <div className="mt-2 text-[11px] leading-4 text-slate-600">{summary}</div>
      )}
    </div>
  );
}

function TimingValue({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="rounded border border-slate-100 bg-white px-1.5 py-1">
      <div>{label}</div>
      <div className="font-mono text-slate-800">{formatDuration(value)}</div>
    </div>
  );
}

function findReducerAssignment(assignments: AgentAssignment[], handoffs: AgentHandoff[]) {
  const reducerByRole = assignments.find((assignment) => assignment.agent_id === "reviewer");
  if (reducerByRole) {
    return reducerByRole;
  }
  const reducerIds = new Set(handoffs.map((handoff) => handoff.to_assignment_id));
  return assignments.find((assignment) => reducerIds.has(assignment.id)) ?? assignments.at(-1);
}

function assignmentTiming(assignment: AgentAssignment) {
  const createdAt = Date.parse(assignment.created_at);
  const startedAt = assignment.started_at ? Date.parse(assignment.started_at) : null;
  const completedAt = assignment.completed_at ? Date.parse(assignment.completed_at) : null;
  const now = Date.now();
  const queueEnd = startedAt ?? completedAt ?? now;
  const runEnd = completedAt ?? (startedAt ? now : null);
  return {
    queueMs: Number.isFinite(createdAt) && queueEnd ? Math.max(queueEnd - createdAt, 0) : null,
    runMs: startedAt && runEnd ? Math.max(runEnd - startedAt, 0) : null,
    totalMs: Number.isFinite(createdAt) && (completedAt || startedAt)
      ? Math.max((completedAt ?? now) - createdAt, 0)
      : null,
  };
}

function slowestCompletedAssignment(assignments: AgentAssignment[]) {
  return assignments
    .map((assignment) => ({ assignment, timing: assignmentTiming(assignment) }))
    .filter((item) => item.timing.totalMs !== null)
    .sort((left, right) => (right.timing.totalMs ?? 0) - (left.timing.totalMs ?? 0))[0]
    ?.assignment;
}

function formatDuration(value: number | null) {
  if (value === null) {
    return "--";
  }
  if (value < 1000) {
    return `${Math.round(value)}ms`;
  }
  if (value < 60_000) {
    return `${(value / 1000).toFixed(1)}s`;
  }
  return `${Math.round(value / 60_000)}m`;
}

function valueText(value: unknown) {
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "--";
}

function numberText(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? String(value) : "0";
}

function sequenceText(value: unknown) {
  if (!Array.isArray(value) || value.length === 0) {
    return "--";
  }
  return value.map((item) => String(item)).join(", ");
}
