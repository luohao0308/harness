import { CheckCircle2, Clock, GitBranch, RotateCcw } from "lucide-react";

import type { AgentEvent, Subagent, TaskPlan, TaskPlanDiff, TaskPlanVersionSummary } from "../api";
import { Badge, type BadgeTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { Dot, statusTone } from "../../../components/ui/badge";
import { useI18n } from "../../../lib/i18n";
import {
  eventLabel,
  executionModeLabel,
  planDiffLabel,
  plannerSourceLabel,
  riskLabel,
  statusLabel,
} from "../../../lib/labels";

type PlanStep = {
  key?: string;
  step_key?: string;
  description: string;
  execution_mode: string;
  status?: string;
  can_spawn_subagent?: boolean;
  assigned_agent_id?: string | null;
  tool_hints?: string[];
  acceptance_criteria?: string[];
  risk_level?: string;
  artifact_expectations?: string[];
  quality_notes?: string[];
  trace_summary?: string | null;
  last_event_sequence?: number | null;
  execution_trace?: Array<Record<string, unknown>>;
};

function diffTone(changeType: string): BadgeTone {
  if (changeType === "added") return "success";
  if (changeType === "changed") return "warning";
  if (changeType === "removed") return "failed";
  return "neutral";
}

function stepDescription(step: Record<string, unknown> | null) {
  const description = step?.description;
  return typeof description === "string" && description.length > 0 ? description : "无步骤描述";
}

function stepMode(step: Record<string, unknown> | null) {
  const mode = step?.execution_mode;
  return typeof mode === "string" ? executionModeLabel(mode) : "未知模式";
}

export function ExecutionPlanPanel({
  events,
  plan,
  planVersions = [],
  planDiff,
  subagents = [],
  canResumeSteps = false,
  resumingStepKey = null,
  onResumeFromStep,
}: {
  events: AgentEvent[];
  plan?: TaskPlan;
  planVersions?: TaskPlanVersionSummary[];
  planDiff?: TaskPlanDiff;
  subagents?: Subagent[];
  canResumeSteps?: boolean;
  resumingStepKey?: string | null;
  onResumeFromStep?: (stepKey: string) => void;
}) {
  const { text } = useI18n();
  const generated = events.find((event) => event.event_type === "PLAN_GENERATED");
  const eventPlan = generated?.payload_json.plan as { steps?: PlanStep[] } | undefined;
  const subagentsById = new Map(subagents.map((subagent) => [subagent.id, subagent]));
  const steps: PlanStep[] =
    plan?.steps.map((step) => ({
      step_key: step.step_key,
      description: step.description,
      execution_mode: step.execution_mode,
      status: step.status,
      can_spawn_subagent: step.can_spawn_subagent,
      assigned_agent_id: step.assigned_agent_id,
      tool_hints: step.tool_hints,
      acceptance_criteria: step.acceptance_criteria,
      risk_level: step.risk_level,
      artifact_expectations: step.artifact_expectations,
      quality_notes: step.quality_notes,
      trace_summary: step.trace_summary,
      last_event_sequence: step.last_event_sequence,
      execution_trace: step.execution_trace,
    })) ??
    eventPlan?.steps ??
    [];

  return (
    <Card>
      <CardHeader>
        <div className="text-[11px] tracking-widest text-slate-500">{text("执行计划", "Execution Plan")}</div>
        <span className="font-mono text-[10px] text-slate-400">
          {text(`${steps.length} 个步骤`, `${steps.length} steps`)}
          {plan ? ` · ${plannerSourceLabel(plan.planner_source)} · ${text(`${plan.planner_attempts} 次`, `${plan.planner_attempts} attempts`)}` : ""}
        </span>
      </CardHeader>
      {planVersions.length > 0 && (
        <div className="border-b border-slate-100 px-3 py-2 text-[10px] text-slate-500">
          <div className="flex flex-wrap items-center gap-1.5">
            <span>{text("计划版本", "Plan version")}</span>
            <span className="font-mono text-slate-800">v{planVersions[0].version}</span>
            <span>{text(`共 ${planVersions.length} 版`, `${planVersions.length} versions`)}</span>
            {planDiff && (
              <>
                <span>·</span>
                <span>
                  {text("对比", "Compare")} v{planDiff.from_version} → v{planDiff.to_version}
                </span>
                <span className="text-emerald-600">{text(`新增 ${planDiff.added}`, `Added ${planDiff.added}`)}</span>
                <span className="text-amber-600">{text(`变更 ${planDiff.changed}`, `Changed ${planDiff.changed}`)}</span>
                <span className="text-rose-600">{text(`移除 ${planDiff.removed}`, `Removed ${planDiff.removed}`)}</span>
              </>
            )}
          </div>
          {planDiff && planDiff.step_diffs.some((diff) => diff.change_type !== "unchanged") && (
            <div className="mt-2 space-y-1">
              {planDiff.step_diffs
                .filter((diff) => diff.change_type !== "unchanged")
                .slice(0, 6)
                .map((diff) => (
                  <div
                    key={`${diff.step_key}-${diff.change_type}`}
                    className="rounded border border-slate-100 bg-white px-2 py-1"
                  >
                    <div className="flex items-center gap-1.5">
                      <Badge tone={diffTone(diff.change_type)} className="px-1 py-0 text-[10px]">
                        {planDiffLabel(diff.change_type)}
                      </Badge>
                      <span className="font-mono text-slate-800">{diff.step_key}</span>
                      <span className="text-slate-400">
                        {stepMode(diff.from_step ?? diff.to_step)}
                      </span>
                    </div>
                    <div className="mt-0.5 truncate text-slate-500">
                      {diff.change_type === "changed"
                        ? `${stepDescription(diff.from_step)} → ${stepDescription(diff.to_step)}`
                        : stepDescription(diff.to_step ?? diff.from_step)}
                    </div>
                  </div>
                ))}
            </div>
          )}
        </div>
      )}
      {plan && (
        <div className="border-b border-slate-100 px-3 py-2 text-[10px] text-slate-500">
          <div className="flex flex-wrap items-center gap-1.5">
            <span>{text("规划器质量", "Planner quality")}</span>
            <Badge tone={plan.quality_score >= 80 ? "success" : plan.quality_score >= 60 ? "warning" : "failed"}>
              {plan.quality_score}
            </Badge>
            <span>Prompt 版本 {plan.planner_prompt_version}</span>
            {Object.entries(plan.quality_gates).map(([gate, passed]) => (
              <Badge key={gate} tone={passed ? "success" : "warning"}>
                {text(qualityGateLabel(gate), qualityGateLabelEn(gate))}{" "}
                {passed ? text("通过", "Passed") : text("需关注", "Check")}
              </Badge>
            ))}
          </div>
          {plan.validation_warnings.length > 0 && (
            <div className="mt-2 space-y-1">
              {plan.validation_warnings.slice(0, 4).map((warning) => (
                <div key={warning} className="rounded border border-amber-100 bg-amber-50 px-2 py-1 text-amber-700">
                  {warning}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      <div className="space-y-1 p-2">
        {steps.length === 0 ? (
          <div className="rounded-md border border-dashed border-slate-200 p-3 text-xs text-slate-500">
            {text("任务启动后这里会显示规划结果。", "The generated plan appears here after the task starts.")}
          </div>
        ) : (
          steps.map((step, index) => {
            const stepKey = step.step_key ?? step.key ?? "";
            const completed = events.some(
              (event) =>
                event.event_type === "STEP_COMPLETED" &&
                event.payload_json.step_key === stepKey,
            );
            const running = events.some(
              (event) =>
                event.event_type === "STEP_STARTED" &&
                event.payload_json.step_key === stepKey &&
                !completed,
            );
            const status = step.status ?? (completed ? "COMPLETED" : running ? "RUNNING" : "PENDING");
            const tone = statusTone(status);
            const completedEvent = events.find(
              (event) =>
                event.event_type === "STEP_COMPLETED" &&
                event.payload_json.step_key === stepKey &&
                typeof event.payload_json.assigned_agent_id === "string",
            );
            const assignedAgentId =
              step.assigned_agent_id ??
              (completedEvent?.payload_json.assigned_agent_id as string | undefined) ??
              null;
            const assignedSubagent = assignedAgentId ? subagentsById.get(assignedAgentId) : undefined;
            const isAsync = step.execution_mode === "async" || Boolean(step.can_spawn_subagent);
            const toolHints = step.tool_hints ?? [];
            const acceptanceCriteria = step.acceptance_criteria ?? [];
            const artifactExpectations = step.artifact_expectations ?? [];
            const qualityNotes = step.quality_notes ?? [];
            const executionTrace = step.execution_trace ?? [];
            return (
              <div
                key={stepKey}
                className="rounded-md border border-slate-100 px-2.5 py-2 hover:bg-slate-50"
              >
                <div className="flex items-center gap-2">
                  <span className="w-4 font-mono text-[11px] text-slate-400">{index + 1}</span>
                  {completed ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                  ) : running ? (
                    <Dot tone="running" />
                  ) : (
                    <Clock className="h-3.5 w-3.5 text-slate-300" />
                  )}
                  <span className="min-w-0 flex-1 truncate font-mono text-xs text-slate-800">
                    {stepKey}
                  </span>
                  {onResumeFromStep && (
                    <Button
                      type="button"
                      variant="ghost"
                      className="h-6 px-1.5 text-[10px]"
                      title={text("从此步骤续跑", "Resume from this step")}
                      disabled={!canResumeSteps || resumingStepKey === stepKey || stepKey.length === 0}
                      onClick={() => onResumeFromStep(stepKey)}
                    >
                      <RotateCcw className="h-3 w-3" /> {text("从此续跑", "Resume")}
                    </Button>
                  )}
                  <Dot tone={tone} />
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-1 pl-6 text-[10px] text-slate-500">
                  <span>{step.description}</span>
                  <span>·</span>
                  <span className="rounded border border-slate-200 px-1 py-0.5 text-slate-700">
                    {executionModeLabel(step.execution_mode)}
                  </span>
                  <span>·</span>
                  <Badge tone={statusTone(step.risk_level ?? "low")}>
                    {riskLabel(step.risk_level ?? "low")}
                  </Badge>
                  <span>·</span>
                  <span>{statusLabel(status)}</span>
                </div>
                {(toolHints.length > 0 ||
                  acceptanceCriteria.length > 0 ||
                  artifactExpectations.length > 0 ||
                  qualityNotes.length > 0) && (
                  <div className="mt-2 space-y-1 pl-6 text-[10px] text-slate-500">
                    {toolHints.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        <span className="text-slate-400">{text("工具", "Tools")}</span>
                        {toolHints.map((tool) => (
                          <span
                            key={tool}
                            className="rounded border border-slate-200 px-1 py-0.5 font-mono text-slate-700"
                          >
                            {tool}
                          </span>
                        ))}
                      </div>
                    )}
                    {acceptanceCriteria.length > 0 && (
                      <div>
                        <span className="text-slate-400">{text("验收 ", "Acceptance ")}</span>
                        <span>{acceptanceCriteria.join("；")}</span>
                      </div>
                    )}
                    {artifactExpectations.length > 0 && (
                      <div>
                        <span className="text-slate-400">{text("产物 ", "Artifacts ")}</span>
                        <span>{artifactExpectations.join("；")}</span>
                      </div>
                    )}
                    {qualityNotes.length > 0 && (
                      <div>
                        <span className="text-slate-400">{text("质量提示 ", "Quality ")}</span>
                        <span>{qualityNotes.join("；")}</span>
                      </div>
                    )}
                  </div>
                )}
                {(step.trace_summary || executionTrace.length > 0) && (
                  <div className="mt-2 rounded border border-slate-100 bg-slate-50 px-2 py-1.5 pl-6 text-[10px] text-slate-500">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-slate-400">{text("执行轨迹", "Execution trace")}</span>
                      {step.trace_summary && <span>{step.trace_summary}</span>}
                      {step.last_event_sequence && (
                        <span className="font-mono text-slate-700">#{step.last_event_sequence}</span>
                      )}
                    </div>
                    {executionTrace.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {executionTrace.slice(-4).map((item) => (
                          <Badge key={`${item.sequence}-${item.event_type}`} tone={statusTone(String(item.event_type))}>
                            {eventLabel(String(item.event_type))} #{String(item.sequence)}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                )}
                {isAsync && (
                  <div className="mt-2 flex flex-wrap items-center gap-1 pl-6 text-[10px] text-slate-500">
                    <GitBranch className="h-3 w-3 text-slate-400" />
                    <span>{text("派生子代理", "Spawn subagent")}</span>
                    {assignedAgentId ? (
                      <>
                        <span className="font-mono text-slate-700">{assignedAgentId.slice(0, 8)}</span>
                        <Badge tone={statusTone(assignedSubagent?.status ?? "PENDING")}>
                          {statusLabel(assignedSubagent?.status ?? "PENDING")}
                        </Badge>
                      </>
                    ) : (
                      <span className="text-slate-400">{text("等待派生", "Waiting to spawn")}</span>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </Card>
  );
}

function qualityGateLabel(gate: string) {
  const labels: Record<string, string> = {
    step_count_in_range: "步骤数",
    has_tool_intent: "工具意图",
    has_acceptance_criteria: "验收标准",
    async_steps_have_artifacts: "异步产物",
    high_risk_requires_sandbox: "高风险沙箱",
    unique_step_keys: "步骤键",
  };
  return labels[gate] ?? gate;
}

function qualityGateLabelEn(gate: string) {
  const labels: Record<string, string> = {
    step_count_in_range: "Step count",
    has_tool_intent: "Tool intent",
    has_acceptance_criteria: "Acceptance",
    async_steps_have_artifacts: "Async artifacts",
    high_risk_requires_sandbox: "Risk sandbox",
    unique_step_keys: "Step keys",
  };
  return labels[gate] ?? gate;
}
