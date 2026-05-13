/**
 * ChatSurface — chat-first Workspace viewport.
 *
 * The page keeps a lightweight Harness shell above the conversation, leaves
 * the middle region to messages or the welcome state, and makes the composer
 * the primary persistent control. Secondary controls live in the composer
 * options popover so they remain reachable without crowding the conversation.
 */

import {
  useEffect,
  useCallback,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type JSX,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import {
  ChevronRight,
  ListChecks,
  Paperclip,
  PlugZap,
} from "lucide-react";

import { useI18n } from "../../../lib/i18n";
import {
  useWorkspaceStore,
  type ConversationNode,
} from "../../../stores/workspaceStore";
import type { AgentAttachmentPayload, ToolMetadata } from "../../tasks/api";
import type { ChatStreamController } from "../hooks/useChatStream";
import { useOutsideClick } from "../hooks/useOutsideClick";
import { canResume as canResumeQuery } from "../lib/activePathQueries";
import { copyText } from "../lib/clipboard";
import { stripThinkBlocks } from "../lib/copyText";
import { planApprovalGate } from "../lib/planApprovalGate";
import type { SlashCommand } from "../lib/slashCommands";
import type { InspectorSection, WorkspaceMode } from "../lib/types";
import {
  ChatComposer,
  type ComposerAttachment,
} from "./ChatComposer";
import { ChatMessageList, type ChatMessageListHandle } from "./ChatMessageList";
import type { UsageSummary } from "./InspectorDrawer";
import type { ModelOption } from "./ModelPicker";
import { PlanApprovalPanel } from "./PlanApprovalPanel";
import { WorkspaceShellBar } from "./WorkspaceShellBar";

const MAX_ATTACHMENT_TEXT_BYTES = 120_000;

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
  pendingApprovalCount: number;
  metadataUsage: UsageSummary;
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
    metadataUsage,
    onOpenInspector,
    stream,
    tools,
    providers,
    selectedProviderId,
    selectedModelId,
    onModelChange,
    onClearConversation,
    onOpenSearch,
    onOpenShortcut,
  } = props;

  const { text } = useI18n();
  const draft = useWorkspaceStore((state) => state.draft);
  const setDraft = useWorkspaceStore((state) => state.setDraft);
  const nodesById = useWorkspaceStore((state) => state.nodesById);
  const rootNodeId = useWorkspaceStore((state) => state.rootNodeId);
  const activeLeafId = useWorkspaceStore((state) => state.activeLeafId);
  const togglePinned = useWorkspaceStore((state) => state.togglePinned);
  const dismissedPlanNodeIds = useWorkspaceStore((state) => state.dismissedPlanNodeIds);
  const dismissPlanNode = useWorkspaceStore((state) => state.dismissPlanNode);
  const activeStream = useWorkspaceStore((state) => state.activeStream);

  const activePath = useMemo(
    () => buildActivePath(nodesById, activeLeafId, rootNodeId),
    [nodesById, activeLeafId, rootNodeId],
  );

  const tail = activePath.length > 0 ? activePath[activePath.length - 1] : null;
  const canResume = canResumeQuery(activePath);
  const placeholder = composerPlaceholder(workspaceMode, text);

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
  const [bottomPanel, setBottomPanel] = useState<"tools" | "model" | null>(null);
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const optionsTriggerRef = useRef<HTMLButtonElement | null>(null);
  const chatListRef = useRef<ChatMessageListHandle | null>(null);
  const attachmentsRef = useRef<ComposerAttachment[]>([]);

  useEffect(() => {
    attachmentsRef.current = attachments;
  }, [attachments]);

  useEffect(
    () => () => {
      for (const attachment of attachmentsRef.current) {
        revokeAttachmentPreview(attachment);
      }
    },
    [],
  );

  const attachmentNames = useMemo(
    () => attachments.map((attachment) => attachment.name),
    [attachments],
  );
  const attachmentPayloads = useMemo<AgentAttachmentPayload[]>(
    () =>
      attachments.map((attachment) => ({
        name: attachment.name,
        mime_type: attachment.mimeType,
        size_bytes: attachment.sizeBytes,
        content_text: attachment.contentText,
        content_status: attachment.contentStatus,
        truncated: attachment.truncated,
      })),
    [attachments],
  );

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
    void stream.start({
      goal,
      mode: workspaceMode,
      attachmentNames,
      attachments: attachmentPayloads,
    });
    setAttachments((current) => {
      for (const attachment of current) revokeAttachmentPreview(attachment);
      return [];
    });
  }, [attachmentNames, attachmentPayloads, draft, stream, workspaceMode, text]);

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

  const handleAddFiles = useCallback((): void => {
    fileInputRef.current?.click();
  }, []);

  const handleFilesSelected = useCallback(
    (event: ChangeEvent<HTMLInputElement>): void => {
      const selected = Array.from(event.currentTarget.files ?? []);
      if (selected.length === 0) return;
      void (async () => {
        const prepared = await Promise.all(selected.map(toComposerAttachment));
        setAttachments((current) => {
          const next = [...current];
          const existingKeys = new Set(current.map(attachmentKey));
          for (const attachment of prepared) {
            const key = attachmentKey(attachment);
            if (existingKeys.has(key) || next.length >= 12) {
              revokeAttachmentPreview(attachment);
              continue;
            }
            next.push(attachment);
            existingKeys.add(key);
          }
          return next;
        });
      })();
      event.currentTarget.value = "";
    },
    [],
  );

  const handleRemoveAttachment = useCallback((id: string): void => {
    setAttachments((current) => {
      const target = current.find((attachment) => attachment.id === id);
      if (target !== undefined) revokeAttachmentPreview(target);
      return current.filter((attachment) => attachment.id !== id);
    });
  }, []);

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
        metadata: { workspace_mode: "chat" },
        tool_calls: [],
        artifacts: [],
      });
      await stream.driveBranch({
        assistantNodeId: newAssistantId,
        goal: planNode.content,
        mode: "chat",
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

  const handleShellToolMention = useCallback(
    (toolName: string): void => {
      handleInsertMention(toolName);
      setBottomPanel(null);
    },
    [handleInsertMention],
  );

  // ─── Slash command dispatcher (v3 / Req 5) ─────────────────────────────
  const handleSlashDispatch = useCallback(
    (cmd: SlashCommand, args: string): void => {
      switch (cmd.name) {
        case "plan":
          onWorkspaceModeChange("markdown_plan");
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
          setBottomPanel("model");
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
      onWorkspaceModeChange,
      setDraft,
      tail,
      togglePinned,
    ],
  );

  return (
    <div className="flex h-full w-full min-w-0 flex-col bg-white">
      <WorkspaceShellBar
        agentId={agentId}
        agentName={agentName}
        modelLabel={modelLabel}
        modelLabelIsFallback={modelLabelIsFallback}
        tools={tools}
        providers={providers}
        selectedProviderId={selectedProviderId}
        selectedModelId={selectedModelId}
        isStreaming={stream.isStreaming}
        activeRunId={activeRunId}
        runStatus={runStatus}
        onModelChange={onModelChange}
        onInsertToolMention={handleShellToolMention}
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

      <footer className="sticky bottom-0 z-10 bg-gradient-to-t from-white via-white/95 to-white/0 px-3 pb-5 pt-6">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-2">
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
          <div className="relative">
            <BottomToolsPopover
              open={bottomPanel !== null}
              onClose={() => setBottomPanel(null)}
              title={
                bottomPanel === "model"
                  ? text("切换模型", "Switch model")
                  : text("输入设置", "Composer settings")
              }
            >
              {bottomPanel === "model" ? (
                <BottomModelPanel
                  providers={providers}
                  selectedProviderId={selectedProviderId}
                  selectedModelId={selectedModelId}
                  onModelChange={(providerId, modelId) => {
                    onModelChange(providerId, modelId);
                    setBottomPanel(null);
                  }}
                  modelLabelFallback={modelLabel}
                  text={text}
                />
              ) : (
                <ComposerSettingsPanel
                  workspaceMode={workspaceMode}
                  onWorkspaceModeChange={onWorkspaceModeChange}
                  attachmentNames={attachmentNames}
                  onAddFiles={handleAddFiles}
                  tools={tools}
                  onInsertMention={handleShellToolMention}
                  text={text}
                />
              )}
            </BottomToolsPopover>
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
              optionsOpen={bottomPanel !== null}
              onOptionsToggle={() =>
                setBottomPanel((current) => (current === "tools" ? null : "tools"))
              }
              optionsTriggerRef={optionsTriggerRef}
              metadata={<ComposerMetadataRow usage={metadataUsage} text={text} />}
              attachments={attachments}
              onRemoveAttachment={handleRemoveAttachment}
              isEditLocked={editingNodeId !== null}
              onSlashDispatch={handleSlashDispatch}
            />
          </div>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            aria-label={text("添加照片和文件", "Add photos and files")}
            className="hidden"
            onChange={handleFilesSelected}
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
// Bottom tools panel helpers
// ---------------------------------------------------------------------------

type ToolsPanelProps = {
  tools: ToolMetadata[];
  onInsertMention: (toolName: string) => void;
  text: (zh: string, en: string) => string;
  workspaceMode: WorkspaceMode;
  onWorkspaceModeChange: (mode: WorkspaceMode) => void;
  attachmentNames: string[];
  onAddFiles: () => void;
};

function BottomToolsPopover({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: JSX.Element;
}): JSX.Element | null {
  const popoverRef = useRef<HTMLDivElement | null>(null);
  useOutsideClick(popoverRef, onClose, open);

  if (!open) return null;

  return (
    <div
      ref={popoverRef}
      role="dialog"
      aria-modal="false"
      aria-label={title}
      className="absolute bottom-[68px] left-4 z-30 w-[min(220px,calc(100vw-2rem))] rounded-lg border border-slate-200 bg-white p-1.5 shadow-lg"
    >
      {children}
    </div>
  );
}

function ComposerSettingsPanel({
  workspaceMode,
  onWorkspaceModeChange,
  attachmentNames,
  onAddFiles,
  tools,
  onInsertMention,
  text,
}: ToolsPanelProps): JSX.Element {
  const [pluginsOpen, setPluginsOpen] = useState(false);
  const mcpTools = tools.filter(isMcpTool);

  return (
    <div className="flex flex-col text-xs text-slate-800">
      <ToolActionRow
        icon={<Paperclip aria-hidden="true" className="h-3.5 w-3.5" />}
        label={
          attachmentNames.length > 0
            ? text(
                `添加照片和文件 (${attachmentNames.length})`,
                `Add photos and files (${attachmentNames.length})`,
              )
            : text("添加照片和文件", "Add photos and files")
        }
        onClick={onAddFiles}
      />
      <ToolToggleRow
        icon={<ListChecks aria-hidden="true" className="h-3.5 w-3.5" />}
        label={text("计划模式", "Plan mode")}
        checked={workspaceMode === "markdown_plan"}
        onChange={(checked) => onWorkspaceModeChange(checked ? "markdown_plan" : "chat")}
      />
      <ToolActionRow
        icon={<PlugZap aria-hidden="true" className="h-3.5 w-3.5" />}
        label={text("插件 / MCP", "Plugins / MCP")}
        trailing={
          <ChevronRight
            aria-hidden="true"
            className={[
              "h-4 w-4 text-slate-400 transition-transform",
              pluginsOpen ? "rotate-90" : "",
            ].join(" ")}
          />
        }
        onClick={() => setPluginsOpen((open) => !open)}
      />
      {pluginsOpen && (
        <div className="ml-5 mt-0.5 max-h-24 overflow-y-auto border-l border-slate-200 pl-1.5">
          {mcpTools.length === 0 ? (
            <p className="px-2 py-1.5 text-xs text-slate-500">
              {text("暂无 MCP 功能", "No MCP capabilities")}
            </p>
          ) : (
            mcpTools.map((tool) => (
              <button
                key={`${tool.source ?? "tool"}:${tool.name}`}
                type="button"
                onClick={() => onInsertMention(tool.name)}
                className="block w-full rounded-md px-1.5 py-1 text-left text-[11px] text-slate-600 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
              >
                <span className="block truncate font-mono">@{tool.name}</span>
                <span className="block truncate text-[11px] text-slate-500">
                  {formatMcpCapability(tool)}
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}

function BottomModelPanel({
  providers,
  selectedProviderId,
  selectedModelId,
  onModelChange,
  modelLabelFallback,
  text,
}: {
  providers: ModelOption[];
  selectedProviderId: string | null;
  selectedModelId: string | null;
  onModelChange: (providerId: string, modelId: string) => void;
  modelLabelFallback: string;
  text: (zh: string, en: string) => string;
}): JSX.Element {
  const [activeIndex, setActiveIndex] = useState(0);
  const listRef = useRef<HTMLDivElement | null>(null);
  const selectedIndex = providers.findIndex(
    (option) =>
      option.providerId === selectedProviderId && option.modelId === selectedModelId,
  );

  useEffect(() => {
    if (providers.length === 0) return;
    setActiveIndex(selectedIndex >= 0 ? selectedIndex : 0);
    window.requestAnimationFrame(() => listRef.current?.focus());
  }, [providers.length, selectedIndex]);

  if (providers.length === 0) {
    return (
      <div className="rounded-md border border-amber-200 bg-amber-50 p-1.5 text-xs text-amber-800">
        {text("模型设置不可用", "Model settings unavailable")} · {modelLabelFallback}
      </div>
    );
  }

  function handleKeyDown(event: ReactKeyboardEvent<HTMLDivElement>): void {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setActiveIndex((index) => (index + 1) % providers.length);
        return;
      case "ArrowUp":
        event.preventDefault();
        setActiveIndex((index) => (index - 1 + providers.length) % providers.length);
        return;
      case "Enter": {
        event.preventDefault();
        const next = providers[activeIndex];
        if (next === undefined) return;
        onModelChange(next.providerId, next.modelId);
        return;
      }
      default:
        return;
    }
  }

  return (
    <div
      ref={listRef}
      role="listbox"
      tabIndex={-1}
      aria-label={text("切换模型", "Switch model")}
      onKeyDown={handleKeyDown}
      className="flex max-h-36 flex-col gap-0.5 overflow-y-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
    >
      {providers.map((option, index) => {
        const selected =
          option.providerId === selectedProviderId && option.modelId === selectedModelId;
        const active = index === activeIndex;
        return (
          <button
            key={`${option.providerId}:${option.modelId}`}
            type="button"
            role="option"
            aria-selected={selected}
            onClick={() => onModelChange(option.providerId, option.modelId)}
            onMouseEnter={() => setActiveIndex(index)}
            aria-pressed={selected}
            className={[
              "flex items-center justify-between gap-2 rounded-md px-1.5 py-1 text-left text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400",
              selected || active
                ? "bg-slate-100 font-medium text-slate-900"
                : "text-slate-700 hover:bg-slate-50",
            ].join(" ")}
          >
            <span className="min-w-0">
              <span className="block truncate">{option.providerLabel}</span>
              <span className="block truncate text-slate-500">{option.modelLabel}</span>
            </span>
            {selected && (
              <span className="shrink-0 rounded-full bg-slate-900 px-1 py-0.5 text-[10px] font-normal text-white">
                {text("当前", "Current")}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

function isMcpTool(tool: ToolMetadata): boolean {
  return tool.source === "mcp" || tool.mcp_server !== null || tool.mcp_method !== null;
}

function formatMcpCapability(tool: ToolMetadata): string {
  if (tool.mcp_server !== null && tool.mcp_method !== null) {
    return `${tool.mcp_server}.${tool.mcp_method}`;
  }
  if (tool.mcp_server !== null) return tool.mcp_server;
  if (tool.mcp_method !== null) return tool.mcp_method;
  return tool.description || tool.category;
}

function ToolActionRow({
  icon,
  label,
  trailing = null,
  onClick,
}: {
  icon: JSX.Element;
  label: string;
  trailing?: JSX.Element | null;
  onClick: () => void;
}): JSX.Element {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex h-7 items-center gap-2 rounded-md px-1.5 text-left transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
    >
      <span className="text-slate-500">{icon}</span>
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {trailing}
    </button>
  );
}

function ToolToggleRow({
  icon,
  label,
  checked,
  onChange,
}: {
  icon: JSX.Element;
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}): JSX.Element {
  return (
    <div className="flex h-7 items-center gap-2 rounded-md px-1.5 transition-colors hover:bg-slate-50">
      <span className="flex h-4 w-4 shrink-0 items-center justify-center text-slate-500">
        {icon}
      </span>
      <span className="min-w-0 flex-1 truncate">{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
        className={[
          "relative inline-flex h-5 w-8 shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400",
          checked ? "bg-slate-900" : "bg-slate-200",
        ].join(" ")}
      >
        <span
          className={[
            "h-4 w-4 rounded-full bg-white shadow transition-transform",
            checked ? "translate-x-[14px]" : "translate-x-[2px]",
          ].join(" ")}
        />
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

function ComposerMetadataRow({
  usage,
  text,
}: {
  usage: UsageSummary;
  text: (zh: string, en: string) => string;
}): JSX.Element {
  const items = [
    [text("输入", "In"), formatMetricNumber(usage.inputTokens)],
    [text("输出", "Out"), formatMetricNumber(usage.outputTokens)],
    [text("花费", "Cost"), usage.costUsd],
    [text("耗时", "Time"), formatDuration(usage.durationMs)],
    [text("模型", "Models"), formatMetricNumber(usage.modelCalls)],
    [text("工具", "Tools"), formatMetricNumber(usage.toolCalls)],
  ];

  return (
    <div
      className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] leading-4 text-slate-500"
      aria-label={text("运行元数据", "Run metadata")}
    >
      {items.map(([label, value]) => (
        <span key={label} className="inline-flex min-w-0 items-baseline gap-1">
          <span>{label}</span>
          <span className="font-mono text-slate-700">{value}</span>
        </span>
      ))}
    </div>
  );
}

async function toComposerAttachment(file: File): Promise<ComposerAttachment> {
  const isImage = file.type.startsWith("image/");
  const content = await readAttachmentText(file);
  return {
    id: makeAttachmentId(file),
    name: file.name,
    mimeType: file.type,
    previewUrl: isImage ? URL.createObjectURL(file) : null,
    sizeBytes: file.size,
    kind: isImage ? "image" : "file",
    contentText: content.contentText,
    contentStatus: content.contentStatus,
    truncated: content.truncated,
  };
}

async function readAttachmentText(
  file: File,
): Promise<Pick<ComposerAttachment, "contentText" | "contentStatus" | "truncated">> {
  if (!isReadableTextFile(file)) {
    return { contentText: null, contentStatus: "unsupported", truncated: false };
  }
  try {
    const truncated = file.size > MAX_ATTACHMENT_TEXT_BYTES;
    const text = await readBlobText(file.slice(0, MAX_ATTACHMENT_TEXT_BYTES));
    return { contentText: text, contentStatus: "ready", truncated };
  } catch {
    return { contentText: null, contentStatus: "error", truncated: false };
  }
}

function readBlobText(blob: Blob): Promise<string> {
  if (typeof blob.text === "function") return blob.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      resolve(typeof reader.result === "string" ? reader.result : "");
    });
    reader.addEventListener("error", () => reject(reader.error));
    reader.readAsText(blob);
  });
}

function isReadableTextFile(file: File): boolean {
  if (file.type.startsWith("text/")) return true;
  const mime = file.type.toLowerCase();
  if (
    [
      "application/json",
      "application/xml",
      "application/yaml",
      "application/x-yaml",
      "application/javascript",
      "application/typescript",
    ].includes(mime)
  ) {
    return true;
  }
  return /\.(txt|md|markdown|csv|tsv|json|jsonl|yaml|yml|xml|log|ini|env|py|js|ts|tsx|jsx|css|html)$/i.test(
    file.name,
  );
}

function revokeAttachmentPreview(attachment: ComposerAttachment): void {
  if (attachment.previewUrl !== null) URL.revokeObjectURL(attachment.previewUrl);
}

function attachmentKey(attachment: ComposerAttachment): string {
  return `${attachment.name}:${attachment.sizeBytes}:${attachment.mimeType}`;
}

function makeAttachmentId(file: File): string {
  const random =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2);
  return `${file.name}:${file.size}:${file.lastModified}:${random}`;
}

function formatMetricNumber(value: number): string {
  return new Intl.NumberFormat("en", { notation: "compact" }).format(value);
}

function formatDuration(durationMs: number): string {
  if (!Number.isFinite(durationMs) || durationMs <= 0) return "0ms";
  if (durationMs < 1000) return `${Math.round(durationMs)}ms`;
  return `${(durationMs / 1000).toFixed(1)}s`;
}

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
