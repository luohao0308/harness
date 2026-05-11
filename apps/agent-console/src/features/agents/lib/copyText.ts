/**
 * `<think>` block scrubber used by the Copy_Button pipeline (Req 5.2 / P7).
 *
 * Extracted from the v1 `ChatMessageBubble` private helper so the scrub logic
 * can be exercised by an independent property-based test suite. The function
 * MUST be:
 *
 * - TOTAL — never throws on any input string (including empty strings and
 *   malformed / unbalanced `<think>` tags).
 * - IDEMPOTENT — applying the function twice yields the same result as
 *   applying it once: `stripThinkBlocks(stripThinkBlocks(c)) === stripThinkBlocks(c)`.
 *
 * The regex uses a non-greedy match on `[\s\S]*?` so multiple adjacent
 * `<think>…</think>` blocks are stripped independently, and a leading/trailing
 * `trim()` collapses whitespace introduced by the removal.
 */

export function stripThinkBlocks(content: string): string {
  return content.replace(/<think>[\s\S]*?<\/think>/g, "").trim();
}
