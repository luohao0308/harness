/**
 * SSE-driven chat stream hook for the Workspace chat surface.
 *
 * The hook owns:
 *   - Pre-flight creation of the user + assistant `ConversationNode` pair.
 *   - A 10-second watchdog that aborts the in-flight `fetch` when the server
 *     never writes a single event.
 *   - HTTP status + Content-Type classification into `SseError`.
 *   - SSE frame-by-frame dispatch into `useWorkspaceStore` via the store's
 *     command-style actions (`appendContent`, `appendArtifact`, `updateNode`).
 *   - A single `catch` block that writes terminal state (`error` or `paused`)
 *     onto the assistant node, honouring the error-over-abort precedence
 *     (Req 4.8).
 *   - Pause / resume / retry controllers that stay consistent with the
 *     reducer semantics in `lib/chatEventReducer.ts` (Property 5) even though
 *     the hook talks to the store imperatively.
 *
 * This module is intentionally free of React UI concerns — it never touches
 * `useI18n`, JSX, or routing. Callers compose the returned controller inside
 * their surface components. See design.md §useChatStream Hook for the full
 * contract and requirements.md Req 3, 4, 5 plus P2, P3 for the invariants
 * this hook enforces.
 */

import { useCallback, useRef } from "react";

import type {
  AgentAttachmentPayload,
  AgentChatStreamEvent,
  AgentChatStreamMessage,
  AgentChatStreamPayload,
  ToolMetadata,
} from "../../tasks/api";
import { parseChatSseFrame } from "../../tasks/api";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import type { ConversationArtifact, ConversationNode } from "../../../stores/workspaceStore";
import { mergeToolCallEvent } from "../streamEvents";
import { mergeErrorMeta, planInitialNodes } from "../lib/chatEventReducer";
import {
  COMPRESSION_PROMPT_VERSION,
  SUMMARY_SCHEMA_VERSION,
  contextCompressionBranchKey,
  selectBestCompressionSummary,
  uncoveredContextPath,
} from "../lib/contextCompression";
import { truncateForContext } from "../lib/contextTruncation";
import { extractToolMentions } from "../lib/toolMentions";
import {
  SseError,
  classifyFetchError,
  classifyHttpStatus,
  isSseContentType,
  readBodyPreview,
  type ConversationErrorMeta,
} from "../lib/sseErrors";
import type { WorkspaceMode } from "../lib/types";
import { useStreamFlush } from "./useStreamFlush";

/**
 * API base URL used for the chat stream request. Mirrors the expression in
 * `features/tasks/api.ts`; duplicated here rather than imported because the
 * constant is module-private there and this hook must not widen that file's
 * public surface (see design.md §Wrapping streamAgentChatRun).
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const DEV_BEARER_TOKEN = import.meta.env.VITE_DEV_BEARER_TOKEN ?? "dev-engineer-token";

/** 10 seconds — no server byte within this window aborts the stream. */
const CONNECTION_TIMEOUT_MS = 10_000;
/** Maximum body preview kept when the Content-Type rejects the stream. */
const NON_SSE_PREVIEW_BYTES = 256;

export type UseChatStreamArgs = {
  agentId: string;
  workspaceMode: WorkspaceMode;
  selectedProviderId?: string | null;
  selectedModelId?: string | null;
  /** Invoked exactly once per run, with the `run_id` from `run_created`. */
  onRunCreated?: (runId: string) => void;
  /** Current registry entries used to serialize `@tool` mentions. */
  tools?: readonly ToolMetadata[];
  /** Test hook; defaults to `globalThis.fetch`. */
  fetchImpl?: typeof fetch;
};

export type ChatStreamController = {
  isStreaming: boolean;
  start(input: StreamStartInput): Promise<void>;
  pause(): void;
  resume(pausedNodeId: string): Promise<void>;
  retry(errorNodeId: string): Promise<void>;
  /**
   * Drive an SSE run against an already-appended assistant node (additive
   * for v2 Edit / Regenerate / Plan-approve flows; see design.md §Branch
   * creation for Edit/Regenerate). The caller is responsible for having
   * created the user + assistant node pair (or just the assistant node in
   * the Regenerate case) before invocation.
   *
   * Shares the hook's single in-flight controller with `start` / `pause` /
   * `resume` / `retry`; when a stream is already in flight the call is a
   * no-op (Req 4.8).
   */
  driveBranch(input: {
    assistantNodeId: string;
    goal: string;
    mode: WorkspaceMode;
  }): Promise<void>;
};

