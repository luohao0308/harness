/**
 * Commit-scheduling hook that lets SSE delta writes survive React 18
 * automatic batching (Req 2 / P2 / P3).
 *
 * Strategies:
 *   - `flush_sync`: Wrap the write in `flushSync(() => write())` so each
 *     delta produces an independent React commit.
 *   - `microtask`: `queueMicrotask(() => flushSync(() => write()))` — used
 *     as a JSDOM fallback where `flushSync` inside a sync dispatch path
 *     is constrained.
 *   - `raf_window`: Accumulate pending writes and flush them together on
 *     the next animation frame. Bounds the time between commits to one
 *     frame (~16ms). If rAF is unavailable or we observe a frame interval
 *     > 32ms (slow frames), we downgrade back to `flush_sync` for the
 *     remainder of the stream.
 *   - `auto` (default): Start at `flush_sync`. Maintain a 4-slot ring
 *     buffer of commit timestamps. When the rolling average interval of
 *     the last four commits drops below 8ms, upgrade to `raf_window`
 *     for the rest of the stream. `drain()` resets the evaluator so the
 *     next stream starts fresh.
 *
 * The hook is pure state + refs — it does not import React components or
 * the workspace store, so it remains trivially testable.
 */

import { useCallback, useEffect, useRef } from "react";
import { flushSync } from "react-dom";

export type FlushStrategy =
  | "flush_sync"
  | "microtask"
  | "raf_window"
  | "auto";

export type UseStreamFlushOptions = {
  /** Strategy override; defaults to `"auto"`. */
  strategy?: FlushStrategy;
};

export type StreamFlushApi = {
  /**
   * Apply a store-mutating write and ensure it produces a React commit
   * within the Req 2 / P2 / P3 budget.
   */
  commit(write: () => void): void;
  /** Flush any pending writes; call on stream `done` / `abort`. */
  drain(): void;
};

/** Number of recent commit timestamps retained for auto strategy evaluation. */
const RING_BUFFER_SIZE = 4;
/** Auto-upgrades to `raf_window` when rolling average interval drops below this. */
const AUTO_UPGRADE_THRESHOLD_MS = 8;
/** `raf_window` downgrades to `flush_sync` when an observed frame interval exceeds this. */
const RAF_DOWNGRADE_THRESHOLD_MS = 32;

type ResolvedStrategy = "flush_sync" | "microtask" | "raf_window";

type InternalState = {
  configured: FlushStrategy;
  effective: ResolvedStrategy;
  commitTimestamps: number[];
  ringIndex: number;
  ringCount: number;
  pendingWrites: Array<() => void>;
  rafHandle: number | null;
  lastRafTime: number | null;
};

function nowMs(): number {
  if (
    typeof performance !== "undefined" &&
    typeof performance.now === "function"
  ) {
    return performance.now();
  }
  return Date.now();
}

function hasRaf(): boolean {
  return typeof requestAnimationFrame === "function";
}

function resolveInitialEffective(configured: FlushStrategy): ResolvedStrategy {
  if (configured === "auto") return "flush_sync";
  if (configured === "raf_window") {
    return hasRaf() ? "raf_window" : "flush_sync";
  }
  return configured;
}

function recordCommitTimestamp(s: InternalState): void {
  s.commitTimestamps[s.ringIndex] = nowMs();
  s.ringIndex = (s.ringIndex + 1) % RING_BUFFER_SIZE;
  if (s.ringCount < RING_BUFFER_SIZE) s.ringCount += 1;
}

function averageIntervalMs(s: InternalState): number | null {
  if (s.ringCount < RING_BUFFER_SIZE) return null;
  // Extract ring buffer in chronological order. After RING_BUFFER_SIZE writes
  // the oldest slot sits at `ringIndex` and the newest at `ringIndex - 1`.
  const ordered: number[] = [];
  for (let i = 0; i < RING_BUFFER_SIZE; i += 1) {
    ordered.push(s.commitTimestamps[(s.ringIndex + i) % RING_BUFFER_SIZE]);
  }
  let total = 0;
  for (let i = 1; i < ordered.length; i += 1) {
    total += ordered[i] - ordered[i - 1];
  }
  return total / (ordered.length - 1);
}

