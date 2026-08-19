import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Accessibility,
  AppWindow,
  ChevronDown,
  Circle,
  Download,
  FolderOpen,
  Layers3,
  Loader2,
  MonitorCog,
  PlugZap,
  Power,
  RefreshCw,
  Save,
  Send,
  Store,
  TextCursorInput,
  WifiOff,
} from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, type BadgeTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Input, Textarea } from "../../../components/ui/input";
import { VirtualList } from "../../../components/ui/VirtualList";
import {
  createPromptTemplate,
  deletePromptTemplate,
  installPlugin,
  listPluginMarketplace,
  listPromptTemplates,
  uninstallPlugin,
  type PluginMarketplaceItem,
  type PromptTemplatePayload,
} from "../../tasks/api";

type DesktopBridgeState = {
  profiles: DesktopProfile[];
  activeProfileId: string;
  windows: DesktopWindowSummary[];
  localModel: DesktopLocalModelSettings | null;
  localModelHealth: DesktopLocalModelHealth | null;
  offlineTasks: DesktopOfflineTask[];
  offlineAgentRuns: DesktopOfflineAgentRun[];
  offlineAgentSnapshots: Record<string, { approvals: Array<{ status: string; reason: string; decision?: Record<string, unknown>; target?: { path?: string; exists?: boolean; sha256?: string | null; mtimeMs?: number | null; sizeBytes?: number | null }; proposal?: { sha256?: string; sizeBytes?: number } }> }>;
  startupEnabled: boolean | null;
  fileRoot: DesktopFileWatchState | null;
  updateStatus: DesktopUpdateStatus | null;
  syncStatus: DesktopSyncRuntimeStatus | null;
};

type DesktopBridgeHealth = "web-fallback" | "loading" | "connected" | "read-failed";

const EMPTY_BRIDGE_STATE: DesktopBridgeState = {
  profiles: [],
  activeProfileId: "",
  windows: [],
  localModel: null,
  localModelHealth: null,
  offlineTasks: [],
  offlineAgentRuns: [],
  offlineAgentSnapshots: {},
  startupEnabled: null,
  fileRoot: null,
  updateStatus: null,
  syncStatus: null,
};

const CHAPTERS = [
  { id: "workspace", label: "工作区与窗口" },
  { id: "native", label: "系统与发布" },
  { id: "offline", label: "离线执行" },
  { id: "plugins", label: "插件与模板" },
];

