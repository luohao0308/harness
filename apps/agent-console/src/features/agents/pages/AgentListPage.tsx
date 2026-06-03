import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bot,
  Brain,
  ChevronRight,
  Database,
  GitBranch,
  Package,
  ScrollText,
  Settings,
  Shield,
  Wrench,
} from "lucide-react";
import { Link } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { MenuSelect } from "../../../components/ui/menu-select";
import { cn } from "../../../lib/utils";
import { useI18n } from "../../../lib/i18n";
import { listAgents, type AgentDefinition } from "../../tasks/api";
import { KnowledgeManagementPanel } from "../components/KnowledgeManagementPanel";

export function AgentListPage() {
  const { text } = useI18n();
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const [selectedAgentId, setSelectedAgentId] = useState("default");
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
            status={text("接口已接入", "API-backed")}
            description={text("知识源可创建并回看持久化文档与索引状态。", "Knowledge sources can be created and revisited as persisted documents and index state.")}
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
      </div>
    </ConsoleShell>
  );
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
