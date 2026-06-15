/**
 * Vitest setup for component-level render tests (`*.test.tsx`).
 *
 * - Imports `@testing-library/jest-dom` to extend `expect` with
 *   `toBeInTheDocument`, `toHaveAttribute`, etc.
 * - Imports `jest-axe` to extend `expect` with `toHaveNoViolations` for
 *   accessibility testing.
 * - Registers a cleanup hook so React roots from one test don't leak
 *   into the next (react-testing-library normally relies on the
 *   vitest-globals auto-cleanup; we call it explicitly here because our
 *   config sets `globals: false`).
 * - Polyfills `IntersectionObserver` because jsdom ships without it and
 *   `ChatMessageList` guards against that, but a polyfill keeps the
 *   branch consistent with browsers when we do want to exercise the
 *   observer path.
 */

import "@testing-library/jest-dom/vitest";
import { toHaveNoViolations } from "jest-axe";
import { afterEach, expect } from "vitest";
import { cleanup } from "@testing-library/react";

// Extend expect with jest-axe matchers
expect.extend(toHaveNoViolations);

// React 18 requires this global for `act(...)` to know it's in a test.
// See https://react.dev/reference/react/act#making-your-tests-async
// eslint-disable-next-line @typescript-eslint/no-explicit-any
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

afterEach(() => {
  cleanup();
});

if (typeof globalThis.IntersectionObserver === "undefined") {
  class MockIntersectionObserver {
    readonly root: Element | null = null;
    readonly rootMargin: string = "";
    readonly thresholds: ReadonlyArray<number> = [];

    constructor() {
      // no-op
    }

    observe(): void {
      /* no-op */
    }
    unobserve(): void {
      /* no-op */
    }
    disconnect(): void {
      /* no-op */
    }
    takeRecords(): IntersectionObserverEntry[] {
      return [];
    }
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).IntersectionObserver = MockIntersectionObserver;
}
