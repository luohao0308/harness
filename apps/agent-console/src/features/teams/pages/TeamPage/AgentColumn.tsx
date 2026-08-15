import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  type ChangeEvent,
  type ReactNode,
} from "react";
import { Bot, Brain, Maximize2, UsersRound, X } from "lucide-react";

import { Badge } from "../../../../components/ui/badge";
import { notifyFeedback } from "../../../../components/ui/feedback-toast";
import { cn } from "../../../../lib/utils";
import { ChatComposer, type ComposerAttachment } from "../../../agents/components/ChatComposer";
import { ContextRing } from "../../../agents/components/ContextRing";
import { ContextSummaryManager } from "../../../agents/components/ContextSummaryManager";
import type { InspectorSection, WorkspaceMode } from "../../../agents/lib/types";
import { copyText } from "../../../agents/lib/clipboard";
import { stripThinkBlocks } from "../../../agents/lib/copyText";
import { selectBestCompressionSummary, type ContextCompressionSummary } from "../../../agents/lib/contextCompression";
import type { SlashCommand } from "../../../agents/lib/slashCommands";
import type { ModelOption } from "../../../agents/components/ModelPicker";
import type { Team, TeamAgent, TeamMailboxMessage, TeamTask, ToolMetadata } from "../../../tasks/api";
import type { ConversationNode } from "../../../../stores/workspaceStore";
import { teamAgentStatusLabel, teamAgentStatusTone, teamTaskStatusLabel, teamTaskStatusTone } from "../../lib/teamLabels";

import {
  applyTeamBranchGroups,
  defaultComposerTarget,
  findLastAssistantNodeId,
  isMcpTool,
  summarizeTeamUsage,
  teamCompressionKey,
  teamComposerPlaceholder,
  teamContextTokenEstimate,
  teamConversationEntriesWithPending,
  teamEffectiveContextTokenEstimate,
} from "./conversation";
import { displayAgentStatus } from "./teamState";
import { TeamChatMessage } from "./TeamChatMessage";
import {
  TeamBottomPopover,
  TeamComposerMetadataRow,
  TeamComposerSettingsPanel,
  TeamModelPanel,
} from "./TeamComposerPanels";
import type {
  PendingSend,
  SettledWakeCutoffs,
  StreamingWake,
  TeamBottomPanel,
  TeamBranchGroup,
  TeamComposerState,
  TeamComposerStateUpdater,
  TeamConversationEntry,
  TeamModelChangeHandler,
  TextFn,
} from "./types";

export type AgentColumnProps = {
  team: Team;
  agent: TeamAgent;
  text: TextFn;
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
  modelOptions: ModelOption[];
  contextMaxTokens: number;
  autoCompressionRatio: number;
  onContextMaxTokensChange: (value: number) => void;
  onAutoCompressionRatioChange: (value: number) => void;
  onClearContextCompression: (slotId: string, branchKey: string) => void;
  addComposerFiles: (slotId: string) => void;
  handleComposerFilesSelected: (slotId: string, event: ChangeEvent<HTMLInputElement>) => void;
  removeComposerAttachment: (slotId: string, attachmentId: string) => void;
  setComposerBottomPanel: (slotId: string, panel: TeamBottomPanel) => void;
  onModelChange: TeamModelChangeHandler;
  fileInputRef: (node: HTMLInputElement | null) => void;
  isSending: boolean;
  editingMessageId: string | null;
  pinnedMessageIds: string[];
  branchGroups: Record<string, TeamBranchGroup>;
  contextCompressions: Record<string, ContextCompressionSummary>;
  onCompressContext: (
    agent: TeamAgent,
    entries: TeamConversationEntry[],
    reason?: "manual" | "background" | "pre_send",
  ) => Promise<ContextCompressionSummary | null>;
  onComposerChange: (value: TeamComposerStateUpdater) => void;
  onSend: (content: string, target: string, mode: WorkspaceMode) => void;
  onMessageActionSend: (content: string, target: string) => void;
  onBranchMessage: (nodeId: string, entries: TeamConversationEntry[]) => void;
  onSwitchBranch: (anchorUserId: string, nodeId: string) => void;
  onStartMessageEdit: (nodeId: string) => void;
  onCancelMessageEdit: () => void;
  onTogglePin: (nodeId: string) => void;
  onOpenMessageInspector: (section: InspectorSection, node: ConversationNode) => void;
  onStopWake: () => void;
  onFullscreen?: () => void;
  onRemove: () => void;
  onFocus: () => void;
  isFlashing?: boolean;
  setScrollRef: (node: HTMLDivElement | null) => void;
  visibleColumnCount?: number;
  fullscreen?: boolean;
  conversationSupplement?: ReactNode;
  hideTaskSteps?: boolean;
};

