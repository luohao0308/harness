import { useQuery } from "@tanstack/react-query";
import { Activity, Box, ExternalLink, Gauge, GitBranch, Logs, RefreshCw } from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, Dot, statusTone } from "../../../components/ui/badge";
import { Card, CardHeader } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { useI18n } from "../../../lib/i18n";
import { enabledLabel, eventLabel, statusLabel } from "../../../lib/labels";
import type { CountItem } from "../../tasks/api";
import {
  getObservabilityServicesHealth,
  getObservabilitySummary,
  getObservabilityTrace,
  listGrafanaDashboards,
  listObservabilityLogs,
} from "../../tasks/api";

export function ObservabilityPage() {
  const { text } = useI18n();
  const summary = useQuery({
    queryKey: ["observability", "summary"],
    queryFn: getObservabilitySummary,
  });
  const health = useQuery({
    queryKey: ["observability", "services-health"],
    queryFn: getObservabilityServicesHealth,
  });
  const dashboards = useQuery({
    queryKey: ["observability", "grafana-dashboards"],
    queryFn: listGrafanaDashboards,
  });
  const logs = useQuery({
    queryKey: ["observability", "logs"],
    queryFn: () => listObservabilityLogs({ limit: 8 }),
  });
  const firstTraceId = logs.data?.items.find((item) => item.trace_id)?.trace_id;
  const trace = useQuery({
    queryKey: ["observability", "trace", firstTraceId],
    queryFn: () => getObservabilityTrace(firstTraceId!),
    enabled: Boolean(firstTraceId),
  });
  const data = summary.data;

  return (
    <ConsoleShell title={text("观测", "Observability")}>
      <div className="space-y-4 p-4">
        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Activity className="h-4 w-4" /> {text("运行总览", "Runtime Overview")}
            </div>
            <a
              className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-900"
              href="http://127.0.0.1:8000/metrics"
            >
              {text("Prometheus 指标", "Prometheus metrics")} /metrics <ExternalLink className="h-3 w-3" />
            </a>
          </CardHeader>
          <div className="grid grid-cols-6 gap-3 p-3 text-xs">
            <Metric label={text("任务总数", "Total Tasks")} value={formatNumber(data?.task_total)} />
            <Metric label={text("失败任务", "Failed Tasks")} value={formatNumber(data?.failed_task_total)} />
            <Metric label={text("事件总数", "Total Events")} value={formatNumber(data?.event_total)} />
            <Metric label={text("模型调用", "Model Calls")} value={formatNumber(data?.model_call_total)} />
            <Metric label={text("工具调用", "Tool Calls")} value={formatNumber(data?.tool_call_total)} />
            <Metric label={text("沙箱总数", "Sandboxes")} value={formatNumber(data?.sandbox_total)} />
          </div>
          <StatusLine isLoading={summary.isLoading} error={summary.error} />
        </Card>

        <div className="grid grid-cols-2 gap-4">
          <DistributionCard title={text("任务状态", "Task Status")} items={data?.tasks_by_status ?? []} />
          <DistributionCard title={text("子 Agent 状态", "Subagent Status")} items={data?.subagents_by_status ?? []} />
          <DistributionCard title={text("模型调用状态", "Model Call Status")} items={data?.model_calls_by_status ?? []} />
          <DistributionCard title={text("工具调用状态", "Tool Call Status")} items={data?.tool_calls_by_status ?? []} />
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
              <Metric label={text("空闲", "Idle")} value={formatNumber(data?.warm_pool.idle)} />
              <Metric label={text("忙碌", "Busy")} value={formatNumber(data?.warm_pool.busy)} />
              <Metric label={text("失败", "Failed")} value={formatNumber(data?.warm_pool.failed)} />
              <Metric
                label={text("容量", "Capacity")}
                value={`${formatNumber(data?.warm_pool.min_size)} / ${formatNumber(
                  data?.warm_pool.max_size,
                )}`}
              />
              <Metric label={text("命中", "Hits")} value={formatNumber(data?.warm_pool.hit_total)} />
              <Metric label={text("未命中", "Misses")} value={formatNumber(data?.warm_pool.miss_total)} />
            </div>
          </Card>

          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Gauge className="h-4 w-4" /> {text("沙箱状态", "Sandbox Status")}
              </div>
              <span className="text-xs text-slate-500">{text("Docker 沙箱实例分布", "Docker sandbox instance distribution")}</span>
            </CardHeader>
            <DistributionTable items={data?.sandboxes_by_status ?? []} emptyText={text("暂无沙箱实例", "No sandbox instances")} />
          </Card>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Activity className="h-4 w-4" /> {text("观测服务健康", "Observability Service Health")}
              </div>
              <span className="text-xs text-slate-500">Prometheus / Grafana / Loki / OTel / Tempo</span>
            </CardHeader>
            <Table>
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <Th>{text("服务", "Service")}</Th>
                  <Th>{text("状态", "Status")}</Th>
                  <Th className="text-right">{text("耗时", "Latency")}</Th>
                </tr>
              </thead>
              <tbody>
                {(health.data?.services ?? []).map((service) => (
                  <tr key={service.name} className="border-t border-slate-100">
                    <Td className="font-mono text-slate-900">{service.name}</Td>
                    <Td>
                      <Badge tone={statusTone(service.status)}>
                        {service.status === "unreachable" ? text("不可达", "Unreachable") : statusLabel(service.status)}
                      </Badge>
                    </Td>
                    <Td className="text-right font-mono text-slate-600">
                      {service.latency_ms ?? "-"}ms
                    </Td>
                  </tr>
                ))}
                {!health.isLoading && (health.data?.services.length ?? 0) === 0 && (
                  <tr className="border-t border-slate-100">
                    <Td colSpan={3} className="py-8 text-center text-slate-500">
                      {text("暂无服务健康数据", "No service health data")}
                    </Td>
                  </tr>
                )}
              </tbody>
            </Table>
          </Card>

          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Gauge className="h-4 w-4" /> Grafana Dashboard
              </div>
              <span className="text-xs text-slate-500">{text("后端代理返回 dashboard 深链", "Backend proxy returns dashboard deep links")}</span>
            </CardHeader>
            <div className="space-y-2 p-3">
              {(dashboards.data?.items ?? []).map((dashboard) => (
                <a
                  key={dashboard.uid}
                  href={dashboard.url}
                  className="flex items-center justify-between rounded-md border border-slate-100 px-3 py-2 text-xs hover:bg-slate-50"
                >
                  <span className="text-slate-900">{dashboard.title}</span>
                  <span className="inline-flex items-center gap-1 text-slate-500">
                    {dashboard.source} <ExternalLink className="h-3 w-3" />
                  </span>
                </a>
              ))}
              {!dashboards.isLoading && (dashboards.data?.items.length ?? 0) === 0 && (
                <div className="py-8 text-center text-xs text-slate-500">
                  {text("暂无 Grafana dashboard", "No Grafana dashboards")}
                </div>
              )}
            </div>
          </Card>
        </div>

        <div className="grid grid-cols-[1.2fr_0.8fr] gap-4">
          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Logs className="h-4 w-4" /> {text("结构化日志", "Structured Logs")}
              </div>
              <span className="text-xs text-slate-500">
                {text("来源：", "Source: ")}{logs.data?.source ?? text("读取中", "loading")}
              </span>
            </CardHeader>
            <Table>
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <Th>{text("事件", "Event")}</Th>
                  <Th>{text("任务", "Task")}</Th>
                  <Th>Trace</Th>
                  <Th>{text("级别", "Level")}</Th>
                </tr>
              </thead>
              <tbody>
                {(logs.data?.items ?? []).map((item) => (
                  <tr key={`${item.task_id}-${item.event_type}-${item.timestamp}`} className="border-t border-slate-100">
                    <Td>{item.event_type ? eventLabel(item.event_type) : item.message}</Td>
                    <Td className="font-mono text-[11px] text-slate-600">
                      {item.task_id?.slice(0, 8) ?? "-"}
                    </Td>
                    <Td className="font-mono text-[11px] text-slate-600">
                      {item.trace_id?.slice(0, 12) ?? "-"}
                    </Td>
                    <Td>
                      <Badge tone={item.level === "ERROR" ? "failed" : "success"}>{item.level}</Badge>
                    </Td>
                  </tr>
                ))}
                {!logs.isLoading && (logs.data?.items.length ?? 0) === 0 && (
                  <tr className="border-t border-slate-100">
                    <Td colSpan={4} className="py-8 text-center text-slate-500">
                      {text("暂无结构化日志", "No structured logs")}
                    </Td>
                  </tr>
                )}
              </tbody>
            </Table>
          </Card>

          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <GitBranch className="h-4 w-4" /> {text("Trace 链路", "Trace Chain")}
              </div>
              <span className="font-mono text-xs text-slate-500">
                {firstTraceId?.slice(0, 16) ?? text("等待 trace", "Waiting for trace")}
              </span>
            </CardHeader>
            <div className="space-y-2 p-3">
              {(trace.data?.spans ?? []).map((span) => (
                <div key={span.span_id} className="rounded-md border border-slate-100 px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-xs text-slate-900">{eventLabel(span.name)}</span>
                    <span className="font-mono text-[10px] text-slate-500">{span.span_id}</span>
                  </div>
                  <div className="mt-1 text-[10px] text-slate-500">
                    {span.service} · {span.duration_ms}ms
                  </div>
                </div>
              ))}
              {!trace.isLoading && (trace.data?.spans.length ?? 0) === 0 && (
                <div className="py-8 text-center text-xs text-slate-500">
                  {text("暂无 Trace span", "No trace spans")}
                </div>
              )}
            </div>
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
  const { text } = useI18n();
  return (
    <Card>
      <CardHeader>
        <div className="text-[11px] tracking-widest text-slate-500">{title}</div>
      </CardHeader>
      <DistributionTable items={items} emptyText={text("暂无数据", "No data")} />
    </Card>
  );
}

function DistributionTable({ items, emptyText }: { items: CountItem[]; emptyText: string }) {
  const { text } = useI18n();
  return (
    <Table>
      <thead className="bg-slate-50 text-slate-500">
        <tr>
          <Th>{text("状态", "Status")}</Th>
          <Th className="text-right">{text("数量", "Count")}</Th>
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
  const { text } = useI18n();
  if (isLoading) {
    return (
      <div className="flex items-center gap-2 border-t border-slate-100 px-3 py-2 text-xs text-slate-500">
        <RefreshCw className="h-3 w-3 animate-spin" /> {text("正在读取后端观测数据", "Reading backend observability data")}
      </div>
    );
  }

  if (error) {
    return (
      <div className="border-t border-red-100 bg-red-50 px-3 py-2 text-xs text-red-700">
        {text("观测数据读取失败：", "Failed to read observability data: ")}{error.message}
      </div>
    );
  }

  return null;
}

function formatNumber(value: number | undefined) {
  return value === undefined ? "..." : new Intl.NumberFormat("zh-CN").format(value);
}
