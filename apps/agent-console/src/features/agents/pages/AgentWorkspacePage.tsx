/**
 * AgentWorkspacePage — thin route host for `/agents/:agentId/workspace` (v3).
 *
 * v3 responsibilities (on top of v2):
 *   - Own the `<ConversationHistoryPanel>` left rail (Req 4).
 *   - Drive conversation snapshot hydration:
 *       1. Prefer v3 `harness.workspace.v3.<agentId>.conversations`.
 *       2. Fall back to v2 `harness.workspace.v2.<agentId>` via
 *          `legacyMigration` (then clear the v2 key).
 *       3. Fall back to a single `genesisConversation`.
 *   - Wire slash-command targets: `onOpenSearch`, `onOpenShortcut`,
 *     `onRequestModelPicker` (via a monotonic seq counter).
 *   - Keep v2 shortcut handling (Cmd+K / ? / Escape) untouched.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { useConfirmDialog } from "../../../components/ui/confirm-dialog";
import { notifyFeedback } from "../../../components/ui/feedback-toast";
import { useI18n } from "../../../lib/i18n";
import { createReconnectingSseClient, type SseClient } from "../../../lib/sse-client";
import { cn } from "../../../lib/utils";
import {
  useWorkspaceStore,
  type ConversationArtifact,
  type ConversationNode,
} from "../../../stores/workspaceStore";
import {
  bindLocalAgentConversation,
  createTeam,
  getAgent,
  getAgentRunWorkspace,
  getModelSettings,
  getToolRegistry,
  listAgentsPage,
  listLocalAgentBindingTasks,
  listAgentSessionMessages,
  listLocalAgentConnections,
  listLocalAgentConversationBindings,
  listTeams,
  sendLocalAgentMessage,
  taskEventReconnectStreamUrl,
  type AgentEvent,
  type AgentChatStreamMessage,
  type AgentMessage,
  type LocalAgentSendMessagePayload,
  type LocalAgentBindingTask,
  type LocalAgentConnection,
  type LocalAgentConversationBinding,
  type LocalAgentConversationBindingPage,
  type ModelSettings,
  type ToolCall,
} from "../../tasks/api";
import { ChatSurface, type LocalAgentSubmitContext } from "../components/ChatSurface";
import { ConversationHistoryPanel } from "../components/ConversationHistoryPanel";
import { InspectorDrawer } from "../components/InspectorDrawer";
import type { ModelOption } from "../components/ModelPicker";
import { SearchOverlay } from "../components/SearchOverlay";
import { ShortcutOverlay } from "../components/ShortcutOverlay";
import { useChatStream } from "../hooks/useChatStream";
import {
  downloadBlob,
  exportJson,
  exportMarkdown,
} from "../lib/exporter";
import { readAutoCompressionRatio, readContextMaxTokens } from "../lib/contextTokens";
import {
  generateConversationId,
  genesisConversationLocalized,
  legacyMigration,
  readConversationsSnapshot,
  readHistoryPanelCollapsed,
  saveConversationsSnapshot,
  CONVERSATIONS_SCHEMA_VERSION,
  type ConversationSummary,
} from "../lib/conversationHistory";
import { clearSnapshot, loadSnapshot } from "../lib/localPersistence";
import type { InspectorSection, WorkspaceMode } from "../lib/types";
import { nextAvailableTeamName } from "../../teams/pages/TeamCreateModal";
import {
  buildActivePath,
  buildTeamSeedMessagesFromPath,
  deriveModelLabel,
  isNodeVisibleInPath,
  summarizeUsage,
} from "./agentWorkspaceDerive";

export function AgentWorkspacePage() {
  const { text } = useI18n();
  const { confirm, confirmDialog } = useConfirmDialog();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { agentId = "default" } = useParams();

  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>("chat");
  const [inspectorSection, setInspectorSection] = useState<InspectorSection | null>(null);
  const activeRunId = useWorkspaceStore((s) => s.activeRunId);
  const setActiveRunId = useWorkspaceStore((s) => s.setActiveRunId);
  const updateNode = useWorkspaceStore((s) => s.updateNode);
  const [searchOpen, setSearchOpen] = useState(false);
  const [shortcutOpen, setShortcutOpen] = useState(false);
  const [selectedProviderId, setSelectedProviderId] = useState<string | null>(null);
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
  const [modelPickerOpenSeq, setModelPickerOpenSeq] = useState(0);
  const [historyOverlayOpen, setHistoryOverlayOpen] = useState(false);
  const [historyNarrow, setHistoryNarrow] = useState(false);
  const [jumpTarget, setJumpTarget] = useState<{ nodeId: string; seq: number } | null>(null);
  const [localAgentEnabled, setLocalAgentEnabled] = useState(false);
  const [selectedLocalConnectionId, setSelectedLocalConnectionId] = useState<string | null>(null);
  const [activeLocalBinding, setActiveLocalBinding] =
    useState<LocalAgentConversationBinding | null>(null);
  const [localPendingAssistantNodeId, setLocalPendingAssistantNodeId] = useState<string | null>(null);
  const localPendingAssistantNodeIdRef = useRef<string | null>(null);
  const localPendingDraftRef = useRef<{
    userNode: ConversationNode;
    assistantNode: ConversationNode;
  } | null>(null);
  const localBindingCreateForRef = useRef<string | null>(null);
  const localTargetRequestSeqRef = useRef(0);
  const localBindingFocusConnectionRef = useRef<string | null>(null);
  const selectedLocalConnectionIdRef = useRef<string | null>(null);
  const localAgentEnabledRef = useRef(localAgentEnabled);
  const focusLocalConversationOnceRef = useRef(false);
  const localAgentStreamRef = useRef<SseClient | null>(null);
  const localAgentStreamTokenRef = useRef<string | null>(null);
  const localModelSyncConnectionRef = useRef<string | null>(null);
  const userSelectedModelRef = useRef(false);
  const setLocalPendingAssistant = useCallback((nodeId: string | null) => {
    localPendingAssistantNodeIdRef.current = nodeId;
    if (nodeId === null) {
      localPendingDraftRef.current = null;
    }
    setLocalPendingAssistantNodeId(nodeId);
  }, []);

  const agent = useQuery({ queryKey: ["agents", agentId], queryFn: () => getAgent(agentId) });
  const agentsQuery = useQuery({
    queryKey: ["agents", "page"],
    queryFn: () => listAgentsPage({ limit: 100 }),
  });
  const settings = useQuery({ queryKey: ["settings", "models"], queryFn: getModelSettings });
  const toolsQuery = useQuery({
    queryKey: ["tools", "registry", agentId],
    queryFn: () => getToolRegistry(agentId),
  });
  const teamsQuery = useQuery({ queryKey: ["teams"], queryFn: listTeams });
  const localConnectionsQuery = useQuery({
    queryKey: ["local-agent-connections"],
    queryFn: listLocalAgentConnections,
    refetchInterval: 3000,
  });
  const localConnections = useMemo(
    () =>
      sortLocalAgentConnections(
        (localConnectionsQuery.data?.items ?? []).filter(
          (connection) =>
            connection.agent_id === agentId && isUsableLocalAgentConnection(connection),
        ),
      ),
    [agentId, localConnectionsQuery.data],
  );
  const selectedLocalConnection = useMemo(
    () => {
      if (selectedLocalConnectionId !== null) {
        return (
          localConnections.find((connection) => connection.id === selectedLocalConnectionId) ??
          null
        );
      }
      return defaultLocalAgentConnection(localConnections);
    },
    [localConnections, selectedLocalConnectionId],
  );
  const selectedLocalAgentModel = useMemo(
    () => localAgentModelFromConnection(selectedLocalConnection),
    [selectedLocalConnection],
  );
  selectedLocalConnectionIdRef.current =
    selectedLocalConnectionId ?? selectedLocalConnection?.id ?? null;
  localAgentEnabledRef.current = localAgentEnabled;

  const localBindingsQuery = useQuery({
    queryKey: ["local-agent-bindings", selectedLocalConnection?.id],
    queryFn: () => listLocalAgentConversationBindings(selectedLocalConnection?.id ?? ""),
    enabled: localAgentEnabled && selectedLocalConnection !== null,
  });
  const localMessagesQuery = useQuery({
    queryKey: ["agent-session-messages", activeLocalBinding?.agent_session_id],
    queryFn: () => listAgentSessionMessages(activeLocalBinding?.agent_session_id ?? ""),
    enabled: localAgentEnabled && activeLocalBinding !== null,
    refetchInterval: localAgentEnabled && activeLocalBinding !== null ? 2000 : false,
  });
  const localBindingTasksQuery = useQuery({
    queryKey: ["local-agent-binding-tasks", activeLocalBinding?.id],
    queryFn: () => listLocalAgentBindingTasks(activeLocalBinding?.id ?? ""),
    enabled: localAgentEnabled && activeLocalBinding !== null,
    refetchInterval: localAgentEnabled && activeLocalBinding !== null ? 2000 : false,
  });
  const localBindingMutation = useMutation({
    mutationFn: (connectionId: string) =>
      bindLocalAgentConversation(connectionId, {
        title: `${agent.data?.name ?? agentId} 本地 Agent 会话`,
      }),
    onSuccess: async (binding) => {
      if (
        localAgentEnabledRef.current &&
        selectedLocalConnectionIdRef.current === binding.connection_id
      ) {
        setActiveLocalBinding(binding);
      }
      await queryClient.invalidateQueries({
        queryKey: ["local-agent-bindings", binding.connection_id],
      });
    },
  });
  const localSendMutation = useMutation({
    mutationFn: ({
      bindingId,
      content,
      clientMessageId,
      context,
    }: {
      bindingId: string;
      content: string;
      clientMessageId: string;
      context: LocalAgentSubmitContext;
    }) => {
      const payload: LocalAgentSendMessagePayload = {
        content,
        client_message_id: clientMessageId,
        workspace_context_provided: true,
        workspace_mode: context.mode,
        model_provider: context.model_provider,
        model_name: context.model_name,
        messages: context.messages,
        active_leaf_id: context.active_leaf_id,
        active_branch_id: context.active_branch_id,
        pinned_node_ids: context.pinned_node_ids,
        context_window_turns: context.context_window_turns,
        tool_mentions: context.tool_mentions,
        attachment_names: context.attachment_names,
        attachments: context.attachments,
        context_max_tokens: context.context_max_tokens,
        compressed_context: context.compressed_context,
      };
      return sendLocalAgentMessage(bindingId, payload);
    },
  });

  const workspace = useQuery({
    queryKey: ["agent-run-workspace", activeRunId],
    queryFn: () => getAgentRunWorkspace(activeRunId as string),
    enabled: Boolean(activeRunId),
    refetchInterval: activeRunId ? 3000 : false,
  });

  const defaultModelLabel = useMemo(
    () => deriveModelLabel(agent.data, settings.data),
    [agent.data, settings.data],
  );
  const providers = useMemo<ModelOption[]>(
    () => deriveModelOptions(settings.data),
    [settings.data],
  );
  const selectedModelLabel = useMemo(
    () => {
      if (selectedProviderId === null || selectedModelId === null) {
        return defaultModelLabel;
      }
      const selected = providers.find(
        (option) =>
          option.providerId === selectedProviderId &&
          option.modelId === selectedModelId,
      );
      return selected?.modelLabel ?? selectedModelId;
    },
    [defaultModelLabel, providers, selectedModelId, selectedProviderId],
  );
  const modelLabelIsFallback = settings.isError || settings.data === undefined;

  useEffect(() => {
    if (!localAgentEnabled || selectedLocalAgentModel === null) {
      localModelSyncConnectionRef.current = null;
      userSelectedModelRef.current = false;
      return;
    }
    const connectionId = selectedLocalConnection?.id ?? null;
    if (localModelSyncConnectionRef.current !== connectionId) {
      localModelSyncConnectionRef.current = connectionId;
      userSelectedModelRef.current = false;
    }
    if (userSelectedModelRef.current) return;
    if (
      selectedProviderId !== selectedLocalAgentModel.providerId ||
      selectedModelId !== selectedLocalAgentModel.modelId
    ) {
      setSelectedProviderId(selectedLocalAgentModel.providerId);
      setSelectedModelId(selectedLocalAgentModel.modelId);
    }
  }, [
    localAgentEnabled,
    selectedLocalAgentModel,
    selectedLocalConnection?.id,
    selectedModelId,
    selectedProviderId,
  ]);
  const workspaceAgents = useMemo(() => {
    const items = agentsQuery.data?.items ?? [];
    if (agent.data === undefined || items.some((item) => item.id === agent.data.id)) {
      return items;
    }
    return [agent.data, ...items];
  }, [agent.data, agentsQuery.data?.items]);
  const conversationGroupLabel = useCallback(
    (conversation: ConversationSummary): string => {
      const localConnectionId = localAgentConnectionIdFromConversation(conversation);
      if (localConnectionId !== null) {
        const connection = localConnections.find((item) => item.id === localConnectionId);
        return connection?.display_name ?? connection?.adapter_kind ?? "本地 Agent";
      }
      return agent.data?.name ?? agentId;
    },
    [agent.data?.name, agentId, localConnections],
  );

  const tools = useMemo(() => toolsQuery.data?.items ?? [], [toolsQuery.data]);
  const stream = useChatStream({
    agentId,
    workspaceMode,
    selectedProviderId,
    selectedModelId,
    tools,
    onRunCreated: setActiveRunId,
  });

  const nodesById = useWorkspaceStore((s) => s.nodesById);
  const rootNodeId = useWorkspaceStore((s) => s.rootNodeId);
  const activeLeafId = useWorkspaceStore((s) => s.activeLeafId);
  const activePath = useMemo(
    () => buildActivePath(nodesById, activeLeafId, rootNodeId),
    [nodesById, activeLeafId, rootNodeId],
  );
  const localAgentTaskBlocking =
    localBindingMutation.isPending ||
    localSendMutation.isPending ||
    (localAgentEnabled &&
      (selectedLocalConnection === null ||
        activeLocalBinding === null ||
        activeLocalBinding.connection_id !== selectedLocalConnection.id ||
        localMessagesQuery.data === undefined)) ||
    (localBindingTasksQuery.data?.items.some(isLocalAgentTaskActive) ?? false);
  const createTeamFromConversation = useMutation({
    mutationFn: async () => {
      const teams =
        teamsQuery.data?.items ??
        (await queryClient.fetchQuery({ queryKey: ["teams"], queryFn: listTeams })).items;
      return createTeam({
        name: nextAvailableTeamName(teams, `${agent.data?.name ?? agentId} 团队`),
        leader_agent_id: agentId,
        leader_name: agent.data?.name ?? "队长",
        workspace_mode: "shared",
        seed_messages: buildTeamSeedMessagesFromPath(activePath, agentId),
      });
    },
    onSuccess: async (team) => {
      notifyFeedback({
        tone: "success",
        title: text("团队已创建", "Team created"),
        description: text(
          `已根据当前会话创建“${team.name}”，正在进入团队模式。`,
          `${team.name} was created from the current conversation. Opening Team Mode now.`,
        ),
      });
      await queryClient.invalidateQueries({ queryKey: ["teams"] });
      navigate(`/teams/${team.id}`);
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("团队创建失败", "Team creation failed"),
        description:
          error instanceof Error && error.message.trim()
            ? error.message
            : text("请检查当前会话状态或稍后重试。", "Check the current conversation state and retry."),
      });
    },
  });

  // v3 conversation store wiring
  const conversations = useWorkspaceStore((s) => s.conversations);
  const currentConversationId = useWorkspaceStore((s) => s.currentConversationId);
  const historyPanelCollapsed = useWorkspaceStore((s) => s.historyPanelCollapsed);
  const newConversation = useWorkspaceStore((s) => s.newConversation);
  const setCurrentConversation = useWorkspaceStore((s) => s.setCurrentConversation);
  const deleteConversation = useWorkspaceStore((s) => s.deleteConversation);
  const setHistoryPanelCollapsed = useWorkspaceStore((s) => s.setHistoryPanelCollapsed);
  const hydrateFromConversations = useWorkspaceStore((s) => s.hydrateFromConversations);
  const upsertConversationSummary = useWorkspaceStore((s) => s.upsertConversationSummary);

  const inspectorArtifacts = useMemo<ConversationArtifact[]>(
    () => activePath.flatMap((node) => node.artifacts).slice(-10),
    [activePath],
  );
  const inspectorUsage = useMemo(
    () => summarizeUsage(activePath, workspace.data),
    [activePath, workspace.data],
  );
  const pendingApprovalCount =
    workspace.data?.approvals.filter((approval) => approval.status === "PENDING").length ?? 0;

  useEffect(() => {
    if (!localAgentEnabled || activeLocalBinding === null || selectedLocalConnection === null) {
      return;
    }
    if (activeLocalBinding.connection_id !== selectedLocalConnection.id) {
      return;
    }
    const shouldFocus = focusLocalConversationOnceRef.current;
    ensureLocalAgentConversation({
      binding: activeLocalBinding,
      connection: selectedLocalConnection,
      fallbackTitle: `${agent.data?.name ?? agentId} 本地 Agent`,
      pendingApprovalCount,
      focus: shouldFocus,
    });
    if (shouldFocus) {
      focusLocalConversationOnceRef.current = false;
      localBindingFocusConnectionRef.current = null;
    }
  }, [
    activeLocalBinding,
    agent.data?.name,
    agentId,
    localAgentEnabled,
    pendingApprovalCount,
    selectedLocalConnection,
  ]);

  useEffect(() => {
    if (selectedLocalConnectionId !== null) {
      return;
    }
    setSelectedLocalConnectionId(defaultLocalAgentConnection(localConnections)?.id ?? null);
  }, [localConnections, selectedLocalConnectionId]);

  useEffect(() => {
    setActiveLocalBinding(null);
    setLocalPendingAssistant(null);
    localBindingCreateForRef.current = null;
    localAgentStreamTokenRef.current = null;
    localAgentStreamRef.current?.close();
    localAgentStreamRef.current = null;
  }, [agentId, selectedLocalConnectionId, setLocalPendingAssistant]);

  useEffect(
    () => () => {
      localAgentStreamTokenRef.current = null;
      localAgentStreamRef.current?.close();
      localAgentStreamRef.current = null;
    },
    [],
  );

  useEffect(() => {
    if (!localAgentEnabled || selectedLocalConnection === null) return;
    const bindings = localBindingsQuery.data?.items;
    if (bindings === undefined) return;
    const state = useWorkspaceStore.getState();
    const currentConversation = state.conversations.find(
      (conversation) => conversation.id === state.currentConversationId,
    );
    const currentLocalBinding = localAgentBindingHintFromConversation(currentConversation);
    const bindingRequestedForFocus =
      localBindingFocusConnectionRef.current === selectedLocalConnection.id;
    const activeBinding =
      currentLocalBinding?.connectionId === selectedLocalConnection.id
        ? bindings.find((binding) => localAgentBindingMatchesHint(binding, currentLocalBinding)) ??
          (activeLocalBinding !== null &&
          localAgentBindingMatchesHint(activeLocalBinding, currentLocalBinding)
            ? activeLocalBinding
            : localAgentBindingFromHint(currentLocalBinding, agentId))
        : (bindingRequestedForFocus
            ? mostRecentActiveBindingForConnection(bindings, selectedLocalConnection.id)
            : undefined) ??
          bindings.find((binding) => binding.status === "active") ??
          bindings[0];
    if (activeBinding !== undefined) {
      if (activeBinding.connection_id !== selectedLocalConnection.id) return;
      if (activeLocalBinding?.id !== activeBinding.id) {
        setActiveLocalBinding(activeBinding);
      }
      return;
    }
    if (
      localBindingCreateForRef.current === selectedLocalConnection.id ||
      localBindingMutation.isPending
    ) {
      return;
    }
    localBindingCreateForRef.current = selectedLocalConnection.id;
    localBindingMutation.mutate(selectedLocalConnection.id);
  }, [
    activeLocalBinding?.id,
    currentConversationId,
    localAgentEnabled,
    localBindingMutation,
    localBindingsQuery.data?.items,
    selectedLocalConnection,
  ]);

  useEffect(() => {
    if (!localAgentEnabled || activeLocalBinding === null || localMessagesQuery.data === undefined) {
      return;
    }
    if (
      selectedLocalConnection === null ||
      activeLocalBinding.connection_id !== selectedLocalConnection.id
    ) {
      return;
    }
    const state = useWorkspaceStore.getState();
    const pendingDraft = localPendingDraftRef.current;
    const pendingNode =
      localPendingAssistantNodeIdRef.current !== null
        ? state.nodesById[localPendingAssistantNodeIdRef.current] ??
          (pendingDraft?.assistantNode.id === localPendingAssistantNodeIdRef.current
            ? pendingDraft.assistantNode
            : undefined)
        : undefined;
    const pendingUserNode =
      pendingNode?.parent_id !== null && pendingNode?.parent_id !== undefined
        ? state.nodesById[pendingNode.parent_id] ??
          (pendingDraft?.userNode.id === pendingNode.parent_id ? pendingDraft.userNode : undefined)
        : undefined;
    const summary = localAgentConversationFromMessages({
      binding: activeLocalBinding,
      messages: localMessagesQuery.data.items.filter(
        (message) => message.session_id === activeLocalBinding.agent_session_id,
      ),
      pendingTasks: (localBindingTasksQuery.data?.items ?? []).filter(
        (task) => task.binding_id === activeLocalBinding.id,
      ),
      connection: selectedLocalConnection,
      fallbackTitle: `${agent.data?.name ?? agentId} 本地 Agent`,
      pendingApprovalCount,
      pendingNode: localAgentNodeMatchesBinding(pendingNode, activeLocalBinding)
        ? pendingNode
        : undefined,
      pendingUserNode: localAgentNodeMatchesBinding(pendingUserNode, activeLocalBinding)
        ? pendingUserNode
        : undefined,
    });
    const summaryWithDraft = {
      ...summary,
      draft: state.draft,
    };
    const shouldFocusLocalConversation = focusLocalConversationOnceRef.current;
    focusLocalConversationOnceRef.current = false;
    if (shouldFocusLocalConversation) {
      localBindingFocusConnectionRef.current = null;
    }
    const shouldHydrateLocalConversation =
      shouldFocusLocalConversation ||
      state.currentConversationId === summaryWithDraft.id;
    if (shouldHydrateLocalConversation) {
      const conversationsWithoutLocal = state.conversations.filter(
        (conversation) =>
          conversation.id !== summaryWithDraft.id &&
          !isPendingLocalAgentConversationForConnection(
            conversation,
            activeLocalBinding.connection_id,
          ),
      );
      hydrateFromConversations({
        conversations: [...conversationsWithoutLocal, summaryWithDraft],
        currentConversationId: summaryWithDraft.id,
        historyPanelCollapsed,
      });
    } else {
      upsertConversationSummary(summaryWithDraft);
    }
      if (pendingNode !== undefined) {
        const nextPendingNode = summaryWithDraft.nodesById[pendingNode.id];
        if (
          nextPendingNode === undefined ||
          nextPendingNode.state === "done"
        ) {
          setLocalPendingAssistant(null);
        }
    }
  }, [
    activeLocalBinding,
    agent.data?.name,
    agentId,
    historyPanelCollapsed,
    hydrateFromConversations,
    localBindingTasksQuery.data?.items,
    localAgentEnabled,
    localMessagesQuery.data,
    localPendingAssistantNodeId,
    pendingApprovalCount,
    selectedLocalConnection,
    setLocalPendingAssistant,
    upsertConversationSummary,
  ]);

  useEffect(() => {
    if (!workspace.data?.tool_calls.length) return;
    const callsById = new Map(workspace.data.tool_calls.map((call) => [call.id, call]));
    for (const node of Object.values(nodesById)) {
      const nextToolCalls = syncNodeToolCallsFromWorkspace(node, callsById);
      if (nextToolCalls !== node.tool_calls) {
        updateNode(node.id, { tool_calls: nextToolCalls });
      }
    }
  }, [nodesById, updateNode, workspace.data?.tool_calls]);

  // ─── Agent scope + rehydration (v3 Req 4.10, Legacy migration) ─────────
  useEffect(() => {
    useWorkspaceStore.getState().setAgentScope(agentId);
    const now = new Date().toISOString();
    const locale = "zh-CN";
    const collapsed = readHistoryPanelCollapsed(agentId);

    const applyContextMaxTokens = (): void => {
      const saved = readContextMaxTokens(agentId);
      if (saved !== null) {
        useWorkspaceStore.getState().setContextMaxTokens(saved);
      }
      const savedRatio = readAutoCompressionRatio(agentId);
      if (savedRatio !== null) {
        useWorkspaceStore.getState().setAutoCompressionRatio(savedRatio);
      }
    };

    // v5: Skip hydration when the in-memory store already has content that
    // is newer than what localStorage holds. This happens when the user
    // navigates away mid-stream and comes back — the SSE stream continues
    // writing to the global zustand store in the background, but the
    // debounced localStorage save may not have fired yet. Hydrating from
    // the stale localStorage snapshot would overwrite the stream's output.
    const currentState = useWorkspaceStore.getState();
    const hasStreamingNode = Object.values(currentState.nodesById).some(
      (node) => node.state === "streaming",
    );
    // Check if any assistant node has content that would be lost by hydration
    const storeAssistantContent = Object.values(currentState.nodesById)
      .filter((node) => node.role === "assistant")
      .reduce((total, node) => total + node.content.length, 0);
    const v3Snapshot = readConversationsSnapshot(agentId);
    const snapshotConv = v3Snapshot
      ? (v3Snapshot.conversations.find((c) => c.id === v3Snapshot.currentConversationId) ??
          v3Snapshot.conversations[0])
      : null;
    const snapshotAssistantContent = snapshotConv
      ? Object.values(snapshotConv.nodesById)
          .filter((node: any) => node.role === "assistant")
          .reduce((total: number, node: any) => total + (node.content?.length ?? 0), 0)
      : 0;
    if (
      currentState.activeStream !== null ||
      hasStreamingNode ||
      storeAssistantContent > snapshotAssistantContent
    ) {
      applyContextMaxTokens();
      return () => {
        useWorkspaceStore.getState().setAgentScope(null);
      };
    }

    const v3 = v3Snapshot;
    if (v3 !== null) {
      hydrateFromConversations({
        conversations: v3.conversations,
        currentConversationId: v3.currentConversationId,
        historyPanelCollapsed: collapsed ?? false,
      });
      applyContextMaxTokens();
      return () => {
        useWorkspaceStore.getState().setAgentScope(null);
      };
    }

    const v2 = loadSnapshot(agentId);
    if (v2 !== null) {
      const migrated = legacyMigration(v2, now, generateConversationId);
      hydrateFromConversations({
        conversations: [migrated],
        currentConversationId: migrated.id,
        historyPanelCollapsed: collapsed ?? false,
      });
      saveConversationsSnapshot(agentId, {
        version: CONVERSATIONS_SCHEMA_VERSION,
        conversations: [migrated],
        currentConversationId: migrated.id,
      });
      clearSnapshot(agentId);
      applyContextMaxTokens();
      return () => {
        useWorkspaceStore.getState().setAgentScope(null);
      };
    }

    const genesis = genesisConversationLocalized(now, locale, generateConversationId);
    hydrateFromConversations({
      conversations: [genesis],
      currentConversationId: genesis.id,
      historyPanelCollapsed: collapsed ?? false,
    });
    applyContextMaxTokens();
    return () => {
      useWorkspaceStore.getState().setAgentScope(null);
    };
    // Locale is fixed Chinese; changing old locale state must not rehydrate.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId, hydrateFromConversations]);

  // ─── Seed the session model override from settings defaults ────────────
  useEffect(() => {
    if (settings.data === undefined) return;
    setSelectedProviderId((prev) => prev ?? settings.data.default_provider);
    setSelectedModelId((prev) => prev ?? settings.data.default_model);
  }, [settings.data]);

  // ─── Global keyboard shortcuts ─────────────────────────────────────────
  useEffect(() => {
    const handleKey = (event: KeyboardEvent): void => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen(true);
        return;
      }
      if (event.key === "?") {
        const target = event.target as HTMLElement | null;
        const tag = target?.tagName?.toLowerCase();
        const isEditable =
          tag === "input" ||
          tag === "textarea" ||
          target?.isContentEditable === true;
        if (isEditable) return;
        event.preventDefault();
        setShortcutOpen(true);
        return;
      }
      if (event.key === "Escape") {
        setSearchOpen(false);
        setShortcutOpen(false);
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(max-width: 767px)");
    const apply = (): void => {
      setHistoryNarrow(query.matches);
      if (!query.matches) setHistoryOverlayOpen(false);
    };
    apply();
    query.addEventListener("change", apply);
    return () => query.removeEventListener("change", apply);
  }, []);

  // ─── Export / Clear callbacks ──────────────────────────────────────────
  const handleExport = useCallback((format: "markdown" | "json") => {
    const path = useWorkspaceStore.getState().activePath();
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
    if (format === "markdown") {
      downloadBlob(exportMarkdown(path), `conversation-${timestamp}.md`, "text/markdown");
    } else {
      downloadBlob(exportJson(path), `conversation-${timestamp}.json`, "application/json");
    }
  }, []);

  const handleClearConversation = useCallback(async () => {
    const confirmed = await confirm({
      title: "清空当前会话",
      description: "这会重置当前会话内容，但不会删除历史会话列表。此操作不可撤销。",
      confirmText: "确认清空",
      variant: "danger",
    });
    if (!confirmed) return;
    // v3: clearing only resets the current conversation's runtime fields;
    // the conversations list itself is unchanged. Persistence subscribe
    // will write the empty state back to the active conversation.
    useWorkspaceStore.getState().reset();
    notifyFeedback({
      tone: "warning",
      title: "当前会话已清空",
      description: "当前对话内容已重置，历史会话列表仍然保留。",
    });
  }, [confirm]);

  const handleModelChange = useCallback((providerId: string, modelId: string) => {
    userSelectedModelRef.current = true;
    setSelectedProviderId(providerId);
    setSelectedModelId(modelId);
  }, []);

  const handleJumpToNode = useCallback((nodeId: string) => {
    const store = useWorkspaceStore.getState();
    const visible = isNodeVisibleInPath(store.activePath(), nodeId);
    if (!visible) {
      store.setActiveLeafId(nodeId);
    }
    setJumpTarget((current) => ({
      nodeId,
      seq: (current?.seq ?? 0) + 1,
    }));
  }, []);

  // v3 slash-command targets
  const handleOpenSearch = useCallback(() => {
    setSearchOpen(true);
  }, []);

  const handleOpenShortcut = useCallback(() => {
    setShortcutOpen(true);
  }, []);

  const handleRequestModelPicker = useCallback(() => {
    setModelPickerOpenSeq((seq) => seq + 1);
  }, []);

  const handleAgentChange = useCallback(
    (nextAgentId: string): void => {
      localAgentEnabledRef.current = false;
      focusLocalConversationOnceRef.current = false;
      localBindingFocusConnectionRef.current = null;
      localAgentStreamTokenRef.current = null;
      localAgentStreamRef.current?.close();
      localAgentStreamRef.current = null;
      setLocalAgentEnabled(false);
      if (nextAgentId === agentId) {
        const store = useWorkspaceStore.getState();
        const cloudConversation = store.conversations
          .filter((conversation) => localAgentBindingHintFromConversation(conversation) === null)
          .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))[0];
        if (cloudConversation !== undefined) {
          store.setCurrentConversation(cloudConversation.id);
        } else {
          newConversation();
        }
        return;
      }
      navigate(`/agents/${nextAgentId}/workspace`);
    },
    [agentId, navigate, newConversation],
  );

  const handleLocalAgentTargetChange = useCallback((connectionId: string): void => {
    localTargetRequestSeqRef.current += 1;
    selectedLocalConnectionIdRef.current = connectionId;
    localAgentEnabledRef.current = true;
    focusLocalConversationOnceRef.current = true;
    localBindingFocusConnectionRef.current = connectionId;
    localAgentStreamTokenRef.current = null;
    localAgentStreamRef.current?.close();
    localAgentStreamRef.current = null;
    setActiveLocalBinding(null);
    setLocalPendingAssistant(null);
    setSelectedLocalConnectionId(connectionId);
    setLocalAgentEnabled(true);
    const existingConversation = mostRecentLocalAgentConversationForConnection(
      useWorkspaceStore.getState().conversations,
      connectionId,
    );
    if (existingConversation !== undefined) {
      const localBinding = localAgentBindingHintFromConversation(existingConversation);
      if (localBinding !== null) {
        const bindingFromCache = queryClient
          .getQueryData<LocalAgentConversationBindingPage>([
            "local-agent-bindings",
            localBinding.connectionId,
          ])
          ?.items.find((binding) => localAgentBindingMatchesHint(binding, localBinding));
        setActiveLocalBinding(
          bindingFromCache ?? localAgentBindingFromHint(localBinding, agentId),
        );
        localBindingFocusConnectionRef.current = null;
      }
      setCurrentConversation(existingConversation.id);
    } else {
      const connection =
        localConnections.find((item) => item.id === connectionId) ?? null;
      ensurePendingLocalAgentConversation({
        connection,
        fallbackTitle: `${connection?.display_name ?? "本地 Agent"} 正在恢复`,
        focus: true,
      });
    }
  }, [
    agentId,
    localConnections,
    queryClient,
    setCurrentConversation,
    setLocalPendingAssistant,
  ]);

  const handleLocalAgentEnabledChange = useCallback(
    (enabled: boolean): void => {
      localAgentEnabledRef.current = enabled;
      if (enabled) {
        localTargetRequestSeqRef.current += 1;
        focusLocalConversationOnceRef.current = true;
        localBindingFocusConnectionRef.current = selectedLocalConnection?.id ?? null;
      } else {
        focusLocalConversationOnceRef.current = false;
        localBindingFocusConnectionRef.current = null;
        localAgentStreamTokenRef.current = null;
        localAgentStreamRef.current?.close();
        localAgentStreamRef.current = null;
      }
      setLocalAgentEnabled(enabled);
      if (!enabled || selectedLocalConnection === null) return;
      const connectionId = selectedLocalConnection.id;
      const requestSeq = localTargetRequestSeqRef.current;
      void (async () => {
        try {
          const bindings = await queryClient.fetchQuery({
            queryKey: ["local-agent-bindings", connectionId],
            queryFn: () => listLocalAgentConversationBindings(connectionId),
          });
          if (localTargetRequestSeqRef.current !== requestSeq) return;
          const activeBinding =
            bindings.items.find((binding) => binding.status === "active") ?? bindings.items[0];
          if (activeBinding !== undefined) {
            if (
              localAgentEnabledRef.current &&
              selectedLocalConnectionIdRef.current === activeBinding.connection_id
            ) {
              setActiveLocalBinding(activeBinding);
            }
            return;
          }
          localBindingCreateForRef.current = connectionId;
          const created = await localBindingMutation.mutateAsync(connectionId);
          if (localTargetRequestSeqRef.current !== requestSeq) return;
          if (
            localAgentEnabledRef.current &&
            selectedLocalConnectionIdRef.current === created.connection_id
          ) {
            setActiveLocalBinding(created);
          }
        } catch (error) {
          notifyFeedback({
            tone: "error",
            title: "本地 Agent 会话恢复失败",
            description: error instanceof Error ? error.message : String(error),
          });
        }
      })();
    },
    [localBindingMutation, queryClient, selectedLocalConnection],
  );

  const startLocalAgentEventStream = useCallback(
    ({
      runId,
      bridgeTaskId,
      assistantNodeId,
      connection,
      binding,
    }: {
      runId: string;
      bridgeTaskId: string;
      assistantNodeId: string;
      connection: LocalAgentConnection;
      binding: LocalAgentConversationBinding;
    }): void => {
      if (typeof window === "undefined" || typeof window.EventSource !== "function") {
        return;
      }
      localAgentStreamTokenRef.current = null;
      localAgentStreamRef.current?.close();
      const streamToken = `${runId}:${bridgeTaskId}:${binding.id}:${assistantNodeId}`;
      localAgentStreamTokenRef.current = streamToken;
      let streamedContent = "";
      const closeOwnedStream = () => {
        if (localAgentStreamTokenRef.current !== streamToken) return;
        localAgentStreamTokenRef.current = null;
        localAgentStreamRef.current?.close();
        localAgentStreamRef.current = null;
      };
      const eventStillTargetsCurrentLocalConversation = (): boolean => {
        const state = useWorkspaceStore.getState();
        const node = state.nodesById[assistantNodeId];
        const orchestration = node?.metadata.orchestration;
        return (
          localAgentStreamTokenRef.current === streamToken &&
          localAgentEnabledRef.current &&
          selectedLocalConnectionIdRef.current === connection.id &&
          state.currentConversationId === localAgentConversationId(binding.id) &&
          node !== undefined &&
          node.run_id === runId &&
          orchestration?.source === "local_agent" &&
          orchestration.binding_id === binding.id &&
          orchestration.connection_id === connection.id &&
          (orchestration.agent_session_id === undefined ||
            orchestration.agent_session_id === binding.agent_session_id) &&
          orchestration.bridge_task_id === bridgeTaskId
        );
      };
      const streamClient = createReconnectingSseClient<AgentEvent>(
        (lastEventId) => taskEventReconnectStreamUrl(runId, lastEventId),
        {
          parse: (data) => JSON.parse(data) as AgentEvent,
          onMessage: (event) => {
            if (event.payload_json.bridge_task_id !== bridgeTaskId) return;
            if (event.agent_run_id !== null && event.agent_run_id !== runId) return;
            if (!eventStillTargetsCurrentLocalConversation()) return;
            if (
              event.event_type === "TOOL_APPROVAL_REQUESTED" ||
              event.event_type === "LOCAL_AGENT_TOOL_REQUESTED"
            ) {
              const toolName =
                typeof event.payload_json.tool_name === "string"
                  ? event.payload_json.tool_name
                  : "本地工具";
              const approvalId =
                typeof event.payload_json.approval_id === "string"
                  ? event.payload_json.approval_id
                  : null;
              const state = useWorkspaceStore.getState();
              const node = state.nodesById[assistantNodeId];
              if (node === undefined || node.state === "done" || node.state === "error") return;
              state.updateNode(assistantNodeId, {
                content: localAgentToolApprovalContent(connection, toolName, approvalId),
                state: "streaming",
                metadata: {
                  ...node.metadata,
                  orchestration: {
                    ...node.metadata.orchestration,
                    status: "waiting_approval",
                    streaming_via: "task_event_sse",
                    tool_name: toolName,
                    approval_id: approvalId,
                  },
                },
                tool_calls: [
                  ...node.tool_calls,
                  {
                    tool_name: toolName,
                    status: "PENDING_APPROVAL",
                    approval_id: approvalId,
                  },
                ],
              });
              void queryClient.invalidateQueries({ queryKey: ["agent-run-workspace", runId] });
              return;
            }
            if (event.event_type === "LOCAL_AGENT_DELTA_RECEIVED") {
              const content =
                typeof event.payload_json.content === "string"
                  ? event.payload_json.content
                  : "";
              if (!content) return;
              streamedContent += content;
              const state = useWorkspaceStore.getState();
              const node = state.nodesById[assistantNodeId];
              if (node === undefined || node.state === "done" || node.state === "error") return;
              state.updateNode(assistantNodeId, {
                content: streamedContent,
                state: "streaming",
                metadata: {
                  ...node.metadata,
                  output_tokens: Math.max(1, Math.ceil(streamedContent.length / 4)),
                  orchestration: {
                    ...node.metadata.orchestration,
                    status: "streaming",
                    streaming_via: "task_event_sse",
                  },
                },
              });
              return;
            }
            if (event.event_type === "LOCAL_AGENT_MESSAGE_COMPLETED") {
              const state = useWorkspaceStore.getState();
              const node = state.nodesById[assistantNodeId];
              const hasStreamedContent = streamedContent.trim().length > 0;
              if (node !== undefined) {
                state.updateNode(assistantNodeId, {
                  content: hasStreamedContent ? streamedContent : node.content,
                  state: hasStreamedContent ? "done" : "streaming",
                  metadata: {
                    ...node.metadata,
                    orchestration: {
                      ...node.metadata.orchestration,
                      status: hasStreamedContent ? "completed" : "awaiting_message_hydration",
                      streaming_via: "task_event_sse",
                    },
                  },
                });
              }
              if (hasStreamedContent && localPendingAssistantNodeIdRef.current === assistantNodeId) {
                setLocalPendingAssistant(null);
              }
              closeOwnedStream();
              void queryClient.invalidateQueries({
                queryKey: ["agent-session-messages", binding.agent_session_id],
              });
              void queryClient.invalidateQueries({
                queryKey: ["local-agent-binding-tasks", binding.id],
              });
              void queryClient.invalidateQueries({ queryKey: ["agent-run-workspace", runId] });
              return;
            }
            if (event.event_type === "LOCAL_AGENT_MESSAGE_FAILED") {
              const errorMessage =
                typeof event.payload_json.error_message === "string"
                  ? event.payload_json.error_message
                  : "本地 Agent 执行失败。";
              const state = useWorkspaceStore.getState();
              const node = state.nodesById[assistantNodeId];
              if (node !== undefined) {
                state.updateNode(assistantNodeId, {
                  content: "",
                  state: "error",
                  metadata: {
                    ...node.metadata,
                    retry_disabled: true,
                    error: {
                      kind: "server",
                      detail: "本地 Agent 执行失败",
                      body_preview: errorMessage,
                      happened_at: event.created_at,
                    },
                    orchestration: {
                      ...node.metadata.orchestration,
                      status: "failed",
                      connection_id: connection.id,
                    },
                  },
                });
              }
              setLocalPendingAssistant(null);
              closeOwnedStream();
              void queryClient.invalidateQueries({
                queryKey: ["local-agent-binding-tasks", binding.id],
              });
            }
          },
          maxAttemptsBeforeNotice: 6,
        },
      );
      localAgentStreamRef.current = streamClient;
    },
    [queryClient, setLocalPendingAssistant],
  );

  const handleLocalAgentSubmit = useCallback(
    async (goal: string, context: LocalAgentSubmitContext): Promise<boolean> => {
      const selectedTargetConnectionId = selectedLocalConnectionIdRef.current;
      if (
        !localAgentEnabledRef.current ||
        selectedTargetConnectionId === null ||
        selectedLocalConnection === null ||
        selectedLocalConnection.id !== selectedTargetConnectionId
      ) {
        notifyFeedback({
          tone: "warning",
          title: "本地 Agent 会话尚未就绪",
          description: "正在切换本地连接，请稍后再发送。",
        });
        return false;
      }
      if (activeLocalBinding === null || localBindingMutation.isPending) {
        notifyFeedback({
          tone: "warning",
          title: "本地 Agent 会话尚未就绪",
          description: "正在创建或恢复本地会话，请稍后再发送。",
        });
        return false;
      }
      if (activeLocalBinding.connection_id !== selectedTargetConnectionId) {
        notifyFeedback({
          tone: "warning",
          title: "本地 Agent 会话尚未就绪",
          description: "正在切换本地连接，请稍后再发送。",
        });
        return false;
      }
      if (localMessagesQuery.data === undefined) {
        notifyFeedback({
          tone: "warning",
          title: "本地 Agent 会话尚未就绪",
          description: "正在同步本地会话消息，请稍后再发送。",
        });
        return false;
      }

      const store = useWorkspaceStore.getState();
      focusLocalConversationOnceRef.current = true;
      const localConversationId = localAgentConversationId(activeLocalBinding.id);
      const currentConversation = store.conversations.find(
        (conversation) => conversation.id === store.currentConversationId,
      );
      const currentLocalBinding = localAgentBindingHintFromConversation(currentConversation);
      if (
        currentLocalBinding !== null &&
        (currentLocalBinding.bindingId !== activeLocalBinding.id ||
          currentLocalBinding.connectionId !== selectedLocalConnection.id ||
          currentLocalBinding.agentSessionId !== activeLocalBinding.agent_session_id)
      ) {
        notifyFeedback({
          tone: "warning",
          title: "本地 Agent 会话尚未就绪",
          description: "正在切换本地会话，请稍后再发送。",
        });
        return false;
      }
      if (
        !store.conversations.some((conversation) => conversation.id === localConversationId) ||
        store.currentConversationId !== localConversationId ||
        currentLocalBinding === null
      ) {
        ensureLocalAgentConversation({
          binding: activeLocalBinding,
          connection: selectedLocalConnection,
          fallbackTitle: `${agent.data?.name ?? agentId} 本地 Agent`,
          pendingApprovalCount,
          focus: true,
        });
        notifyFeedback({
          tone: "warning",
          title: "本地 Agent 会话尚未就绪",
          description: "正在切换到目标本地会话，请稍后再发送。",
        });
        return false;
      }
      focusLocalConversationOnceRef.current = false;
      const localStore = useWorkspaceStore.getState();
      const localSubmitContext = localAgentSubmitContextForBinding(
        context,
        localStore,
        activeLocalBinding,
      );
      const clientMessageId = `local-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      const userNodeId = localStore.appendNode({
        parent_id: localStore.activeLeafId,
        role: "user",
        content: goal,
        state: "done",
        metadata: {
          workspace_mode: context.workspace_mode,
          orchestration: {
            source: "local_agent",
            connection_id: selectedLocalConnection.id,
            binding_id: activeLocalBinding.id,
            client_message_id: clientMessageId,
            model_provider: context.model_provider,
            model_name: context.model_name,
            tool_mentions: context.tool_mentions.map((tool) => tool.name),
            attachment_names: context.attachment_names,
          },
        },
        tool_calls: [],
        artifacts: [],
      });
      const assistantNodeId = useWorkspaceStore.getState().appendNode({
        parent_id: userNodeId,
        role: "assistant",
        content: localAgentPendingTaskContent(
          "pending",
          selectedLocalConnection,
          pendingApprovalCount,
        ),
        state: "streaming",
        metadata: {
          workspace_mode: context.workspace_mode,
          input_tokens: estimateLocalAgentInputTokens(goal, localSubmitContext),
          output_tokens: 0,
          model_call_id: `${selectedLocalConnection.adapter_kind}:${selectedModelLabel}`,
          duration_ms: 0,
          orchestration: {
            source: "local_agent",
            connection_id: selectedLocalConnection.id,
            binding_id: activeLocalBinding.id,
            client_message_id: clientMessageId,
            adapter_kind: selectedLocalConnection.adapter_kind,
            model_provider: context.model_provider,
            model_name: context.model_name,
            tool_mentions: context.tool_mentions.map((tool) => tool.name),
            attachment_names: context.attachment_names,
          },
        },
        tool_calls: [],
        artifacts: [],
      });
      const pendingState = useWorkspaceStore.getState();
      const pendingUserNode = pendingState.nodesById[userNodeId];
      const pendingAssistantNode = pendingState.nodesById[assistantNodeId];
      if (pendingUserNode !== undefined && pendingAssistantNode !== undefined) {
        localPendingDraftRef.current = {
          userNode: pendingUserNode,
          assistantNode: pendingAssistantNode,
        };
      }
      setLocalPendingAssistant(assistantNodeId);

      try {
        const response = await localSendMutation.mutateAsync({
          bindingId: activeLocalBinding.id,
          content: goal,
          clientMessageId,
          context: localSubmitContext,
        });
        const responseState = useWorkspaceStore.getState();
        const responseStillTargetsCurrentLocalConversation =
          localAgentEnabledRef.current &&
          selectedLocalConnectionIdRef.current === activeLocalBinding.connection_id &&
          responseState.currentConversationId === localConversationId &&
          responseState.nodesById[assistantNodeId] !== undefined;
        if (!responseStillTargetsCurrentLocalConversation) {
          await queryClient.invalidateQueries({
            queryKey: ["agent-session-messages", activeLocalBinding.agent_session_id],
          });
          await queryClient.invalidateQueries({
            queryKey: ["local-agent-binding-tasks", activeLocalBinding.id],
          });
          return false;
        }
        setActiveRunId(response.run_id);
        useWorkspaceStore.getState().updateNode(assistantNodeId, {
          run_id: response.run_id,
          metadata: {
            ...useWorkspaceStore.getState().nodesById[assistantNodeId]?.metadata,
            orchestration: {
              source: "local_agent",
              connection_id: selectedLocalConnection.id,
              binding_id: activeLocalBinding.id,
              bridge_task_id: response.bridge_task_id,
              client_message_id: clientMessageId,
              adapter_kind: selectedLocalConnection.adapter_kind,
              model_provider: context.model_provider,
              model_name: context.model_name,
              tool_mentions: context.tool_mentions.map((tool) => tool.name),
              attachment_names: context.attachment_names,
            },
          },
        });
        const updatedAssistantNode = useWorkspaceStore.getState().nodesById[assistantNodeId];
        if (updatedAssistantNode !== undefined && localPendingDraftRef.current !== null) {
          localPendingDraftRef.current = {
            ...localPendingDraftRef.current,
            assistantNode: updatedAssistantNode,
          };
        }
        startLocalAgentEventStream({
          runId: response.run_id,
          bridgeTaskId: response.bridge_task_id,
          assistantNodeId,
          connection: selectedLocalConnection,
          binding: activeLocalBinding,
        });
        await queryClient.invalidateQueries({
          queryKey: ["agent-session-messages", activeLocalBinding.agent_session_id],
        });
        await queryClient.invalidateQueries({
          queryKey: ["local-agent-binding-tasks", activeLocalBinding.id],
        });
        await queryClient.invalidateQueries({ queryKey: ["agent-run-workspace", response.run_id] });
        return true;
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        const errorState = useWorkspaceStore.getState();
        const errorStillTargetsCurrentLocalConversation =
          localAgentEnabledRef.current &&
          selectedLocalConnectionIdRef.current === activeLocalBinding.connection_id &&
          errorState.currentConversationId === localConversationId &&
          errorState.nodesById[assistantNodeId] !== undefined;
        if (!errorStillTargetsCurrentLocalConversation) {
          return false;
        }
        useWorkspaceStore.getState().updateNode(assistantNodeId, {
          content: message,
          state: "error",
          metadata: {
            ...useWorkspaceStore.getState().nodesById[assistantNodeId]?.metadata,
            retry_disabled: true,
            error: {
              kind: "server",
              detail: message,
              happened_at: new Date().toISOString(),
            },
          },
        });
        setLocalPendingAssistant(null);
        notifyFeedback({
          tone: "error",
          title: "本地 Agent 发送失败",
          description: message,
        });
        return false;
      }
    },
    [
      activeLocalBinding,
      agent.data?.name,
      agentId,
      localAgentEnabled,
      localMessagesQuery.data,
      localSendMutation,
      pendingApprovalCount,
      queryClient,
      selectedLocalConnection,
      selectedModelLabel,
      setActiveRunId,
      setCurrentConversation,
      setLocalPendingAssistant,
      startLocalAgentEventStream,
    ],
  );

  // v3 conversation history handlers
  const handleNewConversation = useCallback(() => {
    focusLocalConversationOnceRef.current = false;
    if (localAgentEnabled && selectedLocalConnection !== null) {
      localTargetRequestSeqRef.current += 1;
      const requestSeq = localTargetRequestSeqRef.current;
      const connectionId = selectedLocalConnection.id;
      selectedLocalConnectionIdRef.current = connectionId;
      localBindingFocusConnectionRef.current = connectionId;
      focusLocalConversationOnceRef.current = true;
      localAgentStreamTokenRef.current = null;
      localAgentStreamRef.current?.close();
      localAgentStreamRef.current = null;
      setActiveLocalBinding(null);
      setLocalPendingAssistant(null);
      void (async () => {
        try {
          const binding = await localBindingMutation.mutateAsync(connectionId);
          if (
            localTargetRequestSeqRef.current !== requestSeq ||
            !localAgentEnabledRef.current ||
            selectedLocalConnectionIdRef.current !== binding.connection_id
          ) {
            return;
          }
          setActiveLocalBinding(binding);
          ensureLocalAgentConversation({
            binding,
            connection: selectedLocalConnection,
            fallbackTitle: `${agent.data?.name ?? agentId} 本地 Agent`,
            pendingApprovalCount,
            focus: true,
          });
          await queryClient.invalidateQueries({
            queryKey: ["local-agent-bindings", connectionId],
          });
          await queryClient.invalidateQueries({
            queryKey: ["agent-session-messages", binding.agent_session_id],
          });
          await queryClient.invalidateQueries({
            queryKey: ["local-agent-binding-tasks", binding.id],
          });
        } catch (error) {
          focusLocalConversationOnceRef.current = false;
          localBindingFocusConnectionRef.current = null;
          notifyFeedback({
            tone: "error",
            title: "本地 Agent 新会话创建失败",
            description: error instanceof Error ? error.message : String(error),
          });
        }
      })();
      notifyFeedback({
        tone: "info",
        title: "已新建本地 Agent 会话",
        description: "正在创建独立的本地会话，不会复用上一段上下文。",
      });
      if (historyNarrow) setHistoryOverlayOpen(false);
      return;
    }
    newConversation();
    notifyFeedback({
      tone: "info",
      title: "已新建会话",
      description: "现在可以从空白工作台开始新的问题、安装验证或演示流程。",
    });
    if (historyNarrow) setHistoryOverlayOpen(false);
  }, [
    agent.data?.name,
    agentId,
    historyNarrow,
    localAgentEnabled,
    localBindingMutation,
    newConversation,
    pendingApprovalCount,
    queryClient,
    selectedLocalConnection,
    setLocalPendingAssistant,
  ]);

  const handleSelectConversation = useCallback(
    (id: string) => {
      focusLocalConversationOnceRef.current = false;
      const conversation = useWorkspaceStore
        .getState()
        .conversations.find((item) => item.id === id);
      const localBinding = localAgentBindingHintFromConversation(conversation);
      if (localBinding !== null) {
        selectedLocalConnectionIdRef.current = localBinding.connectionId;
        localAgentEnabledRef.current = true;
        localBindingFocusConnectionRef.current = null;
        localAgentStreamTokenRef.current = null;
        localAgentStreamRef.current?.close();
        localAgentStreamRef.current = null;
        const bindingFromCache = queryClient
          .getQueryData<LocalAgentConversationBindingPage>([
            "local-agent-bindings",
            localBinding.connectionId,
          ])
          ?.items.find(
            (binding) =>
              binding.id === localBinding.bindingId ||
              binding.agent_session_id === localBinding.agentSessionId,
          );
        setActiveLocalBinding(
          bindingFromCache ?? localAgentBindingFromHint(localBinding, agentId),
        );
        setLocalPendingAssistant(null);
        setSelectedLocalConnectionId(localBinding.connectionId);
        setLocalAgentEnabled(true);
      } else {
        localAgentEnabledRef.current = false;
        localBindingFocusConnectionRef.current = null;
        localAgentStreamTokenRef.current = null;
        localAgentStreamRef.current?.close();
        localAgentStreamRef.current = null;
        setActiveLocalBinding(null);
        setLocalPendingAssistant(null);
        setLocalAgentEnabled(false);
      }
      setCurrentConversation(id);
      if (historyNarrow) setHistoryOverlayOpen(false);
    },
    [agentId, historyNarrow, queryClient, setCurrentConversation, setLocalPendingAssistant],
  );

  const handleDeleteConversation = useCallback(
    async (id: string) => {
      const current = useWorkspaceStore.getState().conversations.find((c) => c.id === id);
      const title = current?.title ?? "";
      const confirmed = await confirm({
        title: "删除对话",
        description: `将删除对话“${title || "未命名对话"}”。此操作不可撤销。`,
        confirmText: "确认删除",
        variant: "danger",
      });
      if (!confirmed) return;
      deleteConversation(id);
      notifyFeedback({
        tone: "warning",
        title: "对话已删除",
        description: title ? `已删除“${title}”。` : "已删除当前对话。",
      });
    },
    [confirm, deleteConversation],
  );

  const handleToggleHistoryCollapsed = useCallback(() => {
    if (historyNarrow) {
      setHistoryOverlayOpen((open) => !open);
      return;
    }
    setHistoryPanelCollapsed(!historyPanelCollapsed);
  }, [historyNarrow, historyPanelCollapsed, setHistoryPanelCollapsed]);

  const historyCollapsed = historyNarrow
    ? !historyOverlayOpen
    : historyPanelCollapsed;

  return (
    <ConsoleShell title={text("智能体工作台", "Agent Workspace")}>
      <div className="relative flex h-full min-h-0 w-full min-w-0 overflow-hidden bg-white">
        <ConversationHistoryPanel
          collapsed={historyCollapsed}
          conversations={conversations}
          currentConversationId={currentConversationId}
          groupLabelForConversation={conversationGroupLabel}
          onNewConversation={handleNewConversation}
          onSelectConversation={handleSelectConversation}
          onDeleteConversation={handleDeleteConversation}
          onToggleCollapsed={handleToggleHistoryCollapsed}
        />
        <ChatSurface
          agentId={agentId}
          agentName={agent.data?.name ?? agentId}
          modelLabel={selectedModelLabel}
          modelLabelIsFallback={modelLabelIsFallback}
          workspaceMode={workspaceMode}
          onWorkspaceModeChange={setWorkspaceMode}
          activeRunId={activeRunId}
          runStatus={workspace.data?.run.status}
          runCreatedAt={workspace.data?.run.created_at}
          pendingApprovalCount={pendingApprovalCount}
          metadataUsage={inspectorUsage}
          onOpenInspector={setInspectorSection}
          stream={stream}
          tools={tools}
          providers={providers}
          selectedProviderId={selectedProviderId}
          selectedModelId={selectedModelId}
          onModelChange={handleModelChange}
          onExport={handleExport}
          onClearConversation={handleClearConversation}
          onOpenSearch={handleOpenSearch}
          onOpenShortcut={handleOpenShortcut}
          modelPickerOpenSeq={modelPickerOpenSeq}
          onRequestModelPicker={handleRequestModelPicker}
          jumpTarget={jumpTarget}
          onCreateTeamFromConversation={() => createTeamFromConversation.mutate()}
          isCreatingTeam={createTeamFromConversation.isPending}
          agents={workspaceAgents}
          agentsLoading={agentsQuery.isLoading}
          onAgentChange={handleAgentChange}
          localAgentEnabled={localAgentEnabled}
          localAgentConnections={localConnections}
          selectedLocalConnectionId={
            localAgentEnabled
              ? selectedLocalConnectionId ?? selectedLocalConnection?.id ?? null
              : null
          }
          onLocalAgentTargetChange={handleLocalAgentTargetChange}
          localAgentControl={
            <LocalAgentWorkspaceControl
              enabled={localAgentEnabled}
              connections={localConnections}
              selectedConnectionId={selectedLocalConnection?.id ?? null}
              binding={activeLocalBinding}
              isBindingPending={localBindingMutation.isPending}
              isSending={localSendMutation.isPending}
              pendingApprovalCount={pendingApprovalCount}
              activeRunId={activeRunId}
              onEnabledChange={handleLocalAgentEnabledChange}
              onOpenStudio={() => navigate("/agents")}
            />
          }
          localAgentPending={
            localAgentEnabled &&
            localAgentTaskBlocking
          }
          onLocalAgentSubmit={localAgentEnabled ? handleLocalAgentSubmit : undefined}
        />
        <InspectorDrawer
          section={inspectorSection}
          activeRunId={activeRunId}
          pendingApprovalCount={pendingApprovalCount}
          artifacts={inspectorArtifacts}
          onClose={() => setInspectorSection(null)}
        />
      </div>
      <SearchOverlay
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
        nodesById={nodesById}
        onJumpToNode={handleJumpToNode}
      />
      <ShortcutOverlay open={shortcutOpen} onClose={() => setShortcutOpen(false)} />
      {confirmDialog}
    </ConsoleShell>
  );
}

/**
 * Flatten `ModelSettings.providers` (typed as `Array<Record<string, unknown>>`
 * on the API surface, but shaped like `ProviderConfig` at runtime) into the
 * `ModelOption` list consumed by `ModelPicker`.
 */
