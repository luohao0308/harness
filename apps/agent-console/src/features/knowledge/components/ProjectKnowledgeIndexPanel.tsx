import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  FolderOpen,
  Link2Off,
  Pause,
  Play,
  Plus,
  RefreshCw,
  ScanSearch,
  ShieldCheck,
} from "lucide-react";

import { Badge, type BadgeTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { ConfigDialog } from "../../../components/ui/config-dialog";
import { useConfirmDialog } from "../../../components/ui/confirm-dialog";
import { feedbackErrorMessage, notifyFeedback } from "../../../components/ui/feedback-toast";
import { Input, Textarea } from "../../../components/ui/input";
import { useI18n } from "../../../lib/i18n";
import { formatShortDate } from "../../../lib/utils";
import { scanAndSyncProjectKnowledgeIndex, projectSnapshotToSyncPayload } from "../../../lib/project-knowledge-sync";
import {
  createAgentProjectKnowledgeIndex,
  listAgentProjectKnowledgeIndexes,
  pauseAgentProjectKnowledgeIndex,
  resumeAgentProjectKnowledgeIndex,
  syncAgentProjectKnowledgeIndex,
  unbindAgentProjectKnowledgeIndex,
  type ProjectKnowledgeIndex,
} from "../../tasks/api";

const queryKeyForProjectIndexes = (agentId: string) =>
  ["agent-project-knowledge", agentId] as const;

type IndexAction = "scan" | "pause" | "resume" | "unbind";

class ProjectKnowledgeProfileChangedError extends Error {}

export function parseProjectIgnorePatterns(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean),
    ),
  );
}

