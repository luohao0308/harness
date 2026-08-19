import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  Check,
  FileDiff,
  FileImage,
  FolderOpen,
  GitBranch,
  LoaderCircle,
  RefreshCw,
  RotateCcw,
  TriangleAlert,
  Undo2,
} from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { useConfirmDialog } from "../../../components/ui/confirm-dialog";
import { feedbackErrorMessage, notifyFeedback } from "../../../components/ui/feedback-toast";
import { cn } from "../../../lib/utils";
import type {
  ChangeAuditContext,
  ChangeDiff,
  ChangeFile,
  ChangeMutationAction,
  ChangeReviewStatus,
  DesktopChangeReviewApi,
  DiffSection,
} from "../types";

type LoadState = "idle" | "loading" | "ready" | "error";

function getChangeReviewApi(): DesktopChangeReviewApi | null {
  if (typeof window === "undefined") return null;
  const desktopApi = (window as unknown as {
    desktopApi?: { changeReview?: Partial<DesktopChangeReviewApi> };
  }).desktopApi;
  const api = desktopApi?.changeReview;
  if (!api?.getStatus || !api.getDiff || !api.mutate) return null;
  return api as DesktopChangeReviewApi;
}

function getWorkspaceSelector(): (() => Promise<unknown>) | null {
  if (typeof window === "undefined") return null;
  const selectWorkspaceRoot = (window as unknown as {
    desktopApi?: { file?: { selectWorkspaceRoot?: () => Promise<unknown> } };
  }).desktopApi?.file?.selectWorkspaceRoot;
  return selectWorkspaceRoot ?? null;
}