function deriveModelOptions(settings: ModelSettings | undefined): ModelOption[] {
  if (settings === undefined) return [];
  const out: ModelOption[] = [];
  for (const raw of settings.providers) {
    if (typeof raw !== "object" || raw === null) continue;
    const record = raw as Record<string, unknown>;
    const name = record.name;
    if (typeof name !== "string" || name.length === 0) continue;
    const labelRaw = record.label;
    const modelRaw = record.model;
    const providerLabel =
      typeof labelRaw === "string" && labelRaw.length > 0 ? labelRaw : name;
    const modelId =
      typeof modelRaw === "string" && modelRaw.length > 0 ? modelRaw : "default";
    out.push({
      providerId: name,
      providerLabel,
      modelId,
      modelLabel: modelId,
    });
  }
  return out;
}

function localAgentModelFromConnection(
  connection: LocalAgentConnection | null,
): { providerId: string; modelId: string } | null {
  if (connection === null) return null;
  const providerId = firstStringCapability(
    connection.capabilities_json,
    "model_provider",
    "selected_model_provider",
    "default_model_provider",
  );
  const modelId = firstStringCapability(
    connection.capabilities_json,
    "model_name",
    "selected_model",
    "default_model",
    "ANTHROPIC_MODEL",
  );
  if (providerId === null || modelId === null) return null;
  if (providerId === "default" || modelId === "default") return null;
  return { providerId, modelId };
}