function maybeUpgradeToRafWindow(s: InternalState): void {
  if (s.configured !== "auto") return;
  if (s.effective !== "flush_sync") return;
  if (!hasRaf()) return;
  const avg = averageIntervalMs(s);
  if (avg !== null && avg < AUTO_UPGRADE_THRESHOLD_MS) {
    s.effective = "raf_window";
  }
}

function cancelPendingRaf(s: InternalState): void {
  if (s.rafHandle !== null && typeof cancelAnimationFrame === "function") {
    cancelAnimationFrame(s.rafHandle);
  }
  s.rafHandle = null;
}

function flushPendingWrites(s: InternalState): void {
  const writes = s.pendingWrites;
  s.pendingWrites = [];
  if (writes.length === 0) return;
  flushSync(() => {
    for (const fn of writes) fn();
  });
  recordCommitTimestamp(s);
}

export function useStreamFlush(opts?: UseStreamFlushOptions): StreamFlushApi {
  const stateRef = useRef<InternalState | null>(null);
  if (stateRef.current === null) {
    const configured: FlushStrategy = opts?.strategy ?? "auto";
    stateRef.current = {
      configured,
      effective: resolveInitialEffective(configured),
      commitTimestamps: new Array<number>(RING_BUFFER_SIZE).fill(0),
      ringIndex: 0,
      ringCount: 0,
      pendingWrites: [],
      rafHandle: null,
      lastRafTime: null,
    };
  }

  useEffect(() => {
    return () => {
      const s = stateRef.current;
      if (!s) return;
      cancelPendingRaf(s);
      s.pendingWrites = [];
    };
  }, []);

  const commit = useCallback((write: () => void): void => {
    const s = stateRef.current;
    if (s === null) {
      // Defensive: should be unreachable because stateRef is initialised
      // synchronously on first render above.
      write();
      return;
    }

    switch (s.effective) {
      case "flush_sync": {
        flushSync(() => write());
        recordCommitTimestamp(s);
        maybeUpgradeToRafWindow(s);
        return;
      }
      case "microtask": {
        queueMicrotask(() => {
          flushSync(() => write());
          recordCommitTimestamp(s);
        });
        return;
      }
      case "raf_window": {
        if (!hasRaf()) {
          // rAF unavailable at runtime — downgrade for the remainder of
          // the stream and commit synchronously.
          s.effective = "flush_sync";
          flushSync(() => write());
          recordCommitTimestamp(s);
          return;
        }
        s.pendingWrites.push(write);
        if (s.rafHandle === null) {
          s.rafHandle = requestAnimationFrame((frameTime) => {
            const st = stateRef.current;
            if (!st) return;
            st.rafHandle = null;

            // Observe frame cadence. Slow frames (> 32ms) indicate the
            // tab is throttled; stop batching and fall back to per-write
            // flushSync so content remains visible.
            const prev = st.lastRafTime;
            st.lastRafTime = frameTime;
            if (
              prev !== null &&
              frameTime - prev > RAF_DOWNGRADE_THRESHOLD_MS
            ) {
              st.effective = "flush_sync";
            }

            flushPendingWrites(st);
          });
        }
        return;
      }
    }
  }, []);

  const drain = useCallback((): void => {
    const s = stateRef.current;
    if (!s) return;
    cancelPendingRaf(s);
    flushPendingWrites(s);
    // Reset auto-mode evaluator so the next stream re-evaluates from
    // flush_sync. Explicit strategies keep their setting.
    if (s.configured === "auto") {
      s.effective = "flush_sync";
      s.ringIndex = 0;
      s.ringCount = 0;
      s.lastRafTime = null;
      for (let i = 0; i < RING_BUFFER_SIZE; i += 1) {
        s.commitTimestamps[i] = 0;
      }
    }
  }, []);

  return { commit, drain };
}
