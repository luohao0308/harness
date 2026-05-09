import { Brain } from "lucide-react";
import { Link } from "react-router-dom";

import { Card, CardHeader } from "../../../components/ui/card";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Table, Td, Th } from "../../../components/ui/table";
import { useI18n } from "../../../lib/i18n";
import { statusLabel, timeoutCategoryLabel, toolOutputKindLabel } from "../../../lib/labels";
import type { ModelCall, ToolCall, ToolCallFilters } from "../../tasks/api";

export function ModelCallPanel({
  modelCalls,
  toolCalls,
  toolCallFilters,
  onToolCallFiltersChange,
}: {
  modelCalls: ModelCall[];
  toolCalls: ToolCall[];
  toolCallFilters: ToolCallFilters;
  onToolCallFiltersChange: (filters: ToolCallFilters) => void;
}) {
  const { text } = useI18n();
  const updateFilter = (key: keyof ToolCallFilters, value: string) => {
    onToolCallFiltersChange({
      ...toolCallFilters,
      [key]: value.trim() ? value : undefined,
      limit: 100,
    });
  };
  const clearFilters = () => onToolCallFiltersChange({ limit: 100 });
  return (
    <Card>
      <CardHeader>
        <div className="inline-flex items-center gap-1.5 text-[11px] tracking-widest text-slate-500">
          <Brain className="h-3 w-3" /> {text("模型与工具审计", "Model & Tool Audit")}
        </div>
        <span className="font-mono text-[10px] text-slate-400">
          {modelCalls.length} / {toolCalls.length}
        </span>
      </CardHeader>
      <div className="grid grid-cols-[1fr_1fr_1fr_1fr_auto] gap-2 border-t border-slate-100 p-3">
        <Input
          aria-label={text("工具名称", "Tool name")}
          className="h-8 text-xs"
          placeholder={text("工具名称", "Tool name")}
          value={toolCallFilters.tool_name ?? ""}
          onChange={(event) => updateFilter("tool_name", event.target.value)}
        />
        <Input
          aria-label={text("状态", "Status")}
          className="h-8 text-xs"
          placeholder={text("状态，例如 SUCCESS", "Status, e.g. SUCCESS")}
          value={toolCallFilters.status ?? ""}
          onChange={(event) => updateFilter("status", event.target.value)}
        />
        <Input
          aria-label={text("风险等级", "Risk level")}
          className="h-8 text-xs"
          placeholder={text("风险，例如 low", "Risk, e.g. low")}
          value={toolCallFilters.risk_level ?? ""}
          onChange={(event) => updateFilter("risk_level", event.target.value)}
        />
        <Input
          aria-label={text("Trace ID", "Trace ID")}
          className="h-8 text-xs"
          placeholder="Trace ID"
          value={toolCallFilters.trace_id ?? ""}
          onChange={(event) => updateFilter("trace_id", event.target.value)}
        />
        <Button onClick={clearFilters} variant="ghost">
          {text("清空", "Clear")}
        </Button>
      </div>
      <Table>
        <thead className="bg-slate-50 text-slate-500">
          <tr>
            <Th>{text("类型", "Type")}</Th>
            <Th>{text("名称", "Name")}</Th>
            <Th>{text("状态", "Status")}</Th>
            <Th>{text("耗时", "Latency")}</Th>
            <Th>{text("详情", "Details")}</Th>
          </tr>
        </thead>
        <tbody>
          {modelCalls.slice(0, 3).map((call) => (
            <tr key={call.id} className="border-t border-slate-100">
              <Td>{text("模型", "Model")}</Td>
              <Td>
                <div className="font-mono">{call.model_name}</div>
                <div className="mt-0.5 text-[10px] text-slate-400">{call.model_provider}</div>
              </Td>
              <Td>{statusLabel(call.status)}</Td>
              <Td>{call.duration_ms}ms</Td>
              <Td className="text-slate-500">
                <div>
                  {text("Token", "Tokens")} {call.prompt_tokens + call.completion_tokens}
                </div>
                <div className="mt-0.5 max-w-[240px] truncate text-[10px] text-slate-400">
                  {modelCallDetail(call)}
                </div>
                {call.trace_id ? (
                  <Link
                    to={`/observability?trace_id=${encodeURIComponent(call.trace_id)}`}
                    className="mt-0.5 block text-[10px] text-slate-500 hover:text-slate-900"
                  >
                    Trace {call.trace_id.slice(0, 8)}
                  </Link>
                ) : null}
              </Td>
            </tr>
          ))}
          {toolCalls.slice(0, 4).map((call) => (
            <tr key={call.id} className="border-t border-slate-100">
              <Td>{text("工具", "Tool")}</Td>
              <Td className="font-mono">{call.tool_name}</Td>
              <Td>{statusLabel(call.status)}</Td>
              <Td>{call.duration_ms}ms</Td>
              <Td className="max-w-[240px]">
                <div className="truncate text-slate-600">
                  {toolOutputKindLabel(call.output_kind)} · {call.output_summary}
                </div>
                <div className="mt-0.5 flex flex-wrap gap-1 text-[10px] text-slate-400">
                  <span>{call.requires_sandbox ? text("沙箱执行", "Sandbox run") : text("本地执行", "Local run")}</span>
                  <span>{text("风险", "Risk")} {call.risk_level}</span>
                  {call.timeout_category && <span>{timeoutCategoryLabel(call.timeout_category)}</span>}
                  {call.task_id && (
                    <Link to={`/runs//events`} className="hover:text-slate-900">
                      {text("事件深链", "Events")}
                    </Link>
                  )}
                  {call.trace_id && (
                    <Link
                      to={`/observability?trace_id=${encodeURIComponent(call.trace_id)}`}
                      className="hover:text-slate-900"
                    >
                      Trace {call.trace_id.slice(0, 8)}
                    </Link>
                  )}
                </div>
              </Td>
            </tr>
          ))}
          {modelCalls.length === 0 && toolCalls.length === 0 && (
            <tr className="border-t border-slate-100">
              <Td colSpan={5} className="py-8 text-center text-slate-500">
                {text("暂无符合条件的审计记录", "No matching audit records")}
              </Td>
            </tr>
          )}
        </tbody>
      </Table>
    </Card>
  );
}

function modelCallDetail(call: ModelCall) {
  if (call.error_message) return call.error_message;
  const contentPreview = call.response_json.content_preview;
  if (typeof contentPreview === "string" && contentPreview.length > 0) return contentPreview;
  const estimatedTokens = call.request_json.estimated_prompt_tokens;
  if (typeof estimatedTokens === "number") return `estimated_prompt_tokens=${estimatedTokens}`;
  return "无模型响应详情";
}
