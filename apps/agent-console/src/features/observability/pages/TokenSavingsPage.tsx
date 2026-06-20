import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, Database, Filter, History, Route, Sparkles, Zap } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { MenuSelect, type MenuSelectOption } from "../../../components/ui/menu-select";
import { Table, Td, Th } from "../../../components/ui/table";
import { useI18n } from "../../../lib/i18n";
import { statusLabel } from "../../../lib/labels";
import { cn, formatShortDate } from "../../../lib/utils";
import {
  getTokenSavings,
  type CacheSourceSummary,
  type TokenSavingsRunItem,
  type TokenSavingsSummary,
} from "../../tasks/api";

type TimeRange = "all" | "24h" | "7d" | "30d";

const ALL_FILTER = "__all__";
const EMPTY_AGENT = "__empty_agent__";

export function TokenSavingsPage() {
  const { text } = useI18n();
  const [timeRange, setTimeRange] = useState<TimeRange>("all");
  const [modelFilter, setModelFilter] = useState(ALL_FILTER);
  const [agentFilter, setAgentFilter] = useState(ALL_FILTER);
  const tokenSavings = useQuery({
    queryKey: ["observability", "token-savings"],
    queryFn: () => getTokenSavings(50),
  });
  const runs = tokenSavings.data?.runs ?? [];
  const generatedAt = tokenSavings.data?.generated_at ?? null;
  const modelOptions = useMemo(() => uniqueSorted(runs.flatMap((run) => modelNamesForRun(run))), [runs]);
  const agentOptions = useMemo(
    () =>
      uniqueSorted(
        runs.map((run) => (run.agent_id?.trim() ? run.agent_id : EMPTY_AGENT)),
      ),
    [runs],
  );
  const timeRangeOptions = useMemo<MenuSelectOption[]>(
    () => [
      { value: "all", label: text("全部时间", "All time") },
      { value: "24h", label: text("最近 24 小时", "Last 24 hours") },
      { value: "7d", label: text("最近 7 天", "Last 7 days") },
      { value: "30d", label: text("最近 30 天", "Last 30 days") },
    ],
    [text],
  );
  const modelMenuOptions = useMemo<MenuSelectOption[]>(
    () => [
      { value: ALL_FILTER, label: text("全部模型", "All models") },
      ...modelOptions.map((model) => ({ value: model, label: model })),
    ],
    [modelOptions, text],
  );
  const agentMenuOptions = useMemo<MenuSelectOption[]>(
    () => [
      { value: ALL_FILTER, label: text("全部 Agent", "All agents") },
      ...agentOptions.map((agent) => ({
        value: agent,
        label: agent === EMPTY_AGENT ? text("未绑定 Agent", "No agent") : agent,
      })),
    ],
    [agentOptions, text],
  );
  const filteredRuns = useMemo(
    () =>
      runs.filter((run) => {
        if (!matchesTimeRange(run, timeRange, generatedAt)) return false;
        if (modelFilter !== ALL_FILTER && !modelNamesForRun(run).includes(modelFilter)) return false;
        if (agentFilter !== ALL_FILTER) {
          const value = run.agent_id?.trim() ? run.agent_id : EMPTY_AGENT;
          if (value !== agentFilter) return false;
        }
        return true;
      }),
    [agentFilter, generatedAt, modelFilter, runs, timeRange],
  );
  const filtersActive = timeRange !== "all" || modelFilter !== ALL_FILTER || agentFilter !== ALL_FILTER;
  const visibleSummary = useMemo(
    () =>
      filtersActive
        ? summarizeRuns(filteredRuns)
        : summaryFromApi(tokenSavings.data?.summary),
    [filteredRuns, filtersActive, tokenSavings.data?.summary],
  );
  const activePlans = useMemo(
    () =>
      filtersActive
        ? uniqueSorted(filteredRuns.flatMap((run) => run.optimizer_labels))
        : uniqueSorted(tokenSavings.data?.summary.optimizer_labels ?? []),
    [filteredRuns, filtersActive, tokenSavings.data?.summary.optimizer_labels],
  );

  return (
    <ConsoleShell title={text("Token 节省", "Token Savings")}>
      <div className="space-y-4 bg-slate-50/70 p-4">
        <Card className="overflow-visible border-slate-200 shadow-sm">
          <CardHeader className="flex-col items-start gap-2 sm:flex-row sm:items-center">
            <div className="min-w-0">
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <History className="h-4 w-4" />
                {text("Token 节省明细", "Token Savings Details")}
              </div>
              <div className="mt-1 text-[11px] text-slate-500">
                {text("按运行维度查看上下文裁剪、缓存命中、模型路由和实际 Prompt 消耗。", "Review context pruning, cache hits, model routing, and prompt usage by run.")}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={filteredRuns.length ? "success" : "pending"}>
                {text(`${filteredRuns.length} / ${runs.length} 条`, `${filteredRuns.length} / ${runs.length} rows`)}
              </Badge>
              {activePlans.length ? (
                <Badge tone="info">{activePlans.join(" / ")}</Badge>
              ) : (
                <span className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-500">
                  {text("暂无优化方案证据", "No optimizer evidence")}
                </span>
              )}
            </div>
          </CardHeader>

          <div className="grid grid-cols-2 border-b border-slate-100 bg-white md:grid-cols-5">
            <SummaryCell
              label={text("总 Token", "Total Tokens")}
              value={formatTokenValue(visibleSummary.actualTotalTokens)}
              helper={`${text("输入", "Input")} ${formatTokenValue(visibleSummary.actualPromptTokens)} / ${text("输出", "Output")} ${formatTokenValue(visibleSummary.actualCompletionTokens)}`}
              icon={<Route className="h-4 w-4" />}
            />
            <SummaryCell
              label={text("预计节省", "Estimated Saved")}
              value={formatTokenValue(visibleSummary.estimatedSavedTokens)}
              helper={formatPercent(visibleSummary.estimatedSavingsPercent)}
              icon={<Sparkles className="h-4 w-4" />}
            />
            <SummaryCell
              label={text("候选上下文", "Candidate Context")}
              value={formatTokenValue(visibleSummary.estimatedCandidateTokens)}
              helper={`${text("裁剪", "Pruned")} ${formatNumber(visibleSummary.pruningManifestCount)}`}
            />
            <SummaryCell
              label={text("缓存命中率", "Cache Hit Rate")}
              value={formatPercent(visibleSummary.cacheHitRate)}
              helper={`${formatNumber(visibleSummary.cacheHitCount)} / ${formatNumber(visibleSummary.cacheMissCount)}`}
              icon={<Database className="h-4 w-4" />}
            />
            <SummaryCell
              label={text("低成本路由", "Low-cost Routes")}
              value={formatNumber(visibleSummary.lowCostRouteCount)}
              helper={text("模型路由证据", "Model routing evidence")}
              icon={<Zap className="h-4 w-4" />}
            />
          </div>

          <div className="grid gap-2 border-b border-slate-100 bg-slate-50/70 p-3 lg:grid-cols-[minmax(10rem,12rem)_minmax(10rem,1fr)_minmax(10rem,1fr)_auto]">
            <div className="grid gap-1 text-[11px] font-medium text-slate-500">
              <span>{text("时间范围", "Time Range")}</span>
              <MenuSelect
                ariaLabel={text("时间范围", "Time Range")}
                value={timeRange}
                onChange={(value) => setTimeRange(value as TimeRange)}
                options={timeRangeOptions}
                size="compact"
                showSelectedDescription={false}
                buttonClassName="h-8 rounded-md px-2.5 py-1.5 shadow-none"
                menuClassName="max-h-64 rounded-md"
              />
            </div>
            <div className="grid gap-1 text-[11px] font-medium text-slate-500">
              <span>{text("模型", "Model")}</span>
              <MenuSelect
                ariaLabel={text("模型", "Model")}
                value={modelFilter}
                onChange={setModelFilter}
                options={modelMenuOptions}
                size="compact"
                showSelectedDescription={false}
                buttonClassName="h-8 rounded-md px-2.5 py-1.5 shadow-none"
                menuClassName="max-h-64 rounded-md"
              />
            </div>
            <div className="grid gap-1 text-[11px] font-medium text-slate-500">
              <span>Agent</span>
              <MenuSelect
                ariaLabel="Agent"
                value={agentFilter}
                onChange={setAgentFilter}
                options={agentMenuOptions}
                size="compact"
                showSelectedDescription={false}
                buttonClassName="h-8 rounded-md px-2.5 py-1.5 shadow-none"
                menuClassName="max-h-64 rounded-md"
              />
            </div>
            <div className="flex items-end gap-2">
              <Button
                type="button"
                variant="secondary"
                disabled={!filtersActive}
                onClick={() => {
                  setTimeRange("all");
                  setModelFilter(ALL_FILTER);
                  setAgentFilter(ALL_FILTER);
                }}
              >
                <Filter className="h-3.5 w-3.5" />
                {text("重置", "Reset")}
              </Button>
            </div>
          </div>

          <div className="overflow-x-auto">
            <Table className="min-w-[1120px] table-fixed">
              <colgroup>
                <col className="w-[5rem]" />
                <col className="w-[12rem]" />
                <col className="w-[5.5rem]" />
                <col className="w-[7.5rem]" />
                <col className="w-[5rem]" />
                <col className="w-[7rem]" />
                <col className="w-[5rem]" />
                <col className="w-[10rem]" />
                <col className="w-[10rem]" />
                <col className="w-8" />
              </colgroup>
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <Th>{text("时间", "Time")}</Th>
                  <Th>{text("运行", "Run")}</Th>
                  <Th>Agent</Th>
                  <Th>{text("模型", "Model")}</Th>
                  <Th>{text("方案", "Plan")}</Th>
                  <Th>{text("Token", "Tokens")}</Th>
                  <Th>{text("节省", "Saved")}</Th>
                  <Th>{text("缓存", "Cache")}</Th>
                  <Th>{text("证据", "Evidence")}</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {filteredRuns.map((run) => (
                  <TokenSavingsRow key={run.context_manifest_id} run={run} />
                ))}
                {!tokenSavings.isLoading && filteredRuns.length === 0 && (
                  <tr>
                    <Td colSpan={10} className="py-12 text-center text-slate-500">
                      {filtersActive
                        ? text("当前筛选没有匹配的节省证据。", "No token savings evidence matches the filters.")
                        : text(
                            "暂无标记节省证据。先在智能体工作室选择省用方案，然后从工作台发起一次运行。",
                            "No token savings evidence yet. Select a saving plan in Agent Studio, then start a run from Workspace.",
                          )}
                    </Td>
                  </tr>
                )}
              </tbody>
            </Table>
          </div>
        </Card>

        {tokenSavings.error ? (
          <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            {text("加载标记节省数据失败", "Failed to load token savings data")}：
            {tokenSavings.error instanceof Error ? tokenSavings.error.message : String(tokenSavings.error)}
          </div>
        ) : null}
      </div>
    </ConsoleShell>
  );
}

