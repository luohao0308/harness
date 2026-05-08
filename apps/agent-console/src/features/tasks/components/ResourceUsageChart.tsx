import { Activity } from "lucide-react";

import { Card, CardHeader } from "../../../components/ui/card";
import { useI18n } from "../../../lib/i18n";

export function ResourceUsageChart({
  modelCallCount,
  toolCallCount,
}: {
  modelCallCount: number;
  toolCallCount: number;
}) {
  const { text } = useI18n();
  const total = Math.max(modelCallCount + toolCallCount, 1);
  const modelWidth = Math.round((modelCallCount / total) * 100);
  const toolWidth = Math.round((toolCallCount / total) * 100);

  return (
    <Card>
      <CardHeader>
        <div className="inline-flex items-center gap-1.5 text-[11px] tracking-widest text-slate-500">
          <Activity className="h-3 w-3" /> {text("资源使用", "Resource Usage")}
        </div>
      </CardHeader>
      <div className="space-y-3 p-3 text-xs">
        <Bar label={text("模型调用", "Model calls")} value={modelCallCount} width={modelWidth} className="bg-cyan-500" />
        <Bar label={text("工具调用", "Tool calls")} value={toolCallCount} width={toolWidth} className="bg-emerald-500" />
      </div>
    </Card>
  );
}

function Bar({
  label,
  value,
  width,
  className,
}: {
  label: string;
  value: number;
  width: number;
  className: string;
}) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-slate-500">
        <span>{label}</span>
        <span className="font-mono">{value}</span>
      </div>
      <div className="h-2 overflow-hidden rounded bg-slate-100">
        <div className={className} style={{ width: `${Math.max(width, value > 0 ? 8 : 0)}%` }} />
      </div>
    </div>
  );
}
