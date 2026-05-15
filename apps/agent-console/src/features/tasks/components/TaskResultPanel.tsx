import { AlertCircle, Bot } from "lucide-react";
import { Link } from "react-router-dom";

import type { Task, TaskResult } from "../api";
import { Card, CardHeader } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { useI18n } from "../../../lib/i18n";
import { artifactStatusLabel, statusLabel } from "../../../lib/labels";

function numberField(data: Record<string, unknown>, key: string) {
  const value = data[key];
  return typeof value === "number" ? value : 0;
}

function contextCompressionLabel(contextSummary: Record<string, unknown>) {
  const total = numberField(contextSummary, "total_tool_results");
  if (total === 0) return "无工具上下文";
  const retained = numberField(contextSummary, "retained_tool_results");
  const omitted = numberField(contextSummary, "omitted_tool_results");
  return `总计 ${total} · 模型保留 ${retained} · 已压缩 ${omitted}`;
}

export function TaskResultPanel({ task, result }: { task: Task; result?: TaskResult }) {
  const { text } = useI18n();
  const rows = result?.artifacts.map((artifact) => [
    artifact.name,
    artifact.artifact_type,
    artifact.description,
    artifact.status,
  ]) ?? [
    ["plan.json", "json", text("执行计划", "Execution plan"), task.status === "COMPLETED" ? "ready" : "pending"],
    ["events.jsonl", "jsonl", text("事件流导出", "Event stream export"), "ready"],
    ["result.md", "markdown", text("最终任务结果", "Final task result"), task.completed_at ? "ready" : "pending"],
  ];
  return (
    <Card>
      <CardHeader>
        <div className="text-[11px] tracking-widest text-slate-500">{text("任务结果 · 产物", "Task Result · Artifacts")}</div>
        <span className="inline-flex items-center gap-1 text-[11px] text-slate-500">
          <AlertCircle className="h-3 w-3" /> {statusLabel(result?.status ?? task.status)}
        </span>
      </CardHeader>
      {result?.summary && <div className="border-b border-slate-100 p-3 text-xs">{result.summary}</div>}
      {result?.subagent_results && result.subagent_results.length > 0 && (
        <div className="border-b border-slate-100 p-3">
          <div className="mb-2 flex items-center gap-1 text-xs font-semibold text-slate-900">
            <Bot className="h-3.5 w-3.5" /> {text("异步子代理结果", "Async Subagent Results")}
          </div>
          <Table>
            <thead className="bg-slate-50/40 text-slate-500">
              <tr>
                <Th>{text("子代理", "Subagent")}</Th>
                <Th>{text("来源步骤", "Source Step")}</Th>
                <Th>{text("状态", "Status")}</Th>
                <Th>{text("摘要", "Summary")}</Th>
                <Th>{text("上下文压缩", "Context Compression")}</Th>
              </tr>
            </thead>
            <tbody>
              {result.subagent_results.map((subagent) => (
                <tr key={subagent.id} className="border-t border-slate-100">
                  <Td>
                    <Link
                      to={`/subagents/${subagent.id}`}
                      className="font-mono text-slate-800 hover:text-slate-950"
                    >
                      {subagent.id.slice(0, 8)}
                    </Link>
                  </Td>
                  <Td className="font-mono text-slate-600">{subagent.step_key ?? "-"}</Td>
                  <Td className="text-slate-600">
                    {statusLabel(subagent.status)}
                    {subagent.tool_results.length > 0 && (
                      <span className="ml-1 text-[10px] text-slate-400">
                        {text(`工具 ${subagent.tool_results.length}`, `Tools ${subagent.tool_results.length}`)}
                      </span>
                    )}
                    {subagent.artifacts.length > 0 && (
                      <span className="ml-1 text-[10px] text-slate-400">
                        {text(`产物 ${subagent.artifacts.length}`, `Artifacts ${subagent.artifacts.length}`)}
                      </span>
                    )}
                  </Td>
                  <Td className="max-w-[360px] truncate text-slate-600">
                    {subagent.summary ?? text("尚未写入结果", "No result written yet")}
                  </Td>
                  <Td className="text-[11px] text-slate-500">
                    {contextCompressionLabel(subagent.context_summary)}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </div>
      )}
      <Table>
        <thead className="bg-slate-50/40 text-slate-500">
          <tr>
            <Th>{text("名称", "Name")}</Th>
            <Th>{text("类型", "Type")}</Th>
            <Th>{text("描述", "Description")}</Th>
            <Th>{text("状态", "Status")}</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row[0]} className="border-t border-slate-100">
              <Td className="font-mono text-slate-800">{row[0]}</Td>
              <Td className="text-slate-600">{row[1]}</Td>
              <Td className="text-slate-600">{row[2]}</Td>
              <Td className="font-mono text-slate-500">{artifactStatusLabel(row[3])}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  );
}
