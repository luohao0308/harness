/**
 * ChatErrorBubble — renders an assistant node whose `state === "error"`.
 *
 * Satisfies:
 *   - Req 4.1–4.5: renders `role="alert"`, shows human-readable title +
 *     description from `formatErrorMessage`, displays the truncated
 *     `body_preview` in a scrollable `<pre>`, and provides a Retry action.
 *   - Req 3.2 / 3.7 / 1.6: when `node.content` is non-empty (partial output
 *     was accumulated before the failure), that content is still rendered as
 *     markdown so users can see what the agent produced prior to erroring.
 *   - Req 9.1, 9.5: all copy flows through `useI18n().text(zh, en)`; the
 *     Retry button carries a visible label.
 *   - Req 13.6 / 13.8 / 14.2 (v2): exposes a "复制错误详情 / Copy error
 *     details" button alongside Retry that writes a multi-line plain-text
 *     summary to the clipboard via `copyText` (which already falls back to
 *     `document.execCommand("copy")` on browsers that lack `navigator.
 *     clipboard`). On success we briefly swap the Copy icon + label for the
 *     `Check` / "已复制 · Copied" state for 1500ms (mirrors `MessageActions`).
 *
 * Pure presentational component: stateless except for the `justCopied`
 * timer and its ref. Does not import the workspace store. Only reads
 * `VITE_API_BASE_URL` from `import.meta.env` to mirror the api.ts fallback
 * when none is configured.
 */

import { useEffect, useRef, useState, type JSX } from "react";
import { AlertTriangle, Check, Copy, RotateCw } from "lucide-react";

import { Button } from "../../../components/ui/button";
import { useI18n } from "../../../lib/i18n";
import { copyText } from "../lib/clipboard";
import { renderMarkdown } from "../lib/markdown";
import {
  ERROR_COPY_KEYS,
  formatErrorMessage,
  type ConversationErrorMeta,
} from "../lib/sseErrors";
import type { ConversationNode } from "../../../stores/workspaceStore";

// Match apps/agent-console/src/features/tasks/api.ts fallback exactly so the
// network-error description points to the same URL the fetcher actually uses.
const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000";

/**
 * Serialise the user-facing error context into a multi-line plain-text
 * block suitable for pasting into a bug report or support channel.
 *
 * Pure function (TOTAL): deterministic output for identical inputs, never
 * throws, does not touch `window` / `document` / React. Exported so a
 * property-based test can pin its behaviour independently from the React
 * component.
 *
 * Output lines are emitted in a stable order and only fields with a
 * meaningful value are included — there is no trailing blank line, and the
 * return value is `""` when every field is absent.
 *
 * The `node` parameter uses a structural type rather than `ConversationNode`
 * so the helper can be called with either the full node or a partial fixture
 * in tests.
 */
export function formatErrorDetail(
  node: { content?: string; run_id?: string },
  error: ConversationErrorMeta,
  runId: string | undefined,
): string {
  // Touch `node` defensively so the TS compiler treats the parameter as
  // used in strict mode. The helper intentionally only relies on `runId`
  // today; keeping `node` in the signature leaves room for future fields
  // (e.g. partial content) without churning call-sites.
  void node;

  const lines: string[] = [];
  if (error.kind) lines.push(`Kind: ${error.kind}`);
  if (error.status) lines.push(`HTTP: ${error.status}`);
  if (error.detail) lines.push(`Detail: ${error.detail}`);
  if (error.body_preview) lines.push(`Body: ${error.body_preview}`);
  if (runId) lines.push(`Run: ${runId}`);
  if (error.happened_at) lines.push(`At: ${error.happened_at}`);
  return lines.join("\n");
}

export type ChatErrorBubbleProps = {
  /** Node whose `state` is expected to be `"error"`. */
  node: ConversationNode;
  /** Structured error metadata. Required: error bubbles must carry meta. */
  error: ConversationErrorMeta;
  /** Invoked when the user clicks the Retry button. */
  onRetry: () => void;
};

export function ChatErrorBubble({ node, error, onRetry }: ChatErrorBubbleProps): JSX.Element {
  const { text } = useI18n();
  const { title, description } = formatErrorMessage(error, text, {
    apiBaseUrl: API_BASE_URL,
  });
  const partialContent = node.content.replace(/<think>[\s\S]*?<\/think>/g, "").trim();
  const retryLabel = text(ERROR_COPY_KEYS.RETRY[0], ERROR_COPY_KEYS.RETRY[1]);

  // `justCopied` mirrors the `MessageActions` UI pattern: flip to true on a
  // successful clipboard write and auto-reset after 1500ms. A ref holds the
  // timer id so repeated clicks can cancel the previous reset before arming
  // a new one (Req 13.6 / 5.3 analogue).
  const [justCopied, setJustCopied] = useState(false);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  async function handleCopyDetails(): Promise<void> {
    const payload = formatErrorDetail(node, error, node.run_id);
    const ok = await copyText(payload);
    if (!ok) {
      setJustCopied(false);
      return;
    }
    setJustCopied(true);
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
    }
    timerRef.current = window.setTimeout(() => {
      setJustCopied(false);
      timerRef.current = null;
    }, 1500);
  }

  const copyLabel = justCopied
    ? text("已复制", "Copied")
    : text("复制错误详情", "Copy error details");

  return (
    <div className="flex justify-start gap-3">
      <div
        aria-hidden="true"
        className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-red-200 bg-red-50 text-red-700"
      >
        <AlertTriangle className="h-4 w-4" />
      </div>
      <div
        role="alert"
        className="min-w-0 max-w-[75%] rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-800 shadow-sm"
      >
        <div className="flex items-center justify-between gap-3">
          <span className="font-semibold">{title}</span>
        </div>
        {description.length > 0 && (
          <p className="mt-1 whitespace-pre-wrap text-xs text-red-700">{description}</p>
        )}
        {partialContent.length > 0 && (
          <div className="mt-2 rounded-lg border border-red-100 bg-white p-2 text-slate-800">
            {renderMarkdown(partialContent)}
          </div>
        )}
        {error.body_preview && error.body_preview.length > 0 && (
          <pre className="mt-2 max-h-24 overflow-auto rounded bg-white p-2 font-mono text-[10px] text-slate-700">
            {error.body_preview}
          </pre>
        )}
        <div className="mt-3 flex items-center justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={handleCopyDetails}
            aria-label={copyLabel}
          >
            {justCopied ? (
              <Check aria-hidden="true" className="h-3.5 w-3.5 text-emerald-600" />
            ) : (
              <Copy aria-hidden="true" className="h-3.5 w-3.5" />
            )}
            {copyLabel}
          </Button>
          <Button variant="danger" onClick={onRetry} aria-label={retryLabel}>
            <RotateCw aria-hidden="true" className="h-3.5 w-3.5" />
            {retryLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
