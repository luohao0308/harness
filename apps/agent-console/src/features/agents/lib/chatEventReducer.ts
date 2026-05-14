/**
 * Pure state-machine reducer for the Workspace chat stream.
 *
 * Implements:
 *   - Property 4 — Initial node structure (`planInitialNodes`)
 *   - Property 5 — Chat event reducer invariants (`applyChatEvents`)
 *
 * The reducer is **total**: for any well-typed input it returns an
 * `AssistantNodeSnapshot`. It never throws, never performs I/O, never calls
 * React / Zustand. Time-dependent logic is threaded through `options.now`
 * so the function stays deterministic under property testing; the single
 * concession is the `new Date().toISOString()` call used to stamp
 * `happened_at` on server-emitted `error` events (documented in design.md
 * §SSE Parsing → "Error routing").
 *
 * See `.kiro/specs/agent-workspace-chat-refine/design.md` §SSE Parsing and
 * §Error routing and `requirements.md` Req 3.1, 3.3–3.6, 3.8, 4.7, 4.8,
 * 4.9, 11.2 for the governing contracts.
 */

import type { AgentChatStreamEvent } from "../../tasks/api";
import type { ConversationArtifact, ConversationNode } from "../../../stores/workspaceStore";
import { mergeToolCallEvent } from "../streamEvents";
import type { ConversationErrorMeta } from "./sseErrors";
import type { WorkspaceMode } from "./types";

/**
 * Patches handed to `workspaceStore.appendNode`. We reuse `ConversationNode`'s
 * shape minus the fields the store generates (`id`, `children_ids`,
 * `created_at`).
 */
export type UserNodePatch = Omit<ConversationNode, "id" | "children_ids" | "created_at">;
export type AssistantNodePatch = Omit<ConversationNode, "id" | "children_ids" | "created_at">;

/**
 * Snapshot the reducer operates on. Carries the subset of `ConversationNode`
 * fields that `applyChatEvents` can mutate plus two reducer-internal time
 * anchors:
 *   - `started_at_ms` — host-provided reference time (usually the
 *     `performance.now()` value captured right before `fetch`).
 *   - `first_delta_at_ms` — `null` until the first `delta`/`think_delta`
 *     event arrives; afterwards, the absolute value (on the same clock as
 *     `started_at_ms`) when that event was seen. Used to back-fill a missing
 *     `usage.ttfb_ms`.
 */
export type AssistantNodeSnapshot = {
  role: "assistant";
  content: string;
  state: "streaming" | "done" | "paused" | "error";
  run_id?: string;
  metadata: ConversationNode["metadata"];
  tool_calls: ConversationNode["tool_calls"];
  artifacts: ConversationNode["artifacts"];
  started_at_ms: number;
  first_delta_at_ms: number | null;
};

/**
 * Events the reducer understands: every `AgentChatStreamEvent` plus four
 * client-synthesised error envelopes and a user-initiated `abort`. The
 * error envelopes reuse `ConversationErrorMeta` so the hook can classify
 * HTTP / network / non-SSE / stream-closed failures once and pass the
 * finished metadata straight to the reducer.
 */
export type ChatReducerEvent =
  | AgentChatStreamEvent
  | { type: "abort" }
  | { type: "http_error"; meta: ConversationErrorMeta }
  | { type: "network_error"; meta: ConversationErrorMeta }
  | { type: "non_sse"; meta: ConversationErrorMeta }
  | { type: "stream_closed"; meta: ConversationErrorMeta };

/**
 * Optional deterministic dependencies. `now` MUST return a time on the same
 * clock as `AssistantNodeSnapshot.started_at_ms`; the reducer only uses it
 * to mark `first_delta_at_ms`. Default is `() => 0`, which is fine for unit
 * tests that do not inspect the ttfb back-fill value.
 */
export type ApplyChatEventsOptions = {
  now?: () => number;
};

/**
 * Property 4 — plan the initial `[user, assistant]` patch pair for a new
 * chat turn. The reducer does not generate ids; the host (Zustand store)
 * wires `parent_id` / `children_ids` at `appendNode` time (see design.md
 * §useChatStream Hook → "Pre-flight").
 */
export function planInitialNodes(
  draft: string,
  mode: WorkspaceMode,
): [UserNodePatch, AssistantNodePatch] {
  const userPatch: UserNodePatch = {
    parent_id: null,
    role: "user",
    content: draft,
    state: "done",
    metadata: {},
    tool_calls: [],
    artifacts: [],
  };
  const assistantPatch: AssistantNodePatch = {
    parent_id: null,
    role: "assistant",
    content: "",
    state: "streaming",
    metadata: { workspace_mode: mode },
    tool_calls: [],
    artifacts: [],
  };
  return [userPatch, assistantPatch];
}

/**
 * Merge a `ConversationErrorMeta` into an existing node metadata record. The
 * new error fully replaces any previous one — errors are append-only from
 * the UI perspective, so only the most recent classification is kept.
 */
export function mergeErrorMeta(
  existing: ConversationNode["metadata"],
  next: ConversationErrorMeta,
): ConversationNode["metadata"] {
  return { ...existing, error: next };
}