function TokenSavingsRow({ run }: { run: TokenSavingsRunItem }) {
  const { text } = useI18n();
  const plans = run.optimizer_labels.length ? run.optimizer_labels : [text("自定义优化器", "Custom optimizer")];
  const modelNames = modelNamesForRun(run);
  const cacheSources = normalizedCacheSources(run.cache_sources);
  const cacheHitCount = run.retrieval_cache_hit_count ?? 0;
  const cacheMissCount = run.retrieval_cache_miss_count ?? 0;
  const cacheStaleCount = run.retrieval_cache_stale_count ?? 0;
  const cacheRate = percentage(cacheHitCount, cacheHitCount + cacheMissCount + cacheStaleCount);
  const omissionReasons = (run.omission_reasons ?? []).slice(0, 2);
  const lowCostRoute = run.low_cost_routes[0] ?? null;

  return (
    <tr className="border-t border-slate-100 align-top hover:bg-slate-50/60">
      <Td className="whitespace-nowrap font-mono text-slate-500">{formatShortDate(run.updated_at)}</Td>
      <Td>
        <Link
          to={`/runs/${run.run_id}`}
          className="block truncate font-medium text-slate-950 hover:underline"
          title={run.title}
        >
          {run.title}
        </Link>
        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          <span className="font-mono text-[10px] text-slate-400">{run.run_id.slice(0, 8)}</span>
          <Badge tone={statusTone(run.status)}>{statusLabel(run.status)}</Badge>
        </div>
      </Td>
      <Td className="truncate font-mono text-slate-600" title={run.agent_id ?? undefined}>
        {run.agent_id ?? "-"}
      </Td>
      <Td>
        <div className="flex flex-wrap gap-1">
          {modelNames.length ? (
            modelNames.map((model) => (
              <Badge
                key={model}
                tone="neutral"
                className="max-w-[7rem] truncate whitespace-nowrap font-mono normal-case tracking-normal"
              >
                {model}
              </Badge>
            ))
          ) : (
            <span className="text-slate-400">-</span>
          )}
        </div>
      </Td>
      <Td>
        <div className="flex flex-wrap gap-1">
          {plans.map((plan) => (
            <Badge key={plan} tone="info">
              {plan}
            </Badge>
          ))}
        </div>
        {run.optimizer_decision_count > 0 ? (
          <div className="mt-1 text-[11px] text-slate-500">
            {run.optimizer_decision_count} {text("条决策", "decisions")}
          </div>
        ) : null}
      </Td>
      <Td>
        <MetricStack
          items={[
            [text("候选", "Candidate"), formatTokenValue(run.estimated_candidate_tokens)],
            [text("Prompt", "Prompt"), formatTokenValue(run.actual_prompt_tokens)],
            [text("总计", "Total"), formatTokenValue(run.actual_total_tokens)],
          ]}
        />
      </Td>
      <Td>
        <div className="font-mono text-sm font-semibold text-slate-950">
          {formatTokenValue(run.estimated_saved_tokens)}
        </div>
        <div className="mt-1 text-[11px] text-slate-500">{formatPercent(run.estimated_savings_percent)}</div>
      </Td>
      <Td>
        <div className="font-mono text-sm font-semibold text-slate-950">{formatPercent(cacheRate)}</div>
        <div className="mt-1 text-[11px] text-slate-500">
          {formatNumber(cacheHitCount)} / {formatNumber(cacheMissCount)}
          {cacheStaleCount ? ` / ${formatNumber(cacheStaleCount)}` : ""}
        </div>
        <div className="mt-1 truncate text-[11px] text-slate-500" title={cacheSourceText(cacheSources)}>
          {cacheSourceText(cacheSources)}
        </div>
      </Td>
      <Td>
        <div className="text-[11px] text-slate-500">
          {text("保留", "Included")} {formatNumber(run.included_count)}
          <span className="mx-1 text-slate-300">/</span>
          {text("省略", "Omitted")} {formatNumber(run.omitted_count)}
        </div>
        {omissionReasons.length ? (
          <div className="mt-1 flex flex-wrap gap-1">
            {omissionReasons.map((item) => (
              <Badge key={item.reason} tone="warning">
                {omitReasonLabel(item.reason)} · {item.count}
              </Badge>
            ))}
          </div>
        ) : null}
        {lowCostRoute ? (
          <div className="mt-1 truncate text-[11px] text-slate-500" title={lowCostRoute.reason}>
            {text("低成本路由", "Low-cost")}：{lowCostRoute.model_name} · {lowCostRoute.reason}
          </div>
        ) : null}
      </Td>
      <Td className="text-right">
        <Link to={`/runs/${run.run_id}`} className="inline-flex text-slate-400 hover:text-slate-800" aria-label={text("打开运行详情", "Open run detail")}>
          <ArrowUpRight className="h-4 w-4" />
        </Link>
      </Td>
    </tr>
  );
}

