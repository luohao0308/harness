import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  Brain,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Copy,
  Database,
  GitBranch,
  PackagePlus,
  Gauge,
  Monitor,
  PlugZap,
  RefreshCw,
  ScrollText,
  Settings,
  Shield,
  Terminal,
  Wrench,
} from "lucide-react";
import { Link } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, statusTone, type BadgeTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { ConfigDialog } from "../../../components/ui/config-dialog";
import { feedbackErrorMessage, notifyFeedback } from "../../../components/ui/feedback-toast";
import { Input, Textarea } from "../../../components/ui/input";
import { Card, CardHeader } from "../../../components/ui/card";
import { MenuSelect } from "../../../components/ui/menu-select";
import { RefreshOverlay } from "../../../components/ui/refresh-overlay";
import { cn } from "../../../lib/utils";
import { useI18n } from "../../../lib/i18n";
import { statusLabel } from "../../../lib/labels";
import {
  attachAgentCapability,
  cloneAgentDefinition,
  createAgentDefinition,
  createLocalAgentPairingToken,
  listTokenOptimizerPresets,
  listAgentKnowledgeSources,
  listLocalAgentConnections,
  listAgents,
  revokeLocalAgentConnection,
  revokeLocalAgentPairingToken,
  selectAgentTokenOptimizer,
  updateLocalAgentConnection,
  type AgentCapabilityAttachmentSummary,
  type AgentDefinition,
  type KnowledgeSource,
  type LocalAgentConnection,
  type LocalAgentConnectionPage,
  type LocalAgentPairing,
  type TokenOptimizerPresetId,
} from "../../tasks/api";
import { KnowledgeManagementPanel } from "../components/KnowledgeManagementPanel";
import { AgentReadinessRing } from "../components/AgentReadinessRing";
import { CollapsibleCapabilitySection } from "../components/CollapsibleCapabilitySection";
import { copyText } from "../lib/clipboard";

