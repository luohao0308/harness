import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  Box,
  Download,
  ExternalLink,
  Gauge,
  GitBranch,
  Logs,
  RefreshCw,
  RotateCcw,
} from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, Dot, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { Table, Td, Th } from "../../../components/ui/table";
import { useI18n } from "../../../lib/i18n";
import { enabledLabel, eventLabel, statusLabel } from "../../../lib/labels";
import { formatShortDate } from "../../../lib/utils";
import type {
  CountItem,
  ObservabilityExportHistoryItem,
  ObservabilityExportItem,
} from "../../tasks/api";
import {
  downloadObservabilityExport,
  getObservabilityServicesHealth,
  getObservabilitySummary,
  getObservabilityTrace,
  getSubagentRecoveryGlobalSummary,
  getSubagentRecoverySummary,
  listObservabilityExportHistory,
  listObservabilityExports,
  listGrafanaDashboards,
  listObservabilityLogs,
} from "../../tasks/api";

export function ObservabilityPage() {
  const { text } = useI18n();
  const [searchParams] = useSearchParams();
  const initialTraceId = searchParams.get("trace_id") ?? "";
  const initialLogFilters = {
    task_id: searchParams.get("task_id") ?? "",
    trace_id: initialTraceId,
    service: searchParams.get("service") ?? "",
    event_type: searchParams.get("event_type") ?? "",
  };
  const [draftLogFilters, setDraftLogFilters] = useState(initialLogFilters);
  const [logFilters, setLogFilters] = useState(draftLogFilters);
  const [draftTraceId, setDraftTraceId] = useState(initialTraceId);
  const [traceId, setTraceId] = useState(initialTraceId);
  const [draftTraceFilters, setDraftTraceFilters] = useState({
    service: "",
    span_name: "",
    attribute_key: "",
    attribute_value: "",
  });
  const [traceFilters, setTraceFilters] = useState(draftTraceFilters);
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
  const exports = useQuery({
    queryKey: ["observability", "exports"],
    queryFn: listObservabilityExports,
  });
  const exportHistory = useQuery({
    queryKey: ["observability", "exports", "history"],
    queryFn: listObservabilityExportHistory,
  });
  const recovery = useQuery({
    queryKey: ["subagents", "recovery-summary"],
    queryFn: getSubagentRecoverySummary,
  });
  const globalRecovery = useQuery({
    queryKey: ["subagents", "recovery-global-summary"],
    queryFn: () => getSubagentRecoveryGlobalSummary(100),
    retry: false,
  });
  const logs = useQuery({
    queryKey: ["observability", "logs", logFilters],
    queryFn: () =>
      listObservabilityLogs({
        task_id: cleanFilter(logFilters.task_id),
        trace_id: cleanFilter(logFilters.trace_id),
        service: cleanFilter(logFilters.service),
        event_type: cleanFilter(logFilters.event_type),
        limit: 20,
      }),
  });
  const firstTraceId = logs.data?.items.find((item) => item.trace_id)?.trace_id ?? "";
  const activeTraceId = traceId || firstTraceId;
  const [exportStatus, setExportStatus] = useState("");
  const trace = useQuery({
    queryKey: ["observability", "trace", activeTraceId, traceFilters],
    queryFn: () =>
      getObservabilityTrace(activeTraceId, {
        service: cleanFilter(traceFilters.service),
        span_name: cleanFilter(traceFilters.span_name),
        attribute_key: cleanFilter(traceFilters.attribute_key),
        attribute_value: cleanFilter(traceFilters.attribute_value),
      }),
    enabled: Boolean(activeTraceId),
  });
  const data = summary.data;
  const applyLogFilters = () => {
    setLogFilters(draftLogFilters);
    if (draftLogFilters.trace_id.trim()) {
      setTraceId(draftLogFilters.trace_id.trim());
      setDraftTraceId(draftLogFilters.trace_id.trim());
    }
  };
  const clearLogFilters = () => {
    const emptyFilters = { task_id: "", trace_id: "", service: "", event_type: "" };
    setDraftLogFilters(emptyFilters);
    setLogFilters(emptyFilters);
  };
  const queryTrace = (value = draftTraceId) => {
    const nextTraceId = value.trim();
    setDraftTraceId(nextTraceId);
    setTraceId(nextTraceId);
  };
  const exportPath = (item: ObservabilityExportItem) => {
    if (item.name === "logs_jsonl") {
      const searchParams = new URLSearchParams();
      for (const [key, value] of Object.entries(logFilters)) {
        const cleanValue = cleanFilter(value);
        if (cleanValue) {
          searchParams.set(key, cleanValue);
        }
      }
      searchParams.set("limit", "100");
      return `${item.url}?${searchParams.toString()}`;
    }
    if (item.name === "trace_json") {
      const searchParams = new URLSearchParams();
      for (const [key, value] of Object.entries(traceFilters)) {
        const cleanValue = cleanFilter(value);
        if (cleanValue) {
          searchParams.set(key, cleanValue);
        }
      }
      const suffix = searchParams.toString() ? `?${searchParams.toString()}` : "";
      return `${item.url.replace("{trace_id}", encodeURIComponent(activeTraceId))}${suffix}`;
    }
    return item.url;
  };
  const downloadExport = async (item: ObservabilityExportItem) => {
    if (item.name === "trace_json" && !activeTraceId) {
      setExportStatus(text("请先输入 Trace ID", "Enter a Trace ID first"));
      return;
    }
    setExportStatus(text("正在导出...", "Exporting..."));
    try {
      const { blob, filename } = await downloadObservabilityExport(exportPath(item));
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      window.URL.revokeObjectURL(url);
      setExportStatus(text(`已导出 ${filename}`, `Exported ${filename}`));
      void exportHistory.refetch();
    } catch (error) {
      setExportStatus(
        text(
          `导出失败：${error instanceof Error ? error.message : "未知错误"}`,
          `Export failed: ${error instanceof Error ? error.message : "unknown error"}`,
        ),
      );
    }
  };
  const downloadHistoryExport = async (path: string) => {
    setExportStatus(text("正在下载历史文件...", "Downloading retained file..."));
    try {
      const { blob, filename } = await downloadObservabilityExport(path);
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      window.URL.revokeObjectURL(url);
      setExportStatus(text(`已下载 ${filename}`, `Downloaded ${filename}`));
    } catch (error) {
      setExportStatus(
        text(
          `下载失败：${error instanceof Error ? error.message : "未知错误"}`,
          `Download failed: ${error instanceof Error ? error.message : "unknown error"}`,
        ),
      );
    }
  };
  const downloadGlobalRecoveryExport = async () => {
    setExportStatus(text("正在导出全局恢复摘要...", "Exporting global recovery summary..."));
    try {
      const { blob, filename } = await downloadObservabilityExport(
        "/api/subagents/recovery/global-summary/export",
      );
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      window.URL.revokeObjectURL(url);
      setExportStatus(text(`已导出 ${filename}`, `Exported ${filename}`));
    } catch (error) {
      setExportStatus(
        text(
          `导出失败：${error instanceof Error ? error.message : "未知错误"}`,
          `Export failed: ${error instanceof Error ? error.message : "unknown error"}`,
        ),
      );
    }
  };

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

        <div className="grid grid-cols-3 gap-4">
          <DistributionCard title={text("任务状态", "Task Status")} items={data?.tasks_by_status ?? []} />
          <DistributionCard title={text("子 Agent 状态", "Subagent Status")} items={data?.subagents_by_status ?? []} />
          <DistributionCard
            title={text("Agent Assignment 状态", "Agent Assignment Status")}
            items={data?.agent_assignments_by_status ?? []}
          />
          <DistributionCard title={text("模型调用状态", "Model Call Status")} items={data?.model_calls_by_status ?? []} />
          <DistributionCard title={text("工具调用状态", "Tool Call Status")} items={data?.tool_calls_by_status ?? []} />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <QueuePanel
            title={text("子 Agent 队列", "Subagent Queue")}
            subtitle={text("异步长任务派生状态", "Async long-running work state")}
            queue={data?.subagent_queue}
            showTimeout
          />
          <QueuePanel
            title={text("Agent Assignment 队列", "Agent Assignment Queue")}
            subtitle={text("多 Agent 编排 worker 状态", "Multi-agent orchestration worker state")}
            queue={data?.assignment_queue}
          />
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

        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Download className="h-4 w-4" /> {text("观测导出", "Observability Exports")}
            </div>
            <span className="text-xs text-slate-500">
              {exportStatus ||
                text("导出日志、Trace、Grafana dashboard 和服务健康快照", "Export logs, traces, dashboards, and health snapshots")}
            </span>
          </CardHeader>
          <div className="grid grid-cols-4 gap-3 p-3">
            {(exports.data?.items ?? []).map((item) => (
              <div key={item.name} className="rounded-md border border-slate-100 p-3 text-xs">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-semibold text-slate-900">{item.title}</div>
                    <div className="mt-1 text-slate-500">{item.description}</div>
                  </div>
                  <Badge tone="info">{item.format}</Badge>
                </div>
                <Button
                  className="mt-3 w-full"
                  disabled={item.name === "trace_json" && !activeTraceId}
                  onClick={() => void downloadExport(item)}
                >
                  <Download className="h-3 w-3" /> {text("导出", "Export")}
                </Button>
              </div>
            ))}
            {!exports.isLoading && (exports.data?.items.length ?? 0) === 0 && (
              <div className="col-span-4 py-8 text-center text-xs text-slate-500">
                {exports.error
                  ? text(
                      `导出入口读取受限：${exports.error.message}`,
                      `Export access limited: ${exports.error.message}`,
                    )
                  : text("暂无观测导出入口", "No observability exports")}
              </div>
            )}
          </div>
          <ExportHistoryTable
            items={exportHistory.data?.items ?? []}
            isLoading={exportHistory.isLoading}
            onDownload={downloadHistoryExport}
          />
        </Card>

        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <RotateCcw className="h-4 w-4" /> {text("子 Agent 恢复运营", "Subagent Recovery Operations")}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">
                {recovery.data?.latest_completed_at
                  ? text(
                      `最近完成 ${formatShortDate(recovery.data.latest_completed_at)}`,
                      `Latest ${formatShortDate(recovery.data.latest_completed_at)}`,
                    )
                  : text("等待恢复批次", "Waiting for recovery batches")}
              </span>
              <Button
                className="h-7 px-2"
                onClick={downloadGlobalRecoveryExport}
                disabled={!globalRecovery.data}
              >
                <Download className="h-3.5 w-3.5" /> {text("导出全局", "Export Global")}
              </Button>
            </div>
          </CardHeader>
          <div className="grid grid-cols-6 gap-3 border-b border-slate-100 p-3 text-xs">
            <Metric label={text("恢复批次", "Batches")} value={formatNumber(recovery.data?.batch_total)} />
            <Metric label={text("涉及任务", "Tasks")} value={formatNumber(recovery.data?.task_total)} />
            <Metric label={text("扫描子 Agent", "Scanned")} value={formatNumber(recovery.data?.scanned_total)} />
            <Metric label={text("恢复子 Agent", "Recovered")} value={formatNumber(recovery.data?.recovered_total)} />
            <Metric label={text("恢复锁跳过", "Lock Skips")} value={formatNumber(recovery.data?.lock_skipped_total)} />
            <Metric
              label={text("动作类型", "Actions")}
              value={formatNumber(Object.keys(recovery.data?.action_counts ?? {}).length)}
            />
          </div>
          <div className="grid grid-cols-[0.9fr_1.1fr] gap-4 border-b border-slate-100 p-3">
            <div className="grid grid-cols-3 gap-3 text-xs">
              <Metric
                label={text("全局组织", "Global Orgs")}
                value={formatNumber(globalRecovery.data?.organization_count)}
              />
              <Metric
                label={text("全局批次", "Global Batches")}
                value={formatNumber(globalRecovery.data?.batch_total)}
              />
              <Metric
                label={text("全局恢复", "Global Recovered")}
                value={formatNumber(globalRecovery.data?.recovered_total)}
              />
            </div>
            <div className="min-w-0">
              {globalRecovery.data ? (
                <div className="flex flex-wrap gap-1.5">
                  {globalRecovery.data.organizations.slice(0, 6).map((item) => (
                    <Badge key={item.organization_id ?? "none"} tone="purple">
                      <span className="font-mono">{item.organization_id ?? "unscoped"}</span>
                      <span className="font-mono">{item.recovered_total}</span>
                    </Badge>
                  ))}
                </div>
              ) : (
                <div className="rounded-md border border-slate-100 bg-slate-50 px-3 py-2 text-xs text-slate-500">
                  {globalRecovery.error
                    ? text(
                        `全局恢复摘要受限：${globalRecovery.error.message}`,
                        `Global recovery summary limited: ${globalRecovery.error.message}`,
                      )
                    : text("全局恢复摘要加载中", "Loading global recovery summary")}
                </div>
              )}
            </div>
          </div>
          <div className="grid grid-cols-[1.1fr_0.9fr] gap-4 p-3">
            <div className="overflow-hidden rounded-md border border-slate-100">
              <Table>
                <thead className="bg-slate-50 text-slate-500">
                  <tr>
                    <Th>{text("任务", "Task")}</Th>
                    <Th className="text-right">{text("扫描", "Scanned")}</Th>
                    <Th className="text-right">{text("恢复", "Recovered")}</Th>
                    <Th>{text("最近批次", "Latest Batch")}</Th>
                  </tr>
                </thead>
                <tbody>
                  {(recovery.data?.tasks ?? []).slice(0, 6).map((item) => (
                    <tr key={item.task_id} className="border-t border-slate-100">
                      <Td>
                        <Link
                          to={`/runs/${item.task_id}/subagents`}
                          className="font-mono text-slate-900 hover:text-slate-950"
                        >
                          {item.task_id.slice(0, 8)}
                        </Link>
                      </Td>
                      <Td className="text-right font-mono text-slate-600">{item.scanned_count}</Td>
                      <Td className="text-right font-mono text-slate-600">{item.recovered_count}</Td>
                      <Td className="text-slate-500">
                        <div className="font-mono text-[11px]">{item.latest_batch_id.slice(0, 13)}</div>
                        <div className="mt-0.5 text-[10px]">
                          Replay {item.latest_replay_sequence} · {formatShortDate(item.latest_completed_at)}
                        </div>
                      </Td>
                    </tr>
                  ))}
                  {!recovery.isLoading && (recovery.data?.tasks.length ?? 0) === 0 && (
                    <tr className="border-t border-slate-100">
                      <Td colSpan={4} className="py-8 text-center text-slate-500">
                        {text("暂无恢复任务汇总", "No recovery task summary")}
                      </Td>
                    </tr>
                  )}
                </tbody>
              </Table>
            </div>
            <div className="space-y-3">
              <div className="rounded-md border border-slate-100 p-3">
                <div className="mb-2 text-[11px] tracking-widest text-slate-500">
                  {text("恢复动作统计", "Recovery Action Counts")}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(recovery.data?.action_counts ?? {}).map(([action, count]) => (
                    <Badge key={action} tone="info">
                      {action} <span className="font-mono">{count}</span>
                    </Badge>
                  ))}
                  {Object.keys(recovery.data?.action_counts ?? {}).length === 0 && (
                    <span className="text-xs text-slate-500">{text("暂无动作", "No actions")}</span>
                  )}
                </div>
              </div>
              <div className="rounded-md border border-slate-100 p-3">
                <div className="mb-2 text-[11px] tracking-widest text-slate-500">
                  {text("最近批次", "Recent Batches")}
                </div>
                <div className="space-y-1.5">
                  {(recovery.data?.recent_batches ?? []).slice(0, 4).map((batch) => (
                    <div key={`${batch.batch_id}-${batch.task_id ?? "none"}`} className="flex items-center justify-between gap-3 text-xs">
                      <span className="min-w-0 truncate">
                        <span className="font-mono text-slate-700">{batch.batch_id.slice(0, 13)}</span>
                        <span className="ml-2 text-slate-500">
                          {batch.trigger === "auto" ? text("自动", "Auto") : text("手动", "Manual")} ·{" "}
                          {text(`恢复 ${batch.recovered_count}`, `Recovered ${batch.recovered_count}`)}
                        </span>
                      </span>
                      <span className="shrink-0 text-[10px] text-slate-400">
                        {formatShortDate(batch.completed_at)}
                      </span>
                    </div>
                  ))}
                  {!recovery.isLoading && (recovery.data?.recent_batches.length ?? 0) === 0 && (
                    <div className="py-4 text-center text-xs text-slate-500">
                      {text("暂无恢复批次", "No recovery batches")}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </Card>

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
                      {service.alert_status !== "ok" && (
                        <Badge
                          tone={service.alert_severity === "critical" ? "failed" : "warning"}
                          className="ml-1"
                        >
                          {text("告警", "Alert")} {service.alert_severity}
                        </Badge>
                      )}
                    </Td>
                    <Td className="text-right font-mono text-slate-600">
                      {service.latency_ms ?? "-"}ms
                    </Td>
                  </tr>
                ))}
                {!health.isLoading && (health.data?.services.length ?? 0) === 0 && (
                  <tr className="border-t border-slate-100">
                    <Td colSpan={3} className="py-8 text-center text-slate-500">
                      {health.error
                        ? text(
                            `服务健康读取受限：${health.error.message}`,
                            `Service health access limited: ${health.error.message}`,
                          )
                        : text("暂无服务健康数据", "No service health data")}
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
                  {dashboards.error
                    ? text(
                        `Grafana 访问受限：${dashboards.error.message}`,
                        `Grafana access limited: ${dashboards.error.message}`,
                      )
                    : text("暂无 Grafana dashboard", "No Grafana dashboards")}
              </div>
            )}
          </div>
        </Card>
        </div>

        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Logs className="h-4 w-4" /> {text("日志与 Trace 深链查询", "Logs & Trace Deep Search")}
            </div>
            <span className="text-xs text-slate-500">
              {text("按任务、Trace、服务和事件筛选；Trace ID 可直接联动右侧链路。", "Filter by task, trace, service, and event; trace IDs can drive the chain view.")}
            </span>
          </CardHeader>
          <div className="grid grid-cols-[1fr_1fr_1fr_1fr_auto_auto] gap-2 p-3">
            <Input
              aria-label={text("任务 ID", "Task ID")}
              className="h-8 text-xs"
              placeholder={text("任务 ID", "Task ID")}
              value={draftLogFilters.task_id}
              onChange={(event) =>
                setDraftLogFilters((filters) => ({ ...filters, task_id: event.target.value }))
              }
            />
            <Input
              aria-label={text("Trace ID", "Trace ID")}
              className="h-8 text-xs"
              placeholder="Trace ID"
              value={draftLogFilters.trace_id}
              onChange={(event) =>
                setDraftLogFilters((filters) => ({ ...filters, trace_id: event.target.value }))
              }
            />
            <Input
              aria-label={text("服务", "Service")}
              className="h-8 text-xs"
              placeholder={text("服务，例如 api-server", "Service, e.g. api-server")}
              value={draftLogFilters.service}
              onChange={(event) =>
                setDraftLogFilters((filters) => ({ ...filters, service: event.target.value }))
              }
            />
            <Input
              aria-label={text("事件类型", "Event Type")}
              className="h-8 text-xs"
              placeholder={text("事件类型，例如 TASK_STARTED", "Event type, e.g. TASK_STARTED")}
              value={draftLogFilters.event_type}
              onChange={(event) =>
                setDraftLogFilters((filters) => ({ ...filters, event_type: event.target.value }))
              }
            />
            <Button onClick={applyLogFilters}>{text("查询日志", "Search Logs")}</Button>
            <Button onClick={clearLogFilters} variant="ghost">{text("清空", "Clear")}</Button>
          </div>
          <div className="grid grid-cols-[1fr_auto] gap-2 border-t border-slate-100 p-3">
            <Input
              aria-label={text("Trace 查询", "Trace Search")}
              className="h-8 text-xs"
              placeholder={text("输入 Trace ID 查询链路", "Enter Trace ID to query chain")}
              value={draftTraceId}
              onChange={(event) => setDraftTraceId(event.target.value)}
            />
            <Button onClick={() => queryTrace()}>{text("查询 Trace", "Search Trace")}</Button>
          </div>
          <div className="grid grid-cols-[1fr_1fr_1fr_1fr_auto] gap-2 border-t border-slate-100 p-3">
            <Input
              aria-label={text("Trace 服务", "Trace Service")}
              className="h-8 text-xs"
              placeholder={text("服务", "Service")}
              value={draftTraceFilters.service}
              onChange={(event) =>
                setDraftTraceFilters((filters) => ({ ...filters, service: event.target.value }))
              }
            />
            <Input
              aria-label={text("Span 名称", "Span Name")}
              className="h-8 text-xs"
              placeholder={text("Span 名称", "Span name")}
              value={draftTraceFilters.span_name}
              onChange={(event) =>
                setDraftTraceFilters((filters) => ({ ...filters, span_name: event.target.value }))
              }
            />
            <Input
              aria-label={text("属性键", "Attribute Key")}
              className="h-8 text-xs"
              placeholder={text("属性键", "Attribute key")}
              value={draftTraceFilters.attribute_key}
              onChange={(event) =>
                setDraftTraceFilters((filters) => ({ ...filters, attribute_key: event.target.value }))
              }
            />
            <Input
              aria-label={text("属性值", "Attribute Value")}
              className="h-8 text-xs"
              placeholder={text("属性值", "Attribute value")}
              value={draftTraceFilters.attribute_value}
              onChange={(event) =>
                setDraftTraceFilters((filters) => ({ ...filters, attribute_value: event.target.value }))
              }
            />
            <Button onClick={() => setTraceFilters(draftTraceFilters)}>
              {text("筛选 Span", "Filter Spans")}
            </Button>
          </div>
        </Card>

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
            <div className="flex flex-wrap gap-1.5 border-b border-slate-100 px-3 pb-2 text-[10px]">
              {Object.entries(logs.data?.facets ?? {}).flatMap(([facet, items]) =>
                items.slice(0, 3).map((item) => (
                  <Badge key={`${facet}-${item.name}`} tone="info">
                    {text(logFacetLabel(facet), logFacetLabelEn(facet))} {statusLabel(item.name)}
                    <span className="font-mono">{item.count}</span>
                  </Badge>
                )),
              )}
              {Object.keys(logs.data?.facets ?? {}).length === 0 && (
                <span className="text-slate-500">
                  {text("等待日志聚合维度", "Waiting for log facets")}
                </span>
              )}
            </div>
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
                      {item.task_id ? (
                        <Link to={`/runs/${item.task_id}/events`} className="hover:text-slate-950">
                          {item.task_id.slice(0, 8)}
                        </Link>
                      ) : (
                        "-"
                      )}
                    </Td>
                    <Td className="font-mono text-[11px] text-slate-600">
                      {item.trace_id ? (
                        <button
                          className="hover:text-slate-950"
                          onClick={() => queryTrace(item.trace_id ?? "")}
                        >
                          {item.trace_id.slice(0, 12)}
                        </button>
                      ) : (
                        "-"
                      )}
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
                {activeTraceId ? activeTraceId.slice(0, 16) : text("等待 trace", "Waiting for trace")}
              </span>
            </CardHeader>
            <div className="space-y-2 p-3">
              {(trace.data?.service_nodes.length ?? 0) > 0 && (
                <div className="rounded-md border border-slate-100 bg-slate-50 p-2 text-[10px]">
                  <div className="mb-1 text-slate-500">
                    {text("跨服务视图", "Cross-service view")}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {(trace.data?.service_nodes ?? []).map((node) => (
                      <Badge key={node.service} tone={node.error_count > 0 ? "warning" : "success"}>
                        {node.service} <span className="font-mono">{node.span_count}</span>
                      </Badge>
                    ))}
                    {(trace.data?.service_edges ?? []).map((edge) => (
                      <Badge key={`${edge.source}-${edge.target}`} tone="purple">
                        {edge.source} → {edge.target}
                        <span className="font-mono">{edge.span_count}</span>
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
              {(trace.data?.spans ?? []).map((span) => (
                <div key={span.span_id} className="rounded-md border border-slate-100 px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-xs text-slate-900">{eventLabel(span.name)}</span>
                    <span className="font-mono text-[10px] text-slate-500">{span.span_id}</span>
                  </div>
                  <div className="mt-1 text-[10px] text-slate-500">
                    {span.service} · {span.duration_ms}ms
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {Object.entries(span.attributes)
                      .slice(0, 3)
                      .map(([key, value]) => (
                        <span
                          key={`${span.span_id}-${key}`}
                          className="max-w-full truncate rounded border border-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-500"
                        >
                          {key}: {String(value)}
                        </span>
                      ))}
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

function logFacetLabel(facet: string) {
  const labels: Record<string, string> = {
    service: "服务",
    event_type: "事件",
    level: "级别",
    source: "来源",
  };
  return labels[facet] ?? facet;
}

function logFacetLabelEn(facet: string) {
  const labels: Record<string, string> = {
    service: "Service",
    event_type: "Event",
    level: "Level",
    source: "Source",
  };
  return labels[facet] ?? facet;
}

function QueuePanel({
  title,
  subtitle,
  queue,
  showTimeout = false,
}: {
  title: string;
  subtitle: string;
  queue:
    | {
        pending: number;
        queued: number;
        running: number;
        success: number;
        failed: number;
        timeout: number;
        capacity: number;
        available_slots: number;
        utilization_percent: number;
      }
    | undefined;
  showTimeout?: boolean;
}) {
  const { text } = useI18n();
  return (
    <Card>
      <CardHeader>
        <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
          <GitBranch className="h-4 w-4" /> {title}
        </div>
        <span className="text-xs text-slate-500">{subtitle}</span>
      </CardHeader>
      <div className="grid grid-cols-[0.8fr_1.2fr] gap-4 p-3">
        <div className="grid grid-cols-2 gap-3 text-xs">
          <Metric label={text("等待", "Pending")} value={formatNumber(queue?.pending)} />
          <Metric label={text("已入队", "Queued")} value={formatNumber(queue?.queued)} />
          <Metric label={text("运行中", "Running")} value={formatNumber(queue?.running)} />
          <Metric label={text("剩余槽位", "Available")} value={formatNumber(queue?.available_slots)} />
        </div>
        <div className="rounded-md border border-slate-100 p-3 text-xs">
          <div className="mb-3 flex items-center justify-between text-slate-500">
            <span>{text("槽位使用率", "Slot utilization")}</span>
            <span className="font-mono text-slate-900">
              {formatNumber(queue?.utilization_percent)}%
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded bg-slate-100">
            <div
              className="h-full rounded bg-slate-900"
              style={{ width: `${queue?.utilization_percent ?? 0}%` }}
            />
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2">
            <QueueCount label={text("成功", "Success")} value={queue?.success} tone="success" />
            <QueueCount label={text("失败", "Failed")} value={queue?.failed} tone="failed" />
            <QueueCount
              label={showTimeout ? text("超时", "Timeout") : text("容量", "Capacity")}
              value={showTimeout ? queue?.timeout : queue?.capacity}
              tone="warning"
            />
          </div>
        </div>
      </div>
    </Card>
  );
}

function QueueCount({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | undefined;
  tone: "success" | "failed" | "warning";
}) {
  return (
    <div className="rounded border border-slate-100 px-2 py-1.5">
      <div className="mb-1 text-slate-500">{label}</div>
      <Badge tone={tone}>{formatNumber(value)}</Badge>
    </div>
  );
}

function ExportHistoryTable({
  items,
  isLoading,
  onDownload,
}: {
  items: ObservabilityExportHistoryItem[];
  isLoading: boolean;
  onDownload: (path: string) => void;
}) {
  const { text } = useI18n();
  return (
    <div className="border-t border-slate-100 p-3">
      <div className="mb-2 flex items-center justify-between text-xs">
        <span className="font-semibold text-slate-900">{text("导出历史", "Export History")}</span>
        <span className="text-slate-500">{text("已留存文件", "Retained files")}</span>
      </div>
      <Table>
        <thead className="bg-slate-50 text-slate-500">
          <tr>
            <Th>{text("文件", "File")}</Th>
            <Th>{text("类型", "Type")}</Th>
            <Th className="text-right">{text("行数", "Rows")}</Th>
            <Th>{text("时间", "Time")}</Th>
            <Th className="text-right">{text("操作", "Action")}</Th>
          </tr>
        </thead>
        <tbody>
          {items.slice(0, 5).map((item) => (
            <tr key={item.id} className="border-t border-slate-100">
              <Td>
                <div className="font-mono text-[11px] text-slate-900">{item.filename}</div>
                <div className="mt-0.5 text-[10px] text-slate-500">
                  {item.source} · {formatBytes(item.size_bytes)}
                </div>
              </Td>
              <Td>
                <Badge tone="info">{item.export_type}</Badge>
              </Td>
              <Td className="text-right font-mono text-slate-600">{item.row_count}</Td>
              <Td className="text-[11px] text-slate-500">{formatShortDate(item.created_at)}</Td>
              <Td className="text-right">
                <Button variant="ghost" onClick={() => onDownload(item.download_url)}>
                  <Download className="h-3 w-3" /> {text("下载", "Download")}
                </Button>
              </Td>
            </tr>
          ))}
          {!isLoading && items.length === 0 && (
            <tr className="border-t border-slate-100">
              <Td colSpan={5} className="py-6 text-center text-slate-500">
                {text("暂无导出历史", "No export history")}
              </Td>
            </tr>
          )}
        </tbody>
      </Table>
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

function formatBytes(value: number) {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function cleanFilter(value: string) {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}
