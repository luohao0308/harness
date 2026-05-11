/**
 * Clipboard helpers for Workspace message copy actions.
 *
 * Requirement: Req 5.4, 13.8 (agent-workspace-chat-v2-refine).
 * Design: §New lib modules → `clipboard.ts`, §Error Handling → "Clipboard failure".
 *
 * Design guarantees:
 * - TOTAL: `copyText` never rejects; returns `false` on every failure path.
 * - Zero runtime dependencies — pure browser APIs only.
 * - SSR-safe: every entry point tolerates `document` / `navigator` being absent.
 */

/**
 * Copy plain text to the system clipboard.
 *
 * Strategy: try the modern `navigator.clipboard.writeText` first, which is
 * async and permission-aware. If that API is missing or the promise rejects,
 * fall through to the synchronous `<textarea> + execCommand("copy")`
 * fallback. Returns `true` as soon as either path succeeds, otherwise `false`.
 *
 * Never throws (TOTAL) — callers can `await` without `try/catch`.
 */
export async function copyText(text: string): Promise<boolean> {
  if (
    typeof navigator !== "undefined" &&
    typeof navigator.clipboard?.writeText === "function"
  ) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // fall through to the execCommand fallback below
    }
  }
  return copyTextExecFallback(text);
}

/**
 * Whether the current runtime supports any copy primitive at all.
 *
 * Used to disable Copy buttons up-front in hostile environments (e.g. SSR
 * prerender, non-secure contexts without `execCommand`).
 */
export function supportsCopy(): boolean {
  if (typeof document === "undefined") {
    return false;
  }
  const hasClipboard =
    typeof navigator !== "undefined" &&
    typeof navigator.clipboard?.writeText === "function";
  const hasExec = typeof document.execCommand === "function";
  return hasClipboard || hasExec;
}

/**
 * Fallback implementation via hidden `<textarea>` + `execCommand("copy")`.
 * Exposed for direct testing; `copyText` calls it internally on the failure
 * path. Returns `false` (never throws) in SSR / no-DOM environments.
 */
export function copyTextExecFallback(text: string): boolean {
  if (typeof document === "undefined") {
    return false;
  }
  if (typeof document.execCommand !== "function") {
    return false;
  }

  const textarea = document.createElement("textarea");
  try {
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    // Keep the element offscreen & inert so it cannot steal focus or paint.
    textarea.style.position = "fixed";
    textarea.style.top = "0";
    textarea.style.left = "0";
    textarea.style.width = "1px";
    textarea.style.height = "1px";
    textarea.style.opacity = "0";
    textarea.style.pointerEvents = "none";

    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    textarea.setSelectionRange(0, text.length);

    return document.execCommand("copy") === true;
  } catch {
    return false;
  } finally {
    if (textarea.parentNode) {
      textarea.parentNode.removeChild(textarea);
    }
  }
}
