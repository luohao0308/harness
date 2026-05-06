import { AlertCircle, Bot } from "lucide-react";

import type { Task, TaskResult } from "../api";
import { Card, CardHeader } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { artifactStatusLabel, statusLabel } from "../../../lib/labels";

export function TaskResultPanel({ task, result }: { task: Task; result?: TaskResult }) {
  const rows = result?.artifacts.map((artifact) => [
    artifact.name,
    artifact.artifact_type,
    artifact.description,
    artifact.status,
  ]) ?? [
    ["plan.json", "json", "执行计划", task.status === "COMPLETED" ? "ready" : "pending"],
    ["events.jsonl", "jsonl", "事件流导出", "ready"],
    ["result.md", "markdown", "最终任务结果", task.completed_at ? "ready" : "pending"],
  ];
  return (
    <Card>
      <CardHeader>
        <div className="text-[11px] tracking-widest text-slate-500">任务结果 · 产物</div>
        <span className="inline-flex items-center gap-1 text-[11px] text-slate-500">
          <AlertCircle className="h-3 w-3" /> {statusLabel(result?.status ?? task.status)}
        </span>
      </CardHeader>
      {result?.summary && <div className="border-b border-slate-100 p-3 text-xs">{result.summary}</div>}
      {result?.subagent_results && result.subagent_results.length > 0 && (
        <div className="border-b border-slate-100 p-3">
          <div className="mb-2 flex items-center gap-1 text-xs font-semibold text-slate-900">
            <Bot className="h-3.5 w-3.5" /> 异步子 Agent 结果
          </div>
          <Table>
            <thead className="bg-slate-50/40 text-slate-500">
              <tr>
                <Th>子 Agent</Th>
                <Th>来源步骤</Th>
                <Th>状态</Th>
                <Th>摘要</Th>
              </tr>
            </thead>
            <tbody>
              {result.subagent_results.map((subagent) => (
                <tr key={subagent.id} className="border-t border-slate-100">
                  <Td className="font-mono text-slate-800">{subagent.id.slice(0, 8)}</Td>
                  <Td className="font-mono text-slate-600">{subagent.step_key ?? "-"}</Td>
                  <Td className="text-slate-600">
                    {statusLabel(subagent.status)}
                    {subagent.tool_results.length > 0 && (
                      <span className="ml-1 text-[10px] text-slate-400">
                        工具 {subagent.tool_results.length}
                      </span>
                    )}
                    {subagent.artifacts.length > 0 && (
                      <span className="ml-1 text-[10px] text-slate-400">
                        产物 {subagent.artifacts.length}
                      </span>
                    )}
                  </Td>
                  <Td className="max-w-[360px] truncate text-slate-600">
                    {subagent.summary ?? "尚未写入结果"}
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
            <Th>名称</Th>
            <Th>类型</Th>
            <Th>描述</Th>
            <Th>状态</Th>
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