export function AgentColumn({
  team,
  agent,
  text,
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
  modelOptions,
  contextMaxTokens,
  autoCompressionRatio,
  onContextMaxTokensChange,
  onAutoCompressionRatioChange,
  onClearContextCompression,
  addComposerFiles,
  handleComposerFilesSelected,
  removeComposerAttachment,
  setComposerBottomPanel,
  onModelChange,
  fileInputRef,
  isSending,
  editingMessageId,
  pinnedMessageIds,
  branchGroups,
  contextCompressions,
  onCompressContext,
  onComposerChange,
  onSend,
  onMessageActionSend,
  onBranchMessage,
  onSwitchBranch,
  onStartMessageEdit,
  onCancelMessageEdit,
  onTogglePin,
  onOpenMessageInspector,
  onStopWake,
  onFullscreen,
  onRemove,
  onFocus,
  isFlashing,
  setScrollRef,
  visibleColumnCount,
  fullscreen = false,
  conversationSupplement,
  hideTaskSteps = false,
}: AgentColumnProps) {
  const isLeader = agent.role === "leader";
  const roleLabel = isLeader ? text("队长", "Leader") : text("成员", "Teammate");
  const agentDisplayName = isLeader && agent.agent_name.trim().toLowerCase() === "leader"
    ? text("队长", "Leader")
    : agent.agent_name;
  const taskScope = tasks.filter((task) => task.owner_slot_id === agent.slot_id);
  const selectedTarget = defaultComposerTarget(agent);
  const selectedMode = composer.mode ?? "chat";
  const status = displayAgentStatus(agent, pendingWakeSlotIds, streamingWakes, settledWakeCutoffs);
  const visibleEntries = teamConversationEntriesWithPending(
    team,
    agent,
    messages,
    pendingSends,
    pendingWakeSlotIds,
    streamingWakes,
    settledWakeCutoffs,
  );
  const branchVisibleEntries = useMemo(
    () => applyTeamBranchGroups(visibleEntries, branchGroups),
    [branchGroups, visibleEntries],
  );
  const lastAssistantId = findLastAssistantNodeId(branchVisibleEntries);
  const canStopWake = status === "active";
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const rawContextUsageCurrent = useMemo(
    () => teamContextTokenEstimate(visibleEntries, composer.draft),
    [composer.draft, visibleEntries],
  );
  const compressionBranchKey = useMemo(
    () => teamCompressionKey(team, agent, visibleEntries),
    [agent, team, visibleEntries],
  );
  const activeCompression = useMemo(
    () =>
      selectBestCompressionSummary({
        summaries: contextCompressions,
        branchKey: compressionBranchKey,
        activePath: visibleEntries.map((entry) => entry.node),
        pinnedNodeIds: pinnedMessageIds,
        providerId: agent.model_provider || modelOptions[0]?.providerId || null,
        modelId: agent.model_name || modelOptions[0]?.modelId || null,
      }) ?? contextCompressions[compressionBranchKey] ?? null,
    [agent.model_name, agent.model_provider, compressionBranchKey, contextCompressions, modelOptions, pinnedMessageIds, visibleEntries],
  );
  const contextUsageCurrent = useMemo(
    () =>
      teamEffectiveContextTokenEstimate({
        entries: visibleEntries,
        draft: composer.draft,
        summary: activeCompression,
        branchKey: compressionBranchKey,
        pinnedNodeIds: pinnedMessageIds,
        providerId: agent.model_provider || modelOptions[0]?.providerId || null,
        modelId: agent.model_name || modelOptions[0]?.modelId || null,
      }),
    [
      activeCompression,
      agent.model_name,
      agent.model_provider,
      compressionBranchKey,
      composer.draft,
      modelOptions,
      pinnedMessageIds,
      visibleEntries,
    ],
  );
  const contextUsageRatio = contextMaxTokens > 0 ? contextUsageCurrent / contextMaxTokens : 0;
  const usageSummary = useMemo(() => summarizeTeamUsage(visibleEntries), [visibleEntries]);
  const modelLabel = agent.model_name && agent.model_name !== "default"
    ? agent.model_name
    : modelOptions[0]?.modelLabel && modelOptions[0].modelLabel !== "default"
      ? modelOptions[0].modelLabel
      : text("默认模型", "default");
  const providerLabel = agent.model_provider && agent.model_provider !== "default"
    ? agent.model_provider
    : text("默认提供方", "default");
  const selectedModelId = agent.model_name || modelOptions[0]?.modelId || null;
  const selectedProviderId = agent.model_provider || modelOptions[0]?.providerId || null;
  const messageListSignature = useMemo(
    () => visibleEntries.map((entry) => `${entry.node.id}:${entry.node.content.length}`).join("|"),
    [visibleEntries],
  );
  const streamSignature = useMemo(
    () =>
      visibleEntries
        .map((entry) => `${entry.node.id}:${entry.node.state}:${entry.node.content.length}`)
        .join("|"),
    [visibleEntries],
  );
  const scrollConversationToBottom = useCallback((behavior: ScrollBehavior) => {
    const node = scrollerRef.current;
    if (!node) return;
    if (typeof node.scrollTo === "function") {
      node.scrollTo({ top: node.scrollHeight, behavior });
      return;
    }
    node.scrollTop = node.scrollHeight;
  }, []);
  useLayoutEffect(() => {
    scrollConversationToBottom("auto");
  }, [agent.slot_id, messageListSignature, scrollConversationToBottom]);

  useEffect(() => {
    scrollConversationToBottom("smooth");
  }, [scrollConversationToBottom, streamSignature]);

  const handleInsertMention = useCallback(
    (toolName: string) => {
      onComposerChange((current) => {
        const separator =
          current.draft.length === 0 || current.draft.endsWith(" ") || current.draft.endsWith("\n") ? "" : " ";
        return { ...current, draft: `${current.draft}${separator}@${toolName} ` };
      });
      window.requestAnimationFrame(() => composerRef.current?.focus());
    },
    [onComposerChange],
  );
  const handleCompressContext = useCallback(() => {
    if (canStopWake) return;
    setComposerBottomPanel(agent.slot_id, null);
    void onCompressContext(agent, visibleEntries, "manual");
  }, [agent, canStopWake, onCompressContext, setComposerBottomPanel, visibleEntries]);
  const backgroundCompressionKeyRef = useRef<string | null>(null);
  useEffect(() => {
    if (canStopWake) return;
    if (contextUsageRatio < autoCompressionRatio) return;
    const last = visibleEntries[visibleEntries.length - 1];
    if (!last || last.node.role !== "assistant" || last.node.state !== "done") return;
    const key = `${compressionBranchKey}:${last.node.id}:${Math.round(contextUsageCurrent)}`;
    if (backgroundCompressionKeyRef.current === key) return;
    backgroundCompressionKeyRef.current = key;
    void onCompressContext(agent, visibleEntries, "background");
  }, [
    agent,
    autoCompressionRatio,
    canStopWake,
    compressionBranchKey,
    contextUsageCurrent,
    contextUsageRatio,
    onCompressContext,
    visibleEntries,
  ]);
  const handleSlashDispatch = useCallback(
    (cmd: SlashCommand, args: string) => {
      switch (cmd.name) {
        case "pin":
          if (lastAssistantId) onTogglePin(lastAssistantId);
          onComposerChange((current) => ({ ...current, draft: "" }));
          return;
        case "clear":
        case "search":
        case "help":
          onComposerChange((current) => ({ ...current, draft: "" }));
          return;
        case "chat":
          onComposerChange((current) => ({ ...current, draft: "", mode: "chat" }));
          return;
        case "plan":
          onComposerChange((current) => ({ ...current, draft: "", mode: "markdown_plan" }));
          return;
        case "run":
          onComposerChange((current) => ({ ...current, draft: "", mode: "plan" }));
          return;
        case "goal":
          onComposerChange((current) => ({ ...current, draft: "", mode: "goal" }));
          return;
        case "compress":
          setComposerBottomPanel(agent.slot_id, null);
          onComposerChange((current) => ({ ...current, draft: "" }));
          void onCompressContext(agent, visibleEntries, "manual");
          return;
        case "model":
          setComposerBottomPanel(agent.slot_id, "model");
          onComposerChange((current) => ({ ...current, draft: "" }));
          return;
        case "mcp": {
          const mcpCount = tools.filter(isMcpTool).length;
          setComposerBottomPanel(agent.slot_id, "mcp");
          onComposerChange((current) => ({ ...current, draft: "" }));
          notifyFeedback({
            tone: mcpCount > 0 ? "success" : "info",
            title: mcpCount > 0 ? text("MCP 列表已打开", "MCP list opened") : text("暂无可用 MCP", "No MCP tools available"),
            description:
              mcpCount > 0
                ? text(
                    `当前团队列有 ${mcpCount} 个可用 MCP。点击条目可插入 @工具名。`,
                    `This team column has ${mcpCount} available MCP tools. Select one to insert its @mention.`,
                  )
                : text(
                    "已打开 MCP 列表。可以先到 MCP / 技能商店安装并挂载能力。",
                    "The MCP list is open. Install and attach capabilities from the MCP / Skill marketplace first.",
                  ),
          });
          return;
        }
        case "tool": {
          const name = args.replace(/^@/, "").split(/\s+/)[0] ?? "";
          if (name) {
            onComposerChange((current) => ({ ...current, draft: `@${name} ` }));
            window.requestAnimationFrame(() => composerRef.current?.focus());
          }
          return;
        }
        default: {
          const exhaustive: never = cmd.name;
          void exhaustive;
        }
      }
    },
    [
      agent,
      lastAssistantId,
      onCompressContext,
      onComposerChange,
      onTogglePin,
      setComposerBottomPanel,
      text,
      tools,
      visibleEntries,
    ],
  );
  const submitComposer = () => {
    if (!composer.draft.trim() || isSending) return;
    onSend(composer.draft.trim(), selectedTarget, selectedMode);
  };
  const columnStyle =
    fullscreen
      ? { flex: "1 1 100%", minWidth: "min(100%, 400px)" }
      : visibleColumnCount && visibleColumnCount <= 2
        ? { flex: "1 1 320px", minWidth: "min(320px, 100%)" }
        : { flex: "1 0 clamp(288px, 21vw, 304px)", minWidth: "min(288px, 100%)" };

  return (
    <div
      ref={setScrollRef}
      role="region"
      aria-label={`${agentDisplayName} ${roleLabel} ${text("列", "column")}`}
      className={cn(
        "flex h-full min-w-0 snap-start flex-col overflow-hidden border-r border-slate-100 bg-white transition-opacity duration-150",
        isLeader ? "border-l-2 border-l-slate-800" : "",
        isFlashing ? "opacity-60" : "opacity-100",
      )}
      style={columnStyle}
      onClick={onFocus}
    >
      <div className="flex min-h-14 shrink-0 items-center justify-between gap-3 border-b border-slate-100 bg-white px-3 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <div
            aria-hidden="true"
            className={cn(
              "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-white",
              isLeader ? "bg-slate-950" : "bg-slate-700",
            )}
          >
            {isLeader ? <UsersRound className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <div className="truncate text-[14px] font-semibold text-slate-950" title={agentDisplayName}>{agentDisplayName}</div>
              {isLeader ? <Badge tone="running">{text("队长", "Leader")}</Badge> : null}
              <Badge tone={teamAgentStatusTone(status)}>{teamAgentStatusLabel(status)}</Badge>
            </div>
            <div className="mt-0.5 truncate text-[11px] text-slate-500">
              {providerLabel} / {modelLabel}
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <ContextSummaryManager
            summary={activeCompression}
            onRecompress={() => {
              handleCompressContext();
            }}
            onClear={() => {
              onClearContextCompression(agent.slot_id, activeCompression?.branchKey ?? compressionBranchKey);
              notifyFeedback({
                tone: "info",
                title: text("摘要已清除", "Context summary cleared"),
                description: text(
                  `“${agent.agent_name}”后续发送将重新携带原始上下文内容。`,
                  `${agent.agent_name} will use the original conversation context on the next send.`,
                ),
              });
            }}
            text={text}
          />
          {!isLeader ? (
            <button
              type="button"
              aria-label={text("移除成员", "Remove teammate")}
              title={text("移除成员", "Remove teammate")}
              onClick={(event) => {
                event.stopPropagation();
                onRemove();
              }}
              className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-transparent text-slate-400 hover:border-red-100 hover:bg-red-50 hover:text-red-600"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          ) : null}
          {onFullscreen ? (
            <button
              type="button"
              aria-label={text("切换全屏列", "Toggle full-screen column")}
              title={text("切换全屏列", "Toggle full-screen column")}
              onClick={onFullscreen}
              className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-900"
            >
              <Maximize2 className="h-3.5 w-3.5" />
            </button>
          ) : null}
        </div>
      </div>

      <div ref={scrollerRef} className="min-h-0 flex-1 overflow-auto bg-white px-3 py-4">
        <div className="mx-auto w-full max-w-[760px] space-y-4">
          {branchVisibleEntries.length > 0 ? (
            branchVisibleEntries.map((entry) => (
              <TeamChatMessage
                key={entry.node.id}
                entry={entry}
                entries={visibleEntries}
                branchGroups={branchGroups}
                editingMessageId={editingMessageId}
                pinnedMessageIds={pinnedMessageIds}
                canRegenerate={entry.node.id === lastAssistantId && entry.node.state !== "streaming"}
                onStartEdit={onStartMessageEdit}
                onCancelEdit={onCancelMessageEdit}
                onSaveEdit={(nodeId, newContent) => {
                  const current = branchVisibleEntries.find((candidate) => candidate.node.id === nodeId);
                  if (!current) return;
                  onCancelMessageEdit();
                  onMessageActionSend(newContent, current.target);
                }}
                onCopy={async (nodeId) => {
                  const current = branchVisibleEntries.find((candidate) => candidate.node.id === nodeId);
                  const copied = await copyText(stripThinkBlocks(current?.node.content ?? ""));
                  if (!copied) {
                    notifyFeedback({
                      tone: "error",
                      title: text("复制失败", "Copy failed"),
                      description: text(
                        "当前浏览器未允许写入剪贴板，请检查权限后重试。",
                        "The browser could not write to the clipboard. Check permissions and retry.",
                      ),
                    });
                  }
                  return copied;
                }}
                onRegenerate={(nodeId) => {
                  onBranchMessage(nodeId, branchVisibleEntries);
                }}
                onTogglePin={onTogglePin}
                onOpenInspector={onOpenMessageInspector}
                onBranch={(nodeId) => onBranchMessage(nodeId, branchVisibleEntries)}
                onSwitchBranch={onSwitchBranch}
              />
            ))
          ) : (
            <div className="rounded-lg bg-slate-50 px-4 py-5 text-center text-xs text-slate-500">
              {team.name} {agentDisplayName}
            </div>
          )}
        </div>

        {conversationSupplement ? <div className="mx-auto w-full max-w-[760px]">{conversationSupplement}</div> : null}

        {!hideTaskSteps ? (
          <details className="mx-auto mt-4 w-full max-w-[760px] border-t border-slate-100 px-1 py-3">
            <summary className="cursor-pointer text-xs font-semibold text-slate-700">
              {text("查看步骤", "View steps")} ·{" "}
              {text(`${taskScope.length} 项任务`, `${taskScope.length} tasks`)}
            </summary>
            <div className="mt-3 divide-y divide-slate-100">
              {taskScope.length > 0 ? (
                taskScope.map((task) => (
                  <div key={task.id} className="px-1 py-2.5">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="truncate text-xs font-medium text-slate-900">{task.subject}</div>
                        <div className="mt-0.5 text-[11px] text-slate-500">{task.description || "-"}</div>
                      </div>
                      <Badge tone={teamTaskStatusTone(task.status)}>{teamTaskStatusLabel(task.status)}</Badge>
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-[11px] text-slate-400">{text("暂无步骤", "No steps yet")}</div>
              )}
            </div>
          </details>
        ) : null}

      </div>

      <div
        className="shrink-0 border-t border-slate-100 bg-white px-3 pb-4 pt-4"
        data-testid={`team-composer-${agent.slot_id}`}
      >
        <div className="relative mx-auto w-full max-w-3xl">
          <TeamBottomPopover
            open={bottomPanel !== null}
            onClose={() => setComposerBottomPanel(agent.slot_id, null)}
            align={bottomPanel === "model" ? "right" : "left"}
            title={
              bottomPanel === "model"
                ? text("切换模型", "Switch model")
                : bottomPanel === "mcp"
                  ? text("可用 MCP", "Available MCP")
                : text("输入设置", "Composer settings")
            }
          >
            {bottomPanel === "model" ? (
              <TeamModelPanel
                providers={modelOptions}
                selectedProviderId={selectedProviderId}
                selectedModelId={selectedModelId}
                modelLabelFallback={modelLabel}
                onModelChange={(providerId, modelId) => onModelChange(agent.slot_id, providerId, modelId)}
                text={text}
              />
            ) : (
              <TeamComposerSettingsPanel
                workspaceMode={selectedMode}
                onWorkspaceModeChange={(mode) => onComposerChange((current) => ({ ...current, mode }))}
                attachmentNames={attachments.map((attachment) => attachment.name)}
                onAddFiles={() => addComposerFiles(agent.slot_id)}
                tools={tools}
                onInsertMention={handleInsertMention}
                text={text}
                contextMaxTokens={contextMaxTokens}
                onContextMaxTokensChange={onContextMaxTokensChange}
                autoCompressionRatio={autoCompressionRatio}
                onAutoCompressionRatioChange={onAutoCompressionRatioChange}
                pluginsInitiallyOpen={bottomPanel === "mcp"}
              />
            )}
          </TeamBottomPopover>
          <ChatComposer
            ref={composerRef}
            containerClassName="px-0 sm:px-0 lg:px-0"
            frameClassName="rounded-lg border-slate-200 shadow-none [&_textarea]:placeholder:text-slate-500"
            draft={composer.draft}
            onDraftChange={(draft) => onComposerChange((current) => ({ ...current, draft }))}
            onSubmit={submitComposer}
            onPause={onStopWake}
            isStreaming={canStopWake}
            mode={selectedMode}
            onChangeMode={(mode) => onComposerChange((current) => ({ ...current, mode }))}
            placeholder={teamComposerPlaceholder(selectedMode, text)}
            optionsOpen={bottomPanel !== null}
            onOptionsToggle={() =>
              setComposerBottomPanel(
                agent.slot_id,
                bottomPanel === "settings" || bottomPanel === "mcp" ? null : "settings",
              )
            }
            goalModeToggleVisible={false}
            metadata={<TeamComposerMetadataRow usage={usageSummary} text={text} />}
            bottomCenter={
              <div className="flex min-w-0 flex-1 items-center justify-end gap-1.5">
                <ContextRing
                  ratio={contextUsageRatio}
                  currentTokens={contextUsageCurrent}
                  rawTokens={rawContextUsageCurrent}
                  limitTokens={contextMaxTokens}
                  onCompress={handleCompressContext}
                  disabled={canStopWake}
                  status={activeCompression?.status ?? "idle"}
                />
                <button
                  type="button"
                  onClick={() =>
                    setComposerBottomPanel(agent.slot_id, bottomPanel === "model" ? null : "model")
                  }
                  className="inline-flex h-8 min-w-0 max-w-[8rem] items-center gap-1 rounded-md px-2 text-xs text-slate-600 transition-colors hover:bg-slate-100"
                  aria-label={text(`切换模型：${modelLabel}`, `Switch model: ${modelLabel}`)}
                  title={modelLabel}
                >
                  <Brain aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{modelLabel}</span>
                </button>
              </div>
            }
            attachments={attachments}
            onRemoveAttachment={(attachmentId) => removeComposerAttachment(agent.slot_id, attachmentId)}
            isEditLocked={isSending}
            onSlashDispatch={handleSlashDispatch}
          />
          <input
            ref={fileInputRef}
            type="file"
            multiple
            aria-label={text("添加照片和文件", "Add photos and files")}
            className="hidden"
            onChange={(event) => handleComposerFilesSelected(agent.slot_id, event)}
          />
        </div>
      </div>
    </div>
  );
}
