import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Check,
  ChevronRight,
  CircleX,
  Inbox,
  RefreshCw,
  RotateCw,
  Settings2,
} from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { notifyFeedback } from "../../../components/ui/feedback-toast";
import { cn, formatShortDate } from "../../../lib/utils";
import {
  approveToolApproval,
  getDesktopAttention,
  rejectToolApproval,
  type DesktopAttentionItem,
} from "../../tasks/api";

type AttentionFilter = "all" | "approvals" | "runs" | "teams" | "local";

type LocalAttentionItem = {
  id: string;
  category: "local";
  kind: "sync_conflict" | "sync_error" | "runtime_error";
  severity: "critical" | "warning";
  title: string;
  description: string;
  status: string;
  occurred_at: string;
  target_path: string;
  actions: readonly ("sync" | "settings")[];
};

type AttentionItem = DesktopAttentionItem | LocalAttentionItem;

type LocalAttentionProjection = {
  items: LocalAttentionItem[];
  warnings: string[];
};

const filterLabels: Record<AttentionFilter, string> = {
  all: "全部",
  approvals: "审批",
  runs: "运行",
  teams: "团队",
  local: "本地",
};

const categoryLabels: Record<AttentionItem["category"], string> = {
  approvals: "审批",
  runs: "运行",
  teams: "团队",
  local: "本地",
};

