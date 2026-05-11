/**
 * CodeBlockCopyButton — hover / focus-within Copy button rendered in the
 * top-right corner of every fenced code block (v4 / Req 7.1).
 *
 * - Parent `<pre>` carries the `group relative` utility; this button uses
 *   `absolute top-2 right-2 opacity-0 group-hover:opacity-100
 *   focus-within:opacity-100 focus-visible:opacity-100` so the button is
 *   invisible at rest but keyboard-reachable via Tab (Req 7.1.3 / 7.1.4).
 * - On click the button calls `copyText(getCode())`. Success flips the
 *   `Copy` icon to `Check` for 1500 ms (Req 7.1.2).
 * - `aria-label` is bilingual via `useI18n().text` (Req 7.1.1 / Req 8.4).
 * - Never throws; `copyText` itself is TOTAL.
 */

import { useEffect, useRef, useState, type JSX } from "react";
import { Check, Copy } from "lucide-react";

import { useI18n } from "../../../lib/i18n";
import { copyText } from "../lib/clipboard";

export type CodeBlockCopyButtonProps = {
  /**
   * Lazily read the code body so the parent does not stringify it on
   * every render. Should return the exact text that will be copied to the
   * clipboard.
   */
  getCode: () => string;
};

const CONFIRMATION_MS = 1500;

export function CodeBlockCopyButton({
  getCode,
}: CodeBlockCopyButtonProps): JSX.Element {
  const { text } = useI18n();
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clear pending timers on unmount so the async `setCopied(false)` never
  // fires against a disposed component.
  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  async function handleClick(): Promise<void> {
    const ok = await copyText(getCode());
    if (!ok) return;
    setCopied(true);
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
    }
    timerRef.current = setTimeout(() => {
      setCopied(false);
      timerRef.current = null;
    }, CONFIRMATION_MS);
  }

  const label = text("复制代码", "Copy code");

  return (
    <button
      type="button"
      onClick={() => {
        void handleClick();
      }}
      aria-label={label}
      title={label}
      className="absolute top-2 right-2 inline-flex h-6 w-6 items-center justify-center rounded-md border border-slate-700 bg-slate-900/80 text-slate-200 opacity-0 transition-opacity hover:bg-slate-800 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 group-hover:opacity-100 group-focus-within:opacity-100"
    >
      {copied ? (
        <Check aria-hidden="true" className="h-3.5 w-3.5" />
      ) : (
        <Copy aria-hidden="true" className="h-3.5 w-3.5" />
      )}
    </button>
  );
}