export function ProjectKnowledgeIndexPanel({ agentId }: { agentId: string }) {
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const { confirm, confirmDialog } = useConfirmDialog();
  const [bindOpen, setBindOpen] = useState(false);
  const [rootSelected, setRootSelected] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [ignoreText, setIgnoreText] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const indexes = useQuery({
    queryKey: queryKeyForProjectIndexes(agentId),
    queryFn: () => listAgentProjectKnowledgeIndexes(agentId),
  });
  const desktopReady = Boolean(
    window.desktopApi?.file?.selectWorkspaceRoot
      && window.desktopApi.file.scanProjectKnowledge
      && window.desktopApi.profile?.list,
  );

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeyForProjectIndexes(agentId) }),
      queryClient.invalidateQueries({ queryKey: ["agent-knowledge", agentId] }),
    ]);
  };

  const createMutation = useMutation({
    mutationFn: async () => {
      const listProfiles = window.desktopApi?.profile?.list;
      const scan = window.desktopApi?.file?.scanProjectKnowledge;
      if (!listProfiles || !scan) {
        throw new Error(text("当前环境不支持项目目录扫描", "Project scanning is unavailable"));
      }
      if (!rootSelected) {
        throw new Error(text("请先选择项目目录", "Select a project directory first"));
      }
      if (!name.trim()) {
        throw new Error(text("请输入索引名称", "Enter an index name"));
      }

      const contextController = new AbortController();
      let profileChanged = false;
      const unsubscribeProfile = window.desktopApi?.events?.onProfileChanged?.(() => {
        profileChanged = true;
        contextController.abort();
      });
      const profileChangedError = () => new ProjectKnowledgeProfileChangedError(text(
        "绑定期间 Desktop Profile 已切换，请重新绑定",
        "The Desktop Profile changed while linking. Link the directory again.",
      ));

      try {
        const ignorePatterns = parseProjectIgnorePatterns(ignoreText);
        const profileList = await listProfiles();
        const getWorkspaceRoot = window.desktopApi?.file?.getWorkspaceRoot;
        const rootBeforeScan = getWorkspaceRoot ? await getWorkspaceRoot() : null;
        const snapshot = await scan({ ignorePatterns });
        const [currentProfileList, rootAfterScan] = await Promise.all([
          listProfiles(),
          getWorkspaceRoot ? getWorkspaceRoot() : Promise.resolve(null),
        ]);
        if (
          profileChanged
          || currentProfileList.activeProfileId !== profileList.activeProfileId
        ) {
          throw profileChangedError();
        }
        if (rootBeforeScan?.rootPath !== rootAfterScan?.rootPath) {
          throw new Error(text("扫描期间项目目录已切换，请重新绑定", "The project directory changed during scanning. Link the directory again."));
        }
        const createPayload = {
          name: name.trim(),
          description: description.trim(),
          desktop_profile_id: profileList.activeProfileId,
          root_identity: snapshot.rootIdentity,
          ignore_patterns: ignorePatterns,
          idempotency_key: [
            "desktop-project",
            profileList.activeProfileId,
            snapshot.rootIdentity,
            Date.now(),
          ].join(":"),
        };
        let createdIndexId: string | null = null;
        try {
          const created = await createAgentProjectKnowledgeIndex(
            agentId,
            createPayload,
            contextController.signal,
          );
          createdIndexId = created.id;
          if (profileChanged) throw profileChangedError();
          const synced = await syncAgentProjectKnowledgeIndex(
            agentId,
            created.id,
            projectSnapshotToSyncPayload(snapshot, profileList.activeProfileId),
            contextController.signal,
          );
          if (profileChanged) throw profileChangedError();
          return synced;
        } catch (error) {
          if (profileChanged) {
            try {
              const indexId = createdIndexId ?? (
                await createAgentProjectKnowledgeIndex(agentId, createPayload)
              ).id;
              await unbindAgentProjectKnowledgeIndex(agentId, indexId, {
                reason: "desktop_profile_changed_during_initial_link",
              });
            } catch {
              // Preserve the Profile-change error; refresh exposes any cleanup failure for retry.
            }
            throw profileChangedError();
          }
          throw error;
        }
      } catch (error) {
        if (profileChanged) throw profileChangedError();
        throw error;
      } finally {
        unsubscribeProfile?.();
      }
    },
    onSuccess: async () => {
      setActionError(null);
      setBindOpen(false);
      setRootSelected(false);
      setName("");
      setDescription("");
      setIgnoreText("");
      await refresh();
      notifyFeedback({
        tone: "success",
        title: text("项目索引已绑定", "Project index linked"),
        description: text("首次安全扫描与增量同步已完成。", "The first safe scan and incremental sync completed."),
      });
    },
    onError: async (error) => {
      setActionError(
        error instanceof ProjectKnowledgeProfileChangedError
          ? error.message
          : feedbackErrorMessage(error, text("项目索引创建失败", "Failed to create project index")),
      );
      await refresh();
    },
  });

  const actionMutation = useMutation({
    mutationFn: async ({ action, index }: { action: IndexAction; index: ProjectKnowledgeIndex }) => {
      if (action === "scan") return scanAndSyncProjectKnowledgeIndex(agentId, index);
      if (action === "pause") return pauseAgentProjectKnowledgeIndex(agentId, index.id);
      if (action === "resume") return resumeAgentProjectKnowledgeIndex(agentId, index.id);
      return unbindAgentProjectKnowledgeIndex(agentId, index.id);
    },
    onSuccess: async (_result, variables) => {
      setActionError(null);
      await refresh();
      const titles: Record<IndexAction, string> = {
        scan: text("项目索引已更新", "Project index updated"),
        pause: text("项目索引已暂停", "Project index paused"),
        resume: text("项目索引已恢复", "Project index resumed"),
        unbind: text("项目索引已解绑", "Project index unlinked"),
      };
      notifyFeedback({ tone: "success", title: titles[variables.action] });
    },
    onError: (error) => {
      setActionError(feedbackErrorMessage(error, text("项目索引操作失败", "Project index action failed")));
    },
  });

  const selectRoot = async () => {
    const selectWorkspaceRoot = window.desktopApi?.file?.selectWorkspaceRoot;
    if (!selectWorkspaceRoot) return;
    const selected = await selectWorkspaceRoot();
    setRootSelected(Boolean(selected?.rootPath));
  };

  const requestUnbind = async (index: ProjectKnowledgeIndex) => {
    const confirmed = await confirm({
      title: text("解绑项目索引", "Unlink project index"),
      description: text(
        `“${index.name}” 将停止扫描并归档当前知识源。项目文件不会被修改，历史引用证据仍会保留。`,
        `“${index.name}” will stop scanning and archive its knowledge source. Project files stay unchanged and historical citations remain available.`,
      ),
      confirmText: text("确认解绑", "Unlink"),
      variant: "danger",
    });
    if (confirmed) actionMutation.mutate({ action: "unbind", index });
  };

  const items = indexes.data?.items ?? [];

  return (
    <section className="min-w-0 border-y border-slate-200 bg-white">
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-3 px-3 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <ScanSearch className="h-4 w-4 shrink-0" />
            {text("项目自动索引", "Project auto-indexing")}
            <Badge tone="neutral">{items.length}</Badge>
          </div>
          <p className="mt-1 max-w-3xl text-xs leading-5 text-slate-500">
            {text(
              "Desktop 安全扫描受控目录，文件变化自动增量入库；默认密钥、依赖和构建目录始终排除。",
              "Desktop safely scans a controlled directory and incrementally indexes changes; secrets, dependencies, and build output are always excluded.",
            )}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button
            type="button"
            aria-label={text("刷新项目索引", "Refresh project indexes")}
            disabled={indexes.isFetching}
            onClick={() => void indexes.refetch()}
          >
            <RefreshCw className={indexes.isFetching ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} />
            {text("刷新", "Refresh")}
          </Button>
          {desktopReady ? (
            <Button type="button" variant="primary" onClick={() => setBindOpen(true)}>
              <Plus className="h-3.5 w-3.5" />
              {text("绑定目录", "Link directory")}
            </Button>
          ) : null}
        </div>
      </div>

      {!desktopReady ? (
        <div className="border-t border-slate-100 bg-slate-50 px-3 py-2 text-xs text-slate-600">
          {text(
            "当前可查看索引状态；目录绑定与本机重扫需要在 Harness Desktop 中操作。",
            "Index status remains visible here; linking and local rescans require Harness Desktop.",
          )}
        </div>
      ) : null}
      {actionError ? (
        <div role="alert" className="border-t border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {actionError}
        </div>
      ) : null}
      {indexes.isLoading ? (
        <div className="border-t border-slate-100 px-3 py-6 text-center text-xs text-slate-500">
          {text("正在加载项目索引...", "Loading project indexes...")}
        </div>
      ) : null}
      {indexes.error ? (
        <div role="alert" className="border-t border-red-200 bg-red-50 px-3 py-3 text-xs text-red-700">
          <div>{feedbackErrorMessage(indexes.error, text("项目索引加载失败", "Failed to load project indexes"))}</div>
          <Button className="mt-2" onClick={() => void indexes.refetch()}>{text("重试", "Retry")}</Button>
        </div>
      ) : null}
      {!indexes.isLoading && !indexes.error && items.length === 0 ? (
        <div className="border-t border-slate-100 px-3 py-8 text-center">
          <ShieldCheck className="mx-auto h-6 w-6 text-slate-300" />
          <div className="mt-2 text-sm font-medium text-slate-800">
            {text("暂无项目索引", "No project indexes")}
          </div>
          <div className="mt-1 text-xs text-slate-500">
            {desktopReady
              ? text("绑定一个本机项目目录后，Desktop 会持续同步可索引文本。", "Link a local project directory to keep indexable text synchronized.")
              : text("请在 Harness Desktop 中绑定第一个项目目录。", "Link the first project directory in Harness Desktop.")}
          </div>
        </div>
      ) : null}
      {items.length > 0 ? (
        <div className="divide-y divide-slate-100 border-t border-slate-100">
          {items.map((index) => {
            const pending = actionMutation.isPending
              && actionMutation.variables?.index.id === index.id;
            return (
              <ProjectIndexRow
                key={index.id}
                index={index}
                desktopReady={desktopReady}
                pending={pending}
                onAction={(action) => actionMutation.mutate({ action, index })}
                onUnbind={() => void requestUnbind(index)}
              />
            );
          })}
        </div>
      ) : null}

      <ConfigDialog
        open={bindOpen}
        title={text("绑定项目目录", "Link project directory")}
        description={text(
          "绝对目录路径只保存在当前 Desktop Profile；纳入索引的文本内容、相对路径、内容哈希和不可逆目录身份会发送到当前 Harness API。",
          "The absolute directory path stays in the current Desktop Profile. Indexed text, relative paths, content hashes, and an irreversible root identity are sent to the current Harness API.",
        )}
        onClose={() => {
          if (!createMutation.isPending) setBindOpen(false);
        }}
      >
        <div className="space-y-4 p-6">
          <label className="block text-xs font-medium text-slate-700">
            {text("索引名称", "Index name")}
            <Input
              className="mt-1 w-full"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={text("例如：Harness 项目", "For example: Harness project")}
            />
          </label>
          <label className="block text-xs font-medium text-slate-700">
            {text("说明（可选）", "Description (optional)")}
            <Input
              className="mt-1 w-full"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </label>
          <div>
            <div className="text-xs font-medium text-slate-700">{text("项目目录", "Project directory")}</div>
            <div className="mt-1 flex min-w-0 flex-wrap items-center gap-2">
              <Button type="button" onClick={() => void selectRoot()}>
                <FolderOpen className="h-3.5 w-3.5" />
                {rootSelected ? text("重新选择", "Choose again") : text("选择目录", "Choose directory")}
              </Button>
              <span className="text-xs text-slate-500">
                {rootSelected ? text("已选择；绝对路径不会上传或显示", "Selected; the absolute path is not uploaded or displayed") : text("尚未选择", "Not selected")}
              </span>
            </div>
          </div>
          <div>
            <label htmlFor="project-knowledge-ignore-patterns" className="block text-xs font-medium text-slate-700">
              {text("附加忽略规则", "Additional ignore patterns")}
            </label>
            <Textarea
              id="project-knowledge-ignore-patterns"
              className="mt-1 w-full font-mono text-xs"
              value={ignoreText}
              onChange={(event) => setIgnoreText(event.target.value)}
              placeholder={"docs/archive/**\n*.generated.md"}
            />
            <span className="mt-1 block text-[11px] leading-5 text-slate-500">
              {text("每行一条，只能扩大排除范围，不能取消内置安全规则。", "One pattern per line. Patterns can only add exclusions and cannot disable built-in safety rules.")}
            </span>
          </div>
          <div className="flex flex-wrap justify-end gap-2 border-t border-slate-100 pt-4">
            <Button type="button" variant="ghost" disabled={createMutation.isPending} onClick={() => setBindOpen(false)}>
              {text("取消", "Cancel")}
            </Button>
            <Button
              type="button"
              variant="primary"
              disabled={createMutation.isPending || !rootSelected || !name.trim()}
              onClick={() => createMutation.mutate()}
            >
              <ScanSearch className={createMutation.isPending ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} />
              {createMutation.isPending ? text("正在扫描...", "Scanning...") : text("绑定并首次同步", "Link and sync")}
            </Button>
          </div>
        </div>
      </ConfigDialog>
      {confirmDialog}
    </section>
  );
}