function SummaryCell({
  label,
  value,
  helper,
  icon,
}: {
  label: string;
  value: string;
  helper?: string;
  icon?: ReactNode;
}) {
  return (
    <div className="min-w-0 border-r border-slate-100 px-3 py-3 last:border-r-0">
      <div className="flex items-center justify-between gap-2 text-[11px] font-medium text-slate-500">
        <span className="truncate">{label}</span>
        {icon ? <span className="shrink-0 text-slate-400">{icon}</span> : null}
      </div>
      <div className="mt-1 truncate font-mono text-xl font-semibold tracking-normal text-slate-950">
        {value}
      </div>
      {helper ? <div className="mt-0.5 truncate text-[11px] text-slate-500">{helper}</div> : null}
    </div>
  );
}

function MetricStack({ items }: { items: Array<[string, string]> }) {
  return (
    <div className="grid gap-1">
      {items.map(([label, value]) => (
        <div key={label} className="flex min-w-[7rem] items-center justify-between gap-3 text-[11px]">
          <span className="text-slate-500">{label}</span>
          <span className="font-mono font-semibold text-slate-900">{value}</span>
        </div>
      ))}
    </div>
  );
}

function summarizeRuns(runs: TokenSavingsRunItem[]) {
  const summary = runs.reduce(
    (acc, run) => {
      acc.actualPromptTokens += run.actual_prompt_tokens;
      acc.actualCompletionTokens += run.actual_completion_tokens;
      acc.actualTotalTokens += run.actual_total_tokens;
      acc.estimatedCandidateTokens += run.estimated_candidate_tokens;
      acc.estimatedSavedTokens += run.estimated_saved_tokens;
      acc.pruningManifestCount += run.pruning_applied ? 1 : 0;
      acc.cacheHitCount += run.retrieval_cache_hit_count;
      acc.cacheMissCount += run.retrieval_cache_miss_count;
      acc.cacheStaleCount += run.retrieval_cache_stale_count;
      acc.lowCostRouteCount += run.low_cost_routes.length;
      return acc;
    },
    {
      actualPromptTokens: 0,
      actualCompletionTokens: 0,
      actualTotalTokens: 0,
      estimatedCandidateTokens: 0,
      estimatedSavedTokens: 0,
      estimatedSavingsPercent: 0,
      pruningManifestCount: 0,
      cacheHitCount: 0,
      cacheMissCount: 0,
      cacheStaleCount: 0,
      cacheHitRate: 0,
      lowCostRouteCount: 0,
    },
  );
  summary.estimatedSavingsPercent = percentage(
    summary.estimatedSavedTokens,
    summary.estimatedCandidateTokens,
  );
  summary.cacheHitRate = percentage(
    summary.cacheHitCount,
    summary.cacheHitCount + summary.cacheMissCount + summary.cacheStaleCount,
  );
  return summary;
}

