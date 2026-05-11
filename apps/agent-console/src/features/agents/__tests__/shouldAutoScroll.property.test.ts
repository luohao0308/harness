// Feature: agent-workspace-chat-refine, Property 2: Auto-scroll threshold
import { describe, it, expect } from "vitest";
import fc from "fast-check";

import { shouldAutoScroll } from "../lib/scroll";

/**
 * Validates: Requirements 1.8, 1.10
 *
 * Property 2 — shouldAutoScroll returns true iff
 *   (scrollHeight - scrollTop - clientHeight) <= 50.
 */
describe("Property 2: Auto-scroll threshold", () => {
  it("matches the arithmetic threshold for any integer scroll state", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 100_000 }),
        fc.integer({ min: 0, max: 100_000 }),
        fc.integer({ min: 0, max: 100_000 }),
        (scrollTop, clientHeight, scrollHeight) => {
          const expected = scrollHeight - scrollTop - clientHeight <= 50;
          expect(
            shouldAutoScroll({ scrollTop, clientHeight, scrollHeight }),
          ).toBe(expected);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("is true at exactly 50px from the bottom and false at 51px", () => {
    // Fixed boundary generator keeps the invariant tight even if fast-check
    // never samples the exact boundary under random integers.
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 10_000 }),
        fc.integer({ min: 0, max: 10_000 }),
        (scrollTop, clientHeight) => {
          const onThreshold = scrollTop + clientHeight + 50;
          const justPastThreshold = scrollTop + clientHeight + 51;
          expect(
            shouldAutoScroll({
              scrollTop,
              clientHeight,
              scrollHeight: onThreshold,
            }),
          ).toBe(true);
          expect(
            shouldAutoScroll({
              scrollTop,
              clientHeight,
              scrollHeight: justPastThreshold,
            }),
          ).toBe(false);
        },
      ),
      { numRuns: 100 },
    );
  });
});
