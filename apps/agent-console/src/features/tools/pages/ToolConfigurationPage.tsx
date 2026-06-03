import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  KeyRound,
  PlugZap,
  RotateCcw,
  Search,
  Settings2,
  ShieldCheck,
  Timer,
} from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, type BadgeTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { feedbackErrorMessage, notifyFeedback } from "../../../components/ui/feedback-toast";
import { Input, Textarea } from "../../../components/ui/input";
import { MenuSelect, type MenuSelectOption } from "../../../components/ui/menu-select";
import { cn } from "../../../lib/utils";
import {
  type CapabilityRuntimeConfig,
  type ToolExecuteResult,
  listAgents,
  listCapabilityRuntimeConfigs,
  testInvokeCapability,
  updateCapabilityRuntimeConfig,
} from "../../tasks/api";
import { mcpConfigHint, mcpGuideFor, mcpUseSummary } from "../lib/mcpDescriptions";

const BRAVE_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search";

export function ToolConfigurationPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [agentId, setAgentId] = useState("default");
  const [selectedAttachmentId, setSelectedAttachmentId] = useState("");
  const [transport, setTransport] = useState<"http" | "sse" | "stdio">("http");
  const [endpointUrl, setEndpointUrl] = useState("");
  const [command, setCommand] = useState("");
  const [argsText, setArgsText] = useState("");
  const [secretRef, setSecretRef] = useState("");
  const [secretValue, setSecretValue] = useState("");
  const [timeoutSeconds, setTimeoutSeconds] = useState("30");
  const [testQuery, setTestQuery] = useState("MCP 教程");

  const agentsQuery = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const configsQuery = useQuery({
    queryKey: ["capability-runtime-configs", agentId],
    queryFn: () => listCapabilityRuntimeConfigs(agentId),
  });
  const configs = configsQuery.data?.items ?? [];
  const selectedConfig = configs.find((item) => item.attachment_id === selectedAttachmentId) ?? configs[0] ?? null;

  const agentOptions = useMemo<MenuSelectOption[]>(
    () =>
      (agentsQuery.data?.items ?? []).map((agent) => ({
        value: agent.id,
        label: agent.name,
        description: agent.id,
      })),
    [agentsQuery.data?.items],
  );

  useEffect(() => {
    if (!selectedAttachmentId && configs[0]?.attachment_id) {
      setSelectedAttachmentId(configs[0].attachment_id);
    }
    if (selectedAttachmentId && !configs.some((item) => item.attachment_id === selectedAttachmentId)) {
      setSelectedAttachmentId(configs[0]?.attachment_id ?? "");
    }
  }, [configs, selectedAttachmentId]);

  useEffect(() => {
    if (!selectedConfig) return;
    const defaultEndpoint = selectedConfig.tool_name === "brave" ? BRAVE_SEARCH_ENDPOINT : "";
    setTransport(normalizeTransport(selectedConfig.transport));
    setEndpointUrl(selectedConfig.endpoint_url || defaultEndpoint);
    setCommand(selectedConfig.command || "");
    setArgsText((selectedConfig.args ?? []).join("\n"));
    setSecretRef(selectedConfig.secret_ref || defaultSecretRef(selectedConfig.agent_id, selectedConfig.tool_name));
    setSecretValue("");
    setTimeoutSeconds(String(selectedConfig.timeout_seconds || 30));
    setTestQuery(String(selectedConfig.test_input_json.query ?? "MCP 教程"));
  }, [selectedConfig]);

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!selectedConfig) throw new Error("请先选择一个已安装 MCP");
      return updateCapabilityRuntimeConfig({
        agent_id: agentId,
        tool_name: selectedConfig.tool_name,
        transport,
        endpoint_url: transport === "stdio" ? null : endpointUrl.trim(),
        command: transport === "stdio" ? command.trim() : null,
        args: argsText
          .split("\n")
          .map((item) => item.trim())
          .filter(Boolean),
        secret_ref: secretRef.trim() || null,
        secret_value: secretValue.trim() || null,
        timeout_seconds: Number(timeoutSeconds) || selectedConfig.timeout_seconds || 30,
      });
    },
    onSuccess: async (result) => {
      setSecretValue("");
      notifyFeedback({
        tone: result.configured ? "success" : "warning",
        title: result.configured ? "运行配置已保存" : "运行配置已保存但仍需补充",
        description: runtimeFeedback(result),
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["capability-runtime-configs"] }),
        queryClient.invalidateQueries({ queryKey: ["tool-registry"] }),
      ]);
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: "运行配置保存失败",
        description: feedbackErrorMessage(error, "请检查端点、密钥名称和必填项。"),
      });
    },
  });

  const testMutation = useMutation({
    mutationFn: () => {
      if (!selectedConfig) throw new Error("请先选择一个已安装 MCP");
      return testInvokeCapability({
        agent_id: agentId,
        tool_name: selectedConfig.tool_name,
        input_json: { query: testQuery.trim(), limit: 3 },
      });
    },
    onSuccess: (result) => {
      notifyFeedback({
        tone: result.allowed ? "success" : "warning",
        title: result.allowed ? "案例测试成功" : "案例测试已返回",
        description: `${result.tool_call.tool_name} · ${result.tool_call.duration_ms}ms`,
      });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: "案例测试失败",
        description: feedbackErrorMessage(error, "请先保存配置，再检查密钥和端点。"),
      });
    },
  });

  const configuredCount = configs.filter((item) => item.configured).length;
  const missingSecretCount = configs.filter((item) => item.secret_ref && !item.secret_configured).length;

  return (
    <ConsoleShell title="工具配置">
      <div className="space-y-4 p-4">
        <section className="grid gap-3 lg:grid-cols-[minmax(0,1.4fr)_minmax(320px,0.6fr)]">
          <Card className="p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="inline-flex items-center gap-2 text-base font-semibold text-slate-950">
                  <Settings2 className="h-5 w-5" />
                  MCP / 技能运行配置
                </div>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                  这里配置已经安装到智能体的 MCP。像 Brave Search 这类需要端点和 API Key 的工具，先保存运行配置，再用右侧案例测试确认结果来自真实供应商。
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="secondary" onClick={() => navigate("/tools")}>
                  <PlugZap className="h-3.5 w-3.5" />
                  返回工具商店
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => configsQuery.refetch()}
                  disabled={configsQuery.isFetching}
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  {configsQuery.isFetching ? "同步中" : "刷新状态"}
                </Button>
              </div>
            </div>
          </Card>
          <Card className="p-4">
            <label className="grid gap-1 text-xs">
              <span className="font-medium text-slate-600">当前智能体</span>
              <MenuSelect
                ariaLabel="运行配置目标智能体"
                value={agentId}
                onChange={(value) => {
                  setAgentId(value);
                  setSelectedAttachmentId("");
                }}
                options={agentOptions}
                placeholder="选择智能体"
                size="compact"
              />
            </label>
            <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
              <Metric label="已安装 MCP" value={configs.length} />
              <Metric label="已配置" value={configuredCount} />
              <Metric label="缺少密钥" value={missingSecretCount} tone={missingSecretCount ? "warning" : "success"} />
            </div>
          </Card>
        </section>

        <section className="grid gap-4 xl:grid-cols-[minmax(320px,0.42fr)_minmax(0,0.58fr)]">
          <Card className="overflow-hidden">
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <PlugZap className="h-4 w-4" />
                已安装 MCP
              </div>
              <Badge tone={configsQuery.isFetching ? "running" : "neutral"}>
                {configsQuery.isFetching ? "同步中" : `${configs.length} 个`}
              </Badge>
            </CardHeader>
            <div className="max-h-[68vh] overflow-auto bg-slate-50 p-2">
              {configs.map((config) => (
                <button
                  key={config.attachment_id}
                  type="button"
                  className={cn(
                    "mb-2 w-full rounded-md border bg-white p-3 text-left transition active:translate-y-px",
                    selectedConfig?.attachment_id === config.attachment_id
                      ? "border-slate-900 shadow-sm ring-2 ring-slate-100"
                      : "border-slate-200 hover:border-slate-400",
                  )}
                  onClick={() => setSelectedAttachmentId(config.attachment_id)}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate font-mono text-sm text-slate-950">{config.tool_name}</div>
                      <div className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">
                        {mcpUseSummary(runtimeGuideInput(config))}
                      </div>
                    </div>
                    <RuntimeStatusBadge config={config} />
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    <Badge tone="info">{transportLabel(config.transport)}</Badge>
                    <Badge tone={config.registry_visible ? "success" : "warning"}>
                      {config.registry_visible ? "注册表可见" : "注册表不可见"}
                    </Badge>
                    <Badge tone={config.secret_configured ? "success" : "neutral"}>
                      {config.secret_configured ? "密钥已保存" : "密钥未保存"}
                    </Badge>
                  </div>
                </button>
              ))}
              {!configsQuery.isLoading && configs.length === 0 ? (
                <div className="rounded-md border border-slate-200 bg-white p-4 text-sm leading-6 text-slate-600">
                  当前智能体还没有已安装 MCP。请先去工具商店安装，例如 Brave Search，然后回到这里配置端点和密钥。
                  <div className="mt-3">
                    <Button variant="primary" onClick={() => navigate("/tools")}>
                      <Search className="h-3.5 w-3.5" />
                      打开工具商店
                    </Button>
                  </div>
                </div>
              ) : null}
            </div>
          </Card>

          <Card className="self-start">
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Settings2 className="h-4 w-4" />
                运行配置表单
              </div>
              {selectedConfig ? <RuntimeStatusBadge config={selectedConfig} /> : <Badge tone="neutral">未选择</Badge>}
            </CardHeader>
            {selectedConfig ? (
              <div className="grid gap-4 p-4 text-xs">
                <div className="rounded-md border border-cyan-100 bg-cyan-50 p-3 leading-5 text-cyan-900">
                  <div className="font-semibold">新手提示</div>
                  <div className="mt-1">
                    端点决定 MCP 或供应商 API 调用到哪里；密钥名称是服务器端引用，API Key 只在保存时写入一次，不会在页面回显。
                  </div>
                </div>

                <RuntimePurposeGuide config={selectedConfig} />

                <div className="grid gap-3 md:grid-cols-2">
                  <label className="grid gap-1">
                    <span className="font-medium text-slate-600">工具名</span>
                    <Input value={selectedConfig.tool_name} readOnly className="font-mono" />
                  </label>
                  <label className="grid gap-1">
                    <span className="font-medium text-slate-600">传输方式</span>
                    <MenuSelect
                      ariaLabel="MCP 传输方式"
                      value={transport}
                      onChange={(value) => setTransport(normalizeTransport(value))}
                      options={[
                        { value: "http", label: "HTTP / 远程 API", description: "推荐 Brave、Exa 等远程服务" },
                        { value: "sse", label: "SSE / 远程 MCP", description: "长连接事件流 MCP 服务" },
                        { value: "stdio", label: "stdio / 本地命令", description: "本机命令启动 MCP 服务" },
                      ]}
                      size="compact"
                    />
                  </label>
                </div>

                {transport === "stdio" ? (
                  <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                    <label className="grid gap-1">
                      <span className="font-medium text-slate-600">启动命令</span>
                      <Input
                        aria-label="MCP stdio 启动命令"
                        value={command}
                        onChange={(event) => setCommand(event.target.value)}
                        placeholder="npx"
                      />
                    </label>
                    <label className="grid gap-1">
                      <span className="font-medium text-slate-600">命令参数（每行一个）</span>
                      <Textarea
                        aria-label="MCP stdio 参数"
                        value={argsText}
                        onChange={(event) => setArgsText(event.target.value)}
                        className="min-h-24 font-mono text-xs"
                        placeholder="@modelcontextprotocol/server-example"
                      />
                    </label>
                  </div>
                ) : (
                  <label className="grid gap-1">
                    <span className="font-medium text-slate-600">运行端点</span>
                    <Input
                      aria-label="MCP 运行端点"
                      value={endpointUrl}
                      onChange={(event) => setEndpointUrl(event.target.value)}
                      className="font-mono"
                      placeholder={BRAVE_SEARCH_ENDPOINT}
                    />
                    <span className="text-[11px] text-slate-500">
                      Brave Search 默认使用官方 Web Search API 端点；其他 MCP 可填写远程 MCP / SSE 地址。
                    </span>
                  </label>
                )}

                <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                  <label className="grid gap-1">
                    <span className="font-medium text-slate-600">密钥名称</span>
                    <Input
                      aria-label="MCP 密钥名称"
                      value={secretRef}
                      onChange={(event) => setSecretRef(event.target.value)}
                      className="font-mono"
                      placeholder={defaultSecretRef(agentId, selectedConfig.tool_name)}
                    />
                  </label>
                  <label className="grid gap-1">
                    <span className="font-medium text-slate-600">替换 API Key</span>
                    <Input
                      aria-label="MCP API Key"
                      type="password"
                      value={secretValue}
                      onChange={(event) => setSecretValue(event.target.value)}
                      placeholder={selectedConfig.secret_configured ? "留空表示保留已保存密钥" : "粘贴后保存，页面不会回显"}
                    />
                  </label>
                </div>

                <label className="grid gap-1 md:max-w-xs">
                  <span className="font-medium text-slate-600">超时秒数</span>
                  <Input
                    aria-label="MCP 超时秒数"
                    type="number"
                    min={1}
                    max={300}
                    value={timeoutSeconds}
                    onChange={(event) => setTimeoutSeconds(event.target.value)}
                  />
                </label>

                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="primary"
                    onClick={() => saveMutation.mutate()}
                    disabled={saveMutation.isPending || !canSaveRuntimeConfig(transport, endpointUrl, command)}
                  >
                    <ShieldCheck className="h-3.5 w-3.5" />
                    {saveMutation.isPending ? "保存中" : "保存运行配置"}
                  </Button>
                  <Button
                    type="button"
                    onClick={() => testMutation.mutate()}
                    disabled={testMutation.isPending || !testQuery.trim()}
                  >
                    <Timer className="h-3.5 w-3.5" />
                    {testMutation.isPending ? "测试中" : "运行案例测试"}
                  </Button>
                </div>

                {!selectedConfig.configured ? (
                  <div className="rounded-md border border-amber-100 bg-amber-50 p-3 leading-5 text-amber-800">
                    还缺少：{selectedConfig.missing_fields.map(runtimeMissingFieldLabel).join("、") || "运行配置"}。
                    保存后状态会更新为“已配置”或提示具体缺项。
                  </div>
                ) : null}

                <div className="grid gap-2 rounded-md border border-slate-200 bg-slate-50 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="inline-flex items-center gap-1.5 font-semibold text-slate-900">
                      <KeyRound className="h-3.5 w-3.5" />
                      保存状态
                    </div>
                    <Badge tone={selectedConfig.secret_configured ? "success" : "warning"}>
                      {selectedConfig.secret_configured ? "密钥已保存" : "密钥未保存"}
                    </Badge>
                  </div>
                  <div className="grid gap-1 font-mono text-[11px] text-slate-600">
                    <div>附件 {selectedConfig.attachment_id}</div>
                    <div>版本 {selectedConfig.capability_version_id}</div>
                    <div>配置哈希 {selectedConfig.capability_config_sha256.slice(0, 16)}</div>
                  </div>
                </div>

                <label className="grid gap-1">
                  <span className="font-medium text-slate-600">案例查询</span>
                  <Input
                    aria-label="MCP 案例查询"
                    value={testQuery}
                    onChange={(event) => setTestQuery(event.target.value)}
                  />
                </label>
                {testMutation.data ? <RuntimeTestResult result={testMutation.data} /> : null}
                {saveMutation.error instanceof Error ? (
                  <div className="rounded-md border border-red-100 bg-red-50 p-3 text-red-800">
                    {saveMutation.error.message}
                  </div>
                ) : null}
                {testMutation.error instanceof Error ? (
                  <div className="rounded-md border border-red-100 bg-red-50 p-3 text-red-800">
                    {testMutation.error.message}
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="p-4 text-sm text-slate-500">先选择一个已安装 MCP。</div>
            )}
          </Card>
        </section>
      </div>
    </ConsoleShell>
  );
}

