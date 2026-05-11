// Feature: agent-workspace-chat-v4-refine, Property P20/P21/P22
import { describe, expect, it } from "vitest";
import fc from "fast-check";

import {
  AUTO_FOLLOW_BREAK_THRESHOLD_PX,
  reduceAutoFollow,
  type AutoFollowState,
} from "../lib/autoScrollFollow";

const stateArb = fc.record({
  autoFollow: fc.boolean(),
  showJumpButton: fc.boolean(),
}) as fc.Arbitrary<AutoFollowState>;

/**
 * P20 — user_submit always snaps to the bottom and enables Auto_Follow,
 * regardless of prior state. Validates Req 2.2, 12.1.
 */
describe("Property P20: Auto-follow user_submit snap", () => {
  it("returns {autoFollow:true, shouldSnapToBottom:true, showJumpButton:false} for any prior state", () => {
    fc.assert(
      fc.property(stateArb, (state) => {
        const decision = reduceAutoFollow(state, { type: "user_submit" });
        expect(decision.autoFollow).toBe(true);
        expect(decision.shouldSnapToBottom).toBe(true);
        expect(decision.showJumpButton).toBe(false);
      }),
      { numRuns: 200 },
    );
  });
});

/**
 * P21 — assistant_delta is gated by Auto_Follow. Validates Req 2.3, 2.4, 12.2.
 */
describe("Property P21: Auto-follow assistant_delta gated", () => {
  it("autoFollow=true → snap=true", () => {
    fc.assert(
      fc.property(stateArb, (state) => {
        const prev = { ...state, autoFollow: true };
        const decision = reduceAutoFollow(prev, { type: "assistant_delta" });
        expect(decision.autoFollow).toBe(true);
        expect(decision.shouldSnapToBottom).toBe(true);
        expect(decision.showJumpButton).toBe(false);
      }),
      { numRuns: 200 },
    );
  });

  it("autoFollow=false → no snap, state preserved", () => {
    fc.assert(
      fc.property(stateArb, (state) => {
        const prev = { ...state, autoFollow: false };
        const decision = reduceAutoFollow(prev, { type: "assistant_delta" });
        expect(decision.autoFollow).toBe(false);
        expect(decision.shouldSnapToBottom).toBe(false);
        expect(decision.showJumpButton).toBe(prev.showJumpButton);
      }),
      { numRuns: 200 },
    );
  });
});

/**
 * P22 — user_scroll_up respects the 200 px threshold, TOTAL over any
 * distance value (including NaN / ±Infinity / negatives). Validates Req
 * 2.5, 2.6, 12.3.
 */
describe("Property P22: Auto-follow user_scroll_up threshold", () => {
  const distanceArb: fc.Arbitrary<number> = fc.oneof(
    fc.integer({ min: -10_000, max: 10_000 }),
    fc.double(),
    fc.constantFrom<number>(
      Number.NaN,
      Number.POSITIVE_INFINITY,
      Number.NEGATIVE_INFINITY,
    ),
  );

  it("distance > threshold → break autoFollow and show jump button", () => {
    fc.assert(
      fc.property(
        stateArb,
        fc.integer({ min: AUTO_FOLLOW_BREAK_THRESHOLD_PX + 1, max: 100_000 }),
        (state, distance) => {
          const decision = reduceAutoFollow(state, {
            type: "user_scroll_up",
            distanceToBottomPx: distance,
          });
          expect(decision.autoFollow).toBe(false);
          expect(decision.shouldSnapToBottom).toBe(false);
          expect(decision.showJumpButton).toBe(true);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("distance ≤ threshold → state preserved, no jump button", () => {
    fc.assert(
      fc.property(
        stateArb,
        fc.integer({ min: -1000, max: AUTO_FOLLOW_BREAK_THRESHOLD_PX }),
        (state, distance) => {
          const decision = reduceAutoFollow(state, {
            type: "user_scroll_up",
            distanceToBottomPx: distance,
          });
          expect(decision.autoFollow).toBe(state.autoFollow);
          expect(decision.shouldSnapToBottom).toBe(false);
          expect(decision.showJumpButton).toBe(false);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("arbitrary distance (including NaN / ±Infinity) never throws", () => {
    fc.assert(
      fc.property(stateArb, distanceArb, (state, distance) => {
        expect(() =>
          reduceAutoFollow(state, {
            type: "user_scroll_up",
            distanceToBottomPx: distance,
          }),
        ).not.toThrow();
      }),
      { numRuns: 200 },
    );
  });
});