export function AgentListPage() {
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const [selectedAgentId, setSelectedAgentId] = useState("default");
  const [draftAgentId, setDraftAgentId] = useState("research-agent");
  const [draftAgentName, setDraftAgentName] = useState(text("研究智能体", "Research Agent"));
  const [draftSystemPrompt, setDraftSystemPrompt] = useState("Answer with grounded evidence and cite run details.");
  const [tokenBudget, setTokenBudget] = useState(4096);
  const [capabilityName, setCapabilityName] = useState("mcp_context_search");
  const [capabilityKind, setCapabilityKind] = useState("mcp_server");
  const [templateDialogOpen, setTemplateDialogOpen] = useState(false);
  const [capabilityDialogOpen, setCapabilityDialogOpen] = useState(false);
  const [localAgentDialogOpen, setLocalAgentDialogOpen] = useState(false);
  const [tokenOptimizerDialogOpen, setTokenOptimizerDialogOpen] = useState(false);
  const [localAgentPairing, setLocalAgentPairing] = useState<LocalAgentPairing | null>(null);
  const [pairCommandCopied, setPairCommandCopied] = useState(false);
  const [selectedLocalConnectionIds, setSelectedLocalConnectionIds] = useState<string[]>([]);
  const [seenLocalConnectionIds, setSeenLocalConnectionIds] = useState<string[]>([]);
  const [localConnectionNames, setLocalConnectionNames] = useState<Record<string, string>>({});
  const [localDiscoveryManualRefreshing, setLocalDiscoveryManualRefreshing] = useState(false);
  const [isKnowledgeExpanded, setIsKnowledgeExpanded] = useState(true);
  const selectedKnowledgeSources = useQuery({
    queryKey: ["agent-knowledge", selectedAgentId],
    queryFn: () => listAgentKnowledgeSources(selectedAgentId),
  });
  const agentKnowledgeReadinessQueries = useQueries({
    queries: (agents.data?.items ?? []).map((agent) => ({
      queryKey: ["agent-knowledge", agent.id],
      queryFn: () => listAgentKnowledgeSources(agent.id),
    })),
  });
  const localAgentConnections = useQuery({
    queryKey: ["local-agent-connections"],
    queryFn: listLocalAgentConnections,
    refetchInterval: localAgentDialogOpen ? 3000 : false,
  });
  const tokenOptimizerPresets = useQuery({
    queryKey: ["token-optimizer-presets"],
    queryFn: listTokenOptimizerPresets,
  });
  const createAgentMutation = useMutation({
    mutationFn: () =>
      createAgentDefinition({
        id: draftAgentId,
        name: draftAgentName,
        description: "Created from Agent Studio readiness flow",
        role: "researcher",
        model_provider: "default",
        model_name: "default",
        system_prompt: draftSystemPrompt,
        tools_json: [capabilityName],
        routing_tags: ["workspace", "multi-agent"],
        max_parallel_assignments: 2,
        token_budget: tokenBudget,
        template_id: "research-template",
      }),
    onSuccess: async () => {
      setTemplateDialogOpen(false);
      notifyFeedback({
        tone: "success",
        title: text("智能体创建成功", "Agent created"),
        description: text(`已创建 ${draftAgentName}，现在可以继续配置能力和知识源。`, `${draftAgentName} is ready for capabilities and knowledge sources.`),
      });
      await queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("智能体创建失败", "Agent creation failed"),
        description: feedbackErrorMessage(error, text("请检查智能体 ID、名称和当前后端状态。", "Check the Agent ID, name, and backend status.")),
      });
    },
  });
  const cloneAgentMutation = useMutation({
    mutationFn: () =>
      cloneAgentDefinition({
        source_agent_id: selectedAgentId,
        id: `${selectedAgentId}-clone`,
        name: `${selectedAgentLabel} 克隆副本`,
      }),
    onSuccess: async () => {
      setTemplateDialogOpen(false);
      notifyFeedback({
        tone: "success",
        title: text("智能体克隆成功", "Agent cloned"),
        description: text(`已基于 ${selectedAgentLabel} 创建克隆副本。`, `A clone of ${selectedAgentLabel} is ready.`),
      });
      await queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("智能体克隆失败", "Agent clone failed"),
        description: feedbackErrorMessage(error, text("请检查当前智能体选择和克隆参数。", "Check the selected Agent and clone request.")),
      });
    },
  });
  const attachCapabilityMutation = useMutation({
    mutationFn: () =>
      attachAgentCapability(selectedAgentId, {
        capability_id: capabilityName,
        capability_version_id: null,
        enabled: true,
        priority: 10,
      }),
    onSuccess: async () => {
      setCapabilityDialogOpen(false);
      notifyFeedback({
        tone: "success",
        title: text("能力附件已保存", "Capability attached"),
        description: text(`已将 ${capabilityName} 附加到 ${selectedAgentLabel}。`, `${capabilityName} is now attached to ${selectedAgentLabel}.`),
      });
      await queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("能力附件保存失败", "Capability attach failed"),
        description: feedbackErrorMessage(error, text("请检查能力名称、类型和智能体权限。", "Check the capability name, type, and Agent permissions.")),
      });
    },
  });
  const selectTokenOptimizerMutation = useMutation({
    mutationFn: (presetId: TokenOptimizerPresetId) =>
      selectAgentTokenOptimizer(selectedAgentId, presetId),
    onSuccess: async (_result, presetId) => {
      const selectedPreset = tokenOptimizerPresets.data?.items.find((preset) => preset.preset_id === presetId);
      notifyFeedback({
        tone: "success",
        title: text("Token 方案已切换", "Token plan updated"),
        description: text(
          `当前智能体已切换到 ${selectedPreset?.display_name ?? presetId}。`,
          `${selectedPreset?.display_name ?? presetId} is now active for this Agent.`,
        ),
      });
      await queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("Token 方案切换失败", "Token plan update failed"),
        description: feedbackErrorMessage(error, text("请稍后重试，或检查当前智能体是否可写。", "Please retry or verify the current Agent can be updated.")),
      });
    },
  });
  const createLocalAgentPairingMutation = useMutation({
    mutationFn: () => createLocalAgentPairingToken(selectedAgentId),
    onSuccess: (pairing) => {
      setLocalAgentPairing(pairing);
      setPairCommandCopied(false);
      setSelectedLocalConnectionIds([]);
      setSeenLocalConnectionIds([]);
      setLocalConnectionNames({});
      notifyFeedback({
        tone: "success",
        title: text("连接命令已生成", "Connection command generated"),
        description: text("请在本地终端执行命令，执行后会自动出现在识别列表。", "Run it in a local terminal; the connection will appear in discovery."),
      });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("连接命令生成失败", "Pairing command failed"),
        description: feedbackErrorMessage(error, text("请检查当前智能体和权限。", "Check the selected Agent and permissions.")),
      });
    },
  });
  const updateLocalAgentConnectionMutation = useMutation({
    mutationFn: async (payload: {
      detectedConnections: LocalAgentConnection[];
      selectedConnections: LocalAgentConnection[];
      pairingTokenId: string | null;
    }) => {
      if (payload.pairingTokenId) {
        await revokeLocalAgentPairingToken(payload.pairingTokenId);
      }
      const latestConnections = await listLocalAgentConnections();
      const payloadDetectedIds = new Set(payload.detectedConnections.map((connection) => connection.id));
      const payloadSelectedIds = new Set(payload.selectedConnections.map((connection) => connection.id));
      const latestDetectedConnections = latestConnections.items.filter(
        (connection) =>
          connection.agent_id === selectedAgentId &&
          localAgentIsUserFacing(connection) &&
          (
            payloadDetectedIds.has(connection.id) ||
            payloadSelectedIds.has(connection.id) ||
            (payload.pairingTokenId !== null && connection.pairing_token_id === payload.pairingTokenId)
          ),
      );
      const detectedConnectionMap = new Map<string, LocalAgentConnection>();
      for (const connection of [...payload.detectedConnections, ...latestDetectedConnections]) {
        detectedConnectionMap.set(connection.id, connection);
      }
      const detectedConnections = Array.from(detectedConnectionMap.values());
      const selectedConnectionMap = new Map<string, LocalAgentConnection>();
      for (const connection of payload.selectedConnections) {
        selectedConnectionMap.set(connection.id, connection);
      }
      for (const connection of latestDetectedConnections) {
        if (selectedConnectionMap.has(connection.id)) {
          selectedConnectionMap.set(connection.id, connection);
        }
      }
      const saveableConnections = Array.from(selectedConnectionMap.values()).filter(localAgentIsUserFacing);
      const selectedConnectionIds = new Set(saveableConnections.map((connection) => connection.id));
      const unselectedConnections = detectedConnections.filter(
        (connection) => localAgentIsUserFacing(connection) && !selectedConnectionIds.has(connection.id),
      );
      await Promise.all(
        [
          ...saveableConnections.map((connection) =>
            updateLocalAgentConnection(connection.id, {
              display_name: (localConnectionNames[connection.id] ?? connection.display_name).trim(),
            }),
          ),
          ...unselectedConnections.map((connection) => revokeLocalAgentConnection(connection.id)),
        ],
      );
      return {
        selectedConnectionCount: saveableConnections.length,
        revokedConnectionIds: unselectedConnections.map((connection) => connection.id),
      };
    },
    onSuccess: async ({ selectedConnectionCount, revokedConnectionIds }) => {
      if (revokedConnectionIds.length > 0) {
        setSelectedLocalConnectionIds((current) =>
          current.filter((id) => !revokedConnectionIds.includes(id)),
        );
        setSeenLocalConnectionIds((current) =>
          current.filter((id) => !revokedConnectionIds.includes(id)),
        );
        setLocalConnectionNames((current) => {
          let changed = false;
          const next = { ...current };
          for (const id of revokedConnectionIds) {
            if (id in next) {
              delete next[id];
              changed = true;
            }
          }
          return changed ? next : current;
        });
      queryClient.setQueryData<LocalAgentConnectionPage>(["local-agent-connections"], (page) =>
        page
          ? {
              ...page,
              items: page.items.map((connection) =>
                revokedConnectionIds.includes(connection.id)
                  ? {
                      ...connection,
                      status: "revoked",
                      revoked_at: connection.revoked_at ?? new Date().toISOString(),
                      onboarding_confirmed: false,
                    }
                  : connection,
              ),
            }
            : page,
        );
      }
      notifyFeedback({
        tone: "success",
        title:
          selectedConnectionCount > 0
            ? text("本地 Agent 已接入", "Local Agents connected")
            : text("未接入本地 Agent", "No local Agents connected"),
        description:
          selectedConnectionCount > 0
            ? text("已接入勾选的本地 Agent，未勾选的连接已断开。", "Selected local Agents are connected; unselected connections were disconnected.")
            : text("已断开所有未勾选的本地 Agent。", "All unchecked local Agent connections were disconnected."),
      });
      setLocalAgentPairing(null);
      setPairCommandCopied(false);
      setLocalAgentDialogOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["local-agent-connections"] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("接入保存失败", "Connection save failed"),
        description: feedbackErrorMessage(error, text("请检查连接是否仍然在线，或刷新识别列表后重试。", "Check whether the connection is still online, or refresh discovery and retry.")),
      });
    },
  });
  const revokeLocalAgentConnectionMutation = useMutation({
    mutationFn: (connectionId: string) => revokeLocalAgentConnection(connectionId),
    onSuccess: async (revokedConnection, connectionId) => {
      setSelectedLocalConnectionIds((current) => current.filter((id) => id !== connectionId));
      setSeenLocalConnectionIds((current) => current.filter((id) => id !== connectionId));
      setLocalConnectionNames((current) => {
        if (!(connectionId in current)) return current;
        const next = { ...current };
        delete next[connectionId];
        return next;
      });
      queryClient.setQueryData<LocalAgentConnectionPage>(["local-agent-connections"], (page) =>
        page
          ? {
              ...page,
              items: page.items.map((connection) =>
                connection.id === connectionId ? revokedConnection : connection,
              ),
            }
          : page,
      );
      notifyFeedback({
        tone: "success",
        title: text("本地 Agent 已撤销", "Local Agent revoked"),
        description: text("该设备不能继续拉取新任务。", "This device can no longer pull new tasks."),
      });
      await queryClient.invalidateQueries({ queryKey: ["local-agent-connections"] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("撤销失败", "Revoke failed"),
        description: feedbackErrorMessage(error, text("请检查设备状态和权限。", "Check device status and permissions.")),
      });
    },
  });
  const selectedAgent = useMemo(
    () => agents.data?.items.find((agent) => agent.id === selectedAgentId) ?? null,
    [agents.data?.items, selectedAgentId],
  );
  const selectedAgentLabel =
    selectedAgent?.id === "default"
      ? text("默认智能体", "Default Agent")
      : selectedAgent?.name ?? text("默认智能体", "Default Agent");
  const selectedAgentSummary = selectedAgent
    ? selectedAgent.id === "default"
      ? text("默认入口智能体", "Default entry agent")
      : selectedAgent.description
    : text("默认入口智能体", "Default entry agent");
  const activeKnowledgeSources = selectedKnowledgeSources.data?.items.filter(isReadyKnowledgeSource) ?? [];
  const knowledgeConnectorReady = activeKnowledgeSources.length > 0;
  const selectedOptimizerAttachments =
    selectedAgent?.capability_attachments?.filter((attachment) => attachment.capability_type === "context_optimizer") ?? [];
  const enabledOptimizerCount = selectedOptimizerAttachments.filter((attachment) => attachment.enabled).length;
  const activeTokenOptimizerPresetId = tokenOptimizerPresetIdFromAttachments(selectedOptimizerAttachments);
  const activeTokenOptimizerPreset =
    tokenOptimizerPresets.data?.items.find((preset) => preset.preset_id === activeTokenOptimizerPresetId) ?? null;
  const tokenOptimizerStatusLabel =
    activeTokenOptimizerPreset?.display_name ??
    (activeTokenOptimizerPresetId === "custom"
      ? text("自定义", "Custom")
      : text("关闭", "Off"));
  const knowledgeConnectorDetail = selectedKnowledgeSources.isLoading
    ? text("正在读取知识源", "Loading knowledge sources")
    : knowledgeConnectorReady
      ? text(`${activeKnowledgeSources.length} 个已索引知识源`, `${activeKnowledgeSources.length} indexed source(s)`)
      : text("没有已索引知识源", "No indexed knowledge source");
  const selectedLocalAgentConnections = useMemo(
    () =>
      sortLocalAgentConnections(
        localAgentConnections.data?.items.filter((connection) => connection.agent_id === selectedAgentId) ?? [],
      ),
    [localAgentConnections.data?.items, selectedAgentId],
  );
  const detectedLocalAgentConnections = useMemo(
    () =>
      selectedLocalAgentConnections.filter(localAgentIsUserFacing),
    [selectedLocalAgentConnections],
  );
  const selectedDetectedLocalConnections = detectedLocalAgentConnections.filter((connection) =>
    selectedLocalConnectionIds.includes(connection.id),
  );
  const selectedDetectedLocalConnectionNamesValid = selectedDetectedLocalConnections.every(
    (connection) => (localConnectionNames[connection.id] ?? connection.display_name).trim().length > 0,
  );
  const userFacingLocalAgentConnections = selectedLocalAgentConnections.filter(localAgentIsConfirmedUserFacing);
  const activeLocalAgentCount = userFacingLocalAgentConnections.length;
  const onlineLocalAgentCount = userFacingLocalAgentConnections.filter((connection) => connection.status === "online" || connection.status === "busy").length;
  const readyKnowledgeCountForAgent = (agentId: string, index: number) => {
    const sources =
      agentId === selectedAgentId
        ? selectedKnowledgeSources.data?.items
        : agentKnowledgeReadinessQueries[index]?.data?.items;
    return sources?.filter(isReadyKnowledgeSource).length ?? 0;
  };
  const activeLocalAgentCountForAgent = (agentId: string) =>
    localAgentConnections.data?.items.filter(
      (connection) => connection.agent_id === agentId && localAgentIsConfirmedUserFacing(connection),
    ).length ?? 0;

  useEffect(() => {
    if (
      agents.data?.items.length &&
      !agents.data.items.some((agent) => agent.id === selectedAgentId)
    ) {
      setSelectedAgentId(agents.data.items[0].id);
    }
  }, [agents.data?.items, selectedAgentId]);

  useEffect(() => {
    setSelectedLocalConnectionIds([]);
    setSeenLocalConnectionIds([]);
    setLocalConnectionNames({});
    setLocalAgentPairing(null);
    setPairCommandCopied(false);
  }, [selectedAgentId]);

  useEffect(() => {
    if (!localAgentDialogOpen) return;
    setSelectedLocalConnectionIds([]);
    setSeenLocalConnectionIds([]);
    setLocalConnectionNames({});
  }, [localAgentDialogOpen]);

  useEffect(() => {
    if (!localAgentDialogOpen) return;
    const detectedIds = detectedLocalAgentConnections.map((connection) => connection.id);
    const detectedIdSet = new Set(detectedIds);
    const unseenDetectedIds = detectedIds.filter((id) => !seenLocalConnectionIds.includes(id));
    if (unseenDetectedIds.length > 0) {
      setSeenLocalConnectionIds((current) => Array.from(new Set([...current, ...unseenDetectedIds])));
    }
    setSelectedLocalConnectionIds((current) => {
      const nextSelected = new Set(current.filter((id) => detectedIdSet.has(id)));
      const next = detectedIds.filter((id) => nextSelected.has(id));
      return sameStringArray(current, next) ? current : next;
    });
    setLocalConnectionNames((current) => {
      let changed = false;
      const next: Record<string, string> = {};
      for (const connection of detectedLocalAgentConnections) {
        next[connection.id] = current[connection.id] ?? connection.display_name;
        if (next[connection.id] !== current[connection.id]) changed = true;
      }
      if (Object.keys(current).some((id) => !detectedIdSet.has(id))) changed = true;
      return changed ? next : current;
    });
  }, [
    detectedLocalAgentConnections,
    localAgentDialogOpen,
    seenLocalConnectionIds,
  ]);

  const refreshLocalAgentDiscovery = useCallback(async () => {
    setLocalDiscoveryManualRefreshing(true);
    try {
      await localAgentConnections.refetch();
    } finally {
      setLocalDiscoveryManualRefreshing(false);
    }
  }, [localAgentConnections]);

  const localDiscoveryRefreshing =
    localAgentConnections.isLoading ||
    createLocalAgentPairingMutation.isPending ||
    localDiscoveryManualRefreshing;

  return (
    <ConsoleShell title={text("智能体工作室", "Agent Studio")}>
      <div className="space-y-4 p-4">
        <section className="grid grid-cols-1 gap-3 xl:grid-cols-12 xl:gap-4">
          <div className="xl:col-span-8">
            <h1 className="text-lg font-semibold text-slate-950">
              {text("智能体工作室", "Agent Studio")}
            </h1>
            <p className="mt-1 max-w-3xl text-sm text-slate-500">
              {text(
                "这里构建智能体：选择模型、工具、提示词、沙箱和编排能力后进入工作台运行。",
                "Build Model + Harness = Agent here. Choose model, tools, prompt, sandbox, and orchestration before entering Workspace.",
              )}
            </p>
          </div>
          <div className="flex flex-wrap items-start gap-2 xl:col-span-4 xl:justify-end">
            <Link to="/settings/models">
              <Button>
                <Settings className="h-3.5 w-3.5" /> {text("模型配置", "Models")}
              </Button>
            </Link>
            <Link to="/agents/default/workspace">
              <Button variant="primary">
                <Bot className="h-3.5 w-3.5" /> {text("打开默认计划", "Open Default Plan")}
              </Button>
            </Link>
          </div>
        </section>

        {agents.isLoading && (
          <Card>
            <div className="p-4 text-sm text-slate-500">{text("加载智能体...", "Loading Agents...")}</div>
          </Card>
        )}
        {agents.error && (
          <Card>
            <div className="p-4 text-sm text-red-700">
              {agents.error instanceof Error ? agents.error.message : text("加载失败", "Failed to load")}
            </div>
          </Card>
        )}
        {agents.data && (
          <section className="space-y-2">
            <div className="flex items-center justify-between gap-3 border-b border-slate-200 pb-2">
              <div className="inline-flex items-center gap-2 text-xs font-semibold text-slate-900">
                <Bot className="h-4 w-4 text-slate-500" />
                {text("配置目标", "Configuration targets")}
              </div>
              <Badge tone="neutral">{agents.data.items.length} {text("个智能体", "Agents")}</Badge>
            </div>
            <div className="grid grid-cols-1 gap-2 lg:grid-cols-2 2xl:grid-cols-3">
              {agents.data.items.map((agent, index) => (
                <AgentCard
                  key={agent.id}
                  agent={agent}
                  selected={agent.id === selectedAgentId}
                  knowledgeCount={readyKnowledgeCountForAgent(agent.id, index)}
                  connectionsCount={activeLocalAgentCountForAgent(agent.id)}
                  onSelect={() => setSelectedAgentId(agent.id)}
                />
              ))}
            </div>
          </section>
        )}

        <section className="space-y-2">
          <div className="flex items-center justify-between gap-3 border-b border-slate-200 pb-2">
            <div className="inline-flex items-center gap-2 text-xs font-semibold text-slate-900">
              <Settings className="h-4 w-4 text-slate-500" />
              {text("配置入口", "Configuration entry points")}
            </div>
            <Badge tone="neutral">{selectedAgentLabel}</Badge>
          </div>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-4">
            <ConfigEntryCard
              icon={<PackagePlus className="h-4 w-4" />}
              title={text("职业模板", "Role template")}
              status={createAgentMutation.isSuccess || cloneAgentMutation.isSuccess ? text("已更新", "Updated") : text("API 支撑", "API-backed")}
              statusTone={createAgentMutation.isSuccess || cloneAgentMutation.isSuccess ? "success" : "info"}
              summary={draftAgentName}
              detail={`${draftAgentId} · Token ${tokenBudget}`}
              actionLabel={text("配置模板", "Configure template")}
              onAction={() => setTemplateDialogOpen(true)}
            />
            <ConfigEntryCard
              icon={<PlugZap className="h-4 w-4" />}
              title={text("接入本地 Agent", "Connect local Agent")}
              status={
                onlineLocalAgentCount > 0
                  ? text("在线", "Online")
                  : activeLocalAgentCount > 0
                    ? text("待恢复", "Recoverable")
                    : text("未接入", "Not connected")
              }
              statusTone={onlineLocalAgentCount > 0 ? "success" : activeLocalAgentCount > 0 ? "warning" : "neutral"}
              summary={selectedAgentLabel}
              detail={text(`${activeLocalAgentCount} 个本地连接`, `${activeLocalAgentCount} local connection(s)`)}
              actionLabel={text("打开接入向导", "Open connection wizard")}
              onAction={() => setLocalAgentDialogOpen(true)}
            />
            <ConfigEntryCard
              icon={<Wrench className="h-4 w-4" />}
              title={text("能力附件与就绪检查", "Capability attachments and readiness")}
              status={selectedAgent?.tools_json.length ? text("可运行", "Ready") : text("缺少能力", "Needs capability")}
              statusTone={selectedAgent?.tools_json.length ? "success" : "warning"}
              summary={capabilityName}
              detail={text(`知识 ${activeKnowledgeSources.length} · 本地 ${activeLocalAgentCount}`, `Knowledge ${activeKnowledgeSources.length} · Local ${activeLocalAgentCount}`)}
              actionLabel={text("配置能力附件", "Configure attachment")}
              onAction={() => setCapabilityDialogOpen(true)}
            />
            <ConfigEntryCard
              icon={<Gauge className="h-4 w-4" />}
              title={text("Token 省用方案", "Token Saving Plan")}
              status={tokenOptimizerStatusLabel}
              statusTone={enabledOptimizerCount > 0 ? "success" : "neutral"}
              summary={activeTokenOptimizerPreset?.description ?? text("选择内置省 Token 方案", "Choose a built-in token saving plan")}
              detail={text(`${enabledOptimizerCount} 个启用附件`, `${enabledOptimizerCount} enabled attachment(s)`)}
              actionLabel={text("配置 Token 方案", "Configure token plan")}
              onAction={() => setTokenOptimizerDialogOpen(true)}
            />
          </div>
        </section>

        <section className="grid grid-cols-12 gap-4">
          <Card className="col-span-12">
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Bot className="h-4 w-4" />
                {text("知识作用域", "Knowledge Scope")}
              </div>
              <Badge tone="success">{selectedAgentLabel}</Badge>
            </CardHeader>
            <div className="p-3">
              <AgentScopeSwitcher
                agents={agents.data?.items ?? []}
                selectedAgentId={selectedAgentId}
                selectedAgentLabel={selectedAgentLabel}
                selectedAgentSummary={selectedAgentSummary}
                onChange={setSelectedAgentId}
              />
            </div>
          </Card>
        </section>

        <CollapsibleCapabilitySection
          coreCapabilities={[
            {
              icon: <Brain className="h-4 w-4" />,
              title: text("模型", "Model"),
              subtitle: text("模型配置", "Model settings"),
              status: text("接口已接入", "API-backed"),
              description: text("内置模型预置，自定义模型通过模型设置保存。", "DeepSeek presets and custom providers are saved in Model Settings."),
              to: "/settings/models",
            },
            {
              icon: <Wrench className="h-4 w-4" />,
              title: text("工具", "Tools"),
              subtitle: text("MCP（模型上下文协议）", "MCP (Model Context Protocol)"),
              status: text("接口已接入", "API-backed"),
              description: text("工具权限来自智能体定义和工具注册表。", "Tool access comes from Agent definitions and Tool Registry."),
              to: "/tools",
            },
            {
              icon: <Database className="h-4 w-4" />,
              title: text("RAG 知识检索", "RAG Knowledge Retrieval"),
              subtitle: text("检索增强生成", "Retrieval Augmented Generation"),
              status: knowledgeConnectorReady ? text("已配置", "Configured") : text("待配置", "Needs setup"),
              description: text("就绪状态来自已索引知识源，不用固定就绪占位。", "Readiness comes from indexed knowledge sources, not a fixed ready placeholder."),
            },
            {
              icon: <GitBranch className="h-4 w-4" />,
              title: text("编排", "Orchestration"),
              subtitle: text("运行详情与观测", "Run detail and observability"),
              status: text("接口已接入", "API-backed"),
              description: text("工作台只暴露计划；执行、编排和审批作为运行详情与观测能力呈现。", "Workspace exposes Plan only; execution, orchestration, and approval appear as Run detail and Harness observability."),
            },
          ]}
          advancedCapabilities={[
            {
              icon: <Gauge className="h-4 w-4" />,
              title: text("Token 优化", "Token Optimizer"),
              subtitle: text("内置省 Token 方案", "Built-in token saving presets"),
              status: tokenOptimizerStatusLabel,
              description: text(
                "直接为当前智能体选择关闭、保守、均衡或强力方案；下次运行前自动调整上下文预算。",
                "Choose Off, Conservative, Balanced, or Aggressive for this Agent; the next run adjusts context budget automatically.",
              ),
            },
            {
              icon: <ScrollText className="h-4 w-4" />,
              title: text("提示词", "Prompt"),
              subtitle: text("系统提示词", "System prompt"),
              status: text("只读", "Read-only"),
              description: text("当前展示智能体系统提示词摘要，编辑器留到后续阶段。", "Shows Agent system prompt summary; editor belongs to a later stage."),
            },
            {
              icon: <Monitor className="h-4 w-4" />,
              title: text("沙箱", "Sandbox"),
              subtitle: text("隔离运行环境", "Isolated runtime"),
              status: text("接口已接入", "API-backed"),
              description: text("沙箱资源、配额和预热池保留在沙箱页面，智能体配置只展示能力入口。", "Sandbox resources, quota, and WarmPool stay on the Sandboxes page; Agent Studio shows the capability entry point."),
              to: "/sandboxes",
            },
            {
              icon: <Shield className="h-4 w-4" />,
              title: text("策略", "Policy"),
              subtitle: text("审批与审计", "Approval and audit"),
              status: text("接口已接入", "API-backed"),
              description: text("高风险工具通过策略、审批和审计链路执行，不在工作室里重复展开。", "High-risk tools run through policy, approval, and audit without expanding the full policy surface here."),
              to: "/settings/policies",
            },
          ]}
          StudioCapabilityComponent={StudioCapability}
        />

        <section className="space-y-2">
          <div className="flex items-center justify-between border-b border-slate-200 pb-2">
            <button
              onClick={() => setIsKnowledgeExpanded(!isKnowledgeExpanded)}
              className="flex w-full items-center justify-between gap-3 rounded-md px-1 py-1 text-left hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300"
              aria-expanded={isKnowledgeExpanded}
              aria-controls="knowledge-management-section"
            >
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Database className="h-4 w-4" />
                {text("知识管理", "Knowledge Management")}
                {activeKnowledgeSources.length > 0 && (
                  <Badge tone="success">{activeKnowledgeSources.length} {text("个知识源", "sources")}</Badge>
                )}
              </div>
              {isKnowledgeExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
          <div
            id="knowledge-management-section"
            aria-hidden={!isKnowledgeExpanded}
            className={cn(
              "overflow-hidden transition-all duration-300",
              isKnowledgeExpanded ? "max-h-[5000px] opacity-100" : "max-h-0 opacity-0"
            )}
          >
            {isKnowledgeExpanded ? <KnowledgeManagementPanel agentId={selectedAgentId} /> : null}
          </div>
        </section>

        <ConfigDialog
          open={templateDialogOpen}
          title={text("选择职业模板", "Choose role template")}
          description={text("模板配置只在需要创建或克隆智能体时打开，避免常驻占用 Agent Studio 首屏。", "Open template configuration only when creating or cloning an Agent.")}
          onClose={() => setTemplateDialogOpen(false)}
          className="max-w-3xl"
        >
          <div className="grid gap-3 text-xs">
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <label className="grid gap-1">
                <span className="font-medium text-slate-600">智能体 ID</span>
                <Input aria-label="新智能体 ID" value={draftAgentId} onChange={(event) => setDraftAgentId(event.target.value)} />
              </label>
              <label className="grid gap-1">
                <span className="font-medium text-slate-600">{text("名称", "Name")}</span>
                <Input aria-label="新智能体名称" value={draftAgentName} onChange={(event) => setDraftAgentName(event.target.value)} />
              </label>
            </div>
            <label className="grid gap-1">
              <span className="font-medium text-slate-600">{text("系统提示词", "System prompt")}</span>
              <Textarea aria-label="系统提示词编辑器" value={draftSystemPrompt} onChange={(event) => setDraftSystemPrompt(event.target.value)} />
            </label>
            <label className="grid gap-1">
              <span className="font-medium text-slate-600">{text("Token 预算", "Token budget")}: {tokenBudget}</span>
              <Input aria-label="Token 预算" type="range" min={1024} max={16000} step={512} value={tokenBudget} onChange={(event) => setTokenBudget(Number(event.target.value))} />
            </label>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => createAgentMutation.mutate()} disabled={createAgentMutation.isPending}>
                <Bot className="h-3.5 w-3.5" /> {text("使用此模板", "Use template")}
              </Button>
              <Button onClick={() => cloneAgentMutation.mutate()} disabled={cloneAgentMutation.isPending}>
                {text("克隆当前智能体", "Clone selected Agent")}
              </Button>
            </div>
            {(createAgentMutation.error instanceof Error || cloneAgentMutation.error instanceof Error) ? (
              <div className="text-red-700">{(createAgentMutation.error as Error | null)?.message ?? (cloneAgentMutation.error as Error).message}</div>
            ) : null}
          </div>
        </ConfigDialog>

        <ConfigDialog
          open={tokenOptimizerDialogOpen}
          title={text("Token 省用方案", "Token Saving Plan")}
          description={text("为当前智能体选择内置上下文省用方案；保存后后续运行会使用新预算策略。", "Choose a built-in context saving plan for the selected Agent.")}
          onClose={() => setTokenOptimizerDialogOpen(false)}
          className="max-w-3xl"
        >
          <div className="grid gap-2 text-xs">
            <div
              aria-label={text("Token 省用方案", "Token saving plan")}
              className="grid grid-cols-2 gap-2 md:grid-cols-2"
              role="group"
            >
              {(tokenOptimizerPresets.data?.items ?? []).map((preset) => {
                const active = activeTokenOptimizerPresetId === preset.preset_id;
                const pending =
                  selectTokenOptimizerMutation.isPending &&
                  selectTokenOptimizerMutation.variables === preset.preset_id;
                return (
                  <button
                    key={preset.preset_id}
                    type="button"
                    aria-pressed={active}
                    className={cn(
                      "grid min-h-20 gap-2 rounded-md border p-2 text-left transition-colors",
                      active
                        ? "border-slate-900 bg-slate-50 text-slate-950"
                        : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50",
                      selectTokenOptimizerMutation.isPending ? "cursor-wait opacity-70" : "",
                    )}
                    disabled={selectTokenOptimizerMutation.isPending}
                    onClick={() => selectTokenOptimizerMutation.mutate(preset.preset_id)}
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="font-semibold">{preset.display_name}</span>
                      <Badge tone={active ? "success" : "neutral"}>
                        {active ? text("当前", "Current") : pending ? text("保存中", "Saving") : text("可选", "Option")}
                      </Badge>
                    </span>
                    <span className="leading-5 text-slate-500">{preset.description}</span>
                  </button>
                );
              })}
            </div>
            {tokenOptimizerPresets.isLoading ? (
              <div className="rounded-md border border-slate-100 bg-slate-50 p-3 text-slate-500">
                {text("正在读取内置方案...", "Loading built-in plans...")}
              </div>
            ) : null}
            {activeTokenOptimizerPresetId === "custom" ? (
              <div className="rounded-md border border-amber-100 bg-amber-50 p-3 text-amber-800">
                {text(
                  "当前智能体启用了高级自定义 Token 优化。选择上方任一内置方案会切换到该方案。",
                  "This Agent currently uses a custom token optimizer. Selecting a built-in plan above will switch to that plan.",
                )}
              </div>
            ) : null}
            {selectTokenOptimizerMutation.error instanceof Error ? (
              <div className="text-red-700">{selectTokenOptimizerMutation.error.message}</div>
            ) : null}
            {tokenOptimizerPresets.error instanceof Error ? (
              <div className="text-red-700">{tokenOptimizerPresets.error.message}</div>
            ) : null}
          </div>
        </ConfigDialog>

        <ConfigDialog
          open={localAgentDialogOpen}
          title={text("接入本地 Agent", "Connect local Agent")}
          description={text("先生成一条通用连接命令，在本地执行后自动识别 hao、Codex CLI 和 Claude Code。识别完成后再选择并命名需要接入工作台的 Agent。", "Generate one generic connection command first. It auto-detects hao, Codex CLI, and Claude Code. Then choose and name the Agents to connect to the workspace.")}
          onClose={() => setLocalAgentDialogOpen(false)}
          className="max-w-3xl"
        >
          <div className="grid gap-4 text-xs">
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              <WizardStep index="1" title={text("生成连接命令", "Generate command")} active={Boolean(localAgentPairing)} />
              <WizardStep index="2" title={text("本地执行", "Run locally")} active={Boolean(localAgentPairing?.command)} />
              <WizardStep index="3" title={text("选择并命名", "Choose and name")} active={detectedLocalAgentConnections.length > 0} />
            </div>

            <div className="rounded-md border border-slate-100 bg-slate-50 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="font-medium text-slate-800">{text("当前目标智能体", "Selected target Agent")}</div>
                  <div className="mt-1 text-slate-500">{selectedAgentLabel} · {selectedAgentId}</div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="info">{text("自动识别 hao / Codex CLI / Claude Code", "Auto-detect hao / Codex CLI / Claude Code")}</Badge>
                  <Button
                    type="button"
                    onClick={() => createLocalAgentPairingMutation.mutate()}
                    disabled={createLocalAgentPairingMutation.isPending}
                  >
                    <PlugZap className="h-3.5 w-3.5" />
                    {localAgentPairing ? text("重新生成", "Regenerate") : text("生成连接命令", "Generate command")}
                  </Button>
                </div>
              </div>

              {localAgentPairing?.command ? (
                <div className="mt-3 grid gap-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <Badge tone="info">{text("配对码", "Pair code")} · {localAgentPairing.pair_code}</Badge>
                    <Badge tone="warning">{text("10 分钟内有效，可识别多个本地 Agent", "Valid for 10 minutes, can detect multiple local Agents")}</Badge>
                  </div>
                  <pre className="max-h-36 overflow-auto rounded-md border border-slate-200 bg-slate-950 p-3 font-mono text-[11px] leading-5 text-slate-100">
                    {localAgentPairing.command}
                  </pre>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      onClick={async () => {
                        const ok = await copyText(localAgentPairing.command ?? "");
                        setPairCommandCopied(ok);
                      }}
                    >
                      <Copy className="h-3.5 w-3.5" />
                      {pairCommandCopied ? text("已复制", "Copied") : text("复制命令", "Copy command")}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => void refreshLocalAgentDiscovery()}
                      disabled={localDiscoveryRefreshing}
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      {text("我已执行，刷新识别", "I ran it, refresh discovery")}
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="mt-3 grid gap-2 rounded-md border border-slate-200 bg-white p-3 leading-5 text-slate-500">
                  <div>
                    {text("点击生成后复制这一条命令到本地终端。命令会自动探测本机可用的 hao、Codex CLI 和 Claude Code；没有安装的本地 Agent 会跳过。", "Generate and copy this one command into a local terminal. It auto-detects available hao, Codex CLI, and Claude Code Agents; unavailable local Agents are skipped.")}
                  </div>
                  <code className="rounded border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-700">
                    hao bridge pair ... --daemon
                  </code>
                </div>
              )}
            </div>

            <RefreshOverlay
              refreshing={localDiscoveryRefreshing}
              label={text("正在刷新本地 Agent", "Refreshing local Agents")}
              className="rounded-md border border-slate-200 bg-white p-3"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <div className="font-medium text-slate-800">{text("选择并命名已发现 Agent", "Choose and name detected Agents")}</div>
                  <div className="mt-1 text-slate-500">
                    {detectedLocalAgentConnections.length > 0
                      ? text(`已发现 ${detectedLocalAgentConnections.length} 个待确认 Agent，已选择 ${selectedDetectedLocalConnections.length} 个。`, `${detectedLocalAgentConnections.length} pending confirmation, ${selectedDetectedLocalConnections.length} selected.`)
                      : text("执行命令后，已注册的本地 Agent 会自动出现在这里。", "After running the command, registered local Agents appear here automatically.")}
                  </div>
                </div>
                <Badge tone={localDiscoveryRefreshing ? "running" : "neutral"}>
                  {localDiscoveryRefreshing ? text("刷新中", "Refreshing") : text("实时状态", "Live status")}
                </Badge>
              </div>

              {detectedLocalAgentConnections.length > 0 ? (
                <>
                  <div className="mt-3 grid gap-2">
                    {detectedLocalAgentConnections.map((connection) => (
                      <LocalAgentDiscoveryRow
                        key={connection.id}
                        connection={connection}
                        checked={selectedLocalConnectionIds.includes(connection.id)}
                        displayName={localConnectionNames[connection.id] ?? connection.display_name}
                        onToggle={(checked) => {
                          setSelectedLocalConnectionIds((current) =>
                            checked
                              ? Array.from(new Set([...current, connection.id]))
                              : current.filter((id) => id !== connection.id),
                          );
                        }}
                        onNameChange={(value) => {
                          setLocalConnectionNames((current) => ({ ...current, [connection.id]: value }));
                        }}
                        onRevoke={(connectionId) => revokeLocalAgentConnectionMutation.mutate(connectionId)}
                        revokePending={revokeLocalAgentConnectionMutation.isPending}
                      />
                    ))}
                  </div>
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                    <div className="text-slate-500">
                      {text("所有发现的 Agent 默认不会接入；只保留勾选项，未勾选的连接会断开。", "Detected Agents are not connected by default; only checked items are kept, and unchecked connections are disconnected.")}
                    </div>
                    <Button
                      type="button"
                      onClick={() =>
                        updateLocalAgentConnectionMutation.mutate({
                          detectedConnections: detectedLocalAgentConnections,
                          selectedConnections: selectedDetectedLocalConnections,
                          pairingTokenId: localAgentPairing?.id ?? null,
                        })
                      }
                      disabled={
                        !selectedDetectedLocalConnectionNamesValid ||
                        updateLocalAgentConnectionMutation.isPending
                      }
                    >
                      <PlugZap className="h-3.5 w-3.5" />
                      {selectedDetectedLocalConnections.length === 0
                        ? text("不接入，断开全部", "Disconnect all")
                        : text(`接入 ${selectedDetectedLocalConnections.length} 个 Agent`, `Connect ${selectedDetectedLocalConnections.length} Agent(s)`)}
                    </Button>
                  </div>
                </>
              ) : (
                <div className="mt-3 rounded-md border border-dashed border-slate-200 bg-slate-50 p-4 text-center leading-5 text-slate-500">
                  {text("还没有识别到本地 Agent。请先复制并执行上方命令，或点击刷新识别。", "No local Agent detected yet. Copy and run the command above, or refresh discovery.")}
                  <div className="mt-3">
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => void refreshLocalAgentDiscovery()}
                      disabled={localDiscoveryRefreshing}
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      {text("刷新识别", "Refresh discovery")}
                    </Button>
                  </div>
                </div>
              )}
              {localAgentConnections.error instanceof Error ? (
                <div className="mt-2 text-red-700">{localAgentConnections.error.message}</div>
              ) : null}
            </RefreshOverlay>
          </div>
        </ConfigDialog>

        <ConfigDialog
          open={capabilityDialogOpen}
          title={text("配置能力附件", "Configure capability attachment")}
          description={text("为当前智能体附加 MCP、技能或工具能力；保存后刷新就绪检查。", "Attach an MCP, Skill, or tool capability to the current Agent; readiness refreshes after save.")}
          onClose={() => setCapabilityDialogOpen(false)}
        >
          <div className="grid gap-3 text-xs">
            <div className="rounded-md border border-slate-100 bg-slate-50 p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-slate-700">{selectedAgentLabel}</span>
                <Badge tone="neutral">{selectedAgentId}</Badge>
              </div>
              <p className="mt-2 leading-5 text-slate-500">
                {text("附件会进入智能体作用域，运行时通过能力注册表和工具执行器解析。", "The attachment is scoped to this Agent and resolved through the capability registry and ToolRunner at runtime.")}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <label className="grid gap-1">
                <span className="font-medium text-slate-600">{text("能力名称", "Capability name")}</span>
                <Input aria-label="能力名称" value={capabilityName} onChange={(event) => setCapabilityName(event.target.value)} />
              </label>
              <label className="grid gap-1">
                <span className="font-medium text-slate-600">{text("能力类型", "Capability type")}</span>
                <Input aria-label="能力类型" value={capabilityKind} onChange={(event) => setCapabilityKind(event.target.value)} />
              </label>
            </div>
            <Button onClick={() => attachCapabilityMutation.mutate()} disabled={attachCapabilityMutation.isPending || !capabilityName.trim()}>
              <Wrench className="h-3.5 w-3.5" /> {text("附加到当前智能体", "Attach to selected Agent")}
            </Button>
            {attachCapabilityMutation.error instanceof Error ? <div className="text-red-700">{attachCapabilityMutation.error.message}</div> : null}
          </div>
        </ConfigDialog>
      </div>
    </ConsoleShell>
  );
}

