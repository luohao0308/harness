import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  Check,
  Clipboard,
  Code2,
  FileSearch,
  FolderOpen,
  GitBranch,
  History,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Trash2,
  Webhook,
} from "lucide-react";
import { Link } from "react-router-dom";

import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { ConfigDialog } from "../../../components/ui/config-dialog";
import { Input } from "../../../components/ui/input";
import { MenuSelect } from "../../../components/ui/menu-select";
import { useI18n } from "../../../lib/i18n";
import { useOptionalAuth } from "../../auth/AuthProvider";
import {
  API_BASE_URL,
  ApiHttpError,
  createAgentTrigger,
  deleteAgentTrigger,
  listAgentTriggers,
  listTriggerInvocations,
  updateAgentTrigger,
  type AgentTrigger,
  type AgentTriggerCreateRequest,
} from "../../tasks/api";

type TriggerType = AgentTrigger["type"];

const triggerTypes: Array<{ value: TriggerType; zh: string; en: string }> = [
  { value: "webhook", zh: "Webhook", en: "Webhook" },
  { value: "schedule", zh: "定时", en: "Schedule" },
  { value: "file", zh: "文件变更", en: "File change" },
  { value: "git", zh: "Git 提交", en: "Git commit" },
];

function triggerIcon(type: TriggerType) {
  if (type === "schedule") return CalendarClock;
  if (type === "file") return FileSearch;
  if (type === "git") return GitBranch;
  return Webhook;
}

function displayTime(value: string | null | undefined) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function webhookUrl(endpointPath: string) {
  const base = API_BASE_URL === "/"
    ? (typeof window === "undefined" ? "" : window.location.origin)
    : API_BASE_URL.replace(/\/$/, "");
  return `${base}/api/webhook/trigger/${encodeURIComponent(endpointPath)}`;
}

async function copyValue(value: string) {
  await navigator.clipboard.writeText(value);
}

