/**
 * Context usage aggregation helpers for `ContextUsageBar` (Req 13.4 / 13.5).
 *
 * `computeContextUsage` sums the most recent `turns * 2` nodes of the active
 * path (one turn = user + assistant). Missing `input_tokens` / `output_tokens`
 * fields contribute 0; the function is TOTAL and never throws. The default
 * context window size falls back to 8192 tokens — Req 13.4 allows fallback
 * when `getModelSettings()` does not expose a per-model context limit.
 *
 * `readContextWindowLimit` is also TOTAL: it accepts `undefined` settings and
 * tolerates a `ModelSettings` shape that does not surface `context_window`.
 * The current `ModelSettings` type (see `features/tasks/api.ts`) does not
 * include `defaults.context_window` or `models[].context_window`, so this
 * helper always returns `DEFAULT_CONTEXT_WINDOW`. Req 13.4 allows fallback.
 */

import type { ConversationNode } from "../../../stores/workspaceStore";
import type { ModelSettings } from "../../tasks/api";

export type ContextUsage = {
  current: number;
  limit: number;
  /** Clamped to `[0, 1]`; `0` when `limit <= 0` to avoid division by zero. */
  ratio: number;
};

export const DEFAULT_CONTEXT_WINDOW = 8192;

/**
 * Sum `input_tokens + output_tokens` across the most recent `turns * 2`
 * nodes of `activePath`. Truncation is permissive — we do not require pairs
 * to be strictly user+assistant; the tail window is taken verbatim.
 *
 * v4 additive: `limitOverride` lets the caller wire
 * `useWorkspaceStore.contextMaxTokens` through so the usage denominator
 * reflects the user-tuned budget (Req 5.4). When absent or non-finite we
 * fall back to `DEFAULT_CONTEXT_WINDOW` (8192) — preserves v3 semantics.
 */
export function computeContextUsage(
  activePath: ConversationNode[],
  turns: number,
  limitOverride?: number,
): ContextUsage {
  const limit =
    typeof limitOverride === "number" &&
    Number.isFinite(limitOverride) &&
    limitOverride > 0
      ? limitOverride
      : DEFAULT_CONTEXT_WINDOW;
  if (activePath.length === 0 || turns <= 0) {
    return { current: 0, limit, ratio: 0 };
  }

  const windowSize = Math.max(0, Math.floor(turns * 2));
  const startIndex = Math.max(0, activePath.length - windowSize);
  const window = activePath.slice(startIndex);

  let current = 0;
  for (const node of window) {
    const input = node.metadata.input_tokens ?? 0;
    const output = node.metadata.output_tokens ?? 0;
    current += input + output;
  }

  const ratio = limit > 0 ? Math.max(0, Math.min(1, current / limit)) : 0;
  return { current, limit, ratio };
}

/**
 * Read the context window size from `ModelSettings`. Returns
 * `DEFAULT_CONTEXT_WINDOW` (8192) when settings are `undefined` or do not
 * expose a context-window field. Req 13.4 allows fallback.
 *
 * Kept as a pure function for forward compatibility — when `ModelSettings`
 * grows `defaults.context_window` or `models[].context_window`, wire them
 * in here without touching call sites.
 */
export function readContextWindowLimit(
  settings: ModelSettings | undefined,
): number {
  if (!settings) return DEFAULT_CONTEXT_WINDOW;
  return DEFAULT_CONTEXT_WINDOW;
}
