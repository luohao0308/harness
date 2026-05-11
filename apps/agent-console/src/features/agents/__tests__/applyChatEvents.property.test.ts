// Feature: agent-workspace-chat-refine, Property 5: Chat event reducer invariants
import { describe, it, expect } from "vitest";
import fc from "fast-check";

import {
  applyChatEvents,
  type AssistantNodeSnapshot,
  type ChatReducerEvent,
} from "../lib/chatEventReducer";
import type { ConversationErrorMeta } from "../lib/sseErrors";

/**
 * Validates: Requirements 3.3, 3.5, 3.6, 4.7, 4.8, 4.9, 11.2
 *
 * Property 5 — for any ChatReducerEvent sequence applied to a streaming
 * assistant snapshot:
 *   (a) the reducer never throws (total);
 *   (b) the terminal state ∈ {streaming, done, paused, error};
 *   (c) after leaving `streaming`, subsequent events do not revert the state;
 *   (d) error precedence: if any error event is present in the batch,
 *       `abort` is suppressed and the terminal state is `error`, never
 *       `paused`;
 *   (e) every error event leaves metadata.error populated.
 */

const TERMINAL_STATES = new Set(["streaming", "done", "paused", "error"]);

const kindGen: fc.Arbitrary<ConversationErrorMeta["kind"]> = fc.constantFrom(
  "http",
  "network",
  "non_sse",
  "stream_closed",
  "auth",
  "not_found",
  "server",
);

const errorMetaGen: fc.Arbitrary<ConversationErrorMeta> = fc.record(
  {
    kind: kindGen,
    status: fc.option(fc.integer({ min: 100, max: 599 }), { nil: undefined }),
    detail: fc.option(fc.string({ maxLength: 24 }), { nil: undefined }),
    body_preview: fc.option(fc.string({ maxLength: 32 }), { nil: undefined }),
    happened_at: fc.constant(new Date(0).toISOString()),
  },
  { requiredKeys: ["kind", "happened_at"] },
);

const eventGen: fc.Arbitrary<ChatReducerEvent> = fc.oneof(
  fc
    .record({ content: fc.string({ maxLength: 8 }) })
    .map<ChatReducerEvent>((r) => ({ type: "delta", content: r.content })),
  fc
    .record({ content: fc.string({ maxLength: 8 }) })
    .map<ChatReducerEvent>((r) => ({ type: "think_delta", content: r.content })),
  fc
    .record({
      run_id: fc.string({ minLength: 1, maxLength: 12 }),
      step_count: fc.integer({ min: 0, max: 4 }),
      message: fc.string({ maxLength: 8 }),
    })
    .map<ChatReducerEvent>((r) => ({
      type: "run_created",
      run_id: r.run_id,
      status: "running",
      step_count: r.step_count,
      message: r.message,
    })),
  fc
    .record({
      input_tokens: fc.integer({ min: 0, max: 1024 }),
      output_tokens: fc.integer({ min: 0, max: 1024 }),
      cost_usd: fc.option(fc.string({ maxLength: 6 }), { nil: null }),
      cost_unavailable: fc.boolean(),
      ttfb_ms: fc.integer({ min: 0, max: 5000 }),
      duration_ms: fc.integer({ min: 0, max: 60000 }),
      model_call_id: fc.option(fc.string({ maxLength: 8 }), { nil: null }),
    })
    .map<ChatReducerEvent>((r) => ({
      type: "usage",
      input_tokens: r.input_tokens,
      output_tokens: r.output_tokens,
      cost_usd: r.cost_usd,
      cost_unavailable: r.cost_unavailable,
      ttfb_ms: r.ttfb_ms,
      duration_ms: r.duration_ms,
      model_call_id: r.model_call_id,
    })),
  fc
    .record({
      run_id: fc.string({ minLength: 1, maxLength: 12 }),
      step_count: fc.integer({ min: 0, max: 4 }),
      message: fc.string({ maxLength: 8 }),
    })
    .map<ChatReducerEvent>((r) => ({
      type: "done",
      run_id: r.run_id,
      status: "succeeded",
      step_count: r.step_count,
      message: r.message,
    })),
  fc.constant<ChatReducerEvent>({ type: "abort" }),
  errorMetaGen.map<ChatReducerEvent>((meta) => ({ type: "http_error", meta })),
  errorMetaGen.map<ChatReducerEvent>((meta) => ({ type: "network_error", meta })),
  errorMetaGen.map<ChatReducerEvent>((meta) => ({ type: "non_sse", meta })),
  errorMetaGen.map<ChatReducerEvent>((meta) => ({ type: "stream_closed", meta })),
  fc
    .record({ message: fc.string({ maxLength: 24 }) })
    .map<ChatReducerEvent>((r) => ({ type: "error", message: r.message })),
);

function seed(): AssistantNodeSnapshot {
  return {
    role: "assistant",
    content: "",
    state: "streaming",
    metadata: { workspace_mode: "chat" },
    tool_calls: [],
    artifacts: [],
    started_at_ms: 0,
    first_delta_at_ms: null,
  };
}

function isTerminalErrorEvent(event: ChatReducerEvent): boolean {
  return (
    event.type === "error" ||
    event.type === "http_error" ||
    event.type === "network_error" ||
    event.type === "non_sse" ||
    event.type === "stream_closed"
  );
}

describe("Property 5: Chat event reducer invariants", () => {
  it("reducer is total over arbitrary event sequences", () => {
    fc.assert(
      fc.property(fc.array(eventGen, { maxLength: 12 }), (events) => {
        expect(() => applyChatEvents(seed(), events)).not.toThrow();
      }),
      { numRuns: 200 },
    );
  });

  it("terminal state is always in {streaming, done, paused, error}", () => {
    fc.assert(
      fc.property(fc.array(eventGen, { maxLength: 12 }), (events) => {
        const final = applyChatEvents(seed(), events);
        expect(TERMINAL_STATES.has(final.state)).toBe(true);
      }),
      { numRuns: 200 },
    );
  });

  it("once a terminal state is entered, further events do not revert it", () => {
    fc.assert(
      fc.property(
        fc.array(eventGen, { minLength: 1, maxLength: 12 }),
        fc.array(eventGen, { maxLength: 12 }),
        (firstBatch, secondBatch) => {
          const intermediate = applyChatEvents(seed(), firstBatch);
          if (intermediate.state === "streaming") {
            // No terminal state yet; invariant is vacuous in this branch.
            return;
          }
          const final = applyChatEvents(intermediate, secondBatch);
          // Content / metadata / state must all remain as the intermediate's.
          expect(final.state).toBe(intermediate.state);
          expect(final.content).toBe(intermediate.content);
          expect(final.metadata).toEqual(intermediate.metadata);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("error precedence: error events trump abort in the same batch", () => {
    fc.assert(
      fc.property(fc.array(eventGen, { maxLength: 12 }), (events) => {
        if (!events.some(isTerminalErrorEvent)) return;
        // Ensure at least one abort is present somewhere in the batch.
        const withAbort: ChatReducerEvent[] = [...events, { type: "abort" }];
        const final = applyChatEvents(seed(), withAbort);
        expect(final.state).not.toBe("paused");
      }),
      { numRuns: 200 },
    );
  });

  it("every error-producing batch populates metadata.error", () => {
    fc.assert(
      fc.property(fc.array(eventGen, { maxLength: 12 }), (events) => {
        const final = applyChatEvents(seed(), events);
        if (final.state !== "error") return;
        expect(final.metadata.error).toBeDefined();
      }),
      { numRuns: 200 },
    );
  });
});
