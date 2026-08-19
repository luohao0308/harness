import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bot, Cable, FileText, Layers, Radar } from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, type BadgeTone } from "../../../components/ui/badge";
import { Card, CardHeader } from "../../../components/ui/card";
import { MenuSelect } from "../../../components/ui/menu-select";
import { useI18n } from "../../../lib/i18n";
import { listAgents, listAgentKnowledgeSources, type KnowledgeSource } from "../../tasks/api";
import {
  filterKnowledgeSources,
  KnowledgeManagementPanel,
  type KnowledgeSourceFilter,
} from "../../agents/components/KnowledgeManagementPanel";
import { ProjectKnowledgeIndexPanel } from "../components/ProjectKnowledgeIndexPanel";

const filterOptions: Array<{
  id: KnowledgeSourceFilter;
  label: string;
  description: string;
}> = [
  { id: "all", label: "全部", description: "本地文档和 API 配置" },
  { id: "local", label: "本地", description: ".txt / .md / 手动文本" },
  { id: "api", label: "API", description: "Coze / Dify / LangChain / RAGFlow" },
  { id: "preview", label: "预览", description: "未计入可运行的连接器" },
];

export function KnowledgePage() {
  const { text } = useI18n();
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const [selectedAgentId, setSelectedAgentId] = useState("default");
  const [sourceFilter, setSourceFilter] = useState<KnowledgeSourceFilter>("all");
  const knowledgeSources = useQuery({
    queryKey: ["agent-knowledge", selectedAgentId],
    queryFn: () => listAgentKnowledgeSources(selectedAgentId),
  });
  const selectedAgent = useMemo(
    () => agents.data?.items.find((agent) => agent.id === selectedAgentId) ?? null,
    [agents.data?.items, selectedAgentId],
  );
  const sources = knowledgeSources.data?.items ?? [];
  const stats = knowledgeStats(sources);
  const filterCount = (filter: KnowledgeSourceFilter) =>
    filterKnowledgeSources(sources, filter).length;
  const longDescription = text(
    "Dify 和 Coze 可在本地证据不足时参与运行时检索，LangChain Retriever 保存 grounding adapter 配置，RAGFlow 和本地端点仍为配置和预检状态。",
    "Dify and Coze can participate in runtime retrieval, LangChain Retriever stores grounding adapter config, and RAGFlow/local endpoints remain configuration and readiness only.",
  );

  return (
    <ConsoleShell title={text("知识库", "Knowledge Base")}>
      <div className="space-y-4 p-4">
        <section className="grid grid-cols-12 gap-4">
          <div className="col-span-12 xl:col-span-7">
            <h1 className="text-lg font-semibold text-slate-950">
              {text("知识库", "Knowledge Base")}
            </h1>
            <p className="mt-1 max-w-3xl truncate text-sm leading-6 text-slate-500" title={longDescription}>
              {text(
                "集中管理本地文档索引和外部知识库 API 配置；筛选按钮显示当前结果数。",
                "Manage local indexes and external knowledge APIs; filter buttons show current result counts.",
              )}
            </p>
          </div>
          <div className="col-span-12 xl:col-span-5">
            <Card>
              <CardHeader>
                <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                  <Bot className="h-4 w-4" />
                  {text("智能体作用域", "Agent scope")}
                </div>
              </CardHeader>
              <div className="p-3">
                <MenuSelect
                  ariaLabel={text("知识库智能体", "Knowledge base agent")}
                  value={selectedAgentId}
                  onChange={setSelectedAgentId}
                  placeholder={selectedAgent?.name ?? selectedAgentId}
                  className="w-full"
                  buttonClassName="h-10 rounded-md px-3 py-2 shadow-none"
                  menuClassName="w-full"
                  options={(agents.data?.items ?? [{ id: "default", name: "默认智能体", description: "" }]).map(
                    (agent) => ({
                      value: agent.id,
                      label: agent.id === "default" ? text("默认智能体", "Default Agent") : agent.name,
                      description: agent.description || agent.id,
                      meta: agent.id,
                      leading: <Bot className="h-4 w-4" />,
                    }),
                  )}
                />
              </div>
            </Card>
          </div>
        </section>

        <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <KnowledgeMetric icon={<Layers className="h-4 w-4" />} label="全部来源" value={sources.length} tone="info" />
          <KnowledgeMetric icon={<FileText className="h-4 w-4" />} label="本地入库" value={stats.local} tone="success" />
          <KnowledgeMetric icon={<Cable className="h-4 w-4" />} label="API 配置" value={stats.api} tone="warning" />
          <KnowledgeMetric icon={<Radar className="h-4 w-4" />} label="可用" value={stats.usable} tone="success" />
        </section>

        <section className="flex flex-wrap gap-2">
          {filterOptions.map((option) => (
            <button
              key={option.id}
              type="button"
              aria-pressed={sourceFilter === option.id}
              className={`rounded-md border px-3 py-2 text-left text-xs transition ${
                sourceFilter === option.id
                  ? "border-slate-900 bg-slate-50 text-slate-950"
                  : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
              }`}
              onClick={() => setSourceFilter(option.id)}
            >
              <span className="flex items-center justify-between gap-3 font-semibold">
                <span>{option.label}</span>
                <span className="rounded border border-current/20 px-1.5 py-0.5 font-mono text-[10px]">
                  {filterCount(option.id)}
                </span>
              </span>
              <span className="text-[11px] text-slate-500">{option.description}</span>
            </button>
          ))}
        </section>

        <ProjectKnowledgeIndexPanel agentId={selectedAgentId} />

        <KnowledgeManagementPanel
          agentId={selectedAgentId}
          sourceFilter={sourceFilter}
          variant="workbench"
        />
      </div>
    </ConsoleShell>
  );
}

function knowledgeStats(sources: KnowledgeSource[]) {
  return sources.reduce(
    (acc, source) => {
      if (source.source_type === "connector") {
        acc.api += 1;
        if (source.connector_counts_toward_complete_usable) {
          acc.usable += 1;
        }
      } else {
        acc.local += 1;
        if (
          source.status === "ACTIVE" &&
          source.health_status === "HEALTHY" &&
          source.latest_documents.some((document) => document.status === "INDEXED")
        ) {
          acc.usable += 1;
        }
      }
      return acc;
    },
    { local: 0, api: 0, usable: 0 },
  );
}

function KnowledgeMetric({
  icon,
  label,
  value,
  tone,
}: {
  icon: ReactNode;
  label: string;
  value: number;
  tone: BadgeTone;
}) {
  return (
    <Card>
      <div className="flex min-h-20 items-center justify-between gap-3 p-3">
        <div>
          <div className="text-xs text-slate-500">{label}</div>
          <div className="mt-1 text-2xl font-semibold text-slate-950">{value}</div>
        </div>
        <Badge tone={tone}>{icon}</Badge>
      </div>
    </Card>
  );
}
