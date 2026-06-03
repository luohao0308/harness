import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  ChevronRight,
  GitBranch,
  PackagePlus,
  PlugZap,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Timer,
  Workflow,
} from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { ConfigDialog } from "../../../components/ui/config-dialog";
import { Input, Textarea } from "../../../components/ui/input";
import { Table, Td, Th } from "../../../components/ui/table";
import { TermHint } from "../../../components/ui/term";
import { useI18n } from "../../../lib/i18n";
import { booleanLabel, riskLabel, toolSourceLabel } from "../../../lib/labels";
import {
  approveCapabilityPackage,
  attachCapabilityPackage,
  attachAgentCapability,
  capabilityDependencyPreflight,
  enableStagedCapability,
  getToolRegistry,
  installTrustedUrlCapability,
  installUploadedCapability,
  listCapabilityPackages,
  preflightPublicUrlCapability,
  rollbackCapabilityPackage,
  stagePrivateCapabilityPackage,
  stagePublicCapabilityPackage,
  testInvokeCapability,
  uninstallCapabilityPackage,
  updateCapabilityPackageAttachment,
  validateCapabilityPackage,
  type CapabilityPackage,
  type CapabilitySimpleInstallResponse,
} from "../../tasks/api";

type ToolConfigDialog = "trusted-url" | "public-url" | "upload" | "lifecycle" | "test-invoke" | null;

