import { Check } from "lucide-react";

import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { useI18n } from "../../../lib/i18n";
import type { EvalRun, RegressionDelta } from "../../tasks/api";

const metricLabels: Record<string, string> = {
  task_success_rate: "Task Success",
  tool_selection_accuracy: "Tool Accuracy",
  policy_violation_rate: "Policy Violation",
  avg_latency_ms: "Avg Latency",
  avg_cost_usd: "Avg Cost",
  retry_rate: "Retry Rate",
  human_escalation_rate: "Human Escalation",
};

interface EvalRunResultsProps {
  latestRun: EvalRun | null;
  regressionDelta: RegressionDelta | null;
  activeDatasetId: string | null;
  hasBaseline: boolean;
  onSetBaseline: (evalRunId: string) => void;
}

export function EvalRunResults({
  latestRun,
  regressionDelta,
  activeDatasetId,
  hasBaseline,
  onSetBaseline,
}: EvalRunResultsProps) {
  const { text } = useI18n();
  const metrics = latestRun?.metrics_json ?? {};
  const metricEntries = Object.entries(metrics).filter(([key]) => key in metricLabels);

  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <div className="flex items-center gap-2">
          <div className="text-sm font-semibold text-slate-900">
            {text("最近 Eval Run", "Latest Eval Run")}
          </div>
          {latestRun && <Badge>{latestRun.status}</Badge>}
        </div>
        <div className="flex items-center gap-2">
          {latestRun && latestRun.status === "COMPLETED" && (
            <Button
              onClick={() => onSetBaseline(latestRun.id)}
              className="gap-1.5"
            >
              <Check className="h-3.5 w-3.5" />
              {text("设为基线", "Set as Baseline")}
            </Button>
          )}
        </div>
      </CardHeader>

      {/* Regression Delta Display */}
      {regressionDelta && (
        <div className="border-b border-slate-100 p-3">
          <div className="mb-2 text-xs font-semibold text-slate-700">
            {text("回归对比", "Regression Delta")}
          </div>
          <div className="grid grid-cols-3 gap-2">
            <DeltaMetric
              label="Task Success"
              delta={regressionDelta.task_success_rate_delta}
              isPercentage
            />
            <DeltaMetric
              label="Tool Accuracy"
              delta={regressionDelta.tool_selection_accuracy_delta}
              isPercentage
            />
            <DeltaMetric
              label="Avg Latency"
              delta={regressionDelta.avg_latency_ms_delta}
              suffix="ms"
              invertColor
            />
          </div>
          {regressionDelta.is_regression && (
            <div
              data-regression="true"
              className="mt-2 rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-700"
            >
              {text(
                "⚠️ 回归检测：task_success_rate 下降超过 10 个百分点",
                "⚠️ Regression detected: task_success_rate dropped > 10pp",
              )}
            </div>
          )}
          {!regressionDelta.is_regression &&
            regressionDelta.task_success_rate_delta > 0 && (
              <div
                data-improvement="true"
                className="mt-2 rounded-md border border-green-200 bg-green-50 p-2 text-xs text-green-700"
              >
                {text("✓ 改进：指标有所提升", "✓ Improvement: metrics improved")}
              </div>
            )}
          {regressionDelta.newly_failing_case_ids.length > 0 && (
            <div className="mt-2 text-xs text-red-600">
              {text("新增失败", "Newly failing")}: {regressionDelta.newly_failing_case_ids.length}{" "}
              cases
            </div>
          )}
          {regressionDelta.newly_passing_case_ids.length > 0 && (
            <div className="mt-1 text-xs text-green-600">
              {text("新增通过", "Newly passing")}: {regressionDelta.newly_passing_case_ids.length}{" "}
              cases
            </div>
          )}
        </div>
      )}

      {/* No baseline message */}
      {!regressionDelta && latestRun && !hasBaseline && (
        <div className="border-b border-slate-100 p-3 text-center text-xs text-slate-500">
          {text("未设置基线，无法显示回归对比", "No baseline set")}
        </div>
      )}

      {/* Metrics Grid */}
      <div className="grid grid-cols-4 gap-3 border-b border-slate-100 p-3">
        {metricEntries.map(([key, value]) => (
          <div key={key} className="rounded-md border border-slate-200 bg-slate-50 p-3">
            <div className="text-[10px] uppercase text-slate-500">{metricLabels[key]}</div>
            <div className="mt-1 font-mono text-lg text-slate-900">
              {key.includes("latency") ? `${value}ms` : value}
            </div>
          </div>
        ))}
        {!latestRun && (
          <div className="col-span-4 py-8 text-center text-xs text-slate-500">
            {text("运行一次评测后这里会显示指标", "Metrics appear after an eval run")}
          </div>
        )}
      </div>

      {/* Per-case results */}
      <Table>
        <thead className="bg-slate-50 text-slate-500">
          <tr>
            <Th>Result</Th>
            <Th>Status</Th>
            <Th>Task</Th>
            <Th>Score</Th>
            <Th>Trace Grader</Th>
          </tr>
        </thead>
        <tbody>
          {(latestRun?.results ?? []).map((result) => (
            <tr key={result.id} className="border-t border-slate-100">
              <Td className="font-mono text-slate-500">{result.id.slice(0, 8)}</Td>
              <Td>
                <Badge>{result.status}</Badge>
              </Td>
              <Td className="font-mono text-slate-600">
                {result.task_id?.slice(0, 8) ?? "manual"}
              </Td>
              <Td className="font-mono text-slate-900">
                {result.scores_json.task_success ?? 0}
              </Td>
              <Td className="text-slate-600">
                {String(result.grader_trace_json.grader ?? "unknown")}
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  );
}

function DeltaMetric({
  label,
  delta,
  isPercentage = false,
  suffix = "",
  invertColor = false,
}: {
  label: string;
  delta: number;
  isPercentage?: boolean;
  suffix?: string;
  invertColor?: boolean;
}) {
  const isPositive = invertColor ? delta < 0 : delta > 0;
  const isNegative = invertColor ? delta > 0 : delta < 0;
  const colorClass = isPositive
    ? "text-green-700"
    : isNegative
      ? "text-red-700"
      : "text-slate-700";
  const sign = delta > 0 ? "+" : "";
  const displayValue = isPercentage
    ? `${sign}${(delta * 100).toFixed(1)}pp`
    : `${sign}${delta}${suffix}`;

  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-2">
      <div className="text-[10px] uppercase text-slate-500">{label}</div>
      <div className={`mt-1 font-mono text-sm ${colorClass}`}>{displayValue}</div>
    </div>
  );
}
