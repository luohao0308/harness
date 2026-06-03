import { useNavigate } from "react-router-dom";
import {
  ChevronRight,
  Code2,
  GitBranch,
  PackagePlus,
  PlugZap,
  Search,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Timer,
  Workflow,
} from "lucide-react";

import { Badge, statusTone } from "../../../../components/ui/badge";
import { Button } from "../../../../components/ui/button";
import { Card, CardHeader } from "../../../../components/ui/card";
import { Table, Td, Th } from "../../../../components/ui/table";
import { TermHint } from "../../../../components/ui/term";
import { useI18n } from "../../../../lib/i18n";
import { booleanLabel, riskLabel, toolSourceLabel } from "../../../../lib/labels";
import type {
  AdapterMetadata,
  CapabilityMarketplaceItem,
  CapabilityPackage,
  ToolMetadata,
} from "../../../tasks/api";
import {
  localizedCapabilityDescription,
  mcpConfigHint,
  mcpUseSummary,
} from "../../lib/mcpDescriptions";
import { AdapterCell, HarnessTile, MarketStat, Metric, MutationError } from "./components";
import {
  capabilityPackageStatusLabel,
  marketplaceInstallStateMeta,
  sandboxReleasePathLabel,
  toolAuditLevelLabel,
  toolNetworkPolicyLabel,
} from "./labels";
import type { MarketplaceInstallState, ToolConfigDialog } from "./types";

type OpenDialog = (dialog: NonNullable<ToolConfigDialog>) => void;

type ToolRegistryOverviewProps = {
  toolsCount: number;
  mcpCount: number;
  sandboxCount: number;
  categoryCount: number;
  highRiskCount: number;
  sandboxReleasePath: string;
  marketplaceItems: CapabilityMarketplaceItem[];
  marketplaceReadySources: number;
  marketplaceSourceCount: number;
  marketplaceIsError: boolean;
  marketplaceIsFetching: boolean;
  marketplaceHasErrors: boolean;
  selectedAgentDisplayLabel: string;
  selectedMarketplaceInstallState: MarketplaceInstallState;
  latestPackage: CapabilityPackage | null;
  marketplaceCardError: unknown;
  onOpenDialog: OpenDialog;
};

