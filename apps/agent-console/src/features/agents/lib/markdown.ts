/**
 * Zero-dependency Markdown subset for chat bubbles.
 *
 * Implements Property 1 (Markdown rendering safety & text preservation) from
 * `agent-workspace-chat-refine` design. No third-party markdown parser is used,
 * and `dangerouslySetInnerHTML` is forbidden. Every exported function is TOTAL:
 * given any string input it returns a valid result without throwing.
 *
 * Supported block grammar (everything else is rendered as literal text):
 *  - Heading `#`..`######`
 *  - Fenced code ```lang ... ```
 *  - Blockquote (`> `)
 *  - Ordered / unordered list (`- item`, `* item`, `1. item`)
 *  - Paragraph
 *
 * Supported inline grammar:
 *  - Inline code `` `x` ``
 *  - Link `[label](href)` with URL allow-list fallback
 *  - Hard line break (two trailing spaces before `\n`)
 *
 * Any unsupported syntax (images, tables, raw HTML, autolinks, emphasis,
 * reference links, task lists, setext headings) is preserved as plain text.
 *
 * The file is a plain `.ts` module so it intentionally builds React nodes with
 * `React.createElement` instead of JSX, mirroring the design spec.
 */

import { createElement, Fragment, type JSX, type ReactNode } from "react";

import { CodeBlockCopyButton } from "../components/CodeBlockCopyButton";

export type MdToken =
  | { type: "heading"; level: 1 | 2 | 3 | 4 | 5 | 6; inline: InlineToken[] }
  | { type: "paragraph"; inline: InlineToken[] }
  | { type: "code_block"; language: string; body: string }
  | { type: "blockquote"; children: MdToken[] }
  | { type: "list"; ordered: boolean; items: MdToken[][] }
  | { type: "hr" };

export type InlineToken =
  | { type: "text"; value: string }
  | { type: "code"; value: string }
  | { type: "link"; href: string; label: string }
  | { type: "linebreak" };

/** Protocols allowed to render as a real `<a href>` element. */
export const SAFE_URL_PROTOCOLS = ["http:", "https:", "mailto:"] as const;

/**
 * Tokenise a markdown source string into the block token list.
 *
 * TOTAL: returns a valid `MdToken[]` for any input (including empty, malformed
 * or adversarial strings). Never throws.
 */
export function tokenizeMarkdown(source: string): MdToken[] {
  const lines = source.split("\n");
  const tokens: MdToken[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i] ?? "";

    // Fenced code block
    if (line.startsWith("```")) {
      const language = line.slice(3).trim() || "text";
      const bodyLines: string[] = [];
      i += 1;
      while (i < lines.length && !(lines[i] ?? "").startsWith("```")) {
        bodyLines.push(lines[i] ?? "");
        i += 1;
      }
      // consume closing fence when present; tolerate EOF
      if (i < lines.length) {
        i += 1;
      }
      tokens.push({ type: "code_block", language, body: bodyLines.join("\n") });
      continue;
    }

    // Heading
    const headingMatch = /^(#{1,6})\s+(.*)$/.exec(line);
    if (headingMatch) {
      const hashes = headingMatch[1] ?? "";
      const rest = headingMatch[2] ?? "";
      const level = clampHeadingLevel(hashes.length);
      tokens.push({ type: "heading", level, inline: tokenizeInline(rest) });
      i += 1;
      continue;
    }

    // Blockquote
    if (/^>/.test(line)) {
      const quoteBody: string[] = [];
      while (i < lines.length && /^>/.test(lines[i] ?? "")) {
        quoteBody.push((lines[i] ?? "").replace(/^>\s?/, ""));
        i += 1;
      }
      tokens.push({
        type: "blockquote",
        children: tokenizeMarkdown(quoteBody.join("\n")),
      });
      continue;
    }

    // Ordered / unordered list
    if (LIST_LINE.test(line)) {
      const { token, consumed } = collectList(lines, i);
      tokens.push(token);
      i += consumed;
      continue;
    }

    // Blank line
    if (line.trim() === "") {
      i += 1;
      continue;
    }

    // Paragraph: consume until blank or block-starter
    const paraLines: string[] = [];
    while (i < lines.length) {
      const current = lines[i] ?? "";
      if (current.trim() === "" || isBlockStart(current)) break;
      paraLines.push(current);
      i += 1;
    }
    tokens.push({
      type: "paragraph",
      inline: tokenizeInline(paraLines.join("\n")),
    });
  }

  return tokens;
}

