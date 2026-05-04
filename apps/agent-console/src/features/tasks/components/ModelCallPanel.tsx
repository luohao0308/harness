import { Brain } from "lucide-react";

import { Card, CardHeader } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { statusLabel } from "../../../lib/labels";
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
          </tr>
        </thead>
        <tbody>
          {modelCalls.slice(0, 3).map((call) => (
            <tr key={call.id} className="border-t border-slate-100">
              <Td>模型</Td>
              <Td className="font-mono">{call.model_name}</Td>
              <Td>{statusLabel(call.status)}</Td>
              <Td>{call.duration_ms}ms</Td>
            </tr>
          ))}
          {toolCalls.slice(0, 4).map((call) => (
            <tr key={call.id} className="border-t border-slate-100">
              <Td>工具</Td>
              <Td className="font-mono">{call.tool_name}</Td>
              <Td>{statusLabel(call.status)}</Td>
              <Td>{call.duration_ms}ms</Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  );
}
