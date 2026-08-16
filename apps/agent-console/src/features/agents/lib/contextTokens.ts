/**
 * Context max tokens primitives (v4 / Req 5, Property P23).
 *
 * Pure helpers + localStorage IO wrappers that keep the UI-side token
 * token budget clamped into `[CONTEXT_MAX_TOKENS_MIN, CONTEXT_MAX_TOKENS_MAX]`
 * on the `CONTEXT_MAX_TOKENS_STEP` grid. No DOM imports here; DOM-side
 * writes are best-effort via `window.localStorage`.
 */

import { getWorkspaceScopeId, legacyWorkspaceStorageKey, workspaceScopedStorageKey } from "./workspaceScope";
import { getWorkspacePersistenceStorage } from "../../../lib/workspace-persistence-storage";

export const CONTEXT_MAX_TOKENS_MIN = 16_000;
export const CONTEXT_MAX_TOKENS_MAX = 1_000_000;
export const CONTEXT_MAX_TOKENS_STEP = 1_000;

/**
 * Default context window size in tokens. 258k mirrors the compact context
 * usage affordance expected in the workspace.
 */
export const CONTEXT_MAX_TOKENS_DEFAULT = 258_000;
export const AUTO_COMPRESSION_RATIO_DEFAULT = 0.8;
export const AUTO_COMPRESSION_RATIO_MIN = 0.5;
export const AUTO_COMPRESSION_RATIO_MAX = 0.95;
export const AUTO_COMPRESSION_RATIO_STEP = 0.05;

/**
 * Clamp `value` into `[MIN, MAX]` and round it to the nearest
 * `STEP` multiple. TOTAL — never throws.
 *
 * Non-numeric / NaN / ±Infinity inputs collapse to
 * `CONTEXT_MAX_TOKENS_DEFAULT`, which itself is then rounded to the
 * nearest step so the idempotence property holds.
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

export function clampAutoCompressionRatio(value: unknown): number {
  const raw =
    typeof value === "number" && Number.isFinite(value)
      ? value
      : AUTO_COMPRESSION_RATIO_DEFAULT;
  const bounded = Math.min(
    Math.max(raw, AUTO_COMPRESSION_RATIO_MIN),
    AUTO_COMPRESSION_RATIO_MAX,
  );
  const rounded =
    Math.round(bounded / AUTO_COMPRESSION_RATIO_STEP) * AUTO_COMPRESSION_RATIO_STEP;
  return Number(Math.min(Math.max(rounded, AUTO_COMPRESSION_RATIO_MIN), AUTO_COMPRESSION_RATIO_MAX).toFixed(2));
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
  return workspaceScopedStorageKey(getWorkspaceScopeId(), "v5", agentId, "contextMaxTokens");
}

export function autoCompressionRatioStorageKey(agentId: string): string {
  return workspaceScopedStorageKey(getWorkspaceScopeId(), "v5", agentId, "autoCompressionRatio");
}

function legacyContextMaxTokensStorageKey(agentId: string): string {
  return legacyWorkspaceStorageKey("v5", agentId, "contextMaxTokens");
}

function legacyAutoCompressionRatioStorageKey(agentId: string): string {
  return legacyWorkspaceStorageKey("v5", agentId, "autoCompressionRatio");
}

/**
 * Once a write fails (quota, disabled storage, ...), stop trying. Further
 * attempts would only emit identical warnings. Module-local; one tab == one
 * process.
 */
let skipWrites = false;

/**
 * Best-effort read. Returns `null` when no value is stored, when storage
 * is unavailable, or when the stored value fails to parse as a finite
 * number. Valid stored values are re-clamped so stale / out-of-range
 * entries surface as defaults rather than crashing the slider.
 */
export function readContextMaxTokens(agentId: string): number | null {
  const storage = getWorkspacePersistenceStorage();
  if (!storage) return null;
  let raw: string | null;
  let usedLegacyKey = false;
  try {
    raw = storage.getItem(contextMaxTokensStorageKey(agentId));
    if (raw === null) {
      raw = storage.getItem(legacyContextMaxTokensStorageKey(agentId));
      usedLegacyKey = raw !== null;
    }
  } catch {
    return null;
  }
  if (raw === null) return null;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return null;
  // v4.1 compatibility: previous builds persisted this value in KB on a
  // 16..1024 scale. Treat those values as legacy KB and migrate to tokens.
  const normalized = parsed <= 1024 ? parsed * 1000 : parsed;
  if (usedLegacyKey) {
    try {
      storage.setItem(contextMaxTokensStorageKey(agentId), String(clampContextMaxTokens(normalized)));
      storage.removeItem(legacyContextMaxTokensStorageKey(agentId));
    } catch {
      /* ignore migration failures */
    }
  }
  return clampContextMaxTokens(normalized);
}

/**
 * Best-effort write. Returns `true` on success, `false` on any failure
 * (quota, disabled storage, etc.); never throws. Subsequent writes are
 * skipped after the first failure to conserve cycles.
 */
export function saveContextMaxTokens(agentId: string, value: number): boolean {
  if (skipWrites) return false;
  const storage = getWorkspacePersistenceStorage();
  if (!storage) return false;
  try {
    storage.setItem(
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

export function readAutoCompressionRatio(agentId: string): number | null {
  const storage = getWorkspacePersistenceStorage();
  if (!storage) return null;
  let raw: string | null;
  let usedLegacyKey = false;
  try {
    raw = storage.getItem(autoCompressionRatioStorageKey(agentId));
    if (raw === null) {
      raw = storage.getItem(legacyAutoCompressionRatioStorageKey(agentId));
      usedLegacyKey = raw !== null;
    }
  } catch {
    return null;
  }
  if (raw === null) return null;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return null;
  if (usedLegacyKey) {
    try {
      storage.setItem(autoCompressionRatioStorageKey(agentId), String(clampAutoCompressionRatio(parsed)));
      storage.removeItem(legacyAutoCompressionRatioStorageKey(agentId));
    } catch {
      /* ignore migration failures */
    }
  }
  return clampAutoCompressionRatio(parsed);
}

export function saveAutoCompressionRatio(agentId: string, value: number): boolean {
  if (skipWrites) return false;
  const storage = getWorkspacePersistenceStorage();
  if (!storage) return false;
  try {
    storage.setItem(
      autoCompressionRatioStorageKey(agentId),
      String(clampAutoCompressionRatio(value)),
    );
    return true;
  } catch (err) {
    skipWrites = true;
    console.warn("[workspace] autoCompressionRatio persistence disabled", err);
    return false;
  }
}
