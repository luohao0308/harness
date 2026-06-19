/**
 * SSE error classification, HTTP body preview, and i18n error copy for the
 * chat stream. This module is pure: it does not depend on React, zustand,
 * lucide, or any UI library. See design.md §Module Layout → `lib/sseErrors.ts`
 * and §Error Handling for the governing contracts, and Property 6 for the
 * formal statements enforced by the classifiers below.
 */

export type SseErrorKind =
  | "http"
  | "network"
  | "non_sse"
  | "stream_closed"
  | "auth"
  | "model_auth"
  | "not_found"
  | "server"
  | "rate_limited";

/**
 * Stored on `ConversationNode.metadata.error` whenever an assistant node ends
 * in `state === "error"`. Never mutated in place — only replaced wholesale.
 *
 * `body_preview` is already byte-truncated (<= 256 UTF-8 bytes) by
 * `readBodyPreview` before it reaches this structure.
 */
export type ConversationErrorMeta = {
  kind: SseErrorKind;
  status?: number;
  detail?: string;
  body_preview?: string;
  /** ISO-8601 timestamp captured when the failure was classified. */
  happened_at: string;
};

type SseErrorInit = {
  kind: SseErrorKind;
  status?: number;
  detail?: string;
  body_preview?: string;
};

export function isModelAuthError(error: {
  kind?: SseErrorKind;
  status?: number;
  detail?: string;
}): boolean {
  if (error.kind === "model_auth") return true;
  const detail = error.detail ?? "";
  const authStatus =
    error.status === 401 ||
    error.status === 403 ||
    /HTTP\s+(401|403)\b/i.test(detail);
  if (!authStatus) return false;
  return (
    /api\s*key/i.test(detail) ||
    /upstream model gateway/i.test(detail) ||
    /(model|provider).*(auth|credential|key)/i.test(detail)
  );
}

/**
 * Concrete error type thrown inside `useChatStream` when the SSE pre-flight or
 * stream loop fails in a way we can classify eagerly. `toMeta()` returns a
 * plain metadata snapshot for persistence into `ConversationNode.metadata`.
 */
export class SseError extends Error {
  readonly kind: SseErrorKind;
  readonly status?: number;
  readonly detail?: string;
  readonly body_preview?: string;
  readonly happened_at: string;

  constructor(init: SseErrorInit) {
    const parts: string[] = [`[SseError:${init.kind}]`];
    if (init.status != null) parts.push(String(init.status));
    if (init.detail) parts.push(init.detail);
    super(parts.join(" "));
    // Restore the prototype chain so `instanceof SseError` works when
    // compiled to ES5 targets or across module realms.
    Object.setPrototypeOf(this, new.target.prototype);
    this.name = "SseError";
    this.kind = init.kind;
    this.status = init.status;
    this.detail = init.detail;
    this.body_preview = init.body_preview;
    this.happened_at = new Date().toISOString();
  }

  toMeta(): ConversationErrorMeta {
    const meta: ConversationErrorMeta = {
      kind: this.kind,
      happened_at: this.happened_at,
    };
    if (this.status != null) meta.status = this.status;
    if (this.detail != null) meta.detail = this.detail;
    if (this.body_preview != null) meta.body_preview = this.body_preview;
    return meta;
  }
}

/**
 * Classify an HTTP status into an `SseErrorKind`.
 *
 * Contract (Property 6 clause 1):
 *   - 401 / 403 → "auth"
 *   - 404       → "not_found"
 *   - >= 500    → "server"
 *   - other non-2xx → "http"
 *
 * The caller is expected to invoke this only when `res.ok` is false. Inputs
 * outside the well-formed HTTP range `[100, 599]` or non-integers are mapped
 * defensively to "http" so we never throw for unexpected values.
 */
export function classifyHttpStatus(status: number): SseErrorKind {
  if (!Number.isInteger(status)) return "http";
  if (status < 100 || status > 599) return "http";
  if (status === 401 || status === 403) return "auth";
  if (status === 404) return "not_found";
  if (status >= 500) return "server";
  return "http";
}