/**
 * Render a markdown source string as a React element tree.
 *
 * TOTAL: never throws. Does not use `dangerouslySetInnerHTML`. Unsafe URLs
 * (outside {@link SAFE_URL_PROTOCOLS}) degrade to the literal label text.
 * External links are emitted with `target="_blank"` and
 * `rel="noopener noreferrer"`.
 */
export function renderMarkdown(source: string): JSX.Element {
  const tokens = tokenizeMarkdown(source);
  return createElement(
    Fragment,
    null,
    ...tokens.map((token, index) => renderBlock(token, index)),
  );
}

// ---------------------------------------------------------------------------
// Internal helpers — not part of the public API.
// ---------------------------------------------------------------------------

/** Pre-compiled non-backtracking list pattern. */
const LIST_LINE = /^(\s*)([-*]|\d+\.)\s+/;
const ORDERED_LINE = /^(\s*)(\d+)\.\s+(.*)$/;
const UNORDERED_LINE = /^(\s*)([-*])\s+(.*)$/;

function clampHeadingLevel(raw: number): 1 | 2 | 3 | 4 | 5 | 6 {
  switch (raw) {
    case 1:
      return 1;
    case 2:
      return 2;
    case 3:
      return 3;
    case 4:
      return 4;
    case 5:
      return 5;
    default:
      return 6;
  }
}

function isBlockStart(line: string): boolean {
  if (line.startsWith("```")) return true;
  if (/^#{1,6}\s+/.test(line)) return true;
  if (/^>/.test(line)) return true;
  if (LIST_LINE.test(line)) return true;
  return false;
}

/** Collect a contiguous run of list items. Items reset on kind switch or blank. */
function collectList(
  lines: string[],
  start: number,
): { token: MdToken; consumed: number } {
  const first = lines[start] ?? "";
  const ordered = ORDERED_LINE.test(first);
  const items: MdToken[][] = [];
  let i = start;

  while (i < lines.length) {
    const line = lines[i] ?? "";
    if (line.trim() === "") break;

    let content: string | null = null;
    if (ordered) {
      const match = ORDERED_LINE.exec(line);
      if (!match) break;
      content = match[3] ?? "";
    } else {
      const match = UNORDERED_LINE.exec(line);
      if (!match) break;
      content = match[3] ?? "";
    }

    items.push([{ type: "paragraph", inline: tokenizeInline(content) }]);
    i += 1;
  }

  return {
    token: { type: "list", ordered, items },
    consumed: i - start,
  };
}

/**
 * Linear left-to-right inline scanner. No backtracking regexes: all lookups are
 * `indexOf`-based. TOTAL: returns a valid token list for any input. Unclosed
 * backticks or malformed link syntax degrade to literal text.
 */
function tokenizeInline(source: string): InlineToken[] {
  const tokens: InlineToken[] = [];
  let buffer = "";
  let i = 0;

  const flush = (): void => {
    if (buffer.length > 0) {
      tokens.push({ type: "text", value: buffer });
      buffer = "";
    }
  };

  while (i < source.length) {
    const ch = source[i];

    // Hard line break: two trailing spaces immediately before a newline.
    if (ch === "\n") {
      if (buffer.endsWith("  ")) {
        buffer = buffer.slice(0, -2);
        flush();
        tokens.push({ type: "linebreak" });
      } else {
        buffer += "\n";
      }
      i += 1;
      continue;
    }

    // Inline code span.
    if (ch === "`") {
      const close = source.indexOf("`", i + 1);
      if (close !== -1) {
        flush();
        tokens.push({ type: "code", value: source.slice(i + 1, close) });
        i = close + 1;
        continue;
      }
      // Unclosed backtick — keep literal.
      buffer += ch;
      i += 1;
      continue;
    }

    // Link `[label](href)` — label cannot contain `]`, href cannot contain
    // whitespace or `)`. Everything else falls back to literal text.
    if (ch === "[") {
      const rbracket = source.indexOf("]", i + 1);
      if (rbracket !== -1 && source[rbracket + 1] === "(") {
        const rparen = source.indexOf(")", rbracket + 2);
        if (rparen !== -1) {
          const href = source.slice(rbracket + 2, rparen);
          const label = source.slice(i + 1, rbracket);
          if (href.length > 0 && !HAS_HREF_BREAK.test(href)) {
            flush();
            if (isSafeUrl(href)) {
              tokens.push({ type: "link", href, label });
            } else {
              tokens.push({ type: "text", value: label });
            }
            i = rparen + 1;
            continue;
          }
        }
      }
      buffer += ch;
      i += 1;
      continue;
    }

    buffer += ch;
    i += 1;
  }

  flush();
  return tokens;
}

/** Characters that terminate a markdown href (whitespace or closing paren). */
const HAS_HREF_BREAK = /[\s)]/;