export function AttentionCenterPage() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<AttentionFilter>("all");
  const [announcement, setAnnouncement] = useState("");
  const desktopAvailable = typeof window !== "undefined" && Boolean(window.desktopApi);

  const serverAttention = useQuery({
    queryKey: ["desktop", "attention"],
    queryFn: () => getDesktopAttention(),
    retry: false,
  });
  const localAttention = useQuery({
    queryKey: ["desktop", "attention", "local"],
    queryFn: loadLocalAttention,
    enabled: desktopAvailable,
    retry: false,
  });

  const approvalMutation = useMutation({
    mutationFn: async ({ item, decision }: { item: DesktopAttentionItem; decision: "approve" | "reject" }) => {
      if (!item.task_id || !item.approval_id) throw new Error("审批对象缺少关联信息");
      if (decision === "approve") {
        await approveToolApproval(item.task_id, item.approval_id, "通过统一待处理中心批准");
      } else {
        await rejectToolApproval(item.task_id, item.approval_id, "通过统一待处理中心拒绝");
      }
      return { item, decision };
    },
    onSuccess: async ({ item, decision }) => {
      const message = decision === "approve" ? `已批准 ${item.title}` : `已拒绝 ${item.title}`;
      setAnnouncement(message);
      notifyFeedback({ title: message, description: "待处理列表已刷新", tone: "success" });
      await queryClient.invalidateQueries({ queryKey: ["desktop", "attention"] });
    },
    onError: (error) => {
      setAnnouncement(error instanceof Error ? error.message : "审批操作失败");
    },
  });

  const syncMutation = useMutation({
    mutationFn: async () => {
      const runNow = window.desktopApi?.sync?.runNow;
      if (!runNow) throw new Error("桌面同步不可用");
      return runNow();
    },
    onSuccess: async () => {
      setAnnouncement("同步已完成，正在刷新本地状态");
      await queryClient.invalidateQueries({ queryKey: ["desktop", "attention", "local"] });
    },
    onError: (error) => {
      setAnnouncement(error instanceof Error ? error.message : "同步失败");
    },
  });

  const items = useMemo(() => {
    return sortAttentionItems([
      ...(serverAttention.data?.items ?? []),
      ...(localAttention.data?.items ?? []),
    ]);
  }, [localAttention.data?.items, serverAttention.data?.items]);
  const visibleItems = filter === "all" ? items : items.filter((item) => item.category === filter);
  const filterCounts: Record<AttentionFilter, number> = {
    all: items.length,
    approvals: items.filter((item) => item.category === "approvals").length,
    runs: items.filter((item) => item.category === "runs").length,
    teams: items.filter((item) => item.category === "teams").length,
    local: items.filter((item) => item.category === "local").length,
  };

  async function refreshAll() {
    await Promise.all([
      serverAttention.refetch(),
      desktopAvailable ? localAttention.refetch() : Promise.resolve(),
    ]);
  }

  const refreshing = serverAttention.isFetching || localAttention.isFetching;

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden bg-white">
      <header className="shrink-0 border-b border-slate-200 px-5 py-4 sm:px-7">
        <div className="mx-auto flex w-full max-w-5xl items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-lg font-semibold text-slate-950">待处理</h1>
            <p className="mt-1 text-sm text-slate-600">审批、异常运行、团队阻塞与本地恢复项</p>
          </div>
          <Button
            type="button"
            aria-label="刷新待处理"
            disabled={refreshing}
            onClick={() => void refreshAll()}
          >
            <RefreshCw aria-hidden="true" className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
            刷新
          </Button>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-7">
        <div className="mx-auto w-full max-w-5xl">
          <div className="flex flex-wrap gap-1" role="group" aria-label="待处理筛选">
            {(Object.keys(filterLabels) as AttentionFilter[]).map((key) => (
              <button
                key={key}
                type="button"
                aria-pressed={filter === key}
                className={cn(
                  "h-8 rounded-md px-3 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300",
                  filter === key
                    ? "bg-slate-900 text-white"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-950",
                )}
                onClick={() => setFilter(key)}
              >
                {filterLabels[key]} {filterCounts[key]}
              </button>
            ))}
          </div>

          <div aria-live="polite" className="sr-only">{announcement}</div>

          {localAttention.data?.warnings.map((warning) => (
            <div
              key={warning}
              role="status"
              className="mt-3 flex items-center gap-2 border-l-2 border-amber-400 bg-amber-50 px-3 py-2 text-xs text-amber-900"
            >
              <AlertTriangle aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
              {warning}
            </div>
          ))}

          {serverAttention.isError ? (
            <div role="alert" className="mt-4 border-l-2 border-red-500 bg-red-50 px-4 py-3 text-sm text-red-800">
              <div className="font-medium">服务器待处理项加载失败</div>
              <button
                type="button"
                className="mt-2 text-xs font-medium underline underline-offset-2"
                onClick={() => void serverAttention.refetch()}
              >
                重试
              </button>
            </div>
          ) : null}

          {serverAttention.isLoading ? (
            <div aria-label="正在加载待处理" className="mt-4 divide-y divide-slate-100 border-y border-slate-200">
              {[0, 1, 2].map((index) => (
                <div key={index} className="h-24 animate-pulse bg-slate-50/70" />
              ))}
            </div>
          ) : visibleItems.length > 0 ? (
            <ul className="mt-4 divide-y divide-slate-100 border-y border-slate-200">
              {visibleItems.map((item) => (
                <AttentionItemRow
                  key={item.id}
                  item={item}
                  actionPending={approvalMutation.isPending || syncMutation.isPending}
                  onApproval={(approvalItem, decision) => approvalMutation.mutate({ item: approvalItem, decision })}
                  onSync={() => syncMutation.mutate()}
                />
              ))}
            </ul>
          ) : (
            <div className="mt-12 flex flex-col items-center text-center text-slate-500">
              <Inbox aria-hidden="true" className="h-8 w-8 text-slate-300" />
              <p className="mt-3 text-sm font-medium text-slate-700">
                {filter === "all" ? "暂无待处理事项" : `暂无${filterLabels[filter]}待处理事项`}
              </p>
              {filter !== "all" ? (
                <button
                  type="button"
                  className="mt-2 text-xs font-medium text-slate-700 underline underline-offset-2"
                  onClick={() => setFilter("all")}
                >
                  返回全部
                </button>
              ) : null}
            </div>
          )}

          {serverAttention.data?.truncated ? (
            <p className="mt-3 text-xs text-slate-500">仅显示优先级最高的待处理事项。</p>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function AttentionItemRow({
  item,
  actionPending,
  onApproval,
  onSync,
}: {
  item: AttentionItem;
  actionPending: boolean;
  onApproval: (item: DesktopAttentionItem, decision: "approve" | "reject") => void;
  onSync: () => void;
}) {
  const isApproval = item.category === "approvals" && item.kind === "tool_approval";
  const canApprove = isApproval && item.actions.includes("approve");
  const canReject = isApproval && item.actions.includes("reject");
  return (
    <li className="flex min-w-0 flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={item.severity === "critical" ? "failed" : "warning"}>
            {categoryLabels[item.category]}
          </Badge>
          <span className="text-xs font-medium text-slate-600">{statusLabel(item)}</span>
          <span className="text-xs text-slate-400">{formatShortDate(item.occurred_at)}</span>
        </div>
        <h2 className="mt-2 break-words text-sm font-semibold text-slate-950">{item.title}</h2>
        <p className="mt-1 break-words text-sm leading-5 text-slate-600">{item.description}</p>
        {isApproval && item.tool_name ? (
          <p className="mt-1 font-mono text-[11px] text-slate-500">{item.tool_name}</p>
        ) : null}
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-2 sm:justify-end">
        {canApprove || canReject ? (
          <>
            {canApprove ? (
              <Button
                type="button"
                aria-label={`批准${item.title}`}
                disabled={actionPending}
                onClick={() => onApproval(item, "approve")}
              >
                <Check aria-hidden="true" className="h-3.5 w-3.5" />
                批准
              </Button>
            ) : null}
            {canReject ? (
              <Button
                type="button"
                variant="danger"
                aria-label={`拒绝${item.title}`}
                disabled={actionPending}
                onClick={() => onApproval(item, "reject")}
              >
                <CircleX aria-hidden="true" className="h-3.5 w-3.5" />
                拒绝
              </Button>
            ) : null}
          </>
        ) : null}
        {item.category === "local" && item.actions.includes("sync") ? (
          <Button type="button" disabled={actionPending} onClick={onSync}>
            <RotateCw aria-hidden="true" className="h-3.5 w-3.5" />
            立即同步
          </Button>
        ) : null}
        {item.category === "local" && item.actions.includes("settings") ? (
          <Link
            to={item.target_path}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-slate-200 px-3 text-xs font-medium text-slate-700 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300"
          >
            <Settings2 aria-hidden="true" className="h-3.5 w-3.5" />
            打开设置
          </Link>
        ) : null}
        {item.category !== "local" ? (
          <Link
            to={item.target_path}
            aria-label={`查看${item.title}`}
            className="inline-flex h-8 items-center gap-1 rounded-md px-2 text-xs font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300"
          >
            查看
            <ChevronRight aria-hidden="true" className="h-3.5 w-3.5" />
          </Link>
        ) : null}
      </div>
    </li>
  );
}

async function loadLocalAttention(): Promise<LocalAttentionProjection> {
  const api = window.desktopApi;
  if (!api) return { items: [], warnings: [] };

  const [syncStatusResult, conflictsResult, runtimeResult] = await Promise.allSettled([
    api.sync?.getStatus?.(),
    api.sync?.getConflicts?.(),
    api.localRuntime?.getModelStatus?.(),
  ]);
  const items: LocalAttentionItem[] = [];
  const warnings: string[] = [];
  const now = new Date().toISOString();

  if (syncStatusResult.status === "rejected") {
    warnings.push("同步状态读取失败");
  } else if (syncStatusResult.value) {
    const status = syncStatusResult.value;
    if (status.state === "error" || status.online === false) {
      items.push({
        id: "local:sync-status",
        category: "local",
        kind: "sync_error",
        severity: status.online === false ? "warning" : "critical",
        title: status.online === false ? "当前处于离线状态" : "桌面同步需要处理",
        description: status.lastError || (status.online === false ? "连接恢复后可重新同步" : "同步运行失败"),
        status: status.state,
        occurred_at: status.lastChangeTimestamp || now,
        target_path: "/desktop",
        actions: ["sync", "settings"],
      });
    }
  }

  if (conflictsResult.status === "rejected") {
    warnings.push("同步冲突读取失败");
  } else if (conflictsResult.value) {
    for (const task of conflictsResult.value.tasks) {
      items.push({
        id: `local:task-conflict:${task.id}`,
        category: "local",
        kind: "sync_conflict",
        severity: "warning",
        title: task.title || `本地任务 ${task.id}`,
        description: "本地与服务器版本存在冲突",
        status: "conflict",
        occurred_at: task.updated_at || now,
        target_path: "/desktop",
        actions: ["sync", "settings"],
      });
    }
    for (const conflict of conflictsResult.value.serverConflicts) {
      items.push({
        id: `local:server-conflict:${conflict.entity_type}:${conflict.entity_id}`,
        category: "local",
        kind: "sync_conflict",
        severity: "warning",
        title: `同步冲突 ${conflict.entity_id}`,
        description: `${conflict.entity_type} 的本地与服务器版本需要确认`,
        status: "conflict",
        occurred_at: now,
        target_path: "/desktop",
        actions: ["sync", "settings"],
      });
    }
  }

  if (runtimeResult.status === "rejected") {
    warnings.push("本地 Runtime 状态读取失败");
  } else if (runtimeResult.value && ["error", "setup_required"].includes(runtimeResult.value.state)) {
    items.push({
      id: "local:runtime-status",
      category: "local",
      kind: "runtime_error",
      severity: runtimeResult.value.state === "error" ? "critical" : "warning",
      title: "本地 Runtime 需要处理",
      description: runtimeResult.value.message || "请检查模型与密钥设置",
      status: runtimeResult.value.state,
      occurred_at: now,
      target_path: "/desktop?section=models",
      actions: ["settings"],
    });
  }

  return { items: dedupeLocalItems(items), warnings };
}

function dedupeLocalItems(items: LocalAttentionItem[]) {
  return [...new Map(items.map((item) => [item.id, item])).values()];
}

function sortAttentionItems(items: AttentionItem[]) {
  return [...items].sort((left, right) => {
    const severity = Number(left.severity === "warning") - Number(right.severity === "warning");
    if (severity !== 0) return severity;
    const timestamp = Date.parse(right.occurred_at) - Date.parse(left.occurred_at);
    return Number.isNaN(timestamp) || timestamp === 0 ? left.id.localeCompare(right.id) : timestamp;
  });
}

function statusLabel(item: AttentionItem) {
  const labels: Record<string, string> = {
    PENDING: "等待审批",
    FAILED: "运行失败",
    CANCELLED: "已取消",
    WAITING_APPROVAL: "等待处理",
    blocked: "已阻塞",
    failed: "执行失败",
    conflict: "同步冲突",
    error: "需要恢复",
    setup_required: "需要配置",
  };
  return labels[item.status] ?? item.status;
}
