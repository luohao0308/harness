import { useQuery } from "@tanstack/react-query";
import { Box, Gauge } from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Card, CardHeader } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { useI18n } from "../../../lib/i18n";
import { formatShortDate } from "../../../lib/utils";
import { getSandboxQuotaUsage, getWarmPool, listSandboxQuotaHistory } from "../../tasks/api";

export function SandboxesPage() {
  const { text } = useI18n();
  const warmPool = useQuery({ queryKey: ["warm-pool"], queryFn: getWarmPool });
  const quota = useQuery({ queryKey: ["sandbox-quota"], queryFn: getSandboxQuotaUsage });
  const history = useQuery({
    queryKey: ["sandbox-quota-history"],
    queryFn: () => listSandboxQuotaHistory(100),
  });

  return (
    <ConsoleShell title={text("沙箱", "Sandboxes")}>
      <div className="space-y-4 p-4">
        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Gauge className="h-4 w-4" /> {text("资源配额用量", "Resource Quota Usage")}
            </div>
            <span className="text-xs text-slate-500">
              {text("按当前组织聚合沙箱 CPU、内存、网络和 WarmPool 复用情况", "Aggregated sandbox CPU, memory, network, and WarmPool reuse")}
            </span>
          </CardHeader>
          <div className="grid grid-cols-4 gap-3 p-3 text-xs">
            <Metric
              label={text("沙箱总数", "Sandboxes")}
              value={String(quota.data?.sandbox_total ?? "...")}
            />
            <Metric
              label={text("运行中", "Running")}
              value={String(quota.data?.running_total ?? "...")}
            />
            <Metric
              label={text("运行内存", "Running Memory")}
              value={`${quota.data?.running_memory_limit_mb_total ?? "..."} MB`}
            />
            <Metric
              label={text("运行 CPU", "Running CPU")}
              value={formatCpu(quota.data?.running_cpu_limit_total)}
            />
            <Metric
              label={text("策略内存", "Policy Memory")}
              value={`${quota.data?.configured_memory_mb ?? "..."} MB`}
            />
            <Metric
              label={text("策略 CPU", "Policy CPU")}
              value={quota.data?.configured_cpus ?? "..."}
            />
            <Metric
              label={text("工作区配额", "Workspace Quota")}
              value={`${quota.data?.configured_workspace_quota_mb ?? "..."} MB`}
            />
            <Metric
              label={text("网络沙箱", "Network Enabled")}
              value={String(quota.data?.network_enabled_total ?? "...")}
            />
          </div>
        </Card>
        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Box className="h-4 w-4" /> WarmPool
            </div>
            <span className="text-xs text-slate-500">{text("Docker 容器沙箱预热池", "Docker container sandbox warm pool")}</span>
          </CardHeader>
          <div className="grid grid-cols-4 gap-3 p-3 text-xs">
            <Metric label={text("空闲", "Idle")} value={String(warmPool.data?.idle ?? "...")} />
            <Metric label={text("忙碌", "Busy")} value={String(warmPool.data?.busy ?? "...")} />
            <Metric label={text("失败", "Failed")} value={String(warmPool.data?.failed ?? "...")} />
            <Metric label={text("容量", "Capacity")} value={`${warmPool.data?.min_size ?? "..."} / ${warmPool.data?.max_size ?? "..."}`} />
          </div>
        </Card>
        <Card className="overflow-hidden">
          <CardHeader>
            <div className="text-sm font-semibold text-slate-900">
              {text("配额历史审计", "Quota History Audit")}
            </div>
            <span className="text-xs text-slate-500">
              {text("最近 100 条沙箱资源规格、生命周期和 WarmPool 复用记录", "Latest 100 sandbox resource, lifecycle, and WarmPool reuse records")}
            </span>
          </CardHeader>
          <Table>
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <Th>{text("沙箱", "Sandbox")}</Th>
                <Th>{text("状态", "Status")}</Th>
                <Th>{text("CPU", "CPU")}</Th>
                <Th>{text("内存", "Memory")}</Th>
                <Th>{text("网络", "Network")}</Th>
                <Th>WarmPool</Th>
                <Th>{text("生命周期", "Lifetime")}</Th>
                <Th>{text("创建时间", "Created")}</Th>
              </tr>
            </thead>
            <tbody>
              {(history.data?.items ?? []).map((item) => (
                <tr key={item.id} className="border-t border-slate-100">
                  <Td className="font-mono">{item.id.slice(0, 8)}</Td>
                  <Td>{item.status}</Td>
                  <Td className="font-mono">{item.cpu_limit}</Td>
                  <Td className="font-mono">{item.memory_limit_mb} MB</Td>
                  <Td>{item.network_enabled ? text("已启用", "Enabled") : text("关闭", "Disabled")}</Td>
                  <Td>{item.warm_pool_reused ? text("复用", "Reused") : text("冷启动", "Cold start")}</Td>
                  <Td>{formatLifetime(item.lifetime_seconds)}</Td>
                  <Td className="font-mono text-slate-500">{formatShortDate(item.created_at)}</Td>
                </tr>
              ))}
              {!history.isLoading && (history.data?.items ?? []).length === 0 && (
                <tr>
                  <Td colSpan={8} className="py-10 text-center text-slate-500">
                    {text("暂无沙箱配额审计记录", "No sandbox quota audit records")}
                  </Td>
                </tr>
              )}
            </tbody>
          </Table>
        </Card>
      </div>
    </ConsoleShell>
  );
}

function formatCpu(value?: number) {
  if (value === undefined || value === null) return "...";
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 3 });
}

function formatLifetime(value: number | null) {
  if (value === null) return "-";
  return `${value.toLocaleString("zh-CN")}s`;
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50 p-3">
      <div className="text-slate-500">{label}</div>
      <div className="mt-1 font-mono text-slate-900">{value}</div>
    </div>
  );
}