function firstStringCapability(
  capabilities: Record<string, unknown>,
  ...keys: string[]
): string | null {
  for (const key of keys) {
    const value = capabilities[key];
    if (typeof value !== "string") continue;
    const trimmed = value.trim();
    if (trimmed.length > 0) return trimmed;
  }
  return null;
}

function LocalAgentWorkspaceControl({
  enabled,
  connections,
  selectedConnectionId,
  binding,
  isBindingPending,
  isSending,
  pendingApprovalCount,
  activeRunId,
  onEnabledChange,
  onOpenStudio,
}: {
  enabled: boolean;
  connections: LocalAgentConnection[];
  selectedConnectionId: string | null;
  binding: LocalAgentConversationBinding | null;
  isBindingPending: boolean;
  isSending: boolean;
  pendingApprovalCount: number;
  activeRunId: string | null;
  onEnabledChange: (enabled: boolean) => void;
  onOpenStudio: () => void;
}) {
  const selected =
    connections.find((connection) => connection.id === selectedConnectionId) ?? null;
  const usesClaudePermissionBridge =
    selected !== null && localAgentUsesClaudePermissionBridge(selected);
  const statusLabel = selected ? localAgentStatusLabel(selected.status) : "未接入";
  const statusClassName = selected
    ? selected.status === "online" || selected.status === "busy"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : selected.status === "offline"
        ? "border-amber-200 bg-amber-50 text-amber-700"
        : "border-slate-200 bg-slate-50 text-slate-600"
    : "border-slate-200 bg-slate-50 text-slate-600";
  const localAgentSummary = enabled
    ? "本地 Agent"
    : connections.length > 0
      ? `${connections.length} 个本地`
      : "本地 Agent";

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-1.5">
      {connections.length === 0 ? (
        <button
          type="button"
          onClick={onOpenStudio}
          className="inline-flex h-7 items-center rounded-md border border-slate-200 bg-white px-2 text-[11px] font-medium text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
        >
          接入本地 Agent
        </button>
      ) : (
        <button
          type="button"
          onClick={() => onEnabledChange(!enabled)}
          className={cn(
            "inline-flex h-7 items-center rounded-md border px-2 text-[11px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400",
            enabled
              ? "border-slate-900 bg-slate-900 text-white hover:bg-slate-800"
              : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50",
          )}
          aria-label={enabled ? "关闭本地 Agent" : "启用本地 Agent"}
        >
          {localAgentSummary}
        </button>
      )}
      <span
        className={cn(
          "inline-flex h-7 shrink-0 items-center rounded-md border px-2 text-[11px] font-medium",
          statusClassName,
        )}
      >
        {statusLabel}
      </span>
      {enabled && selected !== null ? (
        <span className="max-w-[12rem] truncate text-[11px] text-slate-500">
          {localAgentConnectionOptionLabel(selected)}
        </span>
      ) : null}
      {enabled && isBindingPending ? (
        <span className="shrink-0 text-[11px] text-slate-500">正在恢复...</span>
      ) : null}
      {enabled && binding !== null ? (
        <span className="shrink-0 font-mono text-[11px] text-slate-500">
          Session {formatLocalAgentSessionId(binding.agent_session_id)}
        </span>
      ) : null}
      {enabled && isSending ? (
        <span className="shrink-0 text-[11px] text-slate-500">正在排队...</span>
      ) : null}
      {enabled && selected?.status === "offline" ? (
        <span className="max-w-[18rem] truncate text-[11px] text-amber-700">
          离线时消息会保持 pending
        </span>
      ) : null}
      {enabled && usesClaudePermissionBridge && pendingApprovalCount > 0 ? (
        <span className="max-w-[18rem] truncate text-[11px] text-amber-700">
          等待 Claude Code 本地工具审批
          {activeRunId ? (
            <a
              className="ml-1 font-medium underline-offset-2 hover:underline"
              href={`/runs/${activeRunId}#approvals`}
            >
              运行详情
            </a>
          ) : null}
        </span>
      ) : null}
    </div>
  );
}

