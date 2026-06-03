import { useState } from "react";
import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, CreditCard, Hash, Layers3, RefreshCw, TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { formatShortDate } from "../../../lib/utils";
import { CostStackChart } from "../components/CostStackChart";
import { getCostRollup, type CostRollup } from "../../tasks/api";

const WINDOWS: Array<{ value: CostRollup["window"]; label: string }> = [
  { value: "24h", label: "24 小时" },
  { value: "7d", label: "7 天" },
  { value: "30d", label: "30 天" },
  { value: "all", label: "全部" },
];

const GROUPS: Array<{ value: CostRollup["group_by"]; label: string }> = [
  { value: "agent", label: "按智能体" },
  { value: "provider", label: "按模型" },
  { value: "specialist", label: "按专家" },
  { value: "adapter", label: "按适配器" },
];

export function CostDashboardPage() {
  const [windowValue, setWindowValue] = useState<CostRollup["window"]>("7d");
  const [groupBy, setGroupBy] = useState<CostRollup["group_by"]>("agent");
  const rollup = useQuery({
    queryKey: ["observability", "cost-rollup", windowValue, groupBy],
    queryFn: () => getCostRollup({ window: windowValue, group_by: groupBy }),
    retry: false,
  });
  const data = rollup.data;
  const blockingPricing = (data?.pricing_statuses ?? []).filter((item) => item.blocking);

  return (
    <ConsoleShell title="成本观测">
      <div className="space-y-4 bg-slate-50/70 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Link to="/observability" className="hover:text-slate-900">观测</Link>
            <span>/</span>
            <span className="font-medium text-slate-900">成本</span>
          </div>
          <Button onClick={() => void rollup.refetch()} disabled={rollup.isFetching}>
            <RefreshCw className="h-3.5 w-3.5" /> 刷新
          </Button>
        </div>

        <section className="grid grid-cols-12 gap-3">
          <KpiCard className="col-span-6 lg:col-span-3" label="总 Token" value={formatNumber(data?.total_tokens)} icon={<Hash className="h-4 w-4" />} />
          <KpiCard className="col-span-6 lg:col-span-3" label="总 USD" value={formatUsd(data?.total_cost_usd)} icon={<CreditCard className="h-4 w-4" />} />
          <KpiCard className="col-span-6 lg:col-span-3" label="总运行" value={formatNumber(data?.total_runs)} icon={<Activity className="h-4 w-4" />} />
          <KpiCard className="col-span-6 lg:col-span-3" label="平均运行成本" value={formatUsd(data?.average_run_cost_usd)} icon={<Layers3 className="h-4 w-4" />} />
        </section>

        {blockingPricing.length > 0 ? (
          <div className="flex flex-wrap items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <div className="font-medium">模型价格来源存在企业门禁阻塞</div>
              <div className="mt-1">
                {blockingPricing
                  .map((item) => `${item.model}: ${pricingStatusLabel(item.status)}`)
                  .join(" / ")}
              </div>
            </div>
          </div>
        ) : null}

        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-slate-900">成本维度</div>
            <div className="flex flex-wrap gap-2">
              {WINDOWS.map((item) => (
                <SegmentButton key={item.value} active={windowValue === item.value} onClick={() => setWindowValue(item.value)}>
                  {item.label}
                </SegmentButton>
              ))}
              <span className="mx-1 h-8 border-l border-slate-200" />
              {GROUPS.map((item) => (
                <SegmentButton key={item.value} active={groupBy === item.value} onClick={() => setGroupBy(item.value)}>
                  {item.label}
                </SegmentButton>
              ))}
            </div>
          </CardHeader>
          <div className="grid grid-cols-1 gap-4 p-3 xl:grid-cols-[1fr_420px]">
            <CostStackChart points={data?.series ?? []} />
            <div className="overflow-x-auto">
              <Table className="min-w-[420px]">
                <thead className="bg-slate-50 text-slate-500">
                  <tr>
                    <Th>维度</Th>
                    <Th>成本</Th>
                    <Th>Token</Th>
                    <Th>价格状态</Th>
                    <Th>占比</Th>
                  </tr>
                </thead>
                <tbody>
                  {(data?.breakdown ?? []).map((item) => (
                    <tr key={item.key} className="border-t border-slate-100">
                      <Td>
                        <div className="font-medium text-slate-900">{item.label}</div>
                        <div className="mt-1 font-mono text-[10px] text-slate-400">{item.key}</div>
                      </Td>
                      <Td className="font-mono">{formatUsd(item.cost_usd)}</Td>
                      <Td className="font-mono">{formatNumber(item.tokens_in + item.tokens_out)}</Td>
                      <Td>
                        <Badge tone={item.pricing_blocking ? "warning" : "success"}>
                          {pricingStatusLabel(item.pricing_status)}
                        </Badge>
                      </Td>
                      <Td>{Math.round(item.share * 100)}%</Td>
                    </tr>
                  ))}
                  {!rollup.isLoading && !data?.breakdown.length ? (
                    <tr>
                      <Td colSpan={5} className="py-10 text-center text-slate-500">暂无成本数据</Td>
                    </tr>
                  ) : null}
                </tbody>
              </Table>
            </div>
          </div>
          <div className="flex items-center justify-between border-t border-slate-100 px-3 py-2 text-xs text-slate-500">
            <span>{rollup.error instanceof Error ? rollup.error.message : "实时聚合模型调用、专家预算和工具适配器证据"}</span>
            {data ? <span>生成于 {formatShortDate(data.generated_at)}</span> : null}
          </div>
        </Card>
      </div>
    </ConsoleShell>
  );
}

function KpiCard({ className, label, value, icon }: { className: string; label: string; value: string; icon: ReactNode }) {
  return (
    <Card className={`${className} p-4`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs font-medium text-slate-500">{label}</div>
          <div className="mt-2 font-mono text-2xl font-semibold text-slate-950">{value}</div>
        </div>
        <div className="rounded-md bg-cyan-50 p-2 text-cyan-700">{icon}</div>
      </div>
    </Card>
  );
}

function SegmentButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`h-8 rounded-md border px-3 text-xs font-medium ${active ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"}`}
    >
      {children}
    </button>
  );
}

function formatNumber(value: number | undefined) {
  return (value ?? 0).toLocaleString();
}

function formatUsd(value: number | undefined) {
  return `$${(value ?? 0).toFixed(6)}`;
}

function pricingStatusLabel(status: string) {
  const labels: Record<string, string> = {
    verified: "已验证",
    missing_pricing: "缺失价格",
    price_unverified: "价格未验证",
    sku_ambiguous: "SKU 模糊",
    currency_conversion_required: "需要汇率",
    stale: "已过期",
    invalid_pricing: "价格无效",
  };
  return labels[status] ?? status;
}
