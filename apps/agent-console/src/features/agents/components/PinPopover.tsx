/**
 * PinPopover — chip showing pinned-node count + popover list with unpin
 * actions (Req 6.1, 6.3, 6.4, 6.7, 6.8, 14.2).
 *
 * - The trigger chip reads "Pin · {n}" where `n = pinnedNodes.length`.
 * - While open the popover renders a 320px-wide card above the chip listing
 *   every pinned node with role badge, 40-char snippet and relative time.
 * - Each row exposes an icon-only "取消固定 / Unpin" button.
 * - Empty state shows a bilingual placeholder so the popover never renders
 *   an empty DOM sub-tree.
 * - `useOutsideClick` (mousedown / touchstart / Escape) closes the popover
 *   just like `ContextPopover`.
 *
 * v4 additive (Req 4.6): `PinPopoverContent` is exported so
 * `ComposerOptionsPopover` can embed the pinned-list UI in its Pinned
 * section without nesting a second popover shell. `PinPopover` (default)
 * retains v3 behaviour.
 */

import { useRef, useState, type JSX } from "react";
import { Pin, X } from "lucide-react";

import type { ConversationNode, ConversationRole } from "../../../stores/workspaceStore";
import { useI18n } from "../../../lib/i18n";
import { Button } from "../../../components/ui/button";
import { useOutsideClick } from "../hooks/useOutsideClick";
import { formatRelativeTime } from "../lib/relativeTime";

export type PinPopoverProps = {
  /** Parent derives this from `useWorkspaceStore` — never imported here. */
  pinnedNodes: ConversationNode[];
  onUnpin: (nodeId: string) => void;
};

function roleLabel(role: ConversationRole, isChinese: boolean): string {
  switch (role) {
    case "user":
      return isChinese ? "用户" : "User";
    case "assistant":
      return isChinese ? "模型" : "Assistant";
    case "system":
      return isChinese ? "系统" : "System";
    case "tool":
      return isChinese ? "工具" : "Tool";
  }
}

function snippetOf(content: string): string {
  const trimmed = content.trim();
  if (trimmed.length <= 40) return trimmed;
  return `${trimmed.slice(0, 40)}…`;
}

function parseCreatedAt(iso: string): number {
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : 0;
}

/**
 * Headless list of pinned messages (v4 / Req 4.6). Embeds inside
 * `ComposerOptionsPopover` without re-wrapping in its own popover shell.
 * The default `PinPopover` below keeps the v3 chip + dropdown flow.
 */
export function PinPopoverContent({
  pinnedNodes,
  onUnpin,
}: PinPopoverProps): JSX.Element {
  const { text, isChinese } = useI18n();
  const nowMs = Date.now();
  const locale = isChinese ? "zh-CN" : "en";

  if (pinnedNodes.length === 0) {
    return (
      <div className="text-xs text-slate-400">
        {text("暂无固定消息", "No pinned messages")}
      </div>
    );
  }

  return (
    <ul className="flex max-h-[320px] flex-col gap-2 overflow-y-auto">
      {pinnedNodes.map((node) => {
        const createdMs = parseCreatedAt(node.created_at);
        const relative = formatRelativeTime(createdMs, nowMs, locale);
        return (
          <li
            key={node.id}
            className="flex items-start gap-2 rounded-lg border border-slate-100 p-2"
          >
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <div className="flex items-center gap-2 text-[11px] text-slate-500">
                <span className="rounded-full bg-slate-100 px-1.5 py-0.5 font-medium text-slate-600">
                  {roleLabel(node.role, isChinese)}
                </span>
                {relative !== "" && (
                  <span title={node.created_at}>{relative}</span>
                )}
              </div>
              <p className="break-words text-xs text-slate-700">
                {snippetOf(node.content)}
              </p>
            </div>
            <button
              type="button"
              onClick={() => onUnpin(node.id)}
              aria-label={text("取消固定", "Unpin")}
              className="inline-flex h-6 w-6 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
            >
              <X aria-hidden="true" className="h-3.5 w-3.5" />
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export function PinPopover({ pinnedNodes, onUnpin }: PinPopoverProps): JSX.Element {
  const { text } = useI18n();
  const [open, setOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  useOutsideClick(popoverRef, () => setOpen(false), open);

  return (
    <div ref={popoverRef} className="relative inline-block">
      <Button
        type="button"
        variant="secondary"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={text("已固定消息", "Pinned messages")}
      >
        <Pin aria-hidden="true" className="h-3.5 w-3.5" />
        <span>
          {text("固定", "Pin")} · {pinnedNodes.length}
        </span>
      </Button>
      {open && (
        <div
          role="dialog"
          aria-label={text("已固定消息", "Pinned messages")}
          className="absolute bottom-full left-0 z-20 mb-2 w-[320px] rounded-2xl border border-slate-200 bg-white p-3 shadow-lg"
        >
          <PinPopoverContent pinnedNodes={pinnedNodes} onUnpin={onUnpin} />
        </div>
      )}
    </div>
  );
}
