import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    /**
     * Mixed environments:
     *   - `*.test.ts`  — pure logic / property-based tests (fast-check).
     *                    Run in node for zero-DOM speed (~5s / 72 tests).
     *   - `*.test.tsx` — component-level render tests via
     *                    @testing-library/react; require jsdom.
     *                    See environmentMatchGlobs below.
     */
    environment: "node",
    environmentMatchGlobs: [
      ["src/**/__tests__/**/*.test.tsx", "jsdom"],
    ],
    globals: false,
    include: [
      "src/**/__tests__/**/*.test.ts",
      "src/**/__tests__/**/*.test.tsx",
    ],
    setupFiles: ["./src/test/setup.ts"],
  },
});
