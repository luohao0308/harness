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
  listLocalAgentBindingTasks,
  listAgentSessionMessages,
  listLocalAgentConnections,
  listLocalAgentConversationBindings,
  listTeams,
  sendLocalAgentMessage,
  type AgentMessage,
  type LocalAgentBindingTask,
  type LocalAgentConnection,
  type LocalAgentConversationBinding,
  type ModelSettings,
  type ToolCall,
} from "../../tasks/api";
import { ChatSurface } from "../components/ChatSurface";
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
  const localBindingCreateForRef = useRef<string | null>(null);

  const agent = useQuery({ queryKey: ["agents", agentId], queryFn: () => getAgent(agentId) });
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
      (localConnectionsQuery.data?.items ?? []).filter(
        (connection) => connection.agent_id === agentId && connection.status !== "revoked",
      ),
    [agentId, localConnectionsQuery.data],
  );
  const selectedLocalConnection = useMemo(
    () =>
      localConnections.find((connection) => connection.id === selectedLocalConnectionId) ??
      localConnections[0] ??
      null,
    [localConnections, selectedLocalConnectionId],
  );

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
      setActiveLocalBinding(binding);
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
    }: {
      bindingId: string;
      content: string;
      clientMessageId: string;
    }) => sendLocalAgentMessage(bindingId, { content, client_message_id: clientMessageId }),
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
    if (
      selectedLocalConnectionId !== null &&
      localConnections.some((connection) => connection.id === selectedLocalConnectionId)
    ) {
      return;
    }
    setSelectedLocalConnectionId(localConnections[0]?.id ?? null);
  }, [localConnections, selectedLocalConnectionId]);

  useEffect(() => {
    setActiveLocalBinding(null);
    setLocalPendingAssistantNodeId(null);
    localBindingCreateForRef.current = null;
  }, [agentId, selectedLocalConnectionId]);

  useEffect(() => {
    if (!localAgentEnabled || selectedLocalConnection === null) return;
    const bindings = localBindingsQuery.data?.items;
    if (bindings === undefined) return;
    const activeBinding = bindings.find((binding) => binding.status === "active") ?? bindings[0];
    if (activeBinding !== undefined) {
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
    localAgentEnabled,
    localBindingMutation,
    localBindingsQuery.data?.items,
    selectedLocalConnection,
  ]);

  useEffect(() => {
    if (!localAgentEnabled || activeLocalBinding === null || localMessagesQuery.data === undefined) {
      return;
    }
    const state = useWorkspaceStore.getState();
    const pendingNode =
      localPendingAssistantNodeId !== null
        ? state.nodesById[localPendingAssistantNodeId]
        : undefined;
    const pendingUserNode =
      pendingNode?.parent_id !== null && pendingNode?.parent_id !== undefined
        ? state.nodesById[pendingNode.parent_id]
        : undefined;
    const summary = localAgentConversationFromMessages({
      binding: activeLocalBinding,
      messages: localMessagesQuery.data.items,
      pendingTasks: localBindingTasksQuery.data?.items ?? [],
      connection: selectedLocalConnection,
      fallbackTitle: `${agent.data?.name ?? agentId} 本地 Agent`,
      pendingNode,
      pendingUserNode,
    });
    const conversationsWithoutLocal = state.conversations.filter(
      (conversation) => conversation.id !== summary.id,
    );
    hydrateFromConversations({
      conversations: [...conversationsWithoutLocal, summary],
      currentConversationId: summary.id,
      historyPanelCollapsed,
    });
    if (pendingNode !== undefined && !summary.nodesById[pendingNode.id]) {
      setLocalPendingAssistantNodeId(null);
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
    selectedLocalConnection,
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

  const handleLocalAgentEnabledChange = useCallback(
    (enabled: boolean): void => {
      setLocalAgentEnabled(enabled);
      if (!enabled || selectedLocalConnection === null) return;
      void (async () => {
        try {
          const bindings = await queryClient.fetchQuery({
            queryKey: ["local-agent-bindings", selectedLocalConnection.id],
            queryFn: () => listLocalAgentConversationBindings(selectedLocalConnection.id),
          });
          const activeBinding =
            bindings.items.find((binding) => binding.status === "active") ?? bindings.items[0];
          if (activeBinding !== undefined) {
            setActiveLocalBinding(activeBinding);
            return;
          }
          localBindingCreateForRef.current = selectedLocalConnection.id;
          const created = await localBindingMutation.mutateAsync(selectedLocalConnection.id);
          setActiveLocalBinding(created);
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

  const handleLocalAgentSubmit = useCallback(
    async (goal: string): Promise<void> => {
      if (!localAgentEnabled || selectedLocalConnection === null) return;
      if (activeLocalBinding === null) {
        notifyFeedback({
          tone: "warning",
          title: "本地 Agent 会话尚未就绪",
          description: "正在创建或恢复本地会话，请稍后再发送。",
        });
        return;
      }

      const store = useWorkspaceStore.getState();
      const clientMessageId = `local-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      const userNodeId = store.appendNode({
        parent_id: store.activeLeafId,
        role: "user",
        content: goal,
        state: "done",
        metadata: {
          workspace_mode: "chat",
          orchestration: {
            source: "local_agent",
            connection_id: selectedLocalConnection.id,
            binding_id: activeLocalBinding.id,
            client_message_id: clientMessageId,
          },
        },
        tool_calls: [],
        artifacts: [],
      });
      const assistantNodeId = useWorkspaceStore.getState().appendNode({
        parent_id: userNodeId,
        role: "assistant",
        content:
          selectedLocalConnection.status === "offline"
            ? "本地 Agent 当前离线，消息已排队。bridge 恢复后会继续处理。"
            : "等待本地 Agent 响应...",
        state: "streaming",
        metadata: {
          workspace_mode: "chat",
          orchestration: {
            source: "local_agent",
            connection_id: selectedLocalConnection.id,
            binding_id: activeLocalBinding.id,
            client_message_id: clientMessageId,
            adapter_kind: selectedLocalConnection.adapter_kind,
          },
        },
        tool_calls: [],
        artifacts: [],
      });
      setLocalPendingAssistantNodeId(assistantNodeId);

      try {
        const response = await localSendMutation.mutateAsync({
          bindingId: activeLocalBinding.id,
          content: goal,
          clientMessageId,
        });
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
            },
          },
        });
        await queryClient.invalidateQueries({
          queryKey: ["agent-session-messages", activeLocalBinding.agent_session_id],
        });
        await queryClient.invalidateQueries({
          queryKey: ["local-agent-binding-tasks", activeLocalBinding.id],
        });
        await queryClient.invalidateQueries({ queryKey: ["agent-run-workspace", response.run_id] });
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        useWorkspaceStore.getState().updateNode(assistantNodeId, {
          content: message,
          state: "error",
          metadata: {
            ...useWorkspaceStore.getState().nodesById[assistantNodeId]?.metadata,
            error: {
              kind: "server",
              detail: message,
              happened_at: new Date().toISOString(),
            },
          },
        });
        setLocalPendingAssistantNodeId(null);
        notifyFeedback({
          tone: "error",
          title: "本地 Agent 发送失败",
          description: message,
        });
      }
    },
    [
      activeLocalBinding,
      localAgentEnabled,
      localSendMutation,
      queryClient,
      selectedLocalConnection,
      setActiveRunId,
    ],
  );

  // v3 conversation history handlers
  const handleNewConversation = useCallback(() => {
    newConversation();
    notifyFeedback({
      tone: "info",
      title: "已新建会话",
      description: "现在可以从空白工作台开始新的问题、安装验证或演示流程。",
    });
    if (historyNarrow) setHistoryOverlayOpen(false);
  }, [historyNarrow, newConversation]);

  const handleSelectConversation = useCallback(
    (id: string) => {
      setCurrentConversation(id);
      if (historyNarrow) setHistoryOverlayOpen(false);
    },
    [historyNarrow, setCurrentConversation],
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
          localAgentPanel={
            <LocalAgentWorkspacePanel
              enabled={localAgentEnabled}
              connections={localConnections}
              selectedConnectionId={selectedLocalConnection?.id ?? null}
              binding={activeLocalBinding}
              isBindingPending={localBindingMutation.isPending}
              isSending={localSendMutation.isPending}
              onEnabledChange={handleLocalAgentEnabledChange}
              onConnectionChange={(connectionId) => {
                setSelectedLocalConnectionId(connectionId);
                setLocalAgentEnabled(true);
              }}
              onOpenStudio={() => navigate("/agents")}
            />
          }
          localAgentPending={
            localSendMutation.isPending ||
            localPendingAssistantNodeId !== null ||
            (localBindingTasksQuery.data?.items.length ?? 0) > 0
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

function LocalAgentWorkspacePanel({
  enabled,
  connections,
  selectedConnectionId,
  binding,
  isBindingPending,
  isSending,
  onEnabledChange,
  onConnectionChange,
  onOpenStudio,
}: {
  enabled: boolean;
  connections: LocalAgentConnection[];
  selectedConnectionId: string | null;
  binding: LocalAgentConversationBinding | null;
  isBindingPending: boolean;
  isSending: boolean;
  onEnabledChange: (enabled: boolean) => void;
  onConnectionChange: (connectionId: string) => void;
  onOpenStudio: () => void;
}) {
  const selected =
    connections.find((connection) => connection.id === selectedConnectionId) ?? null;
  const statusLabel = selected ? localAgentStatusLabel(selected.status) : "未接入";
  const statusClass = selected
    ? selected.status === "online" || selected.status === "busy"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : selected.status === "offline"
        ? "border-amber-200 bg-amber-50 text-amber-700"
        : "border-slate-200 bg-slate-50 text-slate-600"
    : "border-slate-200 bg-slate-50 text-slate-600";

  return (
    <div className="shrink-0 border-b border-slate-200 bg-slate-50/80 px-3 py-2 sm:px-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <label className="inline-flex items-center gap-2 text-xs font-medium text-slate-700">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(event) => onEnabledChange(event.currentTarget.checked)}
              className="h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-slate-500"
            />
            本地 Agent
          </label>
          {connections.length > 0 ? (
            <select
              value={selected?.id ?? ""}
              onChange={(event) => onConnectionChange(event.currentTarget.value)}
              className="h-8 max-w-[18rem] rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-700 outline-none focus:border-slate-400"
              aria-label="选择本地 Agent 连接"
            >
              {connections.map((connection) => (
                <option key={connection.id} value={connection.id}>
                  {connection.display_name} · {connection.adapter_kind}
                </option>
              ))}
            </select>
          ) : (
            <button
              type="button"
              onClick={onOpenStudio}
              className="h-8 rounded-md border border-slate-200 bg-white px-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              接入本地 Agent
            </button>
          )}
          <span
            className={`inline-flex h-7 items-center rounded-md border px-2 text-xs font-medium ${statusClass}`}
          >
            {statusLabel}
          </span>
          {selected?.workspace_root ? (
            <span className="max-w-[18rem] truncate text-xs text-slate-500">
              {selected.workspace_root}
            </span>
          ) : null}
        </div>
        <div className="flex min-w-0 items-center gap-2 text-xs text-slate-500">
          {enabled && isBindingPending ? <span>正在恢复会话...</span> : null}
          {enabled && binding !== null ? (
            <span>Session {formatLocalAgentSessionId(binding.agent_session_id)}</span>
          ) : null}
          {enabled && selected?.status === "offline" ? (
            <span className="text-amber-700">离线时消息会保持 pending，bridge 恢复后继续。</span>
          ) : null}
          {isSending ? <span>正在排队...</span> : null}
        </div>
      </div>
    </div>
  );
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
  pendingUserNode,
  pendingNode,
}: {
  binding: LocalAgentConversationBinding;
  messages: AgentMessage[];
  pendingTasks: LocalAgentBindingTask[];
  connection: LocalAgentConnection | null;
  fallbackTitle: string;
  pendingUserNode?: ConversationNode;
  pendingNode?: ConversationNode;
}): ConversationSummary {
  const createdAt = messages[0]?.created_at ?? binding.created_at;
  const updatedAt = messages[messages.length - 1]?.created_at ?? binding.updated_at;
  const root: ConversationNode = {
    id: "root",
    parent_id: null,
    children_ids: [],
    role: "system",
    content: "Agent Workspace Pro root",
    state: "done",
    metadata: {},
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
        workspace_mode: "chat",
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
  const pendingTaskForBrowserNode = pendingTasks.some(
    (task) =>
      task.client_message_id === pendingNode?.metadata.orchestration?.client_message_id ||
      task.id === pendingNode?.metadata.orchestration?.bridge_task_id,
  );
  const shouldKeepPendingAssistant =
    pendingNode !== undefined &&
    !pendingTaskForBrowserNode &&
    lastServerMessage?.role !== "assistant";

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
    const assistant = { ...pendingNode, parent_id: parentId, children_ids: [] };
    nodesById[parentId] = {
      ...nodesById[parentId],
      children_ids: [...nodesById[parentId].children_ids, assistant.id],
    };
    nodesById[assistant.id] = assistant;
    parentId = assistant.id;
  }

  for (const task of pendingTasks) {
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
      messageNodeIds.get(task.user_message_id) ?? clientMessageNodeIds.get(task.client_message_id);
    if (taskParentId === undefined || nodesById[`local-task:${task.id}:pending`] !== undefined) {
      continue;
    }
    const assistant: ConversationNode = {
      id: `local-task:${task.id}:pending`,
      parent_id: taskParentId,
      children_ids: [],
      role: "assistant",
      content: localAgentPendingTaskContent(task.status, connection?.status),
      state: "streaming",
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
      },
      tool_calls: [],
      artifacts: [],
      created_at: task.created_at,
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

function localAgentConversationId(bindingId: string): string {
  return `local-agent:${bindingId}`;
}

function localAgentPendingTaskContent(taskStatus: string, connectionStatus?: string): string {
  if (connectionStatus === "offline") {
    return "本地 Agent 当前离线，消息已排队。bridge 恢复后会继续处理。";
  }
  if (taskStatus === "running" || taskStatus === "leased") {
    return "本地 Agent 正在处理，完成后会同步到这里。";
  }
  return "等待本地 Agent 响应...";
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
