import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Check, Database, FlaskConical, GitBranch, Play, RotateCcw, Shield, Wrench, X } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { Table, Td, Th } from "../../../components/ui/table";
import { useI18n } from "../../../lib/i18n";
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
  type AgentEvent,
  type ReplayResult,
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
  const workspace = useQuery({
    queryKey: ["agent-run-workspace", runId, retrievalSessionId, promptManifestId],
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
  const datasetsQuery = useQuery({ queryKey: ["eval-datasets"], queryFn: listEvalDatasets });
  const execute = useMutation({
    mutationFn: () => executeAgentRun(runId!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["agent-run-workspace", runId] }),
  });
  const orchestrate = useMutation({
    mutationFn: () => orchestrateAgentRun(runId!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["agent-run-workspace", runId] }),
  });
  const replay = useMutation({
    mutationFn: () => replayTask(runId!, parseReplaySequence(replaySequence)),
    onSuccess: (result) => setReplayResult(result),
  });
  const approve = useMutation({
    mutationFn: (approvalId: string) => approveToolApproval(runId!, approvalId, "Approved from Agent Run Detail"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["agent-run-workspace", runId] }),
  });
  const reject = useMutation({
    mutationFn: (approvalId: string) => rejectToolApproval(runId!, approvalId, "Rejected from Agent Run Detail"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["agent-run-workspace", runId] }),
  });
  const saveEvalCase = useMutation({
    mutationFn: async () => {
      let datasetId = selectedEvalDatasetId;
      if (!datasetId || datasetId === DEFAULT_EVAL_DATASET_ID) {
        const dataset = await createEvalDataset({
          name: "Saved Runs",
          description: "Run Detail cases saved from completed or failed agent runs.",
        });
        datasetId = dataset.id;
      }
      if (!datasetId || !runId) throw new Error("No dataset or run");
      const policyDecisions = Array.from(
        new Set((grounding?.policy_audits ?? []).map((audit) => audit.decision)),
      );
      const groundingContract =
        grounding?.selected_retrieval_session_id || grounding?.selected_prompt_manifest_id
          ? {
              grounding_contract: {
                retrieval_session_id: grounding.selected_retrieval_session_id ?? undefined,
                prompt_manifest_id: grounding.selected_prompt_manifest_id ?? undefined,
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
              {run && <Badge tone={statusTone(run.status)}>{run.status}</Badge>}
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
                  <select
                    aria-label={text("选择数据集", "Select Dataset")}
                    value={selectedEvalDatasetValue}
                    onChange={(event) => {
                      setSelectedEvalDatasetId(event.target.value);
                      setSaveEvalSuccess(false);
                    }}
                    disabled={saveEvalCase.isPending || datasetsQuery.isLoading}
                    className="h-8 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-700"
                  >
                    {evalDatasetOptions.map((dataset) => (
                      <option key={dataset.id} value={dataset.id}>
                        {dataset.name}
                      </option>
                    ))}
                  </select>
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
                  {grounding.local_status}
                </Badge>
              </CardHeader>
              <div className="space-y-3 p-3 text-sm">
                <div className="grid grid-cols-2 gap-2 text-xs md:grid-cols-3">
                  <Metric label="向量" value={grounding.vector_capability} />
                  <Metric label="命中" value={String(grounding.retrieval_hits.length)} />
                  <Metric label="已依据" value={grounding.grounded ? "是" : "否"} />
                  <Metric label="Provider" value={grounding.grounding_provider} />
                  <Metric label="Fixture evidence" value={grounding.fixture_grounded ? "是" : "否"} />
                  <Metric label="Source-bound" value={grounding.verified_grounded ? "是" : "否"} />
                  <Metric label="Citation count" value={String(grounding.citations.length)} />
                </div>
                <div className="truncate font-mono text-[11px] text-slate-500" title={grounding.grounding_verification_reason}>
                  {grounding.grounding_verification_reason}
                </div>
                <p className="text-xs text-slate-500">{grounding.evidence_summary}</p>
                {grounding.inferred_fallback && (
                  <div className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
                    fallback {grounding.fallback_reason ?? "latest"} · retrieval{" "}
                    {grounding.selected_retrieval_session_id ?? "n/a"}
                  </div>
                )}
                {grounding.prompt_manifest && (
                  <div className="space-y-2">
                    <div className="text-xs font-medium text-slate-700">Prompt 组装审计</div>
                    <div className="rounded-md border border-slate-100 bg-slate-50 p-2 text-xs">
                      <div className="font-mono text-[11px] text-slate-500">
                        manifest {grounding.prompt_manifest.id}
                      </div>
                      <div className="mt-1 text-slate-600">
                        included {grounding.prompt_manifest.included_retrieval_hit_ids_json.length} · omitted{" "}
                        {grounding.prompt_manifest.omitted_candidates_json.length}
                      </div>
                      <div className="mt-1 break-all text-slate-500">
                        correlation {grounding.prompt_manifest.grounding_correlation_id}
                      </div>
                      <div className="mt-1 break-all text-slate-500">
                        sha256 {grounding.prompt_manifest.evidence_text_sha256}
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
                            {audit.decision}
                          </Badge>
                          <span className="font-mono text-[11px] text-slate-500">
                            {audit.source_kind ?? "manifest"}
                          </span>
                        </div>
                        <div className="mt-1 text-slate-600">{audit.reason}</div>
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
                            {hit.source_kind} #{hit.rank} score={hit.score.toFixed(3)}
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
                              {citation.source_kind}
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
                          {source.status}
                          {source.error_message ? ` · ${source.error_message}` : ""}
                        </div>
                        <div className="mt-1 flex flex-wrap gap-1 text-slate-500">
                          <Badge tone={source.metadata_json.fixture ? "warning" : "info"}>
                            {String(source.metadata_json.provider ?? "unknown")}
                          </Badge>
                          {source.metadata_json.request_id ? (
                            <Badge tone="neutral">
                              {String(source.metadata_json.request_id)}
                            </Badge>
                          ) : null}
                          {source.metadata_json.raw_content_available ? (
                            <Badge tone="warning">raw</Badge>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </Card>
          )}

          <Card id="plan">
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <GitBranch className="h-4 w-4" />
                计划 DAG
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
                    <Badge tone={statusTone(step.status)}>{step.status}</Badge>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    <Badge tone={step.execution_mode === "async" ? "purple" : "neutral"}>{step.execution_mode}</Badge>
                    {step.requires_sandbox && <Badge tone="warning">沙箱</Badge>}
                    {step.can_spawn_subagent && <Badge tone="purple">子代理</Badge>}
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
                        <Badge tone={statusTone(subagent.status)}>{subagent.status}</Badge>
                      </div>
                      <div className="mt-1 text-[11px] text-slate-500">{subagent.agent_type}</div>
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
                    <Badge tone={statusTone(call.status)}>{call.status}</Badge>
                  </div>
                  <div className="mt-1 text-slate-500">
                    {call.prompt_tokens + call.completion_tokens} 标记 · {call.duration_ms}ms
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-1 text-[11px] text-slate-500">
                    <Metric label="Attempt" value={String(call.attempt_index)} />
                    <Metric label="Terminal" value={call.terminal_status ?? "n/a"} />
                    <Metric label="Manifest" value={call.prompt_manifest_id ?? "n/a"} />
                    <Metric label="Correlation" value={call.grounding_correlation_id ?? "n/a"} />
                    <Metric label="Request hash" value={call.model_request_sha256 ?? "n/a"} />
                    <Metric label="Hash audit" value={call.hash_recomputability_status} />
                  </div>
                  <div className="mt-1 truncate font-mono text-[11px] text-slate-400" title={call.request_message_hashes_sha256 ?? undefined}>
                    schema v{call.model_request_hash_schema_version} · messages{" "}
                    {call.request_message_hashes_json.length} ·{" "}
                    {call.request_message_hashes_sha256 ?? "n/a"}
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
              <Badge tone={statusTone(approval.status)}>{approval.status}</Badge>
              <span className="font-mono text-[11px] text-slate-500">{approval.risk_level}</span>
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
            <Th>延迟</Th>
            <Th>输出</Th>
          </tr>
        </thead>
        <tbody>
          {toolCalls.map((call) => (
            <tr key={call.id} className="border-t border-slate-100">
              <Td className="font-mono">{call.tool_name}</Td>
              <Td><Badge tone={statusTone(call.status)}>{call.status}</Badge></Td>
              <Td>{call.risk_level}</Td>
              <Td className="font-mono">{call.duration_ms}ms</Td>
              <Td className="max-w-72 truncate text-slate-500">{call.output_summary}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  );
}

function EventRow({ event }: { event: AgentEvent }) {
  return (
    <div className="rounded-md border border-slate-100 bg-white p-2">
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs text-slate-900">#{event.sequence}</span>
        <Badge tone={statusTone(event.event_type)}>{event.event_type}</Badge>
      </div>
      <div className="mt-1 font-mono text-[11px] text-slate-500">{formatShortDate(event.created_at)}</div>
      {event.trace_id && <div className="mt-1 truncate font-mono text-[10px] text-slate-400">{event.trace_id}</div>}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50 p-2">
      <div className="text-[10px] text-slate-500">{label}</div>
      <div className="mt-1 truncate font-mono text-xs text-slate-900">{value}</div>
    </div>
  );
}

function parseReplaySequence(value: string) {
  const normalized = value.trim();
  if (!normalized) {
    return undefined;
  }
  const sequence = Number(normalized);
  return Number.isFinite(sequence) && sequence > 0 ? sequence : undefined;
}
