// Feature: agent-workspace-chat-refine, Property 1: Markdown rendering safety & text preservation
import { describe, it, expect } from "vitest";
import fc from "fast-check";
import type { ReactElement, ReactNode } from "react";

import {
  SAFE_URL_PROTOCOLS,
  renderMarkdown,
  tokenizeMarkdown,
} from "../lib/markdown";

/**
 * Validates: Requirements 1.6, 10.2, 10.6
 *
 * Property 1 — for any string input:
 *   (a) tokenizeMarkdown is TOTAL (never throws).
 *   (b) renderMarkdown returns a React element object (never throws).
 *   (c) No unsafe URL (e.g. `javascript:`, `data:`) escapes as an `<a>` href.
 */

type ReactElementWithProps = ReactElement<Record<string, unknown>>;

function isReactElement(value: unknown): value is ReactElementWithProps {
  return (
    typeof value === "object" &&
    value !== null &&
    "type" in value &&
    "props" in value
  );
}

/**
 * Walk a React element tree and collect every `<a>` href attribute value.
 * Non-element leaves (strings, numbers, nulls) are ignored.
 */
function collectAnchorHrefs(node: ReactNode): string[] {
  if (!isReactElement(node)) return [];
  const hrefs: string[] = [];
  if (node.type === "a" && typeof node.props.href === "string") {
    hrefs.push(node.props.href);
  }
  const children = node.props.children as ReactNode | ReactNode[] | undefined;
  if (Array.isArray(children)) {
    for (const child of children) {
      hrefs.push(...collectAnchorHrefs(child));
    }
  } else if (children !== undefined) {
    hrefs.push(...collectAnchorHrefs(children));
  }
  return hrefs;
}

describe("Property 1: Markdown rendering safety & text preservation", () => {
  it("tokenizeMarkdown is total for arbitrary strings", () => {
    fc.assert(
      fc.property(fc.string(), (source) => {
        expect(() => tokenizeMarkdown(source)).not.toThrow();
        const tokens = tokenizeMarkdown(source);
        expect(Array.isArray(tokens)).toBe(true);
      }),
      { numRuns: 200 },
    );
  });

  it("renderMarkdown returns a React element for arbitrary strings", () => {
    fc.assert(
      fc.property(fc.string(), (source) => {
        const element = renderMarkdown(source);
        expect(typeof element).toBe("object");
        expect(element).not.toBeNull();
        expect(isReactElement(element)).toBe(true);
      }),
      { numRuns: 200 },
    );
  });

  it("renderMarkdown never emits anchors with unsafe URL protocols", () => {
    const unsafePrefixes = ["javascript:", "data:", "vbscript:", "file:"];
    const labelGen = fc
      .string({ maxLength: 12 })
      .filter((s) => !s.includes("]") && !s.includes("["));
    const unsafeHrefGen = fc
      .tuple(
        fc.constantFrom(...unsafePrefixes),
        fc
          .string({ maxLength: 16 })
          .filter((s) => !/[\s)]/.test(s) && !s.includes("]")),
      )
      .map(([prefix, tail]) => `${prefix}${tail}`);

    fc.assert(
      fc.property(labelGen, unsafeHrefGen, (label, href) => {
        const element = renderMarkdown(`[${label}](${href})`);
        const hrefs = collectAnchorHrefs(element);
        // Every href that survived must be from the safe allow-list.
        for (const emitted of hrefs) {
          const matchesSafe = SAFE_URL_PROTOCOLS.some((protocol) =>
            emitted.toLowerCase().startsWith(protocol),
          );
          expect(matchesSafe).toBe(true);
        }
      }),
      { numRuns: 200 },
    );
  });

  it("renderMarkdown keeps safe http(s) and mailto links intact", () => {
    const safeHrefGen = fc.oneof(
      fc.webUrl(),
      fc
        .tuple(
          fc.string({ minLength: 1, maxLength: 8 }).filter((s) => /^[a-z]+$/i.test(s)),
          fc.string({ minLength: 1, maxLength: 8 }).filter((s) => /^[a-z]+$/i.test(s)),
        )
        .map(([user, host]) => `mailto:${user}@${host}.test`),
    );
    const labelGen = fc
      .string({ minLength: 1, maxLength: 8 })
      .filter((s) => !s.includes("]") && !s.includes("["));

    fc.assert(
      fc.property(safeHrefGen, labelGen, (href, label) => {
        const element = renderMarkdown(`[${label}](${href})`);
        const hrefs = collectAnchorHrefs(element);
        for (const emitted of hrefs) {
          const matchesSafe = SAFE_URL_PROTOCOLS.some((protocol) =>
            emitted.toLowerCase().startsWith(protocol),
          );
          expect(matchesSafe).toBe(true);
        }
      }),
      { numRuns: 100 },
    );
  });
});
