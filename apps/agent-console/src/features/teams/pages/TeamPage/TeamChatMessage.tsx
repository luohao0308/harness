import { ExternalLink, FlaskConical, GitBranch } from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "../../../../components/ui/badge";
import { useI18n } from "../../../../lib/i18n";
import { statusLabel } from "../../../../lib/labels";
import { BranchSwitcher } from "../../../agents/components/BranchSwitcher";
import { ChatMessageBubble } from "../../../agents/components/ChatMessageBubble";
import type { InspectorSection } from "../../../agents/lib/types";
import type { ConversationNode } from "../../../../stores/workspaceStore";

import type { TeamBranchGroup, TeamConversationEntry } from "./types";

export function TeamChatMessage({
  entry,
  entries,
  branchGroups,
  editingMessageId,
  pinnedMessageIds,
  canRegenerate,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onCopy,
  onRegenerate,
  onTogglePin,
  onOpenInspector,
  onBranch,
  onSwitchBranch,
}: {
  entry: TeamConversationEntry;
  entries: TeamConversationEntry[];
  branchGroups: Record<string, TeamBranchGroup>;
  editingMessageId: string | null;
  pinnedMessageIds: string[];
  canRegenerate: boolean;
  onStartEdit: (nodeId: string) => void;
  onCancelEdit: () => void;
  onSaveEdit: (nodeId: string, newContent: string) => void;
  onCopy: (nodeId: string) => Promise<boolean>;
  onRegenerate: (nodeId: string) => void;
  onTogglePin: (nodeId: string) => void;
  onOpenInspector: (section: InspectorSection, node: ConversationNode) => void;
  onBranch: (nodeId: string, entries: TeamConversationEntry[]) => void;
  onSwitchBranch: (anchorUserId: string, nodeId: string) => void;
}) {
  const branchGroup = Object.values(branchGroups).find((group) =>
    group.branchNodeIds.includes(entry.node.id),
  );
  const branchIndex =
    branchGroup?.branchNodeIds.findIndex((nodeId) => nodeId === entry.node.id) ?? -1;
  return (
    <div data-conversation-node-id={entry.node.id} className="space-y-1">
      <ChatMessageBubble
        node={entry.node}
        onOpenInspector={(section) => onOpenInspector(section, entry.node)}
        editingNodeId={editingMessageId}
        onStartEdit={onStartEdit}
        onCancelEdit={onCancelEdit}
        onSaveEdit={onSaveEdit}
        canRegenerate={canRegenerate}
        isStreaming={false}
        onCopy={onCopy}
        onRegenerate={onRegenerate}
        isPinned={pinnedMessageIds.includes(entry.node.id)}
        onTogglePin={onTogglePin}
        onBranch={entry.node.role === "assistant" ? () => onBranch(entry.node.id, entries) : undefined}
      />
      {branchGroup && branchIndex >= 0 ? (
        <div className="ml-11 flex justify-start">
          <BranchSwitcher
            currentIndex={branchIndex + 1}
            totalBranches={branchGroup.branchNodeIds.length}
            onPrevious={() => {
              const previous = branchGroup.branchNodeIds[branchIndex - 1];
              if (previous) onSwitchBranch(branchGroup.anchorUserId, previous);
            }}
            onNext={() => {
              const next = branchGroup.branchNodeIds[branchIndex + 1];
              if (next) onSwitchBranch(branchGroup.anchorUserId, next);
            }}
          />
        </div>
      ) : null}
      {entry.node.run_id ? (
        <TeamMessageRunLinks
          runId={entry.node.run_id}
          runStatus={entry.runStatus}
          runCreatedAt={entry.runCreatedAt}
        />
      ) : null}
    </div>
  );
}

export function TeamMessageRunLinks({
  runId,
  runStatus,
  runCreatedAt,
}: {
  runId: string;
  runStatus?: string;
  runCreatedAt?: string;
}) {
  const { text } = useI18n();
  const createdAt = runCreatedAt ? new Date(runCreatedAt) : null;
  const createdLabel =
    createdAt && Number.isFinite(createdAt.getTime())
      ? createdAt.toLocaleString()
      : null;
  return (
    <div className="ml-11 flex flex-wrap items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] text-slate-600 shadow-sm">
      <GitBranch aria-hidden="true" className="h-3.5 w-3.5 text-slate-500" />
      <span className="font-mono text-slate-800">运行 {runId.slice(0, 8)}</span>
      {runStatus ? <Badge tone="info">{statusLabel(runStatus)}</Badge> : null}
      {createdLabel ? <span className="hidden text-slate-400 sm:inline">{createdLabel}</span> : null}
      <div className="ml-auto flex items-center gap-1">
        <Link
          to={`/runs/${runId}`}
          aria-label={text("查看运行详情", "Open run detail")}
          className="inline-flex h-7 items-center gap-1 rounded-md px-2 font-medium text-slate-700 hover:bg-slate-100"
        >
          <ExternalLink aria-hidden="true" className="h-3 w-3" />
          <span>{text("运行", "Run")}</span>
        </Link>
        <Link
          to={`/evals?run=${encodeURIComponent(runId)}`}
          aria-label={text("打开评测中心", "Open Eval Harness")}
          className="inline-flex h-7 items-center gap-1 rounded-md px-2 font-medium text-slate-700 hover:bg-slate-100"
        >
          <FlaskConical aria-hidden="true" className="h-3 w-3" />
          <span>{text("评测", "Eval")}</span>
        </Link>
      </div>
    </div>
  );
}
