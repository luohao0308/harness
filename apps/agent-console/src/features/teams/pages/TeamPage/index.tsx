import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Loader2 } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";

import { ConsoleShell } from "../../../../app/ConsoleShell";
import { Button } from "../../../../components/ui/button";
import { Card } from "../../../../components/ui/card";
import { feedbackErrorMessage, notifyFeedback } from "../../../../components/ui/feedback-toast";
import { useConfirmDialog } from "../../../../components/ui/confirm-dialog";
import { useI18n } from "../../../../lib/i18n";
import type { ComposerAttachment } from "../../../agents/components/ChatComposer";
import type { ConversationNode } from "../../../../stores/workspaceStore";
import { InspectorDrawer } from "../../../agents/components/InspectorDrawer";
import { AUTO_COMPRESSION_RATIO_DEFAULT, CONTEXT_MAX_TOKENS_DEFAULT } from "../../../agents/lib/contextTokens";
import type { InspectorSection, WorkspaceMode } from "../../../agents/lib/types";
import {
  addTeamAgent,
  getTeam,
  getModelSettings,
  getToolRegistry,
  listAgentsPage,
  listTeams,
  renameTeamAgent,
  removeTeamAgent,
  updateTeamGoal,
  updateTeamAgent,
  type Team,
  type TeamAgent,
  type ToolMetadata,
} from "../../../tasks/api";
import { TeamRail, TeamRailMobileStrip } from "../../components/TeamRail";
import { TeamCreateModal } from "../TeamCreateModal";

import { TeamAgentTabs } from "./TeamAgentTabs";
import { TeamAddMemberModal } from "./TeamAddMemberModal";
import { TeamHeader } from "./TeamHeader";
import { TeamGoalEditorDialog } from "./TeamGoalEditorDialog";
import type { TeamWorkspaceView } from "./DesktopTeamViewSwitch";
import { TeamWorkspaceSurface } from "./TeamWorkspaceSurface";
import {
  activeAgent,
  deriveTeamModelOptions,
  orderedTeamAgents,
} from "./conversation";
import {
  applyTeamEventToTeam,
  mergeTeamAgent,
  normalizeSettledTeam,
} from "./teamState";
import type {
  ComposerState,
  PendingSend,
  SettledWakeCutoffs,
  StreamingWake,
  TeamBottomPanel,
  TeamBranchGroupsBySlot,
  TeamContextCompressions,
  TeamPageEnvelope,
  TeamModelChangeHandler,
} from "./types";
import { useTeamComposerActions } from "./useTeamComposerActions";
import { useTeamContextCompression } from "./useTeamContextCompression";
import { useTeamEventsAndWake } from "./useTeamEventsAndWake";

export { applyTeamEventToTeam } from "./teamState";

const TEAM_WORKSPACE_VIEWS = new Set<TeamWorkspaceView>(["collaboration", "graph", "columns"]);

function desktopTeamViewStorageKey(teamId: string) {
  return `harness-desktop-team-view-${teamId}`;
}

function initialTeamWorkspaceView(teamId: string, desktopEnabled: boolean): TeamWorkspaceView {
  if (!desktopEnabled || typeof window === "undefined") return "columns";
  try {
    const stored = window.localStorage.getItem(desktopTeamViewStorageKey(teamId)) as TeamWorkspaceView | null;
    return stored && TEAM_WORKSPACE_VIEWS.has(stored) ? stored : "collaboration";
  } catch {
    return "collaboration";
  }
}

