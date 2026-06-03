import { useCallback, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  ChevronRight,
  Download,
  FileCheck2,
  ExternalLink,
  GitBranch,
  PackagePlus,
  PlugZap,
  RotateCcw,
  Search,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Timer,
  Workflow,
} from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { ConfigDialog } from "../../../components/ui/config-dialog";
import { feedbackErrorMessage, notifyFeedback } from "../../../components/ui/feedback-toast";
import { Input, Textarea } from "../../../components/ui/input";
import { MenuSelect, type MenuSelectOption } from "../../../components/ui/menu-select";
import { Table, Td, Th } from "../../../components/ui/table";
import { TermHint } from "../../../components/ui/term";
import { useI18n } from "../../../lib/i18n";
import { booleanLabel, riskLabel, statusLabel, toolSourceLabel } from "../../../lib/labels";
import {
  localizedCapabilityDescription,
  mcpConfigHint,
  mcpGuideFor,
  mcpUseSummary,
} from "../lib/mcpDescriptions";
import {
  approveCapabilityPackage,
  type AgentDefinition,
  attachCapabilityPackage,
  attachAgentCapability,
  capabilityDependencyPreflight,
  enableStagedCapability,
  getToolRegistry,
  installTrustedUrlCapability,
  installUploadedCapability,
  listAgents,
  listCapabilityMarketplace,
  listCapabilityPackages,
  preflightMarketplaceCapability,
  preflightPublicUrlCapability,
  rollbackCapabilityPackage,
  stagePrivateCapabilityPackage,
  stagePublicCapabilityPackage,
  testInvokeCapability,
  uninstallCapabilityPackage,
  updateCapabilityPackageAttachment,
  validateCapabilityPackage,
  type CapabilityMarketplaceItem,
  type CapabilityMarketplacePreflightPayload,
  type CapabilityPackage,
  type CapabilitySimpleInstallResponse,
  type CapabilitySimpleInstallPayload,
  type AgentCapabilityAttachmentSummary,
  type ToolExecuteResult,
} from "../../tasks/api";

type ToolConfigDialog =
  | "marketplace"
  | "trusted-url"
  | "public-url"
  | "upload"
  | "lifecycle"
  | "test-invoke"
  | null;
type MarketplaceFilter = "all" | "mcp" | "skill";
type MarketplaceInstallState = "available" | "staged" | "approved" | "installed";

