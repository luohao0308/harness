import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AppWindow,
  ArrowLeft,
  ChevronRight,
  Download,
  ExternalLink,
  FolderOpen,
  KeyRound,
  Loader2,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Terminal,
  Trash2,
} from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { useConfirmDialog } from "../../../components/ui/confirm-dialog";
import { Input } from "../../../components/ui/input";
import { getDesktopLocalRuntimeApi } from "../../../lib/local-runtime";
import { cn } from "../../../lib/utils";
import { getLocalRuntimeModelStatus } from "../../tasks/api";

type DesktopSettingsSection =
  | "general"
  | "models"
  | "permissions"
  | "workspace"
  | "terminal"
  | "web"
  | "updates";

const SETTINGS_SECTIONS: Array<{
  id: DesktopSettingsSection;
  label: string;
  description: string;
  icon: typeof Settings2;
}> = [
  { id: "general", label: "常规", description: "启动与桌面运行", icon: Settings2 },
  { id: "models", label: "模型与密钥", description: "默认模型与安全凭据", icon: KeyRound },
  { id: "permissions", label: "权限", description: "工具审批和沙箱策略", icon: ShieldCheck },
  { id: "workspace", label: "工作区", description: "本地目录与文件访问", icon: FolderOpen },
  { id: "terminal", label: "终端", description: "集成终端工作区", icon: Terminal },
  { id: "web", label: "网页扩展", description: "浏览器观察与协作入口", icon: AppWindow },
  { id: "updates", label: "更新", description: "版本检查与安装", icon: Download },
];

export function DesktopSettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const requestedSection = searchParams.get("section") as DesktopSettingsSection | null;
  const selectedSection = SETTINGS_SECTIONS.some((section) => section.id === requestedSection)
    ? requestedSection!
    : "general";
  const visibleSections = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return SETTINGS_SECTIONS;
    return SETTINGS_SECTIONS.filter((section) =>
      `${section.label} ${section.description} ${section.id}`.toLowerCase().includes(normalized),
    );
  }, [query]);
  const activeSection = visibleSections.some((section) => section.id === selectedSection)
    ? selectedSection
    : visibleSections[0]?.id ?? null;

  return (
    <div data-testid="desktop-settings-space" className="flex h-screen min-h-0 flex-col bg-slate-50/70 text-slate-800 md:grid md:grid-cols-[248px_minmax(0,1fr)]">
      <aside className="border-b border-slate-200 bg-white p-3 md:min-h-0 md:border-b-0 md:border-r">
          <Link
            to="/agents/default/workspace"
            className="mb-3 inline-flex h-8 items-center gap-2 rounded-md px-2 text-xs font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-950"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            返回应用
          </Link>
          <label className="relative block">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-400" />
            <Input
              aria-label="搜索设置"
              className="h-8 w-full pl-8 text-xs"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索设置"
            />
          </label>
          <nav aria-label="桌面设置分类" className="mt-2 flex gap-1 overflow-x-auto pb-1 md:grid md:overflow-visible md:pb-0">
            {visibleSections.map((section) => {
              const Icon = section.icon;
              const selected = section.id === activeSection;
              return (
                <button
                  key={section.id}
                  type="button"
                  onClick={() => setSearchParams({ section: section.id })}
                  className={cn(
                    "flex min-h-11 min-w-[150px] items-center gap-2 rounded-md px-2.5 text-left text-xs transition-colors md:min-w-0",
                    selected
                      ? "bg-slate-100 font-medium text-slate-950"
                      : "text-slate-600 hover:bg-slate-50 hover:text-slate-900",
                  )}
                  aria-current={selected ? "page" : undefined}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  <span className="min-w-0">
                    <span className="block truncate">{section.label}</span>
                    <span className="mt-0.5 hidden truncate text-[10px] font-normal text-slate-400 md:block">
                      {section.description}
                    </span>
                  </span>
                </button>
              );
            })}
          </nav>
          {visibleSections.length === 0 ? (
            <p className="mt-3 px-2 text-xs text-slate-500">没有匹配的设置</p>
          ) : null}
      </aside>

      <main className="min-h-0 overflow-y-auto p-4 sm:p-6 lg:p-8">
        <div className="mx-auto max-w-[920px]">
          {activeSection ? (
            <>
              <SectionHeading section={activeSection} />
              <DesktopSettingsSectionContent section={activeSection} />
            </>
          ) : (
            <div className="py-12 text-center text-sm text-slate-500">没有匹配的设置</div>
          )}
        </div>
      </main>
    </div>
  );
}

