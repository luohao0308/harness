/**
 * MessageActions — hover/focus action row attached to every user / assistant
 * bubble (Req 4.1, 4.8, 5.1, 5.3, 5.4, 5.6, 10.1, 10.4, 10.5, 14.2, 14.3,
 * 16.1, 16.2).
 *
 * Buttons exposed:
 *   - Copy      — rendered for both `user` and `assistant`. On success the
 *                 icon switches to `Check` + label "已复制 / Copied" for
 *                 1500ms (Req 5.3). The label resets early if a fresh click
 *                 lands before the timer fires (the timer is always reset
 *                 before being re-armed).
 *   - Edit      — only for `role === "user" && !isStreaming && !isEditing`
 *                 (Req 4.1, 4.8).
 *   - Regenerate— only for `role === "assistant" && canRegenerate &&
 *                 !isStreaming` (Req 10.1, 10.4).
 *   - Branch    — only for `role === "assistant" && !isStreaming` when
 *                 `onBranch` is provided (Req 16.1, 16.2).
 *
 * Visibility is driven by the parent bubble (`group`) + this row's
 * `opacity-0 group-hover:opacity-100 focus-within:opacity-100` classes, so
 * the action row fades in on hover or keyboard focus (Req 4.1, 5.1, 14.2).
 *
 * Accessibility:
 *   - Every icon-only button carries a bilingual `aria-label` (Req 14.3).
 *   - Decorative icons are `aria-hidden="true"`.
 *   - All copy flows through `useI18n().text(zh, en)` (Req 14.2).
 *
 * The component holds only UI-local state (`justCopied` + its 1500ms timer);
 * it does NOT import `useWorkspaceStore` and never mutates global state.
 * Failure of `onCopy` is intentionally silent here — the parent is free to
 * surface a toast or inline error; this component keeps itself minimal.
 */

import { useEffect, useRef, useState, type JSX } from "react";

import { Check, Copy, GitBranch, Pencil, RotateCw } from "lucide-react";

import { Button } from "../../../components/ui/button";
import { useI18n } from "../../../lib/i18n";
import { cn } from "../../../lib/utils";
import type { ConversationRole } from "../../../stores/workspaceStore";

export type MessageActionsProps = {
  /** Only "user" / "assistant" are rendered upstream. */
  role: ConversationRole;
  /** Whether this bubble is the last assistant in Active_Path AND eligible
   *  for Regenerate (state ∈ {done, error, paused}). */
  canRegenerate: boolean;
  /** True → hide Edit (edit-during-stream is forbidden; Req 4.8). */
  isStreaming: boolean;
  /** Hide Edit when the message is already in edit mode. */
  isEditing: boolean;
  /** Returns `true` when the clipboard write succeeded, `false` otherwise. */
  onCopy: () => Promise<boolean>;
  /** Only called when `role === "user"`. */
  onEdit: () => void;
  /** Only called when `canRegenerate === true`. */
  onRegenerate: () => void;
  /** Called when the user clicks "Branch" on an assistant message (Req 16.1). */
  onBranch?: () => void;
};

// Shared sizing override: the Button primitive defaults to h-8/px-3, which
// is a bit tall for an inline hover row — shrink it to h-7 / px-2.
const SMALL_BUTTON = "h-7 gap-1 px-2 text-[11px]";

export function MessageActions(props: MessageActionsProps): JSX.Element {
  const { role, canRegenerate, isStreaming, isEditing, onCopy, onEdit, onRegenerate, onBranch } = props;
  const { text } = useI18n();

  const [justCopied, setJustCopied] = useState(false);
  const timerRef = useRef<number | null>(null);

  // Cleanup the 1500ms reset timer on unmount so we never call `setState`
  // on an unmounted component (Req 5.3 edge-case).
  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  async function handleCopy(): Promise<void> {
    const ok = await onCopy();
    if (ok) {
      setJustCopied(true);
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
      }
      timerRef.current = window.setTimeout(() => {
        setJustCopied(false);
        timerRef.current = null;
      }, 1500);
    } else {
      // Parent owns the error surface (v1 has no toast library; bubbles
      // may render an inline message). Here we simply keep the default
      // Copy state (Req 5.4 — icon never sticks on "copied" after a
      // failed write).
      setJustCopied(false);
    }
  }

  const showEdit = role === "user" && !isStreaming && !isEditing;
  const showRegenerate = role === "assistant" && canRegenerate && !isStreaming;
  const showBranch = role === "assistant" && !isStreaming && Boolean(onBranch);

  const copyLabel = justCopied ? text("已复制", "Copied") : text("复制", "Copy");

  return (
    <div
      className={cn(
        "flex items-center gap-1 pt-1 opacity-0 transition-opacity",
        "group-hover:opacity-100 focus-within:opacity-100",
      )}
    >
      <Button
        type="button"
        variant="ghost"
        onClick={handleCopy}
        aria-label={copyLabel}
        className={SMALL_BUTTON}
      >
        {justCopied ? (
          <Check aria-hidden="true" className="h-3.5 w-3.5 text-emerald-600" />
        ) : (
          <Copy aria-hidden="true" className="h-3.5 w-3.5" />
        )}
        <span>{copyLabel}</span>
      </Button>

      {showEdit && (
        <Button
          type="button"
          variant="ghost"
          onClick={onEdit}
          aria-label={text("编辑", "Edit")}
          className={SMALL_BUTTON}
        >
          <Pencil aria-hidden="true" className="h-3.5 w-3.5" />
          <span>{text("编辑", "Edit")}</span>
        </Button>
      )}

      {showRegenerate && (
        <Button
          type="button"
          variant="ghost"
          onClick={onRegenerate}
          aria-label={text("重新生成", "Regenerate")}
          className={SMALL_BUTTON}
        >
          <RotateCw aria-hidden="true" className="h-3.5 w-3.5" />
          <span>{text("重新生成", "Regenerate")}</span>
        </Button>
      )}

      {showBranch && (
        <Button
          type="button"
          variant="ghost"
          onClick={onBranch}
          aria-label={text("分支", "Branch")}
          className={SMALL_BUTTON}
        >
          <GitBranch aria-hidden="true" className="h-3.5 w-3.5" />
          <span>{text("分支", "Branch")}</span>
        </Button>
      )}
    </div>
  );
}