function ConfigEntryCard({
  icon,
  title,
  status,
  statusTone = "neutral",
  summary,
  detail,
  actionLabel,
  onAction,
}: {
  icon: ReactNode;
  title: string;
  status: string;
  statusTone?: BadgeTone;
  summary: string;
  detail: string;
  actionLabel: string;
  onAction: () => void;
}) {
  return (
    <Card className="h-full">
      <div className="flex h-full flex-col gap-3 p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-2 text-xs font-semibold text-slate-900">
              <span className="text-slate-500">{icon}</span>
              <span className="truncate">{title}</span>
            </div>
            <div className="mt-1 truncate text-[11px] text-slate-500" title={summary}>
              {summary}
            </div>
          </div>
          <Badge tone={statusTone} className="shrink-0 whitespace-nowrap text-[10px]">
            {status}
          </Badge>
        </div>
        <div className="min-h-8 text-xs leading-4 text-slate-500" title={detail}>
          {detail}
        </div>
        <div className="mt-auto">
          <Button type="button" className="w-full justify-between" onClick={onAction}>
            <span>{actionLabel}</span>
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        </div>
      </div>
    </Card>
  );
}

function WizardStep({ index, title, active }: { index: string; title: string; active: boolean }) {
  return (
    <div className={cn(
      "rounded-md border p-3",
      active ? "border-slate-900 bg-slate-50 text-slate-950" : "border-slate-200 bg-white text-slate-500",
    )}>
      <div className="flex items-center gap-2">
        <span className={cn(
          "inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold",
          active ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-500",
        )}>
          {index}
        </span>
        <span className="font-medium">{title}</span>
      </div>
    </div>
  );
}