export function TeamPage() {
  const { text } = useI18n();
  const { confirm, confirmDialog } = useConfirmDialog();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { teamId = "" } = useParams();
  const desktopTeamEnabled = typeof window !== "undefined" && "desktopApi" in window;
  const workspaceViewStorageKey =
    desktopTeamEnabled && teamId ? desktopTeamViewStorageKey(teamId) : null;
  const [workspaceViewState, setWorkspaceViewState] = useState(() => ({
    storageKey: workspaceViewStorageKey,
    view: initialTeamWorkspaceView(teamId, desktopTeamEnabled),
  }));
  const workspaceView =
    workspaceViewState.storageKey === workspaceViewStorageKey
      ? workspaceViewState.view
      : initialTeamWorkspaceView(teamId, desktopTeamEnabled);
  const [focusSlotId, setFocusSlotId] = useState<string | null>(null);
  const [focusPanel, setFocusPanel] = useState<"inspector" | "graph">("inspector");
  const setWorkspaceView = useCallback(
    (view: TeamWorkspaceView) => {
      setWorkspaceViewState({ storageKey: workspaceViewStorageKey, view });
      if (view !== "collaboration") {
        setFocusSlotId(null);
        setFocusPanel("inspector");
      }
    },
    [workspaceViewStorageKey],
  );
  const [activeSlotId, setActiveSlotId] = useState("leader");
  const [fullscreenSlotId, setFullscreenSlotId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [addMemberOpen, setAddMemberOpen] = useState(false);
  const [newMemberName, setNewMemberName] = useState("");
  const [newMemberAgentId, setNewMemberAgentId] = useState<string | null>(null);
  const [composerState, setComposerState] = useState<ComposerState>({});
  const [pendingSends, setPendingSends] = useState<PendingSend[]>([]);
  const [pendingWakeSlotIds, setPendingWakeSlotIds] = useState<string[]>([]);
  const [streamingWakes, setStreamingWakes] = useState<StreamingWake[]>([]);
  const [settledWakeCutoffs, setSettledWakeCutoffs] = useState<SettledWakeCutoffs>({});
  const [orderedSlotIds, setOrderedSlotIds] = useState<string[]>([]);
  const [editingSlotId, setEditingSlotId] = useState<string | null>(null);
  const [editingAgentName, setEditingAgentName] = useState("");
  const [dragSourceSlotId, setDragSourceSlotId] = useState<string | null>(null);
  const [dragOverSlotId, setDragOverSlotId] = useState<string | null>(null);
  const [flashingSlotId, setFlashingSlotId] = useState<string | null>(null);
  const [taskBoardOpen, setTaskBoardOpen] = useState(false);
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [pinnedMessageIds, setPinnedMessageIds] = useState<string[]>([]);
  const [attachmentsBySlotId, setAttachmentsBySlotId] = useState<Record<string, ComposerAttachment[]>>({});
  const [bottomPanelBySlotId, setBottomPanelBySlotId] = useState<Record<string, TeamBottomPanel>>({});
  const [contextMaxTokens, setContextMaxTokens] = useState(CONTEXT_MAX_TOKENS_DEFAULT);
  const [autoCompressionRatio, setAutoCompressionRatio] = useState(AUTO_COMPRESSION_RATIO_DEFAULT);
  const [contextCompressionsBySlotId, setContextCompressionsBySlotId] = useState<TeamContextCompressions>({});
  const [branchGroupsBySlotId, setBranchGroupsBySlotId] = useState<TeamBranchGroupsBySlot>({});
  const [teamInspector, setTeamInspector] = useState<{
    section: InspectorSection;
    node: ConversationNode;
  } | null>(null);
  const [isNarrowColumns, setIsNarrowColumns] = useState(false);
  const scrollRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const columnsContainerRef = useRef<HTMLDivElement | null>(null);
  const flashTimerRef = useRef<number | null>(null);
  const pendingSendKeysRef = useRef<Set<string>>(new Set());
  const teamFileInputsRef = useRef<Record<string, HTMLInputElement | null>>({});
  const [columnOverflow, setColumnOverflow] = useState({ left: false, right: false });
  const [goalEditorOpen, setGoalEditorOpen] = useState(false);
  const [goalDraft, setGoalDraft] = useState("");

  useEffect(() => {
    setWorkspaceViewState((current) => {
      if (current.storageKey === workspaceViewStorageKey) return current;
      return {
        storageKey: workspaceViewStorageKey,
        view: initialTeamWorkspaceView(teamId, desktopTeamEnabled),
      };
    });
  }, [desktopTeamEnabled, teamId, workspaceViewStorageKey]);

  useEffect(() => {
    if (!workspaceViewStorageKey || workspaceViewState.storageKey !== workspaceViewStorageKey) return;
    try {
      window.localStorage.setItem(workspaceViewStorageKey, workspaceViewState.view);
    } catch {
      // Desktop view persistence is best effort; Team state remains server-backed.
    }
  }, [workspaceViewState, workspaceViewStorageKey]);

  const teamQuery = useQuery({
    queryKey: ["teams", teamId],
    queryFn: () => getTeam(teamId),
    enabled: Boolean(teamId),
    refetchInterval: 4000,
  });
  const teamsQuery = useQuery({
    queryKey: ["teams"],
    queryFn: listTeams,
    refetchInterval: 8000,
  });
  const agentsQuery = useQuery({
    queryKey: ["agents"],
    queryFn: () => listAgentsPage({ limit: 100 }),
    enabled: addMemberOpen,
  });
  const streamReadyTeamId = teamQuery.data?.id;

  const team = useMemo(
    () => normalizeSettledTeam(teamQuery.data ?? null, settledWakeCutoffs),
    [settledWakeCutoffs, teamQuery.data],
  );
  const teams = teamsQuery.data?.items ?? [];
  const agents = useMemo(() => team?.agents ?? [], [team?.agents]);
  const toolAgentIds = useMemo(
    () => Array.from(new Set(agents.map((agent) => agent.agent_id).filter(Boolean))).sort(),
    [agents],
  );
  const settingsQuery = useQuery({ queryKey: ["settings", "models"], queryFn: getModelSettings });
  const toolsQuery = useQuery({
    queryKey: ["tools", "registry", "team", toolAgentIds],
    queryFn: async () =>
      Promise.all(
        toolAgentIds.map(async (agentId) => ({
          agentId,
          registry: await getToolRegistry(agentId),
        })),
      ),
    enabled: toolAgentIds.length > 0,
  });
  const agentDefinitions = agentsQuery.data?.items ?? [];
  const toolsByAgentId = useMemo(() => {
    const next = new Map<string, ToolMetadata[]>();
    for (const entry of toolsQuery.data ?? []) {
      next.set(entry.agentId, entry.registry.items);
    }
    return next;
  }, [toolsQuery.data]);
  const modelOptions = useMemo(() => deriveTeamModelOptions(settingsQuery.data), [settingsQuery.data]);
  const messages = team?.messages ?? [];
  const tasks = team?.tasks ?? [];
  const leader = agents.find((agent) => agent.role === "leader") ?? agents[0] ?? null;
  const selectedAgent = activeAgent(team ?? undefined, activeSlotId);
  const leaderSlotId = team?.leader_slot_id ?? leader?.slot_id ?? "leader";
  const activeTeam = team ?? teams.find((item) => item.id === teamId) ?? null;
  const orderStorageKey = teamId ? `harness-team-agent-order-${teamId}` : "";
  const orderedAgents = useMemo(() => orderedTeamAgents(agents, orderedSlotIds), [agents, orderedSlotIds]);
  const openTaskCount = tasks.filter((task) => task.status !== "completed" && task.status !== "deleted").length;
  const selectedNewMemberAgent =
    agentDefinitions.find((agent) => agent.id === newMemberAgentId) ?? agentDefinitions[0] ?? null;
  const addMemberError = agentsQuery.error instanceof Error ? agentsQuery.error.message : null;

  useEffect(() => {
    if (!leaderSlotId) return;
    setActiveSlotId((current) => (agents.some((agent) => agent.slot_id === current) ? current : leaderSlotId));
  }, [agents, leaderSlotId]);

  useEffect(() => {
    if (focusSlotId && !agents.some((agent) => agent.slot_id === focusSlotId)) {
      setFocusSlotId(null);
      setFocusPanel("inspector");
    }
  }, [agents, focusSlotId]);

  useEffect(() => {
    setGoalDraft(activeTeam?.active_goal?.objective ?? "");
  }, [activeTeam?.active_goal?.id, activeTeam?.active_goal?.objective]);

  useEffect(() => {
    if (!addMemberOpen || newMemberAgentId || agentDefinitions.length === 0) return;
    setNewMemberAgentId(agentDefinitions.find((agent) => agent.id === "default")?.id ?? agentDefinitions[0].id);
  }, [addMemberOpen, agentDefinitions, newMemberAgentId]);

  useEffect(() => {
    if (!orderStorageKey) return;
    try {
      const stored = window.localStorage.getItem(orderStorageKey);
      if (stored) {
        const parsed = JSON.parse(stored) as unknown;
        if (Array.isArray(parsed)) {
          setOrderedSlotIds(parsed.filter((value): value is string => typeof value === "string"));
        }
      }
    } catch {
      setOrderedSlotIds([]);
    }
  }, [orderStorageKey]);

  useEffect(() => {
    const teammateIds = agents.filter((agent) => agent.role !== "leader").map((agent) => agent.slot_id);
    setOrderedSlotIds((current) => {
      const next = current.filter((slotId) => teammateIds.includes(slotId));
      for (const slotId of teammateIds) {
        if (!next.includes(slotId)) next.push(slotId);
      }
      return next.join("\n") === current.join("\n") ? current : next;
    });
  }, [agents]);

  useEffect(() => {
    if (!orderStorageKey) return;
    window.localStorage.setItem(orderStorageKey, JSON.stringify(orderedSlotIds));
  }, [orderStorageKey, orderedSlotIds]);

  useEffect(() => {
    if (!activeSlotId) return;
    const node = scrollRefs.current[activeSlotId];
    if (node) {
      node.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "start" });
      if (flashTimerRef.current) {
        window.clearTimeout(flashTimerRef.current);
      }
      setFlashingSlotId(activeSlotId);
      flashTimerRef.current = window.setTimeout(() => {
        setFlashingSlotId((current) => (current === activeSlotId ? null : current));
        flashTimerRef.current = null;
      }, 320);
    }
  }, [activeSlotId]);

  useEffect(
    () => () => {
      if (flashTimerRef.current) {
        window.clearTimeout(flashTimerRef.current);
      }
    },
    [],
  );

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia(desktopTeamEnabled ? "(max-width: 1023px)" : "(max-width: 767px)");
    const apply = (): void => setIsNarrowColumns(query.matches);
    apply();
    query.addEventListener("change", apply);
    return () => query.removeEventListener("change", apply);
  }, [desktopTeamEnabled]);

  const updateColumnOverflow = useCallback(() => {
    const node = columnsContainerRef.current;
    if (!node) {
      setColumnOverflow({ left: false, right: false });
      return;
    }
    const hasOverflow = node.scrollWidth > node.clientWidth + 1;
    setColumnOverflow({
      left: hasOverflow && node.scrollLeft > 10,
      right: hasOverflow && node.scrollLeft + node.clientWidth < node.scrollWidth - 10,
    });
  }, []);

  const invalidateTeamQueries = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["teams", teamId] });
    await queryClient.invalidateQueries({ queryKey: ["teams"] });
  }, [queryClient, teamId]);

  const patchGoalStatus = useCallback(
    async (nextStatus: "active" | "paused") => {
      if (!activeTeam?.active_goal) return;
      try {
        await updateTeamGoal(activeTeam.id, activeTeam.active_goal.id, { status: nextStatus });
        await invalidateTeamQueries();
      } catch (error) {
        notifyFeedback({
          title: text("目标状态更新失败", "Failed to update goal status"),
          description: feedbackErrorMessage(error, text("请稍后重试。", "Please try again.")),
          tone: "error",
        });
      }
    },
    [activeTeam, invalidateTeamQueries, text],
  );

  const saveGoalObjective = useCallback(async () => {
    if (!activeTeam?.active_goal) return;
    const objective = goalDraft.trim();
    if (!objective) return;
    try {
      await updateTeamGoal(activeTeam.id, activeTeam.active_goal.id, { objective });
      setGoalEditorOpen(false);
      await invalidateTeamQueries();
    } catch (error) {
      notifyFeedback({
        title: text("目标编辑失败", "Failed to edit goal"),
        description: feedbackErrorMessage(error, text("请稍后重试。", "Please try again.")),
        tone: "error",
        });
      }
  }, [activeTeam, goalDraft, invalidateTeamQueries, text]);

  useEffect(() => {
    const node = columnsContainerRef.current;
    if (!node) return;
    node.addEventListener("scroll", updateColumnOverflow, { passive: true });
    window.addEventListener("resize", updateColumnOverflow);
    const observer =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(updateColumnOverflow);
    observer?.observe(node);
    requestAnimationFrame(updateColumnOverflow);
    return () => {
      node.removeEventListener("scroll", updateColumnOverflow);
      window.removeEventListener("resize", updateColumnOverflow);
      observer?.disconnect();
    };
  }, [agents.length, fullscreenSlotId, isNarrowColumns, updateColumnOverflow]);

  const scrollColumns = useCallback(
    (direction: "left" | "right") => {
      const node = columnsContainerRef.current;
      if (!node) return;
      node.scrollBy({ left: direction === "left" ? -420 : 420, behavior: "smooth" });
      window.setTimeout(updateColumnOverflow, 260);
    },
    [updateColumnOverflow],
  );

  const invalidateTeam = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["teams", teamId] });
  }, [queryClient, teamId]);

  const { triggerWake, stopWake } = useTeamEventsAndWake({
    teamId,
    streamReadyTeamId,
    setActiveSlotId,
    setSettledWakeCutoffs,
    setPendingWakeSlotIds,
    setStreamingWakes,
  });

  const renameAgentMutation = useMutation({
    mutationFn: (payload: { slotId: string; agentName: string }) =>
      renameTeamAgent(teamId, payload.slotId, payload.agentName),
    onSuccess: async (_agent, payload) => {
      setEditingSlotId(null);
      setEditingAgentName("");
      notifyFeedback({
        tone: "success",
        title: "成员名称已更新",
        description: `已将团队成员更新为 ${payload.agentName}。`,
      });
      await queryClient.invalidateQueries({ queryKey: ["teams", teamId] });
      await queryClient.invalidateQueries({ queryKey: ["teams"] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: "成员名称更新失败",
        description: feedbackErrorMessage(error, "请检查成员名称是否为空，或稍后重试。"),
      });
    },
  });

  const updateAgentMutation = useMutation({
    mutationFn: (payload: { slotId: string; modelProvider: string; modelName: string }) =>
      updateTeamAgent(teamId, payload.slotId, {
        model_provider: payload.modelProvider,
        model_name: payload.modelName,
      }),
    onSuccess: async (agent) => {
      setComposerBottomPanel(agent.slot_id, null);
      notifyFeedback({
        tone: "success",
        title: "成员模型已切换",
        description: `${agent.agent_name} 现在使用 ${agent.model_provider}/${agent.model_name}。`,
      });
      queryClient.setQueryData<Team>(["teams", teamId], (current) =>
        current ? { ...current, agents: mergeTeamAgent(current.agents, agent) } : current,
      );
      await queryClient.invalidateQueries({ queryKey: ["teams", teamId] });
      await queryClient.invalidateQueries({ queryKey: ["teams"] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: "成员模型切换失败",
        description: feedbackErrorMessage(error, "请检查模型配置或稍后重试。"),
      });
    },
  });

  const removeAgentMutation = useMutation({
    mutationFn: (slotId: string) => removeTeamAgent(teamId, slotId),
    onSuccess: async (_agent, slotId) => {
      setFullscreenSlotId((current) => (current === slotId ? null : current));
      setActiveSlotId((current) => (current === slotId ? leaderSlotId : current));
      notifyFeedback({
        tone: "warning",
        title: "团队成员已移除",
        description: "该成员已从当前团队中移除。",
      });
      await queryClient.invalidateQueries({ queryKey: ["teams", teamId] });
      await queryClient.invalidateQueries({ queryKey: ["teams"] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: "移除团队成员失败",
        description: feedbackErrorMessage(error, "请检查该成员是否仍在运行，或稍后重试。"),
      });
    },
  });

  const confirmRemoveAgent = useCallback(
    async (agentName: string, status: string) => {
      if (status !== "active") return true;
      return confirm({
        title: "移除团队成员",
        description: `成员 ${agentName} 当前仍在运行中。移除后会中断该成员的当前团队协作。`,
        confirmText: "确认移除",
        variant: "danger",
      });
    },
    [confirm],
  );

  const addAgentMutation = useMutation({
    mutationFn: (payload: { agentId: string; agentName: string }) =>
      addTeamAgent(teamId, {
        agent_id: payload.agentId,
        agent_name: payload.agentName,
        role: "teammate",
      }),
    onSuccess: async (agent) => {
      setAddMemberOpen(false);
      setNewMemberName("");
      setNewMemberAgentId(null);
      setActiveSlotId(agent.slot_id);
      queryClient.setQueryData<Team>(["teams", teamId], (current) =>
        current ? { ...current, agents: mergeTeamAgent(current.agents, agent) } : current,
      );
      queryClient.setQueryData<TeamPageEnvelope>(["teams"], (current) =>
        current
          ? {
              ...current,
              items: current.items.map((item) =>
                item.id === teamId
                  ? { ...item, agents: mergeTeamAgent(item.agents, agent) }
                  : item,
              ),
            }
          : current,
      );
      notifyFeedback({
        tone: "success",
        title: "团队成员已添加",
        description: `${agent.agent_name} 已加入当前团队。`,
      });
      await queryClient.invalidateQueries({ queryKey: ["teams", teamId] });
      await queryClient.invalidateQueries({ queryKey: ["teams"] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: "团队成员添加失败",
        description: feedbackErrorMessage(error, "请检查成员名称、智能体定义或稍后重试。"),
      });
    },
  });

  const selectedComposer = composerState[activeSlotId] ?? {
    draft: "",
  };

  const {
    clearTeamContextCompression,
    compressTeamContext,
  } = useTeamContextCompression({
    team,
    contextCompressionsBySlotId,
    modelOptions,
    pinnedMessageIds,
    setContextCompressionsBySlotId,
    text,
  });

  const {
    addComposerFiles,
    branchFromAssistant,
    handleComposerFilesSelected,
    removeComposerAttachment,
    sendFromComposer,
    sendFromMessageAction,
    setComposerBottomPanel,
    switchTeamBranch,
    syncBranchGroups,
    updateComposer,
  } = useTeamComposerActions({
    teamId,
    activeTeam,
    agents,
    messages,
    pendingSends,
    pendingWakeSlotIds,
    streamingWakes,
    settledWakeCutoffs,
    pendingSendKeysRef,
    teamFileInputsRef,
    setComposerState,
    setPendingSends,
    setStreamingWakes,
    setAttachmentsBySlotId,
    setBottomPanelBySlotId,
    setBranchGroupsBySlotId,
    triggerWake,
    invalidateTeam,
    text,
  });

  useEffect(() => {
    syncBranchGroups(team);
  }, [syncBranchGroups, team]);

  const handleTeamModelChange = useCallback<TeamModelChangeHandler>(
    (slotId, providerId, modelId) => {
      updateAgentMutation.mutate({ slotId, modelProvider: providerId, modelName: modelId });
    },
    [updateAgentMutation],
  );

  const submitNewMember = useCallback(() => {
    if (!selectedNewMemberAgent) return;
    const trimmed = newMemberName.trim();
    addAgentMutation.mutate({
      agentId: selectedNewMemberAgent.id,
      agentName: trimmed || selectedNewMemberAgent.name,
    });
  }, [addAgentMutation, newMemberName, selectedNewMemberAgent]);

  const togglePinnedMessage = useCallback((nodeId: string) => {
    setPinnedMessageIds((current) =>
      current.includes(nodeId)
        ? current.filter((candidate) => candidate !== nodeId)
        : [...current, nodeId],
    );
  }, []);

  const startEditingAgent = useCallback((agent: TeamAgent) => {
    setEditingSlotId(agent.slot_id);
    setEditingAgentName(agent.agent_name);
  }, []);

  const commitEditingAgent = useCallback(() => {
    if (!editingSlotId) return;
    const trimmed = editingAgentName.trim();
    const current = agents.find((agent) => agent.slot_id === editingSlotId);
    if (!trimmed || trimmed === current?.agent_name) {
      setEditingSlotId(null);
      setEditingAgentName("");
      return;
    }
    renameAgentMutation.mutate({ slotId: editingSlotId, agentName: trimmed });
  }, [agents, editingAgentName, editingSlotId, renameAgentMutation]);

  const dropAgentTab = useCallback(
    (targetSlotId: string) => {
      if (!dragSourceSlotId || dragSourceSlotId === targetSlotId) {
        setDragSourceSlotId(null);
        setDragOverSlotId(null);
        return;
      }
      const targetAgent = agents.find((agent) => agent.slot_id === targetSlotId);
      if (!targetAgent || targetAgent.role === "leader") {
        setDragSourceSlotId(null);
        setDragOverSlotId(null);
        return;
      }
      setOrderedSlotIds((current) => {
        const teammateIds = agents.filter((agent) => agent.role !== "leader").map((agent) => agent.slot_id);
        const next = current.filter((slotId) => teammateIds.includes(slotId));
        for (const slotId of teammateIds) {
          if (!next.includes(slotId)) next.push(slotId);
        }
        const fromIndex = next.indexOf(dragSourceSlotId);
        const toIndex = next.indexOf(targetSlotId);
        if (fromIndex === -1 || toIndex === -1) return current;
        const [moved] = next.splice(fromIndex, 1);
        next.splice(toIndex, 0, moved);
        return next;
      });
      setActiveSlotId(dragSourceSlotId);
      setDragSourceSlotId(null);
      setDragOverSlotId(null);
    },
    [agents, dragSourceSlotId],
  );

  const composerSharedProps = useMemo(
    () => ({
      modelOptions,
      contextMaxTokens,
      autoCompressionRatio,
      onContextMaxTokensChange: setContextMaxTokens,
      onAutoCompressionRatioChange: setAutoCompressionRatio,
      onClearContextCompression: clearTeamContextCompression,
      addComposerFiles,
      handleComposerFilesSelected,
      removeComposerAttachment,
      setComposerBottomPanel,
      onModelChange: handleTeamModelChange,
    }),
    [
      addComposerFiles,
      autoCompressionRatio,
      contextMaxTokens,
      clearTeamContextCompression,
      handleComposerFilesSelected,
      handleTeamModelChange,
      modelOptions,
      removeComposerAttachment,
      setComposerBottomPanel,
    ],
  );

  if (teamQuery.isLoading && !team) {
    return (
      <ConsoleShell title={text("团队", "Teams")}>
        <div className="flex min-h-full items-center justify-center text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin" />
        </div>
      </ConsoleShell>
    );
  }

  if (!activeTeam) {
    return (
      <ConsoleShell title={text("团队", "Teams")}>
        <div className="flex min-h-full items-center justify-center">
          <Card className="p-6 text-center">
            <div className="text-sm font-semibold text-slate-900">{text("团队不存在", "Team not found")}</div>
            <Button className="mt-4" onClick={() => navigate("/teams")}>
              <ArrowLeft className="h-3.5 w-3.5" />
              {text("返回团队列表", "Back to teams")}
            </Button>
          </Card>
        </div>
      </ConsoleShell>
    );
  }

  return (
    <ConsoleShell title={activeTeam.name}>
      <div className="flex h-[100vh] min-h-0 overflow-hidden bg-white">
        <TeamRail teams={teams} activeTeamId={teamId} onCreate={() => setCreateOpen(true)} />

        <main className="flex min-w-0 flex-1 flex-col">
          <TeamRailMobileStrip teams={teams} activeTeamId={teamId} />
          <TeamHeader
            activeTeam={activeTeam}
            agents={agents}
            orderedAgents={orderedAgents}
            tasks={tasks}
            openTaskCount={openTaskCount}
            taskBoardOpen={taskBoardOpen}
            text={text}
            onAddMember={() => setAddMemberOpen(true)}
            onToggleTaskBoard={() => setTaskBoardOpen((open) => !open)}
            onCloseTaskBoard={() => setTaskBoardOpen(false)}
            onPauseGoal={() => void patchGoalStatus("paused")}
            onResumeGoal={() => void patchGoalStatus("active")}
            onEditGoal={() => setGoalEditorOpen(true)}
            workspaceView={desktopTeamEnabled ? workspaceView : undefined}
            onWorkspaceViewChange={desktopTeamEnabled ? setWorkspaceView : undefined}
          />

          {!desktopTeamEnabled || workspaceView === "columns" || focusSlotId !== null ? (
            <TeamAgentTabs
              activeTeam={activeTeam}
              orderedAgents={orderedAgents}
              tasks={tasks}
              activeSlotId={activeSlotId}
              editingSlotId={editingSlotId}
              editingAgentName={editingAgentName}
              dragSourceSlotId={dragSourceSlotId}
              dragOverSlotId={dragOverSlotId}
              pendingWakeSlotIds={pendingWakeSlotIds}
              streamingWakes={streamingWakes}
              settledWakeCutoffs={settledWakeCutoffs}
              text={text}
              onActiveSlotChange={setActiveSlotId}
              onStartEditingAgent={startEditingAgent}
              onEditingAgentNameChange={setEditingAgentName}
              onCommitEditingAgent={commitEditingAgent}
              onCancelEditingAgent={() => {
                setEditingSlotId(null);
                setEditingAgentName("");
              }}
              onDragSourceChange={setDragSourceSlotId}
              onDragOverChange={setDragOverSlotId}
              onDropAgentTab={dropAgentTab}
            />
          ) : null}

          <TeamWorkspaceSurface
            desktopEnabled={desktopTeamEnabled}
            view={workspaceView}
            activeSlotId={activeSlotId}
            focusSlotId={focusSlotId}
            onSelectAgent={setActiveSlotId}
            onEnterFocus={setFocusSlotId}
            onExitFocus={() => {
              setFocusSlotId(null);
              setFocusPanel("inspector");
            }}
            focusPanel={focusPanel}
            onFocusPanelChange={setFocusPanel}
            columnListProps={{
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
              onCompressContext: compressTeamContext,
              onComposerChange: updateComposer,
              onSendFromComposer: sendFromComposer,
              onMessageActionSend: sendFromMessageAction,
              onBranchMessage: branchFromAssistant,
              onSwitchBranch: switchTeamBranch,
              onStartMessageEdit: setEditingMessageId,
              onCancelMessageEdit: () => setEditingMessageId(null),
              onTogglePin: togglePinnedMessage,
              onOpenMessageInspector: (section, node) => setTeamInspector({ section, node }),
              onStopWake: stopWake,
              onToggleFullscreen: (slotId) =>
                setFullscreenSlotId((current) => (current === slotId ? null : slotId)),
              onRemoveAgent: async (agent) => {
                if (agent.role === "leader") return;
                if (!(await confirmRemoveAgent(agent.agent_name, agent.status))) return;
                removeAgentMutation.mutate(agent.slot_id);
              },
              onFocusAgent: setActiveSlotId,
              onScrollColumns: scrollColumns,
            }}
          />
        </main>
      </div>
      <TeamCreateModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(team) => navigate(`/teams/${team.id}`)}
      />
      <TeamAddMemberModal
        open={addMemberOpen}
        agents={agentDefinitions}
        selectedAgentId={selectedNewMemberAgent?.id ?? newMemberAgentId ?? ""}
        memberName={newMemberName}
        loading={agentsQuery.isLoading}
        errorMessage={addMemberError ?? (addAgentMutation.error instanceof Error ? addAgentMutation.error.message : null)}
        submitting={addAgentMutation.isPending}
        text={text}
        onClose={() => {
          setAddMemberOpen(false);
          setNewMemberName("");
          setNewMemberAgentId(null);
        }}
        onAgentChange={setNewMemberAgentId}
        onMemberNameChange={setNewMemberName}
        onSubmit={submitNewMember}
      />
      <InspectorDrawer
        section={teamInspector?.section ?? null}
        activeRunId={teamInspector?.node.run_id ?? null}
        pendingApprovalCount={0}
        artifacts={teamInspector?.node.artifacts ?? []}
        onClose={() => setTeamInspector(null)}
      />
      {confirmDialog}
      {activeTeam?.active_goal ? (
        <TeamGoalEditorDialog
          open={goalEditorOpen}
          objective={goalDraft}
          text={text}
          onClose={() => setGoalEditorOpen(false)}
          onObjectiveChange={setGoalDraft}
          onSave={() => void saveGoalObjective()}
        />
      ) : null}
    </ConsoleShell>
  );
}
