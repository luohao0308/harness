import {
  forwardRef,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";

import { Pause, Play, Send } from "lucide-react";

import { Button } from "../../../components/ui/button";
import { useI18n } from "../../../lib/i18n";
import {
  MAX_COMPOSER_HEIGHT,
  MIN_COMPOSER_HEIGHT,
  clampAutogrowHeight,
} from "../lib/composerAutogrow";
import {
  filterCommandsByPrefix,
  parseSlashCommand,
  replaceSlashPrefix,
  type SlashCommand,
} from "../lib/slashCommands";
import type { WorkspaceMode } from "../lib/types";
import { SlashCommandMenu } from "./SlashCommandMenu";

export type ChatComposerProps = {
  draft: string;
  onDraftChange: (next: string) => void;
  onSubmit: () => void;
  onPause: () => void;
  onResume: () => void;
  isStreaming: boolean;
  canResume: boolean;
  mode: WorkspaceMode;
  onChangeMode: (m: WorkspaceMode) => void;
  placeholder: string;
  /**
   * When `true`, the composer disables Enter-to-submit so that another surface
   * (e.g. `MessageEditForm`) owns Enter semantics while the user is editing a
   * prior message. The textarea remains interactive for typing; only submission
   * gestures (Enter / send button) are locked.
   */
  isEditLocked?: boolean;
  /**
   * v3 additive: dispatched when the user confirms a slash command. The
   * parent decides what to do — mode switch, open overlay, insert mention,
   * clear conversation, etc. When omitted the composer still hides the
   * menu but no-ops on confirm.
   */
  onSlashDispatch?: (command: SlashCommand, args: string) => void;
};

/**
 * Pure keyboard state machine for the composer. Returns `true` iff the provided
 * event should trigger a submission given the current draft and streaming state.
 *
 * Truth table (Property 3):
 * - `event.isComposing === false`
 * - `event.key === "Enter"`
 * - `event.shiftKey === false`
 * - `draft.trim().length >= 1`
 * - `isStreaming === false`
 * - `isEditLocked === false`
 */
export function composerShouldSubmit(
  event: KeyboardEvent,
  draft: string,
  isStreaming: boolean,
  isEditLocked: boolean = false,
): boolean {
  if (isEditLocked) return false;
  if (event.isComposing || event.keyCode === 229) return false;
  if (event.key !== "Enter") return false;
  if (event.shiftKey) return false;
  if (!draft.trim()) return false;
  if (isStreaming) return false;
  return true;
}

/**
 * Re-measure the textarea height and clamp into [MIN, MAX]. Side effect: also
 * toggles `overflow-y` based on whether the content exceeds MAX so users see
 * the scrollbar only when it's actually needed (Req 1.3).
 */
function autogrowTextarea(el: HTMLTextAreaElement): void {
  // Reset to `auto` first so `scrollHeight` reflects the true content height
  // even after the user deletes text.
  el.style.height = "auto";
  const next = clampAutogrowHeight(el.scrollHeight);
  el.style.height = `${next}px`;
  el.style.overflowY = el.scrollHeight > MAX_COMPOSER_HEIGHT ? "auto" : "hidden";
}

export const ChatComposer = forwardRef<HTMLTextAreaElement, ChatComposerProps>(
  function ChatComposer(
    {
      draft,
      onDraftChange,
      onSubmit,
      onPause,
      onResume,
      isStreaming,
      canResume,
      placeholder,
      isEditLocked = false,
      onSlashDispatch,
    },
    forwardedRef,
  ) {
    const { text } = useI18n();
    const textareaRef = useRef<HTMLTextAreaElement | null>(null);

    // ── v3: slash command state ─────────────────────────────────────────
    const slashState = useMemo(() => parseSlashCommand(draft), [draft]);
    const candidates = useMemo(() => {
      if (slashState.kind === "matching") return slashState.candidates;
      if (slashState.kind === "confirmed") {
        // Highlight exactly the confirmed command so Enter dispatches it.
        return [slashState.command];
      }
      return filterCommandsByPrefix("");
    }, [slashState]);

    const slashOpen =
      slashState.kind === "matching" ||
      (slashState.kind === "confirmed" && candidates.length > 0);

    const [slashIndex, setSlashIndex] = useState(0);

    // Clamp `slashIndex` whenever the candidate list changes so the
    // highlight never points at a missing entry.
    useLayoutEffect(() => {
      if (candidates.length === 0) {
        setSlashIndex(0);
        return;
      }
      setSlashIndex((prev) => {
        if (prev < 0) return 0;
        if (prev >= candidates.length) return candidates.length - 1;
        return prev;
      });
    }, [candidates.length]);

    const sendDisabled = !draft.trim() || isStreaming || isEditLocked || slashOpen;

    function assignTextareaRef(node: HTMLTextAreaElement | null) {
      textareaRef.current = node;
      if (typeof forwardedRef === "function") {
        forwardedRef(node);
      } else if (forwardedRef) {
        forwardedRef.current = node;
      }
    }

    // ── v3: autogrow (Req 1) ────────────────────────────────────────────
    useLayoutEffect(() => {
      const el = textareaRef.current;
      if (el === null) return;
      autogrowTextarea(el);
    }, [draft]);

    function dispatchSlash(cmd: SlashCommand, args: string): void {
      if (onSlashDispatch !== undefined) onSlashDispatch(cmd, args);
      // For `tool`, parent replaces draft with `@tool-name ` via
      // `onInsertMention`; for the other commands the parent also clears
      // the draft explicitly so we don't race. We still clear here to
      // defend against parents that forget.
      if (!cmd.needsArgs) {
        onDraftChange("");
      }
      textareaRef.current?.focus();
    }

    function handleSlashKeyDown(
      event: ReactKeyboardEvent<HTMLTextAreaElement>,
    ): boolean {
      if (slashOpen === false) return false;
      if (candidates.length === 0) {
        if (event.key === "Escape") {
          event.preventDefault();
          onDraftChange("");
          return true;
        }
        return false;
      }

      switch (event.key) {
        case "ArrowDown":
          event.preventDefault();
          setSlashIndex((i) => (i + 1) % candidates.length);
          return true;
        case "ArrowUp":
          event.preventDefault();
          setSlashIndex((i) => (i - 1 + candidates.length) % candidates.length);
          return true;
        case "Enter": {
          event.preventDefault();
          const cmd = candidates[Math.min(slashIndex, candidates.length - 1)];
          if (cmd.needsArgs) {
            // `/tool <name>` — re-parse draft to pull the arg.
            const parsed = parseSlashCommand(draft);
            if (parsed.kind === "confirmed") {
              dispatchSlash(parsed.command, parsed.args);
              return true;
            }
            // `/tool` without an arg yet — keep the menu open.
            return true;
          }
          dispatchSlash(cmd, "");
          return true;
        }
        case "Escape":
          event.preventDefault();
          onDraftChange("");
          return true;
        case "Tab": {
          event.preventDefault();
          const cmd = candidates[Math.min(slashIndex, candidates.length - 1)];
          onDraftChange(replaceSlashPrefix(draft, cmd.name));
          return true;
        }
        default:
          return false;
      }
    }

    function handleKeyDown(event: ReactKeyboardEvent<HTMLTextAreaElement>) {
      if (handleSlashKeyDown(event)) return;
      if (composerShouldSubmit(event.nativeEvent, draft, isStreaming, isEditLocked)) {
        event.preventDefault();
        onSubmit();
        onDraftChange("");
        textareaRef.current?.focus();
      }
    }

    function handleMenuHover(index: number): void {
      setSlashIndex(index);
    }

    function handleMenuSelect(cmd: SlashCommand): void {
      if (cmd.needsArgs) {
        const parsed = parseSlashCommand(draft);
        if (parsed.kind === "confirmed") {
          dispatchSlash(parsed.command, parsed.args);
          return;
        }
        // Auto-complete the name and let the user continue typing.
        onDraftChange(replaceSlashPrefix(draft, cmd.name));
        textareaRef.current?.focus();
        return;
      }
      dispatchSlash(cmd, "");
    }

    return (
      <div className="w-full">
        <div className="mx-auto w-full max-w-[56rem] px-3 sm:px-4 lg:px-6 xl:px-12">
          <div className="relative rounded-3xl border border-slate-200 bg-white p-3 shadow-sm focus-within:border-slate-400">
            <SlashCommandMenu
              open={slashOpen}
              candidates={candidates}
              activeIndex={slashIndex}
              onHover={handleMenuHover}
              onSelect={handleMenuSelect}
            />
            <textarea
              ref={assignTextareaRef}
              value={draft}
              onChange={(event) => onDraftChange(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={placeholder}
              rows={1}
              style={{
                minHeight: `${MIN_COMPOSER_HEIGHT}px`,
                maxHeight: `${MAX_COMPOSER_HEIGHT}px`,
                lineHeight: "20px",
              }}
              className="w-full resize-none overflow-hidden border-0 bg-transparent px-2 py-0.5 text-sm text-slate-800 outline-none placeholder:text-slate-400 focus:outline-none"
              autoFocus
            />
            <div className="mt-1 flex items-center justify-between gap-3 px-2">
              <span className="text-[10px] text-slate-400">
                {text(
                  "Enter 发送 · Shift+Enter 换行 · 输入 / 查看命令",
                  "Enter to send · Shift+Enter for newline · type / for commands",
                )}
              </span>
            </div>
            <div className="mt-2 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                {isStreaming ? (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={onPause}
                    aria-label={text("暂停生成", "Pause generation")}
                  >
                    <Pause className="h-3.5 w-3.5" />
                    {text("暂停", "Pause")}
                  </Button>
                ) : null}
                {!isStreaming && canResume ? (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={onResume}
                    aria-label={text("继续生成", "Resume generation")}
                  >
                    <Play className="h-3.5 w-3.5" />
                    {text("继续", "Resume")}
                  </Button>
                ) : null}
              </div>
              <Button
                type="button"
                variant="primary"
                className="h-10 px-4"
                onClick={() => {
                  if (sendDisabled) return;
                  onSubmit();
                  onDraftChange("");
                  textareaRef.current?.focus();
                }}
                disabled={sendDisabled}
                aria-label={text("发送", "Send")}
              >
                <Send className="h-4 w-4" />
                {text("Enter 发送", "Enter to send")}
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  },
);
