import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { Bot, BrainCircuit, Check, Database, FlaskConical, Gauge, GitBranch, Pencil, Play, RotateCcw, Search, Shield, Wrench, X } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { ConfigDialog } from "../../../components/ui/config-dialog";
import { feedbackErrorMessage, notifyFeedback } from "../../../components/ui/feedback-toast";
import { Input, Textarea } from "../../../components/ui/input";
import { MenuSelect } from "../../../components/ui/menu-select";
import { Table, Td, Th } from "../../../components/ui/table";
import { TermHint } from "../../../components/ui/term";
import { useI18n } from "../../../lib/i18n";
import { eventLabel, executionModeLabel, riskLabel, statusLabel } from "../../../lib/labels";
import { formatShortDate } from "../../../lib/utils";
import {
  readWorkspaceReturnTarget,
  saveWorkspaceReturnTarget,
  workspaceReturnPath,
} from "../../agents/lib/runLinks";
import {
  approveToolApproval,
  createEvalDataset,
  createEvalCaseFromRun,
  executeAgentRun,
  executeAgentOrchestration,
  getAgentRunWorkspace,
  listEvalDatasets,
  modifyToolApproval,
  orchestrateAgentRun,
  rejectToolApproval,
  replayTask,
  type AgentRunWorkspace,
  type AgentEvent,
  type AgentAssignment,
  type AgentHandoff,
  type ReplayResult,
  type Subagent,
  type ToolApproval,
  type ToolCall,
} from "../../tasks/api";

const DEFAULT_EVAL_DATASET_ID = "__create_default_eval_dataset__";

type OrchestrationFeedback = {
  description: string;
  at: string;
};

type ModifyApprovalDialogState = {
  approval: ToolApproval;
  jsonText: string;
};

