import type { AgentChatStreamEvent } from "../tasks/api";

export type WorkspaceStreamToolCall = {
  tool_call_id: string;
  tool_name: string;
  source: string | null;
  input_json: Record<string, unknown>;
  output_json?: Record<string, unknown>;
  output_summary?: string | null;
  status: string;
  duration_ms?: number | null;
  trace_id?: string | null;
  approval_id?: string | null;
};

export function mergeToolCallEvent(
  currentToolCalls: Array<Record<string, unknown>>,
  event: Extract<AgentChatStreamEvent, { type: "tool_call_requested" | "tool_call_result" }>,
): WorkspaceStreamToolCall[] {
  const toolCalls = currentToolCalls.map(normalizeToolCall);
  if (event.type === "tool_call_requested") {
    const requested = normalizeToolCall({
      tool_call_id: event.tool_call_id,
      tool_name: event.tool_name,
      source: event.source,
      input_json: event.input_json,
      status: event.status,
      approval_id: event.approval_id,
    });
    return upsertToolCall(toolCalls, requested);
  }

  const result = normalizeToolCall({
    tool_call_id: event.tool_call_id,
    tool_name: event.tool_name,
    source: null,
    input_json: {},
    output_json: event.output_json,
    output_summary: event.output_summary,
    status: event.status,
    duration_ms: event.duration_ms,
    trace_id: event.trace_id,
    approval_id: event.approval_id,
  });
  return upsertToolCall(toolCalls, result);
}

export function formatUsageCost(costUsd: string | null | undefined, costUnavailable?: boolean) {
  if (costUnavailable || costUsd == null || costUsd === "") return "Unavailable";
  return `$${costUsd}`;
}

function upsertToolCall(toolCalls: WorkspaceStreamToolCall[], next: WorkspaceStreamToolCall) {
  const index = toolCalls.findIndex((call) => call.tool_call_id === next.tool_call_id);
  if (index === -1) return [...toolCalls, next];
  return toolCalls.map((call, currentIndex) =>
    currentIndex === index
      ? {
          ...call,
          ...next,
          input_json: Object.keys(next.input_json).length ? next.input_json : call.input_json,
          source: next.source ?? call.source,
        }
      : call,
  );
}

function normalizeToolCall(call: Record<string, unknown>): WorkspaceStreamToolCall {
  const toolName = String(call.tool_name ?? "");
  return {
    tool_call_id: String(call.tool_call_id ?? call.id ?? `${toolName || "tool"}-orphan`),
    tool_name: toolName,
    source: typeof call.source === "string" ? call.source : null,
    input_json: asRecord(call.input_json),
    output_json: call.output_json === undefined ? undefined : asRecord(call.output_json),
    output_summary: typeof call.output_summary === "string" ? call.output_summary : null,
    status: String(call.status ?? "unknown"),
    duration_ms: typeof call.duration_ms === "number" ? call.duration_ms : null,
    trace_id: typeof call.trace_id === "string" ? call.trace_id : null,
    approval_id: typeof call.approval_id === "string" ? call.approval_id : null,
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
