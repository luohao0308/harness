import { useQuery } from "@tanstack/react-query";
import { Activity, Box, ExternalLink, Gauge, RefreshCw } from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, Dot, statusTone } from "../../../components/ui/badge";
import { Card, CardHeader } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { enabledLabel, statusLabel } from "../../../lib/labels";
import type { CountItem } from "../../tasks/api";
import { getObservabilitySummary } from "../../tasks/api";

export function ObservabilityPage() {
  const summary = useQuery({
    queryKey: ["observability", "summary"],
    queryFn: getObservabilitySummary,
  });
  const data = summary.data;

  return (
    <ConsoleShell title="观测">
      <div className="space-y-4 p-4">
        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Activity className="h-4 w-4" /> 运行总览
            </div>
            <a
              className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-900"
              href="http://127.0.0.1:8000/metrics"
            >
              Prometheus 指标 /metrics <ExternalLink className="h-3 w-3" />
            </a>
          </CardHeader>
          <div className="grid grid-cols-6 gap-3 p-3 text-xs">
            <Metric label="任务总数" value={formatNumber(data?.task_total)} />
            <Metric label="失败任务" value={formatNumber(data?.failed_task_total)} />
            <Metric label="事件总数" value={formatNumber(data?.event_total)} />
            <Metric label="模型调用" value={formatNumber(data?.model_call_total)} />
            <Metric label="工具调用" value={formatNumber(data?.tool_call_total)} />
            <Metric label="沙箱总数" value={formatNumber(data?.sandbox_total)} />
          </div>
          <StatusLine isLoading={summary.isLoading} error={summary.error} />
        </Card>

        <div className="grid grid-cols-2 gap-4">
          <DistributionCard title="任务状态" items={data?.tasks_by_status ?? []} />
          <DistributionCard title="子 Agent 状态" items={data?.subagents_by_status ?? []} />
          <DistributionCard title="模型调用状态" items={data?.model_calls_by_status ?? []} />
          <DistributionCard title="工具调用状态" items={data?.tool_calls_by_status ?? []} />
        </div>

        <div className="grid grid-cols-[1fr_2fr] gap-4">
          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Box className="h-4 w-4" /> WarmPool
              </div>
              <span className="text-xs text-slate-500">
                {enabledLabel(Boolean(data?.warm_pool.enabled))}
              </span>
            </CardHeader>
            <div className="grid grid-cols-2 gap-3 p-3 text-xs">
              <Metric label="空闲" value={formatNumber(data?.warm_pool.idle)} />
              <Metric label="忙碌" value={formatNumber(data?.warm_pool.busy)} />
              <Metric label="失败" value={formatNumber(data?.warm_pool.failed)} />
              <Metric
                label="容量"
                value={`${formatNumber(data?.warm_pool.min_size)} / ${formatNumber(
                  data?.warm_pool.max_size,
                )}`}
              />
              <Metric label="命中" value={formatNumber(data?.warm_pool.hit_total)} />
              <Metric label="未命中" value={formatNumber(data?.warm_pool.miss_total)} />
            </div>
          </Card>

          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Gauge className="h-4 w-4" /> 沙箱状态
              </div>
              <span className="text-xs text-slate-500">Docker 沙箱实例分布</span>
            </CardHeader>
            <DistributionTable items={data?.sandboxes_by_status ?? []} emptyText="暂无沙箱实例" />
          </Card>
        </div>
      </div>
    </ConsoleShell>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50 p-3">
      <div className="text-slate-500">{label}</div>
      <div className="mt-1 font-mono text-base font-semibold text-slate-900">{value}</div>
    </div>
  );
}

function DistributionCard({ title, items }: { title: string; items: CountItem[] }) {
  return (
    <Card>
      <CardHeader>
        <div className="text-[11px] tracking-widest text-slate-500">{title}</div>
      </CardHeader>
      <DistributionTable items={items} emptyText="暂无数据" />
    </Card>
  );
}

function DistributionTable({ items, emptyText }: { items: CountItem[]; emptyText: string }) {
  return (
    <Table>
      <thead className="bg-slate-50 text-slate-500">
        <tr>
          <Th>状态</Th>
          <Th className="text-right">数量</Th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => {
          const tone = statusTone(item.name);
          return (
            <tr key={item.name} className="border-t border-slate-100">
              <Td>
                <Badge tone={tone}>
                  <Dot tone={tone} />
                  {statusLabel(item.name)}
                </Badge>
              </Td>
              <Td className="text-right font-mono text-slate-900">{item.count}</Td>
            </tr>
          );
        })}
        {items.length === 0 ? (
          <tr className="border-t border-slate-100">
            <Td colSpan={2} className="py-8 text-center text-slate-500">
              {emptyText}
            </Td>
          </tr>
        ) : null}
      </tbody>
    </Table>
  );
}

function StatusLine({ isLoading, error }: { isLoading: boolean; error: Error | null }) {
  if (isLoading) {
    return (
      <div className="flex items-center gap-2 border-t border-slate-100 px-3 py-2 text-xs text-slate-500">
        <RefreshCw className="h-3 w-3 animate-spin" /> 正在读取后端观测数据
      </div>
    );
  }

  if (error) {
    return (
      <div className="border-t border-red-100 bg-red-50 px-3 py-2 text-xs text-red-700">
        观测数据读取失败：{error.message}
      </div>
    );
  }

  return null;
}

function formatNumber(value: number | undefined) {
  return value === undefined ? "..." : new Intl.NumberFormat("zh-CN").format(value);
}
