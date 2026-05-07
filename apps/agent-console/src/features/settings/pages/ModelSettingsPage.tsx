import { useQuery } from "@tanstack/react-query";
import { Brain, GitBranch } from "lucide-react";
import { Link } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Card, CardHeader } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { useI18n } from "../../../lib/i18n";
import { statusLabel } from "../../../lib/labels";
import { formatShortDate } from "../../../lib/utils";
import { getModelFallbackSummary, getModelHealth, getModelSettings } from "../../tasks/api";

export function ModelSettingsPage() {
  const { text } = useI18n();
  const settings = useQuery({ queryKey: ["settings", "models"], queryFn: getModelSettings });
  const health = useQuery({ queryKey: ["settings", "models", "health"], queryFn: getModelHealth });
  const fallbacks = useQuery({
    queryKey: ["settings", "models", "fallbacks"],
    queryFn: () => getModelFallbackSummary(20),
  });
  const healthByProvider = new Map(
    (health.data?.items ?? []).map((item) => [`${item.provider}:${item.model}`, item]),
  );

  return (
    <ConsoleShell title={text("模型设置", "Model Settings")}>
      <div className="space-y-4 p-4">
        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Brain className="h-4 w-4" /> {text("模型网关", "Model Gateway")}
            </div>
            <span className="text-xs text-slate-500">{text("模型网关、供应商与限流状态", "Model gateway, providers, and rate limits")}</span>
          </CardHeader>
          <div className="grid grid-cols-3 gap-3 p-3 text-xs">
            <Metric label={text("默认供应商", "Default Provider")} value={settings.data?.default_provider ?? "..."} />
            <Metric label={text("默认模型", "Default Model")} value={settings.data?.default_model ?? "..."} />
            <Metric label={text("健康状态", "Health")} value={statusLabel(String(settings.data?.health.status ?? "..."))} />
            <Metric label="RPM 限流" value={formatLimit(settings.data?.rate_limits.rpm, "rpm")} />
            <Metric label="TPM 限流" value={formatLimit(settings.data?.rate_limits.tpm, "tpm")} />
            <Metric
              label={text("熔断规则", "Circuit Breaker")}
              value={`${String(settings.data?.circuit_breaker.failure_threshold ?? "...")} 次失败 / ${String(
                settings.data?.circuit_breaker.cooldown_seconds ?? "...",
              )} 秒`}
            />
            <Metric
              label="Fallback"
              value={String(fallbacks.data?.fallback_total ?? "...")}
            />
          </div>
        </Card>
        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <GitBranch className="h-4 w-4" /> {text("Fallback 策略观测", "Fallback Observability")}
            </div>
            <span className="text-xs text-slate-500">
              {text("展示主模型失败、fallback 供应商分布和最近切换事件", "Shows primary failures, fallback provider distribution, and recent switch events")}
            </span>
          </CardHeader>
          <div className="grid grid-cols-3 gap-3 p-3 text-xs">
            <Metric
              label={text("切换次数", "Fallbacks")}
              value={String(fallbacks.data?.fallback_total ?? "...")}
            />
            <Metric
              label={text("主模型失败", "Primary Failures")}
              value={String(fallbacks.data?.primary_failure_total ?? "...")}
            />
            <Metric
              label={text("供应商分布", "Providers")}
              value={(fallbacks.data?.providers ?? [])
                .map((item) => `${item.name}:${item.count}`)
                .join(" / ") || "..."}
            />
          </div>
          <Table>
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <Th>{text("主模型", "Primary")}</Th>
                <Th>Fallback</Th>
                <Th>{text("原因", "Reason")}</Th>
                <Th>Trace</Th>
                <Th>{text("时间", "Time")}</Th>
              </tr>
            </thead>
            <tbody>
              {(fallbacks.data?.recent_events ?? []).map((event) => (
                <tr key={event.event_id} className="border-t border-slate-100">
                  <Td className="font-mono">
                    {event.primary_provider ?? "-"} / {event.primary_model ?? "-"}
                  </Td>
                  <Td className="font-mono">
                    {event.fallback_provider} / {event.fallback_model}
                  </Td>
                  <Td className="max-w-64 truncate text-slate-500">{event.reason ?? "-"}</Td>
                  <Td>
                    {event.trace_id ? (
                      <Link
                        to={`/observability?trace_id=${encodeURIComponent(event.trace_id)}`}
                        className="font-mono text-slate-600 hover:text-slate-950"
                      >
                        {event.trace_id.slice(0, 8)}
                      </Link>
                    ) : (
                      "-"
                    )}
                  </Td>
                  <Td className="font-mono text-slate-500">{formatShortDate(event.created_at)}</Td>
                </tr>
              ))}
              {!fallbacks.isLoading && (fallbacks.data?.recent_events ?? []).length === 0 && (
                <tr>
                  <Td colSpan={5} className="py-8 text-center text-slate-500">
                    {text("暂无模型 fallback 事件", "No model fallback events")}
                  </Td>
                </tr>
              )}
            </tbody>
          </Table>
        </Card>
        <Card>
          <CardHeader>
            <div>
              <div className="text-[11px] tracking-widest text-slate-500">{text("供应商", "Providers")}</div>
              <div className="mt-1 text-xs text-slate-500">
                {text("展示限流、主动探测和供应商级熔断状态", "Shows rate limits, active probes, and provider circuit state")}
              </div>
            </div>
          </CardHeader>
          <Table>
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <Th>{text("名称", "Name")}</Th>
                <Th>{text("模型", "Model")}</Th>
                <Th>{text("状态", "Status")}</Th>
                <Th>{text("限流", "Rate Limit")}</Th>
                <Th>{text("探测", "Probe")}</Th>
                <Th>{text("熔断", "Circuit")}</Th>
                <Th>{text("失败", "Failures")}</Th>
              </tr>
            </thead>
            <tbody>
              {(settings.data?.providers ?? []).map((provider) => {
                const model = String(provider.model ?? settings.data?.default_model ?? "default");
                const item = healthByProvider.get(`${String(provider.name)}:${model}`);
                return (
                  <tr key={`${String(provider.name)}:${model}`} className="border-t border-slate-100">
                    <Td className="font-mono">{String(provider.name)}</Td>
                    <Td className="font-mono">{model}</Td>
                    <Td>{statusLabel(String(item?.status ?? provider.status))}</Td>
                    <Td>
                      <div>{formatLimit(provider.rate_limit_rpm ?? settings.data?.rate_limits.rpm, "rpm")}</div>
                      <div className="mt-1 text-slate-500">
                        {formatLimit(provider.rate_limit_tpm ?? settings.data?.rate_limits.tpm, "tpm")}
                      </div>
                    </Td>
                    <Td>
                      <div>{statusLabel(String(item?.mode ?? "configured"))}</div>
                      <div className="mt-1 text-slate-500">{formatLatency(item?.latency_ms)}</div>
                      {item?.checked_at ? (
                        <div className="mt-1 text-slate-500">{formatShortDate(item.checked_at)}</div>
                      ) : null}
                    </Td>
                    <Td>
                      <div>{statusLabel(String(item?.circuit_status ?? "closed"))}</div>
                      {item?.circuit_open_until ? (
                        <div className="mt-1 text-slate-500">{formatShortDate(item.circuit_open_until)}</div>
                      ) : null}
                    </Td>
                    <Td>
                      <div>{text(`${String(item?.consecutive_failures ?? 0)} 次`, `${String(item?.consecutive_failures ?? 0)} failures`)}</div>
                      {item?.error_message ? (
                        <div className="mt-1 max-w-56 truncate text-red-600">{item.error_message}</div>
                      ) : null}
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        </Card>
      </div>
    </ConsoleShell>
  );
}

function formatLimit(value: unknown, unit: string) {
  if (value === undefined || value === null || value === "") return `... ${unit}`;
  return `${Number(value).toLocaleString("zh-CN")} ${unit}`;
}

function formatLatency(value?: number) {
  if (value === undefined || value === null) return "... ms";
  return `${value.toLocaleString("zh-CN")} ms`;
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50 p-3">
      <div className="text-slate-500">{label}</div>
      <div className="mt-1 font-mono text-slate-900">{value}</div>
    </div>
  );
}