/**
 * Property 5 — apply a sequence of events to an assistant snapshot.
 *
 * Invariants enforced here:
 *   1. Content order — `delta` and `think_delta` are appended in input
 *      order; `think_delta` is wrapped in `<think>…</think>`.
 *   2. Terminal uniqueness — the first event that moves the snapshot out
 *      of `streaming` is final; subsequent events are ignored.
 *   3. Usage metadata — `usage` persists token/cost/ttfb/duration fields
 *      onto `metadata`; `ttfb_ms === 0` is back-filled from
 *      `first_delta_at_ms - started_at_ms` when possible.
 *   4. Done seals the run — `done` sets `state = "done"` and stores
 *      `run_id`.
 *   5. Error precedence — if `events` contains any error-kind event,
 *      `abort` is suppressed so the terminal state is `"error"`, not
 *      `"paused"` (Req 4.8).
 *   6. No silent failure — every error event produces `state === "error"`
 *      plus a populated `metadata.error`.
 */
export function applyChatEvents(
  init: AssistantNodeSnapshot,
  events: ChatReducerEvent[],
  options?: ApplyChatEventsOptions,
): AssistantNodeSnapshot {
  const now = options?.now ?? (() => 0);

  // Pre-scan: when *any* error event is present, subsequent `abort` events
  // are suppressed so the terminal state resolves to `error` rather than
  // `paused`. This matches Property 5 clause 5 independent of event order.
  const hasError = events.some(isErrorEvent);

  let snap: AssistantNodeSnapshot = init;

  for (const event of events) {
    if (snap.state !== "streaming") {
      // Terminal state reached. Every subsequent event is ignored so the
      // reducer satisfies "terminal uniqueness" (Property 5 clause 2).
      break;
    }

    switch (event.type) {
      case "delta": {
        snap = appendContentAndMaybeMarkTtfb(snap, event.content, now);
        break;
      }
      case "think_delta": {
        snap = appendContentAndMaybeMarkTtfb(snap, `<think>${event.content}</think>`, now);
        break;
      }
      case "run_created": {
        snap = { ...snap, run_id: event.run_id };
        break;
      }
      case "tool_call_requested":
      case "tool_call_result": {
        snap = { ...snap, tool_calls: mergeToolCallEvent(snap.tool_calls, event) };
        break;
      }
      case "artifact_created": {
        const artifact: ConversationArtifact = {
          // Placeholder id — the hook layer overwrites it with the owning
          // node's id prefix before committing to the store.
          id: `artifact-${snap.artifacts.length}`,
          name: event.name,
          artifact_type: event.artifact_type,
          status: event.status,
          content: event.content,
          run_id: event.run_id,
        };
        snap = { ...snap, artifacts: [...snap.artifacts, artifact] };
        break;
      }
      case "usage": {
        const ttfbFromSnapshot =
          snap.first_delta_at_ms != null ? snap.first_delta_at_ms - snap.started_at_ms : 0;
        const ttfb = event.ttfb_ms === 0 ? ttfbFromSnapshot : event.ttfb_ms;
        snap = {
          ...snap,
          metadata: {
            ...snap.metadata,
            input_tokens: event.input_tokens,
            output_tokens: event.output_tokens,
            cost_usd: event.cost_usd,
            cost_unavailable: event.cost_unavailable,
            ttfb_ms: ttfb,
            duration_ms: event.duration_ms,
            model_call_id: event.model_call_id,
          },
        };
        break;
      }
      case "done": {
        snap = {
          ...snap,
          state: "done",
          run_id: event.run_id,
          metadata: {
            ...snap.metadata,
            knowledge_grounding: event.knowledge_grounding,
          },
        };
        break;
      }
      case "error": {
        // Server-emitted terminal error event (Req 4.9). Req 4.8 already
        // guarantees error-over-abort via the pre-scan; within a single
        // pass the `switch` arm below short-circuits once written.
        const meta: ConversationErrorMeta = {
          kind: "server",
          detail: event.message,
          happened_at: new Date().toISOString(),
        };
        snap = {
          ...snap,
          state: "error",
          metadata: mergeErrorMeta(snap.metadata, meta),
        };
        break;
      }
      case "http_error":
      case "network_error":
      case "non_sse":
      case "stream_closed": {
        snap = {
          ...snap,
          state: "error",
          metadata: mergeErrorMeta(snap.metadata, event.meta),
        };
        break;
      }
      case "abort": {
        if (hasError) {
          // Suppressed: a classified error is present in the batch and takes
          // precedence over the user's pause (Req 4.8 / Property 5 clause 5).
          break;
        }
        snap = { ...snap, state: "paused" };
        break;
      }
      default: {
        // Exhaustiveness guard — unreachable when `ChatReducerEvent` stays in
        // sync with `switch` arms above. `never` makes the compiler complain
        // if a new event variant is added without being handled here.
        const exhaustive: never = event;
        void exhaustive;
        break;
      }
    }
  }

  return snap;
}

function appendContentAndMaybeMarkTtfb(
  snap: AssistantNodeSnapshot,
  piece: string,
  now: () => number,
): AssistantNodeSnapshot {
  return {
    ...snap,
    content: snap.content + piece,
    first_delta_at_ms: snap.first_delta_at_ms ?? now(),
  };
}

function isErrorEvent(event: ChatReducerEvent): boolean {
  return (
    event.type === "error" ||
    event.type === "http_error" ||
    event.type === "network_error" ||
    event.type === "non_sse" ||
    event.type === "stream_closed"
  );
}
