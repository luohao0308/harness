/**
 * ChatMessageBubble — chat bubble for one conversation node (v2).
 *
 * Satisfies:
 *   - Req 1.4, 1.5: user right-aligned, assistant/tool left-aligned with
 *     `max-w-[75%]` constraint on the inner column.
 *   - Req 1.6: renders markdown via the zero-dependency `renderMarkdown`.
 *   - Req 2.8: surfaces `metadata.streaming_diagnostic === "possible_buffering"`
 *     as a low-emphasis bilingual amber hint beneath the bubble.
 *   - Req 3.2, 3.4, 3.7: collapsible `<think>` blocks, thinking placeholder,
 *     blinking cursor while streaming.
 *   - Req 4.1, 4.2, 4.9: hover/focus `MessageActions` row (Copy / Edit /
 *     Regenerate); `editingNodeId === node.id` swaps the bubble contents for
 *     {@link MessageEditForm}.
 *   - Req 5.1 / 5.5 / 10.1: Copy / Edit / Regenerate wire through to
 *     parent-provided callbacks; parent strips `<think>` blocks via
 *     {@link stripThinkBlocks} before writing to the clipboard.
 *   - Req 7.7: tool_call chips open the Inspector "runtime" section; artifact
 *     chips open the "artifacts" section.
 *   - Req 8.1 / 8.3 / 8.6 / 8.7 (Property 9): user bubble uses
 *     `bg-white border border-slate-200 text-slate-900`; assistant bubble
 *     keeps the v1 `bg-slate-50 text-slate-800 border border-slate-200`.
 *   - Req 9.5 / 14.3: every icon-only control carries an `aria-label`.
 *   - Req 11.1 / 11.2 / 11.3: relative timestamp below every bubble with
 *     `<time dateTime title>` carrying the ISO 8601 reference.
 *
 * Pure presentational component: no `useState` / `useEffect` / `useRef`, and
 * it does not import the workspace store. All data and side-effect handlers
 * arrive via props; owner is `ChatMessageList` (which is owned by
 * `ChatSurface`).
 */

import type { JSX } from "react";
import { Bot, FileCode2, Pin, Wrench } from "lucide-react";

import { Badge, statusTone } from "../../../components/ui/badge";
import { useI18n } from "../../../lib/i18n";
import { cn } from "../../../lib/utils";
import { stripThinkBlocks } from "../lib/copyText";
import { renderMarkdown } from "../lib/markdown";
import { formatLocalIso, formatRelativeTime } from "../lib/relativeTime";
import type { InspectorSection } from "../lib/types";
import type { ConversationArtifact, ConversationNode } from "../../../stores/workspaceStore";
import { MessageActions } from "./MessageActions";
import { MessageEditForm } from "./MessageEditForm";
import { StreamingCaret } from "./StreamingCaret";

export type ChatMessageBubbleProps = {
  /** Conversation node. Must have `role ∈ {user, assistant, tool}`; error
   * nodes render through {@link ChatErrorBubble} instead. */
  node: ConversationNode;
  /** Invoked when the user clicks a tool-call chip or artifact row. */
  onOpenInspector: (section: InspectorSection, nodeId: string) => void;

  // --- v2 additive: edit state (owned by ChatSurface, Req 4.2 / 4.9) ---
  /** `null` → no bubble is in edit mode; otherwise the node id being edited. */
  editingNodeId: string | null;
  /** Called when the user clicks Edit on a user bubble. */
  onStartEdit: (nodeId: string) => void;
  /** Called when the user cancels an edit (Esc or explicit Cancel). */
  onCancelEdit: () => void;
  /** Called when the user saves an edit — parent creates the new branch. */
  onSaveEdit: (nodeId: string, newContent: string) => void;

  // --- v2 additive: copy / regenerate wiring (Req 5.1 / 10.1) ---
  /**
   * True iff this bubble is the last assistant on `Active_Path` and eligible
   * for Regenerate (`state ∈ {done, error, paused}`, `activeStream === null`).
   */
  canRegenerate: boolean;
  /** True while `activeStream !== null`; suppresses Edit / Regenerate. */
  isStreaming: boolean;
  /** Parent wraps the concrete `copyText(stripThinkBlocks(...))` pipeline. */
  onCopy: (nodeId: string) => Promise<boolean>;
  /** Parent calls `stream.driveBranch(...)` to re-run the previous user turn. */
  onRegenerate: (nodeId: string) => void;

  // --- Phase 4 additive: pin toggle (Req 15.1, 15.2) ---
  /** Whether this node is currently pinned. */
  isPinned?: boolean;
  /** Called when the user clicks the pin/unpin button. */
  onTogglePin?: (nodeId: string) => void;
};