export function ToolRegistryOverview({
  toolsCount,
  mcpCount,
  sandboxCount,
  categoryCount,
  highRiskCount,
  sandboxReleasePath,
  marketplaceItems,
  marketplaceReadySources,
  marketplaceSourceCount,
  marketplaceIsError,
  marketplaceIsFetching,
  marketplaceHasErrors,
  selectedAgentDisplayLabel,
  selectedMarketplaceInstallState,
  latestPackage,
  marketplaceCardError,
  onOpenDialog,
}: ToolRegistryOverviewProps) {
  const { text } = useI18n();
  const navigate = useNavigate();

  return (
    <>
      <section className="grid grid-cols-4 gap-3">
        <Metric label={text("工具总数", "Tools")} value={toolsCount} />
        <Metric label={<TermHint description="模型上下文协议，用于接入外部工具">MCP</TermHint>} value={mcpCount} />
        <Metric label={text("需要沙箱", "Sandboxed")} value={sandboxCount} />
        <Metric label={text("分类", "Categories")} value={categoryCount} />
      </section>

      <section className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <PackagePlus className="h-4 w-4" />
              {text("MCP / 技能商店", "MCP / Skill Marketplace")}
            </div>
            <Badge tone={marketplaceIsError ? "warning" : "info"}>
              {marketplaceIsFetching ? text("同步中", "Syncing") : `${marketplaceItems.length} ${text("条", "items")}`}
            </Badge>
          </CardHeader>
          <div className="grid gap-3 p-3 text-xs text-slate-500">
            <div className="grid gap-2 sm:grid-cols-3">
              <MarketStat label={text("可用来源", "Ready sources")} value={`${marketplaceReadySources}/${marketplaceSourceCount}`} />
              <MarketStat label={text("MCP", "MCP")} value={String(marketplaceItems.filter((item) => item.kind === "mcp").length)} />
              <MarketStat label={text("技能", "Skill")} value={String(marketplaceItems.filter((item) => item.kind === "skill").length)} />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="neutral">目标智能体 · {selectedAgentDisplayLabel}</Badge>
              <Badge tone="success">{marketplaceInstallStateMeta(selectedMarketplaceInstallState).label}</Badge>
              <Badge tone="info">{text("官方 MCP 注册表", "Official MCP Registry")}</Badge>
              <Badge tone="info">Smithery MCP 服务库</Badge>
              <Badge tone="info">{text("Smithery 技能库", "Smithery Skills")}</Badge>
              {marketplaceHasErrors ? (
                <span className="text-amber-700">
                  {text("部分来源降级为本地推荐。", "Some sources fell back to curated entries.")}
                </span>
              ) : null}
            </div>
            <div className="rounded-xl border border-cyan-100 bg-cyan-50 px-3 py-3 text-cyan-900">
              <div className="text-sm font-semibold">新手安装向导</div>
              <div className="mt-2 grid gap-1 leading-5">
                <span>1. 先打开商店，选择 MCP 或技能。</span>
                <span>2. 看右侧状态提示，按“登记 / 审批 / 安装”顺序完成。</span>
                <span>3. 安装后用内置测试案例立即验证能力是否生效。</span>
                <span>4. 成功或失败都会在页面右上角给出明确反馈。</span>
              </div>
            </div>
            <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
              <div className="leading-5">
                {text(
                  "商店负责发现、登记和安装引导；外部条目不会直接下载或运行，必须通过审批后才能进入智能体附件。",
                  "Marketplace discovery registers metadata only; external entries are not downloaded or run before approval.",
                )}
              </div>
              <Button type="button" variant="primary" onClick={() => onOpenDialog("marketplace")}>
                <Search className="h-3.5 w-3.5" />
                {text("打开安装向导", "Open marketplace")}
              </Button>
              <Button type="button" variant="secondary" onClick={() => navigate("/tools/config")}>
                <SlidersHorizontal className="h-3.5 w-3.5" />
                运行配置
              </Button>
              <Button type="button" variant="secondary" onClick={() => onOpenDialog("mcp-servers")}>
                <GitBranch className="h-3.5 w-3.5" />
                MCP Servers
              </Button>
              <Button type="button" variant="secondary" onClick={() => onOpenDialog("code-interpreter")}>
                <Code2 className="h-3.5 w-3.5" />
                Code Interpreter
              </Button>
            </div>
            <MutationError error={marketplaceCardError} />
          </div>
        </Card>

        <Card className="self-start">
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <PackagePlus className="h-4 w-4" />
              {text("高级包管理", "Advanced Packages")}
            </div>
            <Badge tone={latestPackage?.status === "approved" ? "success" : "neutral"}>
              {latestPackage ? capabilityPackageStatusLabel(latestPackage.status) : text("点击配置", "Open to configure")}
            </Badge>
          </CardHeader>
          <div className="space-y-3 p-3 text-xs text-slate-500">
            <p>
              {text(
                "市场导入会先走预检；可信 URL、上传、固定版本、审批、回滚和测试调用仍可在这里手动处理。",
                "Marketplace imports enter preflight first; trusted URL, upload, pinned versions, approvals, rollback, and test invoke remain available here.",
              )}
            </p>
            <div className="grid grid-cols-2 gap-2">
              <Button type="button" variant="secondary" onClick={() => onOpenDialog("trusted-url")}>
                <PackagePlus className="h-3.5 w-3.5" />
                {text("可信 URL", "Trusted URL")}
              </Button>
              <Button type="button" variant="secondary" onClick={() => onOpenDialog("public-url")}>
                <ShieldAlert className="h-3.5 w-3.5" />
                {text("公网预检", "Public preflight")}
              </Button>
              <Button type="button" variant="secondary" onClick={() => onOpenDialog("upload")}>
                <PackagePlus className="h-3.5 w-3.5" />
                {text("上传技能", "Upload Skill")}
              </Button>
              <Button type="button" variant="secondary" onClick={() => onOpenDialog("lifecycle")}>
                <ChevronRight className="h-3.5 w-3.5" />
                {text("生命周期", "Lifecycle")}
              </Button>
              <Button type="button" variant="secondary" className="col-span-2" onClick={() => onOpenDialog("test-invoke")}>
                <PlugZap className="h-3.5 w-3.5" />
                {text("测试调用", "Test invoke")}
              </Button>
              <Button type="button" variant="secondary" className="col-span-2" onClick={() => onOpenDialog("langgraph-workflow")}>
                <Workflow className="h-3.5 w-3.5" />
                LangGraph Workflow
              </Button>
              <Button type="button" variant="secondary" className="col-span-2" onClick={() => onOpenDialog("langchain-adapter")}>
                <PlugZap className="h-3.5 w-3.5" />
                LangChain Adapter
              </Button>
            </div>
          </div>
        </Card>
      </section>

      <section className="grid grid-cols-1 gap-3 md:grid-cols-3 xl:grid-cols-6">
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
          status={sandboxReleasePathLabel(sandboxReleasePath)}
          description={text("v1 本地路径使用无容器验证；高风险能力走沙箱或策略约束，Docker 私有部署烟测为可选项。", "The v1 local path is no-container; high-risk capabilities use sandbox or policy gates, and Docker private smoke is optional.")}
        />
        <HarnessTile
          icon={<GitBranch className="h-4 w-4" />}
          title={<TermHint description="模型上下文协议，用于接入外部工具">MCP</TermHint>}
          status={`${mcpCount} ${text("已注册", "registered")}`}
          description={text("MCP-shaped 工具复用同一工具执行器；LangChain tools 也只作为 MCP-shaped adapter 进入这里。", "MCP-shaped tools reuse ToolRunner; LangChain tools enter only through this MCP-shaped adapter path.")}
        />
        <HarnessTile
          icon={<Workflow className="h-4 w-4" />}
          title="LangGraph Workflow"
          status={text("非工具能力包", "Non-tool package")}
          description={text("Workflow 通过不可变能力包导入、审批和挂载；运行证据写入 Task/Step/Event。", "Workflows are imported, approved, and attached as immutable packages; runtime evidence stays in Task/Step/Event.")}
        />
        <HarnessTile
          icon={<Workflow className="h-4 w-4" />}
          title={text("触发器", "Triggers")}
          status={text("未启用", "Disabled")}
          description={text("触发器配置保留禁用态，不展示伪造数据。", "Trigger configuration stays disabled and shows no fake data.")}
          disabled
        />
      </section>
    </>
  );
}

