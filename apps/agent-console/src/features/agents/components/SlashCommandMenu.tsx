/**
 * SlashCommandMenu — the popup surfaced above the composer textarea when
 * the draft starts with `/` (v3 / Req 5).
 *
 * Pure presentational:
 *   - Receives the candidate list from a parent (which owns `draft` state
 *     and calls `parseSlashCommand`).
 *   - Emits `onHover(index)` / `onSelect(cmd)` callbacks.
 *   - Highlights `activeIndex` so ArrowUp / ArrowDown navigation works.
 *
 * Accessibility (Req 7.3):
 *   - `role="listbox"` + each item `role="option"` with `aria-selected`.
 *   - Bilingual `aria-label` on the root.
 */

import type { JSX } from "react";

import { useI18n } from "../../../lib/i18n";
import { cn } from "../../../lib/utils";
import type { SlashCommand } from "../lib/slashCommands";

export type SlashCommandMenuProps = {
  open: boolean;
  candidates: SlashCommand[];
  activeIndex: number;
  onHover: (index: number) => void;
  onSelect: (cmd: SlashCommand) => void;
};

export function SlashCommandMenu({
  open,
  candidates,
  activeIndex,
  onHover,
  onSelect,
}: SlashCommandMenuProps): JSX.Element | null {
  const { text } = useI18n();
  if (open === false) return null;

  const safeIndex = candidates.length === 0 ? 0 : Math.max(0, Math.min(activeIndex, candidates.length - 1));

  return (
    <div
      role="listbox"
      aria-label={text("命令菜单", "Slash command menu")}
      className="absolute bottom-full left-0 right-0 z-20 mb-2 mx-auto w-[360px] max-w-[90vw] rounded-2xl border border-slate-200 bg-white p-1 shadow-xl"
    >
      {candidates.length === 0 ? (
        <p className="px-3 py-4 text-center text-xs text-slate-500">
          {text("没有匹配的命令", "No matching command")}
        </p>
      ) : (
        <ul className="max-h-[280px] overflow-y-auto">
          {candidates.map((cmd, i) => {
            const active = i === safeIndex;
            return (
              <li key={cmd.name}>
                <button
                  type="button"
                  role="option"
                  aria-selected={active}
                  onMouseEnter={() => onHover(i)}
                  // Use onMouseDown so the click fires before the textarea
                  // loses focus and `parseSlashCommand` re-classifies.
                  onMouseDown={(event) => {
                    event.preventDefault();
                    onSelect(cmd);
                  }}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-xs transition-colors",
                    active ? "bg-slate-100" : "hover:bg-slate-50",
                  )}
                >
                  <span className="shrink-0 font-mono text-slate-900">{cmd.trigger}</span>
                  <span className="min-w-0 flex-1 truncate text-slate-500">
                    {text(cmd.zh, cmd.en)}
                  </span>
                  {cmd.aliases.length > 0 && (
                    <span className="shrink-0 text-[10px] uppercase text-slate-400">
                      {cmd.aliases.map((a) => `/${a}`).join(" ")}
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
