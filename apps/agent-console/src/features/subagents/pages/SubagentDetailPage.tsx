import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Ban,
  Bot,
  Boxes,
  ChevronRight,
  FileText,
  GitBranch,
  ListChecks,
  Network,
  Route,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { feedbackErrorMessage, notifyFeedback } from "../../../components/ui/feedback-toast";
import { Table, Td, Th } from "../../../components/ui/table";
import { TermHint } from "../../../components/ui/term";
import { useI18n } from "../../../lib/i18n";
import { artifactStatusLabel, statusLabel } from "../../../lib/labels";
import { formatShortDate } from "../../../lib/utils";
import { cancelSubagent, getSubagent, getTaskResult, type TaskResult } from "../../tasks/api";

type SubagentResult = TaskResult["subagent_results"][number];

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function arrayValue(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object" && !Array.isArray(item)))
    : [];
}

function stringValue(value: unknown) {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function numberValue(value: unknown) {
  return typeof value === "number" ? value : 0;
}

function subagentTitle(context: Record<string, unknown>) {
  return (
    stringValue(context.label) ??
    stringValue(context.goal) ??
    stringValue(context.description) ??
    "子代理执行详情"
  );
}

function contextCompressionLabel(contextSummary: Record<string, unknown>) {
  const total = numberValue(contextSummary.total_tool_results);
  if (total === 0) return "无工具上下文";
  return `总计 ${total} · 保留 ${numberValue(contextSummary.retained_tool_results)} · 压缩 ${numberValue(contextSummary.omitted_tool_results)}`;
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-[360px] overflow-auto rounded-md bg-slate-950 p-3 text-[11px] leading-relaxed text-slate-100">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function SubagentDetailPage() {
  const { text } = useI18n();
  const { subagentId } = useParams();
  const queryClient = useQueryClient();

  const subagentQuery = useQuery({
    queryKey: ["subagent-detail", subagentId],
    queryFn: () => getSubagent(subagentId!),
    enabled: Boolean(subagentId),
  });
  const taskId = subagentQuery.data?.task_id;
  const resultQuery = useQuery({
    queryKey: ["task-result", taskId],
    queryFn: () => getTaskResult(taskId!),
    enabled: Boolean(taskId),
  });
  const cancelMutation = useMutation({
    mutationFn: () => cancelSubagent(subagentId!),
    onSuccess: async (subagent) => {
      notifyFeedback({
        tone: "warning",
        title: text("子代理已取消", "Subagent cancelled"),
        description: text(`子代理 ${subagent.id.slice(0, 8)} 已收到取消请求。`, `Subagent ${subagent.id.slice(0, 8)} has been cancelled.`),
      });
      await queryClient.invalidateQueries({ queryKey: ["subagent-detail", subagent.id] });
      await queryClient.invalidateQueries({ queryKey: ["task-subagents", subagent.task_id] });
      await queryClient.invalidateQueries({ queryKey: ["task-result", subagent.task_id] });
      await queryClient.invalidateQueries({ queryKey: ["task-events", subagent.task_id] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("子代理取消失败", "Subagent cancel failed"),
        description: feedbackErrorMessage(error, text("请检查子代理状态或稍后重试。", "Check the subagent state and retry.")),
      });
    },
  });

  const subagent = subagentQuery.data;
  const context = subagent?.context_json ?? {};
  const result = objectValue(context.result);
  const assignment = useMemo(() => {
    const assignmentValue = objectValue(context.assignment);
    return Object.keys(assignmentValue).length > 0 ? assignmentValue : context;
  }, [context]);
  const taskResult = resultQuery.data?.subagent_results.find((item) => item.id === subagent?.id);
  const toolResults = taskResult?.tool_results ?? arrayValue(result.tool_results);
  const reactTrace = taskResult?.react_trace ?? arrayValue(result.react_trace);
  const contextSummary = taskResult?.context_summary ?? objectValue(result.context_summary);
  const artifacts: SubagentResult["artifacts"] = taskResult?.artifacts ?? [];
  const canCancel = subagent ? ["PENDING", "RUNNING"].includes(subagent.status) : false;

  if (!subagent) {
    return (
      <ConsoleShell title={text("子代理 / 详情", "Subagent / Detail")}>
        <div className="p-6 text-sm text-slate-500">
          {subagentQuery.isError
            ? text("子代理加载失败，请检查 ID 或权限。", "Failed to load subagent. Check the ID or permission.")
            : text("子代理加载中...", "Loading subagent...")}
        </div>
      </ConsoleShell>
    );
  }

  return (
    <ConsoleShell title={`${text("子代理", "Subagent")} / ${subagent.id.slice(0, 8)}`}>
      <div className="border-b border-slate-200 bg-white px-6 py-5">
        <div className="mb-2 flex items-center gap-2 text-xs text-slate-500">
          <Link to="/subagents">{text("子代理", "Subagents")}</Link>
          <ChevronRight className="h-3 w-3" />
          <span className="font-mono">{subagent.id.slice(0, 8)}</span>
        </div>
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="truncate text-xl font-semibold tracking-tight text-slate-900">
                {subagentTitle(context)}
              </h1>
              <Badge tone={statusTone(subagent.status)}>{statusLabel(subagent.status)}</Badge>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-5 text-xs text-slate-500">
              <span>
                {text("任务", "Task")}{" "}
                <Link
                  to={`/runs/${subagent.task_id}`}
                  className="font-mono text-slate-800 hover:text-slate-950"
                >
                  {subagent.task_id.slice(0, 8)}
                </Link>
              </span>
              <span>
                {text("来源步骤", "Source step")}{" "}
                <span className="font-mono text-slate-800">{stringValue(context.step_key) ?? "-"}</span>
              </span>
              <span>
                {text("类型", "Type")} <span className="font-mono text-slate-800">{subagent.agent_type}</span>
              </span>
              <span>
                {text("超时保护", "Timeout guard")}{" "}
                <span className="font-mono text-slate-800">
                  {subagent.timeout_at ? formatShortDate(subagent.timeout_at) : "-"}
                </span>
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button>
              <Link to={`/runs/${subagent.task_id}/subagents`}>
                <ListChecks className="h-3.5 w-3.5" /> {text("任务子代理", "Task Subagents")}
              </Link>
            </Button>
            <Button
              disabled={!canCancel || cancelMutation.isPending}
              onClick={() => cancelMutation.mutate()}
              variant="danger"
            >
              <Ban className="h-3.5 w-3.5" /> {text("取消子代理", "Cancel Subagent")}
            </Button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4 p-4">
        <section className="col-span-4 space-y-4">
          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-1.5 text-[11px] tracking-widest text-slate-500">
                <Bot className="h-3 w-3" /> {text("运行状态", "Run Status")}
              </div>
              <span className="font-mono text-[10px] text-slate-400">{subagent.id.slice(0, 13)}</span>
            </CardHeader>
            <div className="grid grid-cols-2 gap-px bg-slate-100 text-xs">
              {[
                [text("开始时间", "Started"), subagent.started_at ? formatShortDate(subagent.started_at) : "-"],
                [text("完成时间", "Completed"), subagent.completed_at ? formatShortDate(subagent.completed_at) : "-"],
                [text("工具结果", "Tool results"), String(toolResults.length)],
                [text("产物", "Artifacts"), String(artifacts.length)],
              ].map(([label, value]) => (
                <div key={label} className="bg-white p-3">
                  <div className="text-[11px] text-slate-500">{label}</div>
                  <div className="mt-1 font-mono text-slate-900">{value}</div>
                </div>
              ))}
            </div>
          </Card>

          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-1.5 text-[11px] tracking-widest text-slate-500">
                <Route className="h-3 w-3" /> {text("上下文压缩", "Context Compression")}
              </div>
            </CardHeader>
            <div className="p-3 text-xs text-slate-600">
              {contextCompressionLabel(contextSummary)}
              <div className="mt-3">
                <JsonBlock value={contextSummary} />
              </div>
            </div>
          </Card>
        </section>

        <section className="col-span-8 space-y-4">
          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-1.5 text-[11px] tracking-widest text-slate-500">
                <GitBranch className="h-3 w-3" /> {text("任务说明", "Assignment")}
              </div>
            </CardHeader>
            <div className="p-3">
              <JsonBlock value={assignment} />
            </div>
          </Card>

          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-1.5 text-[11px] tracking-widest text-slate-500">
                <FileText className="h-3 w-3" /> {text("结果摘要与产物", "Result Summary & Artifacts")}
              </div>
              <span className="text-[11px] text-slate-500">
                {taskResult ? text("来自任务结果聚合", "From task result aggregation") : text("等待结果聚合", "Waiting for result aggregation")}
              </span>
            </CardHeader>
            <div className="border-b border-slate-100 p-3 text-xs text-slate-600">
              {taskResult?.summary ??
                stringValue(result.summary) ??
                text("子代理尚未写入结果摘要。", "The subagent has not written a result summary yet.")}
            </div>
            <Table>
              <thead className="bg-slate-50/40 text-slate-500">
                <tr>
                  <Th>{text("名称", "Name")}</Th>
                  <Th>{text("类型", "Type")}</Th>
                  <Th>{text("来源工具", "Source Tool")}</Th>
                  <Th>{text("描述", "Description")}</Th>
                  <Th>{text("状态", "Status")}</Th>
                  <Th>{text("预览", "Preview")}</Th>
                </tr>
              </thead>
              <tbody>
                {artifacts.map((artifact) => (
                  <tr key={`${artifact.source_tool}-${artifact.name}`} className="border-t border-slate-100">
                    <Td className="font-mono text-slate-800">{artifact.name}</Td>
                    <Td className="text-slate-600">{artifact.artifact_type}</Td>
                    <Td className="font-mono text-slate-600">{artifact.source_tool}</Td>
                    <Td className="text-slate-600">{artifact.description}</Td>
                    <Td className="text-slate-500">{artifactStatusLabel(artifact.status)}</Td>
                    <Td className="max-w-[260px] truncate text-slate-500">{artifact.preview ?? "-"}</Td>
                  </tr>
                ))}
                {artifacts.length === 0 && (
                  <tr>
                    <Td colSpan={6} className="py-8 text-center text-slate-500">
                      {text("暂无可预览产物。工具成功返回后会在这里聚合展示。", "No previewable artifacts yet. Successful tool outputs will appear here.")}
                    </Td>
                  </tr>
                )}
              </tbody>
            </Table>
          </Card>

          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-1.5 text-[11px] tracking-widest text-slate-500">
                <Boxes className="h-3 w-3" /> {text("工具执行结果", "Tool Execution Results")}
              </div>
              <span className="text-[11px] text-slate-500">
                {text(`${toolResults.length} 条`, `${toolResults.length} items`)}
              </span>
            </CardHeader>
            <Table>
              <thead className="bg-slate-50/40 text-slate-500">
                <tr>
                  <Th>{text("工具", "Tool")}</Th>
                  <Th>{text("状态", "Status")}</Th>
                  <Th>{text("策略", "Policy")}</Th>
                  <Th>{text("耗时", "Latency")}</Th>
                  <Th>{text("错误", "Error")}</Th>
                </tr>
              </thead>
              <tbody>
                {toolResults.map((tool, index) => (
                  <tr key={`${String(tool.tool_call_id ?? index)}-${index}`} className="border-t border-slate-100">
                    <Td className="font-mono text-slate-800">{String(tool.tool_name ?? "-")}</Td>
                    <Td className="text-slate-600">{statusLabel(String(tool.status ?? "-"))}</Td>
                    <Td className="text-slate-600">
                      {tool.allowed === false ? text("已拒绝", "Denied") : text("已允许", "Allowed")}
                    </Td>
                    <Td className="font-mono text-slate-500">{String(tool.duration_ms ?? 0)}ms</Td>
                    <Td className="max-w-[260px] truncate text-slate-500">
                      {stringValue(tool.error_message) ?? "-"}
                    </Td>
                  </tr>
                ))}
                {toolResults.length === 0 && (
                  <tr>
                    <Td colSpan={5} className="py-8 text-center text-slate-500">
                      {text("暂无工具执行结果。", "No tool execution results yet.")}
                    </Td>
                  </tr>
                )}
              </tbody>
            </Table>
          </Card>

          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-1.5 text-[11px] tracking-widest text-slate-500">
                <Network className="h-3 w-3" />
                <TermHint description="推理与动作交替轨迹">推理行动</TermHint>
                {text("轨迹", "Trace")}
              </div>
              <span className="text-[11px] text-slate-500">
                {text(`${reactTrace.length} 轮`, `${reactTrace.length} rounds`)}
              </span>
            </CardHeader>
            <div className="p-3">
              {reactTrace.length > 0 ? (
                <JsonBlock value={reactTrace} />
              ) : (
                <div className="py-8 text-center text-xs text-slate-500">
                  {text("暂无多轮工具规划轨迹。", "No multi-round tool planning trace yet.")}
                </div>
              )}
            </div>
          </Card>
        </section>
      </div>
    </ConsoleShell>
  );
}
