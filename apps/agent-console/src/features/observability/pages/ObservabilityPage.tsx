import { Activity } from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Card, CardHeader } from "../../../components/ui/card";

const metrics = [
  ["任务吞吐", "agent_tasks_total", "任务创建总数"],
  ["任务失败", "agent_tasks_failed_total", "失败任务总数"],
  ["模型调用", "model_calls_total", "模型请求总数"],
  ["工具执行", "sandbox_command_duration_seconds", "沙箱命令耗时"],
  ["WarmPool", "warm_pool_hit_total", "预热容器命中"],
  ["子 Agent", "agent_subagents_running", "运行中的子 Agent"],
];

export function ObservabilityPage() {
  return (
    <ConsoleShell title="观测">
      <div className="space-y-4 p-4">
        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Activity className="h-4 w-4" /> 运行指标
            </div>
            <a className="text-xs text-slate-500" href="http://127.0.0.1:8000/metrics">
              Prometheus 指标 /metrics
            </a>
          </CardHeader>
          <div className="grid grid-cols-3 gap-3 p-3">
            {metrics.map(([title, metric, description]) => (
              <div key={metric} className="rounded-md border border-slate-100 bg-slate-50 p-3">
                <div className="text-xs text-slate-500">{title}</div>
                <div className="mt-1 font-mono text-xs text-slate-900">{metric}</div>
                <div className="mt-2 text-[11px] text-slate-500">{description}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </ConsoleShell>
  );
}
