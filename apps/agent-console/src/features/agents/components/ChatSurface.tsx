/**
 * ChatSurface — the three-row Workspace chat viewport (v3).
 *
 * Layout (Req 1 unchanged / Req 3, Req 6 v3 updates):
 *   ┌──────────────────────────────────────┐
 *   │  sticky top-0  TopMetaBar (v3 紧凑版) │  agent / model / mode? / streaming / Stop / Inspector↓ / Run Detail
 *   ├──────────────────────────────────────┤
 *   │  flex-1 min-h-0 ChatMessageList      │  scroll + auto-follow + jump button
 *   ├──────────────────────────────────────┤
 *   │  sticky bottom-0                      │
 *   │    PlanApprovalPanel? (gate)         │
 *   │    MetadataStrip (v3 迁移到此)       │  Req 3: not in header anymore
 *   │    ComposerToolbar                   │  popovers / usage / export / clear
 *   │    ChatComposer (isEditLocked)       │  autogrow + slash menu
 *   └──────────────────────────────────────┘
 *
 * v3 deltas vs v2:
 *   - MetadataStrip moved out of TopMetaBar into the footer (Req 3).
 *   - Three Inspector header buttons collapsed into `<InspectorMenu>` (Req 6.2).
 *   - `<ChatModeBanner>` removed from JSX (Req 6.3).
 *   - Workspace_Mode badge hidden in `chat` mode (Req 6.4).
 *   - Slash-command dispatcher wires composer `/` actions to store / page.
 */

import { useCallback, useMemo, useRef, useState, type JSX } from "react";
import { Link, useNavigate } from "react-router-dom";
import { GitBranch, Sparkles, Square } from "lucide-react";

import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { useI18n } from "../../../lib/i18n";
import {
  useWorkspaceStore,
  type ConversationNode,
} from "../../../stores/workspaceStore";
import type { ToolMetadata } from "../../tasks/api";
import type { ChatStreamController } from "../hooks/useChatStream";
import { canResume as canResumeQuery } from "../lib/activePathQueries";
import { copyText } from "../lib/clipboard";
import { stripThinkBlocks } from "../lib/copyText";
import { computeContextUsage } from "../lib/contextUsage";
import { planApprovalGate } from "../lib/planApprovalGate";
import type { SlashCommand } from "../lib/slashCommands";
import type { InspectorSection, WorkspaceMode } from "../lib/types";
import { ChatComposer } from "./ChatComposer";
import { ChatMessageList, type ChatMessageListHandle } from "./ChatMessageList";
import { ComposerOptionsPopover } from "./ComposerOptionsPopover";
import { ComposerToolbar } from "./ComposerToolbar";
import { InspectorMenu } from "./InspectorMenu";
import { MetadataStrip } from "./MetadataStrip";
import type { ModelOption } from "./ModelPicker";
import { PlanApprovalPanel } from "./PlanApprovalPanel";

export type ChatSurfaceProps = {
  agentId: string;
  agentName: string;
  modelLabel: string;
  modelLabelIsFallback: boolean;
  workspaceMode: WorkspaceMode;
  onWorkspaceModeChange: (mode: WorkspaceMode) => void;
  activeRunId: string | null;
  runStatus?: string;
  runCreatedAt?: string;
  onOpenInspector: (section: InspectorSection) => void;
  stream: ChatStreamController;

  tools: ToolMetadata[];
  providers: ModelOption[];
  selectedProviderId: string | null;
  selectedModelId: string | null;
  onModelChange: (providerId: string, modelId: string) => void;
  onExport: (format: "markdown" | "json") => void;
  onClearConversation: () => void;

  // v3 additive: slash-command dispatch targets
  onOpenSearch: () => void;
  onOpenShortcut: () => void;
  /** Monotonic counter; incrementing it pops the ModelPicker dropdown. */
  modelPickerOpenSeq: number;
  onRequestModelPicker: () => void;
};

