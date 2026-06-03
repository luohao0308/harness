import { Check } from "lucide-react";
import type { ReactNode } from "react";

import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { TermHint } from "../../../components/ui/term";
import { useI18n } from "../../../lib/i18n";
import { statusLabel } from "../../../lib/labels";
import type { EvalRun, RegressionDelta } from "../../tasks/api";

const metricLabels: Record<string, string> = {
  task_success_rate: "任务成功率",
  grounding_pass_rate: "依据校验通过率",
  citation_coverage_rate: "引用覆盖率",
  unsupported_marker_rate: "不支持标记率",
  fallback_mismatch_rate: "后备路径不匹配率",
  forbidden_evidence_leak_rate: "禁止证据泄漏率",
  required_evidence_miss_rate: "必需证据缺失率",
  grounding_failure_total: "依据校验失败总数",
  tool_selection_accuracy: "工具选择准确率",
  policy_violation_rate: "策略违规率",
  avg_latency_ms: "平均延迟",
  avg_cost_usd: "平均成本（USD）",
  total_cost_usd: "累计成本（USD）",
  total_prompt_tokens: "累计 Prompt Tokens",
  total_completion_tokens: "累计 Completion Tokens",
  cost_per_passed_case_usd: "单次通过成本",
  tool_contract_pass_rate: "工具契约通过率",
  dialogue_contract_pass_rate: "对话契约通过率",
  cost_contract_pass_rate: "成本契约通过率",
  refusal_contract_pass_rate: "拒答契约通过率",
  overrefusal_rate: "过度拒答率",
  safety_contract_pass_rate: "安全契约通过率",
  safety_violation_total: "安全命中总数",
  persona_contract_pass_rate: "人设契约通过率",
  role_drift_total: "角色漂移总数",
  retry_rate: "重试率",
  human_escalation_rate: "人工升级率",
};

const tokenMetricKeys = new Set(["total_prompt_tokens", "total_completion_tokens"]);
const countMetricKeys = new Set(["safety_violation_total", "role_drift_total"]);
const costMetricKeys = new Set(["avg_cost_usd", "total_cost_usd", "cost_per_passed_case_usd"]);
const rateMetricKeys = new Set([
  "task_success_rate",
  "grounding_pass_rate",
  "citation_coverage_rate",
  "unsupported_marker_rate",
  "fallback_mismatch_rate",
  "forbidden_evidence_leak_rate",
  "required_evidence_miss_rate",
  "tool_selection_accuracy",
  "policy_violation_rate",
  "tool_contract_pass_rate",
  "dialogue_contract_pass_rate",
  "cost_contract_pass_rate",
  "refusal_contract_pass_rate",
  "overrefusal_rate",
  "safety_contract_pass_rate",
  "persona_contract_pass_rate",
  "retry_rate",
  "human_escalation_rate",
]);

