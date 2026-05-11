/**
 * Composer autogrow primitives (v4 / Req 1, Property P18).
 *
 * v4 tightens the minimum height from v3's 40 px to 24 px so the composer
 * starts as a single-line input (matches ChatGPT / Claude Code). The max
 * height remains 200 px.
 *
 * The module stays DOM-free so the clamp can be property-tested and reused
 * without rendering.
 */

/** v4 minimum height; `padding-y (2 + 2) + line-height 20 = 24`. */
export const COMPOSER_MIN_HEIGHT_V4 = 24;

/** v3 / v4 shared maximum; overflow turns on when content exceeds this. */
export const COMPOSER_MAX_HEIGHT = 200;

/**
 * Compatibility alias. Existing call sites and Property P18 import
 * `MIN_COMPOSER_HEIGHT`; keeping the name pointing at the v4 value means
 * no consumer needs to be touched. Range becomes [24, 200] automatically.
 */
export const MIN_COMPOSER_HEIGHT = COMPOSER_MIN_HEIGHT_V4;
export const MAX_COMPOSER_HEIGHT = COMPOSER_MAX_HEIGHT;

/**
 * Clamp a raw `scrollHeight` value into the allowed composer height window.
 *
 * Rules (TOTAL — never throws):
 *   - Returns `MIN_COMPOSER_HEIGHT` for NaN / non-finite / non-number
 *     inputs.
 *   - Returns `MIN_COMPOSER_HEIGHT` when `scrollHeight < MIN_COMPOSER_HEIGHT`.
 *   - Returns `MAX_COMPOSER_HEIGHT` when `scrollHeight > MAX_COMPOSER_HEIGHT`.
 *   - Otherwise returns `scrollHeight` unchanged.
 */
export function clampAutogrowHeight(scrollHeight: number): number {
  if (typeof scrollHeight !== "number" || !Number.isFinite(scrollHeight)) {
    return MIN_COMPOSER_HEIGHT;
  }
  if (scrollHeight < MIN_COMPOSER_HEIGHT) return MIN_COMPOSER_HEIGHT;
  if (scrollHeight > MAX_COMPOSER_HEIGHT) return MAX_COMPOSER_HEIGHT;
  return scrollHeight;
}
