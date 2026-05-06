import { useQuery } from "@tanstack/react-query";
import { Brain } from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Card, CardHeader } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { statusLabel } from "../../../lib/labels";
import { formatShortDate } from "../../../lib/utils";
import { getModelHealth, getModelSettings } from "../../tasks/api";

export function ModelSettingsPage() {
  const settings = useQuery({ queryKey: ["settings", "models"], queryFn: getModelSettings });
  const health = useQuery({ queryKey: ["settings", "models", "health"], queryFn: getModelHealth });
  const healthByProvider = new Map(
    (health.data?.items ?? []).map((item) => [`${item.provider}:${item.model}`, item]),
  );

  return (
    <ConsoleShell title="模型设置">
      <div className="space-y-4 p-4">
        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Brain className="h-4 w-4" /> 模型网关
            </div>
            <span className="text-xs text-slate-500">模型网关、供应商与限流状态</span>
          </CardHeader>
          <div className="grid grid-cols-3 gap-3 p-3 text-xs">
            <Metric label="默认供应商" value={settings.data?.default_provider ?? "..."} />
            <Metric label="默认模型" value={settings.data?.default_model ?? "..."} />
            <Metric label="健康状态" value={statusLabel(String(settings.data?.health.status ?? "..."))} />
            <Metric label="RPM 限流" value={formatLimit(settings.data?.rate_limits.rpm, "rpm")} />
            <Metric label="TPM 限流" value={formatLimit(settings.data?.rate_limits.tpm, "tpm")} />
            <Metric
              label="熔断规则"
              value={`${String(settings.data?.circuit_breaker.failure_threshold ?? "...")} 次失败 / ${String(
                settings.data?.circuit_breaker.cooldown_seconds ?? "...",
              )} 秒`}
            />
          </div>
        </Card>
        <Card>
          <CardHeader>
            <div>
              <div className="text-[11px] tracking-widest text-slate-500">供应商</div>
              <div className="mt-1 text-xs text-slate-500">
                展示限流、主动探测和供应商级熔断状态
              </div>
            </div>
          </CardHeader>
          <Table>
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <Th>名称</Th>
                <Th>模型</Th>
                <Th>状态</Th>
                <Th>限流</Th>
                <Th>探测</Th>
                <Th>熔断</Th>
                <Th>失败</Th>
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
                      <div>{String(item?.consecutive_failures ?? 0)} 次</div>
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
