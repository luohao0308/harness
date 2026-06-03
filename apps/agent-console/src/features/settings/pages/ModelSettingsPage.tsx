import { FormEvent, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Brain, Check, GitBranch, Plus, Save, Star, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { MenuSelect } from "../../../components/ui/menu-select";
import { Table, Td, Th } from "../../../components/ui/table";
import { TermHint } from "../../../components/ui/term";
import { useI18n } from "../../../lib/i18n";
import { statusLabel } from "../../../lib/labels";
import { formatShortDate } from "../../../lib/utils";
import {
  getModelFallbackSummary,
  getModelHealth,
  getModelSettings,
  updateModelSettings,
  type ModelSettings,
} from "../../tasks/api";

type ProviderConfig = {
  name: string;
  label?: string;
  model?: string;
  status?: string;
  api_format?: string;
  base_url?: string;
  api_key?: string;
  api_key_env?: string;
  model_context_window_tokens?: number;
  rate_limit_rpm?: number;
  rate_limit_tpm?: number;
  timeout_seconds?: number;
  health_timeout_seconds?: number;
  circuit_breaker?: {
    failure_threshold?: number;
    cooldown_seconds?: number;
  };
  [key: string]: unknown;
};

const deepSeekPresetBase: Omit<ProviderConfig, "name" | "label" | "model"> = {
  api_format: "openai",
  base_url: "https://api.deepseek.com",
  api_key: "",
  api_key_env: "DEEPSEEK_API_KEY",
  model_context_window_tokens: 1000000,
  max_output_tokens: 384000,
  rate_limit_rpm: 300,
  rate_limit_tpm: 1000000,
  timeout_seconds: 60,
  health_timeout_seconds: 5,
};

const providerPresets: ProviderConfig[] = [
  {
    ...deepSeekPresetBase,
    name: "deepseek-flash",
    label: "DeepSeek Flash",
    model: "deepseek-v4-flash",
  },
  {
    ...deepSeekPresetBase,
    name: "deepseek-pro",
    label: "DeepSeek Pro",
    model: "deepseek-v4-pro",
  },
  {
    name: "openai-compatible",
    label: "OpenAI 兼容",
    model: "gpt-4.1-mini",
    api_format: "openai",
    base_url: "https://api.openai.com/v1",
    api_key: "",
    rate_limit_rpm: 600,
    rate_limit_tpm: 120000,
    timeout_seconds: 30,
    health_timeout_seconds: 5,
  },
  {
    name: "qwen",
    label: "Qwen DashScope 兼容",
    model: "qwen-plus",
    api_format: "openai",
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    api_key: "",
    rate_limit_rpm: 300,
    rate_limit_tpm: 120000,
    timeout_seconds: 30,
    health_timeout_seconds: 5,
  },
  {
    name: "moonshot",
    label: "Moonshot",
    model: "moonshot-v1-8k",
    api_format: "openai",
    base_url: "https://api.moonshot.cn/v1",
    api_key: "",
    rate_limit_rpm: 300,
    rate_limit_tpm: 120000,
    timeout_seconds: 30,
    health_timeout_seconds: 5,
  },
];

const emptyProvider: ProviderConfig = {
  name: "custom-openai-compatible",
  label: "自定义 OpenAI 兼容",
  model: "default",
  api_format: "openai",
  base_url: "",
  api_key: "",
  api_key_env: "",
  model_context_window_tokens: 0,
  rate_limit_rpm: 300,
  rate_limit_tpm: 120000,
  timeout_seconds: 30,
  health_timeout_seconds: 5,
  circuit_breaker: { failure_threshold: 3, cooldown_seconds: 60 },
};

export function ModelSettingsPage() {
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["settings", "models"], queryFn: getModelSettings });
  const health = useQuery({ queryKey: ["settings", "models", "health"], queryFn: getModelHealth });
  const fallbacks = useQuery({
    queryKey: ["settings", "models", "fallbacks"],
    queryFn: () => getModelFallbackSummary(20),
  });
  const healthByProvider = new Map(
    (health.data?.items ?? []).map((item) => [`${item.provider}:${item.model}`, item]),
  );
  const [draftProvider, setDraftProvider] = useState<ProviderConfig>(emptyProvider);
  const [saveMessage, setSaveMessage] = useState("");
  const providers = useMemo(
    () => ((settings.data?.providers ?? []) as ProviderConfig[]),
    [settings.data?.providers],
  );
  const saveMutation = useMutation({
    mutationFn: updateModelSettings,
    onSuccess: async () => {
      setSaveMessage(text("模型配置已保存", "Model settings saved"));
      await queryClient.invalidateQueries({ queryKey: ["settings", "models"] });
      await queryClient.invalidateQueries({ queryKey: ["settings", "models", "health"] });
    },
    onError: (error) => {
      setSaveMessage(
        text(
          `保存失败：${error instanceof Error ? error.message : "未知错误"}`,
          `Save failed: ${error instanceof Error ? error.message : "unknown error"}`,
        ),
      );
    },
  });

  function currentSettings(): ModelSettings {
    return (
      settings.data ?? {
        default_provider: "openai-compatible",
        default_model: "default",
        providers: [],
        rate_limits: { rpm: 600, tpm: 120000 },
        health: {
          status: "healthy",
          updated_at: null,
          mode: "mock",
          latency_ms: 0,
          error_message: null,
        },
        circuit_breaker: { failure_threshold: 3, cooldown_seconds: 60 },
      }
    );
  }

  function save(next: ModelSettings) {
    setSaveMessage("");
    saveMutation.mutate(next);
  }

  function addOrUpdateProvider(provider: ProviderConfig, makeDefault = true) {
    const normalized = normalizeProvider(provider);
    const nextProviders = [
      ...providers.filter((item) => providerKey(item) !== providerKey(normalized)),
      normalized,
    ];
    const next = {
      ...currentSettings(),
      default_provider: makeDefault ? normalized.name : currentSettings().default_provider,
      default_model: makeDefault ? String(normalized.model || "default") : currentSettings().default_model,
      providers: nextProviders,
    };
    save(next);
  }

  function removeProvider(provider: ProviderConfig) {
    const nextProviders = providers.filter((item) => providerKey(item) !== providerKey(provider));
    const fallback = nextProviders[0];
    save({
      ...currentSettings(),
      default_provider:
        currentSettings().default_provider === provider.name
          ? String(fallback?.name ?? "openai-compatible")
          : currentSettings().default_provider,
      default_model:
        currentSettings().default_provider === provider.name
          ? String(fallback?.model ?? "default")
          : currentSettings().default_model,
      providers: nextProviders,
    });
  }

  function setDefaultProvider(provider: ProviderConfig) {
    save({
      ...currentSettings(),
      default_provider: provider.name,
      default_model: String(provider.model || currentSettings().default_model || "default"),
    });
  }

  function submitCustomProvider(event: FormEvent) {
    event.preventDefault();
    addOrUpdateProvider(draftProvider, true);
  }

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
            <Metric label={<TermHint description="每分钟请求数">RPM</TermHint>} value={formatLimit(settings.data?.rate_limits.rpm, "rpm")} />
            <Metric label={<TermHint description="每分钟标记数">TPM</TermHint>} value={formatLimit(settings.data?.rate_limits.tpm, "tpm")} />
            <Metric
              label={text("熔断规则", "Circuit Breaker")}
              value={`${String(settings.data?.circuit_breaker.failure_threshold ?? "...")} 次失败 / ${String(
                settings.data?.circuit_breaker.cooldown_seconds ?? "...",
              )} 秒`}
            />
            <Metric
              label={<TermHint description="主模型失败后的后备切换">Fallback</TermHint>}
              value={String(fallbacks.data?.fallback_total ?? "...")}
            />
          </div>
        </Card>
        <div className="grid grid-cols-2 gap-4">
          <Card>
            <CardHeader>
              <div>
                <div className="text-[11px] tracking-widest text-slate-500">
                  {text("模型切换", "Model Switch")}
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {text("添加预置或自定义模型，并设为智能体默认模型", "Add presets or custom models and switch the Agent default model.")}
                </div>
              </div>
              <span className="text-[11px] text-slate-500">
                {saveMutation.isPending ? text("保存中...", "Saving...") : saveMessage}
              </span>
            </CardHeader>
            <div className="grid gap-2 p-3">
              {providerPresets.map((preset) => {
                const installed = providers.some((provider) => provider.name === preset.name);
                const active =
                  settings.data?.default_provider === preset.name &&
                  settings.data?.default_model === preset.model;
                return (
                  <div
                    key={`${preset.name}:${preset.model}`}
                    className="rounded-md border border-slate-100 bg-white p-3"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-xs text-slate-900">{preset.name}</span>
                          {active && <Badge tone="success">{text("当前默认", "Default")}</Badge>}
                          {installed && !active && <Badge tone="neutral">{text("已添加", "Installed")}</Badge>}
                        </div>
                        <div className="mt-1 text-xs text-slate-500">{preset.label}</div>
                        <div className="mt-1 font-mono text-[11px] text-slate-500">
                          {preset.model} · {preset.api_format ?? "openai"} · {preset.base_url}
                        </div>
                      </div>
                      <Button
                        type="button"
                        variant={active ? "secondary" : "primary"}
                        disabled={saveMutation.isPending}
                        onClick={() => addOrUpdateProvider(preset, true)}
                      >
                        {active ? <Check className="h-3.5 w-3.5" /> : <Plus className="h-3.5 w-3.5" />}
                        {active ? text("已启用", "Active") : text("添加并切换", "Add & Switch")}
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>
          <Card>
            <CardHeader>
              <div>
                <div className="text-[11px] tracking-widest text-slate-500">
                  {text("自定义模型", "Custom Model")}
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  <>
                    {text("支持 ", "Any ")}
                    <TermHint description="兼容 OpenAI 接口形态">OpenAI-compatible</TermHint>
                    {text(" 的聊天补全接口。", " /chat/completions endpoint.")}
                  </>
                </div>
              </div>
            </CardHeader>
            <form onSubmit={submitCustomProvider} className="grid gap-3 p-3 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <Field label={text("供应商标识", "Provider ID")}>
                  <Input
                    value={draftProvider.name}
                    onChange={(event) => setDraftProvider({ ...draftProvider, name: event.target.value })}
                  />
                </Field>
                <Field label={text("显示名称", "Label")}>
                  <Input
                    value={String(draftProvider.label ?? "")}
                    onChange={(event) => setDraftProvider({ ...draftProvider, label: event.target.value })}
                  />
                </Field>
                <Field label={text("模型名称", "Model")}>
                  <Input
                    value={String(draftProvider.model ?? "")}
                    onChange={(event) => setDraftProvider({ ...draftProvider, model: event.target.value })}
                  />
                </Field>
                <Field label={text("协议", "Protocol")}>
                  <MenuSelect
                    ariaLabel={text("协议", "Protocol")}
                    value={String(draftProvider.api_format ?? "openai")}
                    onChange={(value) => setDraftProvider({ ...draftProvider, api_format: value })}
                    placeholder={text("选择协议", "Select protocol")}
                    buttonClassName="h-9 rounded-md px-3 py-2 shadow-none text-xs"
                    menuClassName="w-[280px]"
                    options={[
                      {
                        value: "openai",
                        label: text("OpenAI 兼容", "OpenAI compatible"),
                        description: "/chat/completions",
                      },
                      {
                        value: "anthropic",
                        label: text("Anthropic 兼容", "Anthropic compatible"),
                        description: "/v1/messages",
                      },
                    ]}
                  />
                </Field>
                <Field label={<TermHint description="接口基础地址">Base URL</TermHint>}>
                  <Input
                    value={String(draftProvider.base_url ?? "")}
                    placeholder="https://api.example.com/v1"
                    onChange={(event) => setDraftProvider({ ...draftProvider, base_url: event.target.value })}
                  />
                </Field>
                <Field label={<TermHint description="接口访问密钥">API Key</TermHint>}>
                  <Input
                    type="password"
                    value={String(draftProvider.api_key ?? "")}
                    placeholder="sk-..."
                    onChange={(event) => setDraftProvider({ ...draftProvider, api_key: event.target.value })}
                  />
                </Field>
                <Field label={<TermHint description="保存 API Key 的环境变量">API Key 环境变量</TermHint>}>
                  <Input
                    value={String(draftProvider.api_key_env ?? "")}
                    placeholder="DEEPSEEK_API_KEY"
                    onChange={(event) => setDraftProvider({ ...draftProvider, api_key_env: event.target.value })}
                  />
                </Field>
                <Field label={text("模型上下文标记", "Model context tokens")}>
                  <Input
                    type="number"
                    value={Number(draftProvider.model_context_window_tokens ?? 0)}
                    onChange={(event) =>
                      setDraftProvider({
                        ...draftProvider,
                        model_context_window_tokens: Number(event.target.value),
                      })
                    }
                  />
                </Field>
                <Field label={<TermHint description="每分钟请求数">RPM</TermHint>}>
                  <Input
                    type="number"
                    value={Number(draftProvider.rate_limit_rpm ?? 300)}
                    onChange={(event) =>
                      setDraftProvider({ ...draftProvider, rate_limit_rpm: Number(event.target.value) })
                    }
                  />
                </Field>
                <Field label={<TermHint description="每分钟标记数">TPM</TermHint>}>
                  <Input
                    type="number"
                    value={Number(draftProvider.rate_limit_tpm ?? 120000)}
                    onChange={(event) =>
                      setDraftProvider({ ...draftProvider, rate_limit_tpm: Number(event.target.value) })
                    }
                  />
                </Field>
                <Field label={text("超时秒数", "Timeout seconds")}>
                  <Input
                    type="number"
                    value={Number(draftProvider.timeout_seconds ?? 30)}
                    onChange={(event) =>
                      setDraftProvider({ ...draftProvider, timeout_seconds: Number(event.target.value) })
                    }
                  />
                </Field>
              </div>
              <div className="flex justify-end gap-2 border-t border-slate-100 pt-3">
                <Button
                  type="button"
                  onClick={() => setDraftProvider(emptyProvider)}
                  disabled={saveMutation.isPending}
                >
                  {text("重置", "Reset")}
                </Button>
                <Button type="submit" variant="primary" disabled={saveMutation.isPending}>
                  <Save className="h-3.5 w-3.5" /> {text("保存并设为默认", "Save & Set Default")}
                </Button>
              </div>
            </form>
          </Card>
        </div>
        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <GitBranch className="h-4 w-4" />
              <TermHint description="主模型失败后的后备切换">Fallback</TermHint>
              {text("策略观测", "Observability")}
            </div>
            <span className="text-xs text-slate-500">
              {text("后备切换展示供应商分布和最近切换事件", "Shows primary failures, fallback provider distribution, and recent switch events")}
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
                <Th>
                  <TermHint description="主模型失败后的后备模型">Fallback</TermHint>
                </Th>
                <Th>{text("原因", "Reason")}</Th>
                <Th>
                  <TermHint description="跨服务追踪标识">Trace</TermHint>
                </Th>
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
                    {text("暂无模型后备切换事件", "No model fallback events")}
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
              {providers.map((provider) => {
                const model = String(provider.model ?? settings.data?.default_model ?? "default");
                const item = healthByProvider.get(`${String(provider.name)}:${model}`);
                const active =
                  settings.data?.default_provider === provider.name &&
                  settings.data?.default_model === model;
                return (
                  <tr key={`${String(provider.name)}:${model}`} className="border-t border-slate-100">
                    <Td className="font-mono">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span>{String(provider.name)}</span>
                        {active && <Badge tone="success">{text("默认", "Default")}</Badge>}
                      </div>
                      {provider.label ? (
                        <div className="mt-1 font-sans text-[11px] text-slate-500">
                          {String(provider.label)}
                        </div>
                      ) : null}
                    </Td>
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
                    <Td>
                      <div className="flex items-center gap-1">
                        <Button
                          type="button"
                          variant="ghost"
                          title={text("设为默认", "Set default")}
                          disabled={active || saveMutation.isPending}
                          onClick={() => setDefaultProvider(provider)}
                        >
                          <Star className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          title={text("删除", "Remove")}
                          disabled={saveMutation.isPending}
                          onClick={() => removeProvider(provider)}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
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

function normalizeProvider(provider: ProviderConfig): ProviderConfig {
  const name = String(provider.name || "custom-openai-compatible").trim();
  const model = String(provider.model || "default").trim();
  return {
    ...provider,
    name,
    model,
    status: "healthy",
    api_format: String(provider.api_format || "openai"),
    api_key: String(provider.api_key || "replace-me"),
    api_key_env: String(provider.api_key_env || ""),
    model_context_window_tokens: Number(provider.model_context_window_tokens || 0),
    rate_limit_rpm: Number(provider.rate_limit_rpm || 300),
    rate_limit_tpm: Number(provider.rate_limit_tpm || 120000),
    timeout_seconds: Number(provider.timeout_seconds || 30),
    health_timeout_seconds: Number(provider.health_timeout_seconds || 5),
    circuit_breaker: {
      failure_threshold: Number(provider.circuit_breaker?.failure_threshold || 3),
      cooldown_seconds: Number(provider.circuit_breaker?.cooldown_seconds || 60),
    },
  };
}

function providerKey(provider: ProviderConfig) {
  return `${provider.name}:${String(provider.model ?? "default")}`;
}

function formatLimit(value: unknown, unit: string) {
  if (value === undefined || value === null || value === "") return `... ${unit}`;
  return `${Number(value).toLocaleString("zh-CN")} ${unit}`;
}

function formatLatency(value?: number) {
  if (value === undefined || value === null) return "... ms";
  return `${value.toLocaleString("zh-CN")} ms`;
}

function Metric({ label, value }: { label: ReactNode; value: string }) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50 p-3">
      <div className="text-slate-500">{label}</div>
      <div className="mt-1 font-mono text-slate-900">{value}</div>
    </div>
  );
}

function Field({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <label className="grid gap-1.5 text-slate-700">
      <span>{label}</span>
      {children}
    </label>
  );
}