function summaryFromApi(summary?: TokenSavingsSummary) {
  return {
    actualPromptTokens: summary?.actual_prompt_tokens ?? 0,
    actualCompletionTokens: summary?.actual_completion_tokens ?? 0,
    actualTotalTokens: summary?.actual_total_tokens ?? 0,
    estimatedCandidateTokens: summary?.estimated_candidate_tokens ?? 0,
    estimatedSavedTokens: summary?.estimated_saved_tokens ?? 0,
    estimatedSavingsPercent: summary?.estimated_savings_percent ?? 0,
    pruningManifestCount: summary?.pruning_manifest_count ?? 0,
    cacheHitCount: summary?.retrieval_cache_hit_count ?? 0,
    cacheMissCount: summary?.retrieval_cache_miss_count ?? 0,
    cacheStaleCount: summary?.retrieval_cache_stale_count ?? 0,
    cacheHitRate: percentage(
      summary?.retrieval_cache_hit_count ?? 0,
      (summary?.retrieval_cache_hit_count ?? 0) +
        (summary?.retrieval_cache_miss_count ?? 0) +
        (summary?.retrieval_cache_stale_count ?? 0),
    ),
    lowCostRouteCount: summary?.low_cost_route_count ?? 0,
  };
}

function modelNamesForRun(run: TokenSavingsRunItem) {
  return uniqueSorted([
    ...(run.model_names ?? []),
    ...(run.low_cost_routes ?? []).map((route) => route.model_name),
  ].filter(Boolean));
}

