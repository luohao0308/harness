import { GitBranch, RotateCcw } from "lucide-react";
import { Link } from "react-router-dom";

import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { useI18n } from "../../../lib/i18n";
import { statusLabel } from "../../../lib/labels";
import { formatShortDate } from "../../../lib/utils";
import type { Subagent, SubagentRecoveryBatch, SubagentRecoveryResponse } from "../../tasks/api";

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
  recoveryBatch,
  recoveryBatches = [],
  onRecover,
}: {
  subagents?: Subagent[];
  maxSubagents?: number;
  loading?: boolean;
  recovering?: boolean;
  recoveryBatch?: SubagentRecoveryResponse;
  recoveryBatches?: SubagentRecoveryBatch[];
  onRecover?: () => void;
}) {
  const { text } = useI18n();
  return (
    <Card>
      <CardHeader>
        <div className="inline-flex items-center gap-1.5 text-[11px] tracking-widest text-slate-500">
          <GitBranch className="h-3 w-3" /> {text("子代理", "Subagents")}
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
              <RotateCcw className="h-3 w-3" /> {text("恢复", "Recover")}
            </Button>
          )}
        </div>
      </CardHeader>
      {recoveryBatch && (
        <div className="border-b border-slate-100 px-3 py-2 text-[10px] text-slate-500">
          <div className="flex items-center justify-between gap-2">
            <span className="font-semibold text-slate-700">{text("最近恢复批次", "Latest Recovery Batch")}</span>
            <span className="font-mono text-slate-400">{recoveryBatch.batch_id.slice(0, 13)}</span>
          </div>
          <div className="mt-1 flex flex-wrap gap-x-2 gap-y-1">
            <span>{recoveryBatch.trigger === "auto" ? text("自动巡检", "Auto scan") : text("手动触发", "Manual trigger")}</span>
            <span>{text(`扫描 ${recoveryBatch.scanned_count}`, `Scanned ${recoveryBatch.scanned_count}`)}</span>
            <span>{text(`恢复 ${recoveryBatch.recovered_count}`, `Recovered ${recoveryBatch.recovered_count}`)}</span>
            <span>重放 {recoveryBatch.replay_sequence}</span>
            <span>{text(`卡住阈值 ${recoveryBatch.stale_after_seconds}s`, `Stale threshold ${recoveryBatch.stale_after_seconds}s`)}</span>
            <span>{formatShortDate(recoveryBatch.completed_at)}</span>
          </div>
          {recoveryBatch.recovered.length > 0 && (
            <div className="mt-1 space-y-0.5">
              {recoveryBatch.recovered.slice(0, 3).map((item) => (
                <div key={item.id} className="truncate">
                  <span className="font-mono text-slate-600">{item.id.slice(0, 8)}</span>
                  <span className="ml-1">{item.previous_status}</span>
                  <span className="mx-1">→</span>
                  <span>{statusLabel(item.status)}</span>
                  <span className="ml-1 text-slate-400">{item.action}</span>
                </div>
              ))}
            </div>
          )}
          {recoveryBatch.recovered.length === 0 && (
            <div className="mt-1 text-slate-400">{text("本批次没有需要恢复的子代理。", "No subagents needed recovery in this batch.")}</div>
          )}
        </div>
      )}
      {recoveryBatches.length > 1 && (
        <div className="border-b border-slate-100 px-3 py-2 text-[10px] text-slate-500">
          <div className="mb-1 font-semibold text-slate-700">{text("恢复批次历史", "Recovery Batch History")}</div>
          <div className="space-y-0.5">
            {recoveryBatches.slice(0, 3).map((batch) => (
              <div key={batch.batch_id} className="flex items-center justify-between gap-2">
                <span className="min-w-0 truncate">
                  {batch.trigger === "auto" ? text("自动巡检", "Auto scan") : text("手动触发", "Manual trigger")} ·{" "}
                  {text(`扫描 ${batch.scanned_count}`, `Scanned ${batch.scanned_count}`)} ·{" "}
                  {text(`恢复 ${batch.recovered_count}`, `Recovered ${batch.recovered_count}`)}
                </span>
                <span className="shrink-0 font-mono text-slate-400">
                  {formatShortDate(batch.completed_at)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="space-y-1.5 p-2">
        {loading && <div className="px-2 py-4 text-xs text-slate-500">{text("子代理加载中...", "Loading subagents...")}</div>}
        {!loading && subagents.length === 0 && (
          <div className="px-2 py-4 text-xs text-slate-500">
            {text(
              "当前任务尚未派生子代理。长耗时任务会在这里显示并发状态。",
              "This task has not spawned subagents yet. Long-running tasks show concurrency state here.",
            )}
          </div>
        )}
        {subagents.map((subagent) => (
          <div
            key={subagent.id}
            className="rounded-md border border-slate-100 px-2 py-1.5"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <Link
                  to={`/subagents/${subagent.id}`}
                  className="font-mono text-xs text-slate-800 hover:text-slate-950"
                >
                  {subagent.id.slice(0, 8)}
                </Link>
                <div className="truncate text-[10px] text-slate-500">{subagentLabel(subagent)}</div>
              </div>
              <Badge tone={statusTone(subagent.status)}>{statusLabel(subagent.status)}</Badge>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-1 text-[10px] text-slate-500">
              {subagentStepKey(subagent) && (
                <>
                  <span>{text("来源步骤", "Source step")}</span>
                  <span className="font-mono text-slate-700">{subagentStepKey(subagent)}</span>
                </>
              )}
              {subagent.started_at && <span>{text("已启动", "Started")}</span>}
              {subagent.timeout_at && <span>{text("超时保护已设置", "Timeout guard set")}</span>}
              {subagentToolCount(subagent) > 0 && (
                <span>{text(`工具 ${subagentToolCount(subagent)}`, `Tools ${subagentToolCount(subagent)}`)}</span>
              )}
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