export function ChatSurface(props: ChatSurfaceProps): JSX.Element {
  const {
    agentId,
    agentName,
    modelLabel,
    modelLabelIsFallback,
    workspaceMode,
    onWorkspaceModeChange,
    activeRunId,
    runStatus,
    runCreatedAt,
    onOpenInspector,
    stream,
    tools,
    providers,
    selectedProviderId,
    selectedModelId,
    onModelChange,
    onExport,
    onClearConversation,
    onOpenSearch,
    onOpenShortcut,
    modelPickerOpenSeq,
    onRequestModelPicker,
  } = props;

  const { text } = useI18n();
  const navigate = useNavigate();

  const draft = useWorkspaceStore((state) => state.draft);
  const setDraft = useWorkspaceStore((state) => state.setDraft);
  const nodesById = useWorkspaceStore((state) => state.nodesById);
  const rootNodeId = useWorkspaceStore((state) => state.rootNodeId);
  const activeLeafId = useWorkspaceStore((state) => state.activeLeafId);
  const pinnedNodeIds = useWorkspaceStore((state) => state.pinnedNodeIds);
  const togglePinned = useWorkspaceStore((state) => state.togglePinned);
  const contextWindowTurns = useWorkspaceStore((state) => state.contextWindowTurns);
  const setContextWindowTurns = useWorkspaceStore((state) => state.setContextWindowTurns);
  const contextMaxTokens = useWorkspaceStore((state) => state.contextMaxTokens);
  const setContextMaxTokens = useWorkspaceStore((state) => state.setContextMaxTokens);
  const dismissedPlanNodeIds = useWorkspaceStore((state) => state.dismissedPlanNodeIds);
  const dismissPlanNode = useWorkspaceStore((state) => state.dismissPlanNode);
  const activeStream = useWorkspaceStore((state) => state.activeStream);

  const activePath = useMemo(
    () => buildActivePath(nodesById, activeLeafId, rootNodeId),
    [nodesById, activeLeafId, rootNodeId],
  );

  const pinnedNodes = useMemo<ConversationNode[]>(
    () =>
      pinnedNodeIds
        .map((id) => nodesById[id])
        .filter((node): node is ConversationNode => Boolean(node)),
    [pinnedNodeIds, nodesById],
  );

  const tail = activePath.length > 0 ? activePath[activePath.length - 1] : null;
  const canResume = canResumeQuery(activePath);
  const placeholder = composerPlaceholder(workspaceMode, text);

  const usage = useMemo(
    () => computeContextUsage(activePath, contextWindowTurns, contextMaxTokens),
    [activePath, contextWindowTurns, contextMaxTokens],
  );

  const planGate = useMemo(
    () =>
      planApprovalGate({
        activePath,
        activeStreamNodeId: activeStream?.node_id ?? null,
        dismissedPlanNodeIds,
      }),
    [activePath, activeStream, dismissedPlanNodeIds],
  );

  const [editingNodeId, setEditingNodeId] = useState<string | null>(null);
  const [planSubmitting, setPlanSubmitting] = useState(false);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const optionsTriggerRef = useRef<HTMLButtonElement | null>(null);
  const chatListRef = useRef<ChatMessageListHandle | null>(null);

  // ─── Composer callbacks ────────────────────────────────────────────────
  const handleSubmit = useCallback((): void => {
    const goal = draft.trim();
    if (goal.length === 0) return;
    if (stream.isStreaming) return;

    if (workspaceMode === "plan") {
      const message = text(
        "确认创建 Plan-Act Run？此操作会触发可执行的 Run。",
        "Create a Plan-Act Run? This triggers an executable run.",
      );
      if (!window.confirm(message)) return;
    }

    chatListRef.current?.notifyUserSubmit();
    void stream.start({ goal, mode: workspaceMode });
  }, [draft, stream, workspaceMode, text]);

  const handlePause = useCallback((): void => {
    stream.pause();
  }, [stream]);

  const handleResume = useCallback((): void => {
    const target = findLastResumableNode(activePath);
    if (!target || !target.run_id) return;
    void stream.resume(target.id);
  }, [activePath, stream]);

  const handleRetry = useCallback(
    (nodeId: string): void => {
      void stream.retry(nodeId);
    },
    [stream],
  );

  const handlePickExamplePrompt = useCallback(
    (prompt: string): void => {
      setDraft(prompt);
    },
    [setDraft],
  );

  const handleMessageListInspector = useCallback(
    (section: InspectorSection): void => {
      onOpenInspector(section);
    },
    [onOpenInspector],
  );

  // ─── Edit / Copy / Regenerate callbacks (Req 4 / 5 / 10) ───────────────
  const handleCopy = useCallback(
    async (nodeId: string): Promise<boolean> => {
      const node = useWorkspaceStore.getState().nodesById[nodeId];
      if (!node) return false;
      return copyText(stripThinkBlocks(node.content));
    },
    [],
  );

  const handleStartEdit = useCallback((nodeId: string) => {
    setEditingNodeId(nodeId);
  }, []);

  const handleCancelEdit = useCallback(() => {
    setEditingNodeId(null);
  }, []);

  const handleSaveEdit = useCallback(
    (nodeId: string, newContent: string) => {
      const storeState = useWorkspaceStore.getState();
      const original = storeState.nodesById[nodeId];
      if (!original || original.role !== "user") return;
      const parentId = original.parent_id ?? rootNodeId;

      const newUserId = storeState.appendNode({
        parent_id: parentId,
        role: "user",
        content: newContent,
        state: "done",
        metadata: { workspace_mode: workspaceMode },
        tool_calls: [],
        artifacts: [],
      });
      const newAssistantId = useWorkspaceStore.getState().appendNode({
        parent_id: newUserId,
        role: "assistant",
        content: "",
        state: "streaming",
        metadata: { workspace_mode: workspaceMode },
        tool_calls: [],
        artifacts: [],
      });

      setEditingNodeId(null);
      void stream.driveBranch({
        assistantNodeId: newAssistantId,
        goal: newContent,
        mode: workspaceMode,
      });
    },
    [rootNodeId, stream, workspaceMode],
  );

  const handleRegenerate = useCallback(
    (nodeId: string) => {
      const storeState = useWorkspaceStore.getState();
      const target = storeState.nodesById[nodeId];
      if (!target) return;
      const parentUserId = target.parent_id;
      if (!parentUserId) return;
      const parentUser = storeState.nodesById[parentUserId];
      if (!parentUser || parentUser.role !== "user") return;

      const mode = target.metadata.workspace_mode ?? workspaceMode;
      const newAssistantId = storeState.appendNode({
        parent_id: parentUserId,
        role: "assistant",
        content: "",
        state: "streaming",
        metadata: { workspace_mode: mode },
        tool_calls: [],
        artifacts: [],
      });

      void stream.driveBranch({
        assistantNodeId: newAssistantId,
        goal: parentUser.content,
        mode,
      });
    },
    [stream, workspaceMode],
  );

  // ─── Plan approval callbacks (Req 3) ───────────────────────────────────
  const handleApprovePlan = useCallback(async (): Promise<void> => {
    if (!planGate.visible || !planGate.planNode) return;
    const planNode = planGate.planNode;
    setPlanSubmitting(true);
    try {
      const newAssistantId = useWorkspaceStore.getState().appendNode({
        parent_id: planNode.id,
        role: "assistant",
        content: "",
        state: "streaming",
        metadata: { workspace_mode: "plan" },
        tool_calls: [],
        artifacts: [],
      });
      await stream.driveBranch({
        assistantNodeId: newAssistantId,
        goal: planNode.content,
        mode: "plan",
      });
    } finally {
      setPlanSubmitting(false);
    }
  }, [planGate, stream]);

  const handleEditPlan = useCallback((): void => {
    if (!planGate.visible || !planGate.planNode) return;
    setDraft(planGate.planNode.content);
    window.requestAnimationFrame(() => {
      composerRef.current?.focus();
    });
  }, [planGate, setDraft]);

  const handleDiscardPlan = useCallback((): void => {
    if (planGate.planNode) dismissPlanNode(planGate.planNode.id);
  }, [planGate, dismissPlanNode]);

  // ─── Toolbar callbacks ─────────────────────────────────────────────────
  const handleInsertMention = useCallback(
    (toolName: string): void => {
      const current = useWorkspaceStore.getState().draft;
      const separator =
        current.length === 0 || current.endsWith(" ") || current.endsWith("\n")
          ? ""
          : " ";
      setDraft(`${current}${separator}@${toolName} `);
      window.requestAnimationFrame(() => {
        composerRef.current?.focus();
      });
    },
    [setDraft],
  );

  const handleOpenRunDetail = useCallback(
    (runId: string): void => {
      navigate(`/runs/${runId}`);
    },
    [navigate],
  );

  // ─── Slash command dispatcher (v3 / Req 5) ─────────────────────────────
  const handleSlashDispatch = useCallback(
    (cmd: SlashCommand, args: string): void => {
      switch (cmd.name) {
        case "plan":
          onWorkspaceModeChange("plan");
          setDraft("");
          return;
        case "Harness Agent":
          onWorkspaceModeChange("markdown_plan");
          setDraft("");
          return;
        case "chat":
          onWorkspaceModeChange("chat");
          setDraft("");
          return;
        case "pin": {
          if (tail !== null) togglePinned(tail.id);
          setDraft("");
          return;
        }
        case "clear":
          onClearConversation();
          setDraft("");
          return;
        case "model":
          onRequestModelPicker();
          setDraft("");
          return;
        case "tool":
          if (args.length > 0) {
            // Strip any leading '@' to tolerate `/tool @curl`.
            const name = args.replace(/^@/, "").split(/\s+/)[0] ?? "";
            if (name.length > 0) {
              // Build the full replacement so the draft ends up as the
              // mention (no residual `/tool`).
              setDraft(`@${name} `);
              window.requestAnimationFrame(() => {
                composerRef.current?.focus();
              });
            }
          }
          return;
        case "search":
          onOpenSearch();
          setDraft("");
          return;
        case "help":
          onOpenShortcut();
          setDraft("");
          return;
        default: {
          const _exhaustive: never = cmd.name;
          void _exhaustive;
          return;
        }
      }
    },
    [
      onClearConversation,
      onOpenSearch,
      onOpenShortcut,
      onRequestModelPicker,
      onWorkspaceModeChange,
      setDraft,
      tail,
      togglePinned,
    ],
  );

  return (
    <div className="flex h-full w-full min-h-0 flex-col bg-[#f3f5f7]">
      <TopMetaBar
        agentName={agentName}
        isStreaming={stream.isStreaming}
        activeRunId={activeRunId}
        onOpenInspector={onOpenInspector}
        onStop={handlePause}
      />

      <ChatMessageList
        ref={chatListRef}
        activePath={activePath}
        agentName={agentName}
        modelLabel={modelLabel}
        onPickExamplePrompt={handlePickExamplePrompt}
        onRetry={handleRetry}
        onOpenInspector={(section, _nodeId) => handleMessageListInspector(section)}
        activeRunId={activeRunId}
        runStatus={runStatus}
        runCreatedAt={runCreatedAt}
        editingNodeId={editingNodeId}
        onStartEdit={handleStartEdit}
        onCancelEdit={handleCancelEdit}
        onSaveEdit={handleSaveEdit}
        onCopy={handleCopy}
        onRegenerate={handleRegenerate}
        isStreaming={stream.isStreaming}
      />

      <footer className="sticky bottom-0 z-10 border-t border-slate-200 bg-white/80 px-4 py-3 backdrop-blur">
        <div className="mx-auto flex w-full flex-col gap-2">
          {planGate.visible && planGate.planNode && (
            <PlanApprovalPanel
              planNode={planGate.planNode}
              isSubmitting={planSubmitting}
              onApprove={() => {
                void handleApprovePlan();
              }}
              onEdit={handleEditPlan}
              onDiscard={handleDiscardPlan}
              onClose={handleDiscardPlan}
            />
          )}

          {/* v3: MetadataStrip lives here (Req 3). */}
          <div className="mx-auto w-full max-w-[56rem] px-3 sm:px-4 lg:px-6 xl:px-12 text-[11px] text-slate-400">
            <MetadataStrip
              tail={tail}
              activeRunId={activeRunId}
              onOpenRunDetail={handleOpenRunDetail}
            />
          </div>

          <ComposerToolbar
            optionsOpen={optionsOpen}
            onOptionsToggle={() => setOptionsOpen((prev) => !prev)}
            optionsTriggerRef={optionsTriggerRef}
            usageRatio={usage.ratio}
            usageLimit={usage.limit}
            usageCurrent={usage.current}
            onExport={onExport}
            onClearConversation={onClearConversation}
          />
          <div className="relative">
            <ComposerOptionsPopover
              open={optionsOpen}
              onClose={() => setOptionsOpen(false)}
              anchorRef={optionsTriggerRef}
              contextWindowTurns={contextWindowTurns}
              onContextWindowTurnsChange={setContextWindowTurns}
              contextMaxTokens={contextMaxTokens}
              onContextMaxTokensChange={setContextMaxTokens}
              pinnedNodes={pinnedNodes}
              onUnpin={togglePinned}
              tools={tools}
              onInsertMention={handleInsertMention}
              providers={providers}
              selectedProviderId={selectedProviderId}
              selectedModelId={selectedModelId}
              onModelChange={onModelChange}
              modelLabelFallback={modelLabel}
              modelPickerOpenSeq={modelPickerOpenSeq}
            />
          </div>
          <ChatComposer
            ref={composerRef}
            draft={draft}
            onDraftChange={setDraft}
            onSubmit={handleSubmit}
            onPause={handlePause}
            onResume={handleResume}
            isStreaming={stream.isStreaming}
            canResume={canResume}
            mode={workspaceMode}
            onChangeMode={onWorkspaceModeChange}
            placeholder={placeholder}
            isEditLocked={editingNodeId !== null}
            onSlashDispatch={handleSlashDispatch}
          />
        </div>
        <p className="sr-only" aria-live="polite">
          {stream.isStreaming
            ? text("正在生成", "Streaming response")
            : text(`工作台 ${agentId}`, `Workspace for ${agentId}`)}
        </p>
      </footer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Top meta bar (sticky header) — v4 精简版 (Req 3)
// ---------------------------------------------------------------------------

type TopMetaBarProps = {
  agentName: string;
  isStreaming: boolean;
  activeRunId: string | null;
  onOpenInspector: (section: InspectorSection) => void;
  onStop: () => void;
};

function TopMetaBar({
  agentName,
  isStreaming,
  activeRunId,
  onOpenInspector,
  onStop,
}: TopMetaBarProps): JSX.Element {
  const { text } = useI18n();

  const runDetailLabel = text("Run 详情", "Run Detail");
  const streamingLabel = text("Streaming", "Streaming");

  return (
    <header className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-5 py-2 text-sm">
      <div className="flex min-w-0 items-center gap-3">
        <span className="truncate font-semibold text-slate-900">{agentName}</span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {isStreaming && (
          <Badge tone="warning" className="shrink-0">
            <Sparkles aria-hidden="true" className="h-3 w-3" />
            {streamingLabel}
          </Badge>
        )}

        {isStreaming && (
          <Button
            type="button"
            variant="secondary"
            onClick={onStop}
            aria-label={text("停止生成", "Stop generation")}
            title={text("停止生成", "Stop generation")}
          >
            <Square aria-hidden="true" className="h-3.5 w-3.5" />
            {text("停止", "Stop")}
          </Button>
        )}

        <InspectorMenu onOpenInspector={onOpenInspector} />

        {activeRunId ? (
          <Link to={`/runs/${activeRunId}`} aria-label={runDetailLabel}>
            <Button variant="primary" aria-label={runDetailLabel}>
              <GitBranch aria-hidden="true" className="h-3.5 w-3.5" />
              {runDetailLabel}
            </Button>
          </Link>
        ) : (
          <Button
            variant="secondary"
            disabled
            aria-label={runDetailLabel}
            title={runDetailLabel}
          >
            <GitBranch aria-hidden="true" className="h-3.5 w-3.5" />
            {runDetailLabel}
          </Button>
        )}
      </div>
    </header>
  );
}

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

function composerPlaceholder(
  mode: WorkspaceMode,
  text: (zh: string, en: string) => string,
): string {
  switch (mode) {
    case "chat":
      return text("直接与 Agent 对话", "Chat with the agent");
    case "markdown_plan":
      return text(
        "描述目标，返回 markdown 规划",
        "Describe a goal; returns a markdown plan",
      );
    case "plan":
      return text(
        "描述目标,创建 Plan-Act Run",
        "Describe a goal; creates a Plan-Act Run",
      );
    default: {
      const exhaustive: never = mode;
      void exhaustive;
      return "";
    }
  }
}

function findLastResumableNode(activePath: ConversationNode[]): ConversationNode | null {
  for (let i = activePath.length - 1; i >= 0; i -= 1) {
    const node = activePath[i];
    if (
      node.role === "assistant" &&
      node.state === "paused" &&
      typeof node.run_id === "string" &&
      node.run_id.length > 0
    ) {
      return node;
    }
  }
  return null;
}

function buildActivePath(
  nodesById: Record<string, ConversationNode>,
  activeLeafId: string,
  rootNodeId: string,
): ConversationNode[] {
  const path: ConversationNode[] = [];
  let current: string | null = activeLeafId;
  while (current) {
    const node: ConversationNode | undefined = nodesById[current];
    if (!node) break;
    if (node.id !== rootNodeId) path.push(node);
    current = node.parent_id;
  }
  return path.reverse();
}