const LOCAL_AGENT_ADAPTERS = [
  {
    kind: "fake",
    label: "fake bridge",
    enabled: true,
    badgeZh: "v1 启用",
    badgeEn: "v1 enabled",
    icon: Monitor,
    zh: "用于验证配对、注册、心跳和一次回复，不执行本地命令。",
    en: "Validates pairing, registration, heartbeat, and one reply without local command execution.",
    matchesConnection: (connection: LocalAgentConnection) => connection.adapter_kind === "fake",
  },
  {
    kind: "hao",
    label: "hao",
    enabled: true,
    badgeZh: "v1 启用",
    badgeEn: "v1 enabled",
    icon: Terminal,
    zh: "v1 真实本地 Agent 适配器，支持本地会话恢复和审计回传。",
    en: "The v1 real local Agent adapter with local session resume and audit reporting.",
    matchesConnection: (connection: LocalAgentConnection) => connection.adapter_kind === "hao",
  },
  {
    kind: "codex",
    label: "Codex CLI",
    enabled: true,
    badgeZh: "v4 启用",
    badgeEn: "v4 enabled",
    icon: Bot,
    zh: "v4 本地 Agent 适配器，支持与 hao 一致的 Harness 审批工具链和流式回复。",
    en: "The v4 local Agent adapter with hao-parity Harness-approved local tools and streaming replies.",
    matchesConnection: (connection: LocalAgentConnection) => connection.adapter_kind === "codex",
  },
  {
    kind: "claude_code",
    label: "Claude Code",
    enabled: true,
    badgeZh: "v5 启用",
    badgeEn: "v5 enabled",
    icon: Brain,
    zh: "Claude Code 本地 Agent 适配器，支持与 hao 一致的 Harness 审批工具链和流式回复。",
    en: "Claude Code local Agent adapter with hao-parity Harness-approved local tools and streaming replies.",
    matchesConnection: (connection: LocalAgentConnection) =>
      connection.adapter_kind === "claude_code" && !localAgentUsesClaudePermissionBridge(connection),
  },
  {
    kind: "claude_code_v6",
    label: "Claude Code",
    enabled: true,
    badgeZh: "v6 启用",
    badgeEn: "v6 enabled",
    icon: Brain,
    zh: "v6 SDK 意图捕获 + Harness 执行器，支持 assistant 回复和经 Harness 审批的本地工具。",
    en: "The v6 SDK intent-capture plus Harness executor adapter for assistant replies and Harness-approved local tools.",
    matchesConnection: localAgentUsesClaudePermissionBridge,
  },
] as const;

