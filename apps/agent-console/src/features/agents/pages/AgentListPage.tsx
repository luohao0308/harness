import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  Brain,
  ChevronRight,
  Database,
  GitBranch,
  Package,
  PackagePlus,
  Gauge,
  ScrollText,
  Settings,
  Shield,
  Wrench,
} from "lucide-react";
import { Link } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { ConfigDialog } from "../../../components/ui/config-dialog";
import { Input, Textarea } from "../../../components/ui/input";
import { Card, CardHeader } from "../../../components/ui/card";
import { MenuSelect } from "../../../components/ui/menu-select";
import { cn } from "../../../lib/utils";
import { useI18n } from "../../../lib/i18n";
import {
  attachAgentCapability,
  cloneAgentDefinition,
  createAgentDefinition,
  listTokenOptimizerPresets,
  listAgentKnowledgeSources,
  listAgents,
  selectAgentTokenOptimizer,
  type AgentCapabilityAttachmentSummary,
  type AgentDefinition,
  type KnowledgeSource,
  type TokenOptimizerPresetId,
} from "../../tasks/api";
import { KnowledgeManagementPanel } from "../components/KnowledgeManagementPanel";

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
  const selectedKnowledgeSources = useQuery({
    queryKey: ["agent-knowledge", selectedAgentId],
    queryFn: () => listAgentKnowledgeSources(selectedAgentId),
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
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["agents"] }),
  });
  const cloneAgentMutation = useMutation({
    mutationFn: () =>
      cloneAgentDefinition({
        source_agent_id: selectedAgentId,
        id: `${selectedAgentId}-clone`,
        name: `${selectedAgentLabel} Clone`,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["agents"] }),
  });
  const attachCapabilityMutation = useMutation({
    mutationFn: () =>
      attachAgentCapability(selectedAgentId, {
        capability_id: capabilityName,
        capability_version_id: null,
        enabled: true,
        priority: 10,
      }),
    onSuccess: () => {
      setCapabilityDialogOpen(false);
      return queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
  });
  const selectTokenOptimizerMutation = useMutation({
    mutationFn: (presetId: TokenOptimizerPresetId) =>
      selectAgentTokenOptimizer(selectedAgentId, presetId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["agents"] }),
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

        <section className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <PackagePlus className="h-4 w-4" />
                {text("创建 / 克隆 Agent", "Create / clone Agent")}
              </div>
              <Badge tone={createAgentMutation.isSuccess || cloneAgentMutation.isSuccess ? "success" : "info"}>
                {text("API 支撑", "API-backed")}
              </Badge>
            </CardHeader>
            <div className="grid gap-3 p-3 text-xs">
              <div className="grid grid-cols-2 gap-2">
                <label className="grid gap-1">
                  <span className="font-medium text-slate-600">Agent ID</span>
                  <Input aria-label="新 Agent ID" value={draftAgentId} onChange={(event) => setDraftAgentId(event.target.value)} />
                </label>
                <label className="grid gap-1">
                  <span className="font-medium text-slate-600">{text("名称", "Name")}</span>
                  <Input aria-label="新 Agent 名称" value={draftAgentName} onChange={(event) => setDraftAgentName(event.target.value)} />
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
                  <Bot className="h-3.5 w-3.5" /> {text("创建 Agent", "Create Agent")}
                </Button>
                <Button onClick={() => cloneAgentMutation.mutate()} disabled={cloneAgentMutation.isPending}>
                  {text("克隆当前 Agent", "Clone selected Agent")}
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
                <ReadinessCheck label={text("MCP / Skill / Tool", "MCP / Skill / Tool")} ok={Boolean(selectedAgent?.tools_json.length)} />
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
              "直接为当前 Agent 选择关闭、保守、均衡或强力方案；下次运行前自动调整上下文预算。",
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
                  "当前 Agent 启用了高级自定义 Token 优化。选择上方任一内置方案会切换到该方案。",
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
          open={capabilityDialogOpen}
          title={text("配置能力附件", "Configure capability attachment")}
          description={text("为当前 Agent 附加 MCP、Skill 或工具能力；保存后刷新就绪检查。", "Attach an MCP, Skill, or tool capability to the current Agent; readiness refreshes after save.")}
          onClose={() => setCapabilityDialogOpen(false)}
        >
          <div className="grid gap-3 text-xs">
            <div className="rounded-md border border-slate-100 bg-slate-50 p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-slate-700">{selectedAgentLabel}</span>
                <Badge tone="neutral">{selectedAgentId}</Badge>
              </div>
              <p className="mt-2 leading-5 text-slate-500">
                {text("附件会进入 Agent 作用域，运行时通过能力注册表和工具执行器解析。", "The attachment is scoped to this Agent and resolved through the capability registry and ToolRunner at runtime.")}
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
              <Wrench className="h-3.5 w-3.5" /> {text("附加到当前 Agent", "Attach to selected Agent")}
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
        <Badge tone={ok ? "success" : "warning"}>{ok ? "ready" : "warning"}</Badge>
      </div>
      {detail ? <div className="mt-1 text-[11px] text-slate-500">{detail}</div> : null}
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
            <Badge tone="success">{agent.status}</Badge>
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
