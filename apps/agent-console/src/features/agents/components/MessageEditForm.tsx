/**
 * MessageEditForm — in-place edit textarea for `role = user` message bubbles.
 *
 * Implements the keyboard state machine and visual shell for Requirement 4.2
 * / 4.3 / 4.7 / 4.9 and the "edit validation" error handling slice of the
 * design document:
 *
 *   - Enter (no Shift, not composing) with `value.trim() !== ""`
 *     → calls `onSave(value)` and suppresses the native newline.
 *   - Shift+Enter falls through to the native textarea so a line break is
 *     inserted (Req 4.3).
 *   - Escape → calls `onCancel()` without mutating any store state.
 *   - IME composition (`compositionStart` until `compositionEnd`, or the
 *     Chromium-specific `keyCode === 229`) NEVER submits.
 *   - "Save & resend" is `disabled` while `value.trim().length === 0`
 *     (Req 4.7); the keyboard path mirrors the same guard via
 *     `editFormShouldSubmit`.
 *
 * Visual: white background, black text, `rounded-2xl` shell (Req 8.5) — the
 * editing mode must stay visually consistent with the non-editing user
 * bubble.
 *
 * Pure presentational component: no `useWorkspaceStore` access, no network
 * calls, no side effects beyond local state / focus. The parent (typically
 * `ChatSurface` via `ChatMessageBubble`) owns the branching logic and calls
 * `onSave` / `onCancel` accordingly.
 */

import {
  useEffect,
  useRef,
  useState,
  type CompositionEvent as ReactCompositionEvent,
  type JSX,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";

import { Button } from "../../../components/ui/button";
import { useI18n } from "../../../lib/i18n";

export type MessageEditFormProps = {
  initialContent: string;
  /** Caller re-verifies `trim()` is non-empty before mutating the store. */
  onSave: (newContent: string) => void;
  onCancel: () => void;
};

/**
 * Pure keyboard state machine for `MessageEditForm`. Returns `true` iff the
 * keyboard event should trigger `onSave` given the current textarea value
 * and IME composition flag.
 *
 * Truth table (Req 4.3 / 4.7):
 *   - `isComposing === false`
 *   - `event.keyCode !== 229` (Chromium composition sentinel)
 *   - `event.key === "Enter"`
 *   - `event.shiftKey === false`
 *   - `value.trim().length >= 1`
 *
 * Exported so that the property-based test `editFormShouldSubmit.property`
 * can exercise every branch without rendering React.
 */
export function editFormShouldSubmit(
  event: KeyboardEvent,
  value: string,
  isComposing: boolean,
): boolean {
  if (isComposing) return false;
  if (event.keyCode === 229) return false;
  if (event.key !== "Enter") return false;
  if (event.shiftKey) return false;
  if (value.trim().length === 0) return false;
  return true;
}

export function MessageEditForm({
  initialContent,
  onSave,
  onCancel,
}: MessageEditFormProps): JSX.Element {
  const { text } = useI18n();
  const [value, setValue] = useState<string>(initialContent);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isComposingRef = useRef<boolean>(false);

  // Auto-focus the textarea on mount so the user can immediately start
  // editing without an extra click (Req 4.2).
  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  function handleCompositionStart(_event: ReactCompositionEvent<HTMLTextAreaElement>): void {
    isComposingRef.current = true;
  }

  function handleCompositionEnd(_event: ReactCompositionEvent<HTMLTextAreaElement>): void {
    isComposingRef.current = false;
  }

  function handleKeyDown(event: ReactKeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key === "Escape") {
      event.preventDefault();
      onCancel();
      return;
    }
    if (editFormShouldSubmit(event.nativeEvent, value, isComposingRef.current)) {
      event.preventDefault();
      onSave(value);
    }
  }

  const canSubmit = value.trim().length > 0;

  return (
    <div className="flex w-full flex-col gap-2">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
        onCompositionStart={handleCompositionStart}
        onCompositionEnd={handleCompositionEnd}
        className="bg-white text-slate-900 border border-slate-200 rounded-2xl px-3 py-2 w-full min-h-[80px] focus:outline-none focus:ring-2 focus:ring-slate-400"
        aria-label={text("编辑消息", "Edit message")}
      />
      <div className="flex items-center justify-end gap-2">
        <Button
          type="button"
          variant="ghost"
          onClick={onCancel}
          aria-label={text("取消编辑", "Cancel edit")}
        >
          {text("取消", "Cancel")}
        </Button>
        <Button
          type="button"
          variant="primary"
          disabled={!canSubmit}
          onClick={() => {
            if (!canSubmit) return;
            onSave(value);
          }}
          aria-label={text("保存并重发", "Save and resend")}
        >
          {text("保存并重发", "Save & resend")}
        </Button>
      </div>
    </div>
  );
}