function Metric({ label, value, tone = "neutral" }: { label: string; value: number; tone?: BadgeTone }) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50 p-2">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className={cn("mt-0.5 font-mono text-lg", tone === "warning" ? "text-amber-700" : "text-slate-950")}>
        {value}
      </div>
    </div>
  );
}

function RuntimeStatusBadge({ config }: { config: CapabilityRuntimeConfig }) {
  const status = runtimeConfigStatus(config);
  return <Badge tone={status.tone}>{status.label}</Badge>;
}

function RuntimePurposeGuide({ config }: { config: CapabilityRuntimeConfig }) {
  const guideInput = runtimeGuideInput(config);
  const guide = mcpGuideFor(guideInput);
  return (
    <div className="grid gap-2 rounded-md border border-slate-200 bg-slate-50 p-3 leading-5 text-slate-700">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-semibold text-slate-950">这个 MCP 是干嘛的</div>
        <Badge tone={config.configured ? "success" : "info"}>
          {config.configured ? "可测试" : "先补配置"}
        </Badge>
      </div>
      <div>{guide.summary}</div>
      <div className="grid gap-2 text-[11px] md:grid-cols-3">
        <div className="rounded border border-white bg-white/80 p-2">
          <div className="font-semibold text-slate-900">常见场景</div>
          <div className="mt-1 text-slate-600">{guide.scenarios.join(" / ")}</div>
        </div>
        <div className="rounded border border-white bg-white/80 p-2">
          <div className="font-semibold text-slate-900">配置要求</div>
          <div className="mt-1 text-slate-600">{mcpConfigHint(guideInput)}</div>
        </div>
        <div className="rounded border border-white bg-white/80 p-2">
          <div className="font-semibold text-slate-900">建议测试</div>
          <div className="mt-1 text-slate-600">{guide.testQuery}</div>
        </div>
      </div>
    </div>
  );
}

