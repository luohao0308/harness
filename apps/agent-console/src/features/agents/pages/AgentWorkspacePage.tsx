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

import { useCallback, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { useI18n } from "../../../lib/i18n";
import {
  useWorkspaceStore,
  type ConversationArtifact,
  type ConversationNode,
} from "../../../stores/workspaceStore";
import {
  createTeam,
  getAgent,
  getAgentRunWorkspace,
  getModelSettings,
  getToolRegistry,
  listTeams,
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

  const agent = useQuery({ queryKey: ["agents", agentId], queryFn: () => getAgent(agentId) });
  const settings = useQuery({ queryKey: ["settings", "models"], queryFn: getModelSettings });
  const toolsQuery = useQuery({ queryKey: ["tools", "registry"], queryFn: getToolRegistry });
  const teamsQuery = useQuery({ queryKey: ["teams"], queryFn: listTeams });

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
        leader_name: agent.data?.name ?? "Leader",
        workspace_mode: "shared",
        seed_messages: buildTeamSeedMessagesFromPath(activePath, agentId),
      });
    },
    onSuccess: async (team) => {
      await queryClient.invalidateQueries({ queryKey: ["teams"] });
      navigate(`/teams/${team.id}`);
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

  const handleClearConversation = useCallback(() => {
    const message = text(
      "确定清空当前会话？此操作不可撤销。",
      "Clear the current conversation? This cannot be undone.",
    );
    if (!window.confirm(message)) return;
    // v3: clearing only resets the current conversation's runtime fields;
    // the conversations list itself is unchanged. Persistence subscribe
    // will write the empty state back to the active conversation.
    useWorkspaceStore.getState().reset();
  }, [text]);

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

  // v3 conversation history handlers
  const handleNewConversation = useCallback(() => {
    newConversation();
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
    (id: string) => {
      const current = useWorkspaceStore.getState().conversations.find((c) => c.id === id);
      const title = current?.title ?? "";
      const message = text(
        `确定删除对话"${title}"？此操作不可撤销。`,
        `Delete conversation "${title}"? This cannot be undone.`,
      );
      if (!window.confirm(message)) return;
      deleteConversation(id);
    },
    [deleteConversation, text],
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
      <div className="relative flex h-full min-h-[calc(100vh-3.5rem)] w-full min-w-0 bg-white">
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
