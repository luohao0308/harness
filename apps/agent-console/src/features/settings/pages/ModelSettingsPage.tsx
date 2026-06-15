import { FormEvent, useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRightLeft,
  Brain,
  Check,
  Activity,
  ExternalLink,
  GitBranch,
  Loader2,
  Plus,
  RefreshCw,
  Save,
} from "lucide-react";
import { Link } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, type BadgeTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { ConfigDialog } from "../../../components/ui/config-dialog";
import { feedbackErrorMessage, notifyFeedback } from "../../../components/ui/feedback-toast";
import { Input } from "../../../components/ui/input";
import { MenuSelect } from "../../../components/ui/menu-select";
import { RefreshOverlay } from "../../../components/ui/refresh-overlay";
import { Table, Td, Th } from "../../../components/ui/table";
import { TermHint } from "../../../components/ui/term";
import { useI18n } from "../../../lib/i18n";
import { statusLabel } from "../../../lib/labels";
import { formatShortDate } from "../../../lib/utils";
import {
  getModelFallbackSummary,
  getModelHealth,
  getModelOfficialStatus,
  getModelPricingSources,
  getModelSettings,
  updateModelSettings,
  type ModelHealth,
  type ModelOfficialStatus,
  type ModelPricingSourceItem,
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
  api_key_configured?: boolean;
  api_key_source?: string;
  api_key_secret_id?: string | null;
  model_kind?: string;
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
    model_kind: "文本模型",
  },
  {
    ...deepSeekPresetBase,
    name: "deepseek-pro",
    label: "DeepSeek Pro",
    model: "deepseek-v4-pro",
    model_kind: "推理模型",
  },
  {
    name: "openai-compatible",
    label: "OpenAI GPT-5.5",
    model: "gpt-5.5",
    model_kind: "推理模型",
    api_format: "openai",
    base_url: "https://api.openai.com/v1",
    api_key: "",
    api_key_env: "OPENAI_API_KEY",
    model_context_window_tokens: 272000,
    max_output_tokens: 128000,
    rate_limit_rpm: 600,
    rate_limit_tpm: 120000,
    timeout_seconds: 30,
    health_timeout_seconds: 5,
  },
  {
    name: "kimi",
    label: "Kimi K2.6",
    model: "kimi-k2.6",
    model_kind: "推理模型",
    api_format: "openai",
    base_url: "https://api.moonshot.cn/v1",
    api_key: "",
    api_key_env: "MOONSHOT_API_KEY",
    model_context_window_tokens: 262144,
    rate_limit_rpm: 300,
    rate_limit_tpm: 120000,
    timeout_seconds: 30,
    health_timeout_seconds: 5,
  },
  {
    name: "z-ai",
    label: "Z.AI GLM-5.1",
    model: "glm-5.1",
    model_kind: "推理模型",
    api_format: "openai",
    base_url: "https://api.z.ai/api/paas/v4",
    api_key: "",
    api_key_env: "ZAI_API_KEY",
    model_context_window_tokens: 200000,
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

const MODEL_SETTINGS_ADD_CUSTOM_EVENT = "harness:model-settings:add-custom-model";

type ProviderGroup = {
  key: string;
  label: string;
  providers: ProviderConfig[];
};

export function ModelSettingsPage() {
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["settings", "models"], queryFn: getModelSettings });
  const health = useQuery({
    queryKey: ["settings", "models", "health"],
    queryFn: getModelHealth,
    enabled: false,
  });
  const officialStatus = useQuery({
    queryKey: ["settings", "models", "official-status"],
    queryFn: getModelOfficialStatus,
    enabled: false,
  });
  const fallbacks = useQuery({
    queryKey: ["settings", "models", "fallbacks"],
    queryFn: () => getModelFallbackSummary(20),
  });
  const pricingSources = useQuery({
    queryKey: ["settings", "models", "pricing-sources"],
    queryFn: getModelPricingSources,
  });
  const [providerDialogMode, setProviderDialogMode] = useState<"preset" | "custom" | null>(null);
  const [draftProvider, setDraftProvider] = useState<ProviderConfig>(emptyProvider);
  const [saveMessage, setSaveMessage] = useState("");
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const providers = useMemo(
    () => ((settings.data?.providers ?? []) as ProviderConfig[]),
    [settings.data?.providers],
  );
  const displayProviders = useMemo(() => mergePresetAndConfiguredProviders(providers), [providers]);
  const providerGroups = useMemo(() => groupProvidersByVendor(displayProviders), [displayProviders]);
  const healthItems = useMemo(
    () => modelHealthItems(displayProviders, health.data?.items ?? []),
    [displayProviders, health.data?.items],
  );
  const officialStatusItems = officialStatus.data?.items ?? [];
  const refreshingStatus = health.isFetching || officialStatus.isFetching;
  const defaultProvider = providers.find(
    (provider) =>
      String(provider.name) === String(settings.data?.default_provider) &&
      String(provider.model ?? "default") === String(settings.data?.default_model ?? "default"),
  );
  const pricingItems = (pricingSources.data?.items ?? []).filter(
    (item) => !isDeprecatedPricingSource(item),
  );
  const pricingStatusText = pricingSources.isLoading
    ? text("同步中", "Syncing")
    : pricingSources.isError
      ? text("暂不可用", "Unavailable")
      : text(`${pricingItems.length} 个来源`, `${pricingItems.length} sources`);

  useEffect(() => {
    const openCustomProviderDialog = () => openProviderDialog(emptyProvider, "custom");
    window.addEventListener(MODEL_SETTINGS_ADD_CUSTOM_EVENT, openCustomProviderDialog);
    return () => window.removeEventListener(MODEL_SETTINGS_ADD_CUSTOM_EVENT, openCustomProviderDialog);
  }, []);
  const saveMutation = useMutation({
    mutationFn: updateModelSettings,
    onSuccess: (saved) => {
      setSaveMessage(text("模型配置已保存", "Model settings saved"));
      notifyFeedback({
        tone: "success",
        title: text("模型配置已保存", "Model settings saved"),
        description: text("当前默认模型和提供商列表已经更新。", "The default model and provider list have been updated."),
      });
      queryClient.setQueryData(["settings", "models"], saved);
      void queryClient.invalidateQueries({ queryKey: ["settings", "models"], exact: true });
      void queryClient.invalidateQueries({
        queryKey: ["settings", "models", "fallbacks"],
        exact: true,
      });
    },
    onError: (error) => {
      setSaveMessage(
        text(
          `保存失败：${error instanceof Error ? error.message : "未知错误"}`,
          `Save failed: ${error instanceof Error ? error.message : "unknown error"}`,
        ),
      );
      notifyFeedback({
        tone: "error",
        title: text("模型配置保存失败", "Model settings save failed"),
        description: feedbackErrorMessage(error, text("请检查模型配置项并稍后重试。", "Check the model settings and retry.")),
      });
    },
    onSettled: () => {
      setPendingAction(null);
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

  function save(next: ModelSettings, actionId = "save", options: { closeDialog?: boolean } = {}) {
    setSaveMessage("");
    setPendingAction(actionId);
    saveMutation.mutate(next, {
      onSuccess: () => {
        if (options.closeDialog) {
          closeProviderDialog();
        }
      },
    });
  }

  function addOrUpdateProvider(
    provider: ProviderConfig,
    makeDefault = true,
    options: { closeDialog?: boolean } = {},
  ) {
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
    save(next, providerActionKey(normalized), options);
  }

  function setDefaultProvider(provider: ProviderConfig) {
    if (!providerHasUsableApiKey(provider)) {
      openProviderDialog(provider, "preset");
      return;
    }
    save({
      ...currentSettings(),
      default_provider: provider.name,
      default_model: String(provider.model || currentSettings().default_model || "default"),
    }, `default:${provider.name}:${String(provider.model || "default")}`);
  }

  function openProviderDialog(provider: ProviderConfig, mode: "preset" | "custom") {
    setSaveMessage("");
    setDraftProvider(toEditableProvider(provider));
    setProviderDialogMode(mode);
  }

  function closeProviderDialog() {
    setProviderDialogMode(null);
    setDraftProvider(emptyProvider);
  }

  function handlePresetAction(provider: ProviderConfig) {
    const configuredProvider = providers.find((item) => providerKey(item) === providerKey(provider));
    if (configuredProvider && providerHasUsableApiKey(configuredProvider)) {
      setDefaultProvider(configuredProvider);
      return;
    }
    openProviderDialog(configuredProvider ?? provider, "preset");
  }

  function submitProviderDialog(event: FormEvent) {
    event.preventDefault();
    const normalized = normalizeProvider(draftProvider);
    if (!providerHasUsableApiKey(normalized)) {
      setSaveMessage(text("请先填写 API Key，再启用模型。", "Enter an API key before enabling this model."));
      return;
    }
    setDraftProvider(normalized);
    addOrUpdateProvider(normalized, true, { closeDialog: true });
  }

  async function refreshModelStatus() {
    const [healthResult] = await Promise.all([
      health.refetch(),
      officialStatus.refetch(),
    ]);
    if (!healthResult.error) {
      await queryClient.invalidateQueries({ queryKey: ["settings", "models"], exact: true });
    }
  }

  return (
    <ConsoleShell title={text("模型设置", "Model Settings")}>
      <div className="space-y-4 p-4 pb-24">
        <Card className="overflow-hidden">
          <CardHeader className="items-start gap-3">
            <div>
              <div className="text-[11px] tracking-widest text-slate-500">
                {text("模型切换", "Model Switch")}
              </div>
              <div className="mt-1 text-[11px] text-slate-500">
                {text("只有已配置 API Key 的模型可以直接切换；保存后密钥只进入密钥库，不会回显原文。", "Only models with an API key can switch directly; saved keys go into the secret vault and are never echoed.")}
              </div>
            </div>
            <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
              <span className="text-[11px] text-slate-500">
                {saveMutation.isPending ? text("保存中...", "Saving...") : saveMessage}
              </span>
              <Button type="button" onClick={() => openProviderDialog(emptyProvider, "custom")}>
                <Plus className="h-3.5 w-3.5" />
                {text("添加自定义模型", "Add custom model")}
              </Button>
            </div>
          </CardHeader>
          <div className="grid gap-2 p-3 md:grid-cols-2 xl:grid-cols-5">
            {providerPresets.map((preset) => {
              const installedProvider = providers.find((provider) => providerKey(provider) === providerKey(preset));
              const displayProvider = installedProvider ? { ...preset, ...installedProvider } : preset;
              const modelKind = modelKindLabel(displayProvider);
              const configured = installedProvider ? providerHasUsableApiKey(installedProvider) : false;
              const active =
                settings.data?.default_provider === preset.name &&
                settings.data?.default_model === preset.model;
              const pending = pendingAction === providerActionKey(installedProvider ?? preset);
              const actionLabel = pending
                ? text("切换中", "Switching")
                : active && configured
                  ? text("已启用", "Active")
                  : configured
                    ? text("切换", "Switch")
                    : text("配置并启用", "Configure & Enable");
              return (
                <div
                  key={`${preset.name}:${preset.model}`}
                  className="flex min-h-[104px] flex-col justify-between rounded-md border border-slate-100 bg-white p-2.5 shadow-sm"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-mono text-[13px] font-semibold leading-5 text-slate-900">
                        {preset.model ?? preset.name}
                      </span>
                      <Badge tone={modelKindTone(modelKind)}>{modelKind}</Badge>
                    </div>
                  </div>
                  <Button
                    type="button"
                    className="mt-3 w-full justify-center"
                    variant={active && configured ? "secondary" : configured ? "secondary" : "primary"}
                    disabled={(active && configured) || saveMutation.isPending}
                    aria-label={`${preset.model ?? preset.name} ${actionLabel}`}
                    onClick={() => handlePresetAction(preset)}
                  >
                    {pending ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : active && configured ? (
                      <Check className="h-3.5 w-3.5" />
                    ) : configured ? (
                      <ArrowRightLeft className="h-3.5 w-3.5" />
                    ) : (
                      <Plus className="h-3.5 w-3.5" />
                    )}
                    {actionLabel}
                  </Button>
                </div>
              );
            })}
          </div>
        </Card>
        <Card className="overflow-hidden">
          <CardHeader className="items-start gap-3">
            <div className="min-w-0">
              <div className="inline-flex items-center gap-2 text-[13px] font-semibold text-slate-900">
                <Brain className="h-3.5 w-3.5" /> {text("模型网关", "Model Gateway")}
              </div>
              <div className="mt-1 text-[11px] text-slate-500">
                {text(
                  "当前默认模型、健康状态、限流与后备切换概览。",
                  "Default model, health, rate limits, and fallback overview.",
                )}
              </div>
            </div>
            <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
              <Badge tone={modelHealthTone(String(settings.data?.health.status ?? ""))}>
                {settings.isLoading ? text("同步中", "Syncing") : statusLabel(String(settings.data?.health.status ?? "..."))}
              </Badge>
              <Button
                type="button"
                variant="secondary"
                onClick={() => void refreshModelStatus()}
                disabled={refreshingStatus}
                aria-label={text("刷新模型状态", "Refresh model status")}
              >
                {refreshingStatus ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RefreshCw className="h-3.5 w-3.5" />
                )}
                {refreshingStatus ? text("刷新中", "Refreshing") : text("刷新状态", "Refresh")}
              </Button>
            </div>
          </CardHeader>
          <RefreshOverlay refreshing={refreshingStatus} label={text("正在刷新模型状态", "Refreshing model status")}>
            <div className="grid gap-2.5 p-2.5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
              <div className="rounded-md border border-slate-100 bg-slate-50 p-2.5">
                <div className="text-[10px] uppercase tracking-widest text-slate-500">{text("当前默认", "Current Default")}</div>
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                  <div className="min-w-0 text-[13px] font-semibold leading-5 text-slate-900">
                    {defaultProvider ? vendorDisplayName(defaultProvider) : settings.data?.default_provider ?? "..."}
                  </div>
                  <Badge tone="neutral">{settings.data?.default_model ?? "default"}</Badge>
                </div>
                <div className="mt-1 flex min-w-0 flex-wrap items-center gap-1 text-[11px] text-slate-500">
                  <span className="font-mono">{defaultProvider?.api_format ?? "openai"}</span>
                  <span>·</span>
                  {defaultProvider ? (
                    <ProviderEndpointLink provider={defaultProvider} />
                  ) : (
                    <span className="font-mono">...</span>
                  )}
                </div>
              </div>
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
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
                <Metric label={text("供应商", "Providers")} value={String(providerGroups.length)} />
              </div>
            </div>
            <div className="grid gap-2.5 border-t border-slate-100 p-2.5 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,0.75fr)]">
              <div className="rounded-md border border-slate-100 bg-white">
                <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-2.5 py-2">
                  <div className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-slate-800">
                    <Activity className="h-3.5 w-3.5" />
                    {text("Harness 探测", "Harness Probe")}
                  </div>
                  <span className="text-[10px] text-slate-500">
                    {health.data
                      ? text("刚刚刷新", "Refreshed")
                      : text("使用最近状态", "Recent status")}
                  </span>
                </div>
                <div className="grid gap-1.5 p-2.5 sm:grid-cols-2">
                  {healthItems.map((item) => (
                    <ModelHealthStrip key={`${item.provider}:${item.model}`} item={item} />
                  ))}
                </div>
                {health.isError ? (
                  <div className="border-t border-amber-100 bg-amber-50 px-2.5 py-2 text-[11px] text-amber-700">
                    {modelHealthErrorText(health.error)}
                  </div>
                ) : null}
              </div>
              <div className="rounded-md border border-slate-100 bg-white">
                <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-2.5 py-2">
                  <div className="text-[11px] font-semibold text-slate-800">
                    {text("官方状态", "Official Status")}
                  </div>
                  <span className="text-[10px] text-slate-500">
                    {officialStatus.data ? text("外部服务", "External") : text("未刷新", "Not refreshed")}
                  </span>
                </div>
                <div className="grid gap-1.5 p-2.5">
                  {(officialStatusItems.length > 0 ? officialStatusItems : defaultOfficialStatusItems()).map((item) => (
                    <OfficialStatusStrip key={item.provider} item={item} />
                  ))}
                </div>
                {officialStatus.isError ? (
                  <div className="border-t border-amber-100 bg-amber-50 px-2.5 py-2 text-[11px] text-amber-700">
                    {modelHealthErrorText(officialStatus.error)}
                  </div>
                ) : null}
              </div>
            </div>
          </RefreshOverlay>
        </Card>
        <Card className="overflow-hidden">
          <CardHeader className="items-start gap-3">
            <div>
              <div className="text-[11px] tracking-widest text-slate-500">
                {text("内置模型成本", "Built-in Model Costs")}
              </div>
              <div className="mt-1 text-[11px] text-slate-500">
                {text("价格来自官方来源契约；不可汇总项会单独标记，不影响模型切换。", "Prices come from the official source contract; non-rollup rows are marked without affecting model switching.")}
              </div>
            </div>
            <div className="flex shrink-0 flex-col items-end gap-1">
              <Badge tone={pricingSources.isError ? "warning" : pricingSources.isLoading ? "pending" : "success"}>
                {pricingStatusText}
              </Badge>
              <span className="font-mono text-[11px] text-slate-500">
                {pricingSources.data ? formatShortDate(pricingSources.data.retrieved_at) : "..."}
              </span>
            </div>
          </CardHeader>
          {pricingSources.isError ? (
            <div className="space-y-3 p-3">
              <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                <div className="flex items-center gap-2 font-medium">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  {text("成本来源暂不可用", "Pricing sources unavailable")}
                </div>
                <div className="mt-1 text-amber-700">{modelPricingErrorText(pricingSources.error)}</div>
              </div>
              <div className="rounded-md border border-slate-100 bg-slate-50 px-3 py-2 text-xs text-slate-500">
                {text(
                  "模型切换和自定义供应商保存仍可使用；成本总览会在来源恢复后自动补齐。",
                  "Model switching and custom provider saves still work; cost totals will catch up when the source recovers.",
                )}
              </div>
            </div>
          ) : pricingSources.isLoading ? (
            <div className="p-3">
              <div className="rounded-md border border-slate-100 bg-slate-50 px-3 py-2 text-xs text-slate-500">
                {text("正在同步官方成本来源...", "Syncing official pricing sources...")}
              </div>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <Table className="min-w-[980px] text-[11px]">
                  <thead className="bg-slate-50 text-[10px] uppercase tracking-wide text-slate-500">
                    <tr>
                      <Th>{text("模型", "Model")}</Th>
                      <Th>{text("价格 / 1M token", "Price / 1M tokens")}</Th>
                      <Th>{text("USD / 1K", "USD / 1K")}</Th>
                      <Th>{text("来源状态", "Source Status")}</Th>
                      <Th>{text("区域 / 模式", "Region / Mode")}</Th>
                      <Th>{text("官方来源", "Official Source")}</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {(pricingItems ?? []).map((item) => (
                      <PricingSourceRow key={`${item.provider}:${item.model}`} item={item} />
                    ))}
                    {pricingItems.length === 0 ? (
                      <tr>
                        <Td colSpan={6} className="py-8 text-center text-slate-500">
                          {text("暂无内置模型成本来源", "No built-in model pricing sources")}
                        </Td>
                      </tr>
                    ) : null}
                  </tbody>
                </Table>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 px-3 py-2 text-[11px] text-slate-500">
                <span>
                  {text(
                    "企业门禁会拦截缺失、过期、SKU 模糊或需要汇率换算的价格。",
                    "Enterprise gates block missing, stale, ambiguous, or FX-required prices.",
                  )}
                </span>
                {pricingSources.data ? (
                  <span className="font-mono">
                    {pricingSources.data.schema_version} · {pricingSources.data.parser_version}
                  </span>
                ) : null}
              </div>
            </>
          )}
        </Card>
        <Card className="overflow-hidden">
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
          <div className="grid gap-3 p-3 text-xs sm:grid-cols-3">
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
          <div className="overflow-x-auto">
            <Table className="min-w-[720px]">
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
          </div>
        </Card>
        <Card className="overflow-hidden">
          <CardHeader>
            <div>
              <div className="text-[11px] tracking-widest text-slate-500">{text("供应商", "Providers")}</div>
              <div className="mt-1 text-xs text-slate-500">
                {text("按供应商聚合展示模型、密钥和限流配置", "Groups models by provider with secrets and rate limits")}
              </div>
            </div>
          </CardHeader>
          <div className="overflow-x-auto">
            <Table className="min-w-[860px]">
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <Th>{text("供应商", "Provider")}</Th>
                  <Th>{text("现有模型", "Models")}</Th>
                  <Th>{text("密钥", "Secret")}</Th>
                  <Th>{text("限流", "Rate Limit")}</Th>
                  <Th className="text-right">{text("操作", "Actions")}</Th>
                </tr>
              </thead>
              <tbody>
                {providerGroups.map((group) => {
                  const secretStatus = groupSecretStatus(group.providers);
                  return (
                    <tr key={group.key} className="border-t border-slate-100 align-top">
                      <Td>
                        <span className="font-medium text-slate-900">
                          {group.label}
                        </span>
                        <ProviderEndpointSummary providers={group.providers} />
                      </Td>
                      <Td>
                        <div className="grid gap-1.5">
                          {group.providers.map((provider) => {
                            const model = String(provider.model ?? "default");
                            return (
                              <div
                                key={`${String(provider.name)}:${model}`}
                                className="flex flex-wrap items-center gap-x-2 gap-y-1"
                              >
                                <span className="font-mono text-[11px] text-slate-900">{model}</span>
                                <Badge tone={modelKindTone(modelKindLabel(provider))}>{modelKindLabel(provider)}</Badge>
                              </div>
                            );
                          })}
                        </div>
                      </Td>
                      <Td>
                        <div className="flex flex-wrap items-center gap-1.5">
                          <Badge tone={secretStatus.tone}>
                            {secretStatus.label}
                          </Badge>
                          {secretSourceSummary(group.providers).map((source) => (
                            <Badge key={source} tone="info">{source}</Badge>
                          ))}
                        </div>
                      </Td>
                      <Td>
                        <div className="grid gap-1.5">
                          {group.providers.map((provider) => {
                            const model = String(provider.model ?? "default");
                            return (
                              <div key={`${String(provider.name)}:${model}`} className="text-slate-600">
                                <span className="font-mono text-[11px] text-slate-800">{model}</span>
                                <span className="ml-1">
                                  {formatLimit(provider.rate_limit_rpm ?? settings.data?.rate_limits.rpm, "rpm")}
                                </span>
                                <span className="ml-1 text-slate-500">
                                  {formatLimit(provider.rate_limit_tpm ?? settings.data?.rate_limits.tpm, "tpm")}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      </Td>
                      <Td>
                        <div className="flex flex-wrap items-center justify-end gap-1">
                          {group.providers.map((provider) => {
                            const model = String(provider.model ?? "default");
                            const modelActive =
                              settings.data?.default_provider === provider.name &&
                              settings.data?.default_model === model;
                            const canSwitch = providerHasUsableApiKey(provider);
                            const actionTitle =
                              !canSwitch
                                ? text(`配置：${model}`, `Configure: ${model}`)
                                : modelActive
                                  ? text(`当前：${model}`, `Current: ${model}`)
                                  : text(`切换：${model}`, `Switch: ${model}`);
                            return (
                              <div key={`${String(provider.name)}:${model}`} className="flex items-center gap-1">
                                <Button
                                  type="button"
                                  variant="ghost"
                                  className="h-7 px-2"
                                  aria-label={actionTitle}
                                  title={actionTitle}
                                  disabled={(modelActive && canSwitch) || saveMutation.isPending}
                                  onClick={() =>
                                    canSwitch
                                      ? setDefaultProvider(provider)
                                      : openProviderDialog(provider, "preset")
                                  }
                                >
                                  {!canSwitch
                                    ? text("配置", "Configure")
                                    : modelActive
                                      ? text("当前", "Current")
                                      : text("切换", "Switch")}
                                </Button>
                              </div>
                            );
                          })}
                        </div>
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          </div>
        </Card>
      </div>
      <ConfigDialog
        open={providerDialogMode !== null}
        title={
          providerDialogMode === "custom"
            ? text("添加自定义模型", "Add Custom Model")
            : text(`配置 ${providerDisplayName(draftProvider)}`, `Configure ${providerDisplayName(draftProvider)}`)
        }
        description={text(
          "填写 API Key 后保存，系统才会把该模型设为默认模型。",
          "Enter an API key before saving; the model is set as default only after configuration.",
        )}
        onClose={closeProviderDialog}
        className="max-w-3xl"
      >
        <form onSubmit={submitProviderDialog} className="grid gap-3 text-xs">
          <div className="grid gap-3 md:grid-cols-2">
            <Field label={text("供应商标识", "Provider ID")}>
              <Input
                required
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
                required
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
                required
                value={String(draftProvider.base_url ?? "")}
                placeholder="https://api.example.com/v1"
                onChange={(event) => setDraftProvider({ ...draftProvider, base_url: event.target.value })}
              />
            </Field>
            <Field label={<TermHint description="接口访问密钥">API Key</TermHint>}>
              <Input
                required
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
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3">
            <span className="text-[11px] text-slate-500">
              {text("保存后会更新供应商列表，把 API Key 写入密钥库，并立即设为默认模型。", "Saving updates the provider list, writes the API key to the secret vault, and makes it the default model.")}
            </span>
            <div className="flex flex-wrap justify-end gap-2">
              <Button type="button" onClick={closeProviderDialog} disabled={saveMutation.isPending}>
                {text("取消", "Cancel")}
              </Button>
              <Button type="submit" variant="primary" disabled={saveMutation.isPending}>
                {pendingAction === providerActionKey(normalizeProvider(draftProvider)) ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Save className="h-3.5 w-3.5" />
                )}
                {pendingAction === providerActionKey(normalizeProvider(draftProvider))
                  ? text("保存中", "Saving")
                  : text("保存并启用", "Save & Enable")}
              </Button>
            </div>
          </div>
        </form>
      </ConfigDialog>
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
    api_key: String(provider.api_key || "").trim(),
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

function toEditableProvider(provider: ProviderConfig): ProviderConfig {
  const apiKey = String(provider.api_key ?? "").trim();
  return {
    ...emptyProvider,
    ...provider,
    api_key: apiKey === "replace-me" ? "" : apiKey,
  };
}

function providerKey(provider: ProviderConfig) {
  return `${provider.name}:${String(provider.model ?? "default")}`;
}

function providerActionKey(provider: ProviderConfig) {
  return `provider:${provider.name}:${String(provider.model ?? "default")}`;
}

function mergePresetAndConfiguredProviders(configuredProviders: ProviderConfig[]) {
  const merged = new Map<string, ProviderConfig>();
  for (const preset of providerPresets) {
    const configured = configuredProviders.find((provider) => providerKey(provider) === providerKey(preset));
    merged.set(providerKey(preset), configured ? { ...preset, ...configured } : preset);
  }
  for (const provider of configuredProviders) {
    if (!merged.has(providerKey(provider))) {
      merged.set(providerKey(provider), provider);
    }
  }
  return Array.from(merged.values());
}

function providerHasUsableApiKey(provider: ProviderConfig) {
  if (provider.api_key_configured === true) {
    return true;
  }
  const apiKey = String(provider.api_key ?? "").trim();
  return apiKey.length > 0 && apiKey !== "replace-me";
}

function providerDisplayName(provider: ProviderConfig) {
  return String(provider.label || provider.model || provider.name);
}

function vendorKey(provider: ProviderConfig) {
  const name = String(provider.name ?? "").toLowerCase();
  const baseUrl = String(provider.base_url ?? "").toLowerCase();
  if (name.startsWith("deepseek") || baseUrl.includes("deepseek")) return "deepseek";
  if (name.startsWith("openai") || baseUrl.includes("openai")) return "openai";
  if (name.startsWith("kimi") || name.includes("moonshot") || baseUrl.includes("moonshot")) return "kimi";
  if (name.startsWith("z-ai") || name.startsWith("zai") || baseUrl.includes("z.ai")) return "z-ai";
  return String(provider.name || provider.label || "custom-provider").trim().toLowerCase();
}

function vendorDisplayName(provider: ProviderConfig) {
  const labels: Record<string, string> = {
    deepseek: "DeepSeek",
    openai: "OpenAI",
    kimi: "Kimi",
    "z-ai": "Z.AI",
  };
  return labels[vendorKey(provider)] ?? String(provider.label || provider.name || "自定义供应商");
}

function groupProvidersByVendor(providers: ProviderConfig[]): ProviderGroup[] {
  const groups = new Map<string, ProviderGroup>();
  for (const provider of providers) {
    const key = vendorKey(provider);
    const existing = groups.get(key);
    if (existing) {
      existing.providers.push(provider);
      continue;
    }
    groups.set(key, {
      key,
      label: vendorDisplayName(provider),
      providers: [provider],
    });
  }
  return Array.from(groups.values()).map((group) => ({
    ...group,
    providers: [...group.providers].sort((left, right) =>
      String(left.model ?? left.name).localeCompare(String(right.model ?? right.name), "zh-CN"),
    ),
  }));
}

function modelKindLabel(provider: ProviderConfig) {
  const explicit = String(provider.model_kind ?? "").trim();
  if (explicit) return normalizeModelKind(explicit);
  const model = String(provider.model ?? provider.label ?? provider.name).toLowerCase();
  return normalizeModelKind(model);
}

function normalizeModelKind(value: string) {
  const normalized = value.toLowerCase();
  if (value.includes("图片") || normalized.includes("vision") || normalized.includes("image") || normalized.includes("dall") || value.includes("绘图")) {
    return "图片模型";
  }
  if (value.includes("向量") || normalized.includes("embed") || normalized.includes("vector")) return "向量模型";
  if (
    value.includes("推理") ||
    normalized.includes("reason") ||
    normalized.includes("thinking") ||
    normalized.includes("pro") ||
    normalized.includes("r1") ||
    normalized.includes("o1") ||
    normalized.includes("o3") ||
    normalized.includes("gpt-5") ||
    normalized.includes("k2") ||
    normalized.includes("glm-5")
  ) {
    return "推理模型";
  }
  return "文本模型";
}

function modelKindTone(kind: string): BadgeTone {
  if (kind.includes("推理")) return "purple";
  if (kind.includes("图片")) return "info";
  if (kind.includes("向量")) return "running";
  return "neutral";
}

function secretSourceSummary(providers: ProviderConfig[]) {
  return Array.from(
    new Set(
      providers
        .map((provider) =>
          provider.api_key_source ? secretSourceLabel(String(provider.api_key_source)) : null,
        )
        .filter((source): source is string => Boolean(source)),
    ),
  );
}

function secretSourceLabel(source: string) {
  const normalized = source.trim();
  if (!normalized || normalized === "missing" || normalized === "not_configured") return null;
  const labels: Record<string, string> = {
    stored_secret_user: "用户密钥",
    stored_secret_org: "组织密钥",
    stored_secret: "密钥库",
    db_user: "用户密钥",
    db_org: "组织密钥",
    env_legacy: "Env 兼容",
    legacy_setting: "旧配置",
  };
  return labels[normalized] ?? normalized;
}

function groupSecretStatus(providers: ProviderConfig[]): { label: string; tone: BadgeTone } {
  const configuredCount = providers.filter(providerHasUsableApiKey).length;
  if (configuredCount === 0) return { label: "未配置", tone: "warning" };
  if (configuredCount === providers.length) return { label: "已配置", tone: "success" };
  return { label: "部分已配置", tone: "warning" };
}

function modelHealthItems(providers: ProviderConfig[], refreshedItems: ModelHealth[]) {
  const refreshed = new Map(refreshedItems.map((item) => [`${item.provider}:${item.model}`, item]));
  return providers.map((provider) => {
    const providerName = String(provider.name);
    const model = String(provider.model ?? "default");
    const item = refreshed.get(`${providerName}:${model}`);
    if (item) return item;
    const lastHealth = provider.last_health && typeof provider.last_health === "object"
      ? (provider.last_health as Partial<ModelHealth> & Record<string, unknown>)
      : {};
    return {
      provider: providerName,
      model,
      status: String(lastHealth.status ?? provider.status ?? "unknown"),
      mode: String(lastHealth.mode ?? (providerHasUsableApiKey(provider) ? "configured" : "missing_key")),
      checked_at: String(lastHealth.checked_at ?? ""),
      latency_ms: Number(lastHealth.latency_ms ?? 0),
      error_message:
        typeof lastHealth.error_message === "string"
          ? lastHealth.error_message
          : null,
      circuit_status: "closed",
      circuit_open_until: null,
      consecutive_failures: 0,
    };
  });
}

function defaultOfficialStatusItems(): ModelOfficialStatus[] {
  const now = new Date(0).toISOString();
  return [
    {
      provider: "openai",
      label: "OpenAI",
      status: "unknown",
      indicator: "unknown",
      description: "点击刷新后查询官方状态",
      page_url: "https://status.openai.com/",
      api_url: "https://status.openai.com/api/v2/status.json",
      checked_at: now,
      updated_at: null,
      error_message: null,
    },
    {
      provider: "deepseek",
      label: "DeepSeek",
      status: "unknown",
      indicator: "unknown",
      description: "点击刷新后查询官方状态",
      page_url: "https://status.deepseek.com/",
      api_url: "https://status.deepseek.com/",
      checked_at: now,
      updated_at: null,
      error_message: null,
    },
  ];
}

function ModelHealthStrip({ item }: { item: ModelHealth }) {
  const status = String(item.status || "unknown");
  const detail = item.error_message || `${statusLabel(String(item.mode))} · ${formatLatency(item.latency_ms)}`;
  return (
    <div className="flex min-w-0 items-center gap-2 rounded-md border border-slate-100 bg-slate-50 px-2 py-1.5">
      <span className={`h-6 w-1 rounded-full ${statusBarClass(status)}`} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center gap-1.5">
          <span className="truncate font-mono text-[11px] font-medium text-slate-900">{item.model}</span>
          <Badge tone={modelHealthTone(status)}>{statusLabel(status)}</Badge>
        </div>
        <div className="mt-0.5 truncate text-[10px] text-slate-500" title={detail}>
          {detail}
        </div>
      </div>
    </div>
  );
}

function OfficialStatusStrip({ item }: { item: ModelOfficialStatus }) {
  const detail = item.error_message ? "官方状态暂不可查" : item.description;
  return (
    <div className="flex min-w-0 items-center gap-2 rounded-md border border-slate-100 bg-slate-50 px-2 py-1.5">
      <span className={`h-6 w-1 rounded-full ${statusBarClass(item.status)}`} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center justify-between gap-2">
          <span className="truncate text-[11px] font-medium text-slate-900">{item.label}</span>
          <a
            href={item.page_url}
            target="_blank"
            rel="noreferrer"
            aria-label={`${item.label} 官方状态页`}
            className="inline-flex shrink-0 items-center gap-1 text-[10px] text-slate-500 hover:text-slate-900"
          >
            Status
            <ExternalLink className="h-3 w-3" />
          </a>
        </div>
        <div className="mt-0.5 flex min-w-0 items-center gap-1.5">
          <Badge tone={officialStatusTone(item.status)}>{officialStatusLabel(item.status)}</Badge>
          <span className="truncate text-[10px] text-slate-500" title={detail}>
            {detail}
          </span>
        </div>
      </div>
    </div>
  );
}

function ProviderEndpointSummary({ providers }: { providers: ProviderConfig[] }) {
  const endpoints = providerEndpointValues(providers);
  if (endpoints.length === 0) {
    return <div className="mt-1 font-mono text-[11px] text-slate-500">openai · ...</div>;
  }
  return (
    <div
      className="mt-1 flex max-w-[260px] flex-col gap-1 text-[11px] text-slate-500"
      title={providerEndpointTitle(providers)}
    >
      {endpoints.map((endpoint) => (
        <div key={`${endpoint.apiFormat}:${endpoint.baseUrl}`} className="flex min-w-0 items-center gap-1">
          <span className="shrink-0 font-mono">{endpoint.apiFormat}</span>
          <span>·</span>
          <ProviderEndpointAnchor baseUrl={endpoint.baseUrl} />
        </div>
      ))}
    </div>
  );
}

function providerEndpointTitle(providers: ProviderConfig[]) {
  return providers
    .map((provider) => `${String(provider.model ?? "default")} · ${providerEndpointValue(provider)}`)
    .join("\n");
}

function providerEndpointValues(providers: ProviderConfig[]) {
  const endpoints = new Map<string, { apiFormat: string; baseUrl: string }>();
  for (const provider of providers) {
    const apiFormat = String(provider.api_format ?? "openai");
    const baseUrl = providerBaseUrl(provider);
    endpoints.set(`${apiFormat}:${baseUrl}`, { apiFormat, baseUrl });
  }
  return Array.from(endpoints.values());
}

function providerEndpointValue(provider: ProviderConfig) {
  return `${String(provider.api_format ?? "openai")} · ${providerBaseUrl(provider)}`;
}

function providerBaseUrl(provider: ProviderConfig) {
  return String(provider.base_url ?? "").trim() || "...";
}

function ProviderEndpointLink({ provider }: { provider: ProviderConfig }) {
  return <ProviderEndpointAnchor baseUrl={providerBaseUrl(provider)} />;
}

function ProviderEndpointAnchor({ baseUrl }: { baseUrl: string }) {
  if (!isHttpUrl(baseUrl)) {
    return <span className="font-mono">{baseUrl}</span>;
  }
  return (
    <a
      href={baseUrl}
      target="_blank"
      rel="noreferrer"
      className="inline-flex min-w-0 items-center gap-1 font-mono text-slate-600 underline-offset-2 hover:text-slate-950 hover:underline"
    >
      <span className="truncate">{baseUrl}</span>
      <ExternalLink className="h-3 w-3 shrink-0" />
    </a>
  );
}

function isHttpUrl(value: string) {
  return /^https?:\/\//i.test(value);
}

function isDeprecatedPricingSource(item: ModelPricingSourceItem) {
  const key = `${item.mapped_provider || item.provider}/${item.mapped_model || item.model}`.toLowerCase();
  return key === "moonshot/moonshot-v1-8k" || key === "z-ai/glm-5-turbo";
}

function formatLimit(value: unknown, unit: string) {
  if (value === undefined || value === null || value === "") return `... ${unit}`;
  return `${Number(value).toLocaleString("zh-CN")} ${unit}`;
}

function modelHealthTone(status: string): BadgeTone {
  const normalized = status.toLowerCase();
  if (["healthy", "success", "ok", "closed", "operational"].includes(normalized)) return "success";
  if (["degraded", "warning", "open", "timeout", "maintenance"].includes(normalized)) return "warning";
  if (["unhealthy", "failed", "error"].includes(normalized)) return "failed";
  return "neutral";
}

function officialStatusTone(status: string): BadgeTone {
  const normalized = status.toLowerCase();
  if (normalized === "operational") return "success";
  if (normalized === "degraded" || normalized === "maintenance") return "warning";
  if (normalized === "outage") return "failed";
  return "neutral";
}

function officialStatusLabel(status: string) {
  const labels: Record<string, string> = {
    operational: "正常",
    degraded: "降级",
    outage: "中断",
    maintenance: "维护",
    unknown: "未知",
  };
  return labels[status] ?? status;
}

function statusBarClass(status: string) {
  const normalized = status.toLowerCase();
  if (["healthy", "success", "ok", "closed", "operational"].includes(normalized)) return "bg-emerald-500";
  if (["degraded", "warning", "open", "timeout", "maintenance"].includes(normalized)) return "bg-amber-500";
  if (["unhealthy", "failed", "error", "outage"].includes(normalized)) return "bg-rose-500";
  return "bg-slate-300";
}

function formatLatency(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "未探测";
  return `${Math.round(value)} ms`;
}

function modelHealthErrorText(error: unknown) {
  const message = error instanceof Error ? error.message : String(error || "");
  return message ? `状态刷新失败：${message}` : "状态刷新失败，请稍后重试。";
}

function modelPricingErrorText(error: unknown) {
  const message = error instanceof Error ? error.message : String(error || "");
  if (!message) return "成本来源同步失败，请稍后重试。";
  if (message.includes("404")) {
    return "价格来源接口返回 404，当前后端暂未提供内置成本来源；模型切换和保存不受影响。";
  }
  return `成本来源同步失败：${message}`;
}

function PricingSourceRow({ item }: { item: ModelPricingSourceItem }) {
  return (
    <tr className="border-t border-slate-100">
      <Td>
        <div className="text-[13px] font-medium leading-5 text-slate-900">{item.display_name}</div>
        <div className="mt-1 font-mono text-[11px] text-slate-500">{item.mapped_model}</div>
        <div className="mt-1 text-[11px] text-slate-500">
          {item.context_window_tokens ? `上下文 ${item.context_window_tokens.toLocaleString("zh-CN")}` : "上下文 -"}
          {item.max_output_tokens ? ` / 最大输出 ${item.max_output_tokens.toLocaleString("zh-CN")}` : ""}
        </div>
      </Td>
      <Td className="font-mono leading-5">
        <div>输入 {formatPrice(item.input_per_1m, item.currency)}</div>
        <div className="mt-1 text-slate-500">缓存输入 {formatPrice(item.cached_input_per_1m, item.currency)}</div>
        <div className="mt-1">输出 {formatPrice(item.output_per_1m, item.currency)}</div>
      </Td>
      <Td className="font-mono leading-5">
        <div>输入 {formatUsdSource(item.prompt_per_1k_usd)}</div>
        <div className="mt-1 text-slate-500">缓存输入 {formatUsdSource(item.cache_prompt_per_1k_usd)}</div>
        <div className="mt-1">输出 {formatUsdSource(item.completion_per_1k_usd)}</div>
      </Td>
      <Td>
        <Badge tone={item.blocks_usd_rollup ? "warning" : "success"}>
          {pricingStatusLabel(item.verification_status)}
        </Badge>
        {item.blocks_usd_rollup ? (
          <div className="mt-1 text-[10px] text-amber-600">不计入汇总</div>
        ) : null}
        {item.valid_until ? (
          <div className="mt-1 text-[11px] text-slate-500">有效至 {formatShortDate(item.valid_until)}</div>
        ) : null}
      </Td>
      <Td>
        <div className="text-slate-900">{item.region ?? "-"}</div>
        <div className="mt-1 text-slate-500">{pricingModeLabel(item)}</div>
        <div className="mt-1 text-slate-500">{item.token_tier ?? "-"}</div>
      </Td>
      <Td>
        <a
          href={item.official_url}
          target="_blank"
          rel="noreferrer"
          aria-label={`官方来源 ${item.display_name}`}
          className="inline-flex items-center gap-1 text-slate-700 hover:text-slate-950"
        >
          {item.source_hash.slice(0, 8)}
          <ExternalLink className="h-3 w-3" />
        </a>
        <div className="mt-1 max-w-72 truncate text-[11px] text-slate-500">{item.notes ?? item.source_excerpt}</div>
      </Td>
    </tr>
  );
}

function formatPrice(value: string | null, currency: string) {
  return value ? `${currency} ${value}` : "-";
}

function formatUsdSource(value: string | null) {
  return value ? `$${value}` : "-";
}

function pricingStatusLabel(status: string) {
  const labels: Record<string, string> = {
    verified: "已验证",
    price_unverified: "价格未验证",
    sku_ambiguous: "SKU 模糊",
    currency_conversion_required: "需要汇率",
    stale: "已过期",
    missing_pricing: "缺失价格",
    invalid_pricing: "价格无效",
  };
  return labels[status] ?? status;
}

function pricingModeLabel(item: ModelPricingSourceItem) {
  if (!item.mode) return "-";
  const normalized = item.mode.toLowerCase();
  if (normalized === "openai-compatible") return "兼容聊天接口";
  if (normalized === "standard") return "标准文本模式";
  if (normalized === "text") return "文本模式";
  return item.mode;
}

function Metric({ label, value }: { label: ReactNode; value: string }) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50 p-2.5">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 min-w-0 truncate font-mono text-[11px] text-slate-900" title={value}>{value}</div>
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