export function ToolRegistryPage() {
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const [sourceFilter, setSourceFilter] = useState("all");
  const [presetCapabilityId, setPresetCapabilityId] = useState<string | null>(null);
  const [activeConfigDialog, setActiveConfigDialog] = useState<ToolConfigDialog>(null);
  const [trustedUrl, setTrustedUrl] = useState("https://example.com/customer-research.skill");
  const [publicUrl, setPublicUrl] = useState("https://example.com/community-skill.skill");
  const [uploadName, setUploadName] = useState("uploaded-skill");
  const [uploadContent, setUploadContent] = useState("# Uploaded Skill\n\nRun the operator test.");
  const [simpleAgentId, setSimpleAgentId] = useState("default");
  const [packageSource, setPackageSource] = useState("git+https://github.com/acme/skill-pack.git");
  const [packagePinnedRef, setPackagePinnedRef] = useState("commit:demo-pinned-commit");
  const [packageAgentId, setPackageAgentId] = useState("default");
  const [rollbackVersionId, setRollbackVersionId] = useState("");
  const [latestAttachmentId, setLatestAttachmentId] = useState<string | null>(null);
  const [packageManifest, setPackageManifest] = useState(`{
  "package_manifest": {
    "package_type": "context_optimizer",
    "name": "conservative-token-saver",
    "version": "1.0.0",
    "description": "Declarative Agent context optimizer",
    "permissions": ["context:optimize"],
    "optimizer": {
      "mode": "budget_overlay",
      "max_candidate_tokens_ratio": 0.8,
      "section_limits": {
        "recent_window": 12,
        "long_term_memory": 8,
        "rag_evidence": 6
      },
      "drop_order": [
        "rag_evidence_low_relevance_first",
        "long_term_memory_low_score_first",
        "recent_window_oldest_first"
      ],
      "prefer_valid_compressed_summary": true,
      "low_cost_route_hint": "summarization under budget"
    },
    "secret_refs": []
  }
}`);
  const [testAgentId, setTestAgentId] = useState("default");
  const [testToolName, setTestToolName] = useState("mcp_context_search");
  const [invokeInput, setInvokeInput] = useState(`{ "query": "release readiness", "limit": 2 }`);
  const registryQuery = useQuery({ queryKey: ["tool-registry"], queryFn: getToolRegistry });
  const packagesQuery = useQuery({
    queryKey: ["capability-packages"],
    queryFn: listCapabilityPackages,
    enabled: activeConfigDialog === "lifecycle",
  });
  const dependencyPreflightQuery = useQuery({ queryKey: ["capability-dependency-preflight"], queryFn: capabilityDependencyPreflight });
  const latestPackage = packagesQuery.data?.items[0] ?? null;
  const selectedRollbackVersion = rollbackVersionId.trim() || latestPackage?.capability_version_id || "";
  const refreshPackages = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["capability-packages"] }),
      queryClient.invalidateQueries({ queryKey: ["tool-registry"] }),
    ]);
  };
  const validationMutation = useMutation({
    mutationFn: () =>
      validateCapabilityPackage({
        content: JSON.parse(packageManifest) as Record<string, unknown>,
        config: {
          source_type: packageSource.startsWith("git+") ? "public_git" : "public_url",
          source_url: packageSource,
          commit: packagePinnedRef,
        },
      }),
  });
  const trustedInstallMutation = useMutation({
    mutationFn: () =>
      installTrustedUrlCapability({
        source_uri: trustedUrl,
        display_name: "trusted-url-skill",
        package_type: "context_optimizer",
        agent_id: simpleAgentId,
      }),
    onSuccess: async (result) => {
      setLatestAttachmentId(result.attachment?.attachment_id ?? latestAttachmentId);
      await refreshPackages();
    },
  });
  const publicPreflightMutation = useMutation({
    mutationFn: () =>
      preflightPublicUrlCapability({
        source_uri: publicUrl,
        pinned_ref: packagePinnedRef || null,
        display_name: "public-preflight-skill",
        package_type: "context_optimizer",
      }),
    onSuccess: refreshPackages,
  });
  const publicEnableMutation = useMutation({
    mutationFn: () => {
      const packageId = publicPreflightMutation.data?.staged_capability_id;
      if (!packageId) {
        throw new Error(text("没有可启用的预检包", "No staged package is ready to enable"));
      }
      return enableStagedCapability(packageId, "console public preflight validation passed");
    },
    onSuccess: refreshPackages,
  });
  const uploadInstallMutation = useMutation({
    mutationFn: () =>
      installUploadedCapability({
        display_name: uploadName,
        package_type: "context_optimizer",
        agent_id: simpleAgentId,
        content: { filename: "SKILL.md", body: uploadContent },
      }),
    onSuccess: async (result) => {
      setLatestAttachmentId(result.attachment?.attachment_id ?? latestAttachmentId);
      await refreshPackages();
    },
  });
  const attachPresetCapabilityMutation = useMutation({
    mutationFn: (capabilityId: string) =>
      attachAgentCapability(simpleAgentId, {
        capability_id: capabilityId,
        capability_version_id: null,
        enabled: true,
        priority: 10,
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["agents"] }),
        queryClient.invalidateQueries({ queryKey: ["tool-registry"] }),
      ]);
      setPresetCapabilityId(null);
    },
  });
  const stageMutation = useMutation({
    mutationFn: () => {
      const draft = parsePackageDraft(packageManifest);
      if (isPublicPackageSource(packageSource)) {
        return stagePublicCapabilityPackage({
          ...draft,
          source_kind: packageSource.startsWith("git+") ? "public_git" : "public_url",
          source_uri: packageSource,
          pinned_ref: packagePinnedRef,
        });
      }
      return stagePrivateCapabilityPackage(draft);
    },
    onSuccess: async (pkg) => {
      setRollbackVersionId(pkg.capability_version_id ?? "");
      await refreshPackages();
    },
  });
  const approveMutation = useMutation({
    mutationFn: (pkg: CapabilityPackage) =>
      approveCapabilityPackage(pkg.id, "console capability lifecycle approval"),
    onSuccess: async (pkg) => {
      setRollbackVersionId(pkg.capability_version_id ?? "");
      await refreshPackages();
    },
  });
  const attachMutation = useMutation({
    mutationFn: (pkg: CapabilityPackage) =>
      attachCapabilityPackage(pkg.id, { agent_id: packageAgentId, enabled: true, priority: 10 }),
    onSuccess: async (attachment) => {
      setLatestAttachmentId(attachment.attachment_id);
      await queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
  });
  const disableAttachmentMutation = useMutation({
    mutationFn: () => {
      if (!latestAttachmentId) {
        throw new Error(text("没有可停用的附件", "No attachment available to disable"));
      }
      return updateCapabilityPackageAttachment(latestAttachmentId, false);
    },
    onSuccess: async () => {
      setLatestAttachmentId(null);
      await queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
  });
  const rollbackMutation = useMutation({
    mutationFn: (pkg: CapabilityPackage) =>
      rollbackCapabilityPackage(pkg.id, selectedRollbackVersion, "console package rollback"),
    onSuccess: refreshPackages,
  });
  const uninstallMutation = useMutation({
    mutationFn: (pkg: CapabilityPackage) => uninstallCapabilityPackage(pkg.id),
    onSuccess: refreshPackages,
  });
  const testInvokeMutation = useMutation({
    mutationFn: () =>
      testInvokeCapability({
        agent_id: testAgentId,
        tool_name: testToolName,
        input_json: JSON.parse(invokeInput) as Record<string, unknown>,
      }),
  });
  const tools = registryQuery.data?.items ?? [];
  const filteredTools = useMemo(
    () => tools.filter((tool) => sourceFilter === "all" || tool.source === sourceFilter),
    [sourceFilter, tools],
  );
  const mcpCount = tools.filter((tool) => tool.source === "mcp").length;
  const sandboxCount = tools.filter((tool) => tool.requires_sandbox).length;
  const highRiskCount = tools.filter((tool) => ["high", "critical"].includes(tool.risk_level)).length;
  const adminOnlyCount = tools.filter((tool) => tool.allowed_roles.includes("admin")).length;
  const presets = presetCapabilities(text);
  const selectedPreset = presets.find((preset) => preset.capabilityId === presetCapabilityId) ?? null;

  return (
    <ConsoleShell title={text("工具运行层", "Tool Runtime")}>
      <div className="space-y-4 p-4">
        <section className="grid grid-cols-4 gap-3">
          <Metric label={text("工具总数", "Tools")} value={tools.length} />
          <Metric label={<TermHint description="模型上下文协议，用于接入外部工具">MCP</TermHint>} value={mcpCount} />
          <Metric label={text("需要沙箱", "Sandboxed")} value={sandboxCount} />
          <Metric label={text("分类", "Categories")} value={registryQuery.data?.categories.length ?? 0} />
        </section>

        <section className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]">
          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Sparkles className="h-4 w-4" />
                {text("常用预置能力", "Built-in Presets")}
              </div>
              <Badge tone={attachPresetCapabilityMutation.isSuccess ? "success" : "info"}>
                {attachPresetCapabilityMutation.isSuccess ? text("已启用", "Enabled") : text("无需安装", "No install")}
              </Badge>
            </CardHeader>
            <div className="grid gap-3 p-3 text-xs">
              <div className="flex flex-wrap items-center justify-between gap-2 text-slate-500">
                <span>{text("选择能力后在弹窗中确认目标 Agent。", "Choose a capability, then confirm the target Agent in a dialog.")}</span>
                <Badge tone="neutral">Agent · {simpleAgentId}</Badge>
              </div>
              <div className="grid gap-2 md:grid-cols-3">
                {presets.map((preset) => {
                  const pending =
                    attachPresetCapabilityMutation.isPending &&
                    attachPresetCapabilityMutation.variables === preset.capabilityId;
                  return (
                    <button
                      key={preset.capabilityId}
                      type="button"
                      className="min-h-28 rounded-md border border-slate-200 bg-white p-3 text-left transition hover:border-slate-400 hover:bg-slate-50 disabled:cursor-wait disabled:opacity-70"
                      disabled={attachPresetCapabilityMutation.isPending}
                      onClick={() => setPresetCapabilityId(preset.capabilityId)}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-slate-950">{preset.label}</span>
                        <Badge tone={pending ? "warning" : "neutral"}>
                          {pending ? text("启用中", "Enabling") : preset.kind}
                        </Badge>
                      </div>
                      <p className="mt-2 leading-5 text-slate-500">{preset.description}</p>
                    </button>
                  );
                })}
              </div>
              {attachPresetCapabilityMutation.error instanceof Error ? (
                <div className="text-red-700">{attachPresetCapabilityMutation.error.message}</div>
              ) : null}
            </div>
          </Card>

          <Card className="self-start">
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <PackagePlus className="h-4 w-4" />
                {text("高级包管理", "Advanced Packages")}
              </div>
              <Badge tone={latestPackage?.status === "approved" ? "success" : "neutral"}>
                {latestPackage?.status ?? text("点击配置", "Open to configure")}
              </Badge>
            </CardHeader>
            <div className="space-y-3 p-3 text-xs text-slate-500">
              <p>
                {text(
                  "普通使用请直接选择左侧预置能力；自定义包、固定版本、审批、回滚和测试调用统一在弹窗中配置。",
                  "Use presets for normal setup; custom packages, pinned versions, approvals, rollback, and test invoke are configured in dialogs.",
                )}
              </p>
              <div className="grid grid-cols-2 gap-2">
                <Button type="button" variant="secondary" onClick={() => setActiveConfigDialog("trusted-url")}>
                  <PackagePlus className="h-3.5 w-3.5" />
                  {text("可信 URL", "Trusted URL")}
                </Button>
                <Button type="button" variant="secondary" onClick={() => setActiveConfigDialog("public-url")}>
                  <ShieldAlert className="h-3.5 w-3.5" />
                  {text("公网预检", "Public preflight")}
                </Button>
                <Button type="button" variant="secondary" onClick={() => setActiveConfigDialog("upload")}>
                  <PackagePlus className="h-3.5 w-3.5" />
                  {text("上传 Skill", "Upload Skill")}
                </Button>
                <Button type="button" variant="secondary" onClick={() => setActiveConfigDialog("lifecycle")}>
                  <ChevronRight className="h-3.5 w-3.5" />
                  {text("生命周期", "Lifecycle")}
                </Button>
                <Button type="button" variant="secondary" className="col-span-2" onClick={() => setActiveConfigDialog("test-invoke")}>
                  <PlugZap className="h-3.5 w-3.5" />
                  {text("测试调用", "Test invoke")}
                </Button>
              </div>
            </div>
          </Card>
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
            status={String((dependencyPreflightQuery.data?.local_release_path as string | undefined) ?? `${sandboxCount} ${text("需要隔离", "isolated")}`)}
            description={text("v1 本地路径使用无容器验证；高风险能力走沙箱或策略约束，Docker 私有部署烟测为可选项。", "The v1 local path is no-container; high-risk capabilities use sandbox or policy gates, and Docker private smoke is optional.")}
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

        <ConfigDialog
          open={selectedPreset !== null}
          title={selectedPreset ? text(`配置${selectedPreset.label}`, `Configure ${selectedPreset.label}`) : text("配置预置能力", "Configure preset capability")}
          description={text("确认目标 Agent 后启用这个 MCP / Skill / Tool 能力。", "Confirm the target Agent before enabling this MCP / Skill / Tool capability.")}
          onClose={() => setPresetCapabilityId(null)}
        >
          {selectedPreset ? (
            <div className="grid gap-3 text-xs">
              <div className="rounded-md border border-slate-100 bg-slate-50 p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-semibold text-slate-900">{selectedPreset.label}</div>
                  <Badge tone="neutral">{selectedPreset.kind}</Badge>
                </div>
                <p className="mt-2 leading-5 text-slate-500">{selectedPreset.description}</p>
              </div>
              <label className="grid gap-1">
                <span className="font-medium text-slate-600">{text("目标 Agent", "Target Agent")}</span>
                <Input
                  aria-label={text("预置能力目标 Agent", "Preset capability target Agent")}
                  value={simpleAgentId}
                  onChange={(event) => setSimpleAgentId(event.target.value)}
                />
              </label>
              <Button
                type="button"
                onClick={() => attachPresetCapabilityMutation.mutate(selectedPreset.capabilityId)}
                disabled={attachPresetCapabilityMutation.isPending || !simpleAgentId.trim()}
              >
                <CheckCircle2 className="h-3.5 w-3.5" />
                {attachPresetCapabilityMutation.isPending ? text("启用中", "Enabling") : text("启用能力", "Enable capability")}
              </Button>
              <MutationError error={attachPresetCapabilityMutation.error} />
            </div>
          ) : null}
        </ConfigDialog>

        <ConfigDialog
          open={activeConfigDialog === "trusted-url"}
          title={text("可信 URL 一键安装", "Trusted URL one-click install")}
          description={text("从可信来源下载 Skill 或能力包，并安装到目标 Agent。", "Download a Skill or capability package from a trusted source and attach it to the target Agent.")}
          onClose={() => setActiveConfigDialog(null)}
        >
          <div className="grid gap-3 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-slate-600">{text("当前状态", "Current status")}</span>
              <Badge tone={trustedInstallMutation.data?.ready_state === "attached" ? "success" : "info"}>
                {trustedInstallMutation.data?.ready_state ?? text("v1 gate", "v1 gate")}
              </Badge>
            </div>
            <label className="grid gap-1">
              <span className="font-medium text-slate-600">{text("可信来源 URL", "Trusted source URL")}</span>
              <Input aria-label="可信 URL 安装" value={trustedUrl} onChange={(event) => setTrustedUrl(event.target.value)} />
            </label>
            <label className="grid gap-1">
              <span className="font-medium text-slate-600">Agent ID</span>
              <Input aria-label="可信 URL 目标 Agent" value={simpleAgentId} onChange={(event) => setSimpleAgentId(event.target.value)} />
            </label>
            <Button onClick={() => trustedInstallMutation.mutate()} disabled={trustedInstallMutation.isPending || !trustedUrl.trim()}>
              <CheckCircle2 className="h-3.5 w-3.5" /> {text("下载、安装并启用", "Download, install, and enable")}
            </Button>
            <SimpleInstallResult result={trustedInstallMutation.data} />
            <MutationError error={trustedInstallMutation.error} />
          </div>
        </ConfigDialog>

        <ConfigDialog
          open={activeConfigDialog === "public-url"}
          title={text("公网 URL 预检", "Public URL preflight")}
          description={text("公网来源只做下载预检和暂存，验证后再手动启用。", "Public sources are downloaded, preflighted, and staged; enable them manually after validation.")}
          onClose={() => setActiveConfigDialog(null)}
        >
          <div className="grid gap-3 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-slate-600">{text("当前状态", "Current status")}</span>
              <Badge tone={publicPreflightMutation.data?.staged_capability_id ? "warning" : "neutral"}>
                {publicPreflightMutation.data?.staged_capability_id ? text("等待启用", "Enable required") : text("不自动启用", "No auto-enable")}
              </Badge>
            </div>
            <label className="grid gap-1">
              <span className="font-medium text-slate-600">{text("公网 HTTPS URL", "Public HTTPS URL")}</span>
              <Input aria-label="公网 URL 预检" value={publicUrl} onChange={(event) => setPublicUrl(event.target.value)} />
            </label>
            <label className="grid gap-1">
              <span className="font-medium text-slate-600">{text("可选固定引用", "Optional pinned ref")}</span>
              <Input aria-label="公网 URL 固定引用" value={packagePinnedRef} onChange={(event) => setPackagePinnedRef(event.target.value)} />
            </label>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => publicPreflightMutation.mutate()} disabled={publicPreflightMutation.isPending || !publicUrl.trim()}>
                <ShieldCheck className="h-3.5 w-3.5" /> {text("下载并预检", "Download and preflight")}
              </Button>
              <Button onClick={() => publicEnableMutation.mutate()} disabled={!publicPreflightMutation.data?.staged_capability_id || publicEnableMutation.isPending}>
                <CheckCircle2 className="h-3.5 w-3.5" /> {text("启用", "Enable")}
              </Button>
            </div>
            {publicPreflightMutation.data?.staged_capability_id ? (
              <div className="rounded-md border border-amber-100 bg-amber-50 p-2 text-amber-800">
                {text("已生成 staged_capability_id，必须在验证后点启用才能运行。", "staged_capability_id created; Enable is required before runtime attachment.")}{" "}
                <span className="font-mono">{publicPreflightMutation.data.staged_capability_id}</span>
              </div>
            ) : null}
            <SimpleInstallResult result={publicPreflightMutation.data} />
            <SimpleInstallResult result={publicEnableMutation.data} />
            <MutationError error={publicPreflightMutation.error ?? publicEnableMutation.error} />
          </div>
        </ConfigDialog>

        <ConfigDialog
          open={activeConfigDialog === "upload"}
          title={text("上传文件安装", "Upload file install")}
          description={text("上传 SKILL.md 内容并安装到目标 Agent。", "Upload SKILL.md content and attach it to the target Agent.")}
          onClose={() => setActiveConfigDialog(null)}
        >
          <div className="grid gap-3 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-slate-600">{text("当前状态", "Current status")}</span>
              <Badge tone={uploadInstallMutation.data?.ready_state === "attached" ? "success" : "info"}>
                {uploadInstallMutation.data?.ready_state ?? text("无需编辑清单", "No manifest editing")}
              </Badge>
            </div>
            <label className="grid gap-1">
              <span className="font-medium text-slate-600">{text("包名称", "Package name")}</span>
              <Input aria-label="上传包名称" value={uploadName} onChange={(event) => setUploadName(event.target.value)} />
            </label>
            <label className="grid gap-1">
              <span className="font-medium text-slate-600">SKILL.md</span>
              <Textarea aria-label="上传 SKILL.md 内容" value={uploadContent} onChange={(event) => setUploadContent(event.target.value)} className="font-mono text-xs" />
            </label>
            <Button onClick={() => uploadInstallMutation.mutate()} disabled={uploadInstallMutation.isPending || !uploadName.trim()}>
              <PackagePlus className="h-3.5 w-3.5" /> {text("上传并安装", "Upload and install")}
            </Button>
            <SimpleInstallResult result={uploadInstallMutation.data} />
            <MutationError error={uploadInstallMutation.error} />
          </div>
        </ConfigDialog>

        <ConfigDialog
          open={activeConfigDialog === "lifecycle"}
          title={text("高级生命周期", "Advanced lifecycle")}
          description={text("自定义能力包的校验、暂存、审批、安装、停用、回滚和卸载。", "Validate, stage, approve, install, disable, roll back, and uninstall custom capability packages.")}
          onClose={() => setActiveConfigDialog(null)}
          className="max-w-4xl"
        >
          <div className="grid gap-3 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-slate-600">{text("当前包状态", "Current package status")}</span>
              <Badge tone={latestPackage?.status === "approved" ? "success" : "warning"}>
                {latestPackage?.status ?? text("未暂存", "Not staged")}
              </Badge>
            </div>
            <label className="grid gap-1">
              <span className="font-medium text-slate-600">{text("来源：留空或 private 表示私有包", "Source: blank or private for private packages")}</span>
              <Input aria-label="能力包来源" value={packageSource} onChange={(event) => setPackageSource(event.target.value)} />
            </label>
            <div className="grid grid-cols-2 gap-2">
              <label className="grid gap-1">
                <span className="font-medium text-slate-600">{text("公共来源固定引用", "Pinned public ref")}</span>
                <Input aria-label="能力包固定引用" value={packagePinnedRef} onChange={(event) => setPackagePinnedRef(event.target.value)} disabled={!isPublicPackageSource(packageSource)} />
              </label>
              <label className="grid gap-1">
                <span className="font-medium text-slate-600">Agent ID</span>
                <Input aria-label="能力包安装 Agent ID" value={packageAgentId} onChange={(event) => setPackageAgentId(event.target.value)} />
              </label>
            </div>
            <label className="grid gap-1">
              <span className="font-medium text-slate-600">{text("包清单", "Package manifest")}</span>
              <Textarea aria-label="能力包清单" value={packageManifest} onChange={(event) => setPackageManifest(event.target.value)} className="min-h-56 font-mono text-xs" />
            </label>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => validationMutation.mutate()} disabled={validationMutation.isPending}>
                <ShieldCheck className="h-3.5 w-3.5" /> {text("仅校验", "Validate only")}
              </Button>
              <Button onClick={() => stageMutation.mutate()} disabled={stageMutation.isPending || (isPublicPackageSource(packageSource) && !packagePinnedRef.trim())}>
                <PackagePlus className="h-3.5 w-3.5" /> {text("暂存包", "Stage package")}
              </Button>
              <Button onClick={() => latestPackage && approveMutation.mutate(latestPackage)} disabled={!latestPackage || latestPackage.status !== "staged" || approveMutation.isPending}>
                <CheckCircle2 className="h-3.5 w-3.5" /> {text("审批版本", "Approve version")}
              </Button>
              <Button onClick={() => latestPackage && attachMutation.mutate(latestPackage)} disabled={!latestPackage || latestPackage.status !== "approved" || !packageAgentId.trim() || attachMutation.isPending}>
                {text("安装到 Agent", "Install to Agent")}
              </Button>
              <Button onClick={() => disableAttachmentMutation.mutate()} disabled={!latestAttachmentId || disableAttachmentMutation.isPending}>
                {text("停用附件", "Disable attachment")}
              </Button>
              <Button onClick={() => latestPackage && rollbackMutation.mutate(latestPackage)} disabled={!latestPackage?.capability_id || !selectedRollbackVersion || rollbackMutation.isPending}>
                <RotateCcw className="h-3.5 w-3.5" /> {text("回滚", "Rollback")}
              </Button>
              <Button onClick={() => latestPackage && uninstallMutation.mutate(latestPackage)} disabled={!latestPackage || latestPackage.status === "uninstalled" || uninstallMutation.isPending}>
                {text("卸载", "Uninstall")}
              </Button>
            </div>
            <label className="grid gap-1">
              <span className="font-medium text-slate-600">{text("回滚目标版本", "Rollback target version")}</span>
              <Input aria-label="回滚目标版本" value={rollbackVersionId} onChange={(event) => setRollbackVersionId(event.target.value)} placeholder={latestPackage?.capability_version_id ?? ""} />
            </label>
            {latestPackage ? (
              <PackageLifecycleSummary pkg={latestPackage} />
            ) : packagesQuery.isLoading ? (
              <div className="rounded-md border border-slate-100 bg-slate-50 p-2 text-slate-500">
                {text("正在加载能力包...", "Loading capability packages...")}
              </div>
            ) : null}
            {validationMutation.data ? (
              <div className="rounded-md border border-slate-100 bg-slate-50 p-2 font-mono text-[11px] text-slate-600">
                {text("校验状态", "Validation")} {validationMutation.data.status} · {validationMutation.data.validation_mode ?? "manifest_only_no_execution"}
                <br />
                sha {validationMutation.data.content_sha256.slice(0, 12)} / {validationMutation.data.config_sha256.slice(0, 12)}
              </div>
            ) : null}
            {latestAttachmentId ? (
              <div className="rounded-md border border-emerald-100 bg-emerald-50 p-2 font-mono text-[11px] text-emerald-700">
                {text("最近附件", "Latest attachment")} {latestAttachmentId}
              </div>
            ) : null}
            <MutationError error={validationMutation.error ?? stageMutation.error ?? approveMutation.error ?? attachMutation.error ?? disableAttachmentMutation.error ?? rollbackMutation.error ?? uninstallMutation.error ?? packagesQuery.error} />
          </div>
        </ConfigDialog>

        <ConfigDialog
          open={activeConfigDialog === "test-invoke"}
          title={text("Agent 作用域测试调用", "Agent-scoped test invoke")}
          description={text("使用 Agent 作用域执行一次工具测试，验证附件和策略链路。", "Run one Agent-scoped tool test to validate attachment and policy routing.")}
          onClose={() => setActiveConfigDialog(null)}
        >
          <div className="grid gap-3 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-slate-600">{text("当前状态", "Current status")}</span>
              <Badge tone={testInvokeMutation.data?.allowed ? "success" : "neutral"}>
                {testInvokeMutation.data ? testInvokeMutation.data.tool_call.status : text("待测试", "Ready")}
              </Badge>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <label className="grid gap-1">
                <span className="font-medium text-slate-600">Agent ID</span>
                <Input aria-label="测试 Agent ID" value={testAgentId} onChange={(event) => setTestAgentId(event.target.value)} />
              </label>
              <label className="grid gap-1">
                <span className="font-medium text-slate-600">{text("工具名", "Tool name")}</span>
                <Input aria-label="测试工具名" value={testToolName} onChange={(event) => setTestToolName(event.target.value)} />
              </label>
            </div>
            <Textarea aria-label="测试输入 JSON" value={invokeInput} onChange={(event) => setInvokeInput(event.target.value)} className="font-mono text-xs" />
            <Button onClick={() => testInvokeMutation.mutate()} disabled={testInvokeMutation.isPending}>
              <Timer className="h-3.5 w-3.5" /> {text("测试调用", "Test invoke")}
            </Button>
            {testInvokeMutation.data ? (
              <pre className="max-h-32 overflow-auto rounded border border-slate-100 bg-slate-50 p-2 font-mono text-[10px] text-slate-600">
                {JSON.stringify(testInvokeMutation.data.output, null, 2)}
              </pre>
            ) : null}
            {testInvokeMutation.error instanceof Error ? <div className="text-red-700">{testInvokeMutation.error.message}</div> : null}
          </div>
        </ConfigDialog>
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

