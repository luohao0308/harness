import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  Brain,
  ChevronRight,
  Copy,
  Database,
  GitBranch,
  Package,
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
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { ConfigDialog } from "../../../components/ui/config-dialog";
import { feedbackErrorMessage, notifyFeedback } from "../../../components/ui/feedback-toast";
import { Input, Textarea } from "../../../components/ui/input";
import { Card, CardHeader } from "../../../components/ui/card";
import { MenuSelect } from "../../../components/ui/menu-select";
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
  selectAgentTokenOptimizer,
  type AgentCapabilityAttachmentSummary,
  type AgentDefinition,
  type KnowledgeSource,
  type LocalAgentConnection,
  type LocalAgentPairing,
  type TokenOptimizerPresetId,
} from "../../tasks/api";
import { KnowledgeManagementPanel } from "../components/KnowledgeManagementPanel";
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
  const [capabilityDialogOpen, setCapabilityDialogOpen] = useState(false);
  const [localAgentDialogOpen, setLocalAgentDialogOpen] = useState(false);
  const [localAgentPairing, setLocalAgentPairing] = useState<LocalAgentPairing | null>(null);
  const [pairCommandCopied, setPairCommandCopied] = useState(false);
  const selectedKnowledgeSources = useQuery({
    queryKey: ["agent-knowledge", selectedAgentId],
    queryFn: () => listAgentKnowledgeSources(selectedAgentId),
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
  const revokeLocalAgentConnectionMutation = useMutation({
    mutationFn: (connectionId: string) => revokeLocalAgentConnection(connectionId),
    onSuccess: async () => {
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
  const selectedLocalAgentConnections =
    localAgentConnections.data?.items.filter((connection) => connection.agent_id === selectedAgentId) ?? [];
  const activeLocalAgentCount = selectedLocalAgentConnections.filter((connection) => connection.status !== "revoked").length;
  const onlineLocalAgentCount = selectedLocalAgentConnections.filter((connection) => connection.status === "online" || connection.status === "busy").length;

  useEffect(() => {
    if (
      agents.data?.items.length &&
      !agents.data.items.some((agent) => agent.id === selectedAgentId)
    ) {
      setSelectedAgentId(agents.data.items[0].id);
    }
  }, [agents.data?.items, selectedAgentId]);

  return (
    <ConsoleShell title={text("智能体工作室", "Agent Studio")}>
      <div className="space-y-4 p-4">
        <section className="grid grid-cols-12 gap-4">
          <div className="col-span-8">
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
          <div className="col-span-4 flex items-start justify-end gap-2">
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

        <section className="grid grid-cols-1 gap-3 xl:grid-cols-3">
          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <PackagePlus className="h-4 w-4" />
                {text("选择职业模板", "Choose role template")}
              </div>
              <Badge tone={createAgentMutation.isSuccess || cloneAgentMutation.isSuccess ? "success" : "info"}>
                {text("API 支撑", "API-backed")}
              </Badge>
            </CardHeader>
            <div className="grid gap-3 p-3 text-xs">
              <div className="grid grid-cols-2 gap-2">
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
                  <Bot className="h-3.5 w-3.5" /> {text("创建智能体", "Create Agent")}
                </Button>
                <Button onClick={() => cloneAgentMutation.mutate()} disabled={cloneAgentMutation.isPending}>
                  {text("克隆当前智能体", "Clone selected Agent")}
                </Button>
              </div>
              {(createAgentMutation.error instanceof Error || cloneAgentMutation.error instanceof Error) ? (
                <div className="text-red-700">{(createAgentMutation.error as Error | null)?.message ?? (cloneAgentMutation.error as Error).message}</div>
              ) : null}
            </div>
          </Card>

          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <PlugZap className="h-4 w-4" />
                {text("接入本地 Agent", "Connect local Agent")}
              </div>
              <Badge tone={onlineLocalAgentCount > 0 ? "success" : activeLocalAgentCount > 0 ? "warning" : "neutral"}>
                {onlineLocalAgentCount > 0
                  ? text("在线", "Online")
                  : activeLocalAgentCount > 0
                    ? text("待恢复", "Recoverable")
                    : text("未接入", "Not connected")}
              </Badge>
            </CardHeader>
            <div className="grid gap-3 p-3 text-xs">
              <div className="rounded-md border border-slate-100 bg-slate-50 p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-slate-700">{selectedAgentLabel}</span>
                  <Badge tone="neutral">{selectedAgentId}</Badge>
                </div>
                <div className="mt-2 grid grid-cols-3 gap-2">
                  <ReadinessCheck label={text("fake", "fake")} ok={Boolean(selectedLocalAgentConnections.some((connection) => connection.adapter_kind === "fake" && connection.status !== "revoked"))} />
                  <ReadinessCheck label={text("hao", "hao")} ok={Boolean(selectedLocalAgentConnections.some((connection) => connection.adapter_kind === "hao" && connection.status !== "revoked"))} />
                  <ReadinessCheck label={text("恢复", "Resume")} ok={Boolean(selectedLocalAgentConnections.some(localAgentSupportsResume))} />
                </div>
              </div>
              <Button type="button" onClick={() => setLocalAgentDialogOpen(true)}>
                <Terminal className="h-3.5 w-3.5" /> {text("打开接入向导", "Open connection wizard")}
              </Button>
              {selectedLocalAgentConnections.length > 0 ? (
                <div className="grid gap-1">
                  {selectedLocalAgentConnections.slice(0, 2).map((connection) => (
                    <LocalAgentConnectionRow
                      key={connection.id}
                      connection={connection}
                      compact
                      onRevoke={(connectionId) => revokeLocalAgentConnectionMutation.mutate(connectionId)}
                      revokePending={revokeLocalAgentConnectionMutation.isPending}
                    />
                  ))}
                </div>
              ) : (
                <div className="rounded-md border border-slate-100 bg-white p-2 leading-5 text-slate-500">
                  {text("首次配对后会在这里显示本地设备、工作目录和恢复能力。", "After pairing, local devices, workspace roots, and resume support appear here.")}
                </div>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Wrench className="h-4 w-4" />
                {text("能力附件与就绪检查", "Capability attachments and readiness")}
              </div>
              <Badge tone={selectedAgent?.tools_json.length ? "success" : "warning"}>
                {selectedAgent?.tools_json.length ? text("可运行", "Ready") : text("缺少能力", "Needs capability")}
              </Badge>
            </CardHeader>
            <div className="grid gap-3 p-3 text-xs">
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-slate-100 bg-slate-50 p-2">
                <div className="min-w-0">
                  <div className="font-medium text-slate-700">{capabilityName}</div>
                  <div className="mt-1 font-mono text-[11px] text-slate-500">{capabilityKind}</div>
                </div>
                <Button type="button" onClick={() => setCapabilityDialogOpen(true)}>
                  <Wrench className="h-3.5 w-3.5" /> {text("配置能力附件", "Configure attachment")}
                </Button>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <ReadinessCheck label={text("MCP / 技能 / 工具", "MCP / Skill / Tool")} ok={Boolean(selectedAgent?.tools_json.length)} />
                <ReadinessCheck label={text("知识连接器", "Knowledge connector")} ok={knowledgeConnectorReady} detail={knowledgeConnectorDetail} />
                <ReadinessCheck label={text("Token 预算", "Token budget")} ok={tokenBudget >= 1024} detail={`${tokenBudget}`} />
                <ReadinessCheck label={text("策略冲突", "Policy conflicts")} ok={capabilityKind !== "high_risk_unapproved"} />
              </div>
            </div>
          </Card>
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

        <section className="grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-3">
          <StudioCapability
            icon={<Brain className="h-4 w-4" />}
            title={text("模型", "Model")}
            subtitle={text("模型配置", "Model settings")}
            status={text("接口已接入", "API-backed")}
            description={text("内置模型预置，自定义模型通过模型设置保存。", "DeepSeek presets and custom providers are saved in Model Settings.")}
            to="/settings/models"
          />
          <StudioCapability
            icon={<Wrench className="h-4 w-4" />}
            title={text("工具", "Tools")}
            subtitle={text("MCP（模型上下文协议）", "MCP (Model Context Protocol)")}
            status={text("接口已接入", "API-backed")}
            description={text("工具权限来自智能体定义和工具注册表。", "Tool access comes from Agent definitions and Tool Registry.")}
            to="/tools"
          />
          <StudioCapability
            icon={<ScrollText className="h-4 w-4" />}
            title={text("提示词", "Prompt")}
            subtitle={text("系统提示词", "System prompt")}
            status={text("只读", "Read-only")}
            description={text("当前展示智能体系统提示词摘要，编辑器留到后续阶段。", "Shows Agent system prompt summary; editor belongs to a later stage.")}
          />
          <StudioCapability
            icon={<Database className="h-4 w-4" />}
            title={text("RAG 知识检索", "RAG Knowledge Retrieval")}
            subtitle={text("检索增强生成", "Retrieval Augmented Generation")}
            status={knowledgeConnectorReady ? text("已配置", "Configured") : text("待配置", "Needs setup")}
            description={text("就绪状态来自已索引知识源，不用固定就绪占位。", "Readiness comes from indexed knowledge sources, not a fixed ready placeholder.")}
          />
          <StudioCapability
            icon={<Gauge className="h-4 w-4" />}
            title={text("Token 优化", "Token Optimizer")}
            subtitle={text("内置省 Token 方案", "Built-in token saving presets")}
            status={tokenOptimizerStatusLabel}
            description={text(
              "直接为当前智能体选择关闭、保守、均衡或强力方案；下次运行前自动调整上下文预算。",
              "Choose Off, Conservative, Balanced, or Aggressive for this Agent; the next run adjusts context budget automatically.",
            )}
          />
          <StudioCapability
            icon={<Package className="h-4 w-4" />}
            title={text("模板", "Templates")}
            subtitle={text("模板市场", "Template marketplace")}
            status={text("未启用", "Disabled")}
            description={text("模板市场保留禁用态，等待接口支撑。", "Template marketplace remains disabled until API-backed.")}
            disabled
          />
          <StudioCapability
            icon={<GitBranch className="h-4 w-4" />}
            title={text("编排", "Orchestration")}
            subtitle={text("运行详情与观测", "Run detail and observability")}
            status={text("接口已接入", "API-backed")}
            description={text("工作台只暴露计划；执行、编排和审批作为运行详情与观测能力呈现。", "Workspace exposes Plan only; execution, orchestration, and approval appear as Run detail and Harness observability.")}
          />
        </section>

        <KnowledgeManagementPanel agentId={selectedAgentId} />

        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Gauge className="h-4 w-4" />
              {text("Token 省用方案", "Token Saving Plan")}
            </div>
            <Badge tone={enabledOptimizerCount > 0 ? "success" : "neutral"}>
              {tokenOptimizerStatusLabel}
            </Badge>
          </CardHeader>
          <div className="grid gap-3 p-3 text-xs">
            <div
              aria-label={text("Token 省用方案", "Token saving plan")}
              className="grid grid-cols-1 gap-2 md:grid-cols-4"
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
                      "grid min-h-28 gap-2 rounded-md border p-3 text-left transition-colors",
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
        </Card>

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
          <div className="grid grid-cols-12 gap-3">
            {agents.data.items.map((agent) => (
              <AgentCard key={agent.id} agent={agent} />
            ))}
          </div>
        )}

        <ConfigDialog
          open={localAgentDialogOpen}
          title={text("接入本地 Agent", "Connect local Agent")}
          description={text("生成连接命令，在本地执行后由 bridge 自动注册；云端只负责会话、事件、权限和审计。", "Generate a pairing command, run it locally, then let the bridge register itself; Harness owns sessions, events, policy, and audit.")}
          onClose={() => setLocalAgentDialogOpen(false)}
          className="max-w-3xl"
        >
          <div className="grid gap-4 text-xs">
            <div className="grid grid-cols-3 gap-2">
              <WizardStep index="1" title={text("生成连接命令", "Generate command")} active={Boolean(localAgentPairing)} />
              <WizardStep index="2" title={text("本地执行", "Run locally")} active={Boolean(localAgentPairing?.command)} />
              <WizardStep index="3" title={text("自动识别", "Auto discovery")} active={selectedLocalAgentConnections.length > 0} />
            </div>

            <div className="rounded-md border border-slate-100 bg-slate-50 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="font-medium text-slate-800">{text("当前目标智能体", "Selected target Agent")}</div>
                  <div className="mt-1 text-slate-500">{selectedAgentLabel} · {selectedAgentId}</div>
                </div>
                <Button
                  type="button"
                  onClick={() => createLocalAgentPairingMutation.mutate()}
                  disabled={createLocalAgentPairingMutation.isPending}
                >
                  <PlugZap className="h-3.5 w-3.5" />
                  {localAgentPairing ? text("重新生成", "Regenerate") : text("生成连接命令", "Generate command")}
                </Button>
              </div>

              {localAgentPairing?.command ? (
                <div className="mt-3 grid gap-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <Badge tone="info">{text("配对码", "Pair code")} · {localAgentPairing.pair_code}</Badge>
                    <Badge tone="warning">{text("10 分钟内有效，单次使用", "Valid for 10 minutes, one use")}</Badge>
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
                      onClick={() => void localAgentConnections.refetch()}
                      disabled={localAgentConnections.isFetching}
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      {text("刷新识别", "Refresh discovery")}
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="mt-3 rounded-md border border-slate-200 bg-white p-3 leading-5 text-slate-500">
                  {text("点击生成后复制命令到本地终端。前台终端关闭不影响已作为 daemon 运行的 bridge。", "Generate and copy the command into a local terminal. Closing the foreground terminal does not stop a bridge already running as a daemon.")}
                </div>
              )}
            </div>

            <div className="grid gap-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="font-medium text-slate-800">{text("自动识别列表", "Auto discovery")}</div>
                <Badge tone={localAgentConnections.isFetching ? "running" : "neutral"}>
                  {localAgentConnections.isFetching ? text("刷新中", "Refreshing") : text("实时状态", "Live status")}
                </Badge>
              </div>
              <div className="grid gap-2">
                {LOCAL_AGENT_ADAPTERS.map((adapter) => {
                  const matches = selectedLocalAgentConnections.filter((connection) => connection.adapter_kind === adapter.kind);
                  return (
                    <div key={adapter.kind} className="rounded-md border border-slate-200 bg-white p-3">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <adapter.icon className="h-4 w-4 text-slate-500" />
                            <span className="font-medium text-slate-900">{adapter.label}</span>
                            <Badge tone={adapter.enabled ? "success" : "neutral"}>
                              {adapter.enabled ? text("v1 启用", "v1 enabled") : text("后续接入", "Future")}
                            </Badge>
                          </div>
                          <div className="mt-1 leading-5 text-slate-500">{text(adapter.zh, adapter.en)}</div>
                        </div>
                        <Badge tone={matches.some((connection) => connection.status === "online" || connection.status === "busy") ? "success" : matches.length ? "warning" : "pending"}>
                          {matches.some((connection) => connection.status === "online" || connection.status === "busy")
                            ? text("在线", "Online")
                            : matches.length
                              ? text("可恢复", "Recoverable")
                              : adapter.enabled
                                ? text("未识别", "Not detected")
                                : text("禁用", "Disabled")}
                        </Badge>
                      </div>
                      {matches.length > 0 ? (
                        <div className="mt-3 grid gap-2">
                          {matches.map((connection) => (
                            <LocalAgentConnectionRow
                              key={connection.id}
                              connection={connection}
                              onRevoke={(connectionId) => revokeLocalAgentConnectionMutation.mutate(connectionId)}
                              revokePending={revokeLocalAgentConnectionMutation.isPending}
                            />
                          ))}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
              {localAgentConnections.error instanceof Error ? (
                <div className="text-red-700">{localAgentConnections.error.message}</div>
              ) : null}
            </div>
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

function ReadinessCheck({ label, ok, detail }: { label: string; ok: boolean; detail?: string }) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50 p-2">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-slate-700">{label}</span>
        <Badge tone={ok ? "success" : "warning"}>{ok ? "已就绪" : "待处理"}</Badge>
      </div>
      {detail ? <div className="mt-1 text-[11px] text-slate-500">{detail}</div> : null}
    </div>
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
    icon: Monitor,
    zh: "用于验证配对、注册、心跳和一次回复，不执行本地命令。",
    en: "Validates pairing, registration, heartbeat, and one reply without local command execution.",
  },
  {
    kind: "hao",
    label: "hao",
    enabled: true,
    icon: Terminal,
    zh: "v1 真实本地 Agent 适配器，支持本地会话恢复和审计回传。",
    en: "The v1 real local Agent adapter with local session resume and audit reporting.",
  },
  {
    kind: "codex",
    label: "Codex CLI",
    enabled: false,
    icon: Bot,
    zh: "后续切片按相同 bridge protocol 接入；不支持的能力会在 UI 禁用。",
    en: "Future slice on the same bridge protocol; unsupported capabilities stay disabled.",
  },
  {
    kind: "claude_code",
    label: "Claude Code",
    enabled: false,
    icon: Brain,
    zh: "后续切片接入；v1 不发放可执行适配器。",
    en: "Future adapter slice; v1 does not issue executable support.",
  },
] as const;

function localAgentSupportsResume(connection: LocalAgentConnection) {
  return connection.capabilities_json.supports_resume === true;
}

function localAgentStatusTone(connection: LocalAgentConnection) {
  if (connection.status === "online" || connection.status === "busy") return "success";
  if (connection.status === "revoked") return "failed";
  return "warning";
}

function localAgentStatusLabel(connection: LocalAgentConnection) {
  if (connection.status === "online") return "在线";
  if (connection.status === "busy") return "运行中";
  if (connection.status === "revoked") return "已撤销";
  return "离线可恢复";
}

function LocalAgentConnectionRow({
  connection,
  compact = false,
  onRevoke,
  revokePending,
}: {
  connection: LocalAgentConnection;
  compact?: boolean;
  onRevoke: (connectionId: string) => void;
  revokePending: boolean;
}) {
  const { text } = useI18n();
  const supportsResume = localAgentSupportsResume(connection);
  return (
    <div className="rounded-md border border-slate-100 bg-white p-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span className="truncate font-medium text-slate-800">{connection.display_name}</span>
            <Badge tone={localAgentStatusTone(connection)}>{text(localAgentStatusLabel(connection), connection.status)}</Badge>
            <Badge tone={supportsResume ? "success" : "warning"}>
              {supportsResume ? text("原生恢复", "Native resume") : text("上下文重放", "Context replay")}
            </Badge>
          </div>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[11px] text-slate-500">
            <span>{connection.adapter_kind}</span>
            {connection.workspace_root ? <span>{connection.workspace_root}</span> : null}
            {!compact && connection.last_seen_at ? <span>{new Date(connection.last_seen_at).toLocaleString()}</span> : null}
          </div>
          {!compact && connection.risk_capabilities_json.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-1">
              {connection.risk_capabilities_json.map((capability) => (
                <Badge key={capability} tone="warning">{capability}</Badge>
              ))}
            </div>
          ) : null}
        </div>
        {connection.status !== "revoked" ? (
          <Button
            type="button"
            variant="ghost"
            className="shrink-0"
            onClick={() => onRevoke(connection.id)}
            disabled={revokePending}
          >
            {text("撤销", "Revoke")}
          </Button>
        ) : null}
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
      <div className="flex h-full flex-col gap-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <div className="flex min-w-0 items-center gap-2 text-sm font-semibold text-slate-900">
              {icon}
              <span className="truncate">{title}</span>
            </div>
            {subtitle ? <div className="text-[11px] leading-4 text-slate-400">{subtitle}</div> : null}
          </div>
          <Badge tone={disabled ? "neutral" : "success"} className="shrink-0 whitespace-nowrap">
            {status}
          </Badge>
        </div>
        <p className="flex-1 text-xs leading-5 text-slate-500">{description}</p>
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

function AgentCard({ agent }: { agent: AgentDefinition }) {
  const { text } = useI18n();
  return (
    <Card className="col-span-6">
      <CardHeader>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Bot className="h-4 w-4 text-slate-500" />
            <div className="truncate text-sm font-semibold text-slate-950">{agent.name}</div>
            <Badge tone="success">{statusLabel(agent.status)}</Badge>
          </div>
          <div className="mt-1 font-mono text-[11px] text-slate-500">{agent.id}</div>
        </div>
        <Link to={`/agents/${agent.id}/workspace`}>
          <Button>
            {text("打开", "Open")} <ChevronRight className="h-3.5 w-3.5" />
          </Button>
        </Link>
      </CardHeader>
      <div className="space-y-3 p-3">
        <p className="min-h-10 text-sm leading-5 text-slate-600">{agent.description}</p>
        <div className="grid grid-cols-3 gap-2 text-xs">
          <Metric icon={<Brain className="h-3.5 w-3.5" />} label={text("角色", "Role")} value={agent.role} />
          <Metric icon={<GitBranch className="h-3.5 w-3.5" />} label={text("并行", "Parallel")} value={String(agent.max_parallel_assignments)} />
          <Metric icon={<Shield className="h-3.5 w-3.5" />} label={text("模型", "Model")} value={agent.model_name} />
        </div>
        <div>
          <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-slate-700">
            <Wrench className="h-3.5 w-3.5" /> {text("工具权限", "Tool Access")}
          </div>
          <div className="flex flex-wrap gap-1">
            {agent.tools_json.map((tool) => (
              <Badge key={tool} tone={tool.includes("run") || tool.includes("write") ? "warning" : "neutral"}>
                {tool}
              </Badge>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap gap-1">
          {agent.routing_tags.map((tag) => (
            <span key={tag} className="rounded border border-slate-200 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">
              {tag}
            </span>
          ))}
        </div>
      </div>
    </Card>
  );
}

function Metric({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50 px-2 py-1.5">
      <div className="flex items-center gap-1 text-[11px] text-slate-500">
        {icon}
        {label}
      </div>
      <div className="mt-1 truncate font-mono text-xs text-slate-900">{value}</div>
    </div>
  );
}
