/**
 * Context max tokens primitives (v4 / Req 5, Property P23).
 *
 * Pure helpers + localStorage IO wrappers that keep the UI-side token
 * budget clamped into `[CONTEXT_MAX_TOKENS_MIN, CONTEXT_MAX_TOKENS_MAX]`
 * on the `CONTEXT_MAX_TOKENS_STEP` grid. No DOM imports here; DOM-side
 * writes are best-effort via `window.localStorage`.
 */

export const CONTEXT_MAX_TOKENS_MIN = 2000;
export const CONTEXT_MAX_TOKENS_MAX = 200_000;
export const CONTEXT_MAX_TOKENS_STEP = 1000;

/**
 * Initial UI value shown to users. This is intentionally NOT rounded to
 * `CONTEXT_MAX_TOKENS_STEP` — v3 displayed 8192 and we preserve that
 * observability until the user touches the slider. `clampContextMaxTokens`
 * only kicks in when the user-supplied value is written back (Req 5.1).
 */
export const CONTEXT_MAX_TOKENS_DEFAULT = 8192;

/**
 * Clamp `value` into `[MIN, MAX]` and round it to the nearest
 * `STEP` multiple. TOTAL — never throws.
 *
 * Non-numeric / NaN / ±Infinity inputs collapse to
 * `CONTEXT_MAX_TOKENS_DEFAULT`, which itself is then rounded to the
 * nearest step (→ 8000) so the idempotence property holds.
 *
 * Invariants (verified by Property P23):
 *   - `CONTEXT_MAX_TOKENS_MIN ≤ r ≤ CONTEXT_MAX_TOKENS_MAX`
 *   - `r % CONTEXT_MAX_TOKENS_STEP === 0`
 *   - `clampContextMaxTokens(clampContextMaxTokens(x)) === clampContextMaxTokens(x)`
 */
export function clampContextMaxTokens(value: unknown): number {
  const raw =
    typeof value === "number" && Number.isFinite(value)
      ? value
      : CONTEXT_MAX_TOKENS_DEFAULT;
  const bounded = Math.min(
    Math.max(raw, CONTEXT_MAX_TOKENS_MIN),
    CONTEXT_MAX_TOKENS_MAX,
  );
  const rounded =
    Math.round(bounded / CONTEXT_MAX_TOKENS_STEP) * CONTEXT_MAX_TOKENS_STEP;
  return Math.min(
    Math.max(rounded, CONTEXT_MAX_TOKENS_MIN),
    CONTEXT_MAX_TOKENS_MAX,
  );
}

/**
 * Ratio of used tokens vs. the configured limit, clamped to `[0, 1]`.
 * Returns `0` when the limit is zero / non-finite to avoid division by
 * zero and NaN propagation into styles.
 */
export function computeUsageRatio(current: number, limit: number): number {
  if (!Number.isFinite(limit) || limit <= 0) return 0;
  if (!Number.isFinite(current) || current < 0) return 0;
  return Math.max(0, Math.min(1, current / limit));
}

// ---------------------------------------------------------------------------
// localStorage persistence
// ---------------------------------------------------------------------------

/**
 * Storage key template. Namespaced under `harness.workspace.v4.` so this
 * entry is independent from the v3 `.conversations` snapshot and no
 * migration is needed.
 */
export function contextMaxTokensStorageKey(agentId: string): string {
  return `harness.workspace.v4.${agentId}.contextMaxTokens`;
}

/**
 * Once a write fails (quota, disabled storage, ...), stop trying. Further
 * attempts would only emit identical warnings. Module-local; one tab == one
 * process.
 */
let skipWrites = false;

function hasLocalStorage(): boolean {
  return typeof localStorage !== "undefined";
}

/**
 * Best-effort read. Returns `null` when no value is stored, when storage
 * is unavailable, or when the stored value fails to parse as a finite
 * number. Valid stored values are re-clamped so stale / out-of-range
 * entries surface as defaults rather than crashing the slider.
 */
export function readContextMaxTokens(agentId: string): number | null {
  if (!hasLocalStorage()) return null;
  let raw: string | null;
  try {
    raw = window.localStorage.getItem(contextMaxTokensStorageKey(agentId));
  } catch {
    return null;
  }
  if (raw === null) return null;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return null;
  return clampContextMaxTokens(parsed);
}

/**
 * Best-effort write. Returns `true` on success, `false` on any failure
 * (quota, disabled storage, etc.); never throws. Subsequent writes are
 * skipped after the first failure to conserve cycles.
 */
export function saveContextMaxTokens(agentId: string, value: number): boolean {
  if (skipWrites) return false;
  if (!hasLocalStorage()) return false;
  try {
    window.localStorage.setItem(
      contextMaxTokensStorageKey(agentId),
      String(clampContextMaxTokens(value)),
    );
    return true;
  } catch (err) {
    skipWrites = true;
    // eslint-disable-next-line no-console
    console.warn("[workspace] contextMaxTokens persistence disabled", err);
    return false;
  }
}
