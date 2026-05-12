// Feature: agent-workspace-chat-refine, Property 6: SSE error classification
import { describe, it, expect } from "vitest";
import fc from "fast-check";

import {
  classifyFetchError,
  classifyHttpStatus,
  isSseContentType,
  readBodyPreview,
  type SseErrorKind,
} from "../lib/sseErrors";

/**
 * Validates: Requirements 4.1, 4.2, 4.3, 4.4, 11.3
 *
 * Property 6 — SSE error classification:
 *   1. classifyHttpStatus truth table:
 *        401 / 403       → "auth"
 *        404             → "not_found"
 *        >= 500 && <= 599 → "server"
 *        other non-2xx in [100,599] → "http"
 *   2. isSseContentType is case-insensitive substring matching on
 *      `text/event-stream`.
 *   3. classifyFetchError(new TypeError()) === "network".
 *   4. readBodyPreview returns a string whose TextEncoder byteLength
 *      is <= maxBytes.
 */

function expectedStatusKind(status: number): SseErrorKind {
  if (!Number.isInteger(status)) return "http";
  if (status < 100 || status > 599) return "http";
  if (status === 401 || status === 403) return "auth";
  if (status === 404) return "not_found";
  if (status >= 500) return "server";
  return "http";
}

describe("Property 6: SSE error classification", () => {
  it("classifyHttpStatus matches the truth table for all HTTP codes", () => {
    fc.assert(
      fc.property(fc.integer({ min: 100, max: 599 }), (status) => {
        expect(classifyHttpStatus(status)).toBe(expectedStatusKind(status));
      }),
      { numRuns: 200 },
    );
  });

  it("classifyHttpStatus tolerates out-of-range and non-integer inputs", () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.integer({ min: -1000, max: 99 }),
          fc.integer({ min: 600, max: 10_000 }),
          fc.double({ noNaN: true }).filter((n) => !Number.isInteger(n)),
        ),
        (value) => {
          expect(classifyHttpStatus(value)).toBe("http");
        },
      ),
      { numRuns: 100 },
    );
  });

  it("isSseContentType is case-insensitive substring matching", () => {
    const needle = "text/event-stream";
    const padGen = fc
      .string({ maxLength: 16 })
      .filter((s) => !s.toLowerCase().includes(needle));

    fc.assert(
      fc.property(padGen, padGen, (prefix, suffix) => {
        const positive = `${prefix}TEXT/Event-Stream${suffix}`;
        expect(isSseContentType(positive)).toBe(true);
      }),
      { numRuns: 100 },
    );

    fc.assert(
      fc.property(padGen, (noise) => {
        // Remove any stray "text/event-stream" spelling to keep the negative
        // case genuinely negative.
        if (noise.toLowerCase().includes(needle)) return;
        expect(isSseContentType(noise)).toBe(false);
      }),
      { numRuns: 100 },
    );

    expect(isSseContentType(null)).toBe(false);
    expect(isSseContentType("")).toBe(false);
  });

  it("classifyFetchError(new TypeError()) === 'network'", () => {
    expect(classifyFetchError(new TypeError("nope"))).toBe("network");
    // And remains stable across arbitrary TypeError messages.
    fc.assert(
      fc.property(fc.string({ maxLength: 48 }), (msg) => {
        expect(classifyFetchError(new TypeError(msg))).toBe("network");
      }),
      { numRuns: 100 },
    );
  });

  it("classifyFetchError maps non-fetch errors to 'server'", () => {
    fc.assert(
      fc.property(fc.string({ maxLength: 48 }), (msg) => {
        expect(classifyFetchError(new Error(msg))).toBe("server");
      }),
      { numRuns: 100 },
    );
  });

  it("readBodyPreview returns <= maxBytes UTF-8 bytes", async () => {
    const encoder = new TextEncoder();
    await fc.assert(
      fc.asyncProperty(
        fc.uint8Array({ maxLength: 1024 }),
        fc.integer({ min: 1, max: 512 }),
        async (bytes, maxBytes) => {
          // Copy into a concrete ArrayBuffer-backed Uint8Array so the runtime
          // types satisfy BlobPart regardless of the host's TypedArray
          // buffer flavour.
          const copy = new Uint8Array(bytes.byteLength);
          copy.set(bytes);
          const res = new Response(new Blob([copy]));
          const preview = await readBodyPreview(res, maxBytes);
          expect(encoder.encode(preview).byteLength).toBeLessThanOrEqual(maxBytes);
        },
      ),
      { numRuns: 100 },
    );
  });

  it("readBodyPreview on an empty body returns an empty string", async () => {
    const res = new Response(new Blob([]));
    expect(await readBodyPreview(res, 256)).toBe("");
  });
});

/**
 * v4 regression — `formatErrorMessage` must map the new `rate_limited`
 * kind to a user-readable 429 hint instead of the generic "backend
 * internal error" copy. Matches the upstream `yield sse("error", ...)`
 * path that fires when DeepSeek / other providers return HTTP 429.
 */
describe("v4 rate_limited error copy", () => {
  it("produces the localized rate-limit title when kind === 'rate_limited'", async () => {
    const { formatErrorMessage } = await import("../lib/sseErrors");
    const { title } = formatErrorMessage(
      {
        kind: "rate_limited",
        detail: "HTTP Error 429: Too Many Requests",
        happened_at: "2026-05-10T20:35:38.528Z",
      },
      (zh, _en) => zh,
      { apiBaseUrl: "http://127.0.0.1:8000" },
    );
    expect(title).toContain("429");
  });
});