function localAgentUsesClaudePermissionBridge(connection: LocalAgentConnection | null): boolean {
  return (
    connection !== null &&
    connection.adapter_kind === "claude_code" &&
    connection.capabilities_json.permission_bridge === "harness_local_tool_request_v1" &&
    connection.capabilities_json.permission_bridge_execution === "harness_owned_executor" &&
    connection.capabilities_json.sdk_native_tool_execution_enabled === false
  );
}

function localAgentConnectionOptionLabel(connection: LocalAgentConnection): string {
  if (localAgentUsesClaudePermissionBridge(connection)) {
    return `${connection.display_name} · Claude Code · 权限桥 · 上下文重放`;
  }
  if (connection.adapter_kind === "claude_code") {
    return `${connection.display_name} · Claude Code · 对话模式 · 上下文重放`;
  }
  return `${connection.display_name} · ${connection.adapter_kind}`;
}

function localAgentStatusLabel(status: string): string {
  switch (status) {
    case "online":
      return "在线";
    case "busy":
      return "执行中";
    case "offline":
      return "离线";
    case "revoked":
      return "已撤销";
    default:
      return status || "未知";
  }
}

function formatLocalAgentSessionId(sessionId: string): string {
  return sessionId.length <= 12 ? sessionId : sessionId.slice(0, 8);
}