function SectionHeading({ section }: { section: DesktopSettingsSection }) {
  const item = SETTINGS_SECTIONS.find((candidate) => candidate.id === section)!;
  return (
    <header className="mb-5">
      <h1 className="text-lg font-semibold text-slate-950">{item.label}</h1>
      <p className="mt-1 text-xs leading-5 text-slate-500">{item.description}</p>
    </header>
  );
}

function DesktopSettingsSectionContent({ section }: { section: DesktopSettingsSection }) {
  switch (section) {
    case "models":
      return <ModelAndKeySettings />;
    case "permissions":
      return (
        <SettingsGroup title="运行权限">
          <LinkSettingRow
            title="工具策略"
            description="查看风险等级、审批、沙箱和审计规则。"
            to="/settings/policies"
          />
        </SettingsGroup>
      );
    case "workspace":
      return <WorkspaceSettings />;
    case "terminal":
      return (
        <SettingsGroup title="终端">
          <LinkSettingRow title="打开终端工作区" description="使用当前 Harness 运行时的集成终端。" to="/terminal" />
        </SettingsGroup>
      );
    case "web":
      return <WebExtensionSettings />;
    case "updates":
      return <UpdateSettings />;
    default:
      return <GeneralSettings />;
  }
}

function GeneralSettings() {
  const desktopApi = window.desktopApi;
  const startup = useQuery({
    queryKey: ["desktop-settings", "startup"],
    queryFn: () => desktopApi?.system?.getStartupEnabled?.(),
    enabled: Boolean(desktopApi?.system?.getStartupEnabled),
  });
  const toggle = useMutation({
    mutationFn: async () => {
      if (!desktopApi?.system?.setStartupEnabled) throw new Error("启动设置不可用");
      return desktopApi.system.setStartupEnabled(!Boolean(startup.data));
    },
    onSuccess: (enabled) => startup.refetch().then(() => enabled),
  });
  return (
    <SettingsGroup title="启动">
      <SettingRow title="登录时启动 Harness" description="让桌面运行时在登录后保持可用。">
        <button
          type="button"
          role="switch"
          aria-checked={Boolean(startup.data)}
          aria-label="登录时启动 Harness"
          disabled={!desktopApi?.system?.setStartupEnabled || toggle.isPending}
          onClick={() => toggle.mutate()}
          className={cn(
            "relative h-5 w-9 rounded-full transition-colors disabled:opacity-50",
            startup.data ? "bg-slate-900" : "bg-slate-300",
          )}
        >
          <span className={cn("absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform", startup.data ? "translate-x-4" : "translate-x-0.5")} />
        </button>
      </SettingRow>
    </SettingsGroup>
  );
}

