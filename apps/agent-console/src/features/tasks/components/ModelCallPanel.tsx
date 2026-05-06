import { Brain } from "lucide-react";

import { Card, CardHeader } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { statusLabel, timeoutCategoryLabel, toolOutputKindLabel } from "../../../lib/labels";
import type { ModelCall, ToolCall } from "../api";

export function ModelCallPanel({
  modelCalls,
  toolCalls,
}: {
  modelCalls: ModelCall[];
  toolCalls: ToolCall[];
}) {
  return (
    <Card>
      <CardHeader>
        <div className="inline-flex items-center gap-1.5 text-[11px] tracking-widest text-slate-500">
          <Brain className="h-3 w-3" /> 模型与工具审计
        </div>
        <span className="font-mono text-[10px] text-slate-400">
          {modelCalls.length} / {toolCalls.length}
        </span>
      </CardHeader>
      <Table>
        <thead className="bg-slate-50 text-slate-500">
          <tr>
            <Th>类型</Th>
            <Th>名称</Th>
            <Th>状态</Th>
            <Th>耗时</Th>
            <Th>详情</Th>
          </tr>
        </thead>
        <tbody>
          {modelCalls.slice(0, 3).map((call) => (
            <tr key={call.id} className="border-t border-slate-100">
              <Td>模型</Td>
              <Td className="font-mono">{call.model_name}</Td>
              <Td>{statusLabel(call.status)}</Td>
              <Td>{call.duration_ms}ms</Td>
              <Td className="text-slate-500">
                token {call.prompt_tokens + call.completion_tokens}
              </Td>
            </tr>
          ))}
          {toolCalls.slice(0, 4).map((call) => (
            <tr key={call.id} className="border-t border-slate-100">
              <Td>工具</Td>
              <Td className="font-mono">{call.tool_name}</Td>
              <Td>{statusLabel(call.status)}</Td>
              <Td>{call.duration_ms}ms</Td>
              <Td className="max-w-[240px]">
                <div className="truncate text-slate-600">
                  {toolOutputKindLabel(call.output_kind)} · {call.output_summary}
                </div>
                <div className="mt-0.5 flex flex-wrap gap-1 text-[10px] text-slate-400">
                  <span>{call.requires_sandbox ? "沙箱执行" : "本地执行"}</span>
                  <span>风险 {call.risk_level}</span>
                  {call.timeout_category && <span>{timeoutCategoryLabel(call.timeout_category)}</span>}
                </div>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  );
}
