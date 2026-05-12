import {
  forwardRef,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type JSX,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
  type RefObject,
} from "react";

import { FileText, Pause, Play, Send, SlidersHorizontal, X } from "lucide-react";

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
  optionsOpen?: boolean;
  onOptionsToggle?: () => void;
  optionsTriggerRef?: RefObject<HTMLButtonElement | null>;
  metadata?: ReactNode;
  attachments?: ComposerAttachment[];
  onRemoveAttachment?: (id: string) => void;
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

export type ComposerAttachment = {
  id: string;
  name: string;
  mimeType: string;
  previewUrl: string | null;
  sizeBytes: number;
  kind: "image" | "file";
  contentText: string | null;
  contentStatus: "ready" | "unsupported" | "error";
  truncated: boolean;
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
      optionsOpen = false,
      onOptionsToggle,
      optionsTriggerRef,
      metadata = null,
      attachments = [],
      onRemoveAttachment,
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
        <div className="mx-auto w-full max-w-3xl px-3 sm:px-4 lg:px-6">
          <div className="relative rounded-[28px] border border-slate-200 bg-white p-3 shadow-[0_14px_40px_rgba(15,23,42,0.10)] focus-within:border-slate-300">
            <SlashCommandMenu
              open={slashOpen}
              candidates={candidates}
              activeIndex={slashIndex}
              onHover={handleMenuHover}
              onSelect={handleMenuSelect}
            />
            {metadata !== null && <div className="px-3 pb-2">{metadata}</div>}
            {attachments.length > 0 && (
              <div
                className="mb-2 flex gap-2 overflow-x-auto px-3 pb-1"
                aria-label={text("已选择的附件", "Selected attachments")}
              >
                {attachments.map((attachment) => (
                  <AttachmentPreview
                    key={attachment.id}
                    attachment={attachment}
                    onRemove={onRemoveAttachment}
                  />
                ))}
              </div>
            )}
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
              className="w-full resize-none overflow-hidden border-0 bg-transparent px-3 py-1 text-[15px] text-slate-800 outline-none placeholder:text-slate-400 focus:outline-none"
              autoFocus
            />
            <div className="mt-2 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                {onOptionsToggle !== undefined && (
                  <button
                    ref={optionsTriggerRef}
                    type="button"
                    onClick={onOptionsToggle}
                    aria-haspopup="dialog"
                    aria-expanded={optionsOpen}
                    aria-label={text("打开工具", "Open tools")}
                    title={text("工具", "Tools")}
                    className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
                  >
                    <SlidersHorizontal aria-hidden="true" className="h-4 w-4" />
                  </button>
                )}
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
                className="h-10 w-10 rounded-full px-0"
                onClick={() => {
                  if (sendDisabled) return;
                  onSubmit();
                  onDraftChange("");
                  textareaRef.current?.focus();
                }}
                disabled={sendDisabled}
                aria-label={text("发送", "Send")}
                title={text("发送", "Send")}
              >
                <Send className="h-4 w-4" />
                <span className="sr-only">{text("发送", "Send")}</span>
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  },
);

function AttachmentPreview({
  attachment,
  onRemove,
}: {
  attachment: ComposerAttachment;
  onRemove?: (id: string) => void;
}): JSX.Element {
  const { text } = useI18n();
  const sizeLabel = formatAttachmentSize(attachment.sizeBytes);
  const statusLabel = attachmentStatusLabel(attachment, text);
  const removeLabel = text(
    `移除 ${attachment.name}`,
    `Remove ${attachment.name}`,
  );

  return (
    <div className="group relative h-14 w-14 shrink-0 overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
      {attachment.kind === "image" && attachment.previewUrl !== null ? (
        <img
          src={attachment.previewUrl}
          alt={attachment.name}
          className="h-full w-full object-cover"
        />
      ) : (
        <div className="flex h-full w-full flex-col items-center justify-center gap-0.5 px-1 text-slate-500">
          <FileText aria-hidden="true" className="h-4 w-4" />
          <span className="max-w-full truncate text-[9px] leading-3 text-slate-600">
            {attachment.name}
          </span>
          <span className="text-[8px] leading-3 text-slate-400">{sizeLabel}</span>
        </div>
      )}
      <span
        className="absolute bottom-1 left-1 max-w-[48px] truncate rounded-full bg-white/90 px-1 text-[8px] leading-3 text-slate-500 shadow-sm"
        title={statusLabel}
      >
        {statusLabel}
      </span>
      {onRemove !== undefined && (
        <button
          type="button"
          onClick={() => onRemove(attachment.id)}
          aria-label={removeLabel}
          title={removeLabel}
          className="absolute right-1 top-1 inline-flex h-5 w-5 items-center justify-center rounded-full bg-slate-950/75 text-white opacity-100 transition-colors hover:bg-slate-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100"
        >
          <X aria-hidden="true" className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}

function formatAttachmentSize(sizeBytes: number): string {
  if (!Number.isFinite(sizeBytes) || sizeBytes <= 0) return "0 KB";
  if (sizeBytes < 1024 * 1024) return `${Math.max(1, Math.round(sizeBytes / 1024))} KB`;
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
}

function attachmentStatusLabel(
  attachment: ComposerAttachment,
  text: (zh: string, en: string) => string,
): string {
  if (attachment.contentStatus === "ready") {
    return attachment.truncated ? text("已截取", "Clipped") : text("已读取", "Read");
  }
  if (attachment.contentStatus === "error") return text("读取失败", "Failed");
  return text("仅文件", "File only");
}
