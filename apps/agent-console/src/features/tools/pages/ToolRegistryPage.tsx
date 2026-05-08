import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PlugZap, ShieldCheck } from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { useI18n } from "../../../lib/i18n";
import { booleanLabel, riskLabel } from "../../../lib/labels";
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

  return (
    <ConsoleShell title={text("工具运行层", "Tool Runtime")}>
      <div className="space-y-4 p-4">
        <div className="grid grid-cols-4 gap-3">
          <Metric label={text("工具总数", "Tools")} value={tools.length} />
          <Metric label="MCP" value={mcpCount} />
          <Metric label={text("需要沙箱", "Sandboxed")} value={sandboxCount} />
          <Metric label={text("分类", "Categories")} value={registryQuery.data?.categories.length ?? 0} />
        </div>

        <Card>
          <CardHeader>
            <div>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <PlugZap className="h-4 w-4" />
                {text("统一 Tool Registry", "Unified Tool Registry")}
              </div>
              <div className="mt-1 text-xs text-slate-500">
                {text(
                  "内置工具和 MCP-shaped 工具共用权限、策略、ToolCall 审计和 trace。",
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
                  {source}
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
                <Th>{text("MCP", "MCP")}</Th>
                <Th>{text("Schema", "Schema")}</Th>
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
                    <Badge tone={tool.source === "mcp" ? "info" : "neutral"}>{tool.source}</Badge>
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
                  <Td colSpan={6} className="py-10 text-center text-slate-500">
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

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <Card className="p-4">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="mt-1 font-mono text-2xl text-slate-900">{value}</div>
    </Card>
  );
}
