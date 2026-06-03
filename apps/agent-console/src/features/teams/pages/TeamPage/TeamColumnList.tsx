import { ChevronLeft, ChevronRight } from "lucide-react";
import type { MutableRefObject } from "react";

import { cn } from "../../../../lib/utils";
import type { ComposerAttachment } from "../../../agents/components/ChatComposer";
import type { InspectorSection, WorkspaceMode } from "../../../agents/lib/types";
import type { ContextCompressionSummary } from "../../../agents/lib/contextCompression";
import type { ConversationNode } from "../../../../stores/workspaceStore";
import type { Team, TeamAgent, TeamMailboxMessage, TeamTask, ToolMetadata } from "../../../tasks/api";

import { AgentColumn } from "./AgentColumn";
import { agentMessages, defaultComposerTarget, teamPendingSendKey } from "./conversation";
import type {
  ComposerState,
  PendingSend,
  SettledWakeCutoffs,
  StreamingWake,
  TeamBottomPanel,
  TeamBranchGroupsBySlot,
  TeamComposerState,
  TeamComposerStateUpdater,
  TeamContextCompressions,
  TeamConversationEntry,
  TeamModelChangeHandler,
  TextFn,
} from "./types";

type ComposerSharedProps = {
  modelOptions: Parameters<typeof AgentColumn>[0]["modelOptions"];
  contextMaxTokens: number;
  autoCompressionRatio: number;
  onContextMaxTokensChange: (value: number) => void;
  onAutoCompressionRatioChange: (value: number) => void;
  onClearContextCompression: (slotId: string, branchKey: string) => void;
  addComposerFiles: (slotId: string) => void;
  handleComposerFilesSelected: Parameters<typeof AgentColumn>[0]["handleComposerFilesSelected"];
  removeComposerAttachment: (slotId: string, attachmentId: string) => void;
  setComposerBottomPanel: (slotId: string, panel: TeamBottomPanel) => void;
  onModelChange: TeamModelChangeHandler;
};

