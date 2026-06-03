/**
 * ShortcutOverlay — keyboard-shortcut cheatsheet portal (Req 13.2).
 *
 * Satisfies:
 *   - Req 13.2: displays the full keyboard binding list in a modal overlay.
 *   - Req 14.2: `role="dialog"` + `aria-modal="true"` for accessibility.
 *   - Req 14.4: outside click and Escape both close the overlay via
 *     `useOutsideClick`.
 *
 * Design reference: design.md §New components → `ShortcutOverlay` and
 *   §Architecture → "Search / Shortcut / Export overlays".
 */

import type { JSX, ReactNode } from "react";
import { useRef } from "react";
import { createPortal } from "react-dom";
import { Keyboard, X } from "lucide-react";

import { useI18n } from "../../../lib/i18n";
import { useOutsideClick } from "../hooks/useOutsideClick";

export type ShortcutOverlayProps = {
  open: boolean;
  onClose: () => void;
};

type ShortcutRow = {
  keys: string[];
  zh: string;
  en: string;
};

const SHORTCUTS: ShortcutRow[] = [
  { keys: ["Enter"], zh: "发送消息", en: "Send message" },
  { keys: ["Shift", "Enter"], zh: "换行", en: "Insert newline" },
  { keys: ["Cmd/Ctrl", "K"], zh: "搜索", en: "Search" },
  { keys: ["?"], zh: "快捷键帮助", en: "Keyboard shortcuts" },
  { keys: ["Esc"], zh: "关闭浮层", en: "Close overlay" },
];

function Kbd({ children }: { children: ReactNode }): JSX.Element {
  return (
    <kbd className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-xs">
      {children}
    </kbd>
  );
}

export function ShortcutOverlay({ open, onClose }: ShortcutOverlayProps): JSX.Element | null {
  const { text } = useI18n();
  const dialogRef = useRef<HTMLDivElement>(null);

  useOutsideClick(dialogRef, onClose, open);

  if (open === false) return null;
  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label={text("键盘快捷键", "Keyboard shortcuts")}
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-950/40 p-4 pt-[8vh] backdrop-blur-[2px]"
      onClick={onClose}
    >
      <div
        ref={dialogRef}
        onClick={(event) => event.stopPropagation()}
        className="w-[min(42rem,100%)] rounded-2xl border border-slate-200 bg-white p-4 shadow-2xl"
      >
        <div className="flex items-start justify-between">
          <div>
            <h2 className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Keyboard className="h-4 w-4" />
              {text("键盘快捷键", "Keyboard shortcuts")}
            </h2>
            <p className="mt-0.5 text-[11px] text-slate-500">
              {text("双语提示 · 按 Esc 关闭", "Bilingual hints · press Esc to close")}
            </p>
          </div>
          <button
            type="button"
            aria-label={text("关闭快捷键帮助", "Close keyboard shortcuts")}
            onClick={onClose}
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-500 transition hover:bg-slate-100 hover:text-slate-950"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <ul className="mt-3 space-y-2">
          {SHORTCUTS.map((row) => (
            <li
              key={row.keys.join("+")}
              className="flex items-center justify-between gap-3 rounded-lg px-2 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
            >
              <span className="flex shrink-0 items-center gap-1">
                {row.keys.map((key, index) => (
                  <span key={`${key}-${index}`} className="flex items-center gap-1">
                    {index > 0 ? <span className="text-slate-400">+</span> : null}
                    <Kbd>{key}</Kbd>
                  </span>
                ))}
              </span>
              <span className="min-w-0 flex-1 truncate text-right text-slate-600">
                {row.zh} / {row.en}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>,
    document.body,
  );
}
