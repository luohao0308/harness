import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckSquare, GitBranch, ListFilter, XCircle } from "lucide-react";
import { Link } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { useI18n } from "../../../lib/i18n";
import { statusLabel } from "../../../lib/labels";
import { formatShortDate } from "../../../lib/utils";
import { bulkCancelSubagents, listSubagents, type SubagentListItem } from "../../tasks/api";

const statusFilters = ["ALL", "PENDING", "RUNNING", "SUCCESS", "FAILED", "TIMEOUT", "CANCELLED"];

function contextSummary(context: Record<string, unknown>) {
  const label = context.label;
  const goal = context.goal;
  const description = context.description;
  if (typeof label === "string" && label.length > 0) return label;
  if (typeof goal === "string" && goal.length > 0) return goal;
  if (typeof description === "string" && description.length > 0) return description;
  return "子代理上下文";
}

function resultContextSummary(context: Record<string, unknown>) {
  const result = context.result;
  if (!result || typeof result !== "object") return "尚无压缩摘要";
  const contextSummary = (result as Record<string, unknown>).context_summary;
  if (!contextSummary || typeof contextSummary !== "object") return "尚无压缩摘要";
  const data = contextSummary as Record<string, unknown>;
  const total = typeof data.total_tool_results === "number" ? data.total_tool_results : 0;
  const retained =
    typeof data.retained_tool_results === "number" ? data.retained_tool_results : 0;
  const omitted = typeof data.omitted_tool_results === "number" ? data.omitted_tool_results : 0;
  if (total === 0) return "无工具上下文";
  return `工具 ${total} · 保留 ${retained} · 压缩 ${omitted}`;
}

function statusCounts(items: SubagentListItem[]) {
  return items.reduce<Record<string, number>>((counts, item) => {
    counts[item.status] = (counts[item.status] ?? 0) + 1;
    return counts;
  }, {});
}