/**
 * Classify a thrown value from `fetch` / stream pump into an `SseErrorKind`.
 *
 * Contract (Property 6 clause 3):
 *   - `TypeError`                                → "network"
 *   - `DOMException("NetworkError", …)`          → "network"
 *   - `DOMException("…", "AbortError")`          → "network"
 *     Only the watchdog abort reaches this path; user-initiated `pause()`
 *     aborts are intercepted earlier by the hook by checking
 *     `signal.aborted` before dispatching here.
 *   - anything else (plain `Error`, `{}`, etc.)  → "server"
 */
export function classifyFetchError(err: unknown): SseErrorKind {
  if (err instanceof TypeError) return "network";
  if (typeof DOMException !== "undefined" && err instanceof DOMException) {
    if (err.name === "NetworkError" || err.name === "AbortError") return "network";
  }
  // Duck-typed fallback for cross-realm errors or environments where the
  // `DOMException` / `TypeError` identity does not survive structured cloning.
  if (err !== null && typeof err === "object" && "name" in err) {
    const name = (err as { name: unknown }).name;
    if (name === "TypeError" || name === "NetworkError" || name === "AbortError") {
      return "network";
    }
  }
  return "server";
}

/**
 * Returns true iff `value` contains the substring `text/event-stream`
 * (case-insensitive). `null` and empty strings return false.
 *
 * Contract (Property 6 clause 2). Designed for `Response.headers.get
 * ("content-type")` which returns `string | null`.
 */
export function isSseContentType(value: string | null): boolean {
  if (value == null || value === "") return false;
  return value.toLowerCase().includes("text/event-stream");
}

/**
 * Read the first `maxBytes` bytes of a `Response` body and decode them as
 * UTF-8 with replacement. The returned string is guaranteed to encode back
 * to **at most** `maxBytes` UTF-8 bytes (Property 6 clause 4).
 *
 * Implementation detail: `TextDecoder({ fatal: false })` replaces truncated
 * multi-byte sequences with `U+FFFD` (3 bytes in UTF-8), which can grow the
 * re-encoded length past `maxBytes`. We trim trailing code points until the
 * re-encoded size is within budget. Empty bodies and decode failures both
 * fall back to `""` — this function never throws.
 */
export async function readBodyPreview(res: Response, maxBytes = 256): Promise<string> {
  try {
    const buf = await res.arrayBuffer();
    const bytes = new Uint8Array(buf);
    if (bytes.byteLength === 0) return "";
    const slice = bytes.byteLength <= maxBytes ? bytes : bytes.subarray(0, maxBytes);
    const decoder = new TextDecoder("utf-8", { fatal: false, ignoreBOM: false });
    let str = decoder.decode(slice);
    const encoder = new TextEncoder();
    while (str.length > 0 && encoder.encode(str).byteLength > maxBytes) {
      // Drop one UTF-16 code unit at a time. Every remaining code point
      // encodes to at least 1 UTF-8 byte, so this terminates in O(str.length).
      str = str.slice(0, -1);
    }
    return str;
  } catch {
    return "";
  }
}

/**
 * Copy keys used by `formatErrorMessage`. Each entry is a `[zh, en]` tuple so
 * consumers can forward it to the `useI18n().text(zh, en)` resolver.
 *
 * Exported as a readonly constant so UI components that want to render
 * auxiliary copy (e.g. the Retry button label) can reuse the same
 * localisation pairs without duplicating strings.
 */
export const ERROR_COPY_KEYS = {
  HTTP_PREFIX: ["HTTP 错误", "HTTP error"],
  NETWORK_UNREACHABLE: ["无法连接 Harness 后端", "Cannot reach Harness backend"],
  NON_SSE: ["响应不是 SSE 服务端事件流", "Response is not an SSE stream"],
  STREAM_CLOSED: ["SSE 服务端事件流意外中断", "SSE stream closed unexpectedly"],
  AUTH: ["鉴权失败，请重新登录", "Authentication failed. Please sign in again."],
  MODEL_AUTH: [
    "模型密钥无效",
    "Model API key is invalid",
  ],
  NOT_FOUND: ["目标 Agent 不存在", "Target agent not found"],
  SERVER: ["后端内部错误", "Backend internal error"],
  RATE_LIMITED: [
    "模型触发限流 (429)，请稍后再试或在设置里切换供应商",
    "Model rate-limited (429). Try again later or switch provider in Settings.",
  ],
  RETRY: ["重试", "Retry"],
} as const satisfies {
  readonly HTTP_PREFIX: readonly [string, string];
  readonly NETWORK_UNREACHABLE: readonly [string, string];
  readonly NON_SSE: readonly [string, string];
  readonly STREAM_CLOSED: readonly [string, string];
  readonly AUTH: readonly [string, string];
  readonly MODEL_AUTH: readonly [string, string];
  readonly NOT_FOUND: readonly [string, string];
  readonly SERVER: readonly [string, string];
  readonly RATE_LIMITED: readonly [string, string];
  readonly RETRY: readonly [string, string];
};

