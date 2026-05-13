// Feature: agent-workspace-chat-v4-refine, Property P23
import { describe, expect, it } from "vitest";
import fc from "fast-check";

import {
  CONTEXT_MAX_TOKENS_DEFAULT,
  CONTEXT_MAX_TOKENS_MAX,
  CONTEXT_MAX_TOKENS_MIN,
  CONTEXT_MAX_TOKENS_STEP,
  clampContextMaxTokens,
} from "../lib/contextTokens";

/**
 * P23 — `clampContextMaxTokens` is TOTAL, bounded and idempotent.
 * Validates Req 5.2, 12.4.
 */
describe("Property P23: Context max tokens clamp idempotent", () => {
  const numericArb: fc.Arbitrary<number> = fc.oneof(
    fc.integer({ min: -1_000_000_000, max: 1_000_000_000 }),
    fc.double(),
    fc.constantFrom<number>(
      Number.NaN,
      Number.POSITIVE_INFINITY,
      Number.NEGATIVE_INFINITY,
    ),
  );

  it("always returns a value in [MIN, MAX] divisible by STEP", () => {
    fc.assert(
      fc.property(numericArb, (x) => {
        const r = clampContextMaxTokens(x);
        expect(Number.isFinite(r)).toBe(true);
        expect(r).toBeGreaterThanOrEqual(CONTEXT_MAX_TOKENS_MIN);
        expect(r).toBeLessThanOrEqual(CONTEXT_MAX_TOKENS_MAX);
        expect(r % CONTEXT_MAX_TOKENS_STEP).toBe(0);
      }),
      { numRuns: 200 },
    );
  });

  it("is idempotent", () => {
    fc.assert(
      fc.property(numericArb, (x) => {
        const once = clampContextMaxTokens(x);
        const twice = clampContextMaxTokens(once);
        expect(twice).toBe(once);
      }),
      { numRuns: 200 },
    );
  });

  it("tolerates non-number inputs without throwing", () => {
    const nonNumeric: unknown[] = [
      undefined,
      null,
      "abc",
      "12.5",
      {},
      [],
      true,
      false,
      Symbol("not-a-number"),
    ];
    for (const x of nonNumeric) {
      expect(() => clampContextMaxTokens(x)).not.toThrow();
      const r = clampContextMaxTokens(x);
      expect(Number.isFinite(r)).toBe(true);
      expect(r).toBeGreaterThanOrEqual(CONTEXT_MAX_TOKENS_MIN);
      expect(r).toBeLessThanOrEqual(CONTEXT_MAX_TOKENS_MAX);
      expect(r % CONTEXT_MAX_TOKENS_STEP).toBe(0);
    }
  });

  it("pins values below MIN to MIN and above MAX to MAX", () => {
    expect(clampContextMaxTokens(-1_000_000)).toBe(CONTEXT_MAX_TOKENS_MIN);
    expect(clampContextMaxTokens(0)).toBe(CONTEXT_MAX_TOKENS_MIN);
    expect(clampContextMaxTokens(CONTEXT_MAX_TOKENS_MIN)).toBe(
      CONTEXT_MAX_TOKENS_MIN,
    );
    expect(clampContextMaxTokens(CONTEXT_MAX_TOKENS_MAX)).toBe(
      CONTEXT_MAX_TOKENS_MAX,
    );
    expect(clampContextMaxTokens(1_000_000_000)).toBe(CONTEXT_MAX_TOKENS_MAX);
  });

  it("uses 258k as the default context budget", () => {
    expect(CONTEXT_MAX_TOKENS_DEFAULT).toBe(258_000);
    expect(clampContextMaxTokens(undefined)).toBe(258_000);
  });
});
