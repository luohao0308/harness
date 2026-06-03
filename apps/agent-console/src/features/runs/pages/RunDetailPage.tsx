import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, BrainCircuit, Check, Database, FlaskConical, Gauge, GitBranch, Play, RotateCcw, Shield, Wrench, X } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { feedbackErrorMessage, notifyFeedback } from "../../../components/ui/feedback-toast";
import { Input } from "../../../components/ui/input";
import { MenuSelect } from "../../../components/ui/menu-select";
import { Table, Td, Th } from "../../../components/ui/table";
import { TermHint } from "../../../components/ui/term";
import { useI18n } from "../../../lib/i18n";
import { eventLabel, executionModeLabel, riskLabel, statusLabel } from "../../../lib/labels";
import { formatShortDate } from "../../../lib/utils";
import {
  approveToolApproval,
  createEvalDataset,
  createEvalCaseFromRun,
  executeAgentRun,
  getAgentRunWorkspace,
  listEvalDatasets,
  orchestrateAgentRun,
  rejectToolApproval,
  replayTask,
  type AgentRunWorkspace,
  type AgentEvent,
  type ReplayResult,
  type Subagent,
  type ToolApproval,
  type ToolCall,
} from "../../tasks/api";

const DEFAULT_EVAL_DATASET_ID = "__create_default_eval_dataset__";

export function RunDetailPage({ focus }: { focus?: "events" | "subagents" }) {
  const { text } = useI18n();
  const { runId } = useParams();
  const [searchParams] = useSearchParams();
  const retrievalSessionId = searchParams.get("retrieval_session_id") ?? undefined;
  const promptManifestId = searchParams.get("prompt_manifest_id") ?? undefined;
  const queryClient = useQueryClient();
  const [replaySequence, setReplaySequence] = useState("");
  const [replayResult, setReplayResult] = useState<ReplayResult | null>(null);
  const [saveEvalSuccess, setSaveEvalSuccess] = useState(false);
  const [selectedEvalDatasetId, setSelectedEvalDatasetId] = useState("");
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
    onSuccess: async () => {
      notifyFeedback({
        tone: "success",
        title: text("多智能体编排已启动", "Orchestration started"),
        description: text("团队与事件状态会继续同步到当前页面。", "Team and event updates will keep streaming into this page."),
      });
      await queryClient.invalidateQueries({ queryKey: workspaceQueryKey });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("多智能体编排失败", "Orchestration failed"),
        description: feedbackErrorMessage(error, text("请检查运行状态、模型设置或稍后重试。", "Check the run state, model settings, or retry.")),
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

  useEffect(() => {
    if (selectedEvalDatasetId || !datasetsQuery.data?.items.length) return;
    setSelectedEvalDatasetId(datasetsQuery.data.items[0].id);
  }, [datasetsQuery.data?.items, selectedEvalDatasetId]);
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
                <Metric label="子代理" value={String(run.max_subagents)} />
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
                <GitBranch className="h-3.5 w-3.5" />
                {text("编排多智能体", "Orchestrate Agents")}
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
              <Link to="/agents/default/workspace">
                <Button>
                  <Bot className="h-3.5 w-3.5" />
                  {text("回到工作台", "Back to Workspace")}
                </Button>
              </Link>
            </div>
          </Card>

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
                    <Badge tone={step.execution_mode === "async" ? "purple" : "neutral"}>
                      {executionModeLabel(step.execution_mode)}
                    </Badge>
                    {step.requires_sandbox && <Badge tone="warning">沙箱</Badge>}
                    {step.can_spawn_subagent && <Badge tone="purple">子代理</Badge>}
                    {step.recommended_specialist_slug ? (
                      <Badge tone="purple">专家: {step.recommended_specialist_slug}</Badge>
                    ) : null}
                    {step.fanout_specialist_slugs.length > 1 ? (
                      <Badge tone="info">
                        并行: {step.fanout_specialist_slugs.length} · {step.fanout_aggregation}
                      </Badge>
                    ) : null}
                    {dependsOn.length > 0 ? (
                      <Badge tone="info">依赖: {dependsOn.join(", ")}</Badge>
                    ) : (
                      <Badge tone="neutral">依赖: 无</Badge>
                    )}
                    {step.tool_hints.map((tool) => (
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
                        <span className="font-mono text-xs">{subagent.id.slice(0, 8)}</span>
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

function ApprovalsPanel({
  approvals,
  onApprove,
  onReject,
}: {
  approvals: ToolApproval[];
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
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
              <div className="mt-2 flex gap-1">
                <Button onClick={() => onApprove(approval.id)}>
                  <Check className="h-3.5 w-3.5" />
                  批准
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
            <Th>延迟</Th>
            <Th>输出摘要</Th>
          </tr>
        </thead>
        <tbody>
          {toolCalls.map((call) => (
            <tr key={call.id} className="border-t border-slate-100">
              <Td className="font-mono">{call.tool_name}</Td>
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

function EventRow({ event }: { event: AgentEvent }) {
  return (
    <div className="rounded-md border border-slate-100 bg-white p-2">
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs text-slate-900">#{event.sequence}</span>
        <Badge tone={statusTone(event.event_type)}>{eventLabel(event.event_type)}</Badge>
      </div>
      <div className="mt-1 font-mono text-[11px] text-slate-500">{formatShortDate(event.created_at)}</div>
      {event.trace_id && <div className="mt-1 truncate font-mono text-[10px] text-slate-400">{event.trace_id}</div>}
    </div>
  );
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