export function TeamColumnList({
  activeTeam,
  orderedAgents,
  selectedAgent,
  selectedComposer,
  tasks,
  messages,
  pendingSends,
  pendingWakeSlotIds,
  streamingWakes,
  settledWakeCutoffs,
  composerState,
  attachmentsBySlotId,
  bottomPanelBySlotId,
  toolsByAgentId,
  editingMessageId,
  pinnedMessageIds,
  branchGroupsBySlotId,
  contextCompressionsBySlotId,
  fullscreenSlotId,
  isNarrowColumns,
  columnOverflow,
  flashingSlotId,
  columnsContainerRef,
  scrollRefs,
  teamFileInputsRef,
  composerSharedProps,
  text,
  onCompressContext,
  onComposerChange,
  onSendFromComposer,
  onMessageActionSend,
  onBranchMessage,
  onSwitchBranch,
  onStartMessageEdit,
  onCancelMessageEdit,
  onTogglePin,
  onOpenMessageInspector,
  onStopWake,
  onToggleFullscreen,
  onRemoveAgent,
  onFocusAgent,
  onScrollColumns,
}: {
  activeTeam: Team;
  orderedAgents: TeamAgent[];
  selectedAgent: TeamAgent | null;
  selectedComposer: TeamComposerState;
  tasks: TeamTask[];
  messages: TeamMailboxMessage[];
  pendingSends: PendingSend[];
  pendingWakeSlotIds: string[];
  streamingWakes: StreamingWake[];
  settledWakeCutoffs: SettledWakeCutoffs;
  composerState: ComposerState;
  attachmentsBySlotId: Record<string, ComposerAttachment[]>;
  bottomPanelBySlotId: Record<string, TeamBottomPanel>;
  toolsByAgentId: Map<string, ToolMetadata[]>;
  editingMessageId: string | null;
  pinnedMessageIds: string[];
  branchGroupsBySlotId: TeamBranchGroupsBySlot;
  contextCompressionsBySlotId: TeamContextCompressions;
  fullscreenSlotId: string | null;
  isNarrowColumns: boolean;
  columnOverflow: { left: boolean; right: boolean };
  flashingSlotId: string | null;
  columnsContainerRef: MutableRefObject<HTMLDivElement | null>;
  scrollRefs: MutableRefObject<Record<string, HTMLDivElement | null>>;
  teamFileInputsRef: MutableRefObject<Record<string, HTMLInputElement | null>>;
  composerSharedProps: ComposerSharedProps;
  text: TextFn;
  onCompressContext: (
    agent: TeamAgent,
    entries: TeamConversationEntry[],
    reason?: "manual" | "background" | "pre_send",
  ) => Promise<ContextCompressionSummary | null>;
  onComposerChange: (slotId: string, next: TeamComposerStateUpdater) => void;
  onSendFromComposer: (
    agent: TeamAgent,
    content: string,
    target: string,
    attachments: ComposerAttachment[],
    mode: WorkspaceMode,
  ) => void;
  onMessageActionSend: (sourceSlotId: string, content: string, target: string) => void;
  onBranchMessage: (agent: TeamAgent, entries: TeamConversationEntry[], nodeId: string) => void;
  onSwitchBranch: (slotId: string, anchorUserId: string, nodeId: string) => void;
  onStartMessageEdit: (nodeId: string) => void;
  onCancelMessageEdit: () => void;
  onTogglePin: (nodeId: string) => void;
  onOpenMessageInspector: (section: InspectorSection, node: ConversationNode) => void;
  onStopWake: (slotId: string) => void;
  onToggleFullscreen: (slotId: string) => void;
  onRemoveAgent: (agent: TeamAgent) => void;
  onFocusAgent: (slotId: string) => void;
  onScrollColumns: (direction: "left" | "right") => void;
}) {
  return (
    <div className="relative flex min-h-0 flex-1">
      <div className="min-w-0 flex-1">
        {!isNarrowColumns ? (
          <div className="relative h-full min-h-0">
            <div
              ref={columnsContainerRef}
              role="group"
              aria-label={text("代理会话列", "Agent columns")}
              className={cn(
                "flex h-full min-h-0 w-full snap-x snap-proximity overflow-x-auto overflow-y-hidden bg-slate-50/40 [scrollbar-width:none]",
                (fullscreenSlotId ? 1 : orderedAgents.length) <= 2 ? "justify-start" : "",
              )}
            >
              {(fullscreenSlotId
                ? orderedAgents.filter((agent) => agent.slot_id === fullscreenSlotId)
                : orderedAgents
              ).map((agent) => (
                <TeamAgentColumn
                  key={agent.slot_id}
                  activeTeam={activeTeam}
                  agent={agent}
                  visibleColumnCount={fullscreenSlotId ? 1 : orderedAgents.length}
                  tasks={tasks}
                  messages={messages}
                  pendingSends={pendingSends}
                  pendingWakeSlotIds={pendingWakeSlotIds}
                  streamingWakes={streamingWakes}
                  settledWakeCutoffs={settledWakeCutoffs}
                  composer={composerState[agent.slot_id] ?? { draft: "" }}
                  attachments={attachmentsBySlotId[agent.slot_id] ?? []}
                  bottomPanel={bottomPanelBySlotId[agent.slot_id] ?? null}
                  tools={toolsByAgentId.get(agent.agent_id) ?? []}
                  editingMessageId={editingMessageId}
                  pinnedMessageIds={pinnedMessageIds}
                  branchGroups={branchGroupsBySlotId[agent.slot_id] ?? {}}
                  contextCompressions={contextCompressionsBySlotId[agent.slot_id] ?? {}}
                  fullscreen={fullscreenSlotId === agent.slot_id}
                  isFlashing={flashingSlotId === agent.slot_id}
                  scrollRefs={scrollRefs}
                  teamFileInputsRef={teamFileInputsRef}
                  composerSharedProps={composerSharedProps}
                  text={text}
                  onCompressContext={onCompressContext}
                  onComposerChange={onComposerChange}
                  onSendFromComposer={onSendFromComposer}
                  onMessageActionSend={onMessageActionSend}
                  onBranchMessage={onBranchMessage}
                  onSwitchBranch={onSwitchBranch}
                  onStartMessageEdit={onStartMessageEdit}
                  onCancelMessageEdit={onCancelMessageEdit}
                  onTogglePin={onTogglePin}
                  onOpenMessageInspector={onOpenMessageInspector}
                  onStopWake={onStopWake}
                  onToggleFullscreen={onToggleFullscreen}
                  onRemoveAgent={onRemoveAgent}
                  onFocusAgent={onFocusAgent}
                />
              ))}
            </div>
            <ScrollButton
              visible={columnOverflow.left}
              direction="left"
              label={text("向左滚动代理列", "Scroll agent columns left")}
              onClick={() => onScrollColumns("left")}
            />
            <ScrollButton
              visible={columnOverflow.right}
              direction="right"
              label={text("向右滚动代理列", "Scroll agent columns right")}
              onClick={() => onScrollColumns("right")}
            />
          </div>
        ) : null}

        {isNarrowColumns && selectedAgent ? (
          <div className="flex min-h-0 flex-1">
            <TeamAgentColumn
              activeTeam={activeTeam}
              agent={selectedAgent}
              tasks={tasks}
              messages={messages}
              pendingSends={pendingSends}
              pendingWakeSlotIds={pendingWakeSlotIds}
              streamingWakes={streamingWakes}
              settledWakeCutoffs={settledWakeCutoffs}
              composer={selectedComposer}
              attachments={attachmentsBySlotId[selectedAgent.slot_id] ?? []}
              bottomPanel={bottomPanelBySlotId[selectedAgent.slot_id] ?? null}
              tools={toolsByAgentId.get(selectedAgent.agent_id) ?? []}
              editingMessageId={editingMessageId}
              pinnedMessageIds={pinnedMessageIds}
              branchGroups={branchGroupsBySlotId[selectedAgent.slot_id] ?? {}}
              contextCompressions={contextCompressionsBySlotId[selectedAgent.slot_id] ?? {}}
              isFlashing={flashingSlotId === selectedAgent.slot_id}
              scrollRefs={scrollRefs}
              teamFileInputsRef={teamFileInputsRef}
              composerSharedProps={composerSharedProps}
              text={text}
              onCompressContext={onCompressContext}
              onComposerChange={onComposerChange}
              onSendFromComposer={onSendFromComposer}
              onMessageActionSend={onMessageActionSend}
              onBranchMessage={onBranchMessage}
              onSwitchBranch={onSwitchBranch}
              onStartMessageEdit={onStartMessageEdit}
              onCancelMessageEdit={onCancelMessageEdit}
              onTogglePin={onTogglePin}
              onOpenMessageInspector={onOpenMessageInspector}
              onStopWake={onStopWake}
              onToggleFullscreen={onToggleFullscreen}
              onRemoveAgent={onRemoveAgent}
              onFocusAgent={onFocusAgent}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}

function TeamAgentColumn({
  activeTeam,
  agent,
  tasks,
  messages,
  pendingSends,
  pendingWakeSlotIds,
  streamingWakes,
  settledWakeCutoffs,
  composer,
  attachments,
  bottomPanel,
  tools,
  editingMessageId,
  pinnedMessageIds,
  branchGroups,
  contextCompressions,
  visibleColumnCount,
  fullscreen,
  isFlashing,
  scrollRefs,
  teamFileInputsRef,
  composerSharedProps,
  text,
  onCompressContext,
  onComposerChange,
  onSendFromComposer,
  onMessageActionSend,
  onBranchMessage,
  onSwitchBranch,
  onStartMessageEdit,
  onCancelMessageEdit,
  onTogglePin,
  onOpenMessageInspector,
  onStopWake,
  onToggleFullscreen,
  onRemoveAgent,
  onFocusAgent,
}: {
  activeTeam: Team;
  agent: TeamAgent;
  tasks: TeamTask[];
  messages: TeamMailboxMessage[];
  pendingSends: PendingSend[];
  pendingWakeSlotIds: string[];
  streamingWakes: StreamingWake[];
  settledWakeCutoffs: SettledWakeCutoffs;
  composer: TeamComposerState;
  attachments: ComposerAttachment[];
  bottomPanel: TeamBottomPanel;
  tools: ToolMetadata[];
  editingMessageId: string | null;
  pinnedMessageIds: string[];
  branchGroups: Parameters<typeof AgentColumn>[0]["branchGroups"];
  contextCompressions: Record<string, ContextCompressionSummary>;
  visibleColumnCount?: number;
  fullscreen?: boolean;
  isFlashing?: boolean;
  scrollRefs: MutableRefObject<Record<string, HTMLDivElement | null>>;
  teamFileInputsRef: MutableRefObject<Record<string, HTMLInputElement | null>>;
  composerSharedProps: ComposerSharedProps;
  text: TextFn;
  onCompressContext: (
    agent: TeamAgent,
    entries: TeamConversationEntry[],
    reason?: "manual" | "background" | "pre_send",
  ) => Promise<ContextCompressionSummary | null>;
  onComposerChange: (slotId: string, next: TeamComposerStateUpdater) => void;
  onSendFromComposer: (
    agent: TeamAgent,
    content: string,
    target: string,
    attachments: ComposerAttachment[],
    mode: WorkspaceMode,
  ) => void;
  onMessageActionSend: (sourceSlotId: string, content: string, target: string) => void;
  onBranchMessage: (agent: TeamAgent, entries: TeamConversationEntry[], nodeId: string) => void;
  onSwitchBranch: (slotId: string, anchorUserId: string, nodeId: string) => void;
  onStartMessageEdit: (nodeId: string) => void;
  onCancelMessageEdit: () => void;
  onTogglePin: (nodeId: string) => void;
  onOpenMessageInspector: (section: InspectorSection, node: ConversationNode) => void;
  onStopWake: (slotId: string) => void;
  onToggleFullscreen: (slotId: string) => void;
  onRemoveAgent: (agent: TeamAgent) => void;
  onFocusAgent: (slotId: string) => void;
}) {
  const selectedTarget = defaultComposerTarget(agent);
  const selectedMode = composer.mode ?? "chat";
  const selectedFiles = attachments.map((attachment) => attachment.name);
  const isSending = pendingSends.some((send) => (
    send.key === teamPendingSendKey(
      agent.slot_id,
      selectedTarget,
      selectedMode,
      composer.draft.trim(),
      selectedFiles,
    ) ||
    (
      send.sourceSlotId === agent.slot_id &&
      send.target === selectedTarget &&
      send.content === composer.draft.trim() &&
      send.mode === selectedMode &&
      send.files.join("\n") === selectedFiles.join("\n")
    )
  ));

  return (
    <AgentColumn
      team={activeTeam}
      agent={agent}
      text={text}
      tasks={tasks}
      messages={agentMessages(agent, messages)}
      pendingSends={pendingSends}
      pendingWakeSlotIds={pendingWakeSlotIds}
      streamingWakes={streamingWakes}
      settledWakeCutoffs={settledWakeCutoffs}
      composer={composer}
      attachments={attachments}
      bottomPanel={bottomPanel}
      tools={tools}
      isSending={isSending}
      editingMessageId={editingMessageId}
      pinnedMessageIds={pinnedMessageIds}
      branchGroups={branchGroups}
      contextCompressions={contextCompressions}
      onCompressContext={onCompressContext}
      visibleColumnCount={visibleColumnCount}
      fullscreen={fullscreen}
      onComposerChange={(next) => onComposerChange(agent.slot_id, next)}
      onSend={(content, target, mode) => onSendFromComposer(agent, content, target, attachments, mode)}
      onMessageActionSend={(content, target) => onMessageActionSend(agent.slot_id, content, target)}
      onBranchMessage={(nodeId, entries) => onBranchMessage(agent, entries, nodeId)}
      onSwitchBranch={(anchorUserId, nodeId) => onSwitchBranch(agent.slot_id, anchorUserId, nodeId)}
      onStartMessageEdit={onStartMessageEdit}
      onCancelMessageEdit={onCancelMessageEdit}
      onTogglePin={onTogglePin}
      onOpenMessageInspector={onOpenMessageInspector}
      onStopWake={() => onStopWake(agent.slot_id)}
      onFullscreen={() => onToggleFullscreen(agent.slot_id)}
      onRemove={() => onRemoveAgent(agent)}
      onFocus={() => onFocusAgent(agent.slot_id)}
      isFlashing={isFlashing}
      setScrollRef={(node) => {
        scrollRefs.current[agent.slot_id] = node;
      }}
      fileInputRef={(node) => {
        teamFileInputsRef.current[agent.slot_id] = node;
      }}
      {...composerSharedProps}
    />
  );
}

function ScrollButton({
  visible,
  direction,
  label,
  onClick,
}: {
  visible: boolean;
  direction: "left" | "right";
  label: string;
  onClick: () => void;
}) {
  if (!visible) return null;
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className={cn(
        "absolute top-1/2 inline-flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-md border border-slate-200 bg-white/95 text-slate-600 shadow-panel hover:bg-slate-50 hover:text-slate-950",
        direction === "left" ? "left-2" : "right-2",
      )}
    >
      {direction === "left" ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
    </button>
  );
}
