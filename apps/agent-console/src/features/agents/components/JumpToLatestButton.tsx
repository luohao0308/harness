/**
 * JumpToLatestButton — floating "jump to latest message" button shown in
 * the message list when the user has scrolled far enough away from the
 * bottom that the Scroll_Sentinel is no longer intersecting (v3 / Req 2.4).
 */

import type { JSX } from "react";
import { ArrowDown } from "lucide-react";

import { useI18n } from "../../../lib/i18n";

export type JumpToLatestButtonProps = {
  onClick: () => void;
};

export function JumpToLatestButton({
  onClick,
}: JumpToLatestButtonProps): JSX.Element {
  const { text } = useI18n();
  const label = text("跳到最新", "Jump to latest");
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="absolute bottom-6 right-6 z-10 inline-flex h-9 w-9 items-center justify-center rounded-full bg-slate-900 text-white shadow-lg transition-colors hover:bg-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
    >
      <ArrowDown aria-hidden="true" className="h-4 w-4" />
    </button>
  );
}
