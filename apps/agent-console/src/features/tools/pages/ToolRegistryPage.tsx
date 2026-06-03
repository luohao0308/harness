import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { GitBranch, PlugZap, ShieldAlert, ShieldCheck, Timer, Workflow } from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { TermHint } from "../../../components/ui/term";
import { useI18n } from "../../../lib/i18n";
import { booleanLabel, riskLabel, toolSourceLabel } from "../../../lib/labels";
import { getToolRegistry } from "../../tasks/api";

export function ToolRegistryPage() {
  const { text } = useI18n();
  const [sourceFilter, setSourceFilter] = useState("all");
  const registryQuery = useQuery({ queryKey: ["tool-registry"], queryFn: getToolRegistry });
  const tools = registryQuery.data?.items ?? [];
  const filteredTools = useMemo(
    () => tools.filter((tool) => sourceFilter === "all" || tool.source === sourceFilter),
    [sourceFilter, tools],
  );
  const mcpCount = tools.filter((tool) => tool.source === "mcp").length;
  const sandboxCount = tools.filter((tool) => tool.requires_sandbox).length;
  const highRiskCount = tools.filter((tool) => ["high", "critical"].includes(tool.risk_level)).length;
  const adminOnlyCount = tools.filter((tool) => tool.allowed_roles.includes("admin")).length;

  return (
    <ConsoleShell title={text("工具运行层", "Tool Runtime")}>
      <div className="space-y-4 p-4">
        <section className="grid grid-cols-4 gap-3">
          <Metric label={text("工具总数", "Tools")} value={tools.length} />
          <Metric label={<TermHint description="模型上下文协议，用于接入外部工具">MCP</TermHint>} value={mcpCount} />
          <Metric label={text("需要沙箱", "Sandboxed")} value={sandboxCount} />
          <Metric label={text("分类", "Categories")} value={registryQuery.data?.categories.length ?? 0} />
        </section>

        <section className="grid grid-cols-5 gap-3">
          <HarnessTile
            icon={<PlugZap className="h-4 w-4" />}
            title={text("工具注册表", "Tool Registry")}
            status={text("接口已接入", "API-backed")}
            description={text("工具元数据、来源、结构说明、风险和角色权限来自后端注册表。", "Metadata, source, schema, risk, and role access come from the backend registry.")}
          />
          <HarnessTile
            icon={<ShieldAlert className="h-4 w-4" />}
            title={text("策略", "Policy")}
            status={`${highRiskCount} ${text("高风险", "high risk")}`}
            description={text("高风险工具进入沙箱、审批或拒绝路径，并写入审计事件。", "High-risk tools enter sandbox, approval, or denial paths and append audit events.")}
          />
          <HarnessTile
            icon={<ShieldCheck className="h-4 w-4" />}
            title={text("沙箱", "Sandbox")}
            status={`${sandboxCount} ${text("需要隔离", "isolated")}`}
            description={text("命令行、测试、写文件、版本控制和网络动作通过容器沙箱执行。", "Shell, tests, writes, Git, and network actions run through Docker Sandbox.")}
          />
          <HarnessTile
            icon={<GitBranch className="h-4 w-4" />}
            title={<TermHint description="模型上下文协议，用于接入外部工具">MCP</TermHint>}
            status={`${mcpCount} ${text("已注册", "registered")}`}
            description={text("外部协议形态工具复用同一工具执行器、策略、工具调用审计和事件路径。", "MCP-shaped tools reuse the same ToolRunner, Policy, ToolCall, and Event path.")}
          />
          <HarnessTile
            icon={<Workflow className="h-4 w-4" />}
            title={text("触发器", "Triggers")}
            status={text("未启用", "Disabled")}
            description={text("触发器配置保留禁用态，不展示伪造数据。", "Trigger configuration stays disabled and shows no fake data.")}
            disabled
          />
        </section>

        <Card>
          <CardHeader>
            <div>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <PlugZap className="h-4 w-4" />
                {text("统一工具注册表", "Unified Tool Registry")}
              </div>
              <div className="mt-1 text-xs text-slate-500">
                {text(
                  "内置工具和外部协议形态工具共用权限、策略、工具调用审计和跨服务追踪链路。",
                  "Built-in and MCP-shaped tools share permissions, policy, ToolCall audit, and trace.",
                )}
              </div>
            </div>
            <div className="flex gap-2">
              {["all", ...(registryQuery.data?.sources ?? [])].map((source) => (
                <Button
                  key={source}
                  variant={sourceFilter === source ? "primary" : "ghost"}
                  onClick={() => setSourceFilter(source)}
                >
                  {toolSourceLabel(source)}
                </Button>
              ))}
            </div>
          </CardHeader>
          <Table>
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <Th>{text("工具", "Tool")}</Th>
                <Th>{text("来源", "Source")}</Th>
                <Th>{text("风险", "Risk")}</Th>
                <Th>{text("权限", "Permissions")}</Th>
                <Th>{text("审计", "Audit")}</Th>
                <Th>
                  <TermHint description="模型上下文协议，用于接入外部工具">MCP</TermHint>
                </Th>
                <Th>
                  <TermHint description="结构说明，描述工具入参格式">Schema</TermHint>
                </Th>
              </tr>
            </thead>
            <tbody>
              {filteredTools.map((tool) => (
                <tr key={tool.name} className="border-t border-slate-100">
                  <Td>
                    <div className="font-mono text-slate-900">{tool.name}</div>
                    <div className="mt-0.5 max-w-[360px] text-[11px] text-slate-500">
                      {tool.description}
                    </div>
                  </Td>
                  <Td>
                    <Badge tone={tool.source === "mcp" ? "info" : "neutral"}>{toolSourceLabel(tool.source)}</Badge>
                    <div className="mt-1 text-[11px] text-slate-500">{tool.category}</div>
                  </Td>
                  <Td>
                    <Badge tone={statusTone(tool.risk_level)}>{riskLabel(tool.risk_level)}</Badge>
                    <div className="mt-1 text-[11px] text-slate-500">
                      {tool.network_policy} · {tool.timeout_seconds}s
                    </div>
                  </Td>
                  <Td>
                    <div className="inline-flex items-center gap-1.5 text-xs text-slate-700">
                      <ShieldCheck className="h-3.5 w-3.5" />
                      {booleanLabel(tool.requires_sandbox)}
                    </div>
                    <div className="mt-1 font-mono text-[11px] text-slate-500">
                      {tool.allowed_roles.join(", ")}
                    </div>
                  </Td>
                  <Td>
                    <div className="inline-flex items-center gap-1.5 text-xs text-slate-700">
                      <Timer className="h-3.5 w-3.5" />
                      {tool.audit_level}
                    </div>
                    <div className="mt-1 text-[11px] text-slate-500">
                      {adminOnlyCount > 0 && tool.allowed_roles.includes("admin")
                        ? text("仅管理员", "Admin only")
                        : text("按角色限定", "Role scoped")}
                    </div>
                  </Td>
                  <Td className="font-mono text-[11px] text-slate-600">
                    {tool.mcp_server ? `${tool.mcp_server}.${tool.mcp_method}` : "--"}
                  </Td>
                  <Td>
                    <pre className="max-h-24 max-w-[280px] overflow-auto rounded border border-slate-100 bg-slate-50 p-2 font-mono text-[10px] text-slate-600">
                      {JSON.stringify(tool.input_schema, null, 2)}
                    </pre>
                  </Td>
                </tr>
              ))}
              {!registryQuery.isLoading && filteredTools.length === 0 && (
                <tr>
                  <Td colSpan={7} className="py-10 text-center text-slate-500">
                    {text("没有符合筛选的工具", "No tools match the filter")}
                  </Td>
                </tr>
              )}
            </tbody>
          </Table>
        </Card>
      </div>
    </ConsoleShell>
  );
}

function HarnessTile({
  icon,
  title,
  status,
  description,
  disabled = false,
}: {
  icon: React.ReactNode;
  title: React.ReactNode;
  status: string;
  description: string;
  disabled?: boolean;
}) {
  return (
    <Card className={disabled ? "p-3 opacity-60" : "p-3"}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          {icon}
          {title}
        </div>
        <Badge tone={disabled ? "neutral" : "success"}>{status}</Badge>
      </div>
      <p className="mt-2 min-h-12 text-xs leading-5 text-slate-500">{description}</p>
    </Card>
  );
}

function Metric({ label, value }: { label: React.ReactNode; value: number }) {
  return (
    <Card className="p-4">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="mt-1 font-mono text-2xl text-slate-900">{value}</div>
    </Card>
  );
}
