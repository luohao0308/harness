import { GitBranch, RotateCcw } from "lucide-react";

import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { statusLabel } from "../../../lib/labels";
import type { Subagent } from "../../tasks/api";

function subagentLabel(subagent: Subagent) {
  const label = subagent.context_json.label;
  const goal = subagent.context_json.goal;
  const description = subagent.context_json.description;
  if (typeof label === "string" && label.length > 0) return label;
  if (typeof goal === "string" && goal.length > 0) return goal;
  if (typeof description === "string" && description.length > 0) return description;
  return "子任务执行";
}

function subagentStepKey(subagent: Subagent) {
  const stepKey = subagent.context_json.step_key;
  return typeof stepKey === "string" && stepKey.length > 0 ? stepKey : null;
}

function subagentResultSummary(subagent: Subagent) {
  const result = subagent.context_json.result;
  if (!result || typeof result !== "object" || Array.isArray(result)) return null;
  const summary = (result as Record<string, unknown>).summary;
  return typeof summary === "string" && summary.length > 0 ? summary : null;
}

function subagentToolCount(subagent: Subagent) {
  const result = subagent.context_json.result;
  if (!result || typeof result !== "object" || Array.isArray(result)) return 0;
  const tools = (result as Record<string, unknown>).tool_results;
  return Array.isArray(tools) ? tools.length : 0;
}

export function SubagentPanel({
  subagents = [],
  maxSubagents = 5,
  loading = false,
  recovering = false,
  onRecover,
}: {
  subagents?: Subagent[];
  maxSubagents?: number;
  loading?: boolean;
  recovering?: boolean;
  onRecover?: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="inline-flex items-center gap-1.5 text-[11px] tracking-widest text-slate-500">
          <GitBranch className="h-3 w-3" /> 子 Agent
        </div>
        <div className="flex items-center gap-1">
          <span className="font-mono text-[10px] text-slate-400">
            {subagents.length} / {maxSubagents}
          </span>
          {onRecover && (
            <Button
              className="h-6 px-2 text-[10px]"
              disabled={recovering}
              onClick={onRecover}
              variant="ghost"
            >
              <RotateCcw className="h-3 w-3" /> 恢复
            </Button>
          )}
        </div>
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
            className="rounded-md border border-slate-100 px-2 py-1.5"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="font-mono text-xs text-slate-800">{subagent.id.slice(0, 8)}</div>
                <div className="truncate text-[10px] text-slate-500">{subagentLabel(subagent)}</div>
              </div>
              <Badge tone={statusTone(subagent.status)}>{statusLabel(subagent.status)}</Badge>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-1 text-[10px] text-slate-500">
              {subagentStepKey(subagent) && (
                <>
                  <span>来源步骤</span>
                  <span className="font-mono text-slate-700">{subagentStepKey(subagent)}</span>
                </>
              )}
              {subagent.started_at && <span>已启动</span>}
              {subagent.timeout_at && <span>超时保护已设置</span>}
              {subagentToolCount(subagent) > 0 && <span>工具 {subagentToolCount(subagent)}</span>}
            </div>
            {subagentResultSummary(subagent) && (
              <div className="mt-1 line-clamp-2 text-[10px] text-slate-500">
                {subagentResultSummary(subagent)}
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}