type DriveStreamArgs = {
  assistantNodeId: string;
  abort: AbortController;
  payload: AgentChatStreamPayload;
};

type BuildPayloadInput = {
  mode: WorkspaceMode;
  goal: string;
  runId?: string;
  continueFromNodeId?: string;
  partialContent?: string;
  attachmentNames?: string[];
  attachments?: AgentAttachmentPayload[];
};

type StreamStartInput = {
  goal: string;
  mode: WorkspaceMode;
  attachmentNames?: string[];
  attachments?: AgentAttachmentPayload[];
};

export function useChatStream(args: UseChatStreamArgs): ChatStreamController {
  const {
    agentId,
    workspaceMode,
    selectedProviderId = null,
    selectedModelId = null,
    onRunCreated,
    tools = [],
    fetchImpl,
  } = args;

  // The `isStreaming` derivation subscribes to the store so that consuming
  // components re-render (and disable their send button) whenever a stream
  // begins or ends. See P6 in requirements.md.
  const isStreaming = useWorkspaceStore((state) => Boolean(state.activeStream));

  // Commit scheduler that defeats React 18 automatic batching during SSE
  // delta application. See `useStreamFlush` and design.md §Streaming flush
  // architecture (Req 2 / P2 / P3).
  const flush = useStreamFlush();

  // Mutable refs live outside the render cycle. React never reads these
  // during render, so there is no tearing risk.
  const controllerRef = useRef<AbortController | null>(null);
  const watchdogRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const watchdogTimedOutRef = useRef(false);

  /**
   * Drives one request → parse → store write cycle. Shared by `start`,
   * `resume`, and `retry` (via `start`) so the error routing and cleanup
   * logic live in exactly one place.
   */
  const driveStream = useCallback(
    async ({ assistantNodeId, abort, payload }: DriveStreamArgs): Promise<void> => {
      const startedAtMs = performance.now();
      let firstDeltaAt: number | null = null;
      // Used by the catch branch to decide between `paused` and `error` when
      // the abort signal has fired (watchdog vs user-initiated pause).
      watchdogTimedOutRef.current = false;

      const clearWatchdog = (): void => {
        if (watchdogRef.current !== null) {
          clearTimeout(watchdogRef.current);
          watchdogRef.current = null;
        }
      };

      watchdogRef.current = setTimeout(() => {
        watchdogTimedOutRef.current = true;
        abort.abort(new DOMException("connection timeout", "AbortError"));
      }, CONNECTION_TIMEOUT_MS);

      const dispatchEvent = (event: AgentChatStreamEvent): void => {
        // If this stream has been superseded (retry/start called again), any
        // further store writes would clobber the new assistant node.
        if (controllerRef.current !== abort) return;

        const store = useWorkspaceStore.getState();
        const current = store.nodesById[assistantNodeId];
        if (!current) return;

        switch (event.type) {
          case "run_created": {
            onRunCreated?.(event.run_id);
            store.updateNode(assistantNodeId, { run_id: event.run_id });
            clearWatchdog();
            return;
          }
          case "delta": {
            if (firstDeltaAt === null) firstDeltaAt = performance.now();
            // Write directly to store to survive component unmount during navigation.
            // The store's appendContent is global and does not depend on React lifecycle.
            useWorkspaceStore.getState().appendContent(assistantNodeId, event.content);
            clearWatchdog();
            return;
          }
          case "think_delta": {
            if (firstDeltaAt === null) firstDeltaAt = performance.now();
            useWorkspaceStore
              .getState()
              .appendContent(assistantNodeId, `<think>${event.content}</think>`);
            clearWatchdog();
            return;
          }
          case "tool_call_requested":
          case "tool_call_result": {
            store.updateNode(assistantNodeId, {
              tool_calls: mergeToolCallEvent(current.tool_calls, event),
            });
            return;
          }
          case "artifact_created": {
            const artifact: ConversationArtifact = {
              id: `${assistantNodeId}-${event.name}`,
              name: event.name,
              artifact_type: event.artifact_type,
              status: event.status,
              content: event.content,
              run_id: event.run_id,
            };
            store.appendArtifact(assistantNodeId, artifact);
            return;
          }
          case "usage": {
            const ttfbFallback =
              firstDeltaAt !== null ? Math.round(firstDeltaAt - startedAtMs) : 0;
            const ttfbMs = event.ttfb_ms || ttfbFallback;
            store.updateNode(assistantNodeId, {
              metadata: {
                ...current.metadata,
                input_tokens: event.input_tokens,
                output_tokens: event.output_tokens,
                cost_usd: event.cost_usd,
                cost_unavailable: event.cost_unavailable,
                ttfb_ms: ttfbMs,
                duration_ms:
                  event.duration_ms || Math.round(performance.now() - startedAtMs),
                model_call_id: event.model_call_id,
                active_branch_id: store.activeLeafId,
              },
            });
            return;
          }
          case "done": {
            flush.drain();
            store.updateNode(assistantNodeId, {
              state: "done",
              run_id: event.run_id,
              metadata: {
                ...current.metadata,
                knowledge_grounding: event.knowledge_grounding,
              },
            });
            return;
          }
          case "error": {
            flush.drain();
            const detail = event.message;
            const isRateLimited = /429|rate[- ]?limit|too many requests/i.test(
              detail,
            );
            const meta: ConversationErrorMeta = {
              kind: isRateLimited ? "rate_limited" : "server",
              detail,
              happened_at: new Date().toISOString(),
            };
            store.updateNode(assistantNodeId, {
              state: "error",
              metadata: mergeErrorMeta(current.metadata, meta),
            });
            return;
          }
          default: {
            // Exhaustiveness guard — `AgentChatStreamEvent` is a closed union.
            const exhaustive: never = event;
            void exhaustive;
            return;
          }
        }
      };

      try {
        await runStream({
          agentId,
          payload,
          signal: abort.signal,
          fetchImpl: fetchImpl ?? globalThis.fetch.bind(globalThis),
          onEvent: dispatchEvent,
          onDiagnostic: (kind) => {
            // Stream was superseded — ignore late diagnostics.
            if (controllerRef.current !== abort) return;
            const store = useWorkspaceStore.getState();
            const current = store.nodesById[assistantNodeId];
            if (!current) return;
            store.updateNode(assistantNodeId, {
              metadata: {
                ...current.metadata,
                streaming_diagnostic: kind,
              },
            });
          },
        });
      } catch (err) {
        // Stream was superseded by a newer start/retry — drop the error.
        if (controllerRef.current !== abort) return;
        flush.drain();
        writeTerminalState(assistantNodeId, err, {
          aborted: abort.signal.aborted,
          watchdogTimedOut: watchdogTimedOutRef.current,
        });
      } finally {
        if (controllerRef.current === abort) {
          controllerRef.current = null;
          useWorkspaceStore.getState().setActiveStream(null);
        }
        if (watchdogRef.current !== null) {
          clearTimeout(watchdogRef.current);
          watchdogRef.current = null;
        }
      }
    },
    [agentId, fetchImpl, flush, onRunCreated],
  );

  /**
   * Build the payload for the chat stream endpoint. Mirrors the shape used by
   * the legacy `AgentWorkspacePage` implementation so the backend contract is
   * unchanged (Req 10.3).
   *
   * v4.1 additive: applies `truncateForContext` before serializing messages
   * so the API payload stays within the configured token budget. The store
   * data is never mutated — truncation is payload-only.
   */
  const buildPayload = useCallback(
    (input: BuildPayloadInput): AgentChatStreamPayload => {
      const store = useWorkspaceStore.getState();
      const activePath = store.activePath();
      const branchKey = contextCompressionBranchKey(
        store.currentConversationId,
        store.activeLeafId,
      );
      const summary = selectBestCompressionSummary({
        summaries: store.contextCompressions,
        branchKey,
        activePath,
        pinnedNodeIds: store.pinnedNodeIds,
        providerId: selectedProviderId,
        modelId: selectedModelId,
      });
      const promptPath = uncoveredContextPath({
        activePath,
        pinnedNodeIds: store.pinnedNodeIds,
        summary,
      });

      // Apply fallback truncation after summary + pinned + uncovered assembly.
      const { messages: truncatedMessages } = truncateForContext(
        promptPath,
        store.pinnedNodeIds,
        store.contextMaxTokens,
      );

      return {
        mode: input.mode,
        goal: input.goal,
        model_provider: selectedProviderId,
        model_name: selectedModelId,
        messages: serializeMessages(truncatedMessages),
        active_leaf_id: store.activeLeafId,
        run_id: input.runId,
        active_branch_id: store.activeLeafId,
        pinned_node_ids: store.pinnedNodeIds,
        context_window_turns: store.contextWindowTurns,
        continue_from_node_id: input.continueFromNodeId,
        partial_assistant_content: input.partialContent,
        tool_mentions: extractToolMentions(input.goal, tools),
        attachment_names: input.attachmentNames ?? [],
        attachments: input.attachments ?? [],
        // v4 additive: UI-side context budget hint (Req 5.5).
        context_max_tokens: store.contextMaxTokens,
        compressed_context:
          summary === null
            ? null
            : {
                summary: summary.summary,
                coverage_node_ids: summary.coverageNodeIds,
                coverage_path_hash: summary.coveragePathHash,
                summary_schema_version: SUMMARY_SCHEMA_VERSION,
                compression_prompt_version: COMPRESSION_PROMPT_VERSION,
                compressor_provider: summary.compressorProvider,
                compressor_model: summary.compressorModel,
              },
      };
    },
    [selectedModelId, selectedProviderId, tools],
  );

  const start = useCallback(
    async (input: StreamStartInput): Promise<void> => {
      const goal = input.goal.trim();
      // Req 2.4 / 2.5 — empty drafts and in-flight streams are no-ops.
      if (goal.length === 0 || controllerRef.current !== null) return;

      const store = useWorkspaceStore.getState();
      const [userPatch, assistantPatch] = planInitialNodes(goal, input.mode);

      // Two atomic appends — the store wires `parent_id` from the active leaf
      // on the first call, then we explicitly nest the assistant under the
      // freshly created user node.
      const userNodeId = store.appendNode(userPatch);
      const assistantNodeId = store.appendNode({
        ...assistantPatch,
        parent_id: userNodeId,
      });

      const abort = new AbortController();
      controllerRef.current = abort;
      store.setActiveStream({
        node_id: assistantNodeId,
        controller: abort,
        started_at: performance.now(),
      });

      await driveStream({
        assistantNodeId,
        abort,
        payload: buildPayload({
          mode: input.mode,
          goal,
          attachmentNames: input.attachmentNames,
          attachments: input.attachments,
        }),
      });
    },
    [buildPayload, driveStream],
  );

  const pause = useCallback((): void => {
    const current = controllerRef.current;
    if (current === null) return;
    // The terminal state is decided inside driveStream's catch block — this
    // keeps the error-over-abort precedence (Req 4.8) in one place.
    current.abort();
  }, []);

  const resume = useCallback(
    async (pausedNodeId: string): Promise<void> => {
      if (controllerRef.current !== null) return;

      const store = useWorkspaceStore.getState();
      const paused = store.nodesById[pausedNodeId];
      if (!paused || paused.state !== "paused") return;

      if (!paused.run_id || paused.run_id.length === 0) {
        // Req 5.5 — paused without a run cannot be resumed.
        const meta: ConversationErrorMeta = {
          kind: "server",
          detail: "Run 尚未创建，无法继续",
          happened_at: new Date().toISOString(),
        };
        store.updateNode(pausedNodeId, {
          state: "error",
          metadata: mergeErrorMeta(paused.metadata, meta),
        });
        return;
      }

      const activePath = store.activePath();
      const prevUser = findPrevUserInternal(activePath, pausedNodeId);
      if (!prevUser) return;

      const abort = new AbortController();
      controllerRef.current = abort;
      store.setActiveStream({
        node_id: pausedNodeId,
        controller: abort,
        started_at: performance.now(),
      });
      store.updateNode(pausedNodeId, { state: "streaming" });

      const mode = paused.metadata.workspace_mode ?? workspaceMode;

      await driveStream({
        assistantNodeId: pausedNodeId,
        abort,
        payload: buildPayload({
          mode,
          goal: prevUser.content,
          runId: paused.run_id,
          continueFromNodeId: pausedNodeId,
          partialContent: paused.content,
        }),
      });
    },
    [buildPayload, driveStream, workspaceMode],
  );

  const retry = useCallback(
    async (errorNodeId: string): Promise<void> => {
      if (controllerRef.current !== null) return;

      const store = useWorkspaceStore.getState();
      const errorNode = store.nodesById[errorNodeId];
      if (!errorNode || errorNode.state !== "error") return;

      const activePath = store.activePath();
      const prevUser = findPrevUserInternal(activePath, errorNodeId);
      if (!prevUser) return;

      const mode = errorNode.metadata.workspace_mode ?? workspaceMode;
      await start({ goal: prevUser.content, mode });
    },
    [start, workspaceMode],
  );

  /**
   * Drive an SSE run against an already-appended assistant node. Used by
   * v2 Edit / Regenerate / Plan-approve flows that create the user +
   * assistant branch upstream via `useWorkspaceStore.appendNode`; this
   * controller intentionally skips `planInitialNodes` / `appendNode` so the
   * caller retains full control over the tree shape (Design §Architecture
   * → "Branch creation for Edit/Regenerate").
   *
   * Shares `controllerRef` with `start` / `pause` / `resume` / `retry` —
   * a non-null controller causes an early return to preserve the
   * single-stream invariant (Req 4.8, Req 2.9).
   */
  const driveBranch = useCallback(
    async (input: {
      assistantNodeId: string;
      goal: string;
      mode: WorkspaceMode;
    }): Promise<void> => {
      if (controllerRef.current !== null) return;

      const abort = new AbortController();
      controllerRef.current = abort;

      const store = useWorkspaceStore.getState();
      store.setActiveStream({
        node_id: input.assistantNodeId,
        controller: abort,
        started_at: performance.now(),
      });

      await driveStream({
        assistantNodeId: input.assistantNodeId,
        abort,
        payload: buildPayload({ mode: input.mode, goal: input.goal }),
      });
    },
    [buildPayload, driveStream],
  );

  return { isStreaming, start, pause, resume, retry, driveBranch };
}