const LOCAL_AGENT_DISCOVERY_ADAPTERS = LOCAL_AGENT_ADAPTERS.filter(
  (adapter) => adapter.kind !== "fake",
);

function localAgentIsUserFacing(connection: LocalAgentConnection) {
  return (
    connection.status !== "revoked" &&
    LOCAL_AGENT_DISCOVERY_ADAPTERS.some((adapter) => adapter.matchesConnection(connection))
  );
}

function localAgentIsConfirmedUserFacing(connection: LocalAgentConnection) {
  return localAgentIsUserFacing(connection) && connection.onboarding_confirmed !== false;
}

function localAgentAdapterRank(connection: LocalAgentConnection) {
  const index = LOCAL_AGENT_DISCOVERY_ADAPTERS.findIndex((adapter) =>
    adapter.matchesConnection(connection),
  );
  return index >= 0 ? index : LOCAL_AGENT_DISCOVERY_ADAPTERS.length;
}

function sortLocalAgentConnections(connections: LocalAgentConnection[]) {
  return [...connections].sort((a, b) => {
    const adapterDelta = localAgentAdapterRank(a) - localAgentAdapterRank(b);
    if (adapterDelta !== 0) return adapterDelta;
    const nameDelta = a.display_name.localeCompare(b.display_name);
    if (nameDelta !== 0) return nameDelta;
    const createdDelta = a.created_at.localeCompare(b.created_at);
    if (createdDelta !== 0) return createdDelta;
    return a.id.localeCompare(b.id);
  });
}