function formatMetricValue(key: string, value: unknown): string {
  if (key === "avg_latency_ms") {
    return `${Number(value ?? 0)}ms`;
  }
  if (costMetricKeys.has(key)) {
    return `$${value ?? "0"}`;
  }
  if (tokenMetricKeys.has(key)) {
    return Number(value ?? 0).toLocaleString();
  }
  if (countMetricKeys.has(key)) {
    return Number(value ?? 0).toLocaleString();
  }
  if (rateMetricKeys.has(key)) {
    const num = Number(value ?? 0);
    return `${(num * 100).toFixed(1)}%`;
  }
  return String(value ?? "");
}

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
          {latestRun && (
            <Badge tone={statusTone(latestRun.status)}>{statusLabel(latestRun.status)}</Badge>
          )}
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
              label={<TermHint description="依据校验通过率">依据校验</TermHint>}
              delta={regressionDelta.grounding_pass_rate_delta}
              isPercentage
            />
            <DeltaMetric
              label="工具准确率"
              delta={regressionDelta.tool_selection_accuracy_delta}
              isPercentage
            />
            <DeltaMetric
              label={<TermHint description="禁止证据泄漏率">禁止证据泄漏</TermHint>}
              delta={regressionDelta.forbidden_evidence_leak_rate_delta}
              isPercentage
              invertColor
            />
            <DeltaMetric
              label={<TermHint description="不支持标记率">不支持标记</TermHint>}
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
            <DeltaMetric
              label="工具契约"
              delta={regressionDelta.tool_contract_pass_rate_delta ?? 0}
              isPercentage
            />
            <DeltaMetric
              label="对话契约"
              delta={regressionDelta.dialogue_contract_pass_rate_delta ?? 0}
              isPercentage
            />
            <DeltaMetric
              label="成本契约"
              delta={regressionDelta.cost_contract_pass_rate_delta ?? 0}
              isPercentage
            />
            <DeltaMetric
              label="拒答契约"
              delta={regressionDelta.refusal_contract_pass_rate_delta ?? 0}
              isPercentage
            />
            <DeltaMetric
              label="安全契约"
              delta={regressionDelta.safety_contract_pass_rate_delta ?? 0}
              isPercentage
            />
            <DeltaMetric
              label="人设契约"
              delta={regressionDelta.persona_contract_pass_rate_delta ?? 0}
              isPercentage
            />
            <DeltaMetric
              label="过度拒答"
              delta={regressionDelta.overrefusal_rate_delta ?? 0}
              isPercentage
              invertColor
            />
            <DeltaMetric
              label="安全命中"
              delta={regressionDelta.safety_violation_total_delta ?? 0}
              invertColor
            />
            <DeltaMetric
              label="角色漂移"
              delta={regressionDelta.role_drift_total_delta ?? 0}
              invertColor
            />
            <DeltaMetric
              label="平均成本 USD"
              delta={Number(regressionDelta.avg_cost_usd_delta ?? "0")}
              suffix="$"
              invertColor
            />
          </div>
          {regressionDelta.is_regression && (
            <div
              data-regression="true"
              className="mt-2 rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-700"
            >
              {text(
                "回归检测：评测门禁已触发",
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
              禁止证据泄漏: {regressionDelta.newly_forbidden_leak_case_ids.length} 个用例
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
              {formatMetricValue(key, value)}
            </div>
          </div>
        ))}
        {!latestRun && (
          <div className="col-span-4 py-8 text-center text-xs text-slate-500">
            {text("运行一次评测后这里会显示指标", "Metrics appear after an eval run")}
          </div>
        )}
      </div>

      {/* Contract failure breakdown */}
      {latestRun && <ContractBreakdown metrics={metrics} />}

      {/* Per-case results */}
      <Table>
        <thead className="bg-slate-50 text-slate-500">
          <tr>
            <Th>{text("结果", "Result")}</Th>
            <Th>{text("状态", "Status")}</Th>
            <Th>{text("任务", "Task")}</Th>
            <Th>{text("分数", "Score")}</Th>
            <Th>
              <TermHint description="链路评分器">轨迹评分器</TermHint>
            </Th>
            <Th>
              <TermHint description="依据校验结果">依据校验</TermHint>
            </Th>
            <Th>{text("契约", "Contracts")}</Th>
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
                  <Badge tone={statusTone(result.status)}>{statusLabel(result.status)}</Badge>
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
                      {result.grader_trace_json.passed === false ? "失败" : "通过"}
                    </Badge>
                    {result.grader_trace_json.forbidden_evidence_leaked === true && (
                      <Badge tone="failed">禁止证据泄漏</Badge>
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
                <Td className="max-w-xs text-slate-600">
                  <ContractCell result={result} />
                </Td>
              </tr>
            );
          })}
        </tbody>
      </Table>
    </Card>
  );
}

type ContractTrace = {
  configured?: boolean;
  passed?: boolean;
  failures?: unknown;
  limit_exceeded?: unknown;
  actual_cost_usd?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  violation_total?: number;
  outcome?: string;
  role_drift_count?: number;
};

function readContract(trace: Record<string, unknown>, key: string): ContractTrace | null {
  const value = trace?.[key];
  if (!value || typeof value !== "object") return null;
  return value as ContractTrace;
}

