import { CheckCircle2, Clock } from "lucide-react";

import type { AgentEvent } from "../api";
import { Card, CardHeader } from "../../../components/ui/card";
import { Dot, statusTone } from "../../../components/ui/badge";

type PlanStep = {
  key: string;
  description: string;
  execution_mode: string;
};

export function ExecutionPlanPanel({ events }: { events: AgentEvent[] }) {
  const generated = events.find((event) => event.event_type === "PLAN_GENERATED");
  const plan = generated?.payload_json.plan as { steps?: PlanStep[] } | undefined;
  const steps = plan?.steps ?? [];

  return (
    <Card>
      <CardHeader>
        <div className="text-[11px] tracking-widest text-slate-500">执行计划</div>
        <span className="font-mono text-[10px] text-slate-400">{steps.length} steps</span>
      </CardHeader>
      <div className="space-y-1 p-2">
        {steps.length === 0 ? (
          <div className="rounded-md border border-dashed border-slate-200 p-3 text-xs text-slate-500">
            任务启动后这里会显示规划结果。
          </div>
        ) : (
          steps.map((step, index) => {
            const completed = events.some(
              (event) =>
                event.event_type === "STEP_COMPLETED" &&
                event.payload_json.step_key === step.key,
            );
            const running = events.some(
              (event) =>
                event.event_type === "STEP_STARTED" &&
                event.payload_json.step_key === step.key &&
                !completed,
            );
            const status = completed ? "COMPLETED" : running ? "RUNNING" : "PENDING";
            const tone = statusTone(status);
            return (
              <div
                key={step.key}
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
                    {step.key}
                  </span>
                  <Dot tone={tone} />
                </div>
                <div className="mt-1 pl-6 text-[10px] text-slate-500">
                  {step.description} · {step.execution_mode}
                </div>
              </div>
            );
          })
        )}
      </div>
    </Card>
  );
}
