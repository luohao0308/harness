import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Check, GitBranch, Play, RotateCcw, Shield, Wrench, X } from "lucide-react";
import { Link, useParams } from "react-router-dom";

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
  executeAgentRun,
  getAgentRunWorkspace,
  orchestrateAgentRun,
  rejectToolApproval,
  replayTask,
  type AgentEvent,
  type ReplayResult,
  type ToolApproval,
  type ToolCall,
} from "../../tasks/api";

export function RunDetailPage({ focus }: { focus?: "events" | "subagents" }) {
  const { text } = useI18n();
  const { runId } = useParams();
  const queryClient = useQueryClient();
  const [replaySequence, setReplaySequence] = useState("");
  const [replayResult, setReplayResult] = useState<ReplayResult | null>(null);
  const workspace = useQuery({
    queryKey: ["agent-run-workspace", runId],
    queryFn: () => getAgentRunWorkspace(runId!),
    enabled: Boolean(runId),
    refetchInterval: 5000,
  });
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
  const data = workspace.data;
  const run = data?.run;
  const latestSequence = useMemo(
    () => Math.max(0, ...(data?.events ?? []).map((event) => event.sequence)),
    [data?.events],
  );

  return (
    <ConsoleShell title={text("Agent Run", "Agent Run")}>
      <div className="grid grid-cols-12 gap-4 p-4">
        <section className="col-span-8 space-y-4">
          <Card className="p-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <Link to="/runs" className="text-xs text-slate-500 hover:text-slate-900">
                    {text("Run 历史", "Run History")}
                  </Link>
                  <span className="text-slate-300">/</span>
                  <span className="font-mono text-xs text-slate-500">{run?.id.slice(0, 8) ?? "..."}</span>
                </div>
                <h1 className="mt-2 text-xl font-semibold text-slate-950">{run?.title ?? text("加载 Run...", "Loading Run...")}</h1>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{run?.goal}</p>
              </div>
              {run && <Badge tone={statusTone(run.status)}>{run.status}</Badge>}
            </div>
            {run && (
              <div className="mt-4 grid grid-cols-4 gap-2 text-xs">
                <Metric label={text("模型", "Model")} value={`${run.model_provider}/${run.model_name}`} />
                <Metric label="Subagents" value={String(run.max_subagents)} />
                <Metric label="Sandbox" value={run.enable_sandbox ? "ON" : "OFF"} />
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
                {text("执行 Plan", "Execute Plan")}
              </Button>
              <Button disabled={!run || orchestrate.isPending} onClick={() => orchestrate.mutate()}>
                <GitBranch className="h-3.5 w-3.5" />
                {text("编排多 Agent", "Orchestrate Agents")}
              </Button>
              <Link to="/agents/default/workspace">
                <Button>
                  <Bot className="h-3.5 w-3.5" />
                  {text("回到 Workspace", "Back to Workspace")}
                </Button>
              </Link>
            </div>
          </Card>

          <Card id="plan">
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <GitBranch className="h-4 w-4" />
                Plan DAG
              </div>
              <span className="text-xs text-slate-500">
                {data?.plan ? `${data.plan.steps.length} steps` : text("暂无 Plan", "No Plan")}
              </span>
            </CardHeader>
            <div className="grid gap-2 p-3">
              {(data?.plan?.steps ?? []).map((step, index) => (
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
                    {step.requires_sandbox && <Badge tone="warning">Sandbox</Badge>}
                    {step.can_spawn_subagent && <Badge tone="purple">Subagent</Badge>}
                    {step.tool_hints.map((tool) => (
                      <Badge key={tool} tone="info">{tool}</Badge>
                    ))}
                  </div>
                </div>
              ))}
              {!workspace.isLoading && !data?.plan && (
                <div className="py-8 text-center text-sm text-slate-500">
                  {text("这个 Run 还没有生成 Plan。", "This Run does not have a Plan yet.")}
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
                {focus === "subagents" ? "Subagents" : "Event Stream"}
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
              <div className="text-sm font-semibold text-slate-900">Model Calls</div>
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
                    {call.prompt_tokens + call.completion_tokens} tokens · {call.duration_ms}ms
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
          Replay
        </div>
        <span className="font-mono text-xs text-slate-500">latest #{latestSequence}</span>
      </CardHeader>
      <div className="space-y-3 p-3">
        <div className="grid grid-cols-[1fr_auto] gap-2">
          <Input
            aria-label={text("Replay sequence", "Replay sequence")}
            className="h-8 font-mono text-xs"
            placeholder={text("输入 sequence，留空重放最新", "Sequence, blank for latest")}
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
                {replayResult.requires_manual_review ? "manual_review" : "replayed"}
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
          Guardrails
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
                  Approve
                </Button>
                <Button onClick={() => onReject(approval.id)}>
                  <X className="h-3.5 w-3.5" />
                  Reject
                </Button>
              </div>
            )}
          </div>
        ))}
        {approvals.length === 0 && <div className="text-xs text-slate-500">No approval requests.</div>}
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
          Tool Calls
        </div>
        <span className="text-xs text-slate-500">{toolCalls.length}</span>
      </CardHeader>
      <Table>
        <thead className="bg-slate-50 text-slate-500">
          <tr>
            <Th>Tool</Th>
            <Th>Status</Th>
            <Th>Risk</Th>
            <Th>Latency</Th>
            <Th>Output</Th>
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
