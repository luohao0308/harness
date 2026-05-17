import { Check } from "lucide-react";

import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { useI18n } from "../../../lib/i18n";
import type { EvalRun, RegressionDelta } from "../../tasks/api";

const metricLabels: Record<string, string> = {
  task_success_rate: "任务成功率",
  grounding_pass_rate: "Grounding 通过率",
  citation_coverage_rate: "引用覆盖率",
  unsupported_marker_rate: "Unsupported 标记率",
  fallback_mismatch_rate: "Fallback 不匹配率",
  forbidden_evidence_leak_rate: "Forbidden 泄漏率",
  required_evidence_miss_rate: "Required evidence 缺失率",
  grounding_failure_total: "Grounding 失败总数",
  tool_selection_accuracy: "工具选择准确率",
  policy_violation_rate: "策略违规率",
  avg_latency_ms: "平均延迟",
  avg_cost_usd: "平均成本",
  retry_rate: "重试率",
  human_escalation_rate: "人工升级率",
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
            {text("最近评测运行", "Latest Eval Run")}
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
              label="任务成功率"
              delta={regressionDelta.task_success_rate_delta}
              isPercentage
            />
            <DeltaMetric
              label="Grounding"
              delta={regressionDelta.grounding_pass_rate_delta}
              isPercentage
            />
            <DeltaMetric
              label="工具准确率"
              delta={regressionDelta.tool_selection_accuracy_delta}
              isPercentage
            />
            <DeltaMetric
              label="Forbidden leak"
              delta={regressionDelta.forbidden_evidence_leak_rate_delta}
              isPercentage
              invertColor
            />
            <DeltaMetric
              label="Unsupported"
              delta={regressionDelta.unsupported_marker_rate_delta}
              isPercentage
              invertColor
            />
            <DeltaMetric
              label="平均延迟"
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
                "回归检测：Eval gate 已触发",
                "Regression detected: Eval gate triggered",
              )}
            </div>
          )}
          {regressionDelta.low_sample_count && (
            <div className="mt-2 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
              {regressionDelta.low_sample_caveat ??
                text("样本数偏低，趋势置信度有限", "Low sample count; trend confidence is limited")}
            </div>
          )}
          {!regressionDelta.is_regression &&
            regressionDelta.task_success_rate_delta > 0 && (
              <div
                data-improvement="true"
                className="mt-2 rounded-md border border-green-200 bg-green-50 p-2 text-xs text-green-700"
              >
                {text("改进：指标有所提升", "Improvement: metrics improved")}
              </div>
            )}
          {regressionDelta.newly_failing_case_ids.length > 0 && (
            <div className="mt-2 text-xs text-red-600">
              {text("新增失败", "Newly failing")}: {regressionDelta.newly_failing_case_ids.length}{" "}
              个用例
            </div>
          )}
          {regressionDelta.newly_passing_case_ids.length > 0 && (
            <div className="mt-1 text-xs text-green-600">
              {text("新增通过", "Newly passing")}: {regressionDelta.newly_passing_case_ids.length}{" "}
              个用例
            </div>
          )}
          {regressionDelta.newly_forbidden_leak_case_ids.length > 0 && (
            <div className="mt-1 text-xs text-red-600">
              Forbidden leak: {regressionDelta.newly_forbidden_leak_case_ids.length} 个用例
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
            <Th>{text("结果", "Result")}</Th>
            <Th>{text("状态", "Status")}</Th>
            <Th>{text("任务", "Task")}</Th>
            <Th>{text("分数", "Score")}</Th>
            <Th>{text("Trace 评分器", "Trace Grader")}</Th>
            <Th>{text("Grounding", "Grounding")}</Th>
          </tr>
        </thead>
        <tbody>
          {(latestRun?.results ?? []).map((result) => {
            const failures = stringList(result.grader_trace_json.grounding_failures);
            const leakSources = stringList(result.grader_trace_json.forbidden_leak_sources);
            return (
              <tr key={result.id} className="border-t border-slate-100">
                <Td className="font-mono text-slate-500">{result.id.slice(0, 8)}</Td>
                <Td>
                  <Badge>{result.status}</Badge>
                </Td>
                <Td className="font-mono text-slate-600">
                  {result.task_id?.slice(0, 8) ?? "手动录入"}
                </Td>
                <Td className="font-mono text-slate-900">
                  {result.scores_json.task_success ?? 0}
                </Td>
                <Td className="text-slate-600">
                  {String(result.grader_trace_json.grader ?? "未知评分器")}
                </Td>
                <Td className="max-w-xs text-slate-600">
                  <div className="flex flex-wrap gap-1">
                    <Badge
                      tone={result.grader_trace_json.passed === false ? "failed" : "success"}
                    >
                      {result.grader_trace_json.passed === false ? "failed" : "passed"}
                    </Badge>
                    {result.grader_trace_json.forbidden_evidence_leaked === true && (
                      <Badge tone="failed">forbidden leak</Badge>
                    )}
                    {leakSources.map((source) => (
                      <Badge key={source} tone="warning">
                        {source}
                      </Badge>
                    ))}
                  </div>
                  {failures.length > 0 && (
                    <div className="mt-1 truncate font-mono text-[11px] text-slate-500">
                      {failures.join(", ")}
                    </div>
                  )}
                </Td>
              </tr>
            );
          })}
        </tbody>
      </Table>
    </Card>
  );
}

function stringList(value: unknown) {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
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
