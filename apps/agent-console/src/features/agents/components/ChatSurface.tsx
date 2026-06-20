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
  type ReactNode,
} from "react";
import {
  Brain,
  ChevronRight,
  ListChecks,
  Paperclip,
  PauseCircle,
  Pencil,
  PlayCircle,
  PlugZap,
  Target,
  Trash2,
  X,
} from "lucide-react";

import { ConfigDialog } from "../../../components/ui/config-dialog";
import { notifyFeedback } from "../../../components/ui/feedback-toast";
import { Button } from "../../../components/ui/button";
import { Textarea } from "../../../components/ui/input";
import { useI18n } from "../../../lib/i18n";
import { cn } from "../../../lib/utils";
import {
  useWorkspaceStore,
  type ConversationNode,
} from "../../../stores/workspaceStore";
import {
  compressAgentWorkspaceContext,
  type AgentDefinition,
  type AgentAttachmentPayload,
  type AgentChatStreamMessage,
  type AgentChatStreamPayload,
  type LocalAgentConnection,
  type ToolMetadata,
  type WorkspaceContextCompressionResponse,
} from "../../tasks/api";
import type { ChatStreamController } from "../hooks/useChatStream";
import { useOutsideClick } from "../hooks/useOutsideClick";
import { copyText } from "../lib/clipboard";
import { stripThinkBlocks } from "../lib/copyText";
import {
  COMPRESSION_PROMPT_VERSION,
  SUMMARY_SCHEMA_VERSION,
  contextCompressionBranchKey,
  isCompressionSummaryUsable,
  normalizeModelId,
  selectBestCompressionSummary,
  serializeContextNode,
  uncoveredContextPath,
  type ContextCompressionSummary,
} from "../lib/contextCompression";
import { AUTO_COMPRESSION_RATIO_DEFAULT } from "../lib/contextTokens";
import { estimateTextTokens } from "../lib/contextTruncation";
import { planApprovalGate } from "../lib/planApprovalGate";
import type { SlashCommand } from "../lib/slashCommands";
import { extractToolMentions } from "../lib/toolMentions";
import type { InspectorSection, WorkspaceMode } from "../lib/types";
import {
  ChatComposer,
  type ComposerAttachment,
} from "./ChatComposer";
import { ChatMessageList, type ChatMessageListHandle } from "./ChatMessageList";
import type { UsageSummary } from "./InspectorDrawer";
import { modelOptionDisplay, type ModelOption } from "./ModelPicker";
import { PlanApprovalPanel } from "./PlanApprovalPanel";
import { ContextRing } from "./ContextRing";
import { ContextSummaryManager } from "./ContextSummaryManager";
import { ContextMaxTokensSlider } from "./ContextMaxTokensSlider";
import { editFormShouldSubmit } from "./MessageEditForm";
import { WorkspaceShellBar } from "./WorkspaceShellBar";

const MAX_ATTACHMENT_TEXT_BYTES = 120_000;

export type LocalAgentSubmitContext = {
  workspace_mode: WorkspaceMode;
  mode: AgentChatStreamPayload["mode"];
  model_provider?: string | null;
  model_name?: string | null;
  messages: AgentChatStreamMessage[];
  active_leaf_id?: string | null;
  active_branch_id?: string | null;
  pinned_node_ids: string[];
  context_window_turns: number;
  tool_mentions: NonNullable<AgentChatStreamPayload["tool_mentions"]>;
  attachment_names: string[];
  attachments: AgentAttachmentPayload[];
  context_max_tokens?: number;
  compressed_context: AgentChatStreamPayload["compressed_context"];
};

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
  runReturnTarget?: {
    agentId: string;
    conversationId?: string | null;
  };
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
  /** Search jump target; `seq` increments even when the same node is selected twice. */
  jumpTarget?: { nodeId: string; seq: number } | null;
  onCreateTeamFromConversation?: () => void;
  isCreatingTeam?: boolean;
  agents?: AgentDefinition[];
  agentsLoading?: boolean;
  onAgentChange?: (agentId: string) => void;
  localAgentEnabled?: boolean;
  localAgentConnections?: LocalAgentConnection[];
  selectedLocalConnectionId?: string | null;
  onLocalAgentTargetChange?: (connectionId: string) => void;
  localAgentControl?: ReactNode;
  localAgentPending?: boolean;
  onLocalAgentSubmit?: (
    goal: string,
    context: LocalAgentSubmitContext,
  ) => Promise<boolean | void> | boolean | void;
};

