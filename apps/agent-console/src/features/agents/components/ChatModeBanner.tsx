/**
 * ChatModeBanner — inserted above the Composer when `Workspace_Mode ≠ chat`
 * to make the current mode obvious and offer quick-return entry points.
 *
 * Satisfies:
 *   - Req 6.3: when mode is `markdown_plan` or `plan`, a prominent hint banner
 *     is shown with "Back to Chat" and "Create Run" actions.
 *   - Req 9.1: all copy flows through `useI18n().text(zh, en)`.
 *   - Req 9.5: both actions are real `<button>` elements with visible text.
 *
 * Pure presentational component: stateless, no store access, no hooks beyond
 * `useI18n`. The parent (`ChatSurface`) decides when to render this banner.
 */

import type { JSX } from "react";
import { MessageCircle, Sparkles } from "lucide-react";

import { Button } from "../../../components/ui/button";
import { useI18n } from "../../../lib/i18n";
import { cn } from "../../../lib/utils";
import type { WorkspaceMode } from "../lib/types";

export type ChatModeBannerProps = {
  /** Parent only renders the banner in the two non-chat modes. */
  mode: Exclude<WorkspaceMode, "chat">;
  /** Switch the Workspace_Mode back to `"chat"`. */
  onSwitchToChat: () => void;
  /** Navigate to the Run creation flow (parent decides the destination). */
  onOpenCreateRun: () => void;
};

export function ChatModeBanner({
  mode,
  onSwitchToChat,
  onOpenCreateRun,
}: ChatModeBannerProps): JSX.Element {
  const { text } = useI18n();
  const isPlan = mode === "plan" || mode === "goal";

  const copy = isPlan
    ? text(
        mode === "goal"
          ? "当前是追求目标模式，提交会创建可执行运行并持续推进目标。"
          : "当前是规划后执行运行模式，提交会直接创建可执行运行。",
        mode === "goal"
          ? "Currently in Goal pursuit mode — submitting will create an executable Run and pursue the goal."
          : "Currently in Plan-Act Run mode — submitting will create an executable Run immediately.",
      )
    : text(
        "当前是规划文本模式，不执行工具。切回对话或去创建规划后执行运行。",
        "Currently in Plan (markdown) mode — no tools will run. Switch back to Chat or create a Plan-Act Run.",
      );

  const backLabel = text("切回对话", "Back to Chat");
  const createLabel = text("创建运行", "Create Run");

  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-3 rounded-xl border px-3 py-2 text-xs",
        isPlan
          ? "border-amber-200 bg-amber-50 text-amber-900"
          : "border-blue-200 bg-blue-50 text-blue-900",
      )}
    >
      <span className="flex items-center gap-2">
        <Sparkles aria-hidden="true" className="h-3.5 w-3.5" />
        <span>{copy}</span>
      </span>
      <div className="flex items-center gap-2">
        <Button variant="ghost" onClick={onSwitchToChat} aria-label={backLabel}>
          <MessageCircle aria-hidden="true" className="h-3.5 w-3.5" />
          {backLabel}
        </Button>
        <Button variant="secondary" onClick={onOpenCreateRun} aria-label={createLabel}>
          {createLabel}
        </Button>
      </div>
    </div>
  );
}