export function AdvancedFeaturesPage() {
  const queryClient = useQueryClient();
  const desktopApi = typeof window === "undefined" ? undefined : window.desktopApi;
  const desktopAvailable = Boolean(desktopApi);
  const visibleChapters = CHAPTERS;
  const [bridgeHealth, setBridgeHealth] = useState<DesktopBridgeHealth>(desktopAvailable ? "loading" : "web-fallback");
  const marketplace = useQuery({
    queryKey: ["plugins", "marketplace"],
    queryFn: listPluginMarketplace,
  });
  const promptTemplates = useQuery({
    queryKey: ["plugins", "prompt-templates"],
    queryFn: listPromptTemplates,
  });
  const [bridgeState, setBridgeState] = useState<DesktopBridgeState>(EMPTY_BRIDGE_STATE);
  const [bridgeError, setBridgeError] = useState<string | null>(null);
  const [profileDraft, setProfileDraft] = useState({
    id: "customer-a",
    label: "Customer A",
    apiBaseUrl: "http://localhost:8000",
    authToken: "",
  });
  const [localModelDraft, setLocalModelDraft] = useState({
    enabled: false,
    provider: "ollama" as DesktopLocalModelSettings["provider"],
    baseUrl: "http://127.0.0.1:11434",
    model: "llama3.1",
  });
  const [offlinePrompt, setOfflinePrompt] = useState("整理当前离线工作，列出下一步。");
  const [offlineAgentPrompt, setOfflineAgentPrompt] = useState("检查当前发布证据并给出下一步。");
  const [offlineAgentTool, setOfflineAgentTool] = useState<"none" | "workspace.list_files" | "workspace.read_text" | "workspace.write_text">("none");
  const [offlineAgentPath, setOfflineAgentPath] = useState("README.md");
  const [offlineAgentContent, setOfflineAgentContent] = useState("离线 Agent 审批后写入的内容。");
  const [feedbackDraft, setFeedbackDraft] = useState<Pick<DesktopFeedbackPayload, "title" | "description" | "category">>({
    title: "桌面工作台反馈",
    description: "桌面原生设置已在工作台验证。",
    category: "support",
  });
  const [templateDraft, setTemplateDraft] = useState<PromptTemplatePayload>({
    id: "custom-release-check",
    name: "自定义发布检查",
    description: "生成发布前检查清单。",
    body: "请基于当前 Run 证据输出阻塞项、风险项和上线后观察项。",
    tags: ["release", "check"],
  });

  const refreshBridge = async () => {
    if (!desktopApi) {
      setBridgeHealth("web-fallback");
      return;
    }
    setBridgeHealth("loading");
    setBridgeError(null);
    try {
      const [profiles, windows, localModel, offlineTasks, offlineAgentRuns, startupEnabled, fileRoot, updateStatus, syncStatus] = await Promise.all([
        desktopApi.profile?.list?.(),
        desktopApi.window?.list?.(),
        desktopApi.localModel?.getSettings?.(),
        desktopApi.offline?.listTasks?.(),
        desktopApi.offlineAgent?.listRuns?.(),
        desktopApi.system?.getStartupEnabled?.(),
        desktopApi.file?.getWorkspaceRoot?.(),
        desktopApi.updates?.getStatus?.(),
        desktopApi.sync?.getStatus?.(),
      ]);
      const offlineAgentSnapshots = Object.fromEntries(await Promise.all(
        (offlineAgentRuns?.items ?? []).filter((run) => run.status === "WAITING_APPROVAL").map(async (run) => [run.id, await desktopApi.offlineAgent?.getRun?.(run.id)]),
      ));
      setBridgeState((state) => ({
        profiles: profiles?.profiles ?? [],
        activeProfileId: profiles?.activeProfileId ?? "",
        windows: windows?.items ?? [],
        localModel: localModel ?? null,
        localModelHealth: state.localModelHealth,
        offlineTasks: offlineTasks?.items ?? [],
        offlineAgentRuns: offlineAgentRuns?.items ?? [],
        offlineAgentSnapshots: (offlineAgentSnapshots ?? {}) as DesktopBridgeState["offlineAgentSnapshots"],
        startupEnabled: typeof startupEnabled === "boolean" ? startupEnabled : null,
        fileRoot: fileRoot ?? null,
        updateStatus: updateStatus ?? null,
        syncStatus: syncStatus ?? null,
      }));
      if (localModel) {
        setLocalModelDraft({
          enabled: localModel.enabled,
          provider: localModel.provider,
          baseUrl: localModel.baseUrl,
          model: localModel.model,
        });
      }
      setBridgeHealth("connected");
    } catch (error) {
      setBridgeError(error instanceof Error ? error.message : "桌面桥接不可用");
      setBridgeHealth("read-failed");
    }
  };

  useEffect(() => {
    void refreshBridge();
    const unsubscribe = desktopApi?.events?.onProfileChanged?.(() => {
      void refreshBridge();
    });
    const unsubscribeUpdates = desktopApi?.events?.onUpdateStatus?.((status) => {
      setBridgeState((state) => ({ ...state, updateStatus: status }));
    });
    const unsubscribeSync = desktopApi?.sync?.onStatus?.((status) => {
      setBridgeState((state) => ({ ...state, syncStatus: status }));
    });
    return () => {
      unsubscribe?.();
      unsubscribeUpdates?.();
      unsubscribeSync?.();
    };
    // desktopApi is a stable preload object in Electron; refreshBridge closes over state setters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [desktopAvailable]);

  const installMutation = useMutation({
    mutationFn: (plugin: PluginMarketplaceItem) =>
      plugin.install_state === "installed" ? uninstallPlugin(plugin.id) : installPlugin(plugin.id),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["plugins", "marketplace"] }),
        queryClient.invalidateQueries({ queryKey: ["plugins", "prompt-templates"] }),
      ]);
    },
  });
  const saveTemplateMutation = useMutation({
    mutationFn: () => createPromptTemplate(templateDraft),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["plugins", "prompt-templates"] });
    },
  });
  const deleteTemplateMutation = useMutation({
    mutationFn: deletePromptTemplate,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["plugins", "prompt-templates"] });
    },
  });
  const saveProfileMutation = useMutation({
    mutationFn: async () => {
      if (!desktopApi?.profile?.save) throw new Error("桌面 Profile API 不可用");
      const saved = await desktopApi.profile.save(profileDraft);
      await desktopApi.profile.switch?.(saved.id);
      return saved;
    },
    onSuccess: async () => {
      setProfileDraft((draft) => ({ ...draft, authToken: "" }));
      await refreshBridge();
    },
  });
  const saveLocalModelMutation = useMutation({
    mutationFn: async () => {
      if (!desktopApi?.localModel?.setSettings) throw new Error("本地模型 API 不可用");
      return desktopApi.localModel.setSettings(localModelDraft);
    },
    onSuccess: refreshBridge,
  });
  const testLocalModelMutation = useMutation({
    mutationFn: async () => {
      if (!desktopApi?.localModel?.testConnection) throw new Error("本地模型健康检查 API 不可用");
      return desktopApi.localModel.testConnection();
    },
    onSuccess: (health) => {
      setBridgeState((state) => ({ ...state, localModelHealth: health }));
    },
  });
  const offlineMutation = useMutation({
    mutationFn: async () => {
      if (!desktopApi?.offline?.runSimpleTask) throw new Error("离线任务 API 不可用");
      return desktopApi.offline.runSimpleTask({
        prompt: offlinePrompt,
        useLocalModel: localModelDraft.enabled,
      });
    },
    onSuccess: refreshBridge,
  });
  const promoteOfflineMutation = useMutation({
    mutationFn: async (offlineTaskId: string) => {
      if (!desktopApi?.offline?.promoteResultToPendingAgentTask) throw new Error("离线任务同步 API 不可用");
      return desktopApi.offline.promoteResultToPendingAgentTask(offlineTaskId);
    },
    onSuccess: refreshBridge,
  });
  const offlineAgentMutation = useMutation({
    mutationFn: async () => {
      if (!desktopApi?.offlineAgent?.run) throw new Error("完整离线 Agent API 不可用");
      const toolRequest = offlineAgentTool === "none"
        ? null
        : {
            name: offlineAgentTool,
            input: offlineAgentTool === "workspace.write_text"
              ? { path: offlineAgentPath, content: offlineAgentContent }
              : { path: offlineAgentPath },
          };
      return desktopApi.offlineAgent.run({
        prompt: offlineAgentPrompt,
        useLocalModel: localModelDraft.enabled,
        toolRequest,
      });
    },
    onSuccess: refreshBridge,
  });
  const offlineAgentCancelMutation = useMutation({
    mutationFn: async (runId: string) => {
      if (!desktopApi?.offlineAgent?.cancel) throw new Error("离线 Agent 取消 API 不可用");
      return desktopApi.offlineAgent.cancel(runId);
    },
    onSuccess: refreshBridge,
  });
  const offlineAgentResumeMutation = useMutation({
    mutationFn: async (runId: string) => {
      if (!desktopApi?.offlineAgent?.resume) throw new Error("离线 Agent 恢复 API 不可用");
      return desktopApi.offlineAgent.resume(runId);
    },
    onSuccess: refreshBridge,
  });
  const offlineAgentApprovalMutation = useMutation({
    mutationFn: async ({ approvalId, approved }: { approvalId: string; approved: boolean }) => {
      if (!desktopApi?.offlineAgent?.decideApproval) throw new Error("离线 Agent 审批 API 不可用");
      return desktopApi.offlineAgent.decideApproval(approvalId, approved);
    },
    onSuccess: refreshBridge,
  });
  const runSyncMutation = useMutation({
    mutationFn: async () => {
      if (!desktopApi?.sync?.runNow) throw new Error("桌面同步 API 不可用");
      return desktopApi.sync.runNow();
    },
    onSuccess: (status) => {
      setBridgeState((state) => ({ ...state, syncStatus: status }));
    },
  });
  const openRunWindowMutation = useMutation({
    mutationFn: async () => {
      const runId = bridgeState.windows.find((item) => item.runId)?.runId;
      if (!runId) throw new Error("请从运行详情选择一个真实 Run");
      if (!desktopApi?.window?.openRun) throw new Error("多窗口 API 不可用");
      return desktopApi.window.openRun(runId);
    },
    onSuccess: refreshBridge,
  });
  const toggleStartupMutation = useMutation({
    mutationFn: async () => {
      if (!desktopApi?.system?.setStartupEnabled) throw new Error("系统启动项 API 不可用");
      return desktopApi.system.setStartupEnabled(!Boolean(bridgeState.startupEnabled));
    },
    onSuccess: refreshBridge,
  });
  const selectFileRootMutation = useMutation({
    mutationFn: async () => {
      if (!desktopApi?.file?.selectWorkspaceRoot) throw new Error("文件根选择 API 不可用");
      return desktopApi.file.selectWorkspaceRoot();
    },
    onSuccess: refreshBridge,
  });
  const toggleFileWatchMutation = useMutation({
    mutationFn: async () => {
      if (!desktopApi?.file?.startWatch || !desktopApi.file.stopWatch) throw new Error("文件监听 API 不可用");
      return bridgeState.fileRoot?.watching ? desktopApi.file.stopWatch() : desktopApi.file.startWatch();
    },
    onSuccess: refreshBridge,
  });
  const checkUpdateMutation = useMutation({
    mutationFn: async () => {
      if (!desktopApi?.updates?.check) throw new Error("更新检查 API 不可用");
      return desktopApi.updates.check();
    },
    onSuccess: (updateStatus) => {
      setBridgeState((state) => ({ ...state, updateStatus }));
    },
  });
  const downloadUpdateMutation = useMutation({
    mutationFn: async () => {
      if (!desktopApi?.updates?.download) throw new Error("更新下载 API 不可用");
      return desktopApi.updates.download();
    },
    onSuccess: (updateStatus) => {
      setBridgeState((state) => ({ ...state, updateStatus }));
    },
  });
  const installUpdateMutation = useMutation({
    mutationFn: async () => {
      if (!desktopApi?.updates?.install) throw new Error("更新安装 API 不可用");
      return desktopApi.updates.install();
    },
  });
  const submitFeedbackMutation = useMutation({
    mutationFn: async () => {
      if (!desktopApi?.feedback?.submit) throw new Error("反馈 API 不可用");
      const updateStatus = bridgeState.updateStatus;
      const payload: DesktopFeedbackPayload = {
        ...feedbackDraft,
        app_version: updateStatus?.currentVersion ?? "unknown",
        channel: updateStatus?.channel ?? "stable",
        platform: window.navigator.platform || "unknown",
        logs: [
          `bridge=${bridgeModeLabel}`,
          `fileRoot=${bridgeState.fileRoot?.rootPath ? "selected" : "unset"}`,
          `startup=${bridgeState.startupEnabled === true ? "enabled" : "disabled"}`,
        ],
      };
      return desktopApi.feedback.submit(payload);
    },
    onSuccess: refreshBridge,
  });

  const installedPluginIds = useMemo(
    () => new Set((marketplace.data?.items ?? []).filter((item) => item.install_state === "installed").map((item) => item.id)),
    [marketplace.data?.items],
  );
  const promptItems = promptTemplates.data?.items ?? [];
  const activeProfile = bridgeState.profiles.find((profile) => profile.id === bridgeState.activeProfileId) ?? null;
  const localModelEnabled = Boolean(bridgeState.localModel?.enabled);
  const bridgeModeLabel = bridgeHealthLabel(bridgeHealth);
  const bridgeModeTone: BadgeTone = bridgeHealth === "connected" ? "success" : bridgeHealth === "read-failed" ? "warning" : "neutral";
  const offlineModeLabel = localModelEnabled ? "本地模型已启用" : "确定性离线模式";
  const updateStatus = bridgeState.updateStatus;
  const updateChannelLabel = updateStatus?.channel === "beta" ? "Beta" : "Stable";
  const syncStatus = bridgeState.syncStatus;

  return (
    <ConsoleShell title="桌面">
      <div className="mx-auto flex h-full min-h-0 w-full max-w-7xl flex-col gap-5 overflow-y-auto p-4 lg:p-6">
        <header className="flex flex-col gap-4 border-b border-slate-200 pb-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0 max-w-3xl">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={bridgeModeTone}>{bridgeModeLabel}</Badge>
              <Badge tone={localModelEnabled ? "success" : "neutral"}>{offlineModeLabel}</Badge>
            </div>
            <h1 className="mt-3 text-2xl font-semibold tracking-normal text-slate-950">桌面设置</h1>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              管理工作区、离线执行、本地模型、文件权限、更新、插件和提示词模板。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" onClick={() => void refreshBridge()} disabled={!desktopAvailable}>
              <RefreshCw className="h-3.5 w-3.5" />
              刷新状态
            </Button>
            <HighContrastButton />
          </div>
        </header>

        {bridgeError ? (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">{bridgeError}</div>
        ) : null}

        <section className="grid gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
          <aside className="hidden lg:block">
            <div className="sticky top-6 rounded-md border border-slate-200 bg-white p-3">
              <div className="text-xs font-semibold text-slate-900">章节</div>
              <nav aria-label="桌面章节" className="mt-2 grid gap-1">
                {visibleChapters.map((chapter) => (
                  <a
                    key={chapter.id}
                    href={`#${chapter.id}`}
                    className="rounded px-2 py-1.5 text-xs text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                  >
                    {chapter.label}
                  </a>
                ))}
              </nav>
              <div className="mt-3 border-t border-slate-100 pt-3 text-[11px] leading-5 text-slate-500">
                <div>{bridgeModeLabel}</div>
                <div>{offlineModeLabel}</div>
              </div>
            </div>
          </aside>

          <div className="space-y-7">
            <DocumentChapter
              id="workspace"
              icon={<Layers3 className="h-4 w-4" />}
              title="工作区和窗口"
              badge={bridgeModeLabel}
              badgeTone={bridgeModeTone}
            >
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(300px,0.72fr)]">
                <div className="space-y-3">
                  <StatusLine
                    label="当前工作区"
                    value={activeProfile ? activeProfile.label : "尚未读取"}
                    detail={activeProfile?.dataPath ?? "桌面模式会保存独立的数据路径。"}
                  />
                  <StatusLine
                    label="访问凭据"
                    value={credentialStorageLabel(activeProfile?.credentialStorage)}
                    detail="凭据仅在 Electron 主进程解密，页面不会读取明文。"
                  />
                  <StatusLine
                    label="独立运行窗口"
                    value={`${bridgeState.windows.length} 个`}
                    detail={bridgeState.windows.length ? "窗口状态来自 Electron 主进程。" : "还没有打开独立运行窗口。"}
                  />
                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      variant="primary"
                      onClick={() => openRunWindowMutation.mutate()}
                      disabled={!desktopAvailable || !bridgeState.windows.some((item) => item.runId) || openRunWindowMutation.isPending}
                    >
                      {openRunWindowMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <AppWindow className="h-3.5 w-3.5" />}
                      打开运行窗口
                    </Button>
                    <Button type="button" variant="secondary" onClick={() => void refreshBridge()} disabled={!desktopAvailable}>
                      刷新窗口
                    </Button>
                  </div>
                </div>

                <Disclosure title="工作区配置">
                  <div className="grid gap-2 md:grid-cols-2">
                    <Input
                      aria-label="Profile ID"
                      value={profileDraft.id}
                      onChange={(event) => setProfileDraft((draft) => ({ ...draft, id: event.target.value }))}
                      placeholder="工作区 ID"
                    />
                    <Input
                      aria-label="Profile 名称"
                      value={profileDraft.label}
                      onChange={(event) => setProfileDraft((draft) => ({ ...draft, label: event.target.value }))}
                      placeholder="工作区名称"
                    />
                    <Input
                      aria-label="Profile API"
                      value={profileDraft.apiBaseUrl}
                      onChange={(event) => setProfileDraft((draft) => ({ ...draft, apiBaseUrl: event.target.value }))}
                      placeholder="http://localhost:8000"
                    />
                    <Input
                      aria-label="Profile Token"
                      type="password"
                      autoComplete="new-password"
                      value={profileDraft.authToken}
                      onChange={(event) => setProfileDraft((draft) => ({ ...draft, authToken: event.target.value }))}
                      placeholder={activeProfile?.hasCredential ? "留空以保留现有凭据" : "Bearer token"}
                    />
                  </div>
                  <Button type="button" onClick={() => saveProfileMutation.mutate()} disabled={!desktopAvailable || saveProfileMutation.isPending}>
                    {saveProfileMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                    保存并切换
                  </Button>
                </Disclosure>
              </div>
            </DocumentChapter>

            <DocumentChapter
              id="native"
              icon={<MonitorCog className="h-4 w-4" />}
              title="系统与发布"
              badge={updateStateLabel(updateStatus?.state)}
              badgeTone={updateStatus?.state === "available" || updateStatus?.state === "downloaded" ? "info" : updateStatus?.state === "error" ? "failed" : "neutral"}
            >
              <div className="grid gap-4 xl:grid-cols-2">
                <DocumentPanel>
                  <SectionEyebrow icon={<Power className="h-3.5 w-3.5" />} label="系统启动" />
                  <StatusLine
                    label="开机启动"
                    value={bridgeState.startupEnabled === true ? "已启用" : bridgeState.startupEnabled === false ? "已关闭" : "未读取"}
                    detail="由 Electron 主进程读取登录项状态；关闭窗口后仍可通过托盘和快捷键唤醒。"
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => toggleStartupMutation.mutate()}
                    disabled={!desktopAvailable || toggleStartupMutation.isPending}
                  >
                    {toggleStartupMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Power className="h-3.5 w-3.5" />}
                    {bridgeState.startupEnabled ? "关闭开机启动" : "启用开机启动"}
                  </Button>
                </DocumentPanel>

                <DocumentPanel>
                  <SectionEyebrow icon={<FolderOpen className="h-3.5 w-3.5" />} label="文件根" />
                  <StatusLine
                    label="当前文件根"
                    value={privacySafePath(bridgeState.fileRoot?.rootPath) ?? "未选择文件根"}
                    detail={bridgeState.fileRoot?.watching ? "正在监听文件变化。" : "文件 list/read/write/watch 都从显式选择的根目录开始。"}
                  />
                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => selectFileRootMutation.mutate()}
                      disabled={!desktopAvailable || selectFileRootMutation.isPending}
                    >
                      {selectFileRootMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FolderOpen className="h-3.5 w-3.5" />}
                      选择文件根
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => toggleFileWatchMutation.mutate()}
                      disabled={!desktopAvailable || !bridgeState.fileRoot?.rootPath || toggleFileWatchMutation.isPending}
                    >
                      {toggleFileWatchMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                      {bridgeState.fileRoot?.watching ? "停止监听" : "开始监听"}
                    </Button>
                  </div>
                </DocumentPanel>

                <DocumentPanel>
                  <SectionEyebrow icon={<Download className="h-3.5 w-3.5" />} label="更新渠道" />
                  <StatusLine
                    label="更新渠道"
                    value={updateChannelLabel}
                    detail={`当前 ${updateStatus?.currentVersion ?? "unknown"} · ${updateStatus?.latestVersion ? `可用 ${updateStatus.latestVersion}` : updateStateLabel(updateStatus?.state)}`}
                  />
                  <StatusLine
                    label="可用版本"
                    value={updateStatus?.latestVersion ?? "暂无新版本"}
                    detail={updateStatus?.releaseUrl ?? updateStatus?.reason ?? "更新下载前会先经过后端策略检查。"}
                  />
                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => checkUpdateMutation.mutate()}
                      disabled={!desktopAvailable || checkUpdateMutation.isPending}
                    >
                      {checkUpdateMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                      检查更新
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => downloadUpdateMutation.mutate()}
                      disabled={!desktopAvailable || updateStatus?.state !== "available" || !desktopApi?.updates?.download || downloadUpdateMutation.isPending}
                    >
                      {downloadUpdateMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                      下载更新
                    </Button>
                    <Button
                      type="button"
                      onClick={() => installUpdateMutation.mutate()}
                      disabled={!desktopAvailable || updateStatus?.state !== "downloaded" || !desktopApi?.updates?.install || installUpdateMutation.isPending}
                    >
                      安装更新
                    </Button>
                  </div>
                  {updateStatus?.state === "downloading" ? (
                    <div className="text-[11px] text-slate-500" role="status">
                      下载进度 {Math.round(updateStatus.progress?.percent ?? 0)}%
                    </div>
                  ) : null}
                </DocumentPanel>

                <DocumentPanel>
                  <SectionEyebrow icon={<Send className="h-3.5 w-3.5" />} label="反馈" />
                  <div className="grid gap-2">
                    <Input
                      aria-label="反馈标题"
                      value={feedbackDraft.title}
                      onChange={(event) => setFeedbackDraft((draft) => ({ ...draft, title: event.target.value }))}
                    />
                    <Textarea
                      aria-label="反馈描述"
                      value={feedbackDraft.description}
                      onChange={(event) => setFeedbackDraft((draft) => ({ ...draft, description: event.target.value }))}
                      className="min-h-20"
                    />
                    <Button
                      type="button"
                      className="justify-self-start"
                      onClick={() => submitFeedbackMutation.mutate()}
                      disabled={!desktopAvailable || submitFeedbackMutation.isPending}
                    >
                      {submitFeedbackMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                      提交反馈
                    </Button>
                  </div>
                </DocumentPanel>
              </div>
            </DocumentChapter>

            <DocumentChapter
              id="offline"
              icon={<WifiOff className="h-4 w-4" />}
              title="离线执行"
              badge={localModelEnabled ? "本地模型" : "确定性本地"}
              badgeTone={localModelEnabled ? "success" : "neutral"}
            >
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(300px,0.72fr)]">
                <div className="space-y-3">
                  <StatusLine
                    label="执行来源"
                    value={localModelEnabled ? localModelDraft.model : "确定性本地输出"}
                    detail={localModelEnabled ? localModelDraft.baseUrl : "没有网络时仍可整理简单任务。"}
                  />
                  <StatusLine
                    label="同步状态"
                    value={syncStatus ? syncStateLabel(syncStatus.state) : "未读取"}
                    detail={syncStatus
                      ? `待同步 ${syncStatus.pendingOperations} · 冲突 ${syncStatus.conflictCount}${syncStatus.lastError ? ` · ${syncStatus.lastError}` : ""}`
                      : "离线结果可显式加入同步队列。"}
                  />
                  <div className="grid gap-2">
                    <Textarea
                      aria-label="离线任务输入"
                      value={offlinePrompt}
                      onChange={(event) => setOfflinePrompt(event.target.value)}
                      className="min-h-24"
                    />
                    <Button
                      type="button"
                      variant="primary"
                      onClick={() => offlineMutation.mutate()}
                      disabled={!desktopAvailable || offlineMutation.isPending}
                      className="justify-self-start"
                    >
                      {offlineMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <WifiOff className="h-3.5 w-3.5" />}
                      离线执行
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => runSyncMutation.mutate()}
                      disabled={!desktopAvailable || !desktopApi?.sync?.runNow || runSyncMutation.isPending || syncStatus?.online === false}
                    >
                      {runSyncMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                      立即同步
                    </Button>
                  </div>
                </div>

                <Disclosure title="本地模型设置">
                  <label className="inline-flex items-center gap-2 text-xs font-medium text-slate-700">
                    <input
                      type="checkbox"
                      checked={localModelDraft.enabled}
                      onChange={(event) => setLocalModelDraft((draft) => ({ ...draft, enabled: event.target.checked }))}
                    />
                    启用可选本地模型
                  </label>
                  <label className="grid gap-1 text-xs font-medium text-slate-700">
                    <span>供应商</span>
                    <select
                      aria-label="本地模型供应商"
                      value={localModelDraft.provider}
                      onChange={(event) =>
                        setLocalModelDraft((draft) => ({
                          ...draft,
                          provider: event.target.value as DesktopLocalModelSettings["provider"],
                        }))
                      }
                      className="h-9 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300"
                    >
                      <option value="ollama">Ollama</option>
                      <option value="openai-compatible">OpenAI-compatible</option>
                    </select>
                  </label>
                  <div className="grid gap-2 md:grid-cols-2">
                    <Input
                      aria-label="本地模型地址"
                      value={localModelDraft.baseUrl}
                      onChange={(event) => setLocalModelDraft((draft) => ({ ...draft, baseUrl: event.target.value }))}
                    />
                    <Input
                      aria-label="本地模型名称"
                      value={localModelDraft.model}
                      onChange={(event) => setLocalModelDraft((draft) => ({ ...draft, model: event.target.value }))}
                    />
                  </div>
                  <Button type="button" onClick={() => saveLocalModelMutation.mutate()} disabled={!desktopAvailable || saveLocalModelMutation.isPending}>
                    {saveLocalModelMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <MonitorCog className="h-3.5 w-3.5" />}
                    保存本地模型
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => testLocalModelMutation.mutate()}
                    disabled={!desktopAvailable || !desktopApi?.localModel?.testConnection || testLocalModelMutation.isPending}
                  >
                    {testLocalModelMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                    测试连接
                  </Button>
                  {bridgeState.localModelHealth ? (
                    <div
                      role="status"
                      className={bridgeState.localModelHealth.available ? "text-[11px] text-emerald-700" : "text-[11px] text-amber-700"}
                    >
                      {bridgeState.localModelHealth.available
                        ? `连接可用 · ${bridgeState.localModelHealth.durationMs}ms`
                        : `连接不可用 · ${bridgeState.localModelHealth.error ?? "未知错误"}`}
                    </div>
                  ) : null}
                </Disclosure>
              </div>
              <DocumentPanel>
                <SectionEyebrow icon={<WifiOff className="h-3.5 w-3.5" />} label="完整离线 Agent" />
                <div className="grid gap-2">
                  <Textarea
                    aria-label="完整离线 Agent 目标"
                    value={offlineAgentPrompt}
                    onChange={(event) => setOfflineAgentPrompt(event.target.value)}
                    className="min-h-20"
                  />
                  <label className="grid gap-1 text-xs font-medium text-slate-700">
                    <span>受限工具</span>
                    <select
                      aria-label="离线 Agent 受限工具"
                      value={offlineAgentTool}
                      onChange={(event) => {
                        const nextTool = event.target.value as typeof offlineAgentTool;
                        setOfflineAgentTool(nextTool);
                        if (nextTool === "workspace.list_files") setOfflineAgentPath(".");
                      }}
                      className="h-9 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300"
                    >
                      <option value="none">不使用工具</option>
                      <option value="workspace.list_files">列出工作区文件（只读）</option>
                      <option value="workspace.read_text">读取文本文件（只读）</option>
                      <option value="workspace.write_text">写入文本文件（需审批）</option>
                    </select>
                  </label>
                  {offlineAgentTool !== "none" ? (
                    <Input
                      aria-label="离线 Agent 工具路径"
                      value={offlineAgentPath}
                      onChange={(event) => setOfflineAgentPath(event.target.value)}
                    />
                  ) : null}
                  {offlineAgentTool === "workspace.write_text" ? (
                    <Textarea
                      aria-label="离线 Agent 写入内容"
                      value={offlineAgentContent}
                      onChange={(event) => setOfflineAgentContent(event.target.value)}
                    />
                  ) : null}
                  <Button
                    type="button"
                    onClick={() => offlineAgentMutation.mutate()}
                    disabled={!desktopApi?.offlineAgent?.run || offlineAgentMutation.isPending}
                    className="justify-self-start"
                  >
                    {offlineAgentMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <WifiOff className="h-3.5 w-3.5" />}
                    启动离线 Agent
                  </Button>
                </div>
              </DocumentPanel>
              <ResultList
                title="离线 Agent Runs"
                emptyText="暂无完整离线 Agent Run"
                items={bridgeState.offlineAgentRuns}
                renderItem={(run) => {
                  const approval = bridgeState.offlineAgentSnapshots[run.id]?.approvals.find(
                    (item) => item.status === "PENDING",
                  );
                  const hasConflict = Boolean(approval?.decision && "conflict" in approval.decision);
                  return <ListPanel key={run.id}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="min-w-0 truncate font-semibold text-slate-900">{run.prompt}</span>
                      <Badge tone={offlineAgentStatusTone(run.status)}>{offlineAgentStatusLabel(run.status)}</Badge>
                    </div>
                    {run.result ? <pre className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap text-[11px] leading-5 text-slate-600">{run.result}</pre> : null}
                    {run.errorMessage ? <div className="mt-1 text-[11px] text-amber-700">{run.errorMessage}</div> : null}
                    {run.status === "WAITING_APPROVAL" ? (() => {
                      const target = approval?.target;
                      const proposal = approval?.proposal;
                      return target ? <div className="mt-2 text-[11px] text-slate-600">
                        写入目标：<code>{target.path ?? "(未知路径)"}</code> · {target.exists ? "现有文件" : "新文件"} · 基线 {target.sha256 ? target.sha256.slice(0, 12) : "不存在"}<br />
                        拟写内容：{proposal?.sizeBytes ?? 0} bytes · {proposal?.sha256 ? proposal.sha256.slice(0, 12) : "未知摘要"}{hasConflict ? " · 文件已变化，请重新发起审批" : ""}
                      </div> : null;
                    })() : null}
                    <div className="mt-2 flex flex-wrap gap-2">
                      {run.status === "WAITING_APPROVAL" && run.pendingApprovalId ? (
                        <>
                          <Button type="button" onClick={() => offlineAgentApprovalMutation.mutate({ approvalId: run.pendingApprovalId!, approved: true })} disabled={offlineAgentApprovalMutation.isPending || hasConflict}>批准写入</Button>
                          <Button type="button" variant="secondary" onClick={() => offlineAgentApprovalMutation.mutate({ approvalId: run.pendingApprovalId!, approved: false })} disabled={offlineAgentApprovalMutation.isPending}>拒绝</Button>
                          {hasConflict ? (
                            <Button type="button" variant="secondary" onClick={() => void refreshBridge()}>
                              <RefreshCw className="h-3.5 w-3.5" />
                              刷新审批预览
                            </Button>
                          ) : null}
                        </>
                      ) : null}
                      {run.status === "RUNNING" ? <Button type="button" variant="secondary" onClick={() => offlineAgentCancelMutation.mutate(run.id)} disabled={offlineAgentCancelMutation.isPending}>取消</Button> : null}
                      {(["INTERRUPTED", "FAILED", "CANCELLED"] as DesktopOfflineAgentStatus[]).includes(run.status) ? <Button type="button" variant="secondary" onClick={() => offlineAgentResumeMutation.mutate(run.id)} disabled={offlineAgentResumeMutation.isPending}>恢复</Button> : null}
                    </div>
                  </ListPanel>;
                }}
              />
              <ResultList
                title="离线任务结果"
                emptyText="暂无离线任务"
                items={bridgeState.offlineTasks}
                renderItem={(item) => (
                  <ListPanel key={item.id}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="min-w-0 truncate font-semibold text-slate-900">{item.prompt}</span>
                      <Badge tone={item.status === "completed" ? "success" : "failed"}>{offlineTaskSourceLabel(item.modelSource)}</Badge>
                    </div>
                    <pre className="mt-2 max-h-24 overflow-auto whitespace-pre-wrap text-[11px] leading-5 text-slate-600">{item.result}</pre>
                    {item.fallbackReason ? (
                      <div className="mt-1 text-[11px] text-amber-700">本地模型降级：{item.fallbackReason}</div>
                    ) : null}
                    <Button
                      type="button"
                      variant="secondary"
                      className="mt-2"
                      onClick={() => promoteOfflineMutation.mutate(item.id)}
                      disabled={!desktopApi?.offline?.promoteResultToPendingAgentTask || promoteOfflineMutation.isPending}
                    >
                      {promoteOfflineMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                      加入同步队列
                    </Button>
                  </ListPanel>
                )}
              />
            </DocumentChapter>

            <DocumentChapter
              id="plugins"
              icon={<Store className="h-4 w-4" />}
              title="插件和提示词"
              badge={`${installedPluginIds.size} 已安装`}
              badgeTone={installedPluginIds.size > 0 ? "success" : "neutral"}
            >
              <div className="grid gap-4 xl:grid-cols-2">
                <DocumentPanel>
                  <SectionEyebrow icon={<PlugZap className="h-3.5 w-3.5" />} label="插件市场" />
                  <VirtualList
                    items={marketplace.data?.items ?? []}
                    height={280}
                    estimateSize={112}
                    getItemKey={(item) => item.id}
                    ariaLabel="插件市场列表"
                    renderItem={(item) => (
                      <ListPanel>
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <div className="font-semibold text-slate-900">{item.name}</div>
                              <Badge tone={item.install_state === "installed" ? "success" : "neutral"}>
                                {item.install_state === "installed" ? "已安装" : categoryLabel(item.category)}
                              </Badge>
                            </div>
                            <div className="mt-1 text-xs leading-5 text-slate-600">{item.description}</div>
                            <div className="mt-1 truncate font-mono text-[11px] text-slate-500">{item.publisher} · {item.version}</div>
                          </div>
                          <Button type="button" onClick={() => installMutation.mutate(item)} disabled={installMutation.isPending}>
                            <PlugZap className="h-3.5 w-3.5" />
                            {item.install_state === "installed" ? "卸载" : "安装"}
                          </Button>
                        </div>
                      </ListPanel>
                    )}
                  />
                </DocumentPanel>

                <DocumentPanel>
                  <SectionEyebrow icon={<TextCursorInput className="h-3.5 w-3.5" />} label="提示词模板" />
                  <VirtualList
                    items={promptItems}
                    height={280}
                    estimateSize={96}
                    getItemKey={(item) => item.id}
                    ariaLabel="提示词模板列表"
                    renderItem={(item) => (
                      <ListPanel>
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="font-semibold text-slate-900">{item.name}</div>
                            <div className="mt-1 text-xs leading-5 text-slate-600">{item.description}</div>
                            <div className="mt-1 flex flex-wrap gap-1">
                              <Badge tone={item.source === "custom" ? "success" : item.source === "plugin" ? "info" : "neutral"}>
                                {templateSourceLabel(item.source)}
                              </Badge>
                              {item.tags.map((tag) => <Badge key={tag} tone="neutral">{tag}</Badge>)}
                            </div>
                          </div>
                          {item.source === "custom" ? (
                            <Button type="button" variant="ghost" onClick={() => deleteTemplateMutation.mutate(item.id)} disabled={deleteTemplateMutation.isPending}>
                              删除
                            </Button>
                          ) : null}
                        </div>
                      </ListPanel>
                    )}
                  />
                </DocumentPanel>
              </div>

              <Disclosure title="新建提示词模板">
                <div className="grid gap-2 md:grid-cols-2">
                  <Input
                    aria-label="模板 ID"
                    value={templateDraft.id ?? ""}
                    onChange={(event) => setTemplateDraft((draft) => ({ ...draft, id: event.target.value }))}
                  />
                  <Input
                    aria-label="模板名称"
                    value={templateDraft.name}
                    onChange={(event) => setTemplateDraft((draft) => ({ ...draft, name: event.target.value }))}
                  />
                </div>
                <Textarea
                  aria-label="模板内容"
                  value={templateDraft.body}
                  onChange={(event) => setTemplateDraft((draft) => ({ ...draft, body: event.target.value }))}
                />
                <Button type="button" onClick={() => saveTemplateMutation.mutate()} disabled={saveTemplateMutation.isPending}>
                  {saveTemplateMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                  保存模板
                </Button>
              </Disclosure>
            </DocumentChapter>

          </div>
        </section>
      </div>
    </ConsoleShell>
  );
}

function DocumentChapter({
  id,
  icon,
  title,
  badge,
  badgeTone,
  children,
}: {
  id: string;
  icon: ReactNode;
  title: string;
  badge: string;
  badgeTone: BadgeTone;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-6 border-t border-slate-200 pt-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex min-w-0 items-center gap-2 text-base font-semibold text-slate-950">
          {icon}
          <span className="truncate">{title}</span>
        </div>
        <Badge tone={badgeTone}>{badge}</Badge>
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

function StatusLine({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="grid gap-1 border-b border-slate-100 pb-3 last:border-b-0 last:pb-0">
      <div className="flex items-center justify-between gap-3">
        <div className="text-xs text-slate-500">{label}</div>
        <div className="min-w-0 truncate text-sm font-semibold text-slate-900">{value}</div>
      </div>
      <div className="break-words text-[11px] leading-5 text-slate-500">{detail}</div>
    </div>
  );
}

function SectionEyebrow({ icon, label }: { icon: ReactNode; label: string }) {
  return (
    <div className="flex items-center gap-2 text-xs font-semibold text-slate-700">
      {icon}
      <span>{label}</span>
    </div>
  );
}

function DocumentPanel({ children }: { children: ReactNode }) {
  return (
    <div className="min-w-0 rounded-md border border-slate-200 bg-white p-3">
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function Disclosure({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="rounded-md border border-slate-200 bg-slate-50/70 px-3 py-2 text-xs text-slate-600">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 font-semibold text-slate-800">
        <span>{title}</span>
        <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
      </summary>
      <div className="mt-3 grid gap-3">{children}</div>
    </details>
  );
}

function ListPanel({ children }: { children: ReactNode }) {
  return (
    <div className="mx-1 my-1 rounded-md border border-slate-200 bg-white px-3 py-2">
      {children}
    </div>
  );
}

function ResultList<T>({
  title,
  emptyText,
  items,
  renderItem,
}: {
  title: string;
  emptyText: string;
  items: T[];
  renderItem: (item: T) => ReactNode;
}) {
  return (
    <div className="space-y-2">
      <SectionEyebrow icon={<Circle className="h-3 w-3" />} label={title} />
      {items.length ? (
        <div className="max-h-72 overflow-auto pr-1">{items.slice(0, 6).map(renderItem)}</div>
      ) : (
        <div className="rounded-md border border-dashed border-slate-200 px-3 py-6 text-center text-xs text-slate-500">{emptyText}</div>
      )}
    </div>
  );
}

function HighContrastButton() {
  return (
    <Button
      type="button"
      variant="secondary"
      onClick={() => {
        document.documentElement.classList.toggle("theme-high-contrast");
        window.localStorage.setItem(
          "harness.a11y.high_contrast",
          document.documentElement.classList.contains("theme-high-contrast") ? "1" : "0",
        );
      }}
    >
      <Accessibility className="h-3.5 w-3.5" />
      高对比度
    </Button>
  );
}

function offlineTaskSourceLabel(source: DesktopOfflineTask["modelSource"]) {
  return source === "local-model" ? "本地模型" : "确定性本地";
}

function offlineAgentStatusLabel(status: DesktopOfflineAgentStatus): string {
  return {
    PENDING: "排队中",
    RUNNING: "执行中",
    WAITING_APPROVAL: "等待审批",
    INTERRUPTED: "可恢复",
    COMPLETED: "已完成",
    FAILED: "失败",
    CANCELLED: "已取消",
  }[status];
}

function offlineAgentStatusTone(status: DesktopOfflineAgentStatus): BadgeTone {
  if (status === "COMPLETED") return "success";
  if (status === "FAILED" || status === "CANCELLED") return "warning";
  if (status === "WAITING_APPROVAL") return "info";
  return "neutral";
}

function updateStateLabel(state?: DesktopUpdateState | null) {
  if (state === "checking") return "检查中";
  if (state === "available") return "有新版本";
  if (state === "not-available") return "无更新";
  if (state === "downloading") return "下载中";
  if (state === "downloaded") return "已下载";
  if (state === "error") return "更新错误";
  return "空闲";
}

function bridgeHealthLabel(state: DesktopBridgeHealth): string {
  if (state === "connected") return "桌面桥接已连接";
  if (state === "loading") return "正在读取桌面状态";
  if (state === "read-failed") return "桥接读取失败";
  return "网页回退模式";
}

function syncStateLabel(state: DesktopSyncRuntimeStatus["state"]): string {
  if (state === "syncing") return "同步中";
  if (state === "scheduled") return "等待重试";
  if (state === "error") return "同步错误";
  if (state === "closed") return "已关闭";
  return "已同步";
}

function credentialStorageLabel(storage?: DesktopProfile["credentialStorage"]): string {
  if (storage === "persistent") return "已安全保存";
  if (storage === "session") return "仅当前会话";
  return "未配置";
}

function privacySafePath(value: string | null | undefined): string | null {
  if (!value) return null;
  const normalized = value.replaceAll("\\", "/").replace(/\/+$/, "");
  return normalized.split("/").filter(Boolean).pop() ?? null;
}

function templateSourceLabel(source: string) {
  if (source === "custom") return "自定义";
  if (source === "plugin") return "插件";
  return "内置";
}

function categoryLabel(category: string) {
  if (category === "tool") return "工具";
  if (category === "prompt") return "提示词";
  return category;
}
