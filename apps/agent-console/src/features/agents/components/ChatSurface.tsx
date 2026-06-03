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
  PlugZap,
  RefreshCw,
  Trash2,
} from "lucide-react";

import { useI18n } from "../../../lib/i18n";
import { TermHint } from "../../../components/ui/term";
import { cn } from "../../../lib/utils";
import {
  useWorkspaceStore,
  type ConversationNode,
} from "../../../stores/workspaceStore";
import {
  compressAgentWorkspaceContext,
  type AgentAttachmentPayload,
  type ToolMetadata,
  type WorkspaceContextCompressionResponse,
} from "../../tasks/api";
import type { ChatStreamController } from "../hooks/useChatStream";
import { useOutsideClick } from "../hooks/useOutsideClick";
import { canResume as canResumeQuery } from "../lib/activePathQueries";
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
import type { InspectorSection, WorkspaceMode } from "../lib/types";
import {
  ChatComposer,
  type ComposerAttachment,
} from "./ChatComposer";
import { ChatMessageList, type ChatMessageListHandle } from "./ChatMessageList";
import type { UsageSummary } from "./InspectorDrawer";
import type { ModelOption } from "./ModelPicker";
import { PlanApprovalPanel } from "./PlanApprovalPanel";
import { ContextRing } from "./ContextRing";
import { ContextMaxTokensSlider } from "./ContextMaxTokensSlider";
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
  /** Search jump target; `seq` increments even when the same node is selected twice. */
  jumpTarget?: { nodeId: string; seq: number } | null;
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
      if (compressionInFlightRef.current !== null) return null;
      const eligible = path.filter(
        (node) =>
          (node.role === "user" || node.role === "assistant" || node.role === "system") &&
          !store.pinnedNodeIds.includes(node.id) &&
          node.content.trim().length > 0,
      );
      if (eligible.length === 0) return null;

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
        return commitCompressionResponse(branchKey, response);
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
  const handleSubmit = useCallback(async (): Promise<void> => {
    const goal = draft.trim();
    if (goal.length === 0) return;
    if (stream.isStreaming) return;

    if (workspaceMode === "plan") {
      const message = text(
        "确认创建规划后执行运行？此操作会触发可执行运行。",
        "Create a Plan-Act Run? This triggers an executable run.",
      );
      if (!window.confirm(message)) return;
    }

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
  }, [
    activeCompression,
    activePath,
    attachmentNames,
    attachmentPayloads,
    autoCompressionRatio,
    compressionBranchKey,
    compressCurrentContext,
    contextUsageRatio,
    draft,
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

  // ─── Slash command dispatcher (v3 / Req 5) ─────────────────────────────
  const handleSlashDispatch = useCallback(
    (cmd: SlashCommand, args: string): void => {
      switch (cmd.name) {
        case "plan":
          onWorkspaceModeChange("codex_plan");
          setDraft("");
          return;
        case "codex":
          onWorkspaceModeChange("codex_plan");
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
        summaryManager={
          <ContextSummaryManager
            summary={activeCompression}
            onRecompress={() => {
              void compressCurrentContext("manual");
            }}
            onClear={() => clearContextCompression(compressionBranchKey)}
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
          <div className="relative">
            <BottomToolsPopover
              open={bottomPanel !== null}
              onClose={() => setBottomPanel(null)}
              align={bottomPanel === "model" ? "right" : "left"}
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
                  contextMaxTokens={contextMaxTokens}
                  onContextMaxTokensChange={setContextMaxTokens}
                  autoCompressionRatio={autoCompressionRatio}
                  onAutoCompressionRatioChange={setAutoCompressionRatio}
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

function ContextSummaryManager({
  summary,
  onRecompress,
  onClear,
  text,
}: {
  summary: ContextCompressionSummary | null;
  onRecompress: () => void;
  onClear: () => void;
  text: (zh: string, en: string) => string;
}): JSX.Element | null {
  if (summary === null) return null;
  const isPending = summary.status === "pending";
  const label =
    summary.status === "error"
      ? text("摘要失败", "Summary failed")
      : isPending
        ? text("摘要中", "Summarizing")
        : text(
            `${summary.coverageNodeIds.length} 条已摘要`,
            `${summary.coverageNodeIds.length} summarized`,
          );
  const preview = summary.error || summary.summary || text("正在生成摘要", "Creating summary");
  return (
    <div
      className="group relative inline-flex h-8 items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-700"
      aria-label={text("上下文摘要", "Context summary")}
    >
      <span className="max-w-[8rem] truncate">{label}</span>
      <button
        type="button"
        onClick={onRecompress}
        disabled={isPending}
        aria-label={text("重新压缩上下文", "Recompress context")}
        title={text("重新压缩上下文", "Recompress context")}
        className="inline-flex h-5 w-5 items-center justify-center rounded text-slate-500 hover:bg-slate-100 disabled:opacity-50"
      >
        <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />
      </button>
      <button
        type="button"
        onClick={onClear}
        disabled={isPending}
        aria-label={text("清除上下文摘要", "Clear context summary")}
        title={text("清除上下文摘要", "Clear context summary")}
        className="inline-flex h-5 w-5 items-center justify-center rounded text-slate-500 hover:bg-slate-100 disabled:opacity-50"
      >
        <Trash2 aria-hidden="true" className="h-3.5 w-3.5" />
      </button>
      <div className="pointer-events-none absolute right-0 top-full z-40 mt-1.5 hidden w-64 rounded-md border border-slate-200 bg-white p-2 text-left text-[11px] leading-4 text-slate-600 shadow-lg group-hover:block group-focus-within:block">
        <div className="mb-1 font-medium text-slate-900">
          {text("上下文摘要", "Context summary")}
        </div>
        <div className="line-clamp-5 whitespace-pre-wrap">{preview}</div>
        <div className="mt-1 font-mono text-[10px] text-slate-500">
          {formatTokenCount(summary.estimatedOriginalTokens)} →{" "}
          {formatTokenCount(summary.estimatedSummaryTokens)}
        </div>
      </div>
    </div>
  );
}

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
      className={[
        "absolute bottom-[58px] z-30 w-[min(220px,calc(100vw-2rem))] rounded-lg border border-slate-200 bg-white p-1.5 shadow-lg",
        align === "right" ? "right-4" : "left-4",
      ].join(" ")}
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
  contextMaxTokens,
  onContextMaxTokensChange,
  autoCompressionRatio,
  onAutoCompressionRatioChange,
}: ToolsPanelProps): JSX.Element {
  const [pluginsOpen, setPluginsOpen] = useState(false);
  const mcpTools = tools.filter(isMcpTool);

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
        checked={workspaceMode === "codex_plan"}
        onChange={(checked) => onWorkspaceModeChange(checked ? "codex_plan" : "chat")}
      />
      <ToolActionRow
        icon={<PlugZap aria-hidden="true" className="h-3.5 w-3.5" />}
        ariaLabel={text("插件 / MCP（模型上下文协议）", "Plugins / MCP")}
        label={
          <>
            {text("插件 / ", "Plugins / ")}
            <TermHint description="模型上下文协议，用于接入外部工具">MCP</TermHint>
          </>
        }
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
              {text("暂无外部协议功能。", "No MCP capabilities")}
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
              "flex items-start gap-3 rounded-xl px-3 py-2.5 text-left text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400",
              selected || active
                ? "bg-slate-900 font-medium text-white"
                : "text-slate-700 hover:bg-slate-50",
            ].join(" ")}
          >
            <span
              className={cn(
                "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
                selected || active ? "bg-white/10 text-white" : "bg-slate-100 text-slate-600",
              )}
            >
              <Brain className="h-4 w-4" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-semibold">{option.modelLabel}</span>
              <span className={cn("block truncate text-[11px] leading-4", selected || active ? "text-slate-300" : "text-slate-500")}>
                {option.providerLabel}
              </span>
            </span>
            <span
              className={cn(
                "shrink-0 rounded-full px-2 py-0.5 text-[11px]",
                selected || active ? "bg-white/10 text-white" : "bg-slate-100 text-slate-500",
              )}
            >
              {selected ? text("当前", "Current") : option.providerLabel}
            </span>
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
      className="flex min-h-7 items-center gap-2 rounded-md px-1.5 text-left transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
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
    case "codex_plan":
      return text(
        "描述目标，返回 markdown 规划",
        "Describe a goal; returns a markdown plan",
      );
    case "plan":
      return text(
        "描述目标，创建规划后执行运行",
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
