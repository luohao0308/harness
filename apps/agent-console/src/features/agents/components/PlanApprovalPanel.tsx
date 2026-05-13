/**
 * PlanApprovalPanel — Harness Agent/terminal-style plan review card (Req 3.1–3.9).
 *
 * Rendered inside the sticky footer of `ChatSurface` only when
 * `planApprovalGate` (Task 2.6) returns `{ visible: true, planNode }`. This
 * component is intentionally **stateless** and **visibility-agnostic**: it
 * never inspects the store or decides whether to mount itself. The parent
 * wires the four callbacks:
 *
 *   - `onApprove`  → parent creates a Plan-Act run from the original user goal
 *   - `onEdit`     → seed the composer draft with `planNode.content` and focus it
 *   - `onDiscard`  → `store.dismissPlanNode(planNode.id)`
 *   - `onClose`    → same as discard today; kept separate for future semantic drift
 *
 * While the parent is dispatching an approval (`isSubmitting === true`), all
 * four buttons are disabled to prevent double-submission (Property 4 / 5).
 *
 * Accessibility (Req 14.2, 14.3, 14.4):
 *   - Outer container uses `role="region"` with a bilingual `aria-label`.
 *   - Icon-only close button carries an explicit `aria-label`; decorative
 *     icons are `aria-hidden`.
 *   - All copy runs through `useI18n().text(zh, en)`; no hard-coded locale.
 */

import type { JSX } from "react";

import { Pencil, PlayCircle, Sparkles, X } from "lucide-react";

import { Button } from "../../../components/ui/button";
import { useI18n } from "../../../lib/i18n";
import type { ConversationNode } from "../../../stores/workspaceStore";

export type PlanApprovalPanelProps = {
  /** Tail assistant+done+plan node. Parent already filtered via planApprovalGate. */
  planNode: ConversationNode;
  /** True while an approve-triggered `stream.driveBranch` is running. */
  isSubmitting: boolean;
  /** "批准并执行" → parent creates a Plan-Act run from the original user goal. */
  onApprove: () => void;
  /** "修改规划" → parent seeds the composer draft and focuses the textarea. */
  onEdit: () => void;
  /** "丢弃" → parent calls `store.dismissPlanNode(planNode.id)`. */
  onDiscard: () => void;
  /** "关闭（X）" → equivalent to discard; split for future semantic divergence. */
  onClose: () => void;
};

export function PlanApprovalPanel({
  planNode: _planNode,
  isSubmitting,
  onApprove,
  onEdit,
  onDiscard,
  onClose,
}: PlanApprovalPanelProps): JSX.Element {
  const { text } = useI18n();

  return (
    <section
      role="region"
      aria-label={text("规划审批", "Plan approval")}
      className="relative rounded-2xl border border-slate-200 bg-white p-3 shadow-sm"
    >
      <button
        type="button"
        onClick={onClose}
        disabled={isSubmitting}
        aria-label={text("关闭规划面板", "Close plan panel")}
        className="absolute right-2 top-2 text-slate-400 transition-colors hover:text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        <X aria-hidden="true" className="h-3.5 w-3.5" />
      </button>

      <div className="flex items-start gap-2 pr-6">
        <Sparkles aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-indigo-600" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-slate-900">
            {text("模型已给出规划，请选择下一步", "A plan is ready — what do you want to do?")}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {text(
              "批准会创建 Plan-Act Run；修改会把规划填回输入框；丢弃会隐藏本次审批。",
              "Approving creates a Plan-Act Run; Edit fills the composer with the plan; Discard dismisses it.",
            )}
          </p>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 pl-6">
        <Button type="button" variant="primary" disabled={isSubmitting} onClick={onApprove}>
          <PlayCircle aria-hidden="true" className="h-3.5 w-3.5" />
          {text("批准并执行", "Approve & run")}
        </Button>
        <Button type="button" variant="secondary" disabled={isSubmitting} onClick={onEdit}>
          <Pencil aria-hidden="true" className="h-3.5 w-3.5" />
          {text("修改规划", "Edit plan")}
        </Button>
        <Button type="button" variant="ghost" disabled={isSubmitting} onClick={onDiscard}>
          {text("丢弃", "Discard")}
        </Button>
      </div>
    </section>
  );
}