export function RunDetailPage({ focus }: { focus?: "events" | "subagents" }) {
  const { text } = useI18n();
  const { runId } = useParams();
  const [searchParams] = useSearchParams();
  const retrievalSessionId = searchParams.get("retrieval_session_id") ?? undefined;
  const promptManifestId = searchParams.get("prompt_manifest_id") ?? undefined;
  const requestedReturnTo = searchParams.get("return_to");
  const requestedConversationId = searchParams.get("conversation_id");
  const queryClient = useQueryClient();
  const [replaySequence, setReplaySequence] = useState("");
  const [replayResult, setReplayResult] = useState<ReplayResult | null>(null);
  const [orchestrationFeedback, setOrchestrationFeedback] = useState<OrchestrationFeedback | null>(null);
  const [saveEvalSuccess, setSaveEvalSuccess] = useState(false);
  const [selectedEvalDatasetId, setSelectedEvalDatasetId] = useState("");
  const [modifyApprovalDialog, setModifyApprovalDialog] = useState<ModifyApprovalDialogState | null>(null);
  const workspaceQueryKey = useMemo(
    () => ["agent-run-workspace", runId, retrievalSessionId, promptManifestId] as const,
    [promptManifestId, retrievalSessionId, runId],
  );
  const workspace = useQuery({
    queryKey: workspaceQueryKey,
    queryFn: () =>
      getAgentRunWorkspace(runId!, {
        retrieval_session_id: retrievalSessionId,
        prompt_manifest_id: promptManifestId,
      }),
    enabled: Boolean(runId),
    refetchInterval: 5000,
  });
  const data = workspace.data;
  const run = data?.run;
  const grounding = data?.knowledge_grounding;
  const contextAssembly = data?.context_assembly;
  const tokenOptimization = data?.token_optimization ?? {};
  const langGraphEvents = useMemo(
    () => (data?.events ?? []).filter((event) => isLangGraphEvent(event.event_type)),
    [data?.events],
  );
  const failedStepEvents = useMemo(
    () => (data?.events ?? []).filter((event) => event.event_type === "STEP_FAILED"),
    [data?.events],
  );
  const assignmentEvents = useMemo(
    () => (data?.events ?? []).filter((event) => event.event_type.startsWith("AGENT_")),
    [data?.events],
  );
  const specialistEvidence = useMemo(() => collectSpecialistEvidence(data?.subagents ?? []), [data?.subagents]);
  const datasetsQuery = useQuery({ queryKey: ["eval-datasets"], queryFn: listEvalDatasets });
  const execute = useMutation({
    mutationFn: () => executeAgentRun(runId!),
    onSuccess: async () => {
      notifyFeedback({
        tone: "success",
        title: text("计划已开始执行", "Plan execution started"),
        description: text("运行详情会继续自动刷新。", "Run detail will continue refreshing automatically."),
      });
      await queryClient.invalidateQueries({ queryKey: workspaceQueryKey });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("计划执行失败", "Plan execution failed"),
        description: feedbackErrorMessage(error, text("请检查当前运行状态或稍后重试。", "Check the run state and retry.")),
      });
    },
  });
  const orchestrate = useMutation({
    mutationFn: () => orchestrateAgentRun(runId!),
    onSuccess: async (result) => {
      const description = orchestrationResultDescription(result.message, result.assignments, result.handoffs);
      setOrchestrationFeedback({ description, at: new Date().toISOString() });
      notifyFeedback({
        tone: "success",
        title: assignments.length > 0
          ? text("编排已同步", "Orchestration synced")
          : text("多智能体编排已创建", "Orchestration created"),
        description,
      });
      await refreshWorkspaceQuery(queryClient, workspaceQueryKey);
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("多智能体编排失败", "Orchestration failed"),
        description: feedbackErrorMessage(error, text("请检查运行状态、模型设置或稍后重试。", "Check the run state, model settings, or retry.")),
      });
    },
  });
  const executeOrchestration = useMutation({
    mutationFn: () => executeAgentOrchestration(runId!),
    onSuccess: async (result) => {
      const description = orchestrationResultDescription(result.message, result.assignments, result.handoffs);
      setOrchestrationFeedback({ description, at: new Date().toISOString() });
      notifyFeedback({
        tone: result.assignments.length > 0 && allAssignmentsSuccessful(result.assignments) ? "info" : "success",
        title: result.assignments.length > 0 && allAssignmentsSuccessful(result.assignments)
          ? text("多智能体已完成", "Orchestration already complete")
          : text("多智能体已执行", "Orchestration executed"),
        description,
      });
      await refreshWorkspaceQuery(queryClient, workspaceQueryKey);
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("多智能体执行失败", "Orchestration execution failed"),
        description: feedbackErrorMessage(error, text("请检查 Agent 能力挂载、模型设置或稍后重试。", "Check Agent capability attachments, model settings, or retry.")),
      });
    },
  });
  const replay = useMutation({
    mutationFn: () => replayTask(runId!, parseReplaySequence(replaySequence)),
    onSuccess: (result) => {
      setReplayResult(result);
      notifyFeedback({
        tone: "success",
        title: text("回放完成", "Replay completed"),
        description: text(`已回放到序列 ${result.sequence}。`, `Replayed through sequence ${result.sequence}.`),
      });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("回放失败", "Replay failed"),
        description: feedbackErrorMessage(error, text("请检查回放序列号或稍后重试。", "Check the replay sequence and retry.")),
      });
    },
  });
  const approve = useMutation({
    mutationFn: (approvalId: string) => approveToolApproval(runId!, approvalId, "Approved from Agent Run Detail"),
    onMutate: async (approvalId) => {
      await queryClient.cancelQueries({ queryKey: workspaceQueryKey });
      const previous = queryClient.getQueryData<AgentRunWorkspace>(workspaceQueryKey);
      queryClient.setQueryData<AgentRunWorkspace>(
        workspaceQueryKey,
        optimisticApprovalDecision(previous, approvalId, "APPROVED"),
      );
      return { previous };
    },
    onError: (error, _approvalId, context) => {
      if (context?.previous) queryClient.setQueryData(workspaceQueryKey, context.previous);
      notifyFeedback({
        tone: "error",
        title: text("审批通过失败", "Approval failed"),
        description: feedbackErrorMessage(error, text("请刷新后重试审批操作。", "Refresh and retry the approval action.")),
      });
    },
    onSuccess: (result) => {
      queryClient.setQueryData<AgentRunWorkspace>(
        workspaceQueryKey,
        mergeApprovalPage(queryClient.getQueryData<AgentRunWorkspace>(workspaceQueryKey), result.items),
      );
      notifyFeedback({
        tone: "success",
        title: text("审批已通过", "Approval accepted"),
        description: text("工具审批状态已更新。", "The tool approval state has been updated."),
      });
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: workspaceQueryKey, refetchType: "active" });
      void queryClient.refetchQueries({ queryKey: workspaceQueryKey, type: "active" });
    },
  });
  const reject = useMutation({
    mutationFn: (approvalId: string) => rejectToolApproval(runId!, approvalId, "Rejected from Agent Run Detail"),
    onMutate: async (approvalId) => {
      await queryClient.cancelQueries({ queryKey: workspaceQueryKey });
      const previous = queryClient.getQueryData<AgentRunWorkspace>(workspaceQueryKey);
      queryClient.setQueryData<AgentRunWorkspace>(
        workspaceQueryKey,
        optimisticApprovalDecision(previous, approvalId, "DENIED"),
      );
      return { previous };
    },
    onError: (error, _approvalId, context) => {
      if (context?.previous) queryClient.setQueryData(workspaceQueryKey, context.previous);
      notifyFeedback({
        tone: "error",
        title: text("审批拒绝失败", "Rejection failed"),
        description: feedbackErrorMessage(error, text("请刷新后重试拒绝操作。", "Refresh and retry the reject action.")),
      });
    },
    onSuccess: (result) => {
      queryClient.setQueryData<AgentRunWorkspace>(
        workspaceQueryKey,
        mergeApprovalPage(queryClient.getQueryData<AgentRunWorkspace>(workspaceQueryKey), result.items),
      );
      notifyFeedback({
        tone: "warning",
        title: text("审批已拒绝", "Approval rejected"),
        description: text("工具审批状态已更新为拒绝。", "The tool approval has been marked as rejected."),
      });
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: workspaceQueryKey, refetchType: "active" });
      void queryClient.refetchQueries({ queryKey: workspaceQueryKey, type: "active" });
    },
  });
  const modify = useMutation({
    mutationFn: ({
      approvalId,
      modifiedInputJson,
    }: {
      approvalId: string;
      modifiedInputJson: Record<string, unknown>;
    }) =>
      modifyToolApproval(
        runId!,
        approvalId,
        modifiedInputJson,
        "Modified and approved from Agent Run Detail",
      ),
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("修改审批失败", "Modify approval failed"),
        description: feedbackErrorMessage(error, text("请检查 JSON 后重试。", "Check the JSON and retry.")),
      });
    },
    onSuccess: (result) => {
      queryClient.setQueryData<AgentRunWorkspace>(
        workspaceQueryKey,
        mergeApprovalPage(queryClient.getQueryData<AgentRunWorkspace>(workspaceQueryKey), result.items),
      );
      setModifyApprovalDialog(null);
      notifyFeedback({
        tone: "success",
        title: text("审批已修改并批准", "Approval modified and accepted"),
        description: text("工具将使用修改后的 JSON 参数执行。", "The tool will run with the modified JSON payload."),
      });
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: workspaceQueryKey, refetchType: "active" });
      void queryClient.refetchQueries({ queryKey: workspaceQueryKey, type: "active" });
    },
  });
  const handleSubmitModifyApproval = (approvalId: string, modifiedInputJson: Record<string, unknown>) => {
    modify.mutate({ approvalId, modifiedInputJson });
  };
  const saveEvalCase = useMutation({
    mutationFn: async () => {
      let datasetId = selectedEvalDatasetId;
      if (!datasetId || datasetId === DEFAULT_EVAL_DATASET_ID) {
        const dataset = await createEvalDataset({
          name: "运行详情保存用例",
          description: "从运行详情页保存的完成态或失败态运行案例。",
        });
        datasetId = dataset.id;
      }
      if (!datasetId || !runId) throw new Error("No dataset or run");
      const policyDecisions = Array.from(
        new Set((grounding?.policy_audits ?? []).map((audit) => audit.decision)),
      );
      const citationKeys = Array.from(
        new Set((grounding?.citations ?? []).map((citation) => citation.citation_key)),
      );
      const citationHitIds = Array.from(
        new Set((grounding?.citations ?? []).map((citation) => citation.retrieval_hit_id)),
      );
      const retrievalHitIds = Array.from(
        new Set((grounding?.retrieval_hits ?? []).map((hit) => hit.id)),
      );
      const fallbackExpected = Boolean(
        grounding?.web_sources.length ||
          ["web", "web_fallback", "fallback"].includes(grounding?.retrieval_session?.mode ?? ""),
      );
      const groundingContract =
        grounding?.selected_retrieval_session_id || grounding?.selected_prompt_manifest_id
          ? {
              grounding_contract: {
                retrieval_session_id: grounding.selected_retrieval_session_id ?? undefined,
                prompt_manifest_id: grounding.selected_prompt_manifest_id ?? undefined,
                hit_ids: citationHitIds.length ? citationHitIds : retrievalHitIds,
                citation_keys: citationKeys,
                fallback_expected: fallbackExpected,
                require_grounded: grounding.grounded,
                require_prompt_manifest: Boolean(grounding.selected_prompt_manifest_id),
                require_insufficient: grounding.local_status !== "sufficient",
                allow_fixture_grounding: false,
                ...(policyDecisions.length
                  ? { require_policy_decisions: policyDecisions }
                  : {}),
              },
            }
          : {};
      return createEvalCaseFromRun(datasetId, runId, {
        expected_json: { status: run?.status ?? "COMPLETED", ...groundingContract },
        tags_json: ["saved-from-run"],
      });
    },
    onSuccess: () => {
      setSaveEvalSuccess(true);
      queryClient.invalidateQueries({ queryKey: ["eval-datasets"] });
      queryClient.invalidateQueries({ queryKey: ["eval-cases"] });
      notifyFeedback({
        tone: "success",
        title: text("评测用例已保存", "Eval case saved"),
        description: text("当前运行已经写入评测数据集。", "This run has been added to the eval dataset."),
      });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("评测用例保存失败", "Eval case save failed"),
        description: feedbackErrorMessage(error, text("请检查数据集选择和当前运行状态。", "Check the dataset selection and run state.")),
      });
    },
  });
  const hitsById = useMemo(
    () => new Map((grounding?.retrieval_hits ?? []).map((hit) => [hit.id, hit])),
    [grounding?.retrieval_hits],
  );
  const webSourcesById = useMemo(
    () => new Map((grounding?.web_sources ?? []).map((source) => [source.id, source])),
    [grounding?.web_sources],
  );
  const latestSequence = useMemo(
    () => Math.max(0, ...(data?.events ?? []).map((event) => event.sequence)),
    [data?.events],
  );
  const primaryTraceId = useMemo(
    () => data?.events.find((event) => event.trace_id)?.trace_id ?? null,
    [data?.events],
  );

  useEffect(() => {
    if (selectedEvalDatasetId || !datasetsQuery.data?.items.length) return;
    setSelectedEvalDatasetId(datasetsQuery.data.items[0].id);
  }, [datasetsQuery.data?.items, selectedEvalDatasetId]);
  useEffect(() => {
    const target = workspaceReturnTargetFromPath(requestedReturnTo, requestedConversationId);
    if (target === null) return;
    saveWorkspaceReturnTarget(target, runId);
  }, [requestedConversationId, requestedReturnTo, runId]);
  const evalDatasetOptions =
    datasetsQuery.data?.items.length
      ? datasetsQuery.data.items
      : [
          {
            id: DEFAULT_EVAL_DATASET_ID,
            name: text("新建默认数据集", "Create default Dataset"),
          },
        ];
  const selectedEvalDatasetValue =
    selectedEvalDatasetId || (!datasetsQuery.data?.items.length ? DEFAULT_EVAL_DATASET_ID : "");
  const assignments = data?.assignments ?? [];
  const handoffs = data?.handoffs ?? [];
  const hasAssignments = assignments.length > 0;
  const reduceCompleted = assignmentEvents.some((event) => event.event_type === "AGENT_REDUCE_COMPLETED");
  const orchestrationSummary = orchestrationStateSummary(assignments, handoffs, reduceCompleted);
  const backToWorkspacePath = resolveWorkspaceReturnPath({
    requestedReturnTo,
    requestedConversationId,
    runId,
    agentId: run?.agent_id ?? null,
  });
  const subagentMetric = run ? `${data?.subagents.length ?? 0}/${run.max_subagents}` : "0/0";

  return (
    <ConsoleShell title={text("智能体运行", "Agent Run")}>
      <div className="grid grid-cols-12 gap-4 p-4">
        <section className="col-span-8 space-y-4">
          <Card className="p-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <Link to="/runs" className="text-xs text-slate-500 hover:text-slate-900">
                    {text("运行历史", "Run History")}
                  </Link>
                  <span className="text-slate-300">/</span>
                  <span className="font-mono text-xs text-slate-500">{run?.id.slice(0, 8) ?? "..."}</span>
                </div>
                <h1 className="mt-2 text-xl font-semibold text-slate-950">{run?.title ?? text("加载运行...", "Loading Run...")}</h1>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{run?.goal}</p>
              </div>
              {run && <Badge tone={statusTone(run.status)}>{statusLabel(run.status)}</Badge>}
            </div>
            {run && (
              <div className="mt-4 grid grid-cols-4 gap-2 text-xs">
                <Metric label={text("模型", "Model")} value={`${run.model_provider}/${run.model_name}`} />
                <Metric label="子代理" value={subagentMetric} />
                <Metric label="沙箱" value={run.enable_sandbox ? "开启" : "关闭"} />
                <Metric label={text("更新", "Updated")} value={formatShortDate(run.updated_at)} />
              </div>
            )}
            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                variant="primary"
                disabled={!run || run.status !== "PLANNED" || execute.isPending}
                onClick={() => execute.mutate()}
              >
                <Play className="h-3.5 w-3.5" />
                {text("执行计划", "Execute Plan")}
              </Button>
              <Button disabled={!run || orchestrate.isPending} onClick={() => orchestrate.mutate()}>
                {orchestrate.isPending ? (
                  <RotateCcw className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <GitBranch className="h-3.5 w-3.5" />
                )}
                {orchestrate.isPending
                  ? text("正在刷新编排", "Refreshing")
                  : hasAssignments
                    ? text("刷新编排", "Refresh Orchestration")
                    : text("创建多智能体编排", "Create Orchestration")}
              </Button>
              <Button
                disabled={!run || executeOrchestration.isPending}
                onClick={() => executeOrchestration.mutate()}
                title={hasAssignments ? orchestrationSummary.message : undefined}
              >
                {executeOrchestration.isPending ? (
                  <RotateCcw className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Play className="h-3.5 w-3.5" />
                )}
                {executeOrchestration.isPending
                  ? text("正在执行多智能体", "Executing Agents")
                  : hasAssignments && orchestrationSummary.allSuccessful
                  ? text("多智能体已完成", "Agents Complete")
                  : text("执行多智能体", "Execute Agents")}
              </Button>
              {run && (run.status === "COMPLETED" || run.status === "FAILED") && (
                <div className="flex items-center gap-2">
                  <MenuSelect
                    ariaLabel={text("选择数据集", "Select Dataset")}
                    value={selectedEvalDatasetValue}
                    onChange={(value) => {
                      setSelectedEvalDatasetId(value);
                      setSaveEvalSuccess(false);
                    }}
                    disabled={saveEvalCase.isPending || datasetsQuery.isLoading}
                    placeholder={text("选择数据集", "Select dataset")}
                    className="w-[15rem]"
                    buttonClassName="h-8 rounded-md px-2 py-1.5 shadow-none"
                    menuClassName="w-[15rem]"
                    options={evalDatasetOptions.map((dataset) => ({
                      value: dataset.id,
                      label: dataset.name,
                    }))}
                  />
                  <Button
                    disabled={
                      saveEvalCase.isPending ||
                      saveEvalSuccess ||
                      datasetsQuery.isLoading
                    }
                    onClick={() => saveEvalCase.mutate()}
                  >
                    <FlaskConical className="h-3.5 w-3.5" />
                    {saveEvalSuccess
                      ? text("已保存", "Saved")
                      : text("保存为评测用例", "Save as Eval Case")}
                  </Button>
                </div>
              )}
              <Link to={backToWorkspacePath}>
                <Button>
                  <Bot className="h-3.5 w-3.5" />
                  {text("回到工作台", "Back to Workspace")}
                </Button>
              </Link>
              {primaryTraceId ? (
                <Link to={`/observability/trace?trace_id=${encodeURIComponent(primaryTraceId)}`}>
                  <Button>
                    <Search className="h-3.5 w-3.5" /> 查看 Trace
                  </Button>
                </Link>
              ) : null}
            </div>
            {(orchestrationFeedback || orchestrate.isPending || executeOrchestration.isPending) ? (
              <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs leading-5 text-emerald-800">
                {orchestrate.isPending
                  ? text("正在请求后端刷新编排，完成后这里会显示 assignments / handoffs 证据。", "Refreshing orchestration; assignment and handoff evidence will appear here.")
                  : orchestrationFeedback?.description ??
                    (executeOrchestration.isPending
                      ? text("正在执行多智能体 assignments，完成后这里会显示执行结果。", "Executing assignments; results will appear here.")
                      : "")}
                {orchestrationFeedback ? (
                  <span className="ml-2 font-mono text-[11px] text-emerald-700">
                    {formatShortDate(orchestrationFeedback.at)}
                  </span>
                ) : null}
              </div>
            ) : null}
          </Card>

          {run?.status === "FAILED" && failedStepEvents.length > 0 ? (
            <FailureDiagnosisCard events={failedStepEvents} />
          ) : null}

          {grounding && (
            <Card id="knowledge-grounding">
              <CardHeader>
                <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                  <Database className="h-4 w-4" />
                  知识依据
                </div>
                <Badge tone={grounding.local_status === "sufficient" ? "success" : "warning"}>
                  {runDetailValueLabel(grounding.local_status)}
                </Badge>
              </CardHeader>
              <div className="space-y-3 p-3 text-sm">
                <div className="grid grid-cols-2 gap-2 text-xs md:grid-cols-3">
                  <Metric label="向量" value={runDetailValueLabel(grounding.vector_capability)} />
                  <Metric label="命中" value={String(grounding.retrieval_hits.length)} />
                  <Metric label="已依据" value={grounding.grounded ? "是" : "否"} />
                  <Metric
                    label={<TermHint description="提供依据校验的后端或模型">依据来源</TermHint>}
                    value={runDetailValueLabel(grounding.grounding_provider)}
                  />
                  <Metric label={<TermHint description="夹具证据，仅用于测试或演示">夹具证据</TermHint>} value={grounding.fixture_grounded ? "是" : "否"} />
                  <Metric label={<TermHint description="答案是否绑定到真实来源">来源绑定</TermHint>} value={grounding.verified_grounded ? "是" : "否"} />
                  <Metric label={<TermHint description="引用条数">引用数</TermHint>} value={String(grounding.citations.length)} />
                </div>
                <div className="truncate font-mono text-[11px] text-slate-500" title={grounding.grounding_verification_reason}>
                  {runDetailValueLabel(grounding.grounding_verification_reason)}
                </div>
                <p className="text-xs text-slate-500">
                  {grounding.evidence_message || grounding.evidence_summary}
                </p>
                {grounding.inferred_fallback && (
                  <div className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
                    后备原因 {grounding.fallback_reason ?? "最近一次"} · 检索会话{" "}
                    {grounding.selected_retrieval_session_id ?? "未提供"}
                  </div>
                )}
                {grounding.prompt_manifest && (
                  <div className="space-y-2">
                    <div className="text-xs font-medium text-slate-700">提示词组装审计</div>
                    <div className="rounded-md border border-slate-100 bg-slate-50 p-2 text-xs">
                      <div className="font-mono text-[11px] text-slate-500">
                        清单 {grounding.prompt_manifest.id}
                      </div>
                      <div className="mt-1 text-slate-600">
                        已纳入 {grounding.prompt_manifest.included_retrieval_hit_ids_json.length} · 已省略{" "}
                        {grounding.prompt_manifest.omitted_candidates_json.length}
                      </div>
                      <div className="mt-1 break-all text-slate-500">
                        关联 ID {grounding.prompt_manifest.grounding_correlation_id}
                      </div>
                      <div className="mt-1 break-all text-slate-500">
                        摘要 {grounding.prompt_manifest.evidence_text_sha256}
                      </div>
                    </div>
                  </div>
                )}
                {grounding.policy_audits.length > 0 && (
                  <div className="space-y-2">
                    <div className="text-xs font-medium text-slate-700">策略 / 省略审计</div>
                    {grounding.policy_audits.map((audit) => (
                      <div key={audit.id} className="rounded-md border border-slate-100 bg-white p-2 text-xs">
                        <div className="flex items-center justify-between gap-2">
                          <Badge tone={audit.decision === "allowed" ? "success" : "warning"}>
                            {runDetailValueLabel(audit.decision)}
                          </Badge>
                          <span className="font-mono text-[11px] text-slate-500">
                            {runDetailValueLabel(audit.source_kind ?? "manifest")}
                          </span>
                        </div>
                        <div className="mt-1 text-slate-600">{runDetailValueLabel(audit.reason)}</div>
                        {audit.source_ref_id && (
                          <div className="mt-1 break-all text-slate-500">{audit.source_ref_id}</div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
                {grounding.retrieval_hits.length > 0 && (
                  <div className="space-y-2">
                    <div className="text-xs font-medium text-slate-700">检索命中</div>
                    {grounding.retrieval_hits.map((hit) => (
                      <div key={hit.id} className="rounded-md border border-slate-100 bg-slate-50 p-2 text-xs">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-mono text-[11px] text-slate-500">
                            {runDetailValueLabel(hit.source_kind)} #{hit.rank} score={hit.score.toFixed(3)}
                          </span>
                          <span className="text-slate-500">{hit.chunk_id ?? hit.web_source_id}</span>
                        </div>
                        <div className="mt-1 text-slate-700">{hit.snippet}</div>
                      </div>
                    ))}
                  </div>
                )}
                {grounding.citations.length > 0 && (
                  <div className="space-y-2">
                    <div className="text-xs font-medium text-slate-700">引用</div>
                    <div className="space-y-2">
                      {grounding.citations.map((citation) => (
                        <div key={citation.id} className="rounded-md border border-slate-100 bg-white p-2 text-xs">
                          <div className="flex items-center justify-between gap-2">
                            <Badge tone="info">{citation.citation_key}</Badge>
                            <span className="font-mono text-[11px] text-slate-500">
                              {runDetailValueLabel(citation.source_kind)}
                            </span>
                          </div>
                          <div className="mt-1 text-slate-600">
                            命中: {citation.retrieval_hit_id}
                          </div>
                          <div className="mt-1 text-slate-500">
                            {citation.web_source_id
                              ? webSourcesById.get(citation.web_source_id)?.title ??
                                citation.web_source_id
                              : hitsById.get(citation.retrieval_hit_id)?.snippet ?? citation.chunk_id}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {grounding.web_sources.length > 0 && (
                  <div className="space-y-2">
                    <div className="text-xs font-medium text-slate-700">网页补充</div>
                    {grounding.web_sources.map((source) => (
                      <div key={source.id} className="rounded-md border border-slate-100 bg-white p-2 text-xs">
                        <div className="font-mono text-[11px] text-slate-500">{source.url}</div>
                        <div className="mt-1 font-medium text-slate-700">{source.title}</div>
                        <div className="mt-1 text-slate-600">{source.snippet}</div>
                        <div className="mt-1 text-slate-500">
                          {runDetailValueLabel(source.status)}
                          {source.error_message ? ` · ${source.error_message}` : ""}
                        </div>
                        <div className="mt-1 flex flex-wrap gap-1 text-slate-500">
                          <Badge tone={source.metadata_json.fixture ? "warning" : "info"}>
                            {runDetailValueLabel(String(source.metadata_json.provider ?? "unknown"))}
                          </Badge>
                          {source.metadata_json.request_id ? (
                            <Badge tone="neutral">
                              {String(source.metadata_json.request_id)}
                            </Badge>
                          ) : null}
                          {source.metadata_json.raw_content_available ? (
                            <Badge tone="warning">原始内容</Badge>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </Card>
          )}

          {contextAssembly && (
            <Card id="context-assembly">
              <CardHeader>
                <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                  <Database className="h-4 w-4" />
                  上下文组装
                </div>
                <Badge tone={contextAssembly.mode === "authoritative" ? "success" : "warning"}>
                  {runDetailValueLabel(contextAssembly.mode)}
                </Badge>
              </CardHeader>
              <div className="space-y-3 p-3 text-sm">
                {arrayField(tokenOptimization, "optimizer_capability_version_ids").length > 0 && (
                  <div className="grid gap-2 rounded-md border border-emerald-100 bg-emerald-50 p-2 text-xs text-emerald-900 md:grid-cols-[1fr_auto]">
                    <div className="min-w-0">
                      <div className="font-semibold">上下文优化器</div>
                      <div className="truncate font-mono">
                        {arrayField(tokenOptimization, "optimizer_capability_version_ids").join(", ")}
                      </div>
                      {stringField(tokenOptimization, "optimizer_policy_hash") ? (
                        <div className="mt-1 truncate font-mono text-emerald-700">
                          {stringField(tokenOptimization, "optimizer_policy_hash")?.slice(0, 16)}
                        </div>
                      ) : null}
                    </div>
                    <Badge tone="success">
                      {arrayField(tokenOptimization, "optimizer_decisions").length} 条决策
                    </Badge>
                  </div>
                )}
                <div className="grid grid-cols-2 gap-2 text-xs md:grid-cols-4">
                  <Metric label={<TermHint description="上下文组装清单">组装清单</TermHint>} value={contextAssembly.id} />
                  <Metric label={<TermHint description="提示词组装清单">提示词清单</TermHint>} value={contextAssembly.prompt_manifest_id ?? "未提供"} />
                  <Metric label={<TermHint description="已纳入上下文的引用数">已纳入</TermHint>} value={String(contextAssembly.included_refs_json.length)} />
                  <Metric label={<TermHint description="因预算或策略省略的引用数">已省略</TermHint>} value={String(contextAssembly.omitted_refs_json.length)} />
                  <Metric
                    label={<TermHint description="标记数估算器">估算器</TermHint>}
                    value={runDetailValueLabel(String(contextAssembly.token_budget_json.estimator ?? "未提供"))}
                  />
                  <Metric
                    label={<TermHint description="请求的上下文标记预算">预算</TermHint>}
                    value={String(contextAssembly.token_budget_json.requested_max_tokens ?? "未提供")}
                  />
                  <Metric label={<TermHint description="上下文分段数量">分段</TermHint>} value={String(contextAssembly.sections_json.length)} />
                  <Metric label={<TermHint description="上下文内容摘要哈希">摘要哈希</TermHint>} value={contextAssembly.context_text_sha256.slice(0, 12)} />
                </div>
                {contextAssembly.omitted_refs_json.length > 0 && (
                  <div className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
                    {contextAssembly.omitted_refs_json
                      .map((ref) => String(ref.omission_reason ?? "已省略"))
                      .filter((reason, index, reasons) => reasons.indexOf(reason) === index)
                      .join(", ")}
                  </div>
                )}
              </div>
            </Card>
          )}

          {Object.keys(tokenOptimization).length > 0 && (
            <Card id="token-optimization">
              <CardHeader>
                <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                  <Gauge className="h-4 w-4" />
                  标记节省
                </div>
                <Badge tone={boolField(tokenOptimization, "pruning_applied") ? "success" : "neutral"}>
                  {boolField(tokenOptimization, "pruning_applied") ? "已剪枝" : "未剪枝"}
                </Badge>
              </CardHeader>
              <div className="space-y-3 p-3 text-sm">
                <div className="grid grid-cols-2 gap-2 text-xs md:grid-cols-4">
                  <Metric
                    label={<TermHint description="用户请求的上下文预算">预算</TermHint>}
                    value={formatTokenMetric(numberField(tokenOptimization, "requested_max_tokens"))}
                  />
                  <Metric
                    label={<TermHint description="原始候选上下文估算标记数">原始候选</TermHint>}
                    value={formatTokenMetric(numberField(tokenOptimization, "estimated_candidate_tokens"))}
                  />
                  <Metric
                    label={<TermHint description="实际纳入模型请求的上下文估算标记数">优化后纳入</TermHint>}
                    value={formatTokenMetric(numberField(tokenOptimization, "estimated_included_tokens"))}
                  />
                  <Metric
                    label={<TermHint description="通过预算剪枝节省的估算标记数">已省标记</TermHint>}
                    value={`${formatTokenMetric(numberField(tokenOptimization, "estimated_saved_tokens"))} · ${formatPercentMetric(numberField(tokenOptimization, "estimated_savings_percent"))}`}
                  />
                  <Metric
                    label={<TermHint description="模型返回的实际 prompt 标记数">实际输入</TermHint>}
                    value={formatTokenMetric(numberField(tokenOptimization, "actual_prompt_tokens"))}
                  />
                  <Metric
                    label={<TermHint description="模型返回的实际 completion 标记数">实际输出</TermHint>}
                    value={formatTokenMetric(numberField(tokenOptimization, "actual_completion_tokens"))}
                  />
                  <Metric
                    label={<TermHint description="检索缓存命中次数">缓存命中</TermHint>}
                    value={formatTokenMetric(numberField(recordField(tokenOptimization, "retrieval_cache"), "hit_count"))}
                  />
                  <Metric
                    label={<TermHint description="低成本模型路由次数">低成本路由</TermHint>}
                    value={String(arrayField(tokenOptimization, "low_cost_routes").length)}
                  />
                </div>
                <div className="rounded-md border border-slate-100 bg-slate-50 p-2 text-xs text-slate-600">
                  纳入 {formatTokenMetric(numberField(tokenOptimization, "included_count"))} 个引用，
                  省略 {formatTokenMetric(numberField(tokenOptimization, "omitted_count"))} 个引用。节省证据来自后端上下文组装清单和模型调用实际用量。
                </div>
              </div>
            </Card>
          )}

          <Card id="plan">
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <GitBranch className="h-4 w-4" />
                计划 <TermHint description="有向无环图，表示步骤依赖">依赖图</TermHint>
              </div>
              <span className="text-xs text-slate-500">
                {data?.plan ? `${data.plan.steps.length} 个步骤` : text("暂无计划", "No Plan")}
              </span>
            </CardHeader>
            <div className="grid gap-2 p-3">
              {(data?.plan?.steps ?? []).map((step, index) => {
                const dependsOn = step.depends_on ?? [];
                const toolHints = step.tool_hints ?? [];
                const fanoutSpecialistSlugs = step.fanout_specialist_slugs ?? [];
                return (
                <div key={step.step_key} className="rounded-md border border-slate-100 bg-white p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-mono text-xs text-slate-900">
                        {index + 1}. {step.step_key}
                      </div>
                      <div className="mt-1 text-sm text-slate-600">{step.description}</div>
                    </div>
                    <Badge tone={statusTone(step.status)}>{statusLabel(step.status)}</Badge>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    <Badge tone={step.execution_mode === "langgraph_node" ? "info" : step.execution_mode === "async" ? "purple" : "neutral"}>
                      {executionModeLabel(step.execution_mode)}
                    </Badge>
                    {step.requires_sandbox && <Badge tone="warning">沙箱</Badge>}
                    {step.can_spawn_subagent && <Badge tone="purple">子代理</Badge>}
                    {step.recommended_specialist_slug ? (
                      <Badge tone="purple">专家: {step.recommended_specialist_slug}</Badge>
                    ) : null}
                    {fanoutSpecialistSlugs.length > 1 ? (
                      <Badge tone="info">
                        并行: {fanoutSpecialistSlugs.length} · {step.fanout_aggregation ?? "consensus"}
                      </Badge>
                    ) : null}
                    {dependsOn.length > 0 ? (
                      <Badge tone="info">依赖: {dependsOn.join(", ")}</Badge>
                    ) : (
                      <Badge tone="neutral">依赖: 无</Badge>
                    )}
                    {toolHints.map((tool) => (
                      <Badge key={tool} tone="info">{tool}</Badge>
                    ))}
                  </div>
                </div>
                );
              })}
              {!workspace.isLoading && !data?.plan && (
                <div className="py-8 text-center text-sm text-slate-500">
                  {text("这个运行还没有生成计划。", "This Run does not have a Plan yet.")}
                </div>
              )}
            </div>
          </Card>

          <div id="tool-runtime">
            <ToolCallsTable toolCalls={data?.tool_calls ?? []} />
          </div>
        </section>

        <aside className="col-span-4 space-y-4">
          <ReplayPanel
            latestSequence={latestSequence}
            replaySequence={replaySequence}
            replayResult={replayResult}
            isPending={replay.isPending}
            onSequenceChange={setReplaySequence}
            onReplay={() => replay.mutate()}
          />
          <LangGraphEvidencePanel events={langGraphEvents} />
          <MultiAgentEvidencePanel
            assignments={assignments}
            handoffs={handoffs}
            events={assignmentEvents}
            summary={orchestrationSummary}
          />
          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <BrainCircuit className="h-4 w-4" />
                {text("专家证据", "Specialist Evidence")}
              </div>
              <span className="text-xs text-slate-500">{specialistEvidence.length}</span>
            </CardHeader>
            <div className="max-h-[420px] space-y-3 overflow-auto p-3">
              {specialistEvidence.map((group) => (
                <div key={group.key} className="rounded border border-slate-100 p-2">
                  <div className="mb-2 flex items-center justify-between gap-2 text-xs">
                    <div className="min-w-0">
                      <div className="font-mono text-slate-900">{group.label}</div>
                      {group.batchId ? (
                        <div className="mt-0.5 truncate font-mono text-[10px] text-slate-400">
                          {group.batchId}
                        </div>
                      ) : null}
                    </div>
                    {group.batchId ? <Badge tone="info">fanout {group.items.length}</Badge> : null}
                  </div>
                  <div className="grid gap-2">
                    {group.items.map((item) => (
                      <div key={item.id} className="rounded border border-slate-100 bg-white p-2 text-xs">
                        <div className="flex items-center justify-between gap-2">
                          <Link to={`/subagents/${item.id}`} className="font-mono text-slate-900">
                            {item.slug} / {item.id.slice(0, 8)}
                          </Link>
                          <div className="flex items-center gap-1">
                            {typeof item.fanoutIndex === "number" && typeof item.fanoutTotal === "number" ? (
                              <Badge tone="info">{item.fanoutIndex + 1}/{item.fanoutTotal}</Badge>
                            ) : null}
                            <Badge tone={statusTone(item.status)}>{statusLabel(item.status)}</Badge>
                          </div>
                        </div>
                        <div className="mt-1 text-[11px] text-slate-500">
                          {item.role} · {item.summary}
                        </div>
                        {item.budgetExceeded.length > 0 ? (
                          <div className="mt-2 rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-700">
                            预算超限：{item.budgetExceeded.join(", ")}
                          </div>
                        ) : null}
                        <pre className="mt-2 max-h-40 overflow-auto rounded bg-slate-950 p-2 text-[10px] leading-relaxed text-slate-100">
                          {JSON.stringify(item.output, null, 2)}
                        </pre>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
              {specialistEvidence.length === 0 ? (
                <div className="py-8 text-center text-xs text-slate-500">
                  {text("暂无结构化专家输出。", "No structured specialist outputs yet.")}
                </div>
              ) : null}
            </div>
          </Card>
          <div id="approvals">
          <ApprovalsPanel
            approvals={data?.approvals ?? []}
            onApprove={(id) => approve.mutate(id)}
            onReject={(id) => reject.mutate(id)}
            onModify={(approval) =>
              setModifyApprovalDialog({
                approval,
                jsonText: JSON.stringify(approvalInputJson(approval), null, 2),
              })
            }
          />
          </div>
          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Shield className="h-4 w-4" />
                {focus === "subagents" ? "子代理" : "事件流"}
              </div>
            </CardHeader>
            <div className="max-h-[520px] space-y-2 overflow-auto p-3">
              {focus === "subagents"
                ? (data?.subagents ?? []).map((subagent) => (
                    <div key={subagent.id} className="rounded border border-slate-100 p-2">
                      <div className="flex items-center justify-between">
                        <span className="min-w-0 break-all font-mono text-xs">{subagent.id}</span>
                        <Badge tone={statusTone(subagent.status)}>{statusLabel(subagent.status)}</Badge>
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500">
                        <span>{subagent.agent_type}</span>
                        {subagent.specialist ? <Badge tone="purple">{subagent.specialist.slug}</Badge> : null}
                      </div>
                      {subagent.output ? (
                        <div className="mt-1 truncate text-[11px] text-slate-500">
                          {specialistOutputSummary(subagent.output.output_json)}
                        </div>
                      ) : null}
                    </div>
                  ))
                : (data?.events ?? []).map((event) => <EventRow key={event.id} event={event} />)}
            </div>
          </Card>
          <Card id="model-calls">
            <CardHeader>
              <div className="text-sm font-semibold text-slate-900">模型调用</div>
              <span className="text-xs text-slate-500">{data?.model_calls.length ?? 0}</span>
            </CardHeader>
            <div className="space-y-2 p-3">
              {(data?.model_calls ?? []).map((call) => (
                <div key={call.id} className="rounded border border-slate-100 p-2 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-slate-900">{call.model_provider}/{call.model_name}</span>
                    <Badge tone={statusTone(call.status)}>{statusLabel(call.status)}</Badge>
                  </div>
                  <div className="mt-1 break-all font-mono text-[11px] text-slate-500">{call.id}</div>
                  <div className="mt-1 text-slate-500">
                    {call.prompt_tokens + call.completion_tokens} 标记 · {call.duration_ms}ms
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-1 text-[11px] text-slate-500">
                    <Metric label={<TermHint description="第几次调用尝试">尝试序号</TermHint>} value={String(call.attempt_index)} />
                    <Metric
                      label={<TermHint description="最终状态">终态</TermHint>}
                      value={runDetailValueLabel(call.terminal_status)}
                    />
                    <Metric label={<TermHint description="提示词组装清单">提示词清单</TermHint>} value={call.prompt_manifest_id ?? "未提供"} />
                    <Metric label={<TermHint description="上下文组装清单">上下文清单</TermHint>} value={call.context_manifest_id ?? "未提供"} />
                    <Metric label={<TermHint description="依据链路关联 ID">关联 ID</TermHint>} value={call.grounding_correlation_id ?? "未提供"} />
                    <Metric label={<TermHint description="请求内容摘要哈希">请求哈希</TermHint>} value={call.model_request_sha256 ?? "未提供"} />
                    <Metric
                      label={<TermHint description="哈希可复算审计状态">哈希审计</TermHint>}
                      value={runDetailValueLabel(call.hash_recomputability_status)}
                    />
                  </div>
                  <div className="mt-1 truncate font-mono text-[11px] text-slate-400" title={call.request_message_hashes_sha256 ?? undefined}>
                    模式 v{call.model_request_hash_schema_version} · 消息{" "}
                    {call.request_message_hashes_json.length} ·{" "}
                    {call.request_message_hashes_sha256 ?? "未提供"}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </aside>
      </div>
      <ModifyToolApprovalDialog
        state={modifyApprovalDialog}
        isSubmitting={modify.isPending}
        onChange={(jsonText) => {
          setModifyApprovalDialog((current) => (
            current ? { ...current, jsonText } : current
          ));
        }}
        onClose={() => {
          if (!modify.isPending) setModifyApprovalDialog(null);
        }}
        onSubmit={handleSubmitModifyApproval}
      />
    </ConsoleShell>
  );
}

function ReplayPanel({
  latestSequence,
  replaySequence,
  replayResult,
  isPending,
  onSequenceChange,
  onReplay,
}: {
  latestSequence: number;
  replaySequence: string;
  replayResult: ReplayResult | null;
  isPending: boolean;
  onSequenceChange: (value: string) => void;
  onReplay: () => void;
}) {
  const { text } = useI18n();
  return (
    <Card>
      <CardHeader>
        <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
          <RotateCcw className="h-4 w-4" />
          重放
        </div>
        <span className="font-mono text-xs text-slate-500">最新 #{latestSequence}</span>
      </CardHeader>
      <div className="space-y-3 p-3">
        <div className="grid grid-cols-[1fr_auto] gap-2">
          <Input
            aria-label={text("重放序号", "Replay sequence")}
            className="h-8 font-mono text-xs"
            placeholder={text("输入序号，留空重放最新", "Sequence, blank for latest")}
            value={replaySequence}
            onChange={(event) => onSequenceChange(event.target.value)}
          />
          <Button disabled={isPending || latestSequence === 0} onClick={onReplay}>
            <RotateCcw className="h-3.5 w-3.5" />
            {text("重放", "Replay")}
          </Button>
        </div>
        {replayResult && (
          <div className="space-y-2 rounded-md border border-slate-100 bg-slate-50 p-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-mono text-slate-900">#{replayResult.sequence}</span>
              <Badge tone={replayResult.requires_manual_review ? "warning" : "success"}>
                {replayResult.requires_manual_review ? "需要人工复核" : "已重放"}
              </Badge>
            </div>
            <div className="leading-5 text-slate-600">{replayResult.state_summary}</div>
            <div className="leading-5 text-slate-500">{replayResult.diagnosis}</div>
            {replayResult.failure_point && (
              <pre className="max-h-28 overflow-auto rounded border border-slate-200 bg-white p-2 font-mono text-[10px] text-slate-600">
                {JSON.stringify(replayResult.failure_point, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

function LangGraphEvidencePanel({ events }: { events: AgentEvent[] }) {
  const latest = events[events.length - 1] ?? null;
  const workflowTotal = events.filter((event) => event.event_type.startsWith("LANGGRAPH_WORKFLOW_")).length;
  const nodeTotal = events.filter((event) => event.event_type.startsWith("LANGGRAPH_NODE_")).length;
  const toolNodeTotal = events.filter((event) => event.event_type.startsWith("LANGGRAPH_TOOL_NODE_")).length;
  return (
    <Card>
      <CardHeader>
        <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
          <GitBranch className="h-4 w-4" />
          LangGraph 证据
        </div>
        <Badge tone={events.length ? "info" : "neutral"}>{events.length}</Badge>
      </CardHeader>
      <div className="space-y-3 p-3 text-xs">
        <div className="grid grid-cols-3 gap-2">
          <Metric label="Workflow" value={String(workflowTotal)} />
          <Metric label="Node" value={String(nodeTotal)} />
          <Metric label="Tool node" value={String(toolNodeTotal)} />
        </div>
        {latest ? (
          <div className="rounded-md border border-slate-100 bg-slate-50 p-2">
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-slate-900">#{latest.sequence}</span>
              <Badge tone={langGraphEventTone(latest.event_type)}>{eventLabel(latest.event_type)}</Badge>
            </div>
            <div className="mt-1 text-slate-500">{langGraphEventPayloadSummary(latest.payload_json)}</div>
          </div>
        ) : (
          <div className="rounded-md border border-slate-100 bg-slate-50 p-3 text-slate-500">
            当前运行没有 LangGraph workflow/node/tool-node 事件。
          </div>
        )}
      </div>
    </Card>
  );
}

function FailureDiagnosisCard({ events }: { events: AgentEvent[] }) {
  const latest = events[events.length - 1];
  const payload = latest?.payload_json ?? {};
  const summary = stringField(payload, "summary") ?? "未提供失败摘要";
  const stepKey = stringField(payload, "step_key") ?? stringField(payload, "failed_step") ?? "unknown";
  const toolCallId = stringField(payload, "tool_call_id");
  const permissionBoundary = stringField(payload, "permission_boundary");
  return (
    <Card className="border-red-200 bg-red-50/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-red-950">失败原因</div>
          <div className="mt-1 text-sm leading-6 text-red-900">{summary}</div>
          <div className="mt-2 flex flex-wrap gap-1 text-xs">
            <Badge tone="failed">步骤 {stepKey}</Badge>
            {toolCallId ? <Badge tone="warning">工具调用 {toolCallId.slice(0, 8)}</Badge> : null}
            {permissionBoundary ? <Badge tone="warning">{permissionBoundary}</Badge> : null}
          </div>
        </div>
        <Badge tone="failed">FAILED</Badge>
      </div>
      <div className="mt-3 rounded-md border border-red-200 bg-white/70 p-2 text-xs leading-5 text-red-800">
        如果失败原因是 capability attachment，需要给当前 Agent 挂载对应工具能力，或使用带该能力的具名 Agent 执行多智能体分支。
      </div>
    </Card>
  );
}

function MultiAgentEvidencePanel({
  assignments,
  handoffs,
  events,
  summary,
}: {
  assignments: AgentRunWorkspace["assignments"];
  handoffs: AgentRunWorkspace["handoffs"];
  events: AgentEvent[];
  summary: OrchestrationStateSummary;
}) {
  const statusCounts = countBy(assignments, (assignment) => assignment.status);
  return (
    <Card>
      <CardHeader>
        <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
          <GitBranch className="h-4 w-4" />
          多智能体编排
        </div>
        <Badge tone={assignments.length ? "info" : "neutral"}>{assignments.length}</Badge>
      </CardHeader>
      <div className="space-y-3 p-3 text-xs">
        <div className="grid grid-cols-3 gap-2">
          <Metric label="Assignments" value={String(assignments.length)} />
          <Metric label="Handoffs" value={String(handoffs.length)} />
          <Metric label="Events" value={String(events.length)} />
        </div>
        {Object.keys(statusCounts).length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {Object.entries(statusCounts).map(([status, count]) => (
              <Badge key={status} tone={statusTone(status)}>
                {statusLabel(status)} {count}
              </Badge>
            ))}
          </div>
        ) : null}
        <div className="rounded-md border border-slate-100 bg-slate-50 p-2 leading-5 text-slate-600">
          {summary.message}
        </div>
        {assignments.length > 0 ? (
          <div className="space-y-2">
            {assignments.map((assignment) => (
              <div key={assignment.id} className="rounded border border-slate-100 bg-white p-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-slate-900">{assignment.agent_id}</span>
                  <Badge tone={statusTone(assignment.status)}>{statusLabel(assignment.status)}</Badge>
                </div>
                <div className="mt-1 flex flex-wrap gap-1 text-[11px] text-slate-500">
                  <span>{assignment.role}</span>
                  <span>{assignment.step_key ?? "run-level"}</span>
                </div>
                {assignment.output_json.summary ? (
                  <div className="mt-1 text-[11px] leading-5 text-slate-600">
                    {String(assignment.output_json.summary)}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-md border border-slate-100 bg-slate-50 p-3 text-slate-500">
            尚未创建具名 Agent assignment。点击“创建多智能体编排”后会显示 selected Agent、assignment 和 handoff。
          </div>
        )}
        {handoffs.length > 0 ? (
          <div className="space-y-1">
            <div className="font-medium text-slate-700">交接</div>
            {handoffs.map((handoff) => (
              <div
                key={handoff.id}
                className="flex items-center justify-between gap-2 rounded border border-slate-100 bg-slate-50 px-2 py-1 text-[11px] text-slate-600"
              >
                <span className="min-w-0 truncate">
                  {handoff.handoff_type}: {handoff.from_assignment_id?.slice(0, 8) ?? "entry"} → {handoff.to_assignment_id.slice(0, 8)}
                </span>
                <Badge tone={statusTone(handoff.status)} className="shrink-0">
                  {statusLabel(handoff.status)}
                </Badge>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </Card>
  );
}

function ApprovalsPanel({
  approvals,
  onApprove,
  onReject,
  onModify,
}: {
  approvals: ToolApproval[];
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  onModify: (approval: ToolApproval) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
          <Shield className="h-4 w-4" />
          护栏
        </div>
        <span className="text-xs text-slate-500">{approvals.length}</span>
      </CardHeader>
      <div className="space-y-2 p-3">
        {approvals.map((approval) => (
          <div key={approval.id} className="rounded border border-slate-100 p-2">
            <div className="flex items-center justify-between gap-2">
              <Badge tone={statusTone(approval.status)}>{statusLabel(approval.status)}</Badge>
              <span className="font-mono text-[11px] text-slate-500">{riskLabel(approval.risk_level)}</span>
            </div>
            <div className="mt-2 text-xs text-slate-600">{approval.reason}</div>
            {approval.status === "PENDING" && (
              <div className="mt-2 flex flex-wrap gap-1">
                <Button onClick={() => onApprove(approval.id)}>
                  <Check className="h-3.5 w-3.5" />
                  批准
                </Button>
                <Button variant="secondary" onClick={() => onModify(approval)}>
                  <Pencil className="h-3.5 w-3.5" />
                  修改
                </Button>
                <Button onClick={() => onReject(approval.id)}>
                  <X className="h-3.5 w-3.5" />
                  拒绝
                </Button>
              </div>
            )}
          </div>
        ))}
        {approvals.length === 0 && <div className="text-xs text-slate-500">暂无审批请求。</div>}
      </div>
    </Card>
  );
}

function ModifyToolApprovalDialog({
  state,
  isSubmitting,
  onChange,
  onClose,
  onSubmit,
}: {
  state: ModifyApprovalDialogState | null;
  isSubmitting: boolean;
  onChange: (jsonText: string) => void;
  onClose: () => void;
  onSubmit: (approvalId: string, modifiedInputJson: Record<string, unknown>) => void;
}) {
  const { text } = useI18n();
  const parsed = state ? parseApprovalJson(state.jsonText) : { value: null, error: null };
  const errorId = state ? `modify-approval-json-error-${state.approval.id}` : undefined;
  if (!state) return null;

  const submitDisabled = isSubmitting || parsed.value === null;

  return (
    <ConfigDialog
      open
      title={text("修改工具审批参数", "Modify tool approval payload")}
      description={text(
        "编辑 JSON 参数后将立即按修改后的内容批准此工具调用。",
        "Edit the JSON payload before approving this tool call with the modified input.",
      )}
      onClose={onClose}
      className="max-w-2xl"
    >
      <div className="space-y-4">
        <div className="rounded-md border border-slate-100 bg-slate-50 p-3 text-xs text-slate-600">
          <div className="font-mono text-slate-900">{state.approval.tool_call_id}</div>
          <div className="mt-1">{state.approval.reason}</div>
        </div>
        <label className="block text-xs font-medium text-slate-700" htmlFor="modify-approval-json">
          {text("JSON 参数", "JSON payload")}
        </label>
        <Textarea
          id="modify-approval-json"
          value={state.jsonText}
          onChange={(event) => onChange(event.target.value)}
          spellCheck={false}
          disabled={isSubmitting}
          aria-invalid={parsed.error ? true : undefined}
          aria-describedby={parsed.error ? errorId : undefined}
          className="min-h-72 font-mono text-xs leading-5"
        />
        {parsed.error ? (
          <div id={errorId} className="text-xs text-rose-600">
            {text(`JSON 无效：${parsed.error}`, `Invalid JSON: ${parsed.error}`)}
          </div>
        ) : null}
        <div className="flex items-center justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose} disabled={isSubmitting}>
            {text("取消", "Cancel")}
          </Button>
          <Button
            type="button"
            onClick={() => {
              if (parsed.value) onSubmit(state.approval.id, parsed.value);
            }}
            disabled={submitDisabled}
          >
            {isSubmitting ? text("提交中...", "Submitting...") : text("修改并批准", "Modify and approve")}
          </Button>
        </div>
      </div>
    </ConfigDialog>
  );
}

function ToolCallsTable({ toolCalls }: { toolCalls: ToolCall[] }) {
  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
          <Wrench className="h-4 w-4" />
          工具调用
        </div>
        <span className="text-xs text-slate-500">{toolCalls.length}</span>
      </CardHeader>
      <Table>
        <thead className="bg-slate-50 text-slate-500">
          <tr>
            <Th>工具</Th>
            <Th>状态</Th>
            <Th>风险</Th>
            <Th>
              <TermHint description="工具能力版本">能力版本</TermHint>
            </Th>
            <Th>
              <TermHint description="工具能力内容哈希">内容哈希</TermHint>
            </Th>
            <Th>
              <TermHint description="工具能力配置哈希">配置哈希</TermHint>
            </Th>
            <Th>Adapter</Th>
            <Th>延迟</Th>
            <Th>输出摘要</Th>
          </tr>
        </thead>
        <tbody>
          {toolCalls.map((call) => (
            <tr key={call.id} className="border-t border-slate-100">
              <Td className="font-mono">
                <div>{call.tool_name}</div>
                <div className="mt-1 max-w-40 break-all text-[11px] text-slate-500">{call.id}</div>
              </Td>
              <Td><Badge tone={statusTone(call.status)}>{statusLabel(call.status)}</Badge></Td>
              <Td>{riskLabel(call.risk_level)}</Td>
              <Td>
                <div className="font-mono text-[11px] text-slate-700">
                  {shortCapability(call.capability_version_id)}
                </div>
              </Td>
              <Td className="font-mono text-[11px] text-slate-500">
                {shortCapability(call.capability_content_sha256)}
              </Td>
              <Td className="font-mono text-[11px] text-slate-500">
                {shortCapability(call.capability_config_sha256)}
              </Td>
              <Td>
                <AdapterSnapshotBadge call={call} />
              </Td>
              <Td className="font-mono">{call.duration_ms}ms</Td>
              <Td className="max-w-72 text-slate-500">
                <div className="truncate" title={call.output_summary}>
                  {toolOutputSummary(call)}
                </div>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  );
}

function AdapterSnapshotBadge({ call }: { call: ToolCall }) {
  const adapter = adapterSnapshot(call);
  if (!adapter) return <span className="text-xs text-slate-400">未提供</span>;
  return (
    <span title={`${adapter.slug} · ${adapter.sha}`}>
      <Badge tone="info" className="font-mono">
        {adapter.sha.slice(0, 8)}
      </Badge>
    </span>
  );
}

function adapterSnapshot(call: ToolCall): { slug: string; sha: string } | null {
  const snapshot = call.capability_snapshot_json;
  const adapter = snapshot?.adapter;
  if (!adapter || typeof adapter !== "object") return null;
  const record = adapter as Record<string, unknown>;
  const sha = typeof record.adapter_sha256 === "string" ? record.adapter_sha256 : "";
  if (!sha) return null;
  return {
    slug: typeof record.slug === "string" ? record.slug : call.tool_name,
    sha,
  };
}

export function shortCapability(value?: string | null) {
  return value ? value.slice(0, 18) : "未提供";
}

export function toolOutputSummary(call: ToolCall): string {
  if (call.status === "APPROVED") return "已批准，等待执行";
  if (call.status === "PENDING_APPROVAL") return "等待审批";
  return call.output_summary || "无输出";
}

const RUN_DETAIL_VALUE_LABELS: Record<string, string> = {
  authoritative: "权威组装",
  sufficient: "证据充足",
  insufficient: "证据不足",
  available: "可用",
  unavailable: "不可用",
  local_knowledge: "本地知识库",
  dify_connector: "Dify 连接器",
  coze_connector: "Coze 连接器",
  web: "网页补充",
  fallback: "后备检索",
  local_evidence_sufficient: "本地证据充足",
  seed_fixture_local_evidence: "演示夹具本地证据",
  knowledge_chunk: "知识分块",
  web_source: "网页来源",
  selected_for_prompt: "已纳入提示词",
  allowed: "已允许",
  denied: "已拒绝",
  redacted: "已脱敏",
  manifest: "组装清单",
  recomputable_v2: "可复算 v2",
  success: "成功",
  error: "错误",
  chars_div_4: "字符数/4",
  cl100k_base: "cl100k_base",
  unknown: "未知",
};

export function runDetailValueLabel(value?: string | null): string {
  if (!value) return "未提供";
  return RUN_DETAIL_VALUE_LABELS[value] ?? statusLabel(value);
}

export function optimisticApprovalDecision(
  workspace: AgentRunWorkspace | undefined,
  approvalId: string,
  nextStatus: "APPROVED" | "DENIED",
): AgentRunWorkspace | undefined {
  if (!workspace) return workspace;
  const nextApprovals = workspace.approvals.map((approval) =>
    approval.id !== approvalId
      ? approval
      : {
          ...approval,
          status: nextStatus,
          decided_at: new Date().toISOString(),
        },
  );
  const nextToolCalls = workspace.tool_calls.map((toolCall) =>
    nextApprovals.some((approval) => approval.tool_call_id === toolCall.id && approval.id === approvalId)
      ? {
          ...toolCall,
          status: nextStatus,
          error_message: nextStatus === "APPROVED" ? null : toolCall.error_message,
        }
      : toolCall,
  );
  return {
    ...workspace,
    approvals: nextApprovals,
    tool_calls: nextToolCalls,
  };
}

export function mergeApprovalPage(
  workspace: AgentRunWorkspace | undefined,
  approvals: ToolApproval[],
): AgentRunWorkspace | undefined {
  if (!workspace) return workspace;
  const approvalById = new Map(approvals.map((approval) => [approval.id, approval]));
  return {
    ...workspace,
    approvals: workspace.approvals.map((approval) => approvalById.get(approval.id) ?? approval),
    tool_calls: workspace.tool_calls.map((toolCall) => {
      const approval = workspace.approvals.find((item) => item.tool_call_id === toolCall.id);
      if (!approval) return toolCall;
      const updated = approvalById.get(approval.id);
      if (!updated) return toolCall;
      return {
        ...toolCall,
        status: updated.status === "APPROVED" ? "APPROVED" : "DENIED",
        error_message: updated.status === "APPROVED" ? null : updated.reason,
      };
    }),
  };
}

function approvalInputJson(approval: ToolApproval): Record<string, unknown> {
  const requestInput = approval.request_json.input_json;
  if (isJsonRecord(requestInput)) return requestInput;
  return {};
}

function parseApprovalJson(jsonText: string): {
  value: Record<string, unknown> | null;
  error: string | null;
} {
  if (jsonText.trim().length === 0) {
    return { value: null, error: "JSON payload is required" };
  }
  try {
    const value = JSON.parse(jsonText) as unknown;
    if (!isJsonRecord(value)) {
      return { value: null, error: "payload must be a JSON object" };
    }
    return { value, error: null };
  } catch (error) {
    return {
      value: null,
      error: error instanceof Error ? error.message : "parse failed",
    };
  }
}

function isJsonRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function EventRow({ event }: { event: AgentEvent }) {
  return (
    <div className="rounded-md border border-slate-100 bg-white p-2">
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs text-slate-900">#{event.sequence}</span>
        <Badge tone={isLangGraphEvent(event.event_type) ? langGraphEventTone(event.event_type) : statusTone(event.event_type)}>
          {eventLabel(event.event_type)}
        </Badge>
      </div>
      <div className="mt-1 font-mono text-[11px] text-slate-500">{formatShortDate(event.created_at)}</div>
      {isLangGraphEvent(event.event_type) ? (
        <div className="mt-1 line-clamp-2 text-[11px] text-slate-600">
          {langGraphEventPayloadSummary(event.payload_json)}
        </div>
      ) : null}
      {event.trace_id && (
        <Link
          to={`/observability/trace?trace_id=${encodeURIComponent(event.trace_id)}`}
          className="mt-1 block truncate font-mono text-[10px] text-cyan-700 hover:underline"
        >
          {event.trace_id}
        </Link>
      )}
    </div>
  );
}

function isLangGraphEvent(eventType: string) {
  return eventType.startsWith("LANGGRAPH_");
}

function langGraphEventTone(eventType: string) {
  if (eventType.endsWith("_FAILED") || eventType.endsWith("_DENIED")) return "failed" as const;
  if (eventType.endsWith("_COMPLETED")) return "success" as const;
  return "info" as const;
}

function langGraphEventPayloadSummary(payload: Record<string, unknown>) {
  const fields = [
    ["workflow", payload.workflow_name ?? payload.workflow_id ?? payload.capability_id],
    ["graph", payload.graph_id],
    ["node", payload.node_id ?? payload.node_name ?? payload.step_key],
    ["tool", payload.tool_name],
    ["denial", payload.denial_code ?? payload.error_code],
  ]
    .filter(([, value]) => typeof value === "string" && value.trim())
    .map(([label, value]) => `${label}: ${String(value)}`);
  return fields.length ? fields.join(" · ") : "LangGraph event payload 已写入 EventStore";
}

function Metric({ label, value }: { label: React.ReactNode; value: string }) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50 p-2">
      <div className="text-[10px] text-slate-500">{label}</div>
      <div className="mt-1 truncate font-mono text-xs text-slate-900">{value}</div>
    </div>
  );
}

function collectSpecialistEvidence(subagents: Subagent[]) {
  const items = subagents
    .filter((subagent) => subagent.output || subagent.specialist)
    .map((subagent) => {
      const output = subagent.output?.output_json ?? {};
      const exceeded = subagent.output?.budget_exceeded_json ?? [];
      return {
        id: subagent.id,
        slug: subagent.specialist?.slug ?? "specialist",
        role: subagent.specialist?.role ?? "specialist",
        status: subagent.status,
        fanoutBatchId: subagent.fanout_batch_id,
        fanoutIndex: subagent.fanout_index,
        fanoutTotal: subagent.fanout_total,
        output,
        budgetExceeded: exceeded,
        summary: specialistOutputSummary(output),
      };
    });
  const grouped = new Map<string, typeof items>();
  for (const item of items) {
    const key = item.fanoutBatchId ?? item.id;
    grouped.set(key, [...(grouped.get(key) ?? []), item]);
  }
  return Array.from(grouped.entries()).map(([key, groupItems]) => {
    const batchId = groupItems[0]?.fanoutBatchId ?? null;
    const ordered = [...groupItems].sort((left, right) => {
      const leftIndex = typeof left.fanoutIndex === "number" ? left.fanoutIndex : 9999;
      const rightIndex = typeof right.fanoutIndex === "number" ? right.fanoutIndex : 9999;
      return leftIndex - rightIndex;
    });
    return {
      key,
      batchId,
      label: batchId ? `Fanout 批次 · ${ordered.length} 个专家` : "单专家输出",
      items: ordered,
    };
  });
}

function specialistOutputSummary(output: Record<string, unknown>) {
  const summary = output.summary ?? output.answer;
  if (typeof summary === "string" && summary.trim().length > 0) return summary;
  const issues = output.issues;
  if (Array.isArray(issues)) return `${issues.length} issue(s)`;
  const citations = output.citations;
  if (Array.isArray(citations)) return `${citations.length} citation(s)`;
  const violations = output.violations;
  if (Array.isArray(violations)) return `${violations.length} violation(s)`;
  return "结构化输出已写入";
}

function recordField(value: Record<string, unknown>, key: string): Record<string, unknown> {
  const field = value[key];
  return field && typeof field === "object" && !Array.isArray(field)
    ? (field as Record<string, unknown>)
    : {};
}

function arrayField(value: Record<string, unknown>, key: string): unknown[] {
  const field = value[key];
  return Array.isArray(field) ? field : [];
}

function stringField(value: Record<string, unknown>, key: string): string | null {
  const field = value[key];
  return typeof field === "string" && field.trim() ? field : null;
}

function numberField(value: Record<string, unknown>, key: string): number | null {
  const field = value[key];
  return typeof field === "number" && Number.isFinite(field) ? field : null;
}

function boolField(value: Record<string, unknown>, key: string): boolean {
  return value[key] === true;
}

function countBy<T>(items: T[], keyFn: (item: T) => string) {
  return items.reduce<Record<string, number>>((counts, item) => {
    const key = keyFn(item);
    counts[key] = (counts[key] ?? 0) + 1;
    return counts;
  }, {});
}

type OrchestrationStateSummary = {
  totalAssignments: number;
  activeOrPendingCount: number;
  failedCount: number;
  successCount: number;
  allSuccessful: boolean;
  reduceCompleted: boolean;
  message: string;
};

const ACTIVE_OR_PENDING_ASSIGNMENT_STATUSES = new Set(["PENDING", "QUEUED", "RUNNING"]);

export function allAssignmentsSuccessful(assignments: AgentAssignment[]): boolean {
  return assignments.length > 0 && assignments.every((assignment) => assignment.status === "SUCCESS");
}

export function orchestrationStateSummary(
  assignments: AgentAssignment[],
  handoffs: AgentHandoff[],
  reduceCompleted: boolean,
): OrchestrationStateSummary {
  const activeOrPendingCount = assignments.filter((assignment) =>
    ACTIVE_OR_PENDING_ASSIGNMENT_STATUSES.has(assignment.status),
  ).length;
  const failedCount = assignments.filter((assignment) => assignment.status === "FAILED").length;
  const successCount = assignments.filter((assignment) => assignment.status === "SUCCESS").length;
  const totalAssignments = assignments.length;
  const allSuccessful = totalAssignments > 0 && successCount === totalAssignments;
  const handoffText = handoffs.length ? `，${handoffs.length} 条交接` : "";
  const reduceText = reduceCompleted ? "，Reduce 已完成" : "";
  let message = "尚未创建多智能体 assignment，点击“创建多智能体编排”会先生成分支。";
  if (totalAssignments > 0) {
    if (activeOrPendingCount > 0) {
      message = `${activeOrPendingCount} 个分支待执行，${successCount} 个已成功${failedCount ? `，${failedCount} 个失败` : ""}${handoffText}。`;
    } else if (allSuccessful) {
      message = `无待执行分支，${successCount} 个 assignment 已成功${handoffText}${reduceText || "，Reduce 可保持幂等"}。`;
    } else if (failedCount > 0) {
      message = `无待执行分支，${failedCount} 个 assignment 失败，${successCount} 个已成功${handoffText}。`;
    } else {
      message = `${totalAssignments} 个 assignment 当前没有待执行状态${handoffText}。`;
    }
  }
  return {
    totalAssignments,
    activeOrPendingCount,
    failedCount,
    successCount,
    allSuccessful,
    reduceCompleted,
    message,
  };
}

export function orchestrationResultDescription(
  message: string,
  assignments: AgentAssignment[],
  handoffs: AgentHandoff[],
): string {
  const statusCounts = countBy(assignments, (assignment) => assignment.status);
  const statusText = Object.entries(statusCounts)
    .map(([status, count]) => `${statusLabel(status)} ${count}`)
    .join("，");
  const prefix = message.trim() || "多智能体编排状态已更新。";
  const evidence = [
    `${assignments.length} 个 assignment`,
    `${handoffs.length} 条交接`,
    statusText,
  ].filter(Boolean);
  return `${prefix}${evidence.length ? ` 当前证据：${evidence.join("，")}。` : ""}`;
}

async function refreshWorkspaceQuery(
  queryClient: QueryClient,
  queryKey: readonly unknown[],
) {
  await queryClient.invalidateQueries({ queryKey, refetchType: "active" });
  await queryClient.refetchQueries({ queryKey, type: "active" });
}

export function resolveWorkspaceReturnPath({
  requestedReturnTo,
  requestedConversationId,
  runId,
  agentId,
}: {
  requestedReturnTo: string | null;
  requestedConversationId: string | null;
  runId?: string | null;
  agentId: string | null;
}): string {
  if (requestedReturnTo) {
    const decoded = safeDecodeURIComponent(requestedReturnTo);
    if (isSafeWorkspaceReturnPath(decoded)) return decoded;
  }
  const saved = readWorkspaceReturnTarget(runId);
  if (
    saved !== null &&
    (!agentId || saved.agentId === agentId)
  ) {
    return workspaceReturnPath(saved);
  }
  return workspaceReturnPath({
    agentId: agentId ?? "default",
    conversationId: requestedConversationId,
  });
}

export function workspaceReturnTargetFromPath(
  requestedReturnTo: string | null,
  requestedConversationId: string | null,
) {
  if (!requestedReturnTo) return null;
  const decoded = safeDecodeURIComponent(requestedReturnTo);
  if (!isSafeWorkspaceReturnPath(decoded)) return null;
  try {
    const url = new URL(decoded, "http://harness.local");
    const agentId = decodeURIComponent(
      url.pathname.slice("/agents/".length).replace(/\/workspace$/, ""),
    );
    if (!agentId) return null;
    return {
      agentId,
      conversationId: url.searchParams.get("conversation_id") ?? requestedConversationId,
    };
  } catch {
    return null;
  }
}

function safeDecodeURIComponent(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function isSafeWorkspaceReturnPath(value: string): boolean {
  if (!value.startsWith("/agents/")) return false;
  if (value.startsWith("//")) return false;
  try {
    const url = new URL(value, "http://harness.local");
    return (
      url.origin === "http://harness.local" &&
      /^\/agents\/[^/]+\/workspace$/.test(url.pathname)
    );
  } catch {
    return false;
  }
}

function formatTokenMetric(value: number | null): string {
  if (value === null) return "未提供";
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(value);
}

function formatPercentMetric(value: number | null): string {
  if (value === null) return "未提供";
  return `${new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 1 }).format(value)}%`;
}

function parseReplaySequence(value: string) {
  const normalized = value.trim();
  if (!normalized) {
    return undefined;
  }
  const sequence = Number(normalized);
  return Number.isFinite(sequence) && sequence > 0 ? sequence : undefined;
}