/**
 * Accept only URLs whose resolved protocol is in {@link SAFE_URL_PROTOCOLS}.
 * Relative paths resolve against a placeholder base so they inherit `https:`
 * and are treated as safe.
 */
function isSafeUrl(href: string): boolean {
  try {
    const url = new URL(href, "https://placeholder.local/");
    return (SAFE_URL_PROTOCOLS as readonly string[]).includes(url.protocol);
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

const HEADING_CLASS: Record<1 | 2 | 3 | 4 | 5 | 6, string> = {
  1: "mt-4 text-2xl font-semibold text-slate-900 first:mt-0",
  2: "mt-4 text-xl font-semibold text-slate-900 first:mt-0",
  3: "mt-3 text-lg font-semibold text-slate-900 first:mt-0",
  4: "mt-3 text-base font-semibold text-slate-900 first:mt-0",
  5: "mt-2 text-sm font-semibold text-slate-800 first:mt-0",
  6: "mt-2 text-sm font-medium text-slate-700 first:mt-0",
};

const HEADING_TAG: Record<1 | 2 | 3 | 4 | 5 | 6, "h1" | "h2" | "h3" | "h4" | "h5" | "h6"> = {
  1: "h1",
  2: "h2",
  3: "h3",
  4: "h4",
  5: "h5",
  6: "h6",
};

function renderBlock(token: MdToken, key: number): ReactNode {
  switch (token.type) {
    case "heading":
      return createElement(
        HEADING_TAG[token.level],
        { key, className: HEADING_CLASS[token.level] },
        ...renderInline(token.inline),
      );
    case "paragraph":
      return createElement(
        "p",
        {
          key,
          className: "mt-2 text-sm leading-6 text-slate-800 first:mt-0 whitespace-pre-wrap",
        },
        ...renderInline(token.inline),
      );
    case "code_block":
      return createElement(
        "pre",
        {
          key,
          className:
            "group relative mt-2 overflow-x-auto rounded-lg bg-slate-950 p-3 font-mono text-xs leading-5 text-slate-100",
        },
        createElement(
          "code",
          { "data-language": token.language, className: "font-mono" },
          token.body,
        ),
        createElement(CodeBlockCopyButton, { getCode: () => token.body }),
      );
    case "blockquote":
      return createElement(
        "blockquote",
        {
          key,
          className:
            "mt-2 border-l-2 border-slate-200 pl-3 text-sm italic leading-6 text-slate-600",
        },
        ...token.children.map((child, childIdx) => renderBlock(child, childIdx)),
      );
    case "list": {
      const tag = token.ordered ? "ol" : "ul";
      const className = token.ordered
        ? "mt-2 list-decimal space-y-1 pl-6 text-sm leading-6 text-slate-800"
        : "mt-2 list-disc space-y-1 pl-6 text-sm leading-6 text-slate-800";
      return createElement(
        tag,
        { key, className },
        ...token.items.map((item, itemIdx) =>
          createElement(
            "li",
            { key: itemIdx },
            ...item.map((child, childIdx) => renderBlock(child, childIdx)),
          ),
        ),
      );
    }
    case "hr":
      return createElement("hr", { key, className: "my-3 border-slate-200" });
  }
}

function renderInline(tokens: InlineToken[]): ReactNode[] {
  return tokens.map((token, index) => {
    switch (token.type) {
      case "text":
        return token.value;
      case "code":
        return createElement(
          "code",
          {
            key: index,
            className:
              "rounded bg-slate-100 px-1 py-0.5 font-mono text-[0.85em] text-slate-800",
          },
          token.value,
        );
      case "link":
        return createElement(
          "a",
          {
            key: index,
            href: token.href,
            target: "_blank",
            rel: "noopener noreferrer",
            className: "text-indigo-600 underline hover:text-indigo-500",
          },
          token.label,
        );
      case "linebreak":
        return createElement("br", { key: index });
    }
  });
}
