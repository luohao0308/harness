import { GitBranch } from "lucide-react";

import { Badge, statusTone } from "../../../components/ui/badge";
import { Card, CardHeader } from "../../../components/ui/card";
import { statusLabel } from "../../../lib/labels";

const subagents = [
  ["subagent-1", "依赖审查", "PENDING"],
  ["subagent-2", "测试分析", "PENDING"],
  ["subagent-3", "日志检查", "PENDING"],
];

export function SubagentPanel() {
  return (
    <Card>
      <CardHeader>
        <div className="inline-flex items-center gap-1.5 text-[11px] tracking-widest text-slate-500">
          <GitBranch className="h-3 w-3" /> 子 Agent
        </div>
        <span className="font-mono text-[10px] text-slate-400">0 / 5</span>
      </CardHeader>
      <div className="space-y-1.5 p-2">
        {subagents.map(([id, label, status]) => (
          <div
            key={id}
            className="flex items-center justify-between rounded-md border border-slate-100 px-2 py-1.5"
          >
            <div>
              <div className="font-mono text-xs text-slate-800">{id}</div>
              <div className="text-[10px] text-slate-500">{label}</div>
            </div>
            <Badge tone={statusTone(status)}>{statusLabel(status)}</Badge>
          </div>
        ))}
      </div>
    </Card>
  );
}