function localAgentConversationFromMessages({
  binding,
  messages,
  pendingTasks,
  connection,
  fallbackTitle,
  pendingApprovalCount,
  pendingUserNode,
  pendingNode,
}: {
  binding: LocalAgentConversationBinding;
  messages: AgentMessage[];
  pendingTasks: LocalAgentBindingTask[];
  connection: LocalAgentConnection | null;
  fallbackTitle: string;
  pendingApprovalCount: number;
  pendingUserNode?: ConversationNode;
  pendingNode?: ConversationNode;
}): ConversationSummary {
  const createdAt = messages[0]?.created_at ?? binding.created_at;
  const updatedAt = latestLocalAgentConversationTime(messages, pendingTasks, binding.updated_at);
  const root: ConversationNode = {
    id: "root",
    parent_id: null,
    children_ids: [],
    role: "system",
    content: "Agent Workspace Pro root",
    state: "done",
    metadata: {
      orchestration: {
        source: "local_agent",
        binding_id: binding.id,
        connection_id: binding.connection_id,
        agent_session_id: binding.agent_session_id,
        adapter_kind: connection?.adapter_kind,
      },
    },
    tool_calls: [],
    artifacts: [],
    created_at: createdAt,
  };
  const nodesById: Record<string, ConversationNode> = { [root.id]: root };
  const messageNodeIds = new Map<string, string>();
  const clientMessageNodeIds = new Map<string, string>();
  let parentId = root.id;
  let firstUserContent: string | null = null;

  for (const message of messages) {
    const nodeId = `local-msg:${message.id}`;
    const node: ConversationNode = {
      id: nodeId,
      parent_id: parentId,
      children_ids: [],
      role: message.role,
      content: message.content,
      state: "done",
      run_id: typeof message.metadata_json.run_id === "string" ? message.metadata_json.run_id : undefined,
      metadata: {
        workspace_mode:
          typeof message.metadata_json.workspace_mode === "string"
            ? (message.metadata_json.workspace_mode as ConversationNode["metadata"]["workspace_mode"])
            : "chat",
        input_tokens: readNumberMetadata(message.metadata_json.input_tokens),
        output_tokens: readNumberMetadata(message.metadata_json.output_tokens),
        duration_ms: readNumberMetadata(message.metadata_json.duration_ms),
        cost_usd:
          typeof message.metadata_json.cost_usd === "string"
            ? message.metadata_json.cost_usd
            : null,
        cost_unavailable: message.metadata_json.cost_unavailable === true,
        model_call_id:
          typeof message.metadata_json.model_call_id === "string"
            ? message.metadata_json.model_call_id
            : null,
        orchestration: {
          source: "local_agent",
          binding_id: binding.id,
          connection_id: binding.connection_id,
          agent_session_id: binding.agent_session_id,
          message_id: message.id,
          ...message.metadata_json,
        },
      },
      tool_calls: [],
      artifacts: [],
      created_at: message.created_at,
    };
    messageNodeIds.set(message.id, node.id);
    const clientMessageId = message.metadata_json.client_message_id;
    if (message.role === "user" && typeof clientMessageId === "string") {
      clientMessageNodeIds.set(clientMessageId, node.id);
    }
    nodesById[parentId] = {
      ...nodesById[parentId],
      children_ids: [...nodesById[parentId].children_ids, node.id],
    };
    nodesById[node.id] = node;
    parentId = node.id;
    if (firstUserContent === null && message.role === "user" && message.content.trim()) {
      firstUserContent = message.content.trim();
    }
  }

  const hasServerUserForPending =
    pendingUserNode !== undefined &&
    messages.some(
      (message) =>
        message.role === "user" &&
        message.metadata_json.client_message_id ===
          pendingUserNode.metadata.orchestration?.client_message_id,
    );
  const lastServerMessage = messages[messages.length - 1];
  const pendingBridgeTaskId = pendingNode?.metadata.orchestration?.bridge_task_id;
  const hasServerAssistantForPending =
    typeof pendingBridgeTaskId === "string" &&
    messages.some(
      (message) =>
        message.role === "assistant" && message.metadata_json.bridge_task_id === pendingBridgeTaskId,
    );
  const pendingTaskForBrowserNode = pendingTasks.find(
    (task) =>
      task.client_message_id === pendingNode?.metadata.orchestration?.client_message_id ||
      task.id === pendingNode?.metadata.orchestration?.bridge_task_id,
  );
  const pendingTaskIsTerminalError =
    pendingTaskForBrowserNode?.status === "failed" ||
    pendingTaskForBrowserNode?.status === "cancelled";
  const pendingTaskErrorMessage =
    pendingTaskForBrowserNode?.error_message?.trim() ||
    (pendingTaskForBrowserNode?.status === "cancelled"
      ? "本地 Agent 任务已取消。"
      : "本地 Agent 执行失败。");
  const pendingNodeHasStreamedContent =
    pendingNode?.metadata.orchestration?.streaming_via === "task_event_sse" &&
    pendingNode.content.trim().length > 0;
  const pendingNodeHasActiveStreamedContent =
    pendingNode !== undefined &&
    pendingNodeHasStreamedContent &&
    ["streaming", "waiting_approval", "awaiting_message_hydration"].includes(
      String(pendingNode.metadata.orchestration?.status ?? ""),
    ) &&
    !pendingTaskIsTerminalError &&
    !hasServerAssistantForPending;
  const shouldKeepPendingAssistant =
    pendingNode !== undefined &&
    ((pendingTaskIsTerminalError && !hasServerAssistantForPending) ||
      pendingNodeHasActiveStreamedContent ||
      (!hasServerAssistantForPending &&
        pendingTaskForBrowserNode === undefined &&
        lastServerMessage?.role !== "assistant"));

  if (pendingUserNode !== undefined && !hasServerUserForPending) {
    const user = { ...pendingUserNode, parent_id: parentId, children_ids: [] };
    nodesById[parentId] = {
      ...nodesById[parentId],
      children_ids: [...nodesById[parentId].children_ids, user.id],
    };
    nodesById[user.id] = user;
    parentId = user.id;
    if (firstUserContent === null && user.content.trim()) {
      firstUserContent = user.content.trim();
    }
  }

  if (shouldKeepPendingAssistant) {
    const pendingStatus =
      typeof pendingTaskForBrowserNode?.status === "string"
        ? pendingTaskForBrowserNode.status
        : typeof pendingNode.metadata.orchestration?.status === "string"
        ? pendingNode.metadata.orchestration.status
        : "pending";
    const assistant = {
      ...pendingNode,
      parent_id: parentId,
      children_ids: [],
      run_id: pendingTaskForBrowserNode?.run_id ?? pendingNode.run_id,
      content: pendingTaskIsTerminalError
        ? ""
        : pendingNodeHasStreamedContent
        ? pendingNode.content
        : localAgentPendingTaskContent(pendingStatus, connection, pendingApprovalCount),
      state: pendingTaskIsTerminalError ? "error" : pendingNode.state,
      metadata: {
        ...pendingNode.metadata,
        orchestration: {
          ...pendingNode.metadata.orchestration,
          connection_id:
            pendingTaskForBrowserNode?.connection_id ??
            pendingNode.metadata.orchestration?.connection_id,
          binding_id:
            pendingTaskForBrowserNode?.binding_id ??
            pendingNode.metadata.orchestration?.binding_id,
          agent_session_id:
            pendingTaskForBrowserNode?.agent_session_id ??
            pendingNode.metadata.orchestration?.agent_session_id,
          bridge_task_id:
            pendingTaskForBrowserNode?.id ??
            pendingNode.metadata.orchestration?.bridge_task_id,
          client_message_id:
            pendingTaskForBrowserNode?.client_message_id ??
            pendingNode.metadata.orchestration?.client_message_id,
          status: pendingStatus,
        },
        ...(pendingTaskIsTerminalError
          ? {
              retry_disabled: true,
              error: {
                kind: "server" as const,
                detail:
                  pendingTaskForBrowserNode?.status === "cancelled"
                    ? "本地 Agent 任务已取消"
                    : "本地 Agent 执行失败",
                body_preview: pendingTaskErrorMessage,
                happened_at: pendingTaskForBrowserNode?.updated_at ?? pendingNode.created_at,
              },
            }
          : {}),
      },
    };
    nodesById[parentId] = {
      ...nodesById[parentId],
      children_ids: [...nodesById[parentId].children_ids, assistant.id],
    };
    nodesById[assistant.id] = assistant;
    parentId = assistant.id;
  }

  for (const task of pendingTasks) {
    if (task.id === pendingTaskForBrowserNode?.id) {
      continue;
    }
    if (
      messages.some(
        (message) =>
          message.role === "assistant" &&
          message.metadata_json.bridge_task_id === task.id,
      )
    ) {
      continue;
    }
    const taskParentId =
      task.id === pendingNode?.metadata.orchestration?.bridge_task_id
        ? pendingNode.parent_id ?? undefined
        : messageNodeIds.get(task.user_message_id) ?? clientMessageNodeIds.get(task.client_message_id);
    const taskNodeId = `local-task:${task.id}:${task.status}`;
    if (taskParentId === undefined || nodesById[taskNodeId] !== undefined) {
      continue;
    }
    const isTerminalError = task.status === "failed" || task.status === "cancelled";
    const errorMessage =
      task.error_message?.trim() ||
      (task.status === "cancelled" ? "本地 Agent 任务已取消。" : "本地 Agent 执行失败。");
    const assistant: ConversationNode = {
      id: taskNodeId,
      parent_id: taskParentId,
      children_ids: [],
      role: "assistant",
      content: isTerminalError
        ? ""
        : localAgentPendingTaskContent(task.status, connection, pendingApprovalCount),
      state: isTerminalError ? "error" : "streaming",
      run_id: task.run_id,
      metadata: {
        workspace_mode: "chat",
        orchestration: {
          source: "local_agent",
          connection_id: task.connection_id,
          binding_id: task.binding_id,
          agent_session_id: task.agent_session_id,
          bridge_task_id: task.id,
          client_message_id: task.client_message_id,
          status: task.status,
        },
        ...(isTerminalError
          ? {
              retry_disabled: true,
              error: {
                kind: "server",
                detail:
                  task.status === "cancelled"
                    ? "本地 Agent 任务已取消"
                    : "本地 Agent 执行失败",
                body_preview: errorMessage,
                happened_at: task.updated_at,
              },
            }
          : {}),
      },
      tool_calls: [],
      artifacts: [],
      created_at: isTerminalError ? task.updated_at : task.created_at,
    };
    nodesById[taskParentId] = {
      ...nodesById[taskParentId],
      children_ids: [...nodesById[taskParentId].children_ids, assistant.id],
    };
    nodesById[assistant.id] = assistant;
    parentId = assistant.id;
  }

  const title = firstUserContent?.slice(0, 40) || fallbackTitle;
  return {
    id: localAgentConversationId(binding.id),
    title,
    created_at: createdAt,
    updated_at: updatedAt,
    nodesById,
    rootNodeId: root.id,
    activeLeafId: parentId,
    pinnedNodeIds: [],
    dismissedPlanNodeIds: [],
    draft: "",
    contextWindowTurns: 8,
    contextCompressions: {},
  };
}