function RuntimeTestResult({ result }: { result: ToolExecuteResult }) {
  const outputResult = isRecord(result.output.result) ? result.output.result : null;
  const items = Array.isArray(outputResult?.items) ? outputResult.items : [];
  const source = String(outputResult?.source ?? "工具输出");
  return (
    <div className="grid gap-2 rounded-md border border-emerald-100 bg-emerald-50 p-3 text-xs text-emerald-900">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="inline-flex items-center gap-1.5 font-semibold">
          <CheckCircle2 className="h-3.5 w-3.5" />
          {toolCallStatusLabel(result.tool_call.status)} · {result.tool_call.duration_ms}ms
        </div>
        <Badge tone={source === "brave-search-api" ? "success" : "info"}>
          {source === "brave-search-api" ? "真实 Brave API" : source}
        </Badge>
      </div>
      {items.length ? (
        <div className="grid gap-2">
          {items.slice(0, 3).map((item, index) => {
            const row = isRecord(item) ? item : { title: String(item) };
            return (
              <div key={`${String(row.id ?? index)}-${index}`} className="rounded-md border border-emerald-100 bg-white/80 p-2">
                <div className="truncate font-medium text-emerald-950">
                  {String(row.title ?? row.id ?? `结果 ${index + 1}`)}
                </div>
                {row.url ? <div className="mt-0.5 truncate font-mono text-[11px] text-emerald-700">{String(row.url)}</div> : null}
                {row.snippet ? <div className="mt-1 line-clamp-2 text-emerald-700">{String(row.snippet)}</div> : null}
              </div>
            );
          })}
        </div>
      ) : (
        <pre className="max-h-40 overflow-auto rounded border border-emerald-100 bg-white/80 p-2 font-mono text-[10px]">
          {JSON.stringify(result.output, null, 2)}
        </pre>
      )}
    </div>
  );
}

