import type { ReactNode } from "react";
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
import { useI18n } from "../../../lib/i18n";
import { listAgents, type AgentDefinition } from "../../tasks/api";

export function AgentListPage() {
  const { text } = useI18n();
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });

  return (
    <ConsoleShell title={text("Agent Studio", "Agent Studio")}>
      <div className="space-y-4 p-4">
        <section className="grid grid-cols-12 gap-4">
          <div className="col-span-8">
            <h1 className="text-lg font-semibold text-slate-950">
              {text("Agent Studio", "Agent Studio")}
            </h1>
            <p className="mt-1 max-w-3xl text-sm text-slate-500">
              {text(
                "这里构建 Model + Harness = Agent。选择模型、工具、Prompt、沙箱和编排能力后进入 Workspace 运行。",
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
                <Bot className="h-3.5 w-3.5" /> {text("打开默认 Plan", "Open Default Plan")}
              </Button>
            </Link>
          </div>
        </section>

        <section className="grid grid-cols-6 gap-3">
          <StudioCapability
            icon={<Brain className="h-4 w-4" />}
            title={text("Model", "Model")}
            status={text("API 已接入", "API-backed")}
            description={text("DeepSeek 默认预置，自定义模型通过模型设置保存。", "DeepSeek presets and custom providers are saved in Model Settings.")}
            to="/settings/models"
          />
          <StudioCapability
            icon={<Wrench className="h-4 w-4" />}
            title={text("Tools / MCP", "Tools / MCP")}
            status={text("API 已接入", "API-backed")}
            description={text("工具权限来自 Agent 定义和 Tool Registry。", "Tool access comes from Agent definitions and Tool Registry.")}
            to="/tools"
          />
          <StudioCapability
            icon={<ScrollText className="h-4 w-4" />}
            title="Prompt"
            status={text("只读", "Read-only")}
            description={text("当前展示 Agent system prompt 摘要，编辑器留到后续阶段。", "Shows Agent system prompt summary; editor belongs to a later stage.")}
          />
          <StudioCapability
            icon={<Database className="h-4 w-4" />}
            title="RAG"
            status={text("未启用", "Disabled")}
            description={text("知识库入口保留禁用态，不展示伪造数据。", "Knowledge entry remains disabled and shows no fake data.")}
            disabled
          />
          <StudioCapability
            icon={<Package className="h-4 w-4" />}
            title={text("模板", "Templates")}
            status={text("未启用", "Disabled")}
            description={text("模板市场保留禁用态，等待 API 支撑。", "Template marketplace remains disabled until API-backed.")}
            disabled
          />
          <StudioCapability
            icon={<GitBranch className="h-4 w-4" />}
            title={text("编排", "Orchestration")}
            status={text("API 已接入", "API-backed")}
            description={text("Workspace 只暴露 Plan；执行、编排和审批作为 Run 详情与 Harness 观测能力呈现。", "Workspace exposes Plan only; execution, orchestration, and approval appear as Run detail and Harness observability.")}
          />
        </section>

        {agents.isLoading && (
          <Card>
            <div className="p-4 text-sm text-slate-500">{text("加载 Agent...", "Loading Agents...")}</div>
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
  status,
  description,
  to,
  disabled = false,
}: {
  icon: ReactNode;
  title: string;
  status: string;
  description: string;
  to?: string;
  disabled?: boolean;
}) {
  const body = (
    <Card className={disabled ? "opacity-60" : ""}>
      <div className="space-y-2 p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            {icon}
            {title}
          </div>
          <Badge tone={disabled ? "neutral" : "success"}>{status}</Badge>
        </div>
        <p className="min-h-10 text-xs leading-5 text-slate-500">{description}</p>
      </div>
    </Card>
  );
  if (!to || disabled) {
    return body;
  }
  return <Link to={to}>{body}</Link>;
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
