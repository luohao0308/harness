/**
 * Auto-scroll follow primitives (v4 / Req 2, Properties P19–P22).
 *
 * v4 rewrites the previous v3 implementation into an explicit event-driven
 * state machine. The decision logic lives in a single pure function so it
 * can be property-tested exhaustively and reused by any caller (React or
 * otherwise). No DOM imports.
 *
 * Transition table (design.md §Auto-follow state-machine architecture):
 *
 *   user_submit                            → autoFollow=true,  snap=true,  showJump=false
 *   assistant_delta            (follow)    → autoFollow=true,  snap=true,  showJump=false
 *   assistant_delta            (!follow)   → autoFollow=false, snap=false, showJump=prev
 *   user_scroll_up (distance > 200)        → autoFollow=false, snap=false, showJump=true
 *   user_scroll_up (distance ≤ 200 / NaN)  → autoFollow=prev,  snap=false, showJump=false
 *   user_scroll_to_bottom                  → autoFollow=true,  snap=false, showJump=false
 *   jump_to_latest_click                   → autoFollow=true,  snap=true,  showJump=false
 *
 * TOTAL: `reduceAutoFollow` is closed over the discriminated union of
 * events; unknown event shapes fall into the default branch and return
 * state unchanged. No exceptions.
 *
 * v3 compatibility exports are retained (`computeFollowDecision`,
 * `contentSum`, `isCloseToBottom`, `JUMP_TO_LATEST_THRESHOLD_PX`) so
 * Property P19 keeps passing without touching its test file.
 */

import type { ConversationNode } from "../../../stores/workspaceStore";

// ---------------------------------------------------------------------------
// v4 constants
// ---------------------------------------------------------------------------

/**
 * Distance (in pixels) from the bottom of the scroll container above which
 * an upward user scroll breaks `Auto_Follow` and surfaces the
 * `Jump_To_Latest_Button` (Req 2.5).
 */
export const AUTO_FOLLOW_BREAK_THRESHOLD_PX = 200;

/**
 * Distance (in pixels) within which the scroll container is considered
 * "at the bottom" for the purposes of `user_scroll_to_bottom` (Req 2.7).
 */
export const SNAP_TOLERANCE_PX = 4;

/**
 * v3-era alias. Kept so downstream callers and Property P19 can continue
 * importing the old name with identical semantics (= 200 px).
 */
export const JUMP_TO_LATEST_THRESHOLD_PX = AUTO_FOLLOW_BREAK_THRESHOLD_PX;

// ---------------------------------------------------------------------------
// v4 types
// ---------------------------------------------------------------------------

export type AutoFollowState = {
  autoFollow: boolean;
  showJumpButton: boolean;
};

export type AutoFollowEvent =
  | { type: "user_submit" }
  | { type: "assistant_delta" }
  | { type: "user_scroll_up"; distanceToBottomPx: number }
  | { type: "user_scroll_to_bottom"; distanceToBottomPx: number }
  | { type: "jump_to_latest_click" };

export type AutoFollowDecision = AutoFollowState & {
  shouldSnapToBottom: boolean;
};

// ---------------------------------------------------------------------------
// v4 reducer
// ---------------------------------------------------------------------------

/**
 * TOTAL pure reducer. Accepts any combination of prior state and event and
 * returns a fully-specified decision. Never throws, never reads DOM.
 *
 * When the `distanceToBottomPx` carried by a scroll event is `NaN` /
 * non-finite, we treat it as "within the break threshold" to avoid
 * accidental autoFollow breaks (Req 2.5 defensive handling).
 */
export function reduceAutoFollow(
  state: AutoFollowState,
  event: AutoFollowEvent,
): AutoFollowDecision {
  switch (event.type) {
    case "user_submit":
      return { autoFollow: true, shouldSnapToBottom: true, showJumpButton: false };

    case "assistant_delta":
      if (state.autoFollow) {
        return { autoFollow: true, shouldSnapToBottom: true, showJumpButton: false };
      }
      return {
        autoFollow: false,
        shouldSnapToBottom: false,
        showJumpButton: state.showJumpButton,
      };

    case "user_scroll_up": {
      const distance = event.distanceToBottomPx;
      const crossed =
        typeof distance === "number" &&
        Number.isFinite(distance) &&
        distance > AUTO_FOLLOW_BREAK_THRESHOLD_PX;
      if (crossed) {
        return { autoFollow: false, shouldSnapToBottom: false, showJumpButton: true };
      }
      return {
        autoFollow: state.autoFollow,
        shouldSnapToBottom: false,
        showJumpButton: false,
      };
    }

    case "user_scroll_to_bottom":
      return { autoFollow: true, shouldSnapToBottom: false, showJumpButton: false };

    case "jump_to_latest_click":
      return { autoFollow: true, shouldSnapToBottom: true, showJumpButton: false };

    default: {
      // Exhaustiveness guard — runtime defensive fallback for unknown
      // events (TypeScript union exhaustion already covers compile time).
      const _exhaustive: never = event;
      void _exhaustive;
      return { ...state, shouldSnapToBottom: false };
    }
  }
}

// ---------------------------------------------------------------------------
// v3 compatibility layer
// ---------------------------------------------------------------------------

export type FollowDecision = {
  shouldScroll: boolean;
};

export type FollowDecisionInput = {
  autoFollow: boolean;
  prevContentSum: number;
  nextContentSum: number;
};

/**
 * v3 decision helper retained for backward compatibility (Property P19).
 * Gated purely by `autoFollow`; returns `shouldScroll: true` when
 * `autoFollow === true` regardless of content deltas — the scroll-to-bottom
 * write is an idempotent no-op when the container is already at the bottom.
 */
export function computeFollowDecision(
  input: FollowDecisionInput,
): FollowDecision {
  if (input.autoFollow === false) return { shouldScroll: false };
  return { shouldScroll: true };
}

/**
 * Sum of `content.length` across every node in `activePath`. Used as a
 * React effect dependency so every token delta / branch switch retriggers
 * the layout effect. Empty paths yield `0`.
 */
export function contentSum(activePath: ConversationNode[]): number {
  let total = 0;
  for (const node of activePath) {
    total += node.content.length;
  }
  return total;
}

/**
 * v3 helper — `true` iff the scroll container is within
 * `JUMP_TO_LATEST_THRESHOLD_PX` of the bottom. Preserves the 3-argument
 * signature expected by Property P19's existing test cases.
 */
export function isCloseToBottom(
  scrollHeight: number,
  scrollTop: number,
  clientHeight: number,
): boolean {
  const remaining = scrollHeight - scrollTop - clientHeight;
  return remaining <= JUMP_TO_LATEST_THRESHOLD_PX;
}
