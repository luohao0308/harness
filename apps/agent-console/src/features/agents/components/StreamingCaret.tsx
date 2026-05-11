/**
 * StreamingCaret — blinking 2px × 1em vertical bar appended to an assistant
 * bubble while `state === "streaming"` (v4 / Req 7.2).
 *
 * - Uses the `animate-streaming-caret` Tailwind utility (declared inline
 *   via `styles.css`) keyed off `@keyframes blink`.
 * - Honours `prefers-reduced-motion: reduce` — the media query in
 *   `styles.css` disables the animation and the block stays static, still
 *   visually present so the user knows output is in-flight (Req 7.2.3).
 * - `aria-hidden="true"` — screen readers rely on `role="status"` /
 *   `aria-live="polite"` already set on the bubble wrapper.
 * - Zero runtime dependencies.
 */

import type { JSX } from "react";

export function StreamingCaret(): JSX.Element {
  return (
    <span
      aria-hidden="true"
      className="ml-1 inline-block h-[1em] w-[2px] align-middle bg-slate-500 animate-streaming-caret"
    />
  );
}