export function ChangeReviewPage() {
  const api = getChangeReviewApi();
  const selectWorkspaceRoot = getWorkspaceSelector();
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState<ChangeReviewStatus | null>(null);
  const [statusLoad, setStatusLoad] = useState<LoadState>("idle");
  const [statusError, setStatusError] = useState<string | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [diff, setDiff] = useState<ChangeDiff | null>(null);
  const [diffLoad, setDiffLoad] = useState<LoadState>("idle");
  const [diffError, setDiffError] = useState<string | null>(null);
  const [selectedHunks, setSelectedHunks] = useState<Set<string>>(new Set());
  const [mutationPending, setMutationPending] = useState(false);
  const [workspaceSelecting, setWorkspaceSelecting] = useState(false);
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);
  const { confirm, confirmDialog } = useConfirmDialog();

  const selectedFile = useMemo(
    () => status?.files.find((file) => file.path === selectedPath) ?? null,
    [selectedPath, status],
  );

  const auditContext = useMemo<ChangeAuditContext | undefined>(() => {
    const context = {
      taskId: searchParams.get("task_id") || undefined,
      runId: searchParams.get("run_id") || undefined,
      approvalId: searchParams.get("approval_id") || undefined,
    };
    return context.taskId || context.runId || context.approvalId ? context : undefined;
  }, [searchParams]);

  const loadDiff = useCallback(async (path: string) => {
    if (!api) return;
    setDiffLoad("loading");
    setDiffError(null);
    setSelectedHunks(new Set());
    try {
      const result = await api.getDiff(path);
      setDiff(result);
      setDiffLoad("ready");
    } catch (error) {
      setDiff(null);
      setDiffError(feedbackErrorMessage(error, "无法读取变更详情"));
      setDiffLoad("error");
    }
  }, [api]);

  const loadStatus = useCallback(async (preferredPath?: string | null) => {
    if (!api) return;
    setStatusLoad("loading");
    setStatusError(null);
    try {
      const result = await api.getStatus();
      setStatus(result);
      setStatusLoad("ready");
      if (result.state !== "ready" || result.files.length === 0) {
        setSelectedPath(null);
        setDiff(null);
        return;
      }
      const nextPath = result.files.some((file) => file.path === preferredPath)
        ? preferredPath!
        : result.files[0].path;
      setSelectedPath(nextPath);
      await loadDiff(nextPath);
    } catch (error) {
      setStatus(null);
      setStatusError(feedbackErrorMessage(error, "无法读取工作区变更"));
      setStatusLoad("error");
    }
  }, [api, loadDiff]);

  useEffect(() => {
    if (api) void loadStatus();
  }, [api, loadStatus]);

  const selectFile = useCallback((path: string) => {
    setSelectedPath(path);
    setMobileDetailOpen(true);
    void loadDiff(path);
  }, [loadDiff]);

  const toggleHunk = (id: string) => {
    setSelectedHunks((current) => {
      const next = new Set(current);
      if (selectedFile?.untracked && diff) {
        const fileHunkIds = diff.sections
          .filter((section) => section.mode === "worktree" && section.canStage)
          .flatMap((section) => section.hunks.map((hunk) => hunk.id));
        const allSelected = fileHunkIds.length > 0 && fileHunkIds.every((hunkId) => current.has(hunkId));
        for (const hunkId of fileHunkIds) {
          if (allSelected) next.delete(hunkId);
          else next.add(hunkId);
        }
        return next;
      }
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const runMutation = async (action: ChangeMutationAction) => {
    if (!api || !diff || selectedHunks.size === 0) return;
    let eligibleHunkIds = diff.sections
      .filter((section) => sectionSupportsAction(section, action))
      .flatMap((section) => section.hunks)
      .filter((hunk) => selectedHunks.has(hunk.id))
      .map((hunk) => hunk.id);
    if (selectedFile?.untracked && action === "stage" && eligibleHunkIds.length > 0) {
      eligibleHunkIds = diff.sections
        .filter((section) => sectionSupportsAction(section, action))
        .flatMap((section) => section.hunks.map((hunk) => hunk.id));
    }
    if (eligibleHunkIds.length === 0) return;
    const wording = mutationWording(action);
    const confirmed = await confirm({
      title: wording.title,
      description: action === "revert"
        ? "撤销会修改工作区文件且无法从本页面恢复。执行前会再次校验预览，失效时不会写入。"
        : "执行前会再次校验预览；如果文件已经变化，本次操作会停止且不会写入。",
      confirmText: wording.confirm,
      variant: action === "revert" ? "danger" : "primary",
    });
    if (!confirmed) return;

    setMutationPending(true);
    try {
      const result = await api.mutate({
        previewToken: diff.previewToken,
        hunkIds: eligibleHunkIds,
        action,
        ...(auditContext ? { auditContext } : {}),
      });
      notifyFeedback({
        title: wording.success,
        description: result.auditId ? `审计记录 ${result.auditId}` : undefined,
        tone: "success",
      });
      await loadStatus(diff.path);
    } catch (error) {
      notifyFeedback({
        title: wording.failure,
        description: feedbackErrorMessage(error, "变更操作失败"),
        tone: "error",
      });
    } finally {
      setMutationPending(false);
    }
  };

  const chooseWorkspace = async () => {
    if (!selectWorkspaceRoot) return;
    setWorkspaceSelecting(true);
    try {
      const selected = await selectWorkspaceRoot();
      if (selected) await loadStatus();
    } catch (error) {
      notifyFeedback({
        title: "工作区选择失败",
        description: feedbackErrorMessage(error, "无法选择本地工作区"),
        tone: "error",
      });
    } finally {
      setWorkspaceSelecting(false);
    }
  };

  return (
    <ConsoleShell title="本地变更">
      <div className="flex min-h-0 flex-1 flex-col bg-white">
        <header className="flex min-h-14 items-center justify-between gap-3 border-b border-slate-200 px-4 py-2 sm:px-5">
          <div className="min-w-0">
            <h1 className="flex items-center gap-2 text-base font-semibold text-slate-950">
              <FileDiff className="h-4 w-4" aria-hidden="true" />
              本地变更
            </h1>
            <p className="mt-0.5 truncate text-xs text-slate-500">按文件和分块审查当前工作区</p>
          </div>
          {api ? (
            <Button
              type="button"
              variant="ghost"
              aria-label="刷新变更"
              title="刷新变更"
              disabled={statusLoad === "loading" || mutationPending}
              onClick={() => void loadStatus(selectedPath)}
              className="h-8 w-8 px-0"
            >
              <RefreshCw className={cn("h-4 w-4", statusLoad === "loading" && "animate-spin")} />
            </Button>
          ) : null}
        </header>

        {!api ? (
          <CenteredState
            icon={<GitBranch className="h-5 w-5" />}
            title="请在桌面应用中审查本地变更"
            detail="浏览器页面没有本地工作区权限。"
          />
        ) : statusLoad === "loading" && !status ? (
          <CenteredState icon={<LoaderCircle className="h-5 w-5 animate-spin" />} title="正在读取本地变更" />
        ) : statusError ? (
          <CenteredState icon={<TriangleAlert className="h-5 w-5" />} title="变更读取失败" detail={statusError} />
        ) : status && status.state !== "ready" ? (
          <StatusState
            status={status}
            canSelectWorkspace={Boolean(selectWorkspaceRoot)}
            workspaceSelecting={workspaceSelecting}
            onSelectWorkspace={() => void chooseWorkspace()}
          />
        ) : status?.files.length === 0 ? (
          <CenteredState icon={<Check className="h-5 w-5" />} title="工作区没有待审查变更" />
        ) : status ? (
          <div className="grid min-h-0 flex-1 min-[900px]:grid-cols-[minmax(15rem,22rem)_minmax(0,1fr)]">
            <FileList
              files={status.files}
              selectedPath={selectedPath}
              hiddenOnMobile={mobileDetailOpen}
              onSelect={selectFile}
            />
            <section
              aria-label="变更详情"
              className={cn(
                "min-h-0 min-w-0 flex-col overflow-hidden bg-white",
                mobileDetailOpen ? "flex" : "hidden min-[900px]:flex",
              )}
            >
              <div className="flex min-h-11 items-center gap-2 border-b border-slate-200 px-3 sm:px-4">
                <Button
                  type="button"
                  variant="ghost"
                  aria-label="返回文件列表"
                  className="h-8 w-8 px-0 min-[900px]:hidden"
                  onClick={() => setMobileDetailOpen(false)}
                >
                  <ArrowLeft className="h-4 w-4" />
                </Button>
                <span className="min-w-0 flex-1 truncate font-mono text-xs text-slate-700">
                  {selectedPath}
                </span>
              </div>
              <DiffView
                diff={diff}
                loadState={diffLoad}
                error={diffError}
                selectedHunks={selectedHunks}
                untracked={Boolean(selectedFile?.untracked)}
                mutationPending={mutationPending}
                onToggleHunk={toggleHunk}
                onMutation={(action) => void runMutation(action)}
              />
            </section>
          </div>
        ) : null}
      </div>
      {confirmDialog}
    </ConsoleShell>
  );
}

function FileList({
  files,
  selectedPath,
  hiddenOnMobile,
  onSelect,
}: {
  files: ChangeFile[];
  selectedPath: string | null;
  hiddenOnMobile: boolean;
  onSelect: (path: string) => void;
}) {
  const fileRefs = useRef<Array<HTMLButtonElement | null>>([]);
  return (
    <aside
      aria-label="变更文件"
      className={cn(
        "min-h-0 overflow-y-auto border-r border-slate-200 bg-slate-50/60",
        hiddenOnMobile ? "hidden min-[900px]:block" : "block",
      )}
    >
      <div className="sticky top-0 z-10 flex h-10 items-center justify-between border-b border-slate-200 bg-slate-50 px-3 text-xs font-medium text-slate-600">
        <span>文件</span>
        <span>{files.length}</span>
      </div>
      <div className="divide-y divide-slate-200">
        {files.map((file, index) => (
          <button
            key={file.path}
            ref={(node) => { fileRefs.current[index] = node; }}
            type="button"
            aria-label={`${file.path} ${fileStatusText(file)}`}
            aria-current={file.path === selectedPath ? "true" : undefined}
            onClick={() => onSelect(file.path)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                onSelect(file.path);
                return;
              }
              if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                const offset = event.key === "ArrowDown" ? 1 : -1;
                const nextIndex = Math.min(files.length - 1, Math.max(0, index + offset));
                fileRefs.current[nextIndex]?.focus();
              }
            }}
            className={cn(
              "flex min-h-12 w-full items-center gap-3 px-3 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-slate-400",
              file.path === selectedPath ? "bg-white" : "hover:bg-white/80",
            )}
          >
            <span className={cn(
              "flex h-6 w-6 shrink-0 items-center justify-center rounded font-mono text-[10px] font-semibold",
              file.conflicted ? "bg-red-100 text-red-700" : file.untracked ? "bg-emerald-100 text-emerald-700" : "bg-slate-200 text-slate-700",
            )}>
              {file.conflicted ? "U" : file.untracked ? "?" : file.indexStatus.trim() || file.worktreeStatus.trim() || "M"}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate font-mono text-xs text-slate-800">{file.path}</span>
              {file.previousPath ? <span className="mt-0.5 block truncate text-[10px] text-slate-500">原路径 {file.previousPath}</span> : null}
            </span>
            {file.conflicted ? <Badge tone="failed">冲突</Badge> : null}
          </button>
        ))}
      </div>
    </aside>
  );
}

