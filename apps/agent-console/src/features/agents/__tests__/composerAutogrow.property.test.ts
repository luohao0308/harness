// Feature: agent-workspace-chat-v3-slash-history, Property P18
import { describe, it, expect } from "vitest";
import fc from "fast-check";

import {
  MAX_COMPOSER_HEIGHT,
  MIN_COMPOSER_HEIGHT,
  clampAutogrowHeight,
} from "../lib/composerAutogrow";

/**
 * P18 — clampAutogrowHeight always returns a value in [MIN, MAX].
 */
describe("Property P18: clampAutogrowHeight bounded", () => {
  it("returns a finite number in [40, 200] for any finite input", () => {
    fc.assert(
      fc.property(fc.integer({ min: -1000, max: 10_000 }), (scrollHeight) => {
        const result = clampAutogrowHeight(scrollHeight);
        expect(Number.isFinite(result)).toBe(true);
        expect(result).toBeGreaterThanOrEqual(MIN_COMPOSER_HEIGHT);
        expect(result).toBeLessThanOrEqual(MAX_COMPOSER_HEIGHT);
      }),
      { numRuns: 500 },
    );
  });

  it("returns MIN for NaN / Infinity / non-number", () => {
    expect(clampAutogrowHeight(Number.NaN)).toBe(MIN_COMPOSER_HEIGHT);
    expect(clampAutogrowHeight(Number.POSITIVE_INFINITY)).toBe(MIN_COMPOSER_HEIGHT);
    expect(clampAutogrowHeight(Number.NEGATIVE_INFINITY)).toBe(MIN_COMPOSER_HEIGHT);
    // @ts-expect-error — runtime guard
    expect(clampAutogrowHeight(undefined)).toBe(MIN_COMPOSER_HEIGHT);
    // @ts-expect-error — runtime guard
    expect(clampAutogrowHeight("not a number")).toBe(MIN_COMPOSER_HEIGHT);
  });

  it("passes through values inside the window unchanged", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: MIN_COMPOSER_HEIGHT, max: MAX_COMPOSER_HEIGHT }),
        (scrollHeight) => {
          expect(clampAutogrowHeight(scrollHeight)).toBe(scrollHeight);
        },
      ),
      { numRuns: 100 },
    );
  });
});