export function SubagentsPage() {
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const subagentsQuery = useQuery({
    queryKey: ["subagents", statusFilter],
    queryFn: () => listSubagents({ status: statusFilter, limit: 200 }),
  });
  const allSubagentsQuery = useQuery({
    queryKey: ["subagents", "all-counts"],
    queryFn: () => listSubagents({ limit: 500 }),
  });
  const subagents = subagentsQuery.data?.items ?? [];
  const counts = statusCounts(allSubagentsQuery.data?.items ?? []);
  const selectableIds = subagents
    .filter((subagent) => ["PENDING", "RUNNING"].includes(subagent.status))
    .map((subagent) => subagent.id);
  const selectedSet = new Set(selectedIds);
  const allVisibleSelected =
    selectableIds.length > 0 && selectableIds.every((id) => selectedSet.has(id));
  const bulkCancel = useMutation({
    mutationFn: () => bulkCancelSubagents(selectedIds),
    onSuccess: () => {
      setSelectedIds([]);
      void queryClient.invalidateQueries({ queryKey: ["subagents"] });
    },
  });
  const toggleSelected = (id: string) => {
    setSelectedIds((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  };
  const toggleAllVisible = () => {
    setSelectedIds((current) => {
      if (allVisibleSelected) {
        return current.filter((id) => !selectableIds.includes(id));
      }
      return Array.from(new Set([...current, ...selectableIds]));
    });
  };

  return (
    <ConsoleShell title={text("子代理", "Subagents")}>
      <div className="mx-auto max-w-[1440px] p-6">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 text-lg font-semibold tracking-tight text-slate-900">
              <GitBranch className="h-4 w-4" /> {text("子代理批量运营", "Subagent Operations")}
            </div>
            <div className="mt-1 text-xs text-slate-500">
              {text(
                "按组织查看全部异步子代理，筛选状态并快速跳转到任务、详情和恢复视图。",
                "Inspect all async subagents across the organization, filter by status, and jump to tasks, details, and recovery views.",
              )}
            </div>
          </div>
          <Button>
            <Link to="/observability">{text("查看恢复运营", "Open Recovery Operations")}</Link>
          </Button>
        </div>

        <Card className="mb-4">
          <div className="flex flex-wrap items-center gap-2 p-3">
            <div className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-700">
              <ListFilter className="h-3.5 w-3.5" /> {text("状态筛选", "Status Filter")}
            </div>
            {statusFilters.map((status) => {
              const active = statusFilter === status;
              const count =
                status === "ALL"
                  ? Object.values(counts).reduce((total, value) => total + value, 0)
                  : counts[status] ?? 0;
              return (
                <button
                  key={status}
                  onClick={() => setStatusFilter(status)}
                  className={
                    active
                      ? "rounded-md border border-slate-300 bg-slate-100 px-2.5 py-1 text-xs text-slate-900"
                      : "rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-50"
                  }
                >
                  {status === "ALL" ? text("全部", "All") : statusLabel(status)}
                  <span className="ml-1 font-mono text-[10px] text-slate-400">{count}</span>
                </button>
              );
            })}
          </div>
        </Card>

        <Card className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
            <div>
              <div className="text-xs font-semibold text-slate-900">
                {text("组织子代理列表", "Organization Subagent List")}
              </div>
              <div className="mt-0.5 text-[11px] text-slate-500">
                {text(
                  "展示最近 200 个子代理，技术状态保留原值并显示中文说明。",
                  "Shows the latest 200 subagents with original technical status values and localized labels.",
                )}
              </div>
            </div>
            <span className="text-xs text-slate-500">
              {subagentsQuery.isLoading
                ? text("加载中...", "Loading...")
                : text(`${subagents.length} 个子代理`, `${subagents.length} subagents`)}
            </span>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-3 py-2">
            <div className="inline-flex items-center gap-1.5 text-xs text-slate-500">
              <CheckSquare className="h-3.5 w-3.5" />
              {text(
                `已选择 ${selectedIds.length} 个可取消子代理`,
                `${selectedIds.length} cancellable subagents selected`,
              )}
            </div>
            <Button
              disabled={selectedIds.length === 0 || bulkCancel.isPending}
              onClick={() => bulkCancel.mutate()}
              variant="ghost"
            >
              <span className="inline-flex items-center gap-1.5">
                <XCircle className="h-3.5 w-3.5" />
                {bulkCancel.isPending ? text("取消中", "Cancelling") : text("批量取消", "Bulk Cancel")}
              </span>
            </Button>
          </div>
          <Table>
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <Th>
                  <input
                    aria-label={text("选择当前页", "Select visible")}
                    checked={allVisibleSelected}
                    disabled={selectableIds.length === 0}
                    onChange={toggleAllVisible}
                    type="checkbox"
                  />
                </Th>
                <Th>{text("子代理", "Subagent")}</Th>
                <Th>{text("任务", "Task")}</Th>
                <Th>{text("状态", "Status")}</Th>
                <Th>{text("来源步骤", "Source Step")}</Th>
                <Th>{text("开始时间", "Started")}</Th>
                <Th>{text("完成时间", "Completed")}</Th>
                <Th>{text("上下文压缩", "Context Compression")}</Th>
              </tr>
            </thead>
            <tbody>
              {subagents.map((subagent) => (
                <tr key={subagent.id} className="border-t border-slate-100 hover:bg-slate-50/60">
                  <Td>
                    <input
                      aria-label={text("选择子代理", "Select subagent")}
                      checked={selectedSet.has(subagent.id)}
                      disabled={!["PENDING", "RUNNING"].includes(subagent.status)}
                      onChange={() => toggleSelected(subagent.id)}
                      type="checkbox"
                    />
                  </Td>
                  <Td>
                    <Link
                      to={`/subagents/${subagent.id}`}
                      className="font-mono text-xs text-slate-900 hover:text-slate-950"
                    >
                      {subagent.id.slice(0, 8)}
                    </Link>
                    <div className="mt-0.5 max-w-[220px] truncate text-[11px] text-slate-500">
                      {contextSummary(subagent.context_json)}
                    </div>
                  </Td>
                  <Td>
                    <Link
                      to={`/runs//subagents`}
                      className="text-xs text-slate-900 hover:text-slate-950"
                    >
                      {subagent.task_title}
                    </Link>
                    <div className="mt-0.5 flex items-center gap-1.5 text-[10px] text-slate-500">
                      <span className="font-mono">{subagent.task_id.slice(0, 8)}</span>
                      <span>{statusLabel(subagent.task_status)}</span>
                    </div>
                  </Td>
                  <Td>
                    <Badge tone={statusTone(subagent.status)}>{statusLabel(subagent.status)}</Badge>
                  </Td>
                  <Td className="font-mono text-slate-500">{subagent.step_key ?? "-"}</Td>
                  <Td className="font-mono text-slate-500">
                    {subagent.started_at ? formatShortDate(subagent.started_at) : "-"}
                  </Td>
                  <Td className="font-mono text-slate-500">
                    {subagent.completed_at ? formatShortDate(subagent.completed_at) : "-"}
                  </Td>
                  <Td className="text-[11px] text-slate-500">
                    {resultContextSummary(subagent.context_json)}
                  </Td>
                </tr>
              ))}
              {!subagentsQuery.isLoading && subagents.length === 0 && (
                <tr>
                  <Td colSpan={8} className="py-12 text-center text-slate-500">
                    {text(
                      "暂无符合筛选条件的子代理。",
                      "No subagents match the selected filters.",
                    )}
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