function sameStringArray(left: string[], right: string[]) {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function localAgentAdapterLabel(connection: LocalAgentConnection) {
  const adapter = LOCAL_AGENT_ADAPTERS.find((candidate) => candidate.matchesConnection(connection));
  return adapter?.label ?? connection.adapter_kind;
}

function localAgentAdapterIcon(connection: LocalAgentConnection) {
  const adapter = LOCAL_AGENT_ADAPTERS.find((candidate) => candidate.matchesConnection(connection));
  return adapter?.icon ?? Bot;
}

function localAgentSupportsResume(connection: LocalAgentConnection) {
  return connection.capabilities_json.supports_resume === true;
}

function localAgentUsesClaudePermissionBridge(connection: LocalAgentConnection) {
  return (
    connection.adapter_kind === "claude_code" &&
    connection.capabilities_json.permission_bridge === "harness_local_tool_request_v1" &&
    connection.capabilities_json.host_tools_authorized === true
  );
}

function localAgentStatusTone(connection: LocalAgentConnection) {
  if (connection.onboarding_confirmed === false || connection.status === "pending_confirmation") return "warning";
  if (connection.status === "online" || connection.status === "busy") return "success";
  if (connection.status === "revoked") return "failed";
  return "warning";
}

function localAgentStatusLabel(connection: LocalAgentConnection) {
  if (connection.onboarding_confirmed === false || connection.status === "pending_confirmation") return "待确认";
  if (connection.status === "online") return "在线";
  if (connection.status === "busy") return "运行中";
  if (connection.status === "revoked") return "已撤销";
  return "离线可恢复";
}

function localAgentResumeLabel(connection: LocalAgentConnection) {
  if (localAgentSupportsResume(connection)) return "原生恢复";
  if (connection.adapter_kind === "codex" || connection.adapter_kind === "claude_code") {
    return "上下文重放";
  }
  return "上下文恢复";
}

function localAgentResumeHelp(connection: LocalAgentConnection) {
  if (localAgentSupportsResume(connection)) {
    return "离线后重新运行同一 bridge，会继续使用本地 session 状态。";
  }
  if (connection.adapter_kind === "codex" || connection.adapter_kind === "claude_code") {
    return "离线后重新运行 bridge，Harness 会把最近对话、模型、工具和附件上下文重放给新的本地进程。";
  }
  return "离线后重新运行 bridge，Harness 会按已保存上下文恢复会话。";
}

function localAgentToolBadge(connection: LocalAgentConnection) {
  if (connection.onboarding_confirmed === false || connection.status === "pending_confirmation") {
    return { label: "未接入", tone: "warning" as const };
  }
  if (["hao", "codex", "claude_code"].includes(connection.adapter_kind)) {
    return { label: "本机工具链可用", tone: "success" as const };
  }
  return { label: "无本机执行", tone: "neutral" as const };
}

function localAgentToolHelp(connection: LocalAgentConnection) {
  if (connection.onboarding_confirmed === false || connection.status === "pending_confirmation") {
    return "当前只是已发现，勾选并保存后才会接入工作台。";
  }
  if (localAgentUsesClaudePermissionBridge(connection)) {
    return "Claude Code 权限桥会先捕获工具意图，再由 Harness 审批并执行本机工具。";
  }
  if (connection.adapter_kind === "hao") {
    return "hao 支持本机 read/write/shell/test/git/network 工具，并把审计写回 Harness。";
  }
  if (connection.adapter_kind === "codex") {
    return "Codex CLI 可申请 read/write/shell/test/git/network 本机能力，执行前由 Harness 审批并写入审计。";
  }
  if (connection.adapter_kind === "claude_code") {
    return "Claude Code 可申请 read/write/shell/test/git/network 本机能力，执行前由 Harness 审批并写入审计。";
  }
  return "此 adapter 不执行本机工具。";
}

function localAgentModelLabel(connection: LocalAgentConnection) {
  const provider = stringCapability(connection.capabilities_json.model_provider);
  const model = stringCapability(connection.capabilities_json.model_name);
  if (provider && model) return `${provider}/${model}`;
  if (model) return model;
  return "跟随工作台模型";
}

function localAgentDisplayName(connection: LocalAgentConnection) {
  const draftName = connection.display_name.trim();
  if (draftName.length > 0) return draftName;
  return localAgentAdapterLabel(connection);
}

function stringCapability(value: unknown): string {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : "";
}

function LocalAgentDiscoveryRow({
  connection,
  checked,
  displayName,
  onToggle,
  onNameChange,
  onRevoke,
  revokePending,
}: {
  connection: LocalAgentConnection;
  checked: boolean;
  displayName: string;
  onToggle: (checked: boolean) => void;
  onNameChange: (value: string) => void;
  onRevoke: (connectionId: string) => void;
  revokePending: boolean;
}) {
  const { text } = useI18n();
  const usesClaudePermissionBridge = localAgentUsesClaudePermissionBridge(connection);
  const AdapterIcon = localAgentAdapterIcon(connection);
  const resumeLabel = localAgentResumeLabel(connection);
  const toolBadge = localAgentToolBadge(connection);
  const displayTitle = localAgentDisplayName(connection);

  return (
    <div
      className={cn(
        "rounded-md border p-3",
        checked ? "border-slate-900 bg-slate-50" : "border-slate-200 bg-white",
      )}
    >
      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(15rem,18rem)] md:items-center">
        <label className="flex min-w-0 items-start gap-3">
          <input
            type="checkbox"
            className="mt-1 h-4 w-4 rounded border-slate-300 text-slate-900"
            checked={checked}
            onChange={(event) => onToggle(event.target.checked)}
            aria-label={text(`选择 ${displayTitle}`, `Select ${displayTitle}`)}
          />
          <span className="flex min-w-0 flex-1 gap-3">
            <span className="mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600">
              <AdapterIcon className="h-4 w-4" aria-hidden="true" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="truncate text-sm font-semibold text-slate-900">
                  {displayTitle}
                </span>
                <Badge tone="neutral">{localAgentAdapterLabel(connection)}</Badge>
                <Badge tone={localAgentStatusTone(connection)}>
                  {text(localAgentStatusLabel(connection), connection.status)}
                </Badge>
                <Badge tone={connection.status === "online" || connection.status === "busy" ? "success" : "warning"}>
                  {text(resumeLabel, resumeLabel === "原生恢复" ? "Native resume" : "Context replay")}
                </Badge>
                <Badge tone={toolBadge.tone}>{text(toolBadge.label, toolBadge.label)}</Badge>
                {usesClaudePermissionBridge ? (
                  <Badge tone="purple">{text("权限桥", "Permission bridge")}</Badge>
                ) : null}
              </span>
              <span className="mt-1 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[11px] text-slate-500">
                <span>{connection.adapter_kind}</span>
                <span>{localAgentModelLabel(connection)}</span>
                {connection.workspace_root ? <span>{connection.workspace_root}</span> : null}
              </span>
              <span className="mt-2 grid gap-1 text-[11px] leading-4 text-slate-500">
                <span>{text(localAgentResumeHelp(connection), localAgentResumeHelp(connection))}</span>
                <span>{text(localAgentToolHelp(connection), localAgentToolHelp(connection))}</span>
              </span>
            </span>
          </span>
        </label>
        <div className="grid min-w-0 gap-2">
          <label className="grid gap-1">
            <span className="text-[11px] font-medium text-slate-500">{text("名称", "Name")}</span>
            <Input
              aria-label={text(`本地 Agent 名称 ${displayTitle}`, `Local Agent name ${displayTitle}`)}
              value={displayName}
              onChange={(event) => onNameChange(event.target.value)}
              disabled={!checked}
            />
          </label>
          {connection.status !== "revoked" ? (
            <Button
              type="button"
              variant="ghost"
              className="justify-center md:justify-self-end"
              onClick={() => onRevoke(connection.id)}
              disabled={revokePending}
            >
              {text("撤销", "Revoke")}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function isReadyKnowledgeSource(source: KnowledgeSource) {
  return (
    source.status === "ACTIVE" &&
    source.health_status === "HEALTHY" &&
    source.latest_documents.some((document) => document.status === "INDEXED")
  );
}

function tokenOptimizerPresetIdFromAttachments(
  attachments: AgentCapabilityAttachmentSummary[],
): TokenOptimizerPresetId | "custom" {
  const enabled = attachments.find((attachment) => attachment.enabled);
  if (!enabled) {
    return "off";
  }
  const presetId = enabled.capability_key.match(/^builtin:context-optimizer:(.+)$/)?.[1];
  if (
    presetId === "conservative" ||
    presetId === "balanced" ||
    presetId === "aggressive"
  ) {
    return presetId;
  }
  return "custom";
}

function StudioCapability({
  icon,
  title,
  subtitle,
  status,
  description,
  to,
  disabled = false,
}: {
  icon: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  status: string;
  description: string;
  to?: string;
  disabled?: boolean;
}) {
  const body = (
    <Card className={cn("h-full", disabled ? "opacity-60" : "")}>
      <div className="flex h-full flex-col gap-2 p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 space-y-1">
            <div className="flex min-w-0 items-center gap-2 text-xs font-semibold text-slate-900">
              {icon}
              <span className="truncate">{title}</span>
            </div>
            {subtitle ? <div className="text-[10px] leading-3 text-slate-400">{subtitle}</div> : null}
          </div>
          <Badge tone={disabled ? "neutral" : "success"} className="shrink-0 whitespace-nowrap text-[10px]">
            {status}
          </Badge>
        </div>
        <p className="line-clamp-2 flex-1 text-xs leading-5 text-slate-500" title={description}>{description}</p>
      </div>
    </Card>
  );
  if (!to || disabled) {
    return body;
  }
  return (
    <Link to={to} className="block h-full">
      {body}
    </Link>
  );
}

function AgentScopeSwitcher({
  agents,
  selectedAgentId,
  selectedAgentLabel,
  selectedAgentSummary,
  onChange,
}: {
  agents: AgentDefinition[];
  selectedAgentId: string;
  selectedAgentLabel: string;
  selectedAgentSummary: string;
  onChange: (agentId: string) => void;
}) {
  const { text } = useI18n();
  const options = agents.length > 0 ? agents : [{ id: "default", name: text("默认智能体", "Default Agent"), description: selectedAgentSummary }];

  return (
    <div className="max-w-3xl">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <div className="text-xs font-medium text-slate-500">
            {text("切换知识作用域", "Switch knowledge scope")}
          </div>
          <p className="text-xs leading-4 text-slate-400">
            {text(
              "先选定一个智能体，再在下方查看对应的知识源、文档和索引状态。",
              "Pick an agent first, then inspect its knowledge sources, documents, and index state below.",
            )}
          </p>
        </div>
        <Badge tone="neutral" className="shrink-0 whitespace-nowrap">
          {text("标识", "ID")} · {selectedAgentId}
        </Badge>
      </div>

      <MenuSelect
        ariaLabel={text("知识作用域列表", "Knowledge scope list")}
        value={selectedAgentId}
        onChange={onChange}
        placeholder={selectedAgentLabel}
        className="w-full"
        buttonClassName="h-auto rounded-2xl border-slate-200 px-4 py-3"
        menuClassName="w-full"
        options={options.map((agent) => {
          const label = agent.id === "default" ? text("默认智能体", "Default Agent") : agent.name;
          return {
            value: agent.id,
            label,
            description: agent.description?.trim() || selectedAgentSummary,
            meta: agent.id === selectedAgentId ? text("已选", "Active") : agent.id,
            leading: <Bot className="h-4 w-4" />,
          };
        })}
      />
    </div>
  );
}

function AgentCard({
  agent,
  selected,
  knowledgeCount = 0,
  connectionsCount = 0,
  onSelect,
}: {
  agent: AgentDefinition;
  selected: boolean;
  knowledgeCount?: number;
  connectionsCount?: number;
  onSelect: () => void;
}) {
  const { text } = useI18n();
  const visibleTools = agent.tools_json.slice(0, 3);
  const hiddenToolCount = Math.max(0, agent.tools_json.length - visibleTools.length);
  const visibleTags = agent.routing_tags.slice(0, 3);
  const hiddenTagCount = Math.max(0, agent.routing_tags.length - visibleTags.length);

  return (
    <Card
      className={cn(
        "col-span-1 h-full overflow-hidden transition-colors",
        selected
          ? "border-slate-900 bg-slate-50/60 shadow-sm"
          : "hover:border-slate-300 hover:bg-slate-50/40",
      )}
      role="group"
      aria-label={text(`${agent.name} 配置卡`, `${agent.name} configuration card`)}
    >
      <div className="grid h-full gap-2.5 p-3">
        <div className="flex items-start gap-3">
          <div
            className={cn(
              "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border",
              selected ? "border-slate-900 bg-white text-slate-900" : "border-slate-200 bg-slate-50 text-slate-500",
            )}
          >
            <Bot className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 flex-wrap items-center gap-1.5">
              <div className="min-w-0 truncate text-sm font-semibold text-slate-950" title={agent.name}>
                {agent.name}
              </div>
              <Badge tone={agent.status === "ACTIVE" ? "success" : statusTone(agent.status)} className="shrink-0 px-1.5 py-0 text-[10px]">
                {statusLabel(agent.status)}
              </Badge>
            </div>
            <div className="mt-1 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-[11px] leading-4 text-slate-500">
              <span className="max-w-40 truncate font-mono" title={agent.id}>{agent.id}</span>
              <span>{agent.role}</span>
              <span>{text("并行", "Parallel")} {agent.max_parallel_assignments}</span>
              <span className="max-w-36 truncate font-mono" title={agent.model_name}>{agent.model_name}</span>
            </div>
          </div>
          <AgentReadinessRing
            size="sm"
            label={agent.name}
            toolsCount={agent.tools_json.length}
            knowledgeCount={knowledgeCount}
            connectionsCount={connectionsCount}
          />
        </div>

        <p className="line-clamp-2 min-h-9 text-xs leading-[18px] text-slate-600" title={agent.description}>
          {agent.description}
        </p>

        <div className="flex min-h-7 flex-wrap items-center gap-1.5">
          <span className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-500">
            <Wrench className="h-3.5 w-3.5" />
            {text("工具", "Tools")}
          </span>
          {visibleTools.length > 0 ? (
            visibleTools.map((tool) => (
              <Badge
                key={tool}
                tone={tool.includes("run") || tool.includes("write") ? "warning" : "neutral"}
                className="max-w-44 truncate px-1.5 py-0 text-[10px]"
              >
                {tool}
              </Badge>
            ))
          ) : (
            <Badge tone="warning" className="px-1.5 py-0 text-[10px]">
              {text("未配置", "Not configured")}
            </Badge>
          )}
          {hiddenToolCount > 0 ? (
            <Badge tone="pending" className="px-1.5 py-0 text-[10px]">+{hiddenToolCount}</Badge>
          ) : null}
        </div>

        <div className="flex min-h-7 flex-wrap items-center gap-1.5">
          <span className="text-[11px] font-medium text-slate-500">{text("标签", "Tags")}</span>
          {visibleTags.length > 0 ? (
            visibleTags.map((tag) => (
              <span
                key={tag}
                className="max-w-32 truncate rounded border border-slate-200 bg-white px-1.5 py-0.5 font-mono text-[10px] text-slate-500"
                title={tag}
              >
                {tag}
              </span>
            ))
          ) : (
            <span className="rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[10px] text-slate-400">
              {text("无标签", "No tags")}
            </span>
          )}
          {hiddenTagCount > 0 ? (
            <span className="rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[10px] text-slate-400">
              +{hiddenTagCount}
            </span>
          ) : null}
        </div>

        <div className="flex items-center justify-between gap-2 border-t border-slate-100 pt-2">
          <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-500">
            <span>{text("知识", "Knowledge")} {knowledgeCount}</span>
            <span>{text("本地", "Local")} {connectionsCount}</span>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <Button
              type="button"
              aria-pressed={selected}
              variant={selected ? "ghost" : "secondary"}
              className={cn("h-7 px-2", selected ? "text-slate-500" : "")}
              onClick={onSelect}
              disabled={selected}
            >
              {selected ? text("当前配置", "Current") : text("设为配置", "Configure")}
            </Button>
            <Link
              to={`/agents/${agent.id}/workspace`}
              aria-label={text(`打开 ${agent.name}`, `Open ${agent.name}`)}
              className="inline-flex h-7 items-center justify-center gap-1.5 rounded-md border border-slate-200 bg-white px-2 text-xs font-medium text-slate-700 transition-[background-color,color,border-color,transform,box-shadow] hover:bg-slate-50 active:translate-y-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300"
            >
              {text("打开", "Open")}
              <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
            </Link>
          </div>
        </div>
      </div>
    </Card>
  );
}