function readNumberMetadata(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function localAgentConversationId(bindingId: string): string {
  return `local-agent:${bindingId}`;
}

function localAgentBindingHintFromConversation(
  conversation: ConversationSummary | undefined,
): { bindingId: string; connectionId: string; agentSessionId: string } | null {
  if (conversation === undefined) return null;
  for (const node of Object.values(conversation.nodesById)) {
    const orchestration = node.metadata.orchestration;
    const bindingId = orchestration?.binding_id;
    const connectionId = orchestration?.connection_id;
    const agentSessionId = orchestration?.agent_session_id;
    if (
      typeof bindingId === "string" &&
      bindingId.length > 0 &&
      typeof connectionId === "string" &&
      connectionId.length > 0 &&
      typeof agentSessionId === "string" &&
      agentSessionId.length > 0
    ) {
      return { bindingId, connectionId, agentSessionId };
    }
  }
  return null;
}

function localAgentBindingFromHint(hint: {
  bindingId: string;
  connectionId: string;
  agentSessionId: string;
}, agentId: string): LocalAgentConversationBinding {
  const now = new Date().toISOString();
  return {
    id: hint.bindingId,
    connection_id: hint.connectionId,
    agent_id: agentId,
    agent_session_id: hint.agentSessionId,
    adapter_session_id: null,
    resume_mode: "context_replay_new_session",
    status: "active",
    created_at: now,
    updated_at: now,
  };
}

function localAgentBindingMatchesHint(
  binding: LocalAgentConversationBinding,
  hint: { bindingId: string; connectionId: string; agentSessionId: string },
): boolean {
  return (
    binding.id === hint.bindingId &&
    binding.connection_id === hint.connectionId &&
    binding.agent_session_id === hint.agentSessionId
  );
}

function mostRecentLocalAgentConversationForConnection(
  conversations: ConversationSummary[],
  connectionId: string,
): ConversationSummary | undefined {
  return conversations
    .filter((conversation) => {
      const hint = localAgentBindingHintFromConversation(conversation);
      return hint?.connectionId === connectionId;
    })
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))[0];
}

