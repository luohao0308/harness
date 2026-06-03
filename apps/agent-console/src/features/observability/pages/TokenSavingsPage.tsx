import { useQuery } from "@tanstack/react-query";
import {
  ArrowUpRight,
  Box,
  Database,
  Gauge,
  History,
  Route,
  Scissors,
  Sparkles,
  Zap,
} from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, statusTone } from "../../../components/ui/badge";
import { Card, CardHeader } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { TermHint } from "../../../components/ui/term";
import { useI18n } from "../../../lib/i18n";
import { cn, formatShortDate } from "../../../lib/utils";
import { getTokenSavings, type CacheSourceSummary, type TokenSavingsRunItem } from "../../tasks/api";

export function TokenSavingsPage() {
  const { text } = useI18n();
  const tokenSavings = useQuery({
    queryKey: ["observability", "token-savings"],
    queryFn: () => getTokenSavings(50),
  });
  const summary = tokenSavings.data?.summary;
  const runs = tokenSavings.data?.runs ?? [];
  const savingsPercent = summary?.estimated_savings_percent ?? 0;
  const activePlans = summary?.optimizer_labels.length
    ? summary.optimizer_labels.join(" / ")
    : text("暂无优化方案证据", "No optimizer evidence");
  const cacheHitCount = summary?.retrieval_cache_hit_count ?? 0;
  const cacheMissCount = summary?.retrieval_cache_miss_count ?? 0;
  const cacheStaleCount = summary?.retrieval_cache_stale_count ?? 0;
  const cacheHitRate = percentage(cacheHitCount, cacheHitCount + cacheMissCount + cacheStaleCount);
  const cacheSources = normalizedCacheSources(summary?.cache_sources ?? []);

  return (
    <ConsoleShell title={text("标记节省", "Token Savings")}>
      <div className="space-y-4 bg-slate-50/70 p-4">
        <section className="grid grid-cols-12 gap-3">
          <Card className="col-span-12 overflow-hidden border-slate-200 bg-white p-4 shadow-sm xl:col-span-3">
            <div className="flex min-w-0 items-center gap-4">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-amber-100 text-amber-600">
                <Box className="h-6 w-6" strokeWidth={2} />
              </div>
              <div className="min-w-0">
                <div className="text-xs font-semibold text-slate-500">
                  {text("总 Token", "Total Tokens")}
                </div>
                <div className="mt-0.5 font-mono text-3xl font-semibold tracking-normal text-slate-950">
                  {formatTokenValue(summary?.actual_total_tokens)}
                </div>
                <div className="mt-1 text-xs font-medium text-slate-500">
                  {text("输入", "Input")}：{formatTokenValue(summary?.actual_prompt_tokens)}
                  <span className="mx-1.5 text-slate-300">/</span>
                  {text("输出", "Output")}：{formatTokenValue(summary?.actual_completion_tokens)}
                </div>
              </div>
            </div>
          </Card>

          <KpiCard
            className="col-span-6 md:col-span-3 xl:col-span-2"
            label={text("预计节省 Token", "Estimated Saved Tokens")}
            value={formatTokenValue(summary?.estimated_saved_tokens)}
            icon={<Sparkles className="h-4 w-4" />}
          />
          <KpiCard
            className="col-span-6 md:col-span-3 xl:col-span-2"
            label={text("实际 Prompt Token", "Actual Prompt Tokens")}
            value={formatTokenValue(summary?.actual_prompt_tokens)}
            icon={<Route className="h-4 w-4" />}
          />
          <KpiCard
            className="col-span-6 md:col-span-3 xl:col-span-2"
            label={text("节省率", "Savings Rate")}
            value={formatPercent(savingsPercent)}
            icon={<Gauge className="h-4 w-4" />}
          />
          <KpiCard
            className="col-span-6 md:col-span-3 xl:col-span-3"
            label={text("缓存命中率", "Cache Hit Rate")}
            value={formatPercent(cacheHitRate)}
            icon={<Database className="h-4 w-4" />}
          />
        </section>

        <section className="grid grid-cols-12 gap-3">
          <SmallMetricCard
            className="col-span-6 md:col-span-3"
            label={text("候选上下文", "Candidate Context")}
            value={formatTokenValue(summary?.estimated_candidate_tokens)}
          />
          <SmallMetricCard
            className="col-span-6 md:col-span-3"
            label={text("发生裁剪", "Pruned Runs")}
            value={formatNumber(summary?.pruning_manifest_count)}
            icon={<Scissors className="h-4 w-4" />}
          />
          <SmallMetricCard
            className="col-span-6 md:col-span-3"
            label={text("缓存命中", "Cache")}
            value={`${formatNumber(cacheHitCount)} / ${formatNumber(cacheMissCount)}`}
            helper={
              cacheStaleCount > 0
                ? text(
                    `命中 / 未命中 / 失效 ${formatNumber(cacheStaleCount)}`,
                    `Hits / misses / stale ${formatNumber(cacheStaleCount)}`,
                  )
                : text("命中 / 未命中", "Hits / misses")
            }
            icon={<Database className="h-4 w-4" />}
          />
          <SmallMetricCard
            className="col-span-6 md:col-span-3"
            label={text("低成本路由", "Low-cost Routes")}
            value={formatNumber(summary?.low_cost_route_count)}
            icon={<Zap className="h-4 w-4" />}
          />
        </section>

        <section className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {cacheSources.map((source) => (
            <CacheSourceCard key={source.cache_source} source={source} />
          ))}
        </section>

        <Card className="overflow-hidden border-slate-200 shadow-sm">
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <History className="h-4 w-4" />
              {text("最近运行节省证据", "Recent Run Savings Evidence")}
            </div>
            <div className="flex items-center gap-2">
              <Badge tone={summary?.context_manifest_count ? "success" : "pending"}>
                {activePlans}
              </Badge>
              <div className="text-xs text-slate-500">
                {tokenSavings.isLoading
                  ? text("加载中...", "Loading...")
                  : text(`${runs.length} 个运行`, `${runs.length} runs`)}
              </div>
            </div>
          </CardHeader>
          <div className="overflow-x-auto">
            <Table className="min-w-[880px]">
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <Th>{text("运行", "Run")}</Th>
                  <Th>{text("方案", "Plan")}</Th>
                  <Th>{text("预计节省", "Saved")}</Th>
                  <Th>{text("实际 Prompt", "Prompt")}</Th>
                  <Th>{text("缓存", "Cache")}</Th>
                  <Th>{text("省略原因", "Omit Reasons")}</Th>
                  <Th>{text("更新时间", "Updated")}</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <TokenSavingsRow key={run.context_manifest_id} run={run} />
                ))}
                {!tokenSavings.isLoading && runs.length === 0 && (
                  <tr>
                    <Td colSpan={8} className="py-12 text-center text-slate-500">
                      {text(
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
  const optimizerLabels = run.optimizer_labels ?? [];
  const omissionReasons = (run.omission_reasons ?? []).slice(0, 2);
  const cacheSources = run.cache_sources ?? [];
  const cacheHitCount = run.retrieval_cache_hit_count ?? 0;
  const cacheMissCount = run.retrieval_cache_miss_count ?? 0;
  const cacheStaleCount = run.retrieval_cache_stale_count ?? 0;
  const plans = optimizerLabels.length ? optimizerLabels : [text("自定义优化器", "Custom")];
  const runCacheRate = percentage(
    cacheHitCount,
    cacheHitCount + cacheMissCount + cacheStaleCount,
  );
  const cacheLabel =
    cacheSources.length > 0
      ? cacheSources
          .slice(0, 2)
          .map((source) => `${source.label} ${formatPercent(source.hit_rate)}`)
          .join(" / ")
      : null;
  return (
    <tr className="border-t border-slate-100 hover:bg-slate-50/60">
      <Td>
        <Link to={`/runs/${run.run_id}`} className="font-medium text-slate-950 hover:underline">
          {run.title}
        </Link>
        <div className="mt-1 flex items-center gap-2">
          <span className="font-mono text-[10px] text-slate-400">{run.run_id.slice(0, 8)}</span>
          <Badge tone={statusTone(run.status)}>{run.status}</Badge>
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
        <div className="font-mono text-sm text-slate-950">{formatTokenValue(run.estimated_saved_tokens)}</div>
        <div className="mt-1 text-[11px] text-slate-500">{formatPercent(run.estimated_savings_percent)}</div>
      </Td>
      <Td>
        <div className="font-mono text-sm text-slate-950">{formatTokenValue(run.actual_prompt_tokens)}</div>
        <div className="mt-1 text-[11px] text-slate-500">
          {text("总计", "Total")} {formatTokenValue(run.actual_total_tokens)}
        </div>
      </Td>
      <Td>
        <div className="font-mono text-sm text-slate-950">{formatPercent(runCacheRate)}</div>
        <div className="mt-1 text-[11px] text-slate-500">
          {formatNumber(run.retrieval_cache_hit_count)} / {formatNumber(run.retrieval_cache_miss_count)}
        </div>
        {cacheLabel ? <div className="mt-1 text-[11px] text-slate-500">{cacheLabel}</div> : null}
      </Td>
      <Td>
        {omissionReasons.length ? (
          <div className="flex flex-wrap gap-1">
            {omissionReasons.map((item) => (
              <Badge key={item.reason} tone="warning">
                {omitReasonLabel(item.reason)} · {item.count}
              </Badge>
            ))}
          </div>
        ) : (
          <span className="text-slate-400">-</span>
        )}
        {run.low_cost_routes.length ? (
          <div className="mt-1 text-[11px] text-slate-500">
            <TermHint description="模型调用使用低成本路由的原因">低成本路由</TermHint>：
            {run.low_cost_routes[0]?.reason}
          </div>
        ) : null}
      </Td>
      <Td className="font-mono text-slate-500">{formatShortDate(run.updated_at)}</Td>
      <Td className="text-right">
        <Link to={`/runs/${run.run_id}`} className="inline-flex text-slate-400 hover:text-slate-800">
          <ArrowUpRight className="h-4 w-4" />
        </Link>
      </Td>
    </tr>
  );
}

function KpiCard({
  label,
  value,
  icon,
  className,
}: {
  label: string;
  value: string;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("border-slate-200 p-4 shadow-sm", className)}>
      <div className="flex items-center justify-between gap-3 text-slate-500">
        <span className="min-w-0 text-xs font-medium">{label}</span>
        <span className="shrink-0 text-slate-500">{icon}</span>
      </div>
      <div className="mt-3">
        <span className="font-mono text-3xl font-medium tracking-normal text-slate-950">{value}</span>
      </div>
    </Card>
  );
}

function SmallMetricCard({
  label,
  value,
  helper,
  icon,
  className,
}: {
  label: string;
  value: string;
  helper?: string;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("border-slate-200 p-3.5 shadow-sm", className)}>
      <div className="flex items-center justify-between gap-3 text-slate-500">
        <span className="text-xs font-medium">{label}</span>
        {icon ? <span className="shrink-0 text-slate-400">{icon}</span> : null}
      </div>
      <div className="mt-3 font-mono text-2xl font-medium tracking-normal text-slate-950">
        {value}
      </div>
      {helper ? <div className="mt-1 text-[11px] text-slate-500">{helper}</div> : null}
    </Card>
  );
}

function CacheSourceCard({ source }: { source: CacheSourceSummary }) {
  return (
    <Card className="border-slate-200 p-3.5 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 text-xs font-semibold text-slate-600">{source.label}</div>
        <Database className="h-4 w-4 shrink-0 text-slate-400" />
      </div>
      <div className="mt-3 flex items-end justify-between gap-3">
        <div className="font-mono text-2xl font-medium tracking-normal text-slate-950">
          {formatPercent(source.hit_rate)}
        </div>
        <div className="text-right font-mono text-xs text-slate-500">
          {formatNumber(source.hit_count)} / {formatNumber(source.miss_count)}
        </div>
      </div>
      <div className="mt-2 flex items-center justify-between gap-3 text-[11px] text-slate-500">
        <span>{source.reason ?? "cache_ready"}</span>
        <span>{formatTokenValue(source.estimated_saved_tokens)}</span>
      </div>
    </Card>
  );
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