function ContractCell({
  result,
}: {
  result: { grader_trace_json: Record<string, unknown> };
}) {
  const tool = readContract(result.grader_trace_json, "tool_contract");
  const dialogue = readContract(result.grader_trace_json, "dialogue_contract");
  const cost = readContract(result.grader_trace_json, "cost_contract");
  const refusal = readContract(result.grader_trace_json, "refusal_contract");
  const safety = readContract(result.grader_trace_json, "safety_contract");
  const persona = readContract(result.grader_trace_json, "persona_contract");
  const renderBadge = (label: string, trace: ContractTrace | null) => {
    if (!trace || trace.configured !== true) {
      return (
        <Badge key={label} tone="neutral">
          {label} 未配置
        </Badge>
      );
    }
    return (
      <Badge key={label} tone={trace.passed ? "success" : "failed"}>
        {label} {trace.passed ? "通过" : "失败"}
      </Badge>
    );
  };
  const allFailures: string[] = [];
  if (tool && tool.configured === true && !tool.passed) {
    allFailures.push(...stringList(tool.failures).map((f) => `工具:${f}`));
  }
  if (dialogue && dialogue.configured === true && !dialogue.passed) {
    allFailures.push(...stringList(dialogue.failures).map((f) => `对话:${f}`));
  }
  if (cost && cost.configured === true && !cost.passed) {
    allFailures.push(...stringList(cost.failures).map((f) => `成本:${f}`));
  }
  if (refusal && refusal.configured === true && !refusal.passed) {
    allFailures.push(...stringList(refusal.failures).map((f) => `拒答:${f}`));
  }
  if (safety && safety.configured === true && !safety.passed) {
    allFailures.push(...stringList(safety.failures).map((f) => `安全:${f}`));
  }
  if (persona && persona.configured === true && !persona.passed) {
    allFailures.push(...stringList(persona.failures).map((f) => `人设:${f}`));
  }
  return (
    <div>
      <div className="flex flex-wrap gap-1">
        {renderBadge("工具", tool)}
        {renderBadge("对话", dialogue)}
        {renderBadge("成本", cost)}
        {renderBadge("拒答", refusal)}
        {renderBadge("安全", safety)}
        {renderBadge("人设", persona)}
      </div>
      {cost && cost.configured === true && (
        <div className="mt-1 font-mono text-[11px] text-slate-500">
          ${cost.actual_cost_usd ?? "0"} · {cost.prompt_tokens ?? 0}/
          {cost.completion_tokens ?? 0} tok
        </div>
      )}
      {(refusal?.configured === true ||
        safety?.configured === true ||
        persona?.configured === true) && (
        <div className="mt-1 font-mono text-[11px] text-slate-500">
          拒答:{refusal?.outcome ?? "-"} · 安全:{safety?.violation_total ?? 0} · 漂移:
          {persona?.role_drift_count ?? 0}
        </div>
      )}
      {allFailures.length > 0 && (
        <div className="mt-1 truncate font-mono text-[11px] text-slate-500">
          {allFailures.slice(0, 4).join(", ")}
          {allFailures.length > 4 && ` … +${allFailures.length - 4}`}
        </div>
      )}
    </div>
  );
}

function ContractBreakdown({ metrics }: { metrics: Record<string, unknown> }) {
  const toolBreakdown = metrics["tool_contract_failure_breakdown"];
  const costBreakdown = metrics["cost_contract_failure_breakdown"];
  const dialogueBreakdown = metrics["dialogue_contract_failure_breakdown"];
  const refusalBreakdown = metrics["refusal_contract_failure_breakdown"];
  const safetyBreakdown = metrics["safety_violation_breakdown"];
  const personaBreakdown = metrics["persona_contract_failure_breakdown"];
  const toolConfigured = Number(metrics["tool_contract_configured_count"] ?? 0);
  const dialogueConfigured = Number(metrics["dialogue_contract_configured_count"] ?? 0);
  const costConfigured = Number(metrics["cost_contract_configured_count"] ?? 0);
  const refusalConfigured = Number(metrics["refusal_contract_configured_count"] ?? 0);
  const safetyConfigured = Number(metrics["safety_contract_configured_count"] ?? 0);
  const personaConfigured = Number(metrics["persona_contract_configured_count"] ?? 0);
  if (
    toolConfigured +
      dialogueConfigured +
      costConfigured +
      refusalConfigured +
      safetyConfigured +
      personaConfigured ===
    0
  ) {
    return null;
  }
  return (
    <div className="grid grid-cols-3 gap-3 border-b border-slate-100 p-3 text-xs">
      <BreakdownColumn
        title={`工具契约 (${toolConfigured})`}
        breakdown={toolBreakdown}
        emptyHint="无失败项"
      />
      <BreakdownColumn
        title={`对话契约 (${dialogueConfigured})`}
        breakdown={dialogueBreakdown}
        emptyHint="无失败项"
      />
      <BreakdownColumn
        title={`成本契约 (${costConfigured})`}
        breakdown={costBreakdown}
        emptyHint="未超限"
      />
      <BreakdownColumn
        title={`拒答契约 (${refusalConfigured})`}
        breakdown={refusalBreakdown}
        emptyHint="无失败项"
      />
      <BreakdownColumn
        title={`安全命中 (${safetyConfigured})`}
        breakdown={safetyBreakdown}
        emptyHint="未命中"
      />
      <BreakdownColumn
        title={`人设契约 (${personaConfigured})`}
        breakdown={personaBreakdown}
        emptyHint="无失败项"
      />
    </div>
  );
}

function BreakdownColumn({
  title,
  breakdown,
  emptyHint,
}: {
  title: string;
  breakdown: unknown;
  emptyHint: string;
}) {
  const entries =
    breakdown && typeof breakdown === "object"
      ? Object.entries(breakdown as Record<string, unknown>)
      : [];
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-2">
      <div className="text-[10px] uppercase text-slate-500">{title}</div>
      {entries.length === 0 ? (
        <div className="mt-1 text-slate-400">{emptyHint}</div>
      ) : (
        <ul className="mt-1 space-y-0.5 font-mono text-[11px]">
          {entries.map(([key, value]) => (
            <li key={key}>
              <span className="text-slate-700">{key}</span>
              <span className="text-slate-500"> × {String(value)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
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
  label: ReactNode;
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
