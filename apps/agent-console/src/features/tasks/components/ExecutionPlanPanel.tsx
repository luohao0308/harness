import { CheckCircle2, Clock, GitBranch } from "lucide-react";

import type { AgentEvent, Subagent, TaskPlan, TaskPlanDiff, TaskPlanVersionSummary } from "../api";
import { Badge, type BadgeTone } from "../../../components/ui/badge";
import { Card, CardHeader } from "../../../components/ui/card";
import { Dot, statusTone } from "../../../components/ui/badge";
import {
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
}: {
  events: AgentEvent[];
  plan?: TaskPlan;
  planVersions?: TaskPlanVersionSummary[];
  planDiff?: TaskPlanDiff;
  subagents?: Subagent[];
}) {
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
    })) ??
    eventPlan?.steps ??
    [];

  return (
    <Card>
      <CardHeader>
        <div className="text-[11px] tracking-widest text-slate-500">执行计划</div>
        <span className="font-mono text-[10px] text-slate-400">
          {steps.length} steps
          {plan ? ` · ${plannerSourceLabel(plan.planner_source)} · ${plan.planner_attempts} 次` : ""}
        </span>
      </CardHeader>
      {planVersions.length > 0 && (
        <div className="border-b border-slate-100 px-3 py-2 text-[10px] text-slate-500">
          <div className="flex flex-wrap items-center gap-1.5">
            <span>计划版本</span>
            <span className="font-mono text-slate-800">v{planVersions[0].version}</span>
            <span>共 {planVersions.length} 版</span>
            {planDiff && (
              <>
                <span>·</span>
                <span>
                  对比 v{planDiff.from_version} → v{planDiff.to_version}
                </span>
                <span className="text-emerald-600">新增 {planDiff.added}</span>
                <span className="text-amber-600">变更 {planDiff.changed}</span>
                <span className="text-rose-600">移除 {planDiff.removed}</span>
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
      <div className="space-y-1 p-2">
        {steps.length === 0 ? (
          <div className="rounded-md border border-dashed border-slate-200 p-3 text-xs text-slate-500">
            任务启动后这里会显示规划结果。
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
                  artifactExpectations.length > 0) && (
                  <div className="mt-2 space-y-1 pl-6 text-[10px] text-slate-500">
                    {toolHints.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        <span className="text-slate-400">工具</span>
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
                        <span className="text-slate-400">验收 </span>
                        <span>{acceptanceCriteria.join("；")}</span>
                      </div>
                    )}
                    {artifactExpectations.length > 0 && (
                      <div>
                        <span className="text-slate-400">产物 </span>
                        <span>{artifactExpectations.join("；")}</span>
                      </div>
                    )}
                  </div>
                )}
                {isAsync && (
                  <div className="mt-2 flex flex-wrap items-center gap-1 pl-6 text-[10px] text-slate-500">
                    <GitBranch className="h-3 w-3 text-slate-400" />
                    <span>派生子 Agent</span>
                    {assignedAgentId ? (
                      <>
                        <span className="font-mono text-slate-700">{assignedAgentId.slice(0, 8)}</span>
                        <Badge tone={statusTone(assignedSubagent?.status ?? "PENDING")}>
                          {statusLabel(assignedSubagent?.status ?? "PENDING")}
                        </Badge>
                      </>
                    ) : (
                      <span className="text-slate-400">等待派生</span>
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