function ProjectIndexRow({
  index,
  desktopReady,
  pending,
  onAction,
  onUnbind,
}: {
  index: ProjectKnowledgeIndex;
  desktopReady: boolean;
  pending: boolean;
  onAction: (action: Exclude<IndexAction, "unbind">) => void;
  onUnbind: () => void;
}) {
  const { text } = useI18n();
  const status = projectIndexStatus(index.status, text);
  const canManage = index.status !== "UNBOUND";
  const canScan = desktopReady && (index.status === "ACTIVE" || index.status === "ERROR");

  return (
    <article className="min-w-0 px-3 py-3">
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span className="break-words text-sm font-semibold text-slate-900">{index.name}</span>
            <Badge tone={status.tone}>{status.label}</Badge>
          </div>
          {index.description ? <p className="mt-1 break-words text-xs text-slate-500">{index.description}</p> : null}
          <div className="mt-2 flex min-w-0 flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-slate-500">
            <span className="break-all">profile:{index.desktop_profile_id}</span>
            <span>root:{shortIdentity(index.root_identity)}</span>
            <span>generation:{index.snapshot_generation}</span>
          </div>
        </div>
        {canManage ? (
          <div className="flex shrink-0 flex-wrap gap-2">
            {canScan ? (
              <Button type="button" disabled={pending} onClick={() => onAction("scan")}>
                <RefreshCw className={pending ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} />
                {text("重扫", "Rescan")}
              </Button>
            ) : null}
            {index.status === "PAUSED" ? (
              <Button type="button" disabled={pending} onClick={() => onAction("resume")}>
                <Play className="h-3.5 w-3.5" /> {text("恢复", "Resume")}
              </Button>
            ) : (
              <Button type="button" disabled={pending} onClick={() => onAction("pause")}>
                <Pause className="h-3.5 w-3.5" /> {text("暂停", "Pause")}
              </Button>
            )}
            <Button type="button" variant="ghost" disabled={pending} onClick={onUnbind}>
              <Link2Off className="h-3.5 w-3.5" /> {text("解绑", "Unlink")}
            </Button>
          </div>
        ) : null}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-4">
        <IndexMetric label={text("扫描文件", "Scanned")} value={index.file_count} />
        <IndexMetric label={text("已索引", "Indexed")} value={index.indexed_file_count} />
        <IndexMetric label={text("错误", "Errors")} value={index.error_file_count} warning={index.error_file_count > 0} />
        <IndexMetric label={text("最后同步", "Last sync")} value={formatShortDate(index.last_sync_at)} />
      </div>
      {index.last_error ? (
        <div className="mt-2 break-words border-l-2 border-red-300 pl-2 text-xs leading-5 text-red-700">
          {index.last_error}
        </div>
      ) : null}
    </article>
  );
}

function IndexMetric({
  label,
  value,
  warning = false,
}: {
  label: string;
  value: string | number;
  warning?: boolean;
}) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className={warning ? "mt-0.5 break-words text-xs font-semibold text-red-700" : "mt-0.5 break-words text-xs font-semibold text-slate-800"}>
        {value}
      </div>
    </div>
  );
}

function shortIdentity(identity: string) {
  return identity.length <= 12 ? identity : `${identity.slice(0, 12)}...`;
}

function projectIndexStatus(
  status: ProjectKnowledgeIndex["status"],
  text: (zh: string, en: string) => string,
): { label: string; tone: BadgeTone } {
  const labels: Record<ProjectKnowledgeIndex["status"], { zh: string; en: string; tone: BadgeTone }> = {
    ACTIVE: { zh: "同步中", en: "Active", tone: "success" },
    PAUSED: { zh: "已暂停", en: "Paused", tone: "warning" },
    ERROR: { zh: "有错误", en: "Error", tone: "failed" },
    UNBOUND: { zh: "已解绑", en: "Unlinked", tone: "neutral" },
  };
  const item = labels[status];
  return { label: text(item.zh, item.en), tone: item.tone };
}