function matchesTimeRange(run: TokenSavingsRunItem, range: TimeRange, generatedAt: string | null) {
  if (range === "all") return true;
  const referenceMs = Date.parse(generatedAt ?? "");
  const runMs = Date.parse(run.updated_at);
  if (!Number.isFinite(referenceMs) || !Number.isFinite(runMs)) return true;
  const windows: Record<Exclude<TimeRange, "all">, number> = {
    "24h": 24 * 60 * 60 * 1000,
    "7d": 7 * 24 * 60 * 60 * 1000,
    "30d": 30 * 24 * 60 * 60 * 1000,
  };
  return runMs >= referenceMs - windows[range];
}

function emptyCacheSource(cache_source: string, label: string): CacheSourceSummary {
  return {
    cache_source,
    label,
    hit_count: 0,
    miss_count: 0,
    stale_count: 0,
    estimated_saved_tokens: 0,
    hit_rate: 0,
    reason: null,
  };
}

function normalizedCacheSources(sources: CacheSourceSummary[]) {
  const bySource = new Map(sources.map((source) => [source.cache_source, source]));
  return [
    bySource.get("compression_summary") ?? emptyCacheSource("compression_summary", "摘要缓存"),
    bySource.get("rag_retrieval") ?? emptyCacheSource("rag_retrieval", "RAG 检索"),
    bySource.get("long_term_memory") ?? emptyCacheSource("long_term_memory", "长期记忆"),
  ];
}