export function ToolRegistryPage() {
  const { text } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [sourceFilter, setSourceFilter] = useState("all");
  const [marketplaceFilter, setMarketplaceFilter] = useState<MarketplaceFilter>("all");
  const [marketplaceSearch, setMarketplaceSearch] = useState("");
  const [activeConfigDialog, setActiveConfigDialog] = useState<ToolConfigDialog>(null);
  const [selectedMarketplaceItemId, setSelectedMarketplaceItemId] = useState<string | null>(null);
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
    "description": "声明式智能体上下文优化器",
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
  const [marketplaceQuickQuery, setMarketplaceQuickQuery] = useState("发布准备情况");
  const [lastDirectAttachedMarketplaceItemId, setLastDirectAttachedMarketplaceItemId] = useState<string | null>(null);
  const [lastAttachedMarketplacePackageId, setLastAttachedMarketplacePackageId] = useState<string | null>(null);
  const registryQuery = useQuery({
    queryKey: ["tool-registry", simpleAgentId],
    queryFn: () => getToolRegistry(simpleAgentId),
  });
  const agentsQuery = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const marketplaceQuery = useQuery({
    queryKey: ["capability-marketplace", marketplaceFilter, marketplaceSearch],
    queryFn: () =>
      listCapabilityMarketplace({
        kind: marketplaceFilter,
        query: marketplaceSearch,
        limit: 18,
      }),
  });
  const packagesQuery = useQuery({
    queryKey: ["capability-packages"],
    queryFn: listCapabilityPackages,
    enabled: activeConfigDialog === "lifecycle" || activeConfigDialog === "marketplace",
  });
  const dependencyPreflightQuery = useQuery({ queryKey: ["capability-dependency-preflight"], queryFn: capabilityDependencyPreflight });
  const latestPackage = packagesQuery.data?.items[0] ?? null;
  const selectedRollbackVersion = rollbackVersionId.trim() || latestPackage?.capability_version_id || "";
  const marketplaceItems = marketplaceQuery.data?.items ?? [];
  const selectedMarketplaceItem =
    marketplaceItems.find((item) => item.id === selectedMarketplaceItemId) ?? marketplaceItems[0] ?? null;
  const selectedMarketplacePayload = selectedMarketplaceItem
    ? normalizeMarketplaceInstallPayload(selectedMarketplaceItem)
    : null;
  const agentOptions = useMemo<MenuSelectOption[]>(
    () =>
      (agentsQuery.data?.items ?? []).map((agent) => ({
        value: agent.id,
        label: agent.name,
        description: `${agent.id} · ${statusLabel(agent.status)}`,
      })),
    [agentsQuery.data?.items],
  );
  const selectedAgent = agentsQuery.data?.items.find((agent) => agent.id === simpleAgentId) ?? null;
  const selectedAgentAttachments = selectedAgent?.capability_attachments ?? [];
  const selectedAgentDisplayLabel = agentTargetLabel(simpleAgentId, agentsQuery.data?.items ?? []);
  const packageAgentDisplayLabel = agentTargetLabel(packageAgentId, agentsQuery.data?.items ?? []);
  const refreshPackages = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["capability-packages"] }),
      queryClient.invalidateQueries({ queryKey: ["tool-registry"] }),
      queryClient.invalidateQueries({ queryKey: ["agents"] }),
    ]);
  };
  const notifyMutationError = useCallback(
    (title: string, error: unknown, fallback: string) => {
      notifyFeedback({
        tone: "error",
        title,
        description: feedbackErrorMessage(error, fallback),
      });
    },
    [],
  );
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
    onSuccess: (result) => {
      notifyFeedback({
        tone: "success",
        title: "能力包校验通过",
        description: `已完成仅校验，当前模式：${capabilityValidationModeLabel(result.validation_mode ?? "manifest_only_no_execution")}`,
      });
    },
    onError: (error) => notifyMutationError("能力包校验失败", error, "请检查清单 JSON、来源地址或固定引用。"),
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
      setLatestAttachmentId((current) => result.attachment?.attachment_id ?? current);
      notifyFeedback({
        tone: "success",
        title: "可信来源安装成功",
        description: simpleInstallSuccessSummary(result, selectedAgentDisplayLabel),
      });
      await refreshPackages();
    },
    onError: (error) => notifyMutationError("可信来源安装失败", error, "请检查来源 URL、权限和后端安装日志。"),
  });
  const publicPreflightMutation = useMutation({
    mutationFn: () =>
      preflightPublicUrlCapability({
        source_uri: publicUrl,
        pinned_ref: packagePinnedRef || null,
        display_name: "public-preflight-skill",
        package_type: "context_optimizer",
      }),
    onSuccess: async (result) => {
      notifyFeedback({
        tone: "info",
        title: "公网包已完成预检",
        description: simpleInstallSuccessSummary(result, selectedAgentDisplayLabel),
      });
      await refreshPackages();
    },
    onError: (error) => notifyMutationError("公网包预检失败", error, "请检查 HTTPS 地址、固定引用或后端网络策略。"),
  });
  const publicEnableMutation = useMutation({
    mutationFn: () => {
      const packageId = publicPreflightMutation.data?.staged_capability_id;
      if (!packageId) {
        throw new Error(text("没有可启用的预检包", "No staged package is ready to enable"));
      }
      return enableStagedCapability(packageId, "console public preflight validation passed");
    },
    onSuccess: async (result) => {
      notifyFeedback({
        tone: "success",
        title: "公网包已启用",
        description: simpleInstallSuccessSummary(result, selectedAgentDisplayLabel),
      });
      await refreshPackages();
    },
    onError: (error) => notifyMutationError("公网包启用失败", error, "请先完成预检，再检查审批状态和版本可用性。"),
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
      setLatestAttachmentId((current) => result.attachment?.attachment_id ?? current);
      notifyFeedback({
        tone: "success",
        title: "本地技能安装成功",
        description: simpleInstallSuccessSummary(result, selectedAgentDisplayLabel),
      });
      await refreshPackages();
    },
    onError: (error) => notifyMutationError("上传安装失败", error, "请检查包名称、技能说明文件（SKILL.md）内容和安装权限。"),
  });
  const marketplacePublicPreflightMutation = useMutation({
    mutationFn: (payload: CapabilitySimpleInstallPayload) => preflightPublicUrlCapability(payload),
    onSuccess: async (result) => {
      notifyFeedback({
        tone: "info",
        title: "商店条目已完成预检",
        description: simpleInstallSuccessSummary(result, selectedAgentDisplayLabel),
      });
      await refreshPackages();
    },
    onError: (error) => notifyMutationError("商店条目预检失败", error, "请检查商店源状态、网络策略或来源元数据。"),
  });
  const marketplaceRegistryPreflightMutation = useMutation({
    mutationFn: (payload: CapabilityMarketplacePreflightPayload) => preflightMarketplaceCapability(payload),
    onSuccess: async (result) => {
      notifyFeedback({
        tone: "info",
        title: "商店条目已登记预检",
        description: simpleInstallSuccessSummary(result, selectedAgentDisplayLabel),
      });
      await refreshPackages();
    },
    onError: (error) => notifyMutationError("商店登记预检失败", error, "请检查商店源状态或后端预检链路。"),
  });
  const approveMarketplacePackageMutation = useMutation({
    mutationFn: (pkg: CapabilityPackage) =>
      approveCapabilityPackage(pkg.id, "marketplace preflight approved in console"),
    onSuccess: async (pkg) => {
      notifyFeedback({
        tone: "success",
        title: "商店版本审批通过",
        description: `版本 ${pkg.capability_version_id ?? "待生成"} 已可安装到当前智能体。`,
      });
      await refreshPackages();
    },
    onError: (error) => notifyMutationError("商店版本审批失败", error, "请检查能力包状态或审批权限。"),
  });
  const attachMarketplacePackageMutation = useMutation({
    mutationFn: (pkg: CapabilityPackage) =>
      attachCapabilityPackage(pkg.id, {
        agent_id: simpleAgentId,
        enabled: true,
        priority: 10,
      }),
    onSuccess: async (attachment, pkg) => {
      setLastAttachedMarketplacePackageId(pkg.id);
      setLatestAttachmentId(attachment.attachment_id);
      notifyFeedback({
        tone: "success",
        title: "商店能力已安装到智能体",
        description: `已安装到智能体 ${selectedAgentDisplayLabel}，附件 ${attachment.attachment_id} 已启用。`,
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["agents"] }),
        queryClient.invalidateQueries({ queryKey: ["tool-registry"] }),
      ]);
    },
    onError: (error) => notifyMutationError("商店能力安装失败", error, "请确认版本已审批，并检查智能体权限。"),
  });
  const marketplaceTrustedInstallMutation = useMutation({
    mutationFn: (payload: CapabilitySimpleInstallPayload) => installTrustedUrlCapability(payload),
    onSuccess: async (result) => {
      setLatestAttachmentId((current) => result.attachment?.attachment_id ?? current);
      notifyFeedback({
        tone: "success",
        title: "商店可信来源安装成功",
        description: simpleInstallSuccessSummary(result, selectedAgentDisplayLabel),
      });
      await refreshPackages();
    },
    onError: (error) => notifyMutationError("商店可信来源安装失败", error, "请检查来源地址、审批链路或后端能力安装日志。"),
  });
  const marketplaceUploadInstallMutation = useMutation({
    mutationFn: (payload: CapabilitySimpleInstallPayload) => installUploadedCapability(payload),
    onSuccess: async (result) => {
      setLatestAttachmentId((current) => result.attachment?.attachment_id ?? current);
      notifyFeedback({
        tone: "success",
        title: "商店本地技能安装成功",
        description: simpleInstallSuccessSummary(result, selectedAgentDisplayLabel),
      });
      await refreshPackages();
    },
    onError: (error) => notifyMutationError("商店本地技能安装失败", error, "请检查能力清单和目标智能体。"),
  });
  const attachMarketplaceCapabilityMutation = useMutation({
    mutationFn: (item: CapabilityMarketplaceItem) =>
      attachAgentCapability(simpleAgentId, {
        capability_id: String(item.install_payload.capability_id ?? item.name),
        capability_version_id: null,
        enabled: Boolean(item.install_payload.enabled ?? true),
        priority: Number(item.install_payload.priority ?? 10),
      }),
    onSuccess: async (_result, item) => {
      setLastDirectAttachedMarketplaceItemId(item.id);
      notifyFeedback({
        tone: "success",
        title: "内置能力已启用",
        description: `已启用 ${item.display_name}，当前智能体：${selectedAgentDisplayLabel}。`,
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["agents"] }),
        queryClient.invalidateQueries({ queryKey: ["tool-registry"] }),
      ]);
    },
    onError: (error) => notifyMutationError("内置能力启用失败", error, "请检查智能体附件写入权限或能力标识。"),
  });
  const latestMarketplaceMutationPackage =
    approveMarketplacePackageMutation.data ??
    marketplaceRegistryPreflightMutation.data?.package ??
    marketplacePublicPreflightMutation.data?.package ??
    null;
  const readyMarketplaceSources = marketplaceQuery.data?.sources.filter((source) => source.status === "ready").length ?? 0;
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
      notifyFeedback({
        tone: "info",
        title: "能力包已暂存",
        description: `当前状态：${capabilityPackageStatusLabel(pkg.status)}。下一步请审批版本。`,
      });
      await refreshPackages();
    },
    onError: (error) => notifyMutationError("能力包暂存失败", error, "请检查来源地址、固定引用和包清单。"),
  });
  const approveMutation = useMutation({
    mutationFn: (pkg: CapabilityPackage) =>
      approveCapabilityPackage(pkg.id, "console capability lifecycle approval"),
    onSuccess: async (pkg) => {
      setRollbackVersionId(pkg.capability_version_id ?? "");
      notifyFeedback({
        tone: "success",
        title: "能力版本审批通过",
        description: `版本 ${pkg.capability_version_id ?? "待生成"} 已可安装。`,
      });
      await refreshPackages();
    },
    onError: (error) => notifyMutationError("能力版本审批失败", error, "请检查当前状态是否允许审批。"),
  });
  const attachMutation = useMutation({
    mutationFn: (pkg: CapabilityPackage) =>
      attachCapabilityPackage(pkg.id, { agent_id: packageAgentId, enabled: true, priority: 10 }),
    onSuccess: async (attachment) => {
      setLatestAttachmentId(attachment.attachment_id);
      notifyFeedback({
        tone: "success",
        title: "能力包已安装到智能体",
        description: `${packageAgentDisplayLabel} 的附件 ${attachment.attachment_id} 已启用。`,
      });
      await queryClient.invalidateQueries({ queryKey: ["agents"] });
      await queryClient.invalidateQueries({ queryKey: ["tool-registry"] });
    },
    onError: (error) => notifyMutationError("安装到智能体失败", error, "请检查审批状态、智能体标识和能力版本。"),
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
      notifyFeedback({
        tone: "warning",
        title: "附件已停用",
        description: "当前智能体不再加载这份能力附件。",
      });
      await queryClient.invalidateQueries({ queryKey: ["agents"] });
      await queryClient.invalidateQueries({ queryKey: ["tool-registry"] });
    },
    onError: (error) => notifyMutationError("停用附件失败", error, "请确认附件仍存在且当前账号有更新权限。"),
  });
  const rollbackMutation = useMutation({
    mutationFn: (pkg: CapabilityPackage) =>
      rollbackCapabilityPackage(pkg.id, selectedRollbackVersion, "console package rollback"),
    onSuccess: async (pkg) => {
      notifyFeedback({
        tone: "warning",
        title: "能力包已回滚",
        description: `当前版本已切换到 ${pkg.capability_version_id ?? selectedRollbackVersion}。`,
      });
      await refreshPackages();
    },
    onError: (error) => notifyMutationError("能力包回滚失败", error, "请检查目标版本是否存在，或当前包是否允许回滚。"),
  });
  const uninstallMutation = useMutation({
    mutationFn: (pkg: CapabilityPackage) => uninstallCapabilityPackage(pkg.id),
    onSuccess: async () => {
      notifyFeedback({
        tone: "warning",
        title: "能力包已卸载",
        description: "已完成卸载；若仍有启用中的附件，请先停用后再检查。",
      });
      await refreshPackages();
    },
    onError: (error) => notifyMutationError("能力包卸载失败", error, "请先停用所有启用中的附件，再执行卸载。"),
  });
  const testInvokeMutation = useMutation({
    mutationFn: () =>
      testInvokeCapability({
        agent_id: testAgentId,
        tool_name: testToolName,
        input_json: JSON.parse(invokeInput) as Record<string, unknown>,
      }),
    onSuccess: (result) => {
      notifyFeedback({
        tone: result.allowed ? "success" : "warning",
        title: result.allowed ? "测试调用成功" : "测试调用已返回结果",
        description: `${result.tool_call.tool_name} · ${result.tool_call.duration_ms}ms`,
      });
    },
    onError: (error) => notifyMutationError("测试调用失败", error, "请检查工具名、输入 JSON 和智能体附件状态。"),
  });
  const marketplaceQuickTestMutation = useMutation({
    mutationFn: (toolName: string) =>
      testInvokeCapability({
        agent_id: simpleAgentId,
        tool_name: toolName,
        input_json: { query: marketplaceQuickQuery, limit: 3 },
      }),
    onSuccess: (result) => {
      notifyFeedback({
        tone: result.allowed ? "success" : "warning",
        title: result.allowed ? "商店案例测试通过" : "商店案例测试已返回结果",
        description: `${result.tool_call.tool_name} · ${result.tool_call.duration_ms}ms`,
      });
    },
    onError: (error) => notifyMutationError("商店案例测试失败", error, "请先完成安装或启用，再检查查询词和工具权限。"),
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
  const matchedMarketplacePackage =
    selectedMarketplaceItem && packagesQuery.data?.items
      ? findMarketplacePackageForItem(selectedMarketplaceItem, packagesQuery.data.items)
      : null;
  const selectedMarketplacePackage =
    matchedMarketplacePackage ??
    (selectedMarketplaceItem && latestMarketplaceMutationPackage
      ? packageMatchesMarketplaceItem(selectedMarketplaceItem, latestMarketplaceMutationPackage)
        ? latestMarketplaceMutationPackage
        : null
      : null);
  const selectedMarketplaceInstallState = selectedMarketplaceItem
    ? detectMarketplaceInstallState({
        item: selectedMarketplaceItem,
        payload: selectedMarketplacePayload,
        agentAttachments: selectedAgentAttachments,
        matchedPackage: selectedMarketplacePackage,
        attachedExisting: lastDirectAttachedMarketplaceItemId === selectedMarketplaceItem.id,
        attachedPackage: lastAttachedMarketplacePackageId === selectedMarketplacePackage?.id,
      })
    : "available";

  return (
    <ConsoleShell title={text("工具运行层", "Tool Runtime")}>
      <div className="space-y-4 p-4">
        <section className="grid grid-cols-4 gap-3">
          <Metric label={text("工具总数", "Tools")} value={tools.length} />
          <Metric label={<TermHint description="模型上下文协议，用于接入外部工具">MCP</TermHint>} value={mcpCount} />
          <Metric label={text("需要沙箱", "Sandboxed")} value={sandboxCount} />
          <Metric label={text("分类", "Categories")} value={registryQuery.data?.categories.length ?? 0} />
        </section>

        <section className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <PackagePlus className="h-4 w-4" />
                {text("MCP / 技能商店", "MCP / Skill Marketplace")}
              </div>
              <Badge tone={marketplaceQuery.isError ? "warning" : "info"}>
                {marketplaceQuery.isFetching
                  ? text("同步中", "Syncing")
                  : `${marketplaceItems.length} ${text("条", "items")}`}
              </Badge>
            </CardHeader>
            <div className="grid gap-3 p-3 text-xs text-slate-500">
              <div className="grid gap-2 sm:grid-cols-3">
                <MarketStat label={text("可用来源", "Ready sources")} value={`${readyMarketplaceSources}/${marketplaceQuery.data?.sources.length ?? 0}`} />
                <MarketStat label={text("MCP", "MCP")} value={String(marketplaceItems.filter((item) => item.kind === "mcp").length)} />
                <MarketStat label={text("技能", "Skill")} value={String(marketplaceItems.filter((item) => item.kind === "skill").length)} />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="neutral">目标智能体 · {selectedAgentDisplayLabel}</Badge>
                <Badge tone="success">{marketplaceInstallStateMeta(selectedMarketplaceInstallState).label}</Badge>
                <Badge tone="info">{text("官方 MCP 注册表", "Official MCP Registry")}</Badge>
                <Badge tone="info">Smithery MCP 服务库</Badge>
                <Badge tone="info">{text("Smithery 技能库", "Smithery Skills")}</Badge>
                {marketplaceQuery.data?.errors.length ? (
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
                <Button type="button" variant="primary" onClick={() => setActiveConfigDialog("marketplace")}>
                  <Search className="h-3.5 w-3.5" />
                  {text("打开安装向导", "Open marketplace")}
                </Button>
                <Button type="button" variant="secondary" onClick={() => navigate("/tools/config")}>
                  <SlidersHorizontal className="h-3.5 w-3.5" />
                  运行配置
                </Button>
              </div>
              <MutationError
                error={
                  marketplaceQuery.error ??
                  attachMarketplaceCapabilityMutation.error ??
                  marketplacePublicPreflightMutation.error ??
                  marketplaceTrustedInstallMutation.error ??
                  marketplaceUploadInstallMutation.error
                }
              />
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
                  {text("上传技能", "Upload Skill")}
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
            status={sandboxReleasePathLabel((dependencyPreflightQuery.data?.local_release_path as string | undefined) ?? `${sandboxCount} ${text("需要隔离", "isolated")}`)}
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
                  `当前显示 ${selectedAgentDisplayLabel} 已启用的工具。安装 MCP 或技能后，成功启用的工具会自动出现在这里。`,
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
          open={activeConfigDialog === "marketplace"}
          title={text("MCP / 技能商店", "MCP / Skill Marketplace")}
          description={text("左侧挑选条目，右侧按步骤完成登记预检、审批版本、安装到智能体，并用案例测试。", "Pick an entry on the left, then register, approve, attach, and test it on the right.")}
          onClose={() => setActiveConfigDialog(null)}
          className="max-w-6xl"
        >
          <div className="grid gap-4 text-xs">
            <div className="grid gap-3 border-b border-slate-100 pb-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
              <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
                <label className="relative">
                  <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
                  <Input
                    aria-label={text("搜索 MCP 和技能商店", "Search MCP and Skill marketplace")}
                    value={marketplaceSearch}
                    onChange={(event) => setMarketplaceSearch(event.target.value)}
                    className="pl-8"
                    placeholder={text("搜索 GitHub、上下文、代码审查、知识检索...", "Search GitHub, context, code review...")}
                  />
                </label>
                <div className="inline-flex h-9 rounded-md border border-slate-200 bg-slate-50 p-1">
                  {(["all", "mcp", "skill"] as MarketplaceFilter[]).map((filter) => (
                    <button
                      key={filter}
                      type="button"
                      className={[
                        "rounded px-3 text-xs font-medium transition",
                        marketplaceFilter === filter
                          ? "bg-white text-slate-950 shadow-sm"
                          : "text-slate-500 hover:text-slate-800",
                      ].join(" ")}
                      onClick={() => setMarketplaceFilter(filter)}
                    >
                      {filter === "all" ? text("全部", "All") : filter === "mcp" ? "MCP" : "技能"}
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-slate-500">
                <Badge tone="neutral">目标智能体 · {selectedAgentDisplayLabel}</Badge>
                {(marketplaceQuery.data?.sources ?? []).map((source) => (
                  <Badge key={source.id} tone={source.status === "ready" ? "success" : "warning"}>
                    {marketplaceSourceLabel(source.label)} · {source.item_count}
                  </Badge>
                ))}
              </div>
            </div>
            {marketplaceQuery.data?.errors.length ? (
              <div className="rounded-md border border-amber-100 bg-amber-50 px-3 py-2 text-amber-800">
                {text("部分市场源暂不可用，已保留本地推荐。", "Some marketplace sources are unavailable; local recommendations remain visible.")}
              </div>
            ) : null}
            <div className="grid min-h-[560px] gap-4 xl:grid-cols-[minmax(360px,0.92fr)_minmax(460px,1.08fr)]">
              <div className="min-h-0 overflow-hidden rounded-md border border-slate-200 bg-white">
                <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2">
                  <div>
                    <div className="font-semibold text-slate-900">{text("商店条目", "Marketplace entries")}</div>
                    <div className="mt-0.5 text-[11px] text-slate-500">
                      {text("官方 MCP 注册表、Smithery 与平台推荐来源", "Official MCP Registry, Smithery, and platform curated")}
                    </div>
                  </div>
                  <Badge tone="neutral">{marketplaceItems.length} {text("条", "items")}</Badge>
                </div>
                <div className="max-h-[62vh] overflow-auto bg-slate-50 p-2">
                  {marketplaceItems.map((item) => (
                    <MarketplaceItemCard
                      key={item.id}
                      item={item}
                      selected={selectedMarketplaceItem?.id === item.id}
                      pending={
                        attachMarketplaceCapabilityMutation.isPending &&
                        attachMarketplaceCapabilityMutation.variables?.id === item.id
                      }
                      installState={detectMarketplaceInstallState({
                        item,
                        payload: normalizeMarketplaceInstallPayload(item),
                        agentAttachments: selectedAgentAttachments,
                        matchedPackage: findMarketplacePackageForItem(item, packagesQuery.data?.items ?? []),
                        attachedExisting: lastDirectAttachedMarketplaceItemId === item.id,
                        attachedPackage: false,
                      })}
                      onSelect={() => setSelectedMarketplaceItemId(item.id)}
                    />
                  ))}
                  {marketplaceQuery.isLoading ? (
                    <div className="rounded-md border border-slate-100 bg-white p-4 text-slate-500">
                      {text("正在同步市场...", "Syncing marketplace...")}
                    </div>
                  ) : null}
                  {!marketplaceQuery.isLoading && marketplaceItems.length === 0 ? (
                    <div className="rounded-md border border-slate-100 bg-white p-4 text-slate-500">
                      {text("没有匹配的 MCP 或技能条目", "No matching MCP or Skill entries")}
                    </div>
                  ) : null}
                </div>
              </div>
              <MarketplaceInstallPanel
                agentId={simpleAgentId}
                agentOptions={agentOptions}
                agentDisplayLabel={selectedAgentDisplayLabel}
                item={selectedMarketplaceItem}
                latestPackage={selectedMarketplacePackage}
                loading={packagesQuery.isLoading}
                installPayload={selectedMarketplacePayload}
                installState={selectedMarketplaceInstallState}
                preflightResult={
                  marketplaceRegistryPreflightMutation.data ?? marketplacePublicPreflightMutation.data
                }
                onAgentIdChange={setSimpleAgentId}
                onAttachExisting={(item) => attachMarketplaceCapabilityMutation.mutate(item)}
                onMarketplacePreflight={(payload) =>
                  marketplaceRegistryPreflightMutation.mutate({ ...payload, agent_id: simpleAgentId })
                }
                onPublicPreflight={(payload) =>
                  marketplacePublicPreflightMutation.mutate({ ...payload, agent_id: simpleAgentId })
                }
                onTrustedInstall={(payload) =>
                  marketplaceTrustedInstallMutation.mutate({ ...payload, agent_id: simpleAgentId })
                }
                onUploadInstall={(payload) =>
                  marketplaceUploadInstallMutation.mutate({ ...payload, agent_id: simpleAgentId })
                }
                onApprove={(pkg) => approveMarketplacePackageMutation.mutate(pkg)}
                onAttach={(pkg) => attachMarketplacePackageMutation.mutate(pkg)}
                onQuickTest={(toolName) => marketplaceQuickTestMutation.mutate(toolName)}
                quickTestQuery={marketplaceQuickQuery}
                onQuickTestQueryChange={setMarketplaceQuickQuery}
                quickTestResult={marketplaceQuickTestMutation.data}
                quickTesting={marketplaceQuickTestMutation.isPending}
                attachingExisting={attachMarketplaceCapabilityMutation.isPending}
                preflighting={
                  marketplaceRegistryPreflightMutation.isPending || marketplacePublicPreflightMutation.isPending
                }
                trustedInstalling={marketplaceTrustedInstallMutation.isPending}
                uploadInstalling={marketplaceUploadInstallMutation.isPending}
                approving={approveMarketplacePackageMutation.isPending}
                attaching={attachMarketplacePackageMutation.isPending}
                attachedExisting={lastDirectAttachedMarketplaceItemId === selectedMarketplaceItem?.id}
                attachedPackage={lastAttachedMarketplacePackageId === selectedMarketplacePackage?.id}
              />
            </div>
            <MutationError
              error={
                marketplaceQuery.error ??
                attachMarketplaceCapabilityMutation.error ??
                marketplaceRegistryPreflightMutation.error ??
                marketplacePublicPreflightMutation.error ??
                approveMarketplacePackageMutation.error ??
                attachMarketplacePackageMutation.error ??
                marketplaceQuickTestMutation.error ??
                marketplaceTrustedInstallMutation.error ??
                marketplaceUploadInstallMutation.error
              }
            />
          </div>
        </ConfigDialog>

        <ConfigDialog
          open={activeConfigDialog === "trusted-url"}
          title={text("可信 URL 一键安装", "Trusted URL one-click install")}
          description={text("从可信来源下载技能或能力包，并安装到目标智能体。", "Download a Skill or capability package from a trusted source and attach it to the target Agent.")}
          onClose={() => setActiveConfigDialog(null)}
        >
          <div className="grid gap-3 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-slate-600">{text("当前状态", "Current status")}</span>
              <Badge tone={trustedInstallMutation.data?.ready_state === "attached" ? "success" : "info"}>
                {trustedInstallMutation.data ? capabilityReadyStateLabel(trustedInstallMutation.data.ready_state) : text("等待安装", "v1 gate")}
              </Badge>
            </div>
            <label className="grid gap-1">
              <span className="font-medium text-slate-600">{text("可信来源 URL", "Trusted source URL")}</span>
              <Input aria-label="可信 URL 安装" value={trustedUrl} onChange={(event) => setTrustedUrl(event.target.value)} />
            </label>
            <label className="grid gap-1">
              <span className="font-medium text-slate-600">目标智能体</span>
              <MenuSelect
                ariaLabel="可信 URL 目标智能体"
                value={simpleAgentId}
                onChange={setSimpleAgentId}
                options={agentOptions}
                placeholder={text("选择目标智能体", "Select target agent")}
                size="compact"
              />
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
                {text("已生成暂存包标识，完成验证后再点击“启用”才能进入运行链路。", "staged_capability_id created; Enable is required before runtime attachment.")}{" "}
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
          description={text("上传技能说明文件（SKILL.md）并安装到目标智能体。", "Upload SKILL.md content and attach it to the target Agent.")}
          onClose={() => setActiveConfigDialog(null)}
        >
          <div className="grid gap-3 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-slate-600">{text("当前状态", "Current status")}</span>
              <Badge tone={uploadInstallMutation.data?.ready_state === "attached" ? "success" : "info"}>
                {uploadInstallMutation.data ? capabilityReadyStateLabel(uploadInstallMutation.data.ready_state) : text("无需编辑清单", "No manifest editing")}
              </Badge>
            </div>
            <label className="grid gap-1">
              <span className="font-medium text-slate-600">{text("包名称", "Package name")}</span>
              <Input aria-label="上传包名称" value={uploadName} onChange={(event) => setUploadName(event.target.value)} />
            </label>
            <label className="grid gap-1">
              <span className="font-medium text-slate-600">技能说明文件内容（SKILL.md）</span>
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
                {latestPackage ? capabilityPackageStatusLabel(latestPackage.status) : text("未暂存", "Not staged")}
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
                <span className="font-medium text-slate-600">目标智能体</span>
                <MenuSelect
                  ariaLabel="能力包安装目标智能体"
                  value={packageAgentId}
                  onChange={setPackageAgentId}
                  options={agentOptions}
                  placeholder={text("选择目标智能体", "Select target agent")}
                  size="compact"
                />
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
                {text("安装到智能体", "Install to Agent")}
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
                {text("校验状态", "Validation")} {capabilityValidationStatusLabel(validationMutation.data.status)} · {capabilityValidationModeLabel(validationMutation.data.validation_mode ?? "manifest_only_no_execution")}
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
          title={text("智能体范围测试调用", "Agent-scoped test invoke")}
          description={text("使用智能体范围执行一次工具测试，验证附件和策略链路。", "Run one Agent-scoped tool test to validate attachment and policy routing.")}
          onClose={() => setActiveConfigDialog(null)}
        >
          <div className="grid gap-3 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-slate-600">{text("当前状态", "Current status")}</span>
              <Badge tone={testInvokeMutation.data?.allowed ? "success" : "neutral"}>
                {testInvokeMutation.data ? toolCallStatusLabel(testInvokeMutation.data.tool_call.status) : text("待测试", "Ready")}
              </Badge>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <label className="grid gap-1">
                <span className="font-medium text-slate-600">目标智能体</span>
                <MenuSelect
                  ariaLabel="测试目标智能体"
                  value={testAgentId}
                  onChange={setTestAgentId}
                  options={agentOptions}
                  placeholder={text("选择目标智能体", "Select target agent")}
                  size="compact"
                />
              </label>
              <label className="grid gap-1">
                <span className="font-medium text-slate-600">{text("工具名", "Tool name")}</span>
                <Input aria-label="测试工具名" value={testToolName} onChange={(event) => setTestToolName(event.target.value)} />
              </label>
            </div>
            <Textarea aria-label="测试输入 JSON" value={invokeInput} onChange={(event) => setInvokeInput(event.target.value)} className="font-mono text-xs" />
            <div className="rounded-md border border-cyan-100 bg-cyan-50 p-2 text-cyan-900">
              建议案例：将工具名设置为 <code className="font-mono">mcp_context_search</code>，输入
              {" "}
              <code className="font-mono">{'{"query":"发布准备情况","limit":2}'}</code>
              ，确认工具调用返回命中结果。
            </div>
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
  icon: ReactNode;
  title: ReactNode;
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

function Metric({ label, value }: { label: ReactNode; value: number }) {
  return (
    <Card className="p-4">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="mt-1 font-mono text-2xl text-slate-900">{value}</div>
    </Card>
  );
}

function MarketStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50 px-3 py-2">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="mt-0.5 font-mono text-base text-slate-900">{value}</div>
    </div>
  );
}

function MarketplaceItemCard({
  item,
  selected,
  pending,
  installState,
  onSelect,
}: {
  item: CapabilityMarketplaceItem;
  selected: boolean;
  pending: boolean;
  installState: MarketplaceInstallState;
  onSelect: () => void;
}) {
  const stateMeta = marketplaceInstallStateMeta(installState);
  const guide = mcpGuideFor(item);
  return (
    <button
      type="button"
      className={[
        "mb-2 w-full rounded-xl border bg-white p-3 text-left transition disabled:cursor-wait disabled:opacity-70 active:translate-y-px",
        selected
          ? "border-slate-900 bg-white shadow-sm ring-2 ring-slate-100"
          : "border-slate-200 hover:border-slate-400 hover:bg-slate-50",
      ].join(" ")}
      disabled={pending}
      onClick={onSelect}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-slate-950">{item.display_name}</div>
          <div className="mt-0.5 truncate font-mono text-[11px] text-slate-500">{item.name}</div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <Badge tone={item.kind === "mcp" ? "info" : "neutral"}>
            {item.kind === "mcp" ? "MCP" : "技能"}
          </Badge>
          <Badge tone={stateMeta.tone}>{pending ? "处理中" : stateMeta.label}</Badge>
        </div>
      </div>
      <div className="mt-2 grid gap-1.5 leading-5 text-slate-600">
        <p className="line-clamp-2">{guide.summary}</p>
        <div className="line-clamp-1 text-[11px] text-cyan-800">配置：{guide.config}</div>
        <div className="line-clamp-1 text-[11px] text-slate-500">
          可用于：{guide.scenarios.slice(0, 2).join(" / ")}
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {item.badges.map((badge) => (
          <Badge key={badge} tone={badge === "verified" || item.verified ? "neutral" : "neutral"}>
            {marketplaceBadgeLabel(badge)}
          </Badge>
        ))}
      </div>
      <div className="mt-3 flex items-center justify-between gap-2 text-[11px] text-slate-500">
        <span className="truncate">{marketplaceSourceLabel(item.source_label)}</span>
        <div className="flex shrink-0 items-center gap-1.5">
          {item.verified ? <Badge tone="success">已验证</Badge> : null}
          <Badge tone="neutral">{pending ? "处理中" : installModeLabel(item.install_mode, item.install_label)}</Badge>
        </div>
      </div>
    </button>
  );
}

function MarketplaceInstallPanel({
  agentId,
  agentOptions,
  agentDisplayLabel,
  item,
  latestPackage,
  loading,
  installPayload,
  installState,
  preflightResult,
  onAgentIdChange,
  onAttachExisting,
  onMarketplacePreflight,
  onPublicPreflight,
  onTrustedInstall,
  onUploadInstall,
  onApprove,
  onAttach,
  onQuickTest,
  quickTestQuery,
  onQuickTestQueryChange,
  quickTestResult,
  quickTesting,
  attachingExisting,
  preflighting,
  trustedInstalling,
  uploadInstalling,
  approving,
  attaching,
  attachedExisting,
  attachedPackage,
}: {
  agentId: string;
  agentOptions: MenuSelectOption[];
  agentDisplayLabel: string;
  item: CapabilityMarketplaceItem | null;
  latestPackage: CapabilityPackage | null;
  loading: boolean;
  installPayload: CapabilityMarketplacePreflightPayload | null;
  installState: MarketplaceInstallState;
  preflightResult?: CapabilitySimpleInstallResponse;
  onAgentIdChange: (value: string) => void;
  onAttachExisting: (item: CapabilityMarketplaceItem) => void;
  onMarketplacePreflight: (payload: CapabilityMarketplacePreflightPayload) => void;
  onPublicPreflight: (payload: CapabilitySimpleInstallPayload) => void;
  onTrustedInstall: (payload: CapabilitySimpleInstallPayload) => void;
  onUploadInstall: (payload: CapabilitySimpleInstallPayload) => void;
  onApprove: (pkg: CapabilityPackage) => void;
  onAttach: (pkg: CapabilityPackage) => void;
  onQuickTest: (toolName: string) => void;
  quickTestQuery: string;
  onQuickTestQueryChange: (value: string) => void;
  quickTestResult?: ToolExecuteResult;
  quickTesting: boolean;
  attachingExisting: boolean;
  preflighting: boolean;
  trustedInstalling: boolean;
  uploadInstalling: boolean;
  approving: boolean;
  attaching: boolean;
  attachedExisting: boolean;
  attachedPackage: boolean;
}) {
  const { text } = useI18n();
  const packageReady = latestPackage?.status === "approved";
  const packageStaged = latestPackage?.status === "staged";
  const installMode = item?.install_mode;
  const installStepDone = Boolean(attachedExisting || attachedPackage);
  const quickTestToolName = item ? marketplaceToolName(item, installPayload) : "";
  const installStateMeta = marketplaceInstallStateMeta(installState);
  const quickCases = item ? marketplaceSuggestedTestCases(item) : [];
  const guide = item ? mcpGuideFor(item) : null;
  const canQuickTest =
    Boolean(item?.kind === "mcp" && quickTestToolName && agentId.trim()) &&
    (installMode === "attach_existing" || packageReady || attachedPackage);
  const actionLabel =
    installMode === "attach_existing"
      ? text("直接启用", "Enable")
      : installMode === "marketplace_preflight"
        ? text("登记预检", "Register")
        : installMode === "public_preflight"
          ? text("下载预检", "Download preflight")
          : installMode === "trusted_install"
            ? text("安装并启用", "Install and enable")
            : text("本地安装", "Local install");
  return (
    <aside
      aria-label={text("商店安装工作台", "Marketplace install workbench")}
      className="min-h-0 rounded-md border border-slate-200 bg-white shadow-sm"
    >
      <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="font-semibold text-slate-900">{text("安装工作台", "Install workbench")}</div>
            <div className="mt-0.5 text-[11px] text-slate-500">
              {text("按状态提示连续完成登记、审批、安装与案例验证", "Register, approve, and attach in one place")}
            </div>
          </div>
          <Badge tone={installStateMeta.tone}>
            {installStateMeta.label}
          </Badge>
        </div>
      </div>

      {!item ? (
        <div className="p-4 text-slate-500">
          {text("先在左侧选择 MCP 或技能条目。", "Select an MCP or Skill on the left.")}
        </div>
      ) : (
        <div className="grid gap-4 p-4">
          <div className="rounded-md border border-slate-200 bg-white p-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-slate-950">{item.display_name}</div>
                <div className="mt-0.5 truncate font-mono text-[11px] text-slate-500">{item.name}</div>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1.5">
                <Badge tone={item.kind === "mcp" ? "info" : "neutral"}>{item.kind === "mcp" ? "MCP" : "技能"}</Badge>
                <Badge tone={installStateMeta.tone}>{installStateMeta.label}</Badge>
              </div>
            </div>
            {guide ? (
              <div className="mt-3 grid gap-2 rounded-md border border-cyan-100 bg-cyan-50 p-3 leading-5 text-cyan-950">
                <div className="font-semibold">这个{item.kind === "mcp" ? " MCP" : "技能"}能做什么</div>
                <div>{guide.summary}</div>
                <div className="grid gap-1 text-[11px] text-cyan-900 sm:grid-cols-2">
                  <div>
                    <span className="font-semibold">常见场景：</span>
                    {guide.scenarios.join(" / ")}
                  </div>
                  <div>
                    <span className="font-semibold">配置要求：</span>
                    {guide.config}
                  </div>
                </div>
              </div>
            ) : null}
            <div className="mt-3 flex flex-wrap gap-1.5">
              {item.badges.map((badge) => (
                <Badge key={badge} tone={item.verified && badge === "verified" ? "success" : "neutral"}>
                  {marketplaceBadgeLabel(badge)}
                </Badge>
              ))}
            </div>
            <div className="mt-3 grid gap-1.5 text-[11px] text-slate-500">
              <div className="flex items-center gap-1.5">
                <SlidersHorizontal className="h-3.5 w-3.5" />
                {text("安装方式", "Install mode")} · {installModeLabel(item.install_mode, item.install_label)}
              </div>
              {item.repository_url ? (
                <div className="flex min-w-0 items-center gap-1.5">
                  <GitBranch className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{item.repository_url}</span>
                </div>
              ) : null}
              {item.homepage_url ? (
                <div className="flex min-w-0 items-center gap-1.5">
                  <ExternalLink className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{item.homepage_url}</span>
                </div>
              ) : null}
            </div>
          </div>

          <div className="rounded-md border border-cyan-100 bg-cyan-50 p-3 leading-5 text-cyan-900">
            <div className="mb-1 font-semibold">当前下一步</div>
            <div>{marketplaceNextStepCopy(installState, item.kind)}</div>
          </div>

          <div className="grid gap-2 rounded-md border border-amber-100 bg-amber-50 p-3 leading-5 text-amber-800">
            {item.risk_notes.map((note) => (
              <div key={note}>{note}</div>
            ))}
          </div>

          <div className="grid gap-2 md:grid-cols-2">
            <label className="grid gap-1">
              <span className="font-medium text-slate-600">目标智能体</span>
              <MenuSelect
                ariaLabel="市场侧栏安装目标智能体"
                value={agentId}
                onChange={onAgentIdChange}
                options={agentOptions}
                placeholder={text("选择目标智能体", "Select target agent")}
                size="compact"
              />
            </label>
            <label className="grid gap-1">
              <span className="font-medium text-slate-600">{text("来源", "Source")}</span>
              <Input aria-label="市场安装来源" value={installPayload?.source_uri ?? marketplaceSourceLabel(item.source_label)} readOnly />
            </label>
          </div>

          <div className="grid gap-3 rounded-md border border-slate-200 bg-slate-50 p-3">
            <div className="grid gap-2 sm:grid-cols-3">
              <StepPill active done={Boolean(preflightResult || latestPackage || installMode === "attach_existing")} label={text("登记", "Register")} />
              <StepPill active={packageStaged || packageReady} done={packageReady} label={text("审批", "Approve")} />
              <StepPill active={packageReady} done={installStepDone} label={text("安装", "Attach")} />
            </div>
            <div className="flex flex-wrap gap-2">
              {installMode === "attach_existing" ? (
                <Button
                  type="button"
                  variant="primary"
                  onClick={() => onAttachExisting(item)}
                  disabled={attachingExisting || !agentId.trim()}
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  {attachingExisting ? text("启用中", "Enabling") : actionLabel}
                </Button>
              ) : null}
              {installMode === "marketplace_preflight" && installPayload ? (
                <Button
                  type="button"
                  variant="primary"
                  onClick={() => onMarketplacePreflight(installPayload)}
                  disabled={preflighting}
                >
                  <ShieldCheck className="h-3.5 w-3.5" />
                  {preflighting ? text("登记中", "Registering") : actionLabel}
                </Button>
              ) : null}
              {installMode === "public_preflight" && installPayload ? (
                <Button
                  type="button"
                  variant="primary"
                  onClick={() => onPublicPreflight(installPayload)}
                  disabled={preflighting || !installPayload.source_uri}
                >
                  <ShieldCheck className="h-3.5 w-3.5" />
                  {preflighting ? text("预检中", "Preflighting") : actionLabel}
                </Button>
              ) : null}
              {installMode === "trusted_install" && installPayload ? (
                <Button
                  type="button"
                  variant="primary"
                  onClick={() => onTrustedInstall(installPayload)}
                  disabled={trustedInstalling || !installPayload.source_uri}
                >
                  <Download className="h-3.5 w-3.5" />
                  {trustedInstalling ? text("安装中", "Installing") : actionLabel}
                </Button>
              ) : null}
              {installMode === "upload_install" && installPayload ? (
                <Button
                  type="button"
                  variant="primary"
                  onClick={() => onUploadInstall(installPayload)}
                  disabled={uploadInstalling}
                >
                  <PackagePlus className="h-3.5 w-3.5" />
                  {uploadInstalling ? text("安装中", "Installing") : actionLabel}
                </Button>
              ) : null}
              <Button
                type="button"
                onClick={() => latestPackage && onApprove(latestPackage)}
                disabled={!latestPackage || !packageStaged || approving}
              >
                <CheckCircle2 className="h-3.5 w-3.5" />
                {approving ? text("审批中", "Approving") : text("审批版本", "Approve version")}
              </Button>
              <Button
                type="button"
                onClick={() => latestPackage && onAttach(latestPackage)}
                disabled={!latestPackage || !packageReady || !agentId.trim() || attaching}
              >
                <PackagePlus className="h-3.5 w-3.5" />
                {attaching ? text("安装中", "Installing") : text("安装到智能体", "Install to Agent")}
              </Button>
            </div>
            {loading && !latestPackage ? (
              <div className="rounded-md border border-slate-100 bg-slate-50 p-2 text-slate-500">
                {text("正在加载能力包...", "Loading capability packages...")}
              </div>
            ) : null}
            {preflightResult?.staged_capability_id ? (
              <div className="rounded-md border border-amber-100 bg-amber-50 p-2 text-amber-800">
                {text("登记包已就绪，下一步请审批版本。", "Registered package is ready.")}{" "}
                <span className="font-mono">{preflightResult.staged_capability_id}</span>
              </div>
            ) : null}
            {attachedExisting ? (
              <div className="rounded-md border border-emerald-100 bg-emerald-50 p-2 text-emerald-700">
                {text("已启用到目标智能体。", "Enabled for the target Agent.")}
              </div>
            ) : null}
            {attachedPackage ? (
              <div className="rounded-md border border-emerald-100 bg-emerald-50 p-2 text-emerald-700">
                {text("已安装到目标智能体。", "Installed for the target Agent.")}
              </div>
            ) : null}
          </div>

          {latestPackage ? (
            <PackageLifecycleSummary pkg={latestPackage} />
          ) : (
            <div className="rounded-md border border-slate-100 bg-slate-50 p-3 leading-5 text-slate-500">
              <div className="mb-1 inline-flex items-center gap-1.5 font-medium text-slate-700">
                <FileCheck2 className="h-3.5 w-3.5" />
                {text("商店登记策略", "Marketplace registration policy")}
              </div>
              {text(
                "外部商店条目先登记注册表元数据，不抓取主页 URL；审批通过后才会生成不可变版本。",
                "External marketplace entries register registry metadata first without fetching homepage URLs; approval creates the immutable version.",
              )}
            </div>
          )}

          {item.kind === "mcp" ? (
            <div className="grid gap-3 rounded-md border border-slate-200 bg-white p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="font-semibold text-slate-900">{text("快速测试", "Quick test")}</div>
                  <div className="mt-0.5 font-mono text-[11px] text-slate-500">
                    智能体 {agentDisplayLabel || "--"} · 工具 {quickTestToolName || "--"}
                  </div>
                </div>
                <Badge tone={quickTestResult?.allowed ? "success" : "neutral"}>
                  {quickTestResult ? toolCallStatusLabel(quickTestResult.tool_call.status) : text("待测试", "Ready")}
                </Badge>
              </div>
              {quickCases.length ? (
                <div className="flex flex-wrap gap-2">
                  {quickCases.map((testCase) => (
                    <button
                      key={testCase.query}
                      type="button"
                      onClick={() => onQuickTestQueryChange(testCase.query)}
                      className="rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1 text-[11px] font-medium text-cyan-900 transition hover:bg-cyan-100 active:translate-y-px"
                    >
                      {testCase.label}
                    </button>
                  ))}
                </div>
              ) : null}
              <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto]">
                <Input
                  aria-label="市场快速测试查询"
                  value={quickTestQuery}
                  onChange={(event) => onQuickTestQueryChange(event.target.value)}
                  placeholder={text("输入搜索词", "Enter a query")}
                />
                <Button
                  type="button"
                  onClick={() => quickTestToolName && onQuickTest(quickTestToolName)}
                  disabled={!canQuickTest || quickTesting || !quickTestQuery.trim()}
                >
                  <Timer className="h-3.5 w-3.5" />
                  {quickTesting ? text("测试中", "Testing") : text("一键测试", "Run test")}
                </Button>
              </div>
              {!canQuickTest ? (
                <div className="rounded-md border border-slate-100 bg-slate-50 p-2 text-slate-500">
                  {text(
                    "先完成启用或安装，再从这里直接测试当前 MCP。",
                    "Enable or attach this MCP first, then test it here.",
                  )}
                </div>
              ) : null}
              {quickTestResult ? <QuickTestResult result={quickTestResult} /> : null}
            </div>
          ) : (
            <div className="grid gap-2 rounded-md border border-slate-200 bg-white p-3 text-[11px] leading-5 text-slate-600">
              <div className="font-semibold text-slate-900">建议验证案例</div>
              <div>1. 完成安装后，确认顶部状态变为“已安装”。</div>
              <div>2. 重新打开商店，检查当前智能体仍显示已安装或可继续审批。</div>
              <div>3. 在高级包管理中确认版本、来源和附件标识都已生成。</div>
            </div>
          )}
        </div>
      )}
    </aside>
  );
}

function StepPill({ label, active, done }: { label: string; active: boolean; done: boolean }) {
  return (
    <span
      className={[
        "inline-flex h-7 items-center justify-center gap-1.5 rounded-md border px-2.5 text-[11px] font-medium",
        done
          ? "border-emerald-200 bg-emerald-50 text-emerald-700"
          : active
            ? "border-slate-300 bg-white text-slate-800"
            : "border-slate-200 bg-slate-50 text-slate-400",
      ].join(" ")}
    >
      {done ? <CheckCircle2 className="h-3.5 w-3.5" /> : null}
      {label}
    </span>
  );
}

function PackageLifecycleSummary({ pkg }: { pkg: CapabilityPackage }) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50 p-2 font-mono text-[11px] text-slate-600">
      <div>{pkg.package_key} · {capabilityPackageStatusLabel(pkg.status)} · {capabilitySourceKindLabel(pkg.source_kind)}</div>
      <div>能力包 {pkg.id}</div>
      <div>来源哈希 {pkg.source_sha256.slice(0, 12)}{pkg.pinned_ref ? ` · ${pkg.pinned_ref}` : ""}</div>
      <div>能力 {pkg.capability_id ?? "--"} / {pkg.capability_version_id ?? "--"}</div>
    </div>
  );
}

function SimpleInstallResult({ result }: { result?: CapabilitySimpleInstallResponse }) {
  if (!result) return null;
  return (
    <div className="rounded-md border border-emerald-100 bg-emerald-50 p-3 text-[11px] text-emerald-900">
      <div className="font-semibold">
        {capabilityReadyStateLabel(result.ready_state)} · {capabilityNextStepLabel(result.next_step_label)}
      </div>
      <div className="mt-1 font-mono">能力包 {result.package.id}</div>
      <div className="font-mono">能力 {result.capability_id ?? "--"} / {result.capability_version_id ?? "--"}</div>
      {result.attachment ? <div className="font-mono">附件 {result.attachment.attachment_id}</div> : null}
    </div>
  );
}

function QuickTestResult({ result }: { result: ToolExecuteResult }) {
  const outputResult = isRecord(result.output.result) ? result.output.result : null;
  const items = Array.isArray(outputResult?.items) ? outputResult.items : [];
  return (
    <div className="grid gap-2 rounded-md border border-emerald-100 bg-emerald-50 p-2 text-[11px] text-emerald-800">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">
          {toolCallStatusLabel(result.tool_call.status)} · {result.tool_call.duration_ms}ms
        </span>
        <span className="font-mono">{String(result.output.mcp_server ?? result.tool_call.tool_name)}</span>
      </div>
      {items.length ? (
        <div className="grid gap-1">
          {items.slice(0, 3).map((item, index) => {
            const row = isRecord(item) ? item : { title: String(item) };
            return (
              <div key={`${String(row.id ?? index)}-${index}`} className="rounded border border-emerald-100 bg-white/70 p-2">
                <div className="truncate font-medium text-emerald-950">
                  {String(row.title ?? row.id ?? `result ${index + 1}`)}
                </div>
                {row.snippet ? (
                  <div className="mt-0.5 line-clamp-2 text-emerald-700">
                    {String(row.snippet)}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : (
        <pre className="max-h-28 overflow-auto rounded border border-emerald-100 bg-white/70 p-2 font-mono text-[10px] text-emerald-800">
          {JSON.stringify(result.output, null, 2)}
        </pre>
      )}
    </div>
  );
}

function MutationError({ error }: { error: unknown }) {
  if (!(error instanceof Error)) return null;
  return (
    <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs leading-5 text-red-800">
      {error.message}
    </div>
  );
}

function marketplaceInstallStateMeta(state: MarketplaceInstallState) {
  switch (state) {
    case "installed":
      return { tone: "success" as const, label: "已安装" };
    case "approved":
      return { tone: "info" as const, label: "待安装" };
    case "staged":
      return { tone: "warning" as const, label: "待审批" };
    default:
      return { tone: "neutral" as const, label: "未安装" };
  }
}

function capabilityReadyStateLabel(state: string) {
  switch (state) {
    case "attached":
      return "已安装";
    case "ready":
      return "待安装";
    case "staged":
      return "待审批";
    case "invalid":
      return "校验失败";
    default:
      return state;
  }
}

function capabilityNextStepLabel(label: string) {
  switch (label) {
    case "Open Agent attachment":
      return "已完成安装";
    case "Enable after validation":
      return "验证后启用";
    case "Attach to Agent":
      return "安装到智能体";
    case "Approve marketplace version":
      return "审批商店版本";
    default:
      return label;
  }
}

function capabilityPackageStatusLabel(status: string) {
  switch (status) {
    case "staged":
      return "待审批";
    case "approved":
      return "待安装";
    case "uninstalled":
      return "已卸载";
    case "invalid":
      return "校验失败";
    default:
      return status;
  }
}

function capabilitySourceKindLabel(sourceKind: string) {
  switch (sourceKind) {
    case "marketplace_preflight":
      return "商店登记";
    case "public_git":
      return "公开 Git";
    case "public_url":
      return "公网 URL";
    case "trusted_url":
      return "可信 URL";
    case "private_upload":
      return "本地上传";
    default:
      return sourceKind;
  }
}

function capabilityValidationStatusLabel(status: string) {
  switch (status) {
    case "valid":
      return "通过";
    case "invalid":
      return "失败";
    default:
      return status;
  }
}

function capabilityValidationModeLabel(mode: string) {
  switch (mode) {
    case "manifest_only_no_execution":
      return "仅校验清单，不执行";
    default:
      return mode;
  }
}

function toolCallStatusLabel(status: string) {
  switch (status) {
    case "SUCCESS":
      return "成功";
    case "FAILED":
      return "失败";
    case "PENDING":
      return "处理中";
    default:
      return status;
  }
}

function toolNetworkPolicyLabel(policy: string) {
  switch (policy) {
    case "none":
      return "无网络";
    case "disabled":
    case "deny":
      return "禁网";
    case "allow":
      return "允许联网";
    case "sandbox-only":
      return "仅沙箱联网";
    default:
      return policy;
  }
}

function toolAuditLevelLabel(level: string) {
  switch (level) {
    case "standard":
      return "标准审计";
    case "full":
      return "完整审计";
    case "elevated":
      return "增强审计";
    default:
      return level;
  }
}

function sandboxReleasePathLabel(value: string) {
  if (value === "no-container") {
    return "本地无容器路径";
  }
  return value;
}

function marketplaceSourceLabel(label: string) {
  switch (label) {
    case "Official MCP Registry":
    case "官方 MCP Registry":
    case "官方 MCP 注册表":
      return "官方 MCP 注册表";
    case "Harness 推荐":
    case "平台推荐":
      return "平台推荐";
    case "Smithery MCP":
    case "Smithery MCP 服务库":
      return "Smithery MCP 服务库";
    case "Smithery Skills":
    case "Smithery 技能库":
      return "Smithery 技能库";
    default:
      return label;
  }
}

function marketplaceBadgeLabel(badge: string) {
  switch (badge) {
    case "Skill":
      return "技能";
    case "remote":
      return "远程";
    case "stdio":
      return "标准输入输出";
    case "Knowledge":
      return "知识";
    case "Context":
      return "上下文";
    case "Coding":
      return "代码";
    case "verified":
      return "已验证";
    case "latest":
      return "最新";
    case "active":
      return "活跃";
    default:
      return badge;
  }
}

function installModeLabel(mode: CapabilityMarketplaceItem["install_mode"], fallback: string) {
  switch (mode) {
    case "attach_existing":
      return "直接启用";
    case "marketplace_preflight":
      return "登记预检";
    case "public_preflight":
      return "下载预检";
    case "trusted_install":
      return "安装并启用";
    case "upload_install":
      return "本地安装";
    default:
      return fallback;
  }
}

function packageMatchesMarketplaceItem(item: CapabilityMarketplaceItem, pkg: CapabilityPackage) {
  return findMarketplacePackageForItem(item, [pkg])?.id === pkg.id;
}

function marketplaceNextStepCopy(state: MarketplaceInstallState, kind: CapabilityMarketplaceItem["kind"]) {
  switch (state) {
    case "installed":
      return kind === "mcp"
        ? "已安装完成。现在直接运行下方测试案例，确认当前智能体可以正常调用这个 MCP。"
        : "已安装完成。建议回到高级包管理或智能体能力附件，确认版本和挂载状态都正确。";
    case "approved":
      return "版本已经审批通过，下一步只需点击“安装到智能体”。";
    case "staged":
      return "已经登记预检完成，下一步请点击“审批版本”。";
    default:
      return "先根据条目类型执行“直接启用”或“登记预检”，再按状态提示继续。";
  }
}

function marketplaceSuggestedTestCases(item: CapabilityMarketplaceItem) {
  const guide = mcpGuideFor(item);
  const primary = guide.testQuery;
  if (item.name.includes("context")) {
    return [
      { label: `案例：${primary}`, query: primary },
      { label: "案例：上下文摘要", query: "上下文摘要" },
    ];
  }
  return [
    { label: `案例：${primary}`, query: primary },
    { label: "案例：模型发布新闻", query: "模型发布新闻" },
  ];
}

function detectMarketplaceInstallState({
  item,
  payload,
  agentAttachments,
  matchedPackage,
  attachedExisting,
  attachedPackage,
}: {
  item: CapabilityMarketplaceItem;
  payload: CapabilityMarketplacePreflightPayload | null;
  agentAttachments: AgentCapabilityAttachmentSummary[];
  matchedPackage: CapabilityPackage | null;
  attachedExisting: boolean;
  attachedPackage: boolean;
}): MarketplaceInstallState {
  const identifiers = new Set<string>();
  const manifest = payload?.manifest;

  if (typeof item.install_payload.capability_id === "string") identifiers.add(item.install_payload.capability_id);
  if (typeof item.name === "string" && item.name) identifiers.add(item.name);
  if (item.install_payload.package_type === "mcp_server" && typeof item.name === "string" && item.name) {
    identifiers.add(`package-${item.name}`);
    identifiers.add(`tool:${item.name}`);
  }
  if (typeof matchedPackage?.capability_id === "string" && matchedPackage.capability_id) identifiers.add(matchedPackage.capability_id);
  if (typeof matchedPackage?.capability_version_id === "string" && matchedPackage.capability_version_id) identifiers.add(matchedPackage.capability_version_id);
  if (typeof matchedPackage?.package_key === "string" && matchedPackage.package_key) identifiers.add(matchedPackage.package_key);
  if (isRecord(manifest) && typeof manifest.name === "string" && manifest.name.trim()) identifiers.add(manifest.name);
  if (isRecord(manifest) && typeof manifest.name === "string" && manifest.name.trim()) {
    identifiers.add(`package-${manifest.name}`);
    identifiers.add(`tool:${manifest.name}`);
  }

  const installed = attachedExisting
    || attachedPackage
    || agentAttachments.some(
      (attachment) =>
        attachment.enabled &&
        (stringInSet(identifiers, attachment.capability_id)
          || stringInSet(identifiers, attachment.capability_key)
          || stringInSet(identifiers, attachment.capability_version_id)
          || Array.from(identifiers).some(
            (identifier) =>
              attachment.capability_key === `tool:${identifier}` ||
              attachment.capability_key === `package-${identifier}` ||
              stringStartsWith(attachment.capability_version_id, `${identifier}-`) ||
              stringStartsWith(attachment.capability_version_id, `${identifier}:`),
          )),
    );

  if (installed) return "installed";
  if (matchedPackage?.status === "approved") return "approved";
  if (matchedPackage?.status === "staged") return "staged";
  return "available";
}

function findMarketplacePackageForItem(
  item: CapabilityMarketplaceItem,
  packages: CapabilityPackage[],
) {
  const payload = normalizeMarketplaceInstallPayload(item);
  const manifest = payload.manifest;
  const identifiers = new Set<string>([
    item.name,
    payload.source_uri ?? "",
    payload.pinned_ref ?? "",
    typeof item.install_payload.capability_id === "string" ? item.install_payload.capability_id : "",
    isRecord(manifest) && typeof manifest.name === "string" ? manifest.name : "",
  ]);

  return (
    packages.find((pkg) => {
      const packageValues = [
        pkg.package_key,
        pkg.capability_id ?? "",
        pkg.capability_version_id ?? "",
        pkg.source_uri ?? "",
        pkg.pinned_ref ?? "",
      ];
      return packageValues.some((value) => value && identifiers.has(value));
    }) ?? null
  );
}

function simpleInstallSuccessSummary(result: CapabilitySimpleInstallResponse, agentId: string) {
  const state = capabilityReadyStateLabel(result.ready_state);
  if (result.attachment) {
    return `${state}，已安装到智能体 ${agentId}，附件 ${result.attachment.attachment_id} 已创建。`;
  }
  return `${state}，下一步：${capabilityNextStepLabel(result.next_step_label)}。`;
}

function isPublicPackageSource(value: string) {
  const source = value.trim();
  return source.startsWith("git+") || source.startsWith("https://") || source.startsWith("http://");
}

function stringInSet(values: Set<string>, value: unknown) {
  return typeof value === "string" && values.has(value);
}

function stringStartsWith(value: unknown, prefix: string) {
  return typeof value === "string" && value.startsWith(prefix);
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

function normalizeMarketplaceInstallPayload(
  item: CapabilityMarketplaceItem,
): CapabilityMarketplacePreflightPayload {
  const payload = item.install_payload;
  return {
    source_uri: typeof payload.source_uri === "string" ? payload.source_uri : undefined,
    pinned_ref: typeof payload.pinned_ref === "string" ? payload.pinned_ref : null,
    package_type: payload.package_type,
    display_name: typeof payload.display_name === "string" ? payload.display_name : undefined,
    description: typeof payload.description === "string" ? payload.description : undefined,
    agent_id: null,
    permissions: Array.isArray(payload.permissions) ? payload.permissions.map(String) : [],
    secret_refs: Array.isArray(payload.secret_refs) ? payload.secret_refs.map(String) : [],
    manifest: isRecord(payload.manifest) ? payload.manifest : null,
    content: isRecord(payload.content) ? payload.content : {},
    marketplace_source:
      typeof payload.marketplace_source === "string" ? payload.marketplace_source : item.source,
    marketplace_item_id:
      typeof payload.marketplace_item_id === "string" ? payload.marketplace_item_id : item.id,
  };
}

function marketplaceToolName(
  item: CapabilityMarketplaceItem,
  payload: CapabilityMarketplacePreflightPayload | null,
) {
  if (typeof item.install_payload.capability_id === "string") {
    return item.install_payload.capability_id;
  }
  const manifest = payload?.manifest;
  if (isRecord(manifest) && typeof manifest.name === "string" && manifest.name.trim()) {
    return manifest.name;
  }
  return item.name;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function agentTargetLabel(agentId: string, agents: AgentDefinition[]) {
  const matched = agents.find((agent) => agent.id === agentId);
  if (matched?.name?.trim()) {
    return matched.name === agentId ? matched.name : `${matched.name}（${agentId}）`;
  }
  if (agentId === "default") {
    return "默认智能体（default）";
  }
  return agentId;
}