function DiffView({
  diff,
  loadState,
  error,
  selectedHunks,
  untracked,
  mutationPending,
  onToggleHunk,
  onMutation,
}: {
  diff: ChangeDiff | null;
  loadState: LoadState;
  error: string | null;
  selectedHunks: Set<string>;
  untracked: boolean;
  mutationPending: boolean;
  onToggleHunk: (id: string) => void;
  onMutation: (action: ChangeMutationAction) => void;
}) {
  if (loadState === "loading") {
    return <CenteredState icon={<LoaderCircle className="h-5 w-5 animate-spin" />} title="正在生成 Diff" />;
  }
  if (error) {
    return <CenteredState icon={<TriangleAlert className="h-5 w-5" />} title="Diff 读取失败" detail={error} />;
  }
  if (!diff) {
    return <CenteredState icon={<FileDiff className="h-5 w-5" />} title="选择文件查看变更" />;
  }
  return (
    <div className="min-h-0 flex-1 overflow-auto">
      {diff.sections.map((section, index) => (
        <DiffSectionView
          key={`${section.mode}-${index}`}
          section={section}
          selectedHunks={selectedHunks}
          untracked={untracked}
          mutationPending={mutationPending}
          onToggleHunk={onToggleHunk}
          onMutation={onMutation}
        />
      ))}
    </div>
  );
}