function cacheSourceText(sources: CacheSourceSummary[]) {
  return sources.map((source) => `${source.label} ${formatPercent(source.hit_rate)}`).join(" / ");
}

function uniqueSorted(values: string[]) {
  return Array.from(new Set(values.filter((value) => value.trim().length > 0))).sort((a, b) => a.localeCompare(b));
}

function formatNumber(value?: number | null) {
  return new Intl.NumberFormat("en").format(value ?? 0);
}

function formatTokenValue(value?: number | null) {
  return new Intl.NumberFormat("en", {
    maximumFractionDigits: value != null && Math.abs(value) >= 1000 ? 2 : 0,
    notation: value != null && Math.abs(value) >= 1000 ? "compact" : "standard",
    compactDisplay: "short",
  }).format(value ?? 0);
}

function formatPercent(value?: number | null) {
  return `${new Intl.NumberFormat("en", { maximumFractionDigits: 2 }).format(value ?? 0)}%`;
}

function percentage(numerator: number, denominator: number) {
  if (!Number.isFinite(denominator) || denominator <= 0) {
    return 0;
  }
  return (numerator / denominator) * 100;
}

function omitReasonLabel(reason: string) {
  const labels: Record<string, string> = {
    optimizer_budget: "预算裁剪",
    optimizer_section_limit: "数量上限",
    token_budget: "预算裁剪",
  };
  return labels[reason] ?? reason;
}