/**
 * Format a `ConversationErrorMeta` into `{ title, description }` for
 * `ChatErrorBubble`. The bubble component renders the returned strings
 * directly; HTML is not supported. The caller supplies the i18n resolver so
 * this module stays framework-agnostic.
 */
export function formatErrorMessage(
  error: ConversationErrorMeta,
  text: (zh: string, en: string) => string,
  context: { apiBaseUrl: string },
): { title: string; description: string } {
  const parts: string[] = [];
  let title: string;

  const kind = isModelAuthError(error) ? "model_auth" : error.kind;

  switch (kind) {
    case "auth": {
      title = text(ERROR_COPY_KEYS.AUTH[0], ERROR_COPY_KEYS.AUTH[1]);
      if (typeof error.status === "number") parts.push(`HTTP ${error.status}`);
      if (error.detail) parts.push(error.detail);
      break;
    }
    case "model_auth": {
      title = text(ERROR_COPY_KEYS.MODEL_AUTH[0], ERROR_COPY_KEYS.MODEL_AUTH[1]);
      parts.push(
        text(
          "当前模型供应商认证失败。请在模型设置里更新 DeepSeek API Key，或切换到可用供应商。",
          "The selected model provider rejected authentication. Update the provider API key in Model Settings or switch to a working provider.",
        ),
      );
      if (typeof error.status === "number") parts.push(`HTTP ${error.status}`);
      if (error.detail) parts.push(error.detail);
      break;
    }
    case "not_found": {
      title = text(ERROR_COPY_KEYS.NOT_FOUND[0], ERROR_COPY_KEYS.NOT_FOUND[1]);
      if (typeof error.status === "number") parts.push(`HTTP ${error.status}`);
      if (error.detail) parts.push(error.detail);
      break;
    }
    case "server": {
      title = text(ERROR_COPY_KEYS.SERVER[0], ERROR_COPY_KEYS.SERVER[1]);
      if (typeof error.status === "number") parts.push(`HTTP ${error.status}`);
      if (error.detail) parts.push(error.detail);
      break;
    }
    case "rate_limited": {
      title = text(ERROR_COPY_KEYS.RATE_LIMITED[0], ERROR_COPY_KEYS.RATE_LIMITED[1]);
      if (error.detail) parts.push(error.detail);
      break;
    }
    case "http": {
      title = text(ERROR_COPY_KEYS.HTTP_PREFIX[0], ERROR_COPY_KEYS.HTTP_PREFIX[1]);
      if (typeof error.status === "number") parts.push(`HTTP ${error.status}`);
      if (error.detail) parts.push(error.detail);
      break;
    }
    case "network": {
      title = text(
        ERROR_COPY_KEYS.NETWORK_UNREACHABLE[0],
        ERROR_COPY_KEYS.NETWORK_UNREACHABLE[1],
      );
      parts.push(`API_BASE_URL: ${context.apiBaseUrl}`);
      if (error.detail) parts.push(error.detail);
      break;
    }
    case "non_sse": {
      title = text(ERROR_COPY_KEYS.NON_SSE[0], ERROR_COPY_KEYS.NON_SSE[1]);
      if (typeof error.status === "number") parts.push(`HTTP ${error.status}`);
      if (error.body_preview) parts.push(error.body_preview);
      break;
    }
    case "stream_closed": {
      title = text(ERROR_COPY_KEYS.STREAM_CLOSED[0], ERROR_COPY_KEYS.STREAM_CLOSED[1]);
      if (error.detail) parts.push(error.detail);
      break;
    }
  }

  return { title, description: parts.join(" · ") };
}