function runtimeConfigStatus(config: CapabilityRuntimeConfig): { label: string; tone: BadgeTone } {
  if (config.configured) return { label: "已配置", tone: "success" };
  if (config.secret_ref && !config.secret_configured) return { label: "缺少密钥", tone: "warning" };
  if (config.missing_fields.length > 0) return { label: "未配置", tone: "neutral" };
  return { label: "待检查", tone: "info" };
}

function normalizeTransport(value: string): "http" | "sse" | "stdio" {
  return value === "sse" || value === "stdio" ? value : "http";
}

function transportLabel(value: string) {
  switch (value) {
    case "stdio":
      return "stdio 本地命令";
    case "sse":
      return "SSE 远程连接";
    case "http":
      return "HTTP 远程 API";
    default:
      return value;
  }
}

function runtimeMissingFieldLabel(value: string) {
  switch (value) {
    case "endpoint_url":
      return "运行端点";
    case "command":
      return "启动命令";
    case "secret_value":
      return "API Key";
    default:
      return value;
  }
}

function defaultSecretRef(agentId: string, toolName: string) {
  const clean = (value: string) =>
    value
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
  return `secret://mcp/${clean(agentId) || "agent"}/${clean(toolName) || "tool"}/api-key`;
}

function runtimeGuideInput(config: CapabilityRuntimeConfig) {
  return {
    name: config.tool_name,
    tool_name: config.tool_name,
    description: config.tool_description,
    tool_description: config.tool_description,
    kind: "mcp",
    source: config.source,
    transport: config.transport,
  };
}

function canSaveRuntimeConfig(transport: string, endpointUrl: string, command: string) {
  if (transport === "stdio") return command.trim().length > 0;
  return endpointUrl.trim().length > 0;
}

function runtimeFeedback(result: CapabilityRuntimeConfig) {
  if (result.configured) {
    return `${result.tool_name} 已保存到版本 ${result.capability_version_id}，现在可以运行案例测试。`;
  }
  return `${result.tool_name} 仍缺少：${result.missing_fields.map(runtimeMissingFieldLabel).join("、")}`;
}

function toolCallStatusLabel(status: string) {
  switch (status) {
    case "SUCCESS":
      return "成功";
    case "FAILED":
      return "失败";
    case "TIMEOUT":
      return "超时";
    default:
      return status;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