function mostRecentActiveBindingForConnection(
  bindings: LocalAgentConversationBinding[],
  connectionId: string,
): LocalAgentConversationBinding | undefined {
  return bindings
    .filter(
      (binding) =>
        binding.connection_id === connectionId && binding.status === "active",
    )
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))[0];
}

function ensureLocalAgentConversation({
  binding,
  connection,
  fallbackTitle,
  pendingApprovalCount,
  focus,
}: {
  binding: LocalAgentConversationBinding;
  connection: LocalAgentConnection | null;
  fallbackTitle: string;
  pendingApprovalCount: number;
  focus: boolean;
}): void {
  const store = useWorkspaceStore.getState();
  const conversationId = localAgentConversationId(binding.id);
  const existing = store.conversations.find((conversation) => conversation.id === conversationId);
  if (existing === undefined) {
    const summary = localAgentConversationFromMessages({
      binding,
      messages: [],
      pendingTasks: [],
      connection,
      fallbackTitle,
      pendingApprovalCount,
    });
    const root = summary.nodesById[summary.rootNodeId];
    const summaryWithConnectionMarker: ConversationSummary = {
      ...summary,
      nodesById: {
        ...summary.nodesById,
        [summary.rootNodeId]: {
          ...root,
          metadata: {
            ...root.metadata,
            orchestration: {
              source: "local_agent",
              binding_id: binding.id,
              connection_id: binding.connection_id,
              agent_session_id: binding.agent_session_id,
              adapter_kind: connection?.adapter_kind,
            },
          },
        },
      },
      draft: store.draft,
    };
    store.upsertConversationSummary(summaryWithConnectionMarker);
  }
  if (focus && useWorkspaceStore.getState().currentConversationId !== conversationId) {
    useWorkspaceStore.getState().setCurrentConversation(conversationId);
  }
}