function ModelAndKeySettings() {
  const queryClient = useQueryClient();
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [modelsBaseUrl, setModelsBaseUrl] = useState("");
  const [initialized, setInitialized] = useState(false);
  const baseUrlDirty = useRef(false);
  const modelDirty = useRef(false);
  const [feedback, setFeedback] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const localRuntime = getDesktopLocalRuntimeApi();
  const { confirm, confirmDialog } = useConfirmDialog();
  const status = useQuery({
    queryKey: ["local-runtime", "model-status"],
    queryFn: getLocalRuntimeModelStatus,
    retry: false,
  });

  useEffect(() => {
    if (!status.data || initialized) return;
    if (!baseUrlDirty.current) setBaseUrl(status.data.base_url);
    if (!modelDirty.current) setModel(status.data.model);
    setInitialized(true);
  }, [initialized, status.data]);

  const discoverModels = async () => {
    if (!localRuntime?.discoverModels) throw new Error("MODEL_DISCOVERY_UNAVAILABLE");
    const normalizedBaseUrl = validateBaseUrl(baseUrl);
    const result = await localRuntime.discoverModels({
      baseUrl: normalizedBaseUrl,
      ...(apiKey.trim() ? { apiKey: apiKey.trim() } : {}),
    });
    if (!Array.isArray(result.models) || result.models.some((item) => typeof item !== "string")) {
      throw new Error("MODEL_LIST_FORMAT_INVALID");
    }
    const durationMs =
      typeof result.durationMs === "number" && Number.isFinite(result.durationMs)
        ? result.durationMs
        : typeof result.latencyMs === "number" && Number.isFinite(result.latencyMs)
          ? result.latencyMs
          : 0;
    return {
      models: Array.from(new Set(result.models.map((item) => item.trim()).filter(Boolean))),
      durationMs,
    };
  };

  const applyDiscoveryResult = (result: { models: string[]; durationMs: number }) => {
    setModels(result.models);
    setModelsBaseUrl(normalizeBaseUrlForComparison(baseUrl));
    if (!model.trim() && result.models[0]) setModel(result.models[0]);
    setFeedback({
      tone: "success",
      text: `连接成功，用时 ${Math.max(0, Math.round(result.durationMs))} 毫秒，获取到 ${result.models.length} 个模型。`,
    });
  };

  const testConnection = useMutation({
    mutationFn: discoverModels,
    onSuccess: applyDiscoveryResult,
    onError: (error) => setFeedback({ tone: "error", text: modelConnectionErrorMessage(error) }),
  });
  const refreshModels = useMutation({
    mutationFn: discoverModels,
    onSuccess: applyDiscoveryResult,
    onError: (error) => setFeedback({ tone: "error", text: modelConnectionErrorMessage(error) }),
  });
  const save = useMutation({
    mutationFn: async () => {
      if (!localRuntime?.saveModelConfiguration) throw new Error("MODEL_CONFIGURATION_UNAVAILABLE");
      const nextStatus = await localRuntime.saveModelConfiguration({
        baseUrl: validateBaseUrl(baseUrl),
        model: model.trim(),
        ...(modelsBaseUrl === normalizeBaseUrlForComparison(baseUrl) && models.includes(model.trim())
          ? { models }
          : {}),
        ...(apiKey.trim() ? { apiKey: apiKey.trim() } : {}),
      });
      queryClient.setQueryData(["local-runtime", "model-status"], nextStatus);
      return nextStatus;
    },
    onSuccess: async (nextStatus) => {
      setBaseUrl(nextStatus.base_url);
      setModel(nextStatus.model);
      if (modelsBaseUrl !== normalizeBaseUrlForComparison(nextStatus.base_url) || !models.includes(nextStatus.model)) {
        setModels([]);
        setModelsBaseUrl("");
      }
      setApiKey("");
      setFeedback({ tone: "success", text: "模型配置已保存，新的任务将使用当前默认模型。" });
      await status.refetch();
      await queryClient.invalidateQueries({ queryKey: ["settings", "models"] });
    },
    onError: (error) => setFeedback({ tone: "error", text: modelConfigurationErrorMessage(error) }),
  });
  const modelState = status.data?.state ?? "setup_required";
  const remove = useMutation({
    mutationFn: async () => {
      if (!localRuntime?.deleteModelApiKey) throw new Error("桌面密钥清除接口不可用");
      const nextStatus = await localRuntime.deleteModelApiKey();
      queryClient.setQueryData(["local-runtime", "model-status"], nextStatus);
      await status.refetch();
      return nextStatus;
    },
    onSuccess: async () => {
      setFeedback({ tone: "success", text: "API Key 已清除。" });
      await queryClient.invalidateQueries({ queryKey: ["settings", "models"] });
    },
    onError: (error) => setFeedback({ tone: "error", text: modelConfigurationErrorMessage(error) }),
  });

  async function confirmRemove() {
    const confirmed = await confirm({
      title: "清除模型 API Key？",
      description: "清除后，新的 Agent 与 Task 执行会要求重新配置模型密钥。",
      confirmText: "清除",
      variant: "danger",
    });
    if (confirmed) remove.mutate();
  }

  const storageNotice = modelSecretStorageNotice(status.data?.secret_storage);
  const discovering = testConnection.isPending || refreshModels.isPending;
  const canSave = Boolean(baseUrl.trim() && model.trim() && localRuntime?.saveModelConfiguration);
  return (
    <div className="space-y-4">
      <SettingsGroup title="模型连接">
        <SettingRow title="Base URL" description="OpenAI 兼容 API 根地址，通常包含 /v1。">
          <div className="flex w-full min-w-0 flex-col gap-2 sm:w-[min(52vw,520px)] sm:flex-row">
            <Input
              aria-label="Base URL"
              type="url"
              inputMode="url"
              value={baseUrl}
              onChange={(event) => {
                baseUrlDirty.current = true;
                const nextBaseUrl = event.target.value;
                setBaseUrl(nextBaseUrl);
                if (normalizeBaseUrlForComparison(nextBaseUrl) !== modelsBaseUrl) {
                  setModels([]);
                  setModelsBaseUrl("");
                }
              }}
              placeholder="https://api.example.com/v1"
              className="min-w-0 flex-1 font-mono text-xs"
            />
            <Button
              type="button"
              className="shrink-0"
              disabled={!baseUrl.trim() || discovering || save.isPending}
              onClick={() => testConnection.mutate()}
            >
              {testConnection.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              检测连接
            </Button>
          </div>
        </SettingRow>
        <SettingRow title="默认模型" description="可直接输入模型 ID，或从远端模型列表选择。">
          <div className="flex w-full min-w-0 gap-2 sm:w-[min(52vw,520px)]">
            <Input
              aria-label="默认模型"
              list="desktop-discovered-models"
              value={model}
              onChange={(event) => {
                modelDirty.current = true;
                setModel(event.target.value);
              }}
              placeholder="输入或选择模型"
              className="min-w-0 flex-1 font-mono text-xs"
            />
            <datalist id="desktop-discovered-models">
              {models.map((item) => <option key={item} value={item} />)}
            </datalist>
            <Button
              type="button"
              variant="ghost"
              className="w-8 shrink-0 px-0"
              aria-label="获取模型列表"
              title="获取模型列表"
              disabled={!baseUrl.trim() || discovering || save.isPending}
              onClick={() => refreshModels.mutate()}
            >
              {refreshModels.isPending
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <RefreshCw className="h-3.5 w-3.5" />}
            </Button>
          </div>
        </SettingRow>
        <SettingRow title="API Key" description="留空会保留当前密钥；输入新值会安全替换。">
          <div className="w-full sm:w-[min(52vw,520px)]">
            <Input
              aria-label="API Key"
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="sk-..."
              className="w-full min-w-0 font-mono text-xs"
            />
            <p className="mt-1 text-[11px] leading-5 text-slate-500">密钥只通过 Electron 安全存储写入，不会进入浏览器存储。</p>
            <p className={cn("text-[11px] leading-5", storageNotice.tone)}>{storageNotice.text}</p>
          </div>
        </SettingRow>
        <div className="flex flex-col gap-2 px-3 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0" aria-live="polite">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={modelState === "healthy" ? "success" : modelState === "error" ? "failed" : modelState === "configured" ? "info" : "warning"}>
                {modelStateLabel(modelState)}
              </Badge>
              <span className="break-all text-[11px] text-slate-500">{status.data?.provider || "Harness 本地运行时"}</span>
            </div>
            {feedback ? (
              <p className={cn("mt-1 text-xs leading-5", feedback.tone === "error" ? "text-red-600" : "text-emerald-700")} role={feedback.tone === "error" ? "alert" : "status"}>
                {feedback.text}
              </p>
            ) : null}
          </div>
          <Button
            type="button"
            variant="primary"
            className="shrink-0 self-start sm:self-auto"
            disabled={!canSave || save.isPending || discovering}
            onClick={() => save.mutate()}
          >
            {save.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <KeyRound className="h-3.5 w-3.5" />}
            保存
          </Button>
        </div>
        <SettingRow title="清除 API Key" description="移除 Desktop 安全存储中的当前模型凭据。">
          <Button type="button" variant="danger" disabled={!localRuntime?.deleteModelApiKey || remove.isPending} onClick={() => void confirmRemove()}>
            {remove.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
            清除
          </Button>
        </SettingRow>
        <LinkSettingRow title="高级模型设置" description="管理供应商、模型选择、限流和健康检查。" to="/settings/models" />
      </SettingsGroup>
      {confirmDialog}
    </div>
  );
}

function validateBaseUrl(value: string) {
  const normalized = value.trim().replace(/\/+$/, "");
  try {
    const parsed = new URL(normalized);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") throw new Error();
    if (parsed.username || parsed.password || parsed.search || parsed.hash) throw new Error();
    if (parsed.protocol === "http:") {
      const hostname = parsed.hostname.toLowerCase();
      const isLoopback = hostname === "localhost"
        || hostname === "[::1]"
        || /^127(?:\.\d{1,3}){3}$/.test(hostname);
      if (!isLoopback) throw new Error();
    }
  } catch {
    throw new Error("INVALID_BASE_URL");
  }
  return normalized;
}

function normalizeBaseUrlForComparison(value: string) {
  return value.trim().replace(/\/+$/, "");
}

function modelConnectionErrorMessage(error: unknown) {
  const message = error instanceof Error ? error.message : String(error ?? "");
  const normalized = message.toLowerCase();
  if (normalized.includes("invalid_model_base_url") || normalized.includes("invalid_base_url") || normalized.includes("invalid url")) {
    return "Base URL 无效，请填写以 http:// 或 https:// 开头的 API 根地址。";
  }
  if (normalized.includes("model_api_key_required") || normalized.includes("model_setup_required") || normalized.includes("api key required") || normalized.includes("missing api key")) {
    return "缺少 API Key，请输入密钥后重试。";
  }
  if (normalized.includes("model_discovery_auth_error") || /(^|\D)(401|403)(\D|$)/.test(normalized) || normalized.includes("unauthorized") || normalized.includes("authentication") || normalized.includes("invalid api key")) {
    return "API Key 验证失败，请检查密钥是否有效。";
  }
  if (normalized.includes("timeout") || normalized.includes("timed out") || normalized.includes("etimedout")) {
    return "连接超时，请检查 Base URL 和网络后重试。";
  }
  if (normalized.includes("model_discovery_response_too_large")) {
    return "模型列表响应过大，请检查 Base URL 是否指向 OpenAI 兼容接口。";
  }
  if (normalized.includes("model_discovery_invalid_response") || normalized.includes("model_list_format_invalid") || normalized.includes("model list format") || normalized.includes("incompatible")) {
    return "服务返回的模型列表格式不兼容，请确认这是 OpenAI 兼容接口。";
  }
  if (normalized.includes("model_discovery_unavailable")) {
    return "当前桌面版本不支持获取模型列表，请更新应用后重试。";
  }
  if (normalized.includes("model_discovery_upstream_error") || normalized.includes("fetch failed") || normalized.includes("econnrefused") || normalized.includes("enotfound") || normalized.includes("network") || normalized.includes("unreachable")) {
    return "无法连接到模型服务，请检查 Base URL 和网络。";
  }
  return "模型连接检测失败，请检查 Base URL、API Key 和服务状态。";
}

function modelConfigurationErrorMessage(error: unknown) {
  const message = error instanceof Error ? error.message : String(error ?? "");
  const normalized = message.toLowerCase();
  if (normalized.includes("model_configuration_unavailable")) {
    return "当前桌面版本不支持保存完整模型配置，请更新应用后重试。";
  }
  if (normalized.includes("invalid_model_base_url") || normalized.includes("invalid_base_url")) return modelConnectionErrorMessage(error);
  if (normalized.includes("invalid_model_id")) return "模型 ID 无效，请输入模型服务返回的有效模型 ID。";
  return "模型配置保存失败，请检查输入后重试。";
}

function modelStateLabel(state: string) {
  if (state === "healthy") return "运行正常";
  if (state === "configured") return "已配置";
  if (state === "error") return "需要处理";
  return "尚未配置";
}

function modelSecretStorageNotice(storage: string | undefined) {
  if (storage === "session") {
    return { text: "当前密钥仅保留在本次会话中；重启后需要重新输入。", tone: "text-amber-700" };
  }
  if (storage === "unavailable") {
    return { text: "系统安全存储不可用，无法持久保存模型密钥。", tone: "text-red-600" };
  }
  return { text: "当前密钥由操作系统安全存储持久保护。", tone: "text-slate-500" };
}

function WorkspaceSettings() {
  const desktopApi = window.desktopApi;
  const root = useQuery({
    queryKey: ["desktop-settings", "workspace-root"],
    queryFn: () => desktopApi?.file?.getWorkspaceRoot?.(),
    enabled: Boolean(desktopApi?.file?.getWorkspaceRoot),
  });
  const select = useMutation({
    mutationFn: async () => desktopApi?.file?.selectWorkspaceRoot?.(),
    onSuccess: () => void root.refetch(),
  });
  return (
    <SettingsGroup title="本地文件">
      <SettingRow title="工作区目录" description={root.data?.rootPath || "尚未选择本地目录"}>
        <Button type="button" disabled={!desktopApi?.file?.selectWorkspaceRoot || select.isPending} onClick={() => select.mutate()}>
          <FolderOpen className="h-3.5 w-3.5" />选择目录
        </Button>
      </SettingRow>
      <LinkSettingRow title="高级桌面功能" description="管理 Profile、窗口、同步和插件。" to="/settings/advanced#workspace" />
    </SettingsGroup>
  );
}

function WebExtensionSettings() {
  const open = useMutation({
    mutationFn: async () => {
      const api = getDesktopLocalRuntimeApi();
      if (!api?.openWebExtension) throw new Error("网页扩展暂不可用");
      await api.openWebExtension();
    },
  });
  return (
    <SettingsGroup title="网页扩展">
      <SettingRow title="在浏览器中打开" description="使用一次性会话打开同一个本地 Harness 数据视图。">
        <Button type="button" onClick={() => open.mutate()} disabled={open.isPending}>
          <ExternalLink className="h-3.5 w-3.5" />打开
        </Button>
      </SettingRow>
      {open.isError ? <p className="px-3 py-2 text-xs text-red-600">{open.error.message}</p> : null}
    </SettingsGroup>
  );
}

function UpdateSettings() {
  const desktopApi = window.desktopApi;
  const status = useQuery({
    queryKey: ["desktop-settings", "updates"],
    queryFn: () => desktopApi?.updates?.getStatus?.(),
    enabled: Boolean(desktopApi?.updates?.getStatus),
  });
  const check = useMutation({
    mutationFn: async () => desktopApi?.updates?.check?.(),
    onSuccess: () => void status.refetch(),
  });
  return (
    <SettingsGroup title="应用更新">
      <SettingRow
        title={`Harness ${status.data?.currentVersion || ""}`.trim()}
        description={status.data?.latestVersion ? `可用版本 ${status.data.latestVersion}` : "保持桌面应用和本地运行时一致。"}
      >
        <Button type="button" disabled={!desktopApi?.updates?.check || check.isPending} onClick={() => check.mutate()}>
          {check.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
          检查更新
        </Button>
      </SettingRow>
    </SettingsGroup>
  );
}

function SettingsGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-3 py-2 text-[11px] font-semibold text-slate-500">{title}</div>
      <div className="divide-y divide-slate-100">{children}</div>
    </section>
  );
}

function SettingRow({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-14 flex-col gap-2 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="text-xs font-medium text-slate-900">{title}</div>
        <div className="mt-0.5 break-words text-[11px] leading-5 text-slate-500">{description}</div>
      </div>
      <div className="w-full min-w-0 self-start sm:w-auto sm:max-w-[60%] sm:self-auto">{children}</div>
    </div>
  );
}

function LinkSettingRow({ title, description, to }: { title: string; description: string; to: string }) {
  return (
    <Link to={to} className="flex min-h-14 items-center justify-between gap-3 px-3 py-2.5 hover:bg-slate-50">
      <div className="min-w-0">
        <div className="text-xs font-medium text-slate-900">{title}</div>
        <div className="mt-0.5 text-[11px] leading-5 text-slate-500">{description}</div>
      </div>
      <ChevronRight className="h-4 w-4 shrink-0 text-slate-400" />
    </Link>
  );
}
