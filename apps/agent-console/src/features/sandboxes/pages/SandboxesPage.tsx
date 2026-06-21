import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Box, Copy, Gauge, Globe2, KeyRound, Play, ShieldCheck, Tags, Trash2 } from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { feedbackErrorMessage, notifyFeedback } from "../../../components/ui/feedback-toast";
import { Input } from "../../../components/ui/input";
import { Table, Td, Th } from "../../../components/ui/table";
import { TermHint } from "../../../components/ui/term";
import { useI18n } from "../../../lib/i18n";
import { formatShortDate } from "../../../lib/utils";
import {
  createAgentGatewayRoute,
  deleteAgentGatewayRoute,
  getSandboxQuotaUsage,
  getWarmPool,
  listAgentGatewayRoutes,
  listSandboxQuotaHistory,
  listWarmPoolBenchmarks,
  runWarmPoolBenchmark,
  updateAgentGatewayRoute,
} from "../../tasks/api";

export function SandboxesPage() {
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const agentId = "default";
  const [gatewaySlug, setGatewaySlug] = useState("");
  const [gatewayDescription, setGatewayDescription] = useState("");
  const [gatewayRateLimit, setGatewayRateLimit] = useState("60");
  const [gatewayApiKey, setGatewayApiKey] = useState<string | null>(null);
  const gatewayRoutes = useQuery({
    queryKey: ["agent-gateway-routes", agentId],
    queryFn: () => listAgentGatewayRoutes(agentId),
  });
  const warmPool = useQuery({ queryKey: ["warm-pool"], queryFn: getWarmPool });
  const quota = useQuery({ queryKey: ["sandbox-quota"], queryFn: getSandboxQuotaUsage });
  const history = useQuery({
    queryKey: ["sandbox-quota-history"],
    queryFn: () => listSandboxQuotaHistory(100),
  });
  const benchmarks = useQuery({
    queryKey: ["warm-pool-benchmarks"],
    queryFn: () => listWarmPoolBenchmarks(20),
  });
  const runBenchmark = useMutation({
    mutationFn: () => runWarmPoolBenchmark(),
    onSuccess: async () => {
      notifyFeedback({
        tone: "success",
        title: text("基准测试已启动", "Benchmark started"),
        description: text("WarmPool 基准结果会在当前页自动刷新。", "WarmPool benchmark results will refresh on this page."),
      });
      await queryClient.invalidateQueries({ queryKey: ["warm-pool-benchmarks"] });
      await queryClient.invalidateQueries({ queryKey: ["warm-pool"] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("基准测试启动失败", "Benchmark start failed"),
        description: feedbackErrorMessage(error, text("请检查沙箱服务状态或稍后重试。", "Check the sandbox service and retry.")),
      });
    },
  });
  const createGatewayRoute = useMutation({
    mutationFn: () =>
      createAgentGatewayRoute(agentId, {
        slug: gatewaySlug.trim(),
        description: gatewayDescription.trim(),
        rate_limit: Number(gatewayRateLimit) || 60,
        enabled: true,
      }),
    onSuccess: async (result) => {
      setGatewaySlug("");
      setGatewayDescription("");
      setGatewayRateLimit("60");
      setGatewayApiKey(result.api_key);
      notifyFeedback({
        tone: "success",
        title: text("发布路由已创建", "Gateway route created"),
        description: text("API Key 只会显示一次，请立即保存。", "The API key is shown once. Store it now."),
      });
      await queryClient.invalidateQueries({ queryKey: ["agent-gateway-routes", agentId] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("发布路由创建失败", "Gateway route creation failed"),
        description: feedbackErrorMessage(error, text("请检查 slug 是否重复或格式是否正确。", "Check whether the slug is duplicated or invalid.")),
      });
    },
  });
  const updateGatewayRoute = useMutation({
    mutationFn: (payload: { routeId: string; enabled: boolean }) =>
      updateAgentGatewayRoute(agentId, payload.routeId, { enabled: payload.enabled }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["agent-gateway-routes", agentId] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("发布路由更新失败", "Gateway route update failed"),
        description: feedbackErrorMessage(error, text("请稍后重试。", "Retry later.")),
      });
    },
  });
  const deleteGatewayRoute = useMutation({
    mutationFn: (routeId: string) => deleteAgentGatewayRoute(agentId, routeId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["agent-gateway-routes", agentId] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("发布路由删除失败", "Gateway route deletion failed"),
        description: feedbackErrorMessage(error, text("需要删除权限或稍后重试。", "Deletion permission is required, or retry later.")),
      });
    },
  });
  const latestBenchmark = runBenchmark.data ?? benchmarks.data?.items[0] ?? null;

  return (
    <ConsoleShell title={text("沙箱", "Sandboxes")}>
      <div className="space-y-4 p-4">
        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Gauge className="h-4 w-4" /> {text("资源配额用量", "Resource Quota Usage")}
            </div>
            <span className="text-xs text-slate-500">
              {text("按当前组织聚合沙箱算力、内存、网络和预热池复用情况", "Aggregated sandbox CPU, memory, network, and WarmPool reuse")}
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
              label={
                <>
                  {text("运行 ", "Running ")}
                  <TermHint description="中央处理器">CPU</TermHint>
                </>
              }
              value={formatCpu(quota.data?.running_cpu_limit_total)}
            />
            <Metric
              label={text("策略内存", "Policy Memory")}
              value={`${quota.data?.configured_memory_mb ?? "..."} MB`}
            />
            <Metric
              label={
                <>
                  {text("策略 ", "Policy ")}
                  <TermHint description="中央处理器">CPU</TermHint>
                </>
              }
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
        <section className="grid grid-cols-4 gap-3">
          <InfraTile
            icon={<ShieldCheck className="h-4 w-4" />}
            title={text("多租户隔离", "Tenant Isolation")}
            status={quota.data?.organization_id ? "接口已接入" : "加载中"}
            description={text("沙箱、运行、评测与观测查询按组织标识聚合和隔离。", "Sandbox, Run, Eval, and observability queries are scoped by organization_id.")}
          />
          <InfraTile
            icon={<Box className="h-4 w-4" />}
            title={<TermHint description="沙箱预热池，减少冷启动等待">WarmPool</TermHint>}
            status={`${warmPool.data?.min_size ?? "..."} / ${warmPool.data?.max_size ?? "..."}`}
            description={text("默认预热下限 2、上限 5，目标启动耗时小于 50ms。", "Default min_ready=2 and max_ready=5, with startup target below 50ms.")}
          />
          <InfraTile
            icon={<Globe2 className="h-4 w-4" />}
            title={<TermHint description="应用程序接口">API 网关</TermHint>}
            status={text("接口已接入", "API-backed")}
            description={text("将 Agent 发布为外部 HTTP API，用独立 API Key 调用并进入 Run 审计链路。", "Publish Agents as external HTTP APIs with scoped API keys and Run audit evidence.")}
          />
          <InfraTile
            icon={<Tags className="h-4 w-4" />}
            title={text("版本灰度", "Version Rollout")}
            status={text("未启用", "Disabled")}
            description={text("版本与灰度发布状态保留禁用态，不展示伪造发布数据。", "Version and rollout state stays disabled and shows no fake release data.")}
            disabled
          />
        </section>
        <Card className="overflow-hidden">
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Globe2 className="h-4 w-4" />
              <TermHint description="应用程序接口">API 网关</TermHint>
            </div>
            <span className="text-xs text-slate-500">
              {text("对外发布 default Agent，并用 X-Harness-Gateway-Key 调用。", "Publish the default Agent and invoke with X-Harness-Gateway-Key.")}
            </span>
          </CardHeader>
          <div className="space-y-3 p-3">
            <div className="grid grid-cols-[1fr_1.5fr_120px_auto] gap-2">
              <label className="sr-only" htmlFor="gateway-slug">
                {text("路由 slug", "Route slug")}
              </label>
              <Input
                id="gateway-slug"
                value={gatewaySlug}
                onChange={(event) => setGatewaySlug(event.target.value)}
                placeholder={text("release-review", "release-review")}
                aria-label={text("路由 slug", "Route slug")}
              />
              <label className="sr-only" htmlFor="gateway-description">
                {text("路由描述", "Route description")}
              </label>
              <Input
                id="gateway-description"
                value={gatewayDescription}
                onChange={(event) => setGatewayDescription(event.target.value)}
                placeholder={text("发布用途", "Route purpose")}
                aria-label={text("路由描述", "Route description")}
              />
              <label className="sr-only" htmlFor="gateway-rate-limit">
                {text("每分钟限制", "Rate limit")}
              </label>
              <Input
                id="gateway-rate-limit"
                type="number"
                min={1}
                max={600}
                value={gatewayRateLimit}
                onChange={(event) => setGatewayRateLimit(event.target.value)}
                aria-label={text("每分钟限制", "Rate limit")}
              />
              <Button
                onClick={() => createGatewayRoute.mutate()}
                disabled={createGatewayRoute.isPending}
                className="gap-1.5"
              >
                <KeyRound className="h-3.5 w-3.5" />
                {text("创建发布", "Create Route")}
              </Button>
            </div>
            {gatewayApiKey && (
              <div className="flex items-center justify-between gap-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                <span className="truncate font-mono">{gatewayApiKey}</span>
                <Button
                  variant="ghost"
                  onClick={() => navigator.clipboard?.writeText(gatewayApiKey)}
                  className="h-7 shrink-0 gap-1"
                >
                  <Copy className="h-3.5 w-3.5" />
                  {text("复制", "Copy")}
                </Button>
              </div>
            )}
          </div>
          <Table>
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <Th>{text("Slug", "Slug")}</Th>
                <Th>{text("调用地址", "Invoke URL")}</Th>
                <Th>{text("限制", "Limit")}</Th>
                <Th>{text("状态", "Status")}</Th>
                <Th>{text("最近调用", "Last Invoke")}</Th>
                <Th>{text("操作", "Actions")}</Th>
              </tr>
            </thead>
            <tbody>
              {(gatewayRoutes.data?.items ?? []).map((route) => (
                <tr key={route.id} className="border-t border-slate-100">
                  <Td>
                    <div className="font-mono text-slate-900">{route.slug}</div>
                    {route.description && (
                      <div className="mt-1 max-w-64 truncate text-xs text-slate-500">
                        {route.description}
                      </div>
                    )}
                  </Td>
                  <Td className="font-mono text-xs text-slate-600">
                    {gatewayInvokeUrl(route.slug)}
                  </Td>
                  <Td className="font-mono">{route.rate_limit}/min</Td>
                  <Td>
                    <Badge tone={route.enabled ? "success" : "neutral"}>
                      {route.enabled ? text("已启用", "Enabled") : text("关闭", "Disabled")}
                    </Badge>
                  </Td>
                  <Td className="font-mono text-slate-500">
                    {route.last_invoked_at ? formatShortDate(route.last_invoked_at) : "-"}
                  </Td>
                  <Td>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="ghost"
                        onClick={() =>
                          updateGatewayRoute.mutate({
                            routeId: route.id,
                            enabled: !route.enabled,
                          })
                        }
                        disabled={updateGatewayRoute.isPending}
                      >
                        {route.enabled ? text("停用", "Disable") : text("启用", "Enable")}
                      </Button>
                      <Button
                        variant="danger"
                        onClick={() => deleteGatewayRoute.mutate(route.id)}
                        disabled={deleteGatewayRoute.isPending}
                        aria-label={text("删除发布路由", "Delete gateway route")}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </Td>
                </tr>
              ))}
              {!gatewayRoutes.isLoading && (gatewayRoutes.data?.items ?? []).length === 0 && (
                <tr>
                  <Td colSpan={6} className="py-10 text-center text-slate-500">
                    {text("暂无 API Gateway 发布路由", "No API Gateway routes")}
                  </Td>
                </tr>
              )}
            </tbody>
          </Table>
        </Card>
        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Box className="h-4 w-4" />
              <TermHint description="沙箱预热池，减少冷启动等待">WarmPool</TermHint>
            </div>
            <span className="text-xs text-slate-500">{text("容器沙箱预热池", "Docker container sandbox warm pool")}</span>
          </CardHeader>
          <div className="grid grid-cols-4 gap-3 p-3 text-xs">
            <Metric label={text("空闲", "Idle")} value={String(warmPool.data?.idle ?? "...")} />
            <Metric label={text("忙碌", "Busy")} value={String(warmPool.data?.busy ?? "...")} />
            <Metric label={text("失败", "Failed")} value={String(warmPool.data?.failed ?? "...")} />
            <Metric label={text("容量", "Capacity")} value={`${warmPool.data?.min_size ?? "..."} / ${warmPool.data?.max_size ?? "..."}`} />
            <Metric label={text("命中", "Hits")} value={String(warmPool.data?.hit_total ?? "...")} />
            <Metric label={text("未命中", "Misses")} value={String(warmPool.data?.miss_total ?? "...")} />
            <Metric label={text("命中率", "Hit Rate")} value={hitRate(warmPool.data?.hit_total, warmPool.data?.miss_total)} />
            <Metric label={text("目标", "Target")} value="<50ms" />
          </div>
        </Card>
        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Gauge className="h-4 w-4" />
              <TermHint description="沙箱预热池，减少冷启动等待">WarmPool</TermHint>
              基准测试
            </div>
            <div className="flex items-center gap-2">
              {latestBenchmark && (
                <Badge tone={statusTone(latestBenchmark.status)}>{latestBenchmark.status}</Badge>
              )}
              <Button
                onClick={() => runBenchmark.mutate()}
                disabled={runBenchmark.isPending}
                className="h-8 gap-1.5"
              >
                <Play className="h-3.5 w-3.5" />
                {text("运行基准测试", "Run Benchmark")}
              </Button>
            </div>
          </CardHeader>
          <div className="grid grid-cols-5 gap-3 p-3 text-xs">
            <Metric label="预热平均" value={formatMs(latestBenchmark?.warm_avg_ms)} />
            <Metric label="预热 p95" value={formatMs(latestBenchmark?.warm_p95_ms)} />
            <Metric label="冷启动平均" value={formatMs(latestBenchmark?.cold_avg_ms)} />
            <Metric label="命中率" value={latestBenchmark ? `${latestBenchmark.hit_rate}%` : "..."} />
            <Metric label="迭代次数" value={String(latestBenchmark?.iteration_count ?? "...")} />
          </div>
        </Card>
        <Card className="overflow-hidden">
          <CardHeader>
            <div className="text-sm font-semibold text-slate-900">
              {text("配额历史审计", "Quota History Audit")}
            </div>
            <span className="text-xs text-slate-500">
              {text("最近 100 条沙箱资源规格、生命周期和预热池复用记录", "Latest 100 sandbox resource, lifecycle, and WarmPool reuse records")}
            </span>
          </CardHeader>
          <Table>
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <Th>{text("沙箱", "Sandbox")}</Th>
                <Th>{text("状态", "Status")}</Th>
                <Th>
                  <TermHint description="中央处理器">CPU</TermHint>
                </Th>
                <Th>{text("内存", "Memory")}</Th>
                <Th>{text("网络", "Network")}</Th>
                <Th>
                  <TermHint description="沙箱预热池，减少冷启动等待">WarmPool</TermHint>
                </Th>
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

function InfraTile({
  icon,
  title,
  status,
  description,
  disabled = false,
}: {
  icon: React.ReactNode;
  title: React.ReactNode;
  status: string;
  description: string;
  disabled?: boolean;
}) {
  return (
    <Card className={disabled ? "p-3 opacity-60" : "p-3"}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          {icon}
          {title}
        </div>
        <Badge tone={disabled ? "neutral" : "success"}>{status}</Badge>
      </div>
      <p className="mt-2 min-h-12 text-xs leading-5 text-slate-500">{description}</p>
    </Card>
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

function formatMs(value?: number | null) {
  if (value === undefined || value === null) return "...";
  return `${value.toLocaleString("zh-CN")}ms`;
}

function hitRate(hit?: number, miss?: number) {
  if (hit === undefined || miss === undefined) return "...";
  const total = hit + miss;
  if (total === 0) return "0%";
  return `${Math.round((hit / total) * 100)}%`;
}

function gatewayInvokeUrl(slug: string) {
  if (typeof window === "undefined") {
    return `/api/gateway/${slug}/invoke`;
  }
  return `${window.location.origin}/api/gateway/${slug}/invoke`;
}

function Metric({ label, value }: { label: React.ReactNode; value: string }) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50 p-3">
      <div className="text-slate-500">{label}</div>
      <div className="mt-1 font-mono text-slate-900">{value}</div>
    </div>
  );
}