export function ChatMessageBubble({
  node,
  onOpenInspector,
  editingNodeId,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  canRegenerate,
  isStreaming,
  onCopy,
  onRegenerate,
  isPinned = false,
  onTogglePin,
}: ChatMessageBubbleProps): JSX.Element {
  const { text, isChinese } = useI18n();
  const isUser = node.role === "user";
  const thinkBlocks = extractThinkBlocks(node.content);
  const visibleContent = stripThinkBlocks(node.content);
  const isNodeStreaming = node.state === "streaming";
  const showPlaceholder = isNodeStreaming && visibleContent.length === 0;
  const isEditing = editingNodeId === node.id && isUser;

  const bubbleClass = cn(
    "rounded-2xl px-4 py-3 text-sm leading-6 shadow-sm",
    isUser
      ? "bg-white border border-slate-200 text-slate-900"
      : "bg-slate-50 text-slate-800 border border-slate-200",
    isPinned && "ring-2 ring-amber-300",
  );

  const statusAttrs = isNodeStreaming
    ? ({ role: "status", "aria-live": "polite" } as const)
    : {};

  const createdMs = parseCreatedAtMs(node.created_at);
  const hasBufferingHint =
    node.metadata.streaming_diagnostic === "possible_buffering";

  return (
    <div
      className={cn(
        "group flex gap-3",
        isUser ? "justify-end" : "justify-start",
      )}
    >
      {!isUser && (
        <div
          aria-hidden="true"
          className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-950 text-white"
        >
          <Bot className="h-4 w-4" />
        </div>
      )}
      <div className={cn("min-w-0 max-w-[75%]", isUser && "order-first")}>
        {isEditing ? (
          <MessageEditForm
            initialContent={node.content}
            onSave={(newContent) => onSaveEdit(node.id, newContent)}
            onCancel={onCancelEdit}
          />
        ) : (
          <div {...statusAttrs} className={bubbleClass}>
            {thinkBlocks.length > 0 && (
              <div className="mb-2 space-y-1">
                {thinkBlocks.map((block, index) => (
                  <details
                    key={`${node.id}-think-${index}`}
                    className="rounded-md border border-slate-200 bg-white p-2 text-xs text-slate-500"
                  >
                    <summary className="cursor-pointer font-medium text-slate-700">
                      {text("思考过程 / Thinking", "Thinking trace")}
                    </summary>
                    <div className="mt-2 whitespace-pre-wrap">{block}</div>
                  </details>
                ))}
              </div>
            )}
            {showPlaceholder ? (
              <span className="italic text-slate-500">
                {text("正在生成 · Thinking...", "Generating · Thinking...")}
              </span>
            ) : (
              <div>{renderMarkdown(visibleContent)}</div>
            )}
            {isNodeStreaming && node.role === "assistant" && <StreamingCaret />}
          </div>
        )}

        {!isEditing && node.tool_calls.length > 0 && (
          <ToolCallChipList
            toolCalls={node.tool_calls}
            onOpen={() => onOpenInspector("runtime", node.id)}
            aligned={isUser ? "end" : "start"}
          />
        )}

        {!isEditing && node.artifacts.length > 0 && (
          <ArtifactRowList
            artifacts={node.artifacts}
            onOpen={() => onOpenInspector("artifacts", node.id)}
            aligned={isUser ? "end" : "start"}
            openLabel={text("打开", "Open")}
          />
        )}

        {!isEditing && <MetadataLine node={node} aligned={isUser ? "end" : "start"} />}

        {!isEditing && (node.role === "user" || node.role === "assistant") && (
          <div className={cn("flex items-center gap-1", isUser ? "justify-end" : "justify-start")}>
            {onTogglePin && (
              <button
                type="button"
                onClick={() => onTogglePin(node.id)}
                aria-label={isPinned ? text("取消固定", "Unpin message") : text("固定消息", "Pin message")}
                className={cn(
                  "h-7 w-7 inline-flex items-center justify-center rounded-md text-slate-400 hover:text-amber-600 hover:bg-slate-100 transition-colors",
                  "opacity-0 group-hover:opacity-100 focus-within:opacity-100",
                  isPinned && "opacity-100 text-amber-500",
                )}
              >
                <Pin aria-hidden="true" className={cn("h-3.5 w-3.5", isPinned && "fill-current")} />
              </button>
            )}
            <MessageActions
              role={node.role}
              canRegenerate={canRegenerate}
              isStreaming={isStreaming}
              isEditing={isEditing}
              onCopy={() => onCopy(node.id)}
              onEdit={() => onStartEdit(node.id)}
              onRegenerate={() => onRegenerate(node.id)}
            />
          </div>
        )}

        {!isEditing && createdMs !== null && (
          <div
            className={cn(
              "mt-1 flex",
              isUser ? "justify-end" : "justify-start",
            )}
          >
            <time
              dateTime={node.created_at}
              title={formatLocalIso(createdMs)}
              className="text-[10px] text-slate-400"
            >
              {formatRelativeTime(createdMs, Date.now(), isChinese ? "zh-CN" : "en")}
            </time>
          </div>
        )}

        {!isEditing && hasBufferingHint && (
          <p
            className={cn(
              "mt-2 text-[11px] text-amber-600",
              isUser ? "text-right" : "text-left",
            )}
          >
            {text(
              "检测到可能的代理缓冲（服务器或代理可能合并了 SSE 帧）",
              "Possible proxy buffering detected (server or proxy may be batching SSE frames)",
            )}
          </p>
        )}
      </div>
      {isUser && (
        <div
          aria-hidden="true"
          className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-200 text-[11px] font-semibold text-slate-700"
        >
          U
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Internal helpers (pure)
// ---------------------------------------------------------------------------

function extractThinkBlocks(content: string): string[] {
  return [...content.matchAll(/<think>([\s\S]*?)<\/think>/g)].map((match) =>
    (match[1] ?? "").trim(),
  );
}

/**
 * Parse `ConversationNode.created_at` into a numeric epoch (ms) for
 * {@link formatRelativeTime}. Returns `null` when the string is empty or not
 * a valid ISO-like date; callers then skip the `<time>` rendering.
 */
function parseCreatedAtMs(createdAt: string): number | null {
  if (createdAt.length === 0) return null;
  const ms = Date.parse(createdAt);
  if (!Number.isFinite(ms)) return null;
  return ms;
}

type ToolCallShape = {
  tool_call_id: string;
  tool_name: string;
  status: string;
};

function readToolCall(call: Record<string, unknown>, index: number): ToolCallShape {
  const toolCallId = typeof call.tool_call_id === "string"
    ? call.tool_call_id
    : typeof call.id === "string"
      ? call.id
      : `call-${index}`;
  const toolName = typeof call.tool_name === "string" && call.tool_name.length > 0
    ? call.tool_name
    : "tool";
  const status = typeof call.status === "string" ? call.status : "unknown";
  return { tool_call_id: toolCallId, tool_name: toolName, status };
}

function ToolCallChipList({
  toolCalls,
  onOpen,
  aligned,
}: {
  toolCalls: ReadonlyArray<Record<string, unknown>>;
  onOpen: () => void;
  aligned: "start" | "end";
}): JSX.Element {
  return (
    <div
      className={cn(
        "mt-2 flex flex-wrap gap-1.5",
        aligned === "end" ? "justify-end" : "justify-start",
      )}
    >
      {toolCalls.map((raw, index) => {
        const call = readToolCall(raw, index);
        return (
          <button
            key={call.tool_call_id}
            type="button"
            onClick={onOpen}
            className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-0.5 font-mono text-[11px] text-slate-700 hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-slate-400"
          >
            <Wrench aria-hidden="true" className="h-3 w-3" />
            <span className="truncate max-w-[160px]">@{call.tool_name}</span>
            <Badge tone={statusTone(call.status)}>{call.status}</Badge>
          </button>
        );
      })}
    </div>
  );
}

function ArtifactRowList({
  artifacts,
  onOpen,
  aligned,
  openLabel,
}: {
  artifacts: ConversationArtifact[];
  onOpen: () => void;
  aligned: "start" | "end";
  openLabel: string;
}): JSX.Element {
  return (
    <div
      className={cn(
        "mt-2 flex flex-col gap-1",
        aligned === "end" ? "items-end" : "items-start",
      )}
    >
      {artifacts.map((artifact) => (
        <button
          key={artifact.id}
          type="button"
          onClick={onOpen}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-slate-400"
        >
          <FileCode2 aria-hidden="true" className="h-3.5 w-3.5 text-slate-500" />
          <span className="truncate max-w-[220px] font-medium">{artifact.name}</span>
          <Badge tone="neutral">{artifact.artifact_type}</Badge>
          <span className="text-[11px] text-slate-500">{openLabel}</span>
        </button>
      ))}
    </div>
  );
}

function MetadataLine({
  node,
  aligned,
}: {
  node: ConversationNode;
  aligned: "start" | "end";
}): JSX.Element | null {
  const { input_tokens, output_tokens, cost_usd, duration_ms } = node.metadata;
  const hasAny =
    typeof input_tokens === "number" ||
    typeof output_tokens === "number" ||
    (typeof cost_usd === "string" && cost_usd.length > 0) ||
    typeof duration_ms === "number";
  if (!hasAny) return null;
  return (
    <div
      className={cn(
        "mt-1 flex flex-wrap gap-2 text-[10px] text-slate-400",
        aligned === "end" ? "justify-end" : "justify-start",
      )}
    >
      {typeof input_tokens === "number" && <span>{input_tokens} in</span>}
      {typeof output_tokens === "number" && <span>{output_tokens} out</span>}
      {typeof cost_usd === "string" && cost_usd.length > 0 && <span>${cost_usd}</span>}
      {typeof duration_ms === "number" && <span>{duration_ms}ms</span>}
    </div>
  );
}