type ToolRegistryTableProps = {
  filteredTools: ToolMetadata[];
  registrySources: string[];
  registryLoading: boolean;
  sourceFilter: string;
  onSourceFilterChange: (source: string) => void;
  selectedAgentDisplayLabel: string;
  adminOnlyCount: number;
  adapterBySlug: Map<string, AdapterMetadata>;
  simpleAgentId: string;
  onOpenAdapter: (slug: string) => void;
};

export function ToolRegistryTable({
  filteredTools,
  registrySources,
  registryLoading,
  sourceFilter,
  onSourceFilterChange,
  selectedAgentDisplayLabel,
  adminOnlyCount,
  adapterBySlug,
  simpleAgentId,
  onOpenAdapter,
}: ToolRegistryTableProps) {
  const { text } = useI18n();

  return (
    <Card>
      <CardHeader>
        <div>
          <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
            <PlugZap className="h-4 w-4" />
            {text("统一工具注册表", "Unified Tool Registry")}
          </div>
          <div className="mt-1 text-xs text-slate-500">
            {text(
              `当前显示 ${selectedAgentDisplayLabel} 已启用的工具。安装 MCP 或技能后，成功启用的工具会自动出现在这里。`,
              "Built-in and MCP-shaped tools share permissions, policy, ToolCall audit, and trace.",
            )}
          </div>
        </div>
        <div className="flex gap-2">
          {["all", ...registrySources].map((source) => (
            <Button
              key={source}
              variant={sourceFilter === source ? "primary" : "ghost"}
              onClick={() => onSourceFilterChange(source)}
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
            <Th>Adapter</Th>
            <Th>
              <TermHint description="结构说明，描述工具入参格式">结构说明</TermHint>
            </Th>
          </tr>
        </thead>
        <tbody>
          {filteredTools.map((tool) => (
            <tr key={tool.name} className="border-t border-slate-100">
              <Td>
                <div className="font-mono text-slate-900">{tool.name}</div>
                <div className="mt-0.5 max-w-[360px] text-[11px] text-slate-500">
                  {(() => {
                    const localized = localizedCapabilityDescription(tool);
                    const original = tool.description ?? "";
                    if (localized && localized !== original) return localized;
                    return tool.source === "mcp" ? mcpUseSummary(tool) : localized;
                  })()}
                </div>
                {tool.source === "mcp" ? (
                  <div className="mt-1 max-w-[360px] text-[11px] leading-4 text-cyan-800">
                    配置：{mcpConfigHint(tool)}
                  </div>
                ) : null}
              </Td>
              <Td>
                <Badge tone={tool.source === "mcp" ? "info" : "neutral"}>{toolSourceLabel(tool.source)}</Badge>
                <div className="mt-1 text-[11px] text-slate-500">{tool.category}</div>
              </Td>
              <Td>
                <Badge tone={statusTone(tool.risk_level)}>{riskLabel(tool.risk_level)}</Badge>
                <div className="mt-1 text-[11px] text-slate-500">
                  {toolNetworkPolicyLabel(tool.network_policy)} · {tool.timeout_seconds} 秒
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
                  {toolAuditLevelLabel(tool.audit_level)}
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
                {adapterBySlug.get(tool.name) ? (
                  <AdapterCell
                    adapter={adapterBySlug.get(tool.name)!}
                    agentId={simpleAgentId}
                    onOpen={() => onOpenAdapter(tool.name)}
                  />
                ) : (
                  <span className="text-xs text-slate-400">--</span>
                )}
              </Td>
              <Td>
                <pre className="max-h-24 max-w-[280px] overflow-auto rounded border border-slate-100 bg-slate-50 p-2 font-mono text-[10px] text-slate-600">
                  {JSON.stringify(tool.input_schema, null, 2)}
                </pre>
              </Td>
            </tr>
          ))}
          {!registryLoading && filteredTools.length === 0 && (
            <tr>
              <Td colSpan={8} className="py-10 text-center text-slate-500">
                {text("没有符合筛选的工具", "No tools match the filter")}
              </Td>
            </tr>
          )}
        </tbody>
      </Table>
    </Card>
  );
}