function DiffSectionView({
  section,
  selectedHunks,
  untracked,
  mutationPending,
  onToggleHunk,
  onMutation,
}: {
  section: DiffSection;
  selectedHunks: Set<string>;
  untracked: boolean;
  mutationPending: boolean;
  onToggleHunk: (id: string) => void;
  onMutation: (action: ChangeMutationAction) => void;
}) {
  const selectedInSection = section.hunks.filter((hunk) => selectedHunks.has(hunk.id)).length;
  const wholeFileStage = untracked && section.mode === "worktree" && section.canStage;
  return (
    <section className="border-b border-slate-200" aria-label={section.mode === "staged" ? "已暂存变更" : "工作区变更"}>
      <div className="sticky top-0 z-[1] flex min-h-11 flex-wrap items-center gap-2 border-b border-slate-200 bg-white/95 px-3 py-1.5 backdrop-blur sm:px-4">
        <Badge tone={section.mode === "staged" ? "success" : "warning"}>
          {section.mode === "staged" ? "已暂存" : "工作区"}
        </Badge>
        <span className="text-[11px] text-slate-500">{section.hunks.length} 个分块</span>
        <div className="ml-auto flex items-center gap-1.5">
          {section.canStage ? (
            <Button disabled={selectedInSection === 0 || mutationPending} onClick={() => onMutation("stage")}>
              <Check className="h-3.5 w-3.5" />{wholeFileStage ? "暂存整文件" : "暂存所选"}
            </Button>
          ) : null}
          {section.canUnstage ? (
            <Button disabled={selectedInSection === 0 || mutationPending} onClick={() => onMutation("unstage")}>
              <Undo2 className="h-3.5 w-3.5" />取消暂存
            </Button>
          ) : null}
          {section.canRevert ? (
            <Button variant="danger" disabled={selectedInSection === 0 || mutationPending} onClick={() => onMutation("revert")}>
              <RotateCcw className="h-3.5 w-3.5" />撤销所选
            </Button>
          ) : null}
        </div>
      </div>
      {section.kind !== "text" ? (
        <SectionState section={section} />
      ) : (
        <div className="min-w-max bg-[#fbfbfc] py-2 font-mono text-xs leading-5">
          {section.headerLines.map((line, index) => (
            <div key={`${line}-${index}`} className="px-4 text-slate-500">{line}</div>
          ))}
          {section.hunks.map((hunk) => (
            <div key={hunk.id} className="mt-2">
              <label className="flex cursor-pointer items-center gap-2 bg-cyan-50 px-4 py-1 text-cyan-800">
                <input
                  type="checkbox"
                  checked={selectedHunks.has(hunk.id)}
                  onChange={() => onToggleHunk(hunk.id)}
                  aria-label={`选择${section.mode === "staged" ? "已暂存" : "工作区"}分块 ${hunk.header}`}
                  className="h-3.5 w-3.5 accent-slate-900"
                />
                <span>{hunk.header}</span>
                {wholeFileStage ? <span className="text-[10px] text-cyan-700">未跟踪文件将整份暂存</span> : null}
              </label>
              {hunk.lines.map((line, index) => (
                <div
                  key={`${index}-${line}`}
                  className={cn(
                    "whitespace-pre px-4",
                    line.startsWith("+") && !line.startsWith("+++") && "bg-emerald-50 text-emerald-900",
                    line.startsWith("-") && !line.startsWith("---") && "bg-red-50 text-red-900",
                    !line.startsWith("+") && !line.startsWith("-") && "text-slate-700",
                  )}
                >
                  {line || " "}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function SectionState({ section }: { section: DiffSection }) {
  const content = section.message || {
    binary: "二进制文件不提供文本预览",
    conflict: "文件包含未解决冲突",
    empty: "此区域没有可显示的变更",
    "too-large": "Diff 超过安全预览上限",
    text: "",
  }[section.kind];
  return (
    <div className="flex min-h-32 items-center gap-3 px-5 py-6 text-sm text-slate-600">
      {section.kind === "binary" ? <FileImage className="h-5 w-5 shrink-0" /> : <TriangleAlert className="h-5 w-5 shrink-0" />}
      <span>{content}</span>
    </div>
  );
}

function StatusState({
  status,
  canSelectWorkspace,
  workspaceSelecting,
  onSelectWorkspace,
}: {
  status: ChangeReviewStatus;
  canSelectWorkspace: boolean;
  workspaceSelecting: boolean;
  onSelectWorkspace: () => void;
}) {
  const states = {
    "no-workspace": ["尚未选择工作区", "请先在桌面设置中选择一个本地工作区。"],
    "not-repository": ["当前工作区不是 Git 仓库", "变更审查保持只读，不会初始化仓库。"],
    "git-unavailable": ["Git 当前不可用", "安装 Git 并重新打开桌面应用后再试。"],
    error: ["无法读取 Git 状态", status.message || "工作区仍可继续使用，变更审查暂时降级为只读错误态。"],
    ready: ["", ""],
  } as const;
  const [title, detail] = states[status.state];
  return (
    <CenteredState
      icon={status.state === "no-workspace" ? <FolderOpen className="h-5 w-5" /> : <TriangleAlert className="h-5 w-5" />}
      title={title}
      detail={detail}
      action={status.state === "no-workspace" && canSelectWorkspace ? (
        <Button type="button" disabled={workspaceSelecting} onClick={onSelectWorkspace}>
          <FolderOpen className="h-4 w-4" />
          {workspaceSelecting ? "正在选择" : "选择工作区"}
        </Button>
      ) : undefined}
    />
  );
}

function CenteredState({
  icon,
  title,
  detail,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  detail?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center px-6 py-12">
      <div className="max-w-md text-center">
        <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-md bg-slate-100 text-slate-600">{icon}</div>
        <div className="mt-3 text-sm font-semibold text-slate-900">{title}</div>
        {detail ? <div className="mt-1 text-xs leading-5 text-slate-500">{detail}</div> : null}
        {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
      </div>
    </div>
  );
}

function fileStatusText(file: ChangeFile): string {
  if (file.conflicted) return "冲突";
  if (file.untracked) return "未跟踪";
  if (file.staged && file.unstaged) return "已暂存且工作区有变更";
  if (file.staged) return "已暂存";
  return "工作区有变更";
}

function mutationWording(action: ChangeMutationAction) {
  if (action === "unstage") {
    return { title: "确认取消暂存所选分块", confirm: "确认取消暂存", success: "已取消暂存", failure: "取消暂存失败" };
  }
  if (action === "revert") {
    return { title: "确认撤销所选分块", confirm: "确认撤销", success: "已撤销工作区分块", failure: "撤销失败" };
  }
  return { title: "确认暂存所选分块", confirm: "确认暂存", success: "已暂存所选分块", failure: "暂存失败" };
}

function sectionSupportsAction(section: DiffSection, action: ChangeMutationAction): boolean {
  if (action === "stage") return section.canStage;
  if (action === "unstage") return section.canUnstage;
  return section.canRevert;
}
