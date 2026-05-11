export type ScrollState = {
  scrollTop: number;
  clientHeight: number;
  scrollHeight: number;
};

/**
 * Returns true iff the scroll viewport is within 50 pixels of the bottom.
 *
 * Pure function. Total: for any numeric input it returns a boolean without
 * throwing. NaN propagates through arithmetic so the comparison yields `false`,
 * which matches the intuition "do not auto-scroll on invalid state".
 *
 * Callers (e.g. ChatMessageList) are responsible for supplying meaningful
 * values (`0 <= scrollTop <= scrollHeight`, `clientHeight <= scrollHeight`);
 * this helper performs no defensive coercion.
 *
 * Property 2 (agent-workspace-chat-refine):
 *   shouldAutoScroll({ scrollTop, clientHeight, scrollHeight }) === true
 *     iff scrollHeight - scrollTop - clientHeight <= 50
 *
 * Requirements: 1.8 (auto-scroll when near bottom), 1.10 (preserve user
 * scroll when away from bottom).
 */
export function shouldAutoScroll(state: ScrollState): boolean {
  return state.scrollHeight - state.scrollTop - state.clientHeight <= 50;
}
