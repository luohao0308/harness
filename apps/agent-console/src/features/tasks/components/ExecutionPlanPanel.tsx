import { CheckCircle2, Clock, GitBranch } from "lucide-react";

import type { AgentEvent, Subagent, TaskPlan } from "../api";
import { Badge } from "../../../components/ui/badge";
import { Card, CardHeader } from "../../../components/ui/card";
import { Dot, statusTone } from "../../../components/ui/badge";
import { executionModeLabel, plannerSourceLabel, statusLabel } from "../../../lib/labels";

type PlanStep = {
  key?: string;
  step_key?: string;
  description: string;
  execution_mode: string;
  status?: string;
  can_spawn_subagent?: boolean;
  assigned_agent_id?: string | null;
};

export function ExecutionPlanPanel({
  events,
  plan,
  subagents = [],
}: {
  events: AgentEvent[];
  plan?: TaskPlan;
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
                  <span>{statusLabel(status)}</span>
                </div>
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