/**
 * Fetch + SSE pump. Throws `SseError` for every classified failure (HTTP
 * non-2xx, Content-Type mismatch, reader closed before `done`). Network
 * errors bubble up as the original `TypeError`/`DOMException` so the caller
 * can distinguish them via `classifyFetchError`.
 */
async function runStream(opts: {
  agentId: string;
  payload: AgentChatStreamPayload;
  signal: AbortSignal;
  fetchImpl: typeof fetch;
  onEvent: (event: AgentChatStreamEvent) => void;
  /**
   * Fires once when response headers indicate the stream may be buffered by
   * an upstream proxy (gzip / missing chunked transfer-encoding). The caller
   * is responsible for persisting the diagnostic on the assistant node
   * (Req 2.8; Design §Error Handling → "SSE streaming diagnostic").
   */
  onDiagnostic?: (kind: "possible_buffering") => void;
}): Promise<void> {
  const response = await opts.fetchImpl(
    `${API_BASE_URL}/api/agents/${opts.agentId}/runs/chat/stream`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${DEV_BEARER_TOKEN}`,
      },
      body: JSON.stringify(opts.payload),
      signal: opts.signal,
    },
  );

  if (!response.ok) {
    const detail = await tryParseDetail(response);
    throw new SseError({
      kind: classifyHttpStatus(response.status),
      status: response.status,
      detail,
    });
  }

  if (!isSseContentType(response.headers.get("content-type"))) {
    const bodyPreview = await readBodyPreview(response, NON_SSE_PREVIEW_BYTES);
    throw new SseError({
      kind: "non_sse",
      status: response.status,
      body_preview: bodyPreview,
    });
  }

  if (!response.body) {
    throw new SseError({ kind: "stream_closed" });
  }

  // Req 2.8 — inspect Content-Encoding / Transfer-Encoding to surface likely
  // upstream buffering. Fires at most once per stream. We intentionally
  // allow the read loop to proceed; the diagnostic is advisory.
  const headers = response.headers;
  const contentEncoding = headers.get("content-encoding") ?? "";
  const transferEncoding = headers.get("transfer-encoding") ?? "";
  const contentLength = headers.get("content-length");
  const isCompressed = /gzip|br|deflate/i.test(contentEncoding);
  const lacksChunked =
    !transferEncoding.toLowerCase().includes("chunked") && contentLength !== null;
  if (isCompressed || lacksChunked) {
    opts.onDiagnostic?.("possible_buffering");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let sawDone = false;
  // A server-emitted `error` event is a legitimate terminal state — the
  // dispatcher already writes `{state:"error",metadata}` onto the
  // assistant node. Don't overwrite it with a bogus `stream_closed` just
  // because no `done` frame followed (Req 11.*; previously caused the
  // 429 rate-limit case to surface as "stream_closed" in the UI).
  let sawError = false;

  // The reader loop intentionally mirrors `streamAgentChatRun` in
  // `features/tasks/api.ts` so SSE framing stays consistent across the
  // codebase.
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const event = parseChatSseFrame(frame);
      if (!event) continue;
      if (event.type === "done") sawDone = true;
      if (event.type === "error") sawError = true;
      opts.onEvent(event);
    }
  }
  const tail = parseChatSseFrame(buffer);
  if (tail) {
    if (tail.type === "done") sawDone = true;
    if (tail.type === "error") sawError = true;
    opts.onEvent(tail);
  }

  if (!sawDone && !sawError) {
    throw new SseError({ kind: "stream_closed" });
  }
}

/**
 * Best-effort extraction of the backend-provided `detail` field. Returns
 * `undefined` when the body is not JSON or when `detail` is missing — the
 * caller still has the HTTP status code for the rendered error copy.
 */
async function tryParseDetail(res: Response): Promise<string | undefined> {
  try {
    const clone = res.clone();
    const json = (await clone.json()) as unknown;
    if (
      json !== null &&
      typeof json === "object" &&
      "detail" in json &&
      typeof (json as { detail?: unknown }).detail === "string"
    ) {
      return (json as { detail: string }).detail;
    }
    return undefined;
  } catch {
    return undefined;
  }
}

/**
 * Translate a caught value into the final assistant-node terminal state.
 * Called from the single `catch` in `driveStream`.
 *
 * Routing rules (Req 4.1–4.9):
 *   - `SseError` → `state = "error"` with the classified meta.
 *   - Signal aborted + NOT watchdog-timed-out → `state = "paused"`
 *     (user-initiated `pause()`).
 *   - Signal aborted + watchdog timed out → `state = "error"` with kind
 *     `"network"`.
 *   - Anything else → `classifyFetchError(err)` ("network" or "server").
 */
function writeTerminalState(
  assistantNodeId: string,
  err: unknown,
  context: { aborted: boolean; watchdogTimedOut: boolean },
): void {
  const store = useWorkspaceStore.getState();
  const current = store.nodesById[assistantNodeId];
  if (!current) return;

  if (err instanceof SseError) {
    store.updateNode(assistantNodeId, {
      state: "error",
      metadata: mergeErrorMeta(current.metadata, err.toMeta()),
    });
    return;
  }

  if (context.aborted && !context.watchdogTimedOut) {
    // User pressed pause. Req 4.7.
    store.updateNode(assistantNodeId, { state: "paused" });
    return;
  }

  if (context.aborted && context.watchdogTimedOut) {
    const meta: ConversationErrorMeta = {
      kind: "network",
      detail: err instanceof Error ? err.message : undefined,
      happened_at: new Date().toISOString(),
    };
    store.updateNode(assistantNodeId, {
      state: "error",
      metadata: mergeErrorMeta(current.metadata, meta),
    });
    return;
  }

  const kind = classifyFetchError(err);
  const meta: ConversationErrorMeta = {
    kind,
    detail: err instanceof Error ? err.message : undefined,
    happened_at: new Date().toISOString(),
  };
  store.updateNode(assistantNodeId, {
    state: "error",
    metadata: mergeErrorMeta(current.metadata, meta),
  });
}

/**
 * Locate the most recent user node before `targetNodeId` in `activePath`.
 * Mirrors `lib/activePathQueries.ts#findPrevUser` but is re-declared locally
 * so the hook does not trigger a circular import in environments that
 * resolve `lib/activePathQueries` through the barrel.
 *
 * Keeping the duplication tight (<= 10 lines) is cheaper than wiring a
 * module boundary just for this helper; if the surface grows we'll promote
 * this into `lib/activePathQueries` and import it.
 */
function findPrevUserInternal(
  activePath: ConversationNode[],
  targetNodeId: string,
): ConversationNode | undefined {
  const targetIndex = activePath.findIndex((node) => node.id === targetNodeId);
  if (targetIndex <= 0) return undefined;
  for (let i = targetIndex - 1; i >= 0; i -= 1) {
    const candidate = activePath[i];
    if (candidate.role === "user") return candidate;
  }
  return undefined;
}

function serializeMessages(nodes: ConversationNode[]): AgentChatStreamMessage[] {
  return nodes.map((node) => ({
    id: node.id,
    parent_id: node.parent_id,
    children_ids: node.children_ids,
    role: node.role,
    content: node.content,
    state: node.state,
    run_id: node.run_id,
    metadata: { ...node.metadata },
    tool_calls: node.tool_calls,
    artifacts: node.artifacts.map((artifact) => ({ ...artifact })),
    created_at: node.created_at,
  }));
}
