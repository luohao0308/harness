import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bot, Brain, ChevronRight, GitBranch, Shield, Wrench } from "lucide-react";
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
    <ConsoleShell title={text("Agent 注册表", "Agent Registry")}>
      <div className="space-y-4 p-4">
        <section className="grid grid-cols-12 gap-4">
          <div className="col-span-8">
            <h1 className="text-lg font-semibold text-slate-950">
              {text("具名 Agent", "Named Agents")}
            </h1>
            <p className="mt-1 max-w-3xl text-sm text-slate-500">
              {text(
                "这里是真正的 Agent 入口。Subagent 只是 Run 中的异步工作单元，多 Agent 编排会从这些具名 Agent 中选择参与者。",
                "This is the real Agent entry. Subagents are async work units inside a Run; orchestration chooses named Agents from this registry.",
              )}
            </p>
          </div>
          <div className="col-span-4 flex items-start justify-end">
            <Link to="/agents/default/chat">
              <Button variant="primary">
                <Bot className="h-3.5 w-3.5" /> {text("打开默认 Agent", "Open Default Agent")}
              </Button>
            </Link>
          </div>
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
        <Link to={`/agents/${agent.id}/chat`}>
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