export function AutomationPanel({
  agentId,
  agentLabel,
  agents,
  agentsLoading = false,
  onAgentChange,
}: {
  agentId: string;
  agentLabel: string;
  agents?: Array<{ id: string; name: string }>;
  agentsLoading?: boolean;
  onAgentChange?: (agentId: string) => void;
}) {
  const { text } = useI18n();
  const auth = useOptionalAuth();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [createdWebhook, setCreatedWebhook] = useState<{ secret: string; url: string } | null>(null);
  const [selectedTriggerId, setSelectedTriggerId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<AgentTrigger | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [copied, setCopied] = useState<"url" | "secret" | null>(null);

  const triggers = useQuery({
    queryKey: ["agent-triggers", agentId],
    queryFn: () => listAgentTriggers(agentId),
  });
  const invocations = useQuery({
    queryKey: ["trigger-invocations", agentId, selectedTriggerId],
    queryFn: () => listTriggerInvocations(agentId, selectedTriggerId ?? ""),
    enabled: selectedTriggerId !== null,
  });

  const refresh = async () => {
    setActionError(null);
    await triggers.refetch();
    if (selectedTriggerId) await invocations.refetch();
  };

  const updateMutation = useMutation({
    mutationFn: ({ triggerId, enabled }: { triggerId: string; enabled: boolean }) =>
      updateAgentTrigger(agentId, triggerId, { enabled }),
    onSuccess: async () => {
      setActionError(null);
      await queryClient.invalidateQueries({ queryKey: ["agent-triggers", agentId] });
    },
    onError: (error) => setActionError(error instanceof Error ? error.message : text("操作失败", "Action failed")),
  });
  const deleteMutation = useMutation({
    mutationFn: (triggerId: string) => deleteAgentTrigger(agentId, triggerId),
    onSuccess: async (_result, triggerId) => {
      if (selectedTriggerId === triggerId) setSelectedTriggerId(null);
      setActionError(null);
      await queryClient.invalidateQueries({ queryKey: ["agent-triggers", agentId] });
    },
    onError: (error) => setActionError(error instanceof Error ? error.message : text("删除失败", "Delete failed")),
  });

  const permissionDenied = triggers.error instanceof ApiHttpError && triggers.error.status === 403;
  const capabilities = automationCapabilities(auth?.user?.permissions, auth?.user?.role ?? auth?.currentOrganization?.role);

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto p-3 sm:p-4">
      <section className="flex min-w-0 flex-wrap items-start justify-between gap-3 border-b border-slate-200 pb-3">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            <Code2 className="h-5 w-5 shrink-0 text-slate-600" />
            <h1 className="truncate text-lg font-semibold text-slate-950">{text("自动化", "Automations")}</h1>
            {agents ? (
              <MenuSelect
                ariaLabel={text("管理智能体", "Managed Agent")}
                value={agentId}
                size="compact"
                disabled={agentsLoading || agents.length === 0}
                placeholder={agentsLoading ? text("加载智能体...", "Loading Agents...") : text("暂无智能体", "No Agents")}
                className="w-48 max-w-full"
                options={agents.map((agent) => ({ value: agent.id, label: agent.name, meta: agent.id }))}
                onChange={(nextAgentId) => {
                  setSelectedTriggerId(null);
                  setActionError(null);
                  onAgentChange?.(nextAgentId);
                }}
              />
            ) : <Badge tone="neutral" className="max-w-48 truncate">{agentLabel}</Badge>}
          </div>
          <p className="mt-1 text-sm text-slate-500">
            {text("用外部事件或本机变化启动智能体运行。", "Start Agent runs from external events or local changes.")}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {text("文件与 Git 触发仅在 Forge Harness Desktop 本机运行。", "File and Git triggers run only on this Forge Harness Desktop host.")}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button aria-label={text("刷新自动化", "Refresh automations")} onClick={() => void refresh()} disabled={triggers.isFetching}>
            <RefreshCw className={triggers.isFetching ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} />
            {text("刷新", "Refresh")}
          </Button>
          {!permissionDenied && capabilities.create ? (
            <Button variant="primary" onClick={() => setCreateOpen(true)}>
              <Plus className="h-3.5 w-3.5" /> {text("新建自动化", "New automation")}
            </Button>
          ) : null}
        </div>
      </section>

      {triggers.isLoading ? (
        <div className="py-12 text-center text-sm text-slate-500">{text("正在加载自动化...", "Loading automations...")}</div>
      ) : null}
      {triggers.error ? (
        <div className="mt-4 border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <div>{permissionDenied ? text("当前账号无权读取自动化。", "This account cannot read automations.") : (triggers.error instanceof Error ? triggers.error.message : text("自动化加载失败", "Failed to load automations"))}</div>
          <Button className="mt-3" onClick={() => void triggers.refetch()}>{text("重试", "Retry")}</Button>
        </div>
      ) : null}
      {actionError ? <div className="mt-3 border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{actionError}</div> : null}

      {triggers.data?.items.length === 0 ? (
        <div className="py-16 text-center">
          <Code2 className="mx-auto h-7 w-7 text-slate-300" />
          <div className="mt-3 text-sm font-medium text-slate-800">{text("暂无自动化", "No automations")}</div>
          <div className="mt-1 text-xs text-slate-500">{text("创建第一个 Trigger 来自动启动运行。", "Create the first trigger to start runs automatically.")}</div>
        </div>
      ) : null}

      {triggers.data && triggers.data.items.length > 0 ? (
        <div className="mt-4 grid min-w-0 gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.7fr)]">
          <Card className="min-w-0 overflow-hidden">
            <CardHeader>
              <span className="text-sm font-semibold text-slate-900">{text("Trigger 列表", "Trigger list")}</span>
              <Badge tone="neutral">{triggers.data.items.length}</Badge>
            </CardHeader>
            <div className="divide-y divide-slate-100">
              {triggers.data.items.map((trigger) => {
                const Icon = triggerIcon(trigger.type);
                const name = trigger.name?.trim() || trigger.endpoint_path || trigger.type;
                return (
                  <div key={trigger.id} className="min-w-0 p-3">
                    <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
                      <div className="flex min-w-0 flex-1 gap-2.5">
                        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-slate-100 text-slate-600"><Icon className="h-4 w-4" /></div>
                        <div className="min-w-0">
                          <div className="flex min-w-0 flex-wrap items-center gap-2">
                            <span className="max-w-full truncate text-sm font-medium text-slate-900">{name}</span>
                            <Badge tone={trigger.enabled ? "success" : "neutral"}>{trigger.enabled ? text("已启用", "Enabled") : text("已暂停", "Paused")}</Badge>
                            {(trigger.type === "file" || trigger.type === "git") ? <Badge tone="info">{text("仅本地 Desktop", "Desktop only")}</Badge> : null}
                          </div>
                          <div className="mt-1 break-all text-xs text-slate-500">{triggerSummary(trigger, text)}</div>
                          <div className="mt-1 text-[11px] text-slate-400">{text("最近运行", "Latest run")} · {displayTime(trigger.last_triggered_at)}</div>
                        </div>
                      </div>
                      <div className="flex shrink-0 flex-wrap gap-1">
                        {capabilities.update ? (
                          <Button
                            variant="ghost"
                            aria-label={`${trigger.enabled ? text("暂停", "Pause") : text("启用", "Enable")} ${name}`}
                            title={trigger.enabled ? text("暂停", "Pause") : text("启用", "Enable")}
                            className="w-8 px-0"
                            disabled={updateMutation.isPending || deleteMutation.isPending}
                            onClick={() => updateMutation.mutate({ triggerId: trigger.id, enabled: !trigger.enabled })}
                          >
                            {trigger.enabled ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                          </Button>
                        ) : null}
                        <Button
                          variant="ghost"
                          aria-label={`${text("查看", "View")} ${name} ${text("的最近运行", "recent runs")}`}
                          title={text("最近运行", "Recent runs")}
                          className="w-8 px-0"
                          onClick={() => setSelectedTriggerId(trigger.id)}
                        ><History className="h-3.5 w-3.5" /></Button>
                        {capabilities.delete ? (
                          <Button
                            variant="ghost"
                            aria-label={`${text("删除", "Delete")} ${name}`}
                            title={text("删除", "Delete")}
                            className="w-8 px-0 text-red-600"
                            disabled={updateMutation.isPending || deleteMutation.isPending}
                            onClick={() => setPendingDelete(trigger)}
                          ><Trash2 className="h-3.5 w-3.5" /></Button>
                        ) : null}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>

          <InvocationHistory
            selectedTrigger={triggers.data.items.find((item) => item.id === selectedTriggerId) ?? null}
            isLoading={invocations.isLoading}
            error={invocations.error}
            items={invocations.data?.items ?? []}
          />
        </div>
      ) : null}

      <CreateAutomationDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        agentId={agentId}
        onCreated={async (result) => {
          setCreateOpen(false);
          if (result.trigger.type === "webhook" && result.secret && result.trigger.endpoint_path) {
            setCreatedWebhook({ secret: result.secret, url: webhookUrl(result.trigger.endpoint_path) });
          }
          await queryClient.invalidateQueries({ queryKey: ["agent-triggers", agentId] });
        }}
      />

      <ConfigDialog
        open={pendingDelete !== null}
        title={text("删除自动化", "Delete automation")}
        description={text(
          "配置将被软删除并立即停止新的触发；已有调用历史和 Run 记录会保留。",
          "The configuration will be soft-deleted and stop new triggers immediately. Existing invocation and Run history will be retained.",
        )}
        onClose={() => setPendingDelete(null)}
      >
        <div className="grid gap-4">
          <div className="break-words text-sm text-slate-700">
            {text("即将删除", "About to delete")} <span className="font-medium text-slate-950">{pendingDelete?.name || pendingDelete?.endpoint_path || pendingDelete?.type}</span>
          </div>
          <div className="flex justify-end gap-2">
            <Button onClick={() => setPendingDelete(null)}>{text("取消", "Cancel")}</Button>
            <Button
              variant="danger"
              disabled={deleteMutation.isPending}
              onClick={() => {
                if (!pendingDelete) return;
                const triggerId = pendingDelete.id;
                setPendingDelete(null);
                deleteMutation.mutate(triggerId);
              }}
            >
              <Trash2 className="h-3.5 w-3.5" /> {text("确认删除", "Confirm delete")}
            </Button>
          </div>
        </div>
      </ConfigDialog>

      <ConfigDialog
        open={createdWebhook !== null}
        title={text("保存 Webhook 凭据", "Save webhook credentials")}
        description={text("密钥只在本次创建后显示一次，关闭后无法再次查看。", "The secret is shown only once after creation and cannot be viewed again after closing.")}
        onClose={() => { setCreatedWebhook(null); setCopied(null); setActionError(null); }}
      >
        {createdWebhook ? (
          <div className="grid min-w-0 gap-4">
            <CredentialRow label={text("完整 URL", "Full URL")} value={createdWebhook.url} />
            <CredentialRow label={text("密钥", "Secret")} value={createdWebhook.secret} />
            <div className="flex flex-wrap justify-end gap-2">
              <Button onClick={() => void copyValue(createdWebhook.url).then(() => { setCopied("url"); setActionError(null); }).catch((error) => setActionError(error instanceof Error ? error.message : text("复制失败", "Copy failed")))}>
                {copied === "url" ? <Check className="h-3.5 w-3.5" /> : <Clipboard className="h-3.5 w-3.5" />} {text("复制完整 URL", "Copy full URL")}
              </Button>
              <Button onClick={() => void copyValue(createdWebhook.secret).then(() => { setCopied("secret"); setActionError(null); }).catch((error) => setActionError(error instanceof Error ? error.message : text("复制失败", "Copy failed")))}>
                {copied === "secret" ? <Check className="h-3.5 w-3.5" /> : <Clipboard className="h-3.5 w-3.5" />} {text("复制密钥", "Copy secret")}
              </Button>
              <Button variant="primary" onClick={() => { setCreatedWebhook(null); setCopied(null); setActionError(null); }}>{text("我已保存", "Saved")}</Button>
            </div>
          </div>
        ) : null}
      </ConfigDialog>
    </div>
  );
}

function CreateAutomationDialog({
  open,
  onClose,
  agentId,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  agentId: string;
  onCreated: (result: Awaited<ReturnType<typeof createAgentTrigger>>) => Promise<void>;
}) {
  const { text } = useI18n();
  const [type, setType] = useState<TriggerType>("webhook");
  const [name, setName] = useState("");
  const [endpointPath, setEndpointPath] = useState("");
  const [intervalSeconds, setIntervalSeconds] = useState("300");
  const [workspaceGrant, setWorkspaceGrant] = useState<{ authorization: string; label: string } | null>(null);
  const [pattern, setPattern] = useState("**/*");
  const [repoGrant, setRepoGrant] = useState<{ authorization: string; label: string } | null>(null);
  const [branch, setBranch] = useState("");
  const [maxAttempts, setMaxAttempts] = useState("3");
  const [error, setError] = useState<string | null>(null);
  const desktopWorkspacePicker = typeof window === "undefined"
    ? undefined
    : window.desktopApi?.file?.selectAuthorizedWorkspaceRoot;

  const resetForm = () => {
    setType("webhook");
    setName("");
    setEndpointPath("");
    setIntervalSeconds("300");
    setWorkspaceGrant(null);
    setPattern("**/*");
    setRepoGrant(null);
    setBranch("");
    setMaxAttempts("3");
    setError(null);
  };

  const closeDialog = () => {
    resetForm();
    onClose();
  };

  const validationError = useMemo(() => {
    if (!name.trim()) return text("请输入自动化名称。", "Enter an automation name.");
    const attempts = Number(maxAttempts);
    if (!Number.isInteger(attempts) || attempts < 1 || attempts > 10) return text("失败重试次数必须是 1 到 10 的整数。", "Maximum attempts must be an integer from 1 to 10.");
    if (type === "schedule") {
      const interval = Number(intervalSeconds);
      if (!Number.isInteger(interval) || interval < 5 || interval > 86400) return text("执行间隔必须是 5 到 86400 秒的整数。", "Interval must be an integer from 5 to 86400 seconds.");
    }
    if (type === "file" && (!workspaceGrant || !pattern.trim())) return text("请选择已授权的工作区目录并填写文件匹配条件。", "Select an authorized workspace and enter a file pattern.");
    if (type === "file" && (pattern.startsWith("/") || pattern.split("/").includes(".."))) return text("文件匹配必须是工作区内的相对路径，不能包含 ..。", "File pattern must be relative to the workspace and cannot contain ...");
    if (type === "git" && !repoGrant) return text("请选择已授权的 Git 仓库目录。", "Select an authorized Git repository.");
    return null;
  }, [intervalSeconds, maxAttempts, name, pattern, repoGrant, text, type, workspaceGrant]);

  const payload = useMemo<AgentTriggerCreateRequest>(() => {
    const retry = { max_attempts: Number(maxAttempts) };
    if (type === "schedule") return { type, name, config_json: { ...retry, interval_seconds: Number(intervalSeconds) }, enabled: true };
    if (type === "file") return { type, name, config_json: { ...retry, workspace_authorization: workspaceGrant?.authorization, pattern }, enabled: true };
    if (type === "git") return { type, name, config_json: { ...retry, workspace_authorization: repoGrant?.authorization, ...(branch.trim() ? { branch: branch.trim() } : {}) }, enabled: true };
    return { type, name, endpoint_path: endpointPath || null, config_json: retry, enabled: true };
  }, [branch, endpointPath, intervalSeconds, maxAttempts, name, pattern, repoGrant, type, workspaceGrant]);

  const createMutation = useMutation({
    mutationFn: () => createAgentTrigger(agentId, payload),
    onSuccess: async (result) => {
      resetForm();
      await onCreated(result);
    },
    onError: (mutationError) => setError(mutationError instanceof Error ? mutationError.message : text("创建失败", "Create failed")),
  });

  const selectDesktopWorkspace = async (target: "file" | "git") => {
    if (!desktopWorkspacePicker) return;
    try {
      const selected = await desktopWorkspacePicker();
      if (!selected?.authorization || !selected.label) return;
      const grant = { authorization: selected.authorization, label: selected.label };
      if (target === "file") setWorkspaceGrant(grant);
      else setRepoGrant(grant);
      setError(null);
    } catch (selectionError) {
      setError(selectionError instanceof Error ? selectionError.message : text("选择目录失败", "Directory selection failed"));
    }
  };

  return (
    <ConfigDialog
      open={open}
      title={text("新建自动化", "New automation")}
      description={text("选择 Trigger 类型并配置启动条件。", "Choose a trigger type and configure its condition.")}
      onClose={closeDialog}
    >
      <div className="grid min-w-0 gap-4">
        <label className="grid gap-1 text-xs font-medium text-slate-600">
          {text("自动化名称", "Automation name")}
          <Input aria-label={text("自动化名称", "Automation name")} value={name} onChange={(event) => setName(event.target.value)} placeholder={text("例如：发布后巡检", "For example: post-release check")} />
        </label>
        <div className="grid gap-1 text-xs font-medium text-slate-600">
          {text("触发类型", "Trigger type")}
          <MenuSelect
            ariaLabel={text("触发类型", "Trigger type")}
            value={type}
            onChange={(value) => setType(value as TriggerType)}
            options={triggerTypes.map((item) => ({
              value: item.value,
              label: text(item.zh, item.en),
              description: (item.value === "file" || item.value === "git") ? text("仅本地 Desktop", "Desktop only") : undefined,
            }))}
          />
        </div>
        {type === "webhook" ? (
          <label className="grid gap-1 text-xs font-medium text-slate-600">
            {text("Webhook 路径", "Webhook path")}
            <Input aria-label={text("Webhook 路径", "Webhook path")} value={endpointPath} onChange={(event) => setEndpointPath(event.target.value)} placeholder="release-hook" />
          </label>
        ) : null}
        {type === "schedule" ? (
          <label className="grid gap-1 text-xs font-medium text-slate-600">
            {text("执行间隔（秒）", "Interval (seconds)")}
            <Input aria-label={text("执行间隔（秒）", "Interval (seconds)")} type="number" min="10" value={intervalSeconds} onChange={(event) => setIntervalSeconds(event.target.value)} />
          </label>
        ) : null}
        {type === "file" ? (
          <div className="grid gap-3">
            <Badge tone="info" className="w-fit">{text("仅本地 Desktop", "Desktop only")}</Badge>
            <label className="grid gap-1 text-xs font-medium text-slate-600">
              {text("工作区目录", "Workspace directory")}
              <div className="flex min-w-0 gap-2">
                <Input className="min-w-0 flex-1" aria-label={text("工作区目录", "Workspace directory")} value={workspaceGrant?.label ?? ""} readOnly placeholder={text("请从 Desktop 选择", "Choose from Desktop")} />
                {desktopWorkspacePicker ? (
                  <Button title={text("选择工作区目录", "Select workspace directory")} onClick={() => void selectDesktopWorkspace("file")}>
                    <FolderOpen className="h-4 w-4" /> {text("选择", "Choose")}
                  </Button>
                ) : null}
              </div>
            </label>
            <label className="grid gap-1 text-xs font-medium text-slate-600">
              {text("文件匹配", "File pattern")}
              <Input aria-label={text("文件匹配", "File pattern")} value={pattern} onChange={(event) => setPattern(event.target.value)} placeholder="**/*.md" />
            </label>
          </div>
        ) : null}
        {type === "git" ? (
          <div className="grid gap-3">
            <Badge tone="info" className="w-fit">{text("仅本地 Desktop", "Desktop only")}</Badge>
            <label className="grid gap-1 text-xs font-medium text-slate-600">
              {text("Git 仓库目录", "Git repository directory")}
              <div className="flex min-w-0 gap-2">
                <Input className="min-w-0 flex-1" aria-label={text("Git 仓库目录", "Git repository directory")} value={repoGrant?.label ?? ""} readOnly placeholder={text("请选择 Git 顶层目录", "Choose the Git top-level directory")} />
                {desktopWorkspacePicker ? (
                  <Button title={text("选择 Git 仓库目录", "Select Git repository directory")} onClick={() => void selectDesktopWorkspace("git")}>
                    <FolderOpen className="h-4 w-4" /> {text("选择", "Choose")}
                  </Button>
                ) : null}
              </div>
            </label>
            <label className="grid gap-1 text-xs font-medium text-slate-600">
              {text("分支（可选）", "Branch (optional)")}
              <Input aria-label={text("分支（可选）", "Branch (optional)")} value={branch} onChange={(event) => setBranch(event.target.value)} placeholder="main" />
            </label>
          </div>
        ) : null}
        <label className="grid gap-1 text-xs font-medium text-slate-600">
          {text("失败重试次数", "Maximum attempts")}
          <Input aria-label={text("失败重试次数", "Maximum attempts")} type="number" min="1" max="10" value={maxAttempts} onChange={(event) => setMaxAttempts(event.target.value)} />
        </label>
        {error ? <div className="border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div> : null}
        <div className="flex justify-end gap-2">
          <Button onClick={closeDialog}>{text("取消", "Cancel")}</Button>
          <Button variant="primary" disabled={createMutation.isPending} onClick={() => {
            if (validationError) {
              setError(validationError);
              return;
            }
            setError(null);
            createMutation.mutate();
          }}>
            {createMutation.isPending ? text("创建中...", "Creating...") : text("创建自动化", "Create automation")}
          </Button>
        </div>
      </div>
    </ConfigDialog>
  );
}

function InvocationHistory({
  selectedTrigger,
  isLoading,
  error,
  items,
}: {
  selectedTrigger: AgentTrigger | null;
  isLoading: boolean;
  error: Error | null;
  items: Awaited<ReturnType<typeof listTriggerInvocations>>["items"];
}) {
  const { text } = useI18n();
  return (
    <Card className="min-w-0 overflow-hidden">
      <CardHeader>
        <span className="truncate text-sm font-semibold text-slate-900">{text("调用历史", "Invocation history")}</span>
        {selectedTrigger ? <Badge tone="neutral" className="max-w-40 truncate">{selectedTrigger.name || selectedTrigger.type}</Badge> : null}
      </CardHeader>
      {!selectedTrigger ? <div className="p-6 text-center text-xs text-slate-500">{text("选择 Trigger 查看最近运行。", "Select a trigger to view recent runs.")}</div> : null}
      {selectedTrigger && isLoading ? <div className="p-6 text-center text-xs text-slate-500">{text("加载调用历史...", "Loading invocation history...")}</div> : null}
      {selectedTrigger && error ? <div className="p-4 text-xs text-red-700">{error.message}</div> : null}
      {selectedTrigger && !isLoading && !error && items.length === 0 ? <div className="p-6 text-center text-xs text-slate-500">{text("暂无运行记录", "No runs yet")}</div> : null}
      {items.length > 0 ? (
        <div className="divide-y divide-slate-100">
          {items.map((item) => (
            <div key={item.id} className="min-w-0 p-3 text-xs">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <Badge tone={statusTone(item.status)}>{item.status}</Badge>
                <span className="text-slate-500">{displayTime(item.started_at || item.created_at)}</span>
                <span className="text-slate-500">{text(`第 ${item.attempt ?? 1} 次`, `Attempt ${item.attempt ?? 1}`)}</span>
              </div>
              {item.error ? <div className="mt-2 break-words text-red-700">{item.error}</div> : null}
              {item.run_id ? <Link className="mt-2 inline-flex text-blue-700 hover:underline" aria-label={`${text("打开 Run", "Open Run")} ${item.run_id}`} to={`/runs/${encodeURIComponent(item.run_id)}`}>{text("打开 Run", "Open Run")} · {item.run_id}</Link> : null}
            </div>
          ))}
        </div>
      ) : null}
    </Card>
  );
}

function CredentialRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="text-xs font-medium text-slate-600">{label}</div>
      <div className="mt-1 max-w-full overflow-x-auto rounded-md border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-xs text-slate-800">{value}</div>
    </div>
  );
}

function triggerSummary(trigger: AgentTrigger, text: (zh: string, en: string) => string) {
  const config = trigger.config_json ?? {};
  if (trigger.type === "webhook") return trigger.endpoint_path ? `/api/webhook/trigger/${trigger.endpoint_path}` : text("路径由服务端生成", "Server-generated path");
  if (trigger.type === "schedule") return text(`每 ${String(config.interval_seconds ?? "-")} 秒`, `Every ${String(config.interval_seconds ?? "-")} seconds`);
  if (trigger.type === "file") return `${String(config.workspace_root_label ?? "本地工作区")} · ${String(config.pattern ?? "**/*")}`;
  return String(config.repo_root_label ?? config.workspace_root_label ?? "本地 Git 仓库");
}

function automationCapabilities(permissions: string[] | undefined, role: string | undefined) {
  if (permissions === undefined && role === undefined) return { create: true, update: true, delete: true };
  if (permissions?.length) {
    const all = permissions.includes("*");
    const configure = all || permissions.includes("agent:create");
    return { create: configure, update: configure, delete: all || permissions.includes("agent:delete") };
  }
  const normalizedRole = (role ?? "viewer").toLowerCase();
  const administrator = normalizedRole === "owner" || normalizedRole === "admin" || normalizedRole === "engineer";
  const member = administrator || normalizedRole === "member" || normalizedRole === "operator";
  return { create: member, update: member, delete: administrator };
}