export function ChatSurface(props: ChatSurfaceProps): JSX.Element {
  const {
    agentId,
    agentName,
    modelLabel,
    workspaceMode,
    onWorkspaceModeChange,
    activeRunId,
    runStatus,
    runCreatedAt,
    runReturnTarget,
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
    onCreateTeamFromConversation,
    isCreatingTeam = false,
    agents = [],
    agentsLoading = false,
    onAgentChange,
    localAgentEnabled = false,
    localAgentConnections = [],
    selectedLocalConnectionId = null,
    onLocalAgentTargetChange,
    localAgentControl = null,
    localAgentPending = false,
    onLocalAgentSubmit,
  } = props;

  const { text } = useI18n();
  const draft = useWorkspaceStore((state) => state.draft);
  const setDraft = useWorkspaceStore((state) => state.setDraft);
  const nodesById = useWorkspaceStore((state) => state.nodesById);
  const rootNodeId = useWorkspaceStore((state) => state.rootNodeId);
  const activeLeafId = useWorkspaceStore((state) => state.activeLeafId);
  const togglePinned = useWorkspaceStore((state) => state.togglePinned);
  const pinnedNodeIds = useWorkspaceStore((state) => state.pinnedNodeIds);
  const contextMaxTokens = useWorkspaceStore((state) => state.contextMaxTokens);
  const setContextMaxTokens = useWorkspaceStore((state) => state.setContextMaxTokens);
  const autoCompressionRatio = useWorkspaceStore((state) => state.autoCompressionRatio);
  const setAutoCompressionRatio = useWorkspaceStore((state) => state.setAutoCompressionRatio);
  const contextCompressions = useWorkspaceStore((state) => state.contextCompressions);
  const setContextCompression = useWorkspaceStore((state) => state.setContextCompression);
  const clearContextCompression = useWorkspaceStore((state) => state.clearContextCompression);
  const currentConversationId = useWorkspaceStore((state) => state.currentConversationId);
  const dismissedPlanNodeIds = useWorkspaceStore((state) => state.dismissedPlanNodeIds);
  const dismissPlanNode = useWorkspaceStore((state) => state.dismissPlanNode);
  const activeStream = useWorkspaceStore((state) => state.activeStream);

  const activePath = useMemo(
    () => buildActivePath(nodesById, activeLeafId, rootNodeId),
    [nodesById, activeLeafId, rootNodeId],
  );
  const activeGoalNode = useMemo(
    () => findActiveGoalNode(activePath),
    [activePath],
  );

  // Raw context usage is the full visible history. Effective usage mirrors the
  // next prompt after semantic compression: summary + pinned/uncovered raw
  // messages + draft.
  const rawContextUsageCurrent = useMemo(
    () =>
      activePath.reduce((sum, node) => {
        const metered =
          (node.metadata.input_tokens ?? 0) + (node.metadata.output_tokens ?? 0);
        return sum + Math.max(metered, estimateTextTokens(node.content));
      }, estimateTextTokens(draft)),
    [activePath, draft],
  );
  const compressionBranchKey = useMemo(
    () => contextCompressionBranchKey(currentConversationId, activeLeafId),
    [activeLeafId, currentConversationId],
  );
  const activeCompression = useMemo(
    () =>
      selectBestCompressionSummary({
        summaries: contextCompressions,
        branchKey: compressionBranchKey,
        activePath,
        pinnedNodeIds,
        providerId: selectedProviderId,
        modelId: selectedModelId,
      }) ?? contextCompressions[compressionBranchKey] ?? null,
    [
      activePath,
      compressionBranchKey,
      contextCompressions,
      pinnedNodeIds,
      selectedModelId,
      selectedProviderId,
    ],
  );
  const contextUsageCurrent = useMemo(() => {
    if (
      !isCompressionSummaryUsable({
        summary: activeCompression,
        branchKey: compressionBranchKey,
        activePath,
        pinnedNodeIds,
        providerId: selectedProviderId,
        modelId: selectedModelId,
      })
    ) {
      return rawContextUsageCurrent;
    }
    const uncovered = uncoveredContextPath({
      activePath,
      pinnedNodeIds,
      summary: activeCompression,
    });
    const uncoveredTokens = uncovered.reduce((sum, node) => {
      const metered =
        (node.metadata.input_tokens ?? 0) + (node.metadata.output_tokens ?? 0);
      return sum + Math.max(metered, estimateTextTokens(node.content));
    }, 0);
    const summaryTokens = Math.max(
      activeCompression?.estimatedSummaryTokens ?? 0,
      estimateTextTokens(activeCompression?.summary ?? ""),
    );
    return summaryTokens + uncoveredTokens + estimateTextTokens(draft);
  }, [
    activeCompression,
    activePath,
    compressionBranchKey,
    draft,
    pinnedNodeIds,
    rawContextUsageCurrent,
    selectedModelId,
    selectedProviderId,
  ]);
  const contextUsageRatio = contextMaxTokens > 0 ? contextUsageCurrent / contextMaxTokens : 0;

  const tail = activePath.length > 0 ? activePath[activePath.length - 1] : null;
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
  const [goalEditOpen, setGoalEditOpen] = useState(false);
  const [planSubmitting, setPlanSubmitting] = useState(false);
  const [bottomPanel, setBottomPanel] = useState<"tools" | "model" | "mcp" | null>(null);
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const optionsTriggerRef = useRef<HTMLButtonElement | null>(null);
  const chatListRef = useRef<ChatMessageListHandle | null>(null);
  const attachmentsRef = useRef<ComposerAttachment[]>([]);
  const compressionInFlightRef = useRef<string | null>(null);
  const backgroundCompressionKeyRef = useRef<string | null>(null);

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

  useEffect(() => {
    if (!activeGoalNode) setGoalEditOpen(false);
  }, [activeGoalNode]);

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

  const buildLocalAgentSubmitContext = useCallback(
    (goal: string): LocalAgentSubmitContext => {
      const store = useWorkspaceStore.getState();
      const path = store.activePath();
      return {
        workspace_mode: workspaceMode,
        mode: workspaceMode,
        model_provider: selectedProviderId,
        model_name: selectedModelId,
        messages: serializeLocalAgentMessages(path),
        active_leaf_id: store.activeLeafId,
        active_branch_id: store.activeLeafId,
        pinned_node_ids: store.pinnedNodeIds,
        context_window_turns: store.contextWindowTurns,
        tool_mentions: extractToolMentions(goal, tools),
        attachment_names: attachmentNames,
        attachments: attachmentPayloads,
        context_max_tokens: store.contextMaxTokens,
        compressed_context:
          activeCompression === null
            ? null
            : {
                summary: activeCompression.summary,
                branch_id: store.activeLeafId,
                coverage_node_ids: activeCompression.coverageNodeIds,
                coverage_path_hash: activeCompression.coveragePathHash,
                summary_schema_version: SUMMARY_SCHEMA_VERSION,
                compression_prompt_version: COMPRESSION_PROMPT_VERSION,
                compressor_provider: activeCompression.compressorProvider,
                compressor_model: activeCompression.compressorModel,
                estimated_original_tokens: activeCompression.estimatedOriginalTokens,
                estimated_summary_tokens: activeCompression.estimatedSummaryTokens,
                cache_status: activeCompression.cacheStatus ?? null,
              },
      };
    },
    [
      activeCompression,
      attachmentNames,
      attachmentPayloads,
      selectedModelId,
      selectedProviderId,
      tools,
      workspaceMode,
    ],
  );

  const commitCompressionResponse = useCallback(
    (
      branchKey: string,
      response: WorkspaceContextCompressionResponse,
    ): ContextCompressionSummary => {
      const summary: ContextCompressionSummary = {
        branchKey,
        summary: response.summary,
        coverageNodeIds: response.coverage_node_ids,
        coveragePathHash: response.coverage_path_hash,
        lastCoveredNodeId: response.last_covered_node_id,
        summarySchemaVersion: response.summary_schema_version,
        compressionPromptVersion: response.compression_prompt_version,
        compressorProvider: response.compressor_provider,
        compressorModel: response.compressor_model,
        estimatedOriginalTokens: response.estimated_original_tokens,
        estimatedSummaryTokens: response.estimated_summary_tokens,
        estimatedUncoveredTokens: response.estimated_uncovered_tokens,
        status: response.status === "provider_error" ? "error" : "ready",
        cacheStatus: response.cache_status,
        error: response.error ?? null,
        createdAt: response.created_at,
        updatedAt: response.updated_at,
      };
      setContextCompression(branchKey, summary);
      return summary;
    },
    [setContextCompression],
  );

  const compressCurrentContext = useCallback(
    async (reason: "manual" | "background" | "pre_send"): Promise<ContextCompressionSummary | null> => {
      const store = useWorkspaceStore.getState();
      const path = store.activePath();
      const branchKey = contextCompressionBranchKey(
        store.currentConversationId,
        store.activeLeafId,
      );
      if (compressionInFlightRef.current !== null) {
        if (reason === "manual") {
          notifyFeedback({
            tone: "info",
            title: text("上下文仍在压缩", "Context compression is still running"),
            description: text(
              "请稍候，当前工作台已经在生成摘要。",
              "Please wait while the workspace finishes generating the current summary.",
            ),
          });
        }
        return null;
      }
      const eligible = path.filter(
        (node) =>
          (node.role === "user" || node.role === "assistant" || node.role === "system") &&
          !store.pinnedNodeIds.includes(node.id) &&
          node.content.trim().length > 0,
      );
      if (eligible.length === 0) {
        if (reason === "manual") {
          notifyFeedback({
            tone: "warning",
            title: text("暂无可压缩内容", "Nothing to compress yet"),
            description: text(
              "至少需要一段未固定的会话内容后，才能生成上下文摘要。",
              "Add some unpinned conversation content before generating a context summary.",
            ),
          });
        }
        return null;
      }

      const existing =
        reason === "manual" ? null : store.contextCompressions[branchKey] ?? null;
      compressionInFlightRef.current = branchKey;
      setContextCompression(branchKey, {
        ...(existing ?? {
          branchKey,
          summary: "",
          coverageNodeIds: [],
          coveragePathHash: "",
          lastCoveredNodeId: null,
          summarySchemaVersion: SUMMARY_SCHEMA_VERSION,
          compressionPromptVersion: COMPRESSION_PROMPT_VERSION,
          compressorProvider: normalizeModelId(selectedProviderId),
          compressorModel: normalizeModelId(selectedModelId),
          estimatedOriginalTokens: 0,
          estimatedSummaryTokens: 0,
          estimatedUncoveredTokens: 0,
          cacheStatus: undefined,
          error: null,
          createdAt: new Date().toISOString(),
        }),
        status: "pending",
        updatedAt: new Date().toISOString(),
      });

      try {
        const response = await compressAgentWorkspaceContext(agentId, {
          model_provider: selectedProviderId,
          model_name: selectedModelId,
          messages: path.map(serializeContextNode),
          pinned_node_ids: store.pinnedNodeIds,
          existing_summary: existing?.summary ?? null,
          prior_coverage_node_ids: existing?.coverageNodeIds ?? [],
          prior_coverage_path_hash: existing?.coveragePathHash ?? null,
          summary_schema_version: SUMMARY_SCHEMA_VERSION,
          compression_prompt_version: COMPRESSION_PROMPT_VERSION,
          compressor_provider: existing?.compressorProvider ?? selectedProviderId,
          compressor_model: existing?.compressorModel ?? selectedModelId,
        });
        const summary = commitCompressionResponse(branchKey, response);
        if (reason === "manual") {
          notifyFeedback({
            tone: "success",
            title: text("上下文已压缩", "Context compressed"),
            description: text(
              `已为 ${response.coverage_node_ids.length} 条消息生成摘要，预计从 ${Math.round(
                response.estimated_original_tokens,
              )} 标记压缩到 ${Math.round(response.estimated_summary_tokens)} 标记。`,
              `Summarized ${response.coverage_node_ids.length} messages, reducing the estimated prompt from ${Math.round(
                response.estimated_original_tokens,
              )} to ${Math.round(response.estimated_summary_tokens)} tokens.`,
            ),
          });
        }
        return summary;
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        const now = new Date().toISOString();
        setContextCompression(branchKey, {
          ...(existing ?? {
            branchKey,
            summary: "",
            coverageNodeIds: [],
            coveragePathHash: "",
            lastCoveredNodeId: null,
            summarySchemaVersion: SUMMARY_SCHEMA_VERSION,
            compressionPromptVersion: COMPRESSION_PROMPT_VERSION,
            compressorProvider: normalizeModelId(selectedProviderId),
            compressorModel: normalizeModelId(selectedModelId),
            estimatedOriginalTokens: 0,
            estimatedSummaryTokens: 0,
            estimatedUncoveredTokens: 0,
            createdAt: now,
          }),
          status: "error",
          cacheStatus: "error",
          error: message,
          updatedAt: now,
        });
        if (reason === "manual") {
          notifyFeedback({
            tone: "error",
            title: text("上下文压缩失败", "Context compression failed"),
            description: message || text("请稍后重试。", "Please try again shortly."),
          });
        }
        return null;
      } finally {
        if (compressionInFlightRef.current === branchKey) {
          compressionInFlightRef.current = null;
        }
      }
    },
    [
      agentId,
      commitCompressionResponse,
      selectedModelId,
      selectedProviderId,
      setContextCompression,
      text,
    ],
  );

  const handleCompressContext = useCallback((): void => {
    if (stream.isStreaming) return;
    setBottomPanel(null);
    void compressCurrentContext("manual");
  }, [compressCurrentContext, stream.isStreaming]);

  useEffect(() => {
    if (stream.isStreaming) return;
    if (contextUsageRatio < autoCompressionRatio) return;
    const last = activePath[activePath.length - 1];
    if (!last || last.role !== "assistant" || last.state !== "done") return;
    const key = `${compressionBranchKey}:${last.id}:${Math.round(contextUsageCurrent)}`;
    if (backgroundCompressionKeyRef.current === key) return;
    const usable = isCompressionSummaryUsable({
      summary: activeCompression,
      branchKey: compressionBranchKey,
      activePath,
      pinnedNodeIds,
      providerId: selectedProviderId,
      modelId: selectedModelId,
    });
    if (usable) return;
    backgroundCompressionKeyRef.current = key;
    const timer = window.setTimeout(() => {
      void compressCurrentContext("background");
    }, 350);
    return () => window.clearTimeout(timer);
  }, [
    activeCompression,
    activePath,
    autoCompressionRatio,
    compressionBranchKey,
    compressCurrentContext,
    contextUsageCurrent,
    contextUsageRatio,
    pinnedNodeIds,
    selectedModelId,
    selectedProviderId,
    stream.isStreaming,
  ]);

  // ─── Composer callbacks ────────────────────────────────────────────────
  const handleSubmit = useCallback(async (): Promise<boolean | void> => {
    const goal = draft.trim();
    if (goal.length === 0) return false;
    if (stream.isStreaming || localAgentPending) return false;

    if (contextUsageRatio >= autoCompressionRatio) {
      const usable = isCompressionSummaryUsable({
        summary: activeCompression,
        branchKey: compressionBranchKey,
        activePath,
        pinnedNodeIds,
        providerId: selectedProviderId,
        modelId: selectedModelId,
      });
      if (!usable) {
        await compressCurrentContext("pre_send");
      }
    }

    chatListRef.current?.notifyUserSubmit();
    if (onLocalAgentSubmit !== undefined) {
      const sent = await onLocalAgentSubmit(goal, buildLocalAgentSubmitContext(goal));
      if (sent === false) return false;
      setAttachments((current) => {
        for (const attachment of current) revokeAttachmentPreview(attachment);
        return [];
      });
      return true;
    }

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
    return true;
  }, [
    activeCompression,
    activePath,
    attachmentNames,
    attachmentPayloads,
    autoCompressionRatio,
    buildLocalAgentSubmitContext,
    compressionBranchKey,
    compressCurrentContext,
    contextUsageRatio,
    draft,
    localAgentPending,
    onLocalAgentSubmit,
    pinnedNodeIds,
    selectedModelId,
    selectedProviderId,
    stream,
    workspaceMode,
    text,
  ]);

  const handlePause = useCallback((): void => {
    stream.pause();
  }, [stream]);

  const handleResumeGoal = useCallback((): void => {
    if (!activeGoalNode) return;
    setGoalEditOpen(false);
    void stream.resume(activeGoalNode.id);
  }, [activeGoalNode, stream]);

  const handleEditGoal = useCallback((): void => {
    if (!activeGoalNode) return;
    if (stream.isStreaming && activeStream?.node_id === activeGoalNode.id) {
      stream.pause();
    }
    setGoalEditOpen(true);
  }, [activeGoalNode, activeStream, stream]);

  const handleCancelGoalEdit = useCallback((): void => {
    setGoalEditOpen(false);
  }, []);

  const handleSaveGoalEdit = useCallback(
    async (nextGoal: string): Promise<void> => {
      if (!activeGoalNode) return;
      const trimmed = nextGoal.trim();
      if (trimmed.length === 0) return;
      const storeState = useWorkspaceStore.getState();
      const previousGoal =
        activeGoalNode.metadata.goal_text || findPrevUserContent(activePath, activeGoalNode.id);
      const previousUserNode = findPrevUserNode(activePath, activeGoalNode.id);

      if (stream.isStreaming && activeStream?.node_id === activeGoalNode.id) {
        stream.pause();
      }

      if (previousUserNode) {
        storeState.updateNode(previousUserNode.id, {
          content: trimmed,
        });
      }

      storeState.updateNode(activeGoalNode.id, {
        state: "paused",
        metadata: {
          ...activeGoalNode.metadata,
          workspace_mode: "goal",
          goal_status: "paused",
          goal_text: trimmed,
          goal_phase: "paused",
          goal_message: text("目标已更新，准备继续追踪。", "Goal updated and ready to resume."),
          goal_cleared: false,
        },
      });

      setGoalEditOpen(false);
      onWorkspaceModeChange("goal");
      void stream.resume(activeGoalNode.id);

      if (previousGoal !== trimmed) {
        notifyFeedback({
          tone: "success",
          title: text("目标已更新", "Goal updated"),
          description: text(
            "已基于新目标继续追踪执行。",
            "The pursuit has resumed from the updated goal.",
          ),
        });
      }
    },
    [activeGoalNode, activePath, activeStream, onWorkspaceModeChange, stream, text],
  );

  const handleClearGoal = useCallback((): void => {
    if (!activeGoalNode) return;
    setGoalEditOpen(false);
    if (stream.isStreaming && activeStream?.node_id === activeGoalNode.id) {
      stream.pause();
    }
    useWorkspaceStore.getState().updateNode(activeGoalNode.id, {
      metadata: {
        ...activeGoalNode.metadata,
        goal_status: "cancelled",
        goal_message: text("目标追踪已清除。", "Goal tracking cleared."),
        goal_cleared: true,
      },
    });
  }, [activeGoalNode, activeStream, stream, text]);

  const handleRetry = useCallback(
    (nodeId: string): void => {
      const node = useWorkspaceStore.getState().nodesById[nodeId];
      if (
        node?.metadata.retry_disabled === true ||
        node?.metadata.orchestration?.source === "local_agent"
      ) {
        return;
      }
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
      const copied = await copyText(stripThinkBlocks(node.content));
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
    },
    [text],
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

  // ─── Branch callback (Phase 4 / Req 16) ────────────────────────────────
  const handleBranch = useCallback(
    (nodeId: string) => {
      const storeState = useWorkspaceStore.getState();
      const target = storeState.nodesById[nodeId];
      if (!target || target.role !== "assistant") return;

      const userNodeId = target.parent_id;
      if (!userNodeId) return;
      const userNode = storeState.nodesById[userNodeId];
      if (!userNode || userNode.role !== "user") return;

      const mode = target.metadata.workspace_mode ?? workspaceMode;
      const newAssistantId = storeState.appendNode({
        parent_id: userNodeId,
        role: "assistant",
        content: "",
        state: "streaming",
        metadata: { workspace_mode: mode },
        tool_calls: [],
        artifacts: [],
      });

      void stream.driveBranch({
        assistantNodeId: newAssistantId,
        goal: userNode.content,
        mode,
      });
    },
    [stream, workspaceMode],
  );

  // ─── Plan approval callbacks (Req 3) ───────────────────────────────────
  const handleApprovePlan = useCallback(async (): Promise<void> => {
    if (!planGate.visible || !planGate.planNode) return;
    const planNode = planGate.planNode;
    const storeState = useWorkspaceStore.getState();
    const sourceUser = planNode.parent_id ? storeState.nodesById[planNode.parent_id] : null;
    const goal =
      sourceUser?.role === "user" && sourceUser.content.trim().length > 0
        ? sourceUser.content
        : planNode.content;
    setPlanSubmitting(true);
    try {
      const newAssistantId = storeState.appendNode({
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
        goal,
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

  const handleShellToolMention = useCallback(
    (toolName: string): void => {
      handleInsertMention(toolName);
      setBottomPanel(null);
    },
    [handleInsertMention],
  );

  const handleClearContextSummary = useCallback(() => {
    clearContextCompression(compressionBranchKey);
    notifyFeedback({
      tone: "info",
      title: text("摘要已清除", "Context summary cleared"),
      description: text(
        "后续发送将重新携带原始上下文内容。",
        "The next send will include the original conversation context again.",
      ),
    });
  }, [clearContextCompression, compressionBranchKey, text]);

  // ─── Slash command dispatcher (v3 / Req 5) ─────────────────────────────
  const handleSlashDispatch = useCallback(
    (cmd: SlashCommand, args: string): void => {
      switch (cmd.name) {
        case "plan":
          onWorkspaceModeChange("markdown_plan");
          setDraft("");
          return;
        case "run":
          onWorkspaceModeChange("plan");
          setDraft("");
          return;
        case "chat":
          onWorkspaceModeChange("chat");
          setDraft("");
          return;
        case "goal":
          onWorkspaceModeChange("goal");
          setDraft("");
          return;
        case "compress":
          setBottomPanel(null);
          setDraft("");
          void compressCurrentContext("manual");
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
        case "mcp": {
          const mcpCount = tools.filter(isMcpTool).length;
          setBottomPanel("mcp");
          setDraft("");
          notifyFeedback({
            tone: mcpCount > 0 ? "success" : "info",
            title: mcpCount > 0 ? text("MCP 列表已打开", "MCP list opened") : text("暂无可用 MCP", "No MCP tools available"),
            description:
              mcpCount > 0
                ? text(
                    `当前智能体有 ${mcpCount} 个可用 MCP。点击条目可插入 @工具名。`,
                    `This agent has ${mcpCount} available MCP tools. Select one to insert its @mention.`,
                  )
                : text(
                    "已打开 MCP 列表。可以先到 MCP / 技能商店安装并挂载能力。",
                    "The MCP list is open. Install and attach capabilities from the MCP / Skill marketplace first.",
                  ),
          });
          return;
        }
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
      compressCurrentContext,
      setDraft,
      tail,
      text,
      tools,
      togglePinned,
    ],
  );

  return (
    <div className="flex h-full w-full min-w-0 flex-col bg-white">
      <WorkspaceShellBar
        agentId={agentId}
        agentName={agentName}
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
        onCreateTeamFromConversation={onCreateTeamFromConversation}
        isCreatingTeam={isCreatingTeam}
        agents={agents}
        agentsLoading={agentsLoading}
        onAgentChange={onAgentChange}
        localAgentEnabled={localAgentEnabled}
        localAgentConnections={localAgentConnections}
        selectedLocalConnectionId={selectedLocalConnectionId}
        onLocalAgentTargetChange={onLocalAgentTargetChange}
        localAgentControl={localAgentControl}
        runReturnTarget={runReturnTarget}
        summaryManager={
          <ContextSummaryManager
            summary={activeCompression}
            onRecompress={() => {
              void compressCurrentContext("manual");
            }}
            onClear={handleClearContextSummary}
            text={text}
          />
        }
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
        runReturnTarget={runReturnTarget}
        editingNodeId={editingNodeId}
        onStartEdit={handleStartEdit}
        onCancelEdit={handleCancelEdit}
        onSaveEdit={handleSaveEdit}
        onCopy={handleCopy}
        onRegenerate={handleRegenerate}
        isStreaming={stream.isStreaming}
        pinnedNodeIds={pinnedNodeIds}
        onTogglePin={togglePinned}
        onBranch={handleBranch}
        jumpTarget={props.jumpTarget ?? null}
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
          {activeCompression?.status === "pending" && (
            <div
              className="flex items-center gap-2 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-xs font-medium text-sky-700 shadow-sm"
              role="status"
              aria-live="polite"
            >
              <span className="h-2 w-2 animate-pulse rounded-full bg-sky-500 shadow-[0_0_0_4px_rgba(14,165,233,0.16)]" />
              <span>{text("正在压缩上下文...", "Compressing context...")}</span>
            </div>
          )}
          {activeGoalNode && (
            <GoalProgressRow
              node={activeGoalNode}
              isActiveStream={stream.isStreaming && activeStream?.node_id === activeGoalNode.id}
              onPause={handlePause}
              onResume={handleResumeGoal}
              onEdit={handleEditGoal}
              onClear={handleClearGoal}
              text={text}
            />
          )}
          <div className="relative">
            <BottomToolsPopover
              open={bottomPanel !== null}
              onClose={() => setBottomPanel(null)}
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
                  contextMaxTokens={contextMaxTokens}
                  onContextMaxTokensChange={setContextMaxTokens}
                  autoCompressionRatio={autoCompressionRatio}
                  onAutoCompressionRatioChange={setAutoCompressionRatio}
                  pluginsInitiallyOpen={bottomPanel === "mcp"}
                />
              )}
            </BottomToolsPopover>
            <ChatComposer
              ref={composerRef}
              draft={draft}
              onDraftChange={setDraft}
              onSubmit={handleSubmit}
              onPause={handlePause}
              isStreaming={stream.isStreaming}
              mode={workspaceMode}
              streamingLabel={
                activeGoalNode && activeStream?.node_id === activeGoalNode.id
                  ? text("暂停目标", "Pause goal")
                  : undefined
              }
              onChangeMode={onWorkspaceModeChange}
              placeholder={placeholder}
              optionsOpen={bottomPanel !== null}
              onOptionsToggle={() =>
                setBottomPanel((current) =>
                  current === "tools" || current === "mcp" ? null : "tools",
                )
              }
              optionsTriggerRef={optionsTriggerRef}
              goalModeToggleVisible={false}
              metadata={<ComposerMetadataRow usage={metadataUsage} text={text} />}
              bottomCenter={
                <div className="flex items-center gap-2">
                  <ContextRing
                    ratio={contextUsageRatio}
                    currentTokens={contextUsageCurrent}
                    rawTokens={rawContextUsageCurrent}
                    limitTokens={contextMaxTokens}
                    onCompress={handleCompressContext}
                    disabled={stream.isStreaming}
                    status={activeCompression?.status ?? "idle"}
                  />
                  <button
                    type="button"
                    onClick={() => setBottomPanel((current) => (current === "model" ? null : "model"))}
                    className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 transition-colors"
                  >
                    {modelLabel}
                    <svg className="h-3 w-3" viewBox="0 0 12 12" fill="none"><path d="M3 5l3 3 3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  </button>
                </div>
              }
              attachments={attachments}
              onRemoveAttachment={handleRemoveAttachment}
              isEditLocked={editingNodeId !== null || goalEditOpen || localAgentPending}
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
      {goalEditOpen && activeGoalNode ? (
        <GoalEditDialog
          goal={activeGoalNode.metadata.goal_text || activeGoalNode.content || ""}
          onCancel={handleCancelGoalEdit}
          onSave={handleSaveGoalEdit}
          text={text}
        />
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Bottom tools panel helpers
// ---------------------------------------------------------------------------

function AutoCompressionRatioControl({
  value,
  onChange,
  text,
}: {
  value: number;
  onChange: (next: number) => void;
  text: (zh: string, en: string) => string;
}): JSX.Element {
  const pct = Math.round(value * 100);
  return (
    <div className="mt-2 flex flex-col gap-1.5">
      <div className="flex items-center justify-between gap-2">
        <label className="text-[11px] font-medium text-slate-700">
          {text("自动压缩阈值", "Auto compression threshold")}
        </label>
        <span className="font-mono text-[11px] text-slate-600">{pct}%</span>
      </div>
      <input
        type="range"
        min={0.5}
        max={0.95}
        step={0.05}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        aria-label={text("自动压缩阈值", "Auto compression threshold")}
        className="h-1 accent-slate-900"
      />
      <p className="text-[10px] leading-4 text-slate-500">
        {text(
          `达到 ${pct}% 后自动压缩，默认 ${Math.round(AUTO_COMPRESSION_RATIO_DEFAULT * 100)}%`,
          `Compress automatically at ${pct}%, default ${Math.round(AUTO_COMPRESSION_RATIO_DEFAULT * 100)}%`,
        )}
      </p>
    </div>
  );
}

type ToolsPanelProps = {
  tools: ToolMetadata[];
  onInsertMention: (toolName: string) => void;
  text: (zh: string, en: string) => string;
  workspaceMode: WorkspaceMode;
  onWorkspaceModeChange: (mode: WorkspaceMode) => void;
  attachmentNames: string[];
  onAddFiles: () => void;
  contextMaxTokens?: number;
  onContextMaxTokensChange?: (value: number) => void;
  autoCompressionRatio?: number;
  onAutoCompressionRatioChange?: (value: number) => void;
  pluginsInitiallyOpen?: boolean;
};

function BottomToolsPopover({
  open,
  onClose,
  align,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  align: "left" | "right";
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
      className={cn(
        "absolute bottom-[58px] left-4 right-4 z-30 max-h-[min(70vh,480px)] overflow-y-auto rounded-2xl border border-slate-200 bg-white p-2 shadow-none",
        align === "right"
          ? "sm:left-auto sm:right-4 sm:w-[280px]"
          : "sm:left-4 sm:right-auto sm:w-[280px]",
      )}
    >
      <div className="mb-2 flex items-center justify-between gap-2 border-b border-slate-100 px-1 pb-2">
        <div className="text-xs font-semibold text-slate-900">{title}</div>
        <button
          type="button"
          aria-label={`关闭${title}`}
          onClick={onClose}
          className="inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
        >
          <X aria-hidden="true" className="h-4 w-4" />
        </button>
      </div>
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
  contextMaxTokens,
  onContextMaxTokensChange,
  autoCompressionRatio,
  onAutoCompressionRatioChange,
  pluginsInitiallyOpen = false,
}: ToolsPanelProps): JSX.Element {
  const [pluginsOpen, setPluginsOpen] = useState(pluginsInitiallyOpen);
  const mcpTools = tools.filter(isMcpTool);

  useEffect(() => {
    if (pluginsInitiallyOpen) setPluginsOpen(true);
  }, [pluginsInitiallyOpen]);

  return (
    <div className="flex flex-col text-xs text-slate-800">
      {contextMaxTokens !== undefined && onContextMaxTokensChange && (
        <div className="border-b border-slate-100 px-2 py-1.5">
          <ContextMaxTokensSlider value={contextMaxTokens} onChange={onContextMaxTokensChange} />
          {autoCompressionRatio !== undefined && onAutoCompressionRatioChange && (
            <AutoCompressionRatioControl
              value={autoCompressionRatio}
              onChange={onAutoCompressionRatioChange}
              text={text}
            />
          )}
        </div>
      )}
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
      <ToolToggleRow
        icon={<Target aria-hidden="true" className="h-3.5 w-3.5" />}
        label={text("追踪目标模式", "Goal pursuit mode")}
        checked={workspaceMode === "goal"}
        onChange={(checked) => onWorkspaceModeChange(checked ? "goal" : "chat")}
      />
      <ToolActionRow
        icon={<PlugZap aria-hidden="true" className="h-3.5 w-3.5" />}
        ariaLabel={text("插件 / MCP（模型上下文协议）", "Plugins / MCP")}
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
        <div className="ml-4 mt-0.5 max-h-24 min-w-0 overflow-y-auto border-l border-slate-200 pl-1.5 pr-0.5">
          {mcpTools.length === 0 ? (
            <p className="px-2 py-1.5 text-xs text-slate-500">
              {text("暂无外部协议功能。", "No MCP capabilities")}
            </p>
          ) : (
            mcpTools.map((tool) => (
              <button
                key={`${tool.source ?? "tool"}:${tool.name}`}
                type="button"
                onClick={() => onInsertMention(tool.name)}
                className="block min-w-0 w-full rounded-md px-1.5 py-1 text-left text-[11px] text-slate-600 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
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
      className="flex max-h-48 flex-col gap-1 overflow-y-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
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
              "flex items-start gap-2.5 rounded-xl px-2.5 py-2.5 text-left text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400",
              selected || active
                ? "bg-slate-900 font-medium text-white"
                : "text-slate-700 hover:bg-slate-50",
            ].join(" ")}
          >
            <span
              className={cn(
                "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg",
                selected || active ? "bg-white/10 text-white" : "bg-slate-100 text-slate-600",
              )}
            >
              <Brain className="h-4 w-4" />
            </span>
            <ModelOptionText option={option} active={selected || active} />
          </button>
        );
      })}
    </div>
  );
}

function ModelOptionText({
  option,
  active,
}: {
  option: ModelOption;
  active: boolean;
}): JSX.Element {
  const display = modelOptionDisplay(option);

  return (
    <span className="min-w-0 flex-1">
      <span className="block truncate text-sm font-semibold">{display.title}</span>
      <span
        className={cn(
          "block truncate text-[11px] leading-4",
          active ? "text-slate-300" : "text-slate-500",
        )}
      >
        {display.subtitle}
      </span>
    </span>
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
  ariaLabel,
  label,
  trailing = null,
  onClick,
}: {
  icon: JSX.Element;
  ariaLabel?: string;
  label: ReactNode;
  trailing?: JSX.Element | null;
  onClick: () => void;
}): JSX.Element {
  return (
    <button
      type="button"
      aria-label={ariaLabel}
      onClick={onClick}
      className="flex min-h-7 w-full items-center gap-2 rounded-md px-1.5 text-left transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
    >
      <span className="flex h-4 w-4 shrink-0 items-center justify-center text-slate-500">
        {icon}
      </span>
      <span className="min-w-0 flex-1 truncate leading-4">{label}</span>
      {trailing ? (
        <span className="ml-auto flex h-4 w-4 shrink-0 items-center justify-center text-slate-400">
          {trailing}
        </span>
      ) : null}
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
}): JSX.Element | null {
  const isEmpty =
    usage.inputTokens === 0 &&
    usage.outputTokens === 0 &&
    usage.modelCalls === 0 &&
    usage.toolCalls === 0 &&
    usage.durationMs === 0;

  if (isEmpty) return null;

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

function GoalProgressRow({
  node,
  isActiveStream,
  onPause,
  onResume,
  onEdit,
  onClear,
  text,
}: {
  node: ConversationNode;
  isActiveStream: boolean;
  onPause: () => void;
  onResume: () => void;
  onEdit: () => void;
  onClear: () => void;
  text: (zh: string, en: string) => string;
}): JSX.Element {
  const status = node.metadata.goal_status ?? (node.state === "paused" ? "paused" : "running");
  const goal = node.metadata.goal_text || node.content || text("未命名目标", "Untitled goal");
  const [nowMs, setNowMs] = useState(() => Date.now());
  const isLive = status === "running" && (isActiveStream || node.state === "streaming");
  useEffect(() => {
    if (!isLive) return;
    setNowMs(Date.now());
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [isLive, node.id, node.metadata.goal_started_at, node.metadata.goal_elapsed_ms]);

  const elapsedMs = goalElapsedMs(node, nowMs, isLive);
  const phaseLabel = goalPhaseLabel(node.metadata.goal_phase, status, text);
  const canResume = node.state === "paused" || status === "paused";
  const canPause = status === "running" && isActiveStream && !canResume;
  const titleLabel =
    status === "completed"
      ? text("目标已完成", "Goal completed")
      : canResume
        ? text("目标已暂停", "Paused goal")
        : text("进行中的目标", "Goal in progress");
  const resumeLabel = text("恢复目标", "Resume goal");

  return (
    <div
      role="status"
      aria-live="polite"
      className="mx-auto w-[calc(100%-56px)] max-w-[760px] min-w-0 rounded-[18px] border border-slate-200/90 bg-white/95 px-3 py-1.5 text-[11px] leading-4 text-slate-700 shadow-[0_8px_20px_rgba(15,23,42,0.06)]"
    >
      <div className="flex min-w-0 items-center gap-2">
        <span
          className={cn(
            "mt-0.5 h-2 w-2 shrink-0 rounded-full",
            status === "failed" || status === "cancelled"
              ? "bg-rose-500"
              : status === "completed"
                ? "bg-emerald-500"
                : status === "paused" || status === "needs_input"
                  ? "bg-amber-500"
                  : "animate-pulse bg-sky-500",
          )}
        />
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <span className="shrink-0 font-medium text-slate-900">{titleLabel}</span>
            <span className="truncate text-slate-700" title={goal}>
              {goal}
            </span>
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[10px] text-slate-500">
            <span>{formatGoalElapsed(elapsedMs)}</span>
            {phaseLabel && (
              <>
                <span className="text-slate-300">·</span>
                <span>{phaseLabel}</span>
              </>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <IconButton
            label={text("编辑目标", "Edit goal")}
            onClick={onEdit}
            disabled={status === "completed" || status === "cancelled"}
          >
            <Pencil aria-hidden="true" className="h-3 w-3" />
          </IconButton>
          {canResume ? (
            <IconButton label={resumeLabel} onClick={onResume}>
              <PlayCircle aria-hidden="true" className="h-3 w-3" />
            </IconButton>
          ) : (
            <IconButton
              label={text("暂停目标", "Pause goal")}
              onClick={onPause}
              disabled={!canPause}
            >
              <PauseCircle aria-hidden="true" className="h-3 w-3" />
            </IconButton>
          )}
          <IconButton label={text("清除目标", "Clear goal")} onClick={onClear}>
            <Trash2 aria-hidden="true" className="h-3 w-3" />
          </IconButton>
        </div>
      </div>
    </div>
  );
}

function GoalEditDialog({
  goal,
  onCancel,
  onSave,
  text,
}: {
  goal: string;
  onCancel: () => void;
  onSave: (value: string) => void | Promise<void>;
  text: (zh: string, en: string) => string;
}): JSX.Element {
  const [value, setValue] = useState(goal);
  const [saving, setSaving] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const isComposingRef = useRef(false);

  useEffect(() => {
    setValue(goal);
  }, [goal]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => textareaRef.current?.focus());
    return () => {
      window.cancelAnimationFrame(frame);
    };
  }, [goal]);

  const canSubmit = value.trim().length > 0 && !saving;

  async function submit(): Promise<void> {
    if (!canSubmit) return;
    setSaving(true);
    try {
      await onSave(value);
    } finally {
      setSaving(false);
    }
  }

  return (
    <ConfigDialog
      open
      title={text("编辑目标", "Edit goal")}
      description={text("修改当前追踪中的目标内容。", "Edit the current pursuit goal.")}
      onClose={onCancel}
      className="max-w-lg"
    >
      <div className="grid gap-4 text-xs">
        <label className="grid gap-1.5">
          <span className="font-medium text-slate-600">{text("目标", "Goal")}</span>
          <Textarea
            id="goal-edit-textarea"
            ref={textareaRef}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.preventDefault();
                onCancel();
                return;
              }
              if (editFormShouldSubmit(event.nativeEvent, value, isComposingRef.current)) {
                event.preventDefault();
                void submit();
              }
            }}
            onCompositionStart={() => {
              isComposingRef.current = true;
            }}
            onCompositionEnd={() => {
              isComposingRef.current = false;
            }}
            rows={5}
            aria-label={text("编辑目标", "Edit goal")}
            className="min-h-32 max-h-[40vh] w-full resize-y text-sm leading-6"
          />
        </label>
        <div className="flex items-center justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={onCancel}
            aria-label={text("取消编辑目标", "Cancel goal edit")}
          >
            {text("取消", "Cancel")}
          </Button>
          <Button
            type="button"
            variant="primary"
            disabled={!canSubmit}
            onClick={() => {
              void submit();
            }}
            aria-label={text("保存目标", "Save goal")}
          >
            {saving ? text("保存中", "Saving") : text("保存", "Save")}
          </Button>
        </div>
      </div>
    </ConfigDialog>
  );
}

function IconButton({
  label,
  onClick,
  disabled = false,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: ReactNode;
}): JSX.Element {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      className="inline-flex h-6 w-6 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  );
}

function findActiveGoalNode(activePath: ConversationNode[]): ConversationNode | null {
  for (let index = activePath.length - 1; index >= 0; index -= 1) {
    const node = activePath[index];
    if (node.role !== "assistant") continue;
    if (node.metadata.workspace_mode !== "goal" && !node.metadata.goal_status) continue;
    if (node.metadata.goal_cleared) return null;
    const status = node.metadata.goal_status;
    if (status === "cancelled" || status === undefined) return null;
    return node;
  }
  return null;
}

function findPrevUserContent(activePath: ConversationNode[], nodeId: string): string {
  return findPrevUserNode(activePath, nodeId)?.content ?? "";
}

function findPrevUserNode(activePath: ConversationNode[], nodeId: string): ConversationNode | null {
  const index = activePath.findIndex((node) => node.id === nodeId);
  for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
    const node = activePath[cursor];
    if (node.role === "user") return node;
  }
  return null;
}

function goalPhaseLabel(
  phase: string | undefined,
  status: ConversationNode["metadata"]["goal_status"],
  text: (zh: string, en: string) => string,
): string {
  if (status === "paused") return text("已暂停", "Paused");
  if (status === "needs_input") return text("需要输入", "Needs input");
  if (status === "failed") return text("失败", "Failed");
  if (status === "completed") return text("已完成", "Completed");
  if (phase === "planning") return text("规划中", "Planning");
  if (phase === "executing") return text("执行中", "Executing");
  if (phase === "orchestrating") return text("编排中", "Orchestrating");
  return text("运行中", "Running");
}

function goalElapsedMs(node: ConversationNode, nowMs: number, isLive: boolean): number {
  const serverElapsed =
    typeof node.metadata.goal_elapsed_ms === "number" ? node.metadata.goal_elapsed_ms : 0;
  if (!isLive) return serverElapsed;
  const startedAtMs = parseGoalStartedAtMs(node.metadata.goal_started_at);
  if (startedAtMs === null) return serverElapsed;
  return Math.max(serverElapsed, nowMs - startedAtMs);
}

function parseGoalStartedAtMs(value: string | null | undefined): number | null {
  if (typeof value !== "string" || value.length === 0) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatGoalElapsed(elapsedMs: number): string {
  const seconds = Math.max(0, Math.round(elapsedMs / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}m ${rest}s`;
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

function formatTokenCount(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "0";
  if (value >= 1_000_000) return `${Number.parseFloat((value / 1_000_000).toFixed(1))}m`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}k`;
  return String(Math.round(value));
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
      return text("直接与智能体对话", "Chat with the agent");
    case "markdown_plan":
      return text(
        "描述目标，返回 markdown 规划",
        "Describe a goal; returns a markdown plan",
      );
    case "plan":
      return text(
        "描述目标，创建规划后执行运行",
        "Describe a goal; creates a Plan-Act Run",
      );
    case "goal":
      return text(
        "描述目标，持续规划并推进执行",
        "Describe a goal; plan and pursue execution",
      );
    default: {
      const exhaustive: never = mode;
      void exhaustive;
      return "";
    }
  }
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

function serializeLocalAgentMessages(nodes: ConversationNode[]): AgentChatStreamMessage[] {
  return nodes.map((node) => ({
    id: node.id,
    parent_id: node.parent_id,
    children_ids: node.children_ids,
    role: node.role,
    content: node.content,
    state: node.state,
    run_id: node.run_id,
    metadata: { ...node.metadata },
    tool_calls: node.tool_calls,
    artifacts: node.artifacts.map((artifact) => ({ ...artifact })),
    created_at: node.created_at,
  }));
}