function ensurePendingLocalAgentConversation({
  connection,
  fallbackTitle,
  focus,
}: {
  connection: LocalAgentConnection | null;
  fallbackTitle: string;
  focus: boolean;
}): void {
  if (connection === null) return;
  const store = useWorkspaceStore.getState();
  const conversationId = pendingLocalAgentConversationId(connection.id);
  const existing = store.conversations.find((conversation) => conversation.id === conversationId);
  if (existing === undefined) {
    const now = new Date().toISOString();
    const root: ConversationNode = {
      id: "root",
      parent_id: null,
      children_ids: ["local-agent-pending"],
      role: "system",
      content: "Agent Workspace Pro root",
      state: "done",
      metadata: {
        orchestration: {
          source: "local_agent",
          connection_id: connection.id,
          adapter_kind: connection.adapter_kind,
          pending_binding: true,
        },
      },
      tool_calls: [],
      artifacts: [],
      created_at: now,
    };
    const pending: ConversationNode = {
      id: "local-agent-pending",
      parent_id: root.id,
      children_ids: [],
      role: "assistant",
      content: `正在恢复 ${connection.display_name} 的本地会话...`,
      state: "streaming",
      metadata: {
        workspace_mode: "chat",
        orchestration: {
          source: "local_agent",
          connection_id: connection.id,
          adapter_kind: connection.adapter_kind,
          pending_binding: true,
        },
      },
      tool_calls: [],
      artifacts: [],
      created_at: now,
    };
    store.upsertConversationSummary({
      id: conversationId,
      title: fallbackTitle,
      created_at: now,
      updated_at: now,
      nodesById: { [root.id]: root, [pending.id]: pending },
      rootNodeId: root.id,
      activeLeafId: pending.id,
      pinnedNodeIds: [],
      dismissedPlanNodeIds: [],
      draft: "",
      contextWindowTurns: 8,
      contextCompressions: {},
    });
  }
  if (focus && useWorkspaceStore.getState().currentConversationId !== conversationId) {
    useWorkspaceStore.getState().setCurrentConversation(conversationId);
  }
}

function pendingLocalAgentConversationId(connectionId: string): string {
  return `local-agent-pending:${connectionId}`;
}

function isPendingLocalAgentConversationForConnection(
  conversation: ConversationSummary,
  connectionId: string,
): boolean {
  if (conversation.id === pendingLocalAgentConversationId(connectionId)) {
    return true;
  }
  return Object.values(conversation.nodesById).some((node) => {
    const orchestration = node.metadata.orchestration;
    return (
      orchestration?.source === "local_agent" &&
      orchestration.pending_binding === true &&
      orchestration.connection_id === connectionId
    );
  });
}

function localAgentSubmitContextForBinding(
  context: LocalAgentSubmitContext,
  store: ReturnType<typeof useWorkspaceStore.getState>,
  binding: LocalAgentConversationBinding,
): LocalAgentSubmitContext {
  const localConversationId = localAgentConversationId(binding.id);
  const useRuntimeConversation = store.currentConversationId === localConversationId;
  let nodesById: Record<string, ConversationNode>;
  let activeLeafId: string;
  let rootNodeId: string;
  let pinnedNodeIds: string[];
  let contextWindowTurns: number;
  if (useRuntimeConversation) {
    nodesById = store.nodesById;
    activeLeafId = store.activeLeafId;
    rootNodeId = store.rootNodeId;
    pinnedNodeIds = store.pinnedNodeIds;
    contextWindowTurns = store.contextWindowTurns;
  } else {
    const conversation = store.conversations.find((item) => item.id === localConversationId);
    if (conversation === undefined) {
      return {
        ...context,
        messages: [],
        active_leaf_id: null,
        active_branch_id: null,
        pinned_node_ids: [],
        compressed_context: null,
      };
    }
    nodesById = conversation.nodesById;
    activeLeafId = conversation.activeLeafId;
    rootNodeId = conversation.rootNodeId;
    pinnedNodeIds = conversation.pinnedNodeIds;
    contextWindowTurns = conversation.contextWindowTurns;
  }
  const activePath = buildActivePath(nodesById, activeLeafId, rootNodeId);
  const messages = activePath
    .filter((node) => localAgentNodeMatchesBinding(node, binding))
    .map(localAgentMessageFromNode);
  const messageIds = new Set(messages.map((message) => message.id));
  return {
    ...context,
    messages,
    active_leaf_id: activeLeafId,
    active_branch_id: activeLeafId,
    pinned_node_ids: pinnedNodeIds,
    context_window_turns: contextWindowTurns,
    compressed_context: localAgentCompressedContextForBinding(
      context.compressed_context,
      activeLeafId,
      messageIds,
    ),
  };
}

function localAgentCompressedContextForBinding(
  compressedContext: LocalAgentSubmitContext["compressed_context"],
  activeLeafId: string,
  messageIds: Set<string>,
): LocalAgentSubmitContext["compressed_context"] {
  if (compressedContext === null || compressedContext === undefined) return null;
  if (compressedContext.branch_id !== activeLeafId) return null;
  if (compressedContext.coverage_node_ids.some((nodeId) => !messageIds.has(nodeId))) {
    return null;
  }
  return compressedContext;
}

function localAgentMessageFromNode(node: ConversationNode): AgentChatStreamMessage {
  return {
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
  };
}

function localAgentNodeMatchesBinding(
  node: ConversationNode | undefined,
  binding: LocalAgentConversationBinding,
): node is ConversationNode {
  if (node === undefined) return false;
  const orchestration = node.metadata.orchestration;
  if (orchestration === undefined) return false;
  const source = orchestration.source;
  if (source !== undefined && source !== "local_agent") return false;
  const bindingId = orchestration.binding_id;
  const connectionId = orchestration.connection_id;
  const sessionId = orchestration.agent_session_id;
  if (typeof bindingId === "string" && bindingId !== binding.id) return false;
  if (typeof connectionId === "string" && connectionId !== binding.connection_id) return false;
  if (typeof sessionId === "string" && sessionId !== binding.agent_session_id) return false;
  return (
    typeof bindingId === "string" ||
    typeof connectionId === "string" ||
    typeof sessionId === "string"
  );
}

function estimateLocalAgentInputTokens(goal: string, context: LocalAgentSubmitContext): number {
  const messageChars = context.messages.reduce(
    (total, message) => total + message.content.length + JSON.stringify(message.metadata).length,
    0,
  );
  const attachmentChars = context.attachments.reduce(
    (total, attachment) =>
      total +
      attachment.name.length +
      (attachment.content_text?.length ?? 0) +
      JSON.stringify({
        mime_type: attachment.mime_type,
        size_bytes: attachment.size_bytes,
        content_status: attachment.content_status,
        truncated: attachment.truncated,
      }).length,
    0,
  );
  const toolChars =
    JSON.stringify(context.tool_mentions).length + context.attachment_names.join("\n").length;
  const compressedContext = context.compressed_context ?? null;
  const compressedChars =
    compressedContext === null
      ? 0
      : compressedContext.summary.length +
        compressedContext.coverage_node_ids.join("\n").length +
        compressedContext.coverage_path_hash.length;
  return Math.max(
    1,
    Math.ceil((goal.length + messageChars + attachmentChars + toolChars + compressedChars) / 4),
  );
}

function localAgentConnectionIdFromConversation(conversation: ConversationSummary): string | null {
  for (const node of Object.values(conversation.nodesById)) {
    const connectionId = node.metadata.orchestration?.connection_id;
    if (typeof connectionId === "string" && connectionId.length > 0) {
      return connectionId;
    }
  }
  return null;
}

function isLocalAgentTaskActive(task: LocalAgentBindingTask): boolean {
  return task.status === "pending" || task.status === "leased" || task.status === "running";
}

function latestLocalAgentConversationTime(
  messages: AgentMessage[],
  tasks: LocalAgentBindingTask[],
  fallback: string,
): string {
  const candidates = [
    fallback,
    ...messages.map((message) => message.created_at),
    ...tasks.map((task) => task.updated_at || task.created_at),
  ];
  return candidates.reduce((latest, candidate) =>
    Date.parse(candidate) > Date.parse(latest) ? candidate : latest,
  );
}

function sortLocalAgentConnections(connections: LocalAgentConnection[]): LocalAgentConnection[] {
  const adapterRank: Record<string, number> = {
    hao: 0,
    codex: 1,
    claude_code: 2,
    fake: 3,
  };
  return [...connections].sort((a, b) => {
    const rank = (adapterRank[a.adapter_kind] ?? 99) - (adapterRank[b.adapter_kind] ?? 99);
    if (rank !== 0) return rank;
    const name = a.display_name.localeCompare(b.display_name, "zh-CN");
    if (name !== 0) return name;
    const workspace = String(a.workspace_root ?? "").localeCompare(
      String(b.workspace_root ?? ""),
      "zh-CN",
    );
    if (workspace !== 0) return workspace;
    const created = Date.parse(a.created_at) - Date.parse(b.created_at);
    if (created !== 0) return created;
    return a.id.localeCompare(b.id);
  });
}

function isUsableLocalAgentConnection(connection: LocalAgentConnection): boolean {
  return (
    connection.status !== "revoked" &&
    connection.status !== "pending_confirmation" &&
    connection.onboarding_confirmed === true
  );
}

function defaultLocalAgentConnection(
  connections: LocalAgentConnection[],
): LocalAgentConnection | null {
  return (
    connections.find(
      (connection) => connection.status === "online" || connection.status === "busy",
    ) ??
    connections[0] ??
    null
  );
}

function localAgentPendingTaskContent(
  taskStatus: string,
  connection: LocalAgentConnection | null,
  pendingApprovalCount = 0,
): string {
  if (connection?.status === "offline") {
    return "本地 Agent 当前离线，消息已排队。bridge 恢复后会继续处理。";
  }
  if (localAgentUsesClaudePermissionBridge(connection) && pendingApprovalCount > 0) {
    return "等待 Claude Code 本地工具审批。可在运行详情处理审批。";
  }
  if (taskStatus === "running" || taskStatus === "leased") {
    return "本地 Agent 正在处理，完成后会同步到这里。";
  }
  return "等待本地 Agent 响应...";
}

function localAgentToolApprovalContent(
  connection: LocalAgentConnection | null,
  toolName: string,
  approvalId: string | null,
): string {
  const adapterLabel =
    connection?.adapter_kind === "claude_code"
      ? "Claude Code"
      : connection?.adapter_kind === "codex"
        ? "Codex CLI"
        : "本地 Agent";
  const approvalHint = approvalId
    ? `审批 ${approvalId.slice(0, 8)}`
    : "审批";
  return `${adapterLabel} 请求本地工具 ${toolName}，正在等待 ${approvalHint}。处理后会继续流式输出。`;
}

function syncNodeToolCallsFromWorkspace(
  node: ConversationNode,
  callsById: Map<string, ToolCall>,
): ConversationNode["tool_calls"] {
  let changed = false;
  const next = node.tool_calls.map((raw) => {
    const toolCallId = typeof raw.tool_call_id === "string"
      ? raw.tool_call_id
      : typeof raw.id === "string"
        ? raw.id
        : null;
    if (toolCallId === null) return raw;
    const latest = callsById.get(toolCallId);
    if (!latest) return raw;
    const patch: Record<string, unknown> = {
      status: latest.status,
      output_json: latest.output_json ?? {},
      output_summary: latest.output_summary,
      duration_ms: latest.duration_ms,
      trace_id: latest.trace_id ?? null,
      error_message: latest.error_message ?? null,
    };
    const nextCall = { ...raw, ...patch };
    if (
      raw.status !== nextCall.status ||
      raw.output_summary !== nextCall.output_summary ||
      raw.duration_ms !== nextCall.duration_ms ||
      raw.trace_id !== nextCall.trace_id ||
      raw.error_message !== nextCall.error_message
    ) {
      changed = true;
    }
    return nextCall;
  });
  return changed ? next : node.tool_calls;
}