function presetCapabilities(text: (zh: string, en: string) => string) {
  return [
    {
      capabilityId: "mcp_context_search",
      label: text("上下文搜索", "Context Search"),
      kind: "MCP",
      description: text(
        "让 Agent 直接检索工作区上下文和知识证据。",
        "Let the Agent retrieve workspace context and knowledge evidence.",
      ),
    },
    {
      capabilityId: "read_file",
      label: text("读取文件", "Read File"),
      kind: text("内置", "Built-in"),
      description: text(
        "允许 Agent 在策略边界内读取工作区文件。",
        "Allow the Agent to read workspace files within policy boundaries.",
      ),
    },
    {
      capabilityId: "list_files",
      label: text("列出文件", "List Files"),
      kind: text("内置", "Built-in"),
      description: text(
        "允许 Agent 浏览工作区文件结构，便于定位资料。",
        "Allow the Agent to browse workspace file structure for discovery.",
      ),
    },
  ];
}

function PackageLifecycleSummary({ pkg }: { pkg: CapabilityPackage }) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50 p-2 font-mono text-[11px] text-slate-600">
      <div>{pkg.package_key} · {pkg.status} · {pkg.source_kind}</div>
      <div>package {pkg.id}</div>
      <div>source {pkg.source_sha256.slice(0, 12)}{pkg.pinned_ref ? ` · ${pkg.pinned_ref}` : ""}</div>
      <div>capability {pkg.capability_id ?? "--"} / {pkg.capability_version_id ?? "--"}</div>
    </div>
  );
}

function SimpleInstallResult({ result }: { result?: CapabilitySimpleInstallResponse }) {
  if (!result) return null;
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50 p-2 font-mono text-[11px] text-slate-600">
      <div>{result.ready_state} · {result.next_step_label}</div>
      <div>package {result.package.id}</div>
      <div>capability {result.capability_id ?? "--"} / {result.capability_version_id ?? "--"}</div>
      {result.attachment ? <div>attachment {result.attachment.attachment_id}</div> : null}
    </div>
  );
}

function MutationError({ error }: { error: unknown }) {
  if (!(error instanceof Error)) return null;
  return <div className="text-red-700">{error.message}</div>;
}

function isPublicPackageSource(value: string) {
  const source = value.trim();
  return source.startsWith("git+") || source.startsWith("https://") || source.startsWith("http://");
}

function parsePackageDraft(value: string) {
  const parsed = JSON.parse(value) as Record<string, unknown>;
  const packageManifest = parsed.package_manifest;
  if (isRecord(packageManifest)) {
    const { package_manifest: _packageManifest, ...content } = parsed;
    return { manifest: packageManifest, content };
  }
  return { manifest: parsed, content: {} };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
