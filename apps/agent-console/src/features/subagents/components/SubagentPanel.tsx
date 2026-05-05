import { GitBranch } from "lucide-react";

import { Badge, statusTone } from "../../../components/ui/badge";
import { Card, CardHeader } from "../../../components/ui/card";
import { statusLabel } from "../../../lib/labels";
import type { Subagent } from "../../tasks/api";

function subagentLabel(subagent: Subagent) {
  const label = subagent.context_json.label;
  const goal = subagent.context_json.goal;
  if (typeof label === "string" && label.length > 0) return label;
  if (typeof goal === "string" && goal.length > 0) return goal;
  return "子任务执行";
}

export function SubagentPanel({
  subagents = [],
  maxSubagents = 5,
  loading = false,
}: {
  subagents?: Subagent[];
  maxSubagents?: number;
  loading?: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="inline-flex items-center gap-1.5 text-[11px] tracking-widest text-slate-500">
          <GitBranch className="h-3 w-3" /> 子 Agent
        </div>
        <span className="font-mono text-[10px] text-slate-400">
          {subagents.length} / {maxSubagents}
        </span>
      </CardHeader>
      <div className="space-y-1.5 p-2">
        {loading && <div className="px-2 py-4 text-xs text-slate-500">子 Agent 加载中...</div>}
        {!loading && subagents.length === 0 && (
          <div className="px-2 py-4 text-xs text-slate-500">
            当前任务尚未派生子 Agent。长耗时任务会在这里显示并发状态。
          </div>
        )}
        {subagents.map((subagent) => (
          <div
            key={subagent.id}
            className="flex items-center justify-between rounded-md border border-slate-100 px-2 py-1.5"
          >
            <div>
              <div className="font-mono text-xs text-slate-800">{subagent.id.slice(0, 8)}</div>
              <div className="text-[10px] text-slate-500">{subagentLabel(subagent)}</div>
            </div>
            <Badge tone={statusTone(subagent.status)}>{statusLabel(subagent.status)}</Badge>
          </div>
        ))}
      </div>
    </Card>
  );
}
