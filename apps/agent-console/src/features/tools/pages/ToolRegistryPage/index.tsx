import { useCallback, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ConsoleShell } from "../../../../app/ConsoleShell";
import { feedbackErrorMessage, notifyFeedback } from "../../../../components/ui/feedback-toast";
import type { MenuSelectOption } from "../../../../components/ui/menu-select";
import { useI18n } from "../../../../lib/i18n";
import { statusLabel } from "../../../../lib/labels";
import { AdapterSchemaDrawer } from "../../components/AdapterSchemaDrawer";
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
  listAdapters,
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
  type CapabilitySimpleInstallPayload,
} from "../../../tasks/api";
import { ToolRegistryDialogs } from "./dialogs";
import {
  agentTargetLabel,
  capabilityPackageStatusLabel,
  capabilityValidationModeLabel,
  detectMarketplaceInstallState,
  findMarketplacePackageForItem,
  isPublicPackageSource,
  normalizeMarketplaceInstallPayload,
  packageMatchesMarketplaceItem,
  parsePackageDraft,
  simpleInstallSuccessSummary,
} from "./labels";
import { ToolRegistryOverview, ToolRegistryTable } from "./sections";
import type { MarketplaceFilter, ToolConfigDialog } from "./types";

export function ToolRegistryPage() {
  const { text } = useI18n();
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
  const [schemaAdapterSlug, setSchemaAdapterSlug] = useState<string | null>(null);
  const [lastDirectAttachedMarketplaceItemId, setLastDirectAttachedMarketplaceItemId] = useState<string | null>(null);
  const [lastAttachedMarketplacePackageId, setLastAttachedMarketplacePackageId] = useState<string | null>(null);
  const registryQuery = useQuery({
    queryKey: ["tool-registry", simpleAgentId],
    queryFn: () => getToolRegistry(simpleAgentId),
  });
  const agentsQuery = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const adaptersQuery = useQuery({ queryKey: ["tool-adapters"], queryFn: listAdapters });
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
  const adapterBySlug = useMemo(
    () => new Map((adaptersQuery.data?.items ?? []).map((adapter) => [adapter.slug, adapter])),
    [adaptersQuery.data?.items],
  );
  const selectedSchemaAdapter = schemaAdapterSlug ? adapterBySlug.get(schemaAdapterSlug) ?? null : null;
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
        <ToolRegistryOverview
          toolsCount={tools.length}
          mcpCount={mcpCount}
          sandboxCount={sandboxCount}
          categoryCount={registryQuery.data?.categories.length ?? 0}
          highRiskCount={highRiskCount}
          sandboxReleasePath={
            (dependencyPreflightQuery.data?.local_release_path as string | undefined) ??
            `${sandboxCount} ${text("需要隔离", "isolated")}`
          }
          marketplaceItems={marketplaceItems}
          marketplaceReadySources={readyMarketplaceSources}
          marketplaceSourceCount={marketplaceQuery.data?.sources.length ?? 0}
          marketplaceIsError={marketplaceQuery.isError}
          marketplaceIsFetching={marketplaceQuery.isFetching}
          marketplaceHasErrors={Boolean(marketplaceQuery.data?.errors.length)}
          selectedAgentDisplayLabel={selectedAgentDisplayLabel}
          selectedMarketplaceInstallState={selectedMarketplaceInstallState}
          latestPackage={latestPackage}
          marketplaceCardError={
            marketplaceQuery.error ??
            attachMarketplaceCapabilityMutation.error ??
            marketplacePublicPreflightMutation.error ??
            marketplaceTrustedInstallMutation.error ??
            marketplaceUploadInstallMutation.error
          }
          onOpenDialog={(dialog) => setActiveConfigDialog(dialog)}
        />

        <ToolRegistryTable
          filteredTools={filteredTools}
          registrySources={registryQuery.data?.sources ?? []}
          registryLoading={registryQuery.isLoading}
          sourceFilter={sourceFilter}
          onSourceFilterChange={setSourceFilter}
          selectedAgentDisplayLabel={selectedAgentDisplayLabel}
          adminOnlyCount={adminOnlyCount}
          adapterBySlug={adapterBySlug}
          simpleAgentId={simpleAgentId}
          onOpenAdapter={setSchemaAdapterSlug}
        />

        <AdapterSchemaDrawer
          adapter={selectedSchemaAdapter}
          agentId={simpleAgentId}
          open={selectedSchemaAdapter !== null}
          onClose={() => setSchemaAdapterSlug(null)}
        />

        <ToolRegistryDialogs
          activeConfigDialog={activeConfigDialog}
          onClose={() => setActiveConfigDialog(null)}
          agentOptions={agentOptions}
          simpleAgentId={simpleAgentId}
          onSimpleAgentIdChange={setSimpleAgentId}
          selectedAgentDisplayLabel={selectedAgentDisplayLabel}
          marketplaceSearch={marketplaceSearch}
          onMarketplaceSearchChange={setMarketplaceSearch}
          marketplaceFilter={marketplaceFilter}
          onMarketplaceFilterChange={setMarketplaceFilter}
          marketplaceItems={marketplaceItems}
          marketplaceSources={marketplaceQuery.data?.sources ?? []}
          marketplaceHasErrors={Boolean(marketplaceQuery.data?.errors.length)}
          marketplaceLoading={marketplaceQuery.isLoading}
          marketplaceError={marketplaceQuery.error}
          selectedMarketplaceItem={selectedMarketplaceItem}
          selectedMarketplacePayload={selectedMarketplacePayload}
          selectedMarketplacePackage={selectedMarketplacePackage}
          selectedMarketplaceInstallState={selectedMarketplaceInstallState}
          selectedAgentAttachments={selectedAgentAttachments}
          packages={packagesQuery.data?.items ?? []}
          packagesLoading={packagesQuery.isLoading}
          packagesError={packagesQuery.error}
          lastDirectAttachedMarketplaceItemId={lastDirectAttachedMarketplaceItemId}
          lastAttachedMarketplacePackageId={lastAttachedMarketplacePackageId}
          onSelectMarketplaceItem={setSelectedMarketplaceItemId}
          onAttachMarketplaceExisting={(item) => attachMarketplaceCapabilityMutation.mutate(item)}
          onMarketplacePreflight={(payload) => marketplaceRegistryPreflightMutation.mutate(payload)}
          onMarketplacePublicPreflight={(payload) => marketplacePublicPreflightMutation.mutate(payload)}
          onMarketplaceTrustedInstall={(payload) => marketplaceTrustedInstallMutation.mutate(payload)}
          onMarketplaceUploadInstall={(payload) => marketplaceUploadInstallMutation.mutate(payload)}
          onApproveMarketplacePackage={(pkg) => approveMarketplacePackageMutation.mutate(pkg)}
          onAttachMarketplacePackage={(pkg) => attachMarketplacePackageMutation.mutate(pkg)}
          onMarketplaceQuickTest={(toolName) => marketplaceQuickTestMutation.mutate(toolName)}
          marketplacePreflightResult={
            marketplaceRegistryPreflightMutation.data ?? marketplacePublicPreflightMutation.data
          }
          marketplaceQuickQuery={marketplaceQuickQuery}
          onMarketplaceQuickQueryChange={setMarketplaceQuickQuery}
          marketplaceQuickResult={marketplaceQuickTestMutation.data}
          marketplaceQuickTesting={marketplaceQuickTestMutation.isPending}
          attachMarketplaceExistingPending={attachMarketplaceCapabilityMutation.isPending}
          attachMarketplaceExistingVariables={attachMarketplaceCapabilityMutation.variables}
          marketplacePreflighting={
            marketplaceRegistryPreflightMutation.isPending || marketplacePublicPreflightMutation.isPending
          }
          marketplaceTrustedInstalling={marketplaceTrustedInstallMutation.isPending}
          marketplaceUploadInstalling={marketplaceUploadInstallMutation.isPending}
          marketplaceApproving={approveMarketplacePackageMutation.isPending}
          marketplaceAttaching={attachMarketplacePackageMutation.isPending}
          marketplaceDialogError={
            attachMarketplaceCapabilityMutation.error ??
            marketplaceRegistryPreflightMutation.error ??
            marketplacePublicPreflightMutation.error ??
            approveMarketplacePackageMutation.error ??
            attachMarketplacePackageMutation.error ??
            marketplaceQuickTestMutation.error ??
            marketplaceTrustedInstallMutation.error ??
            marketplaceUploadInstallMutation.error
          }
          trustedUrl={trustedUrl}
          onTrustedUrlChange={setTrustedUrl}
          trustedInstallPending={trustedInstallMutation.isPending}
          trustedInstallData={trustedInstallMutation.data}
          trustedInstallError={trustedInstallMutation.error}
          onTrustedInstallSubmit={() => trustedInstallMutation.mutate()}
          publicUrl={publicUrl}
          onPublicUrlChange={setPublicUrl}
          packagePinnedRef={packagePinnedRef}
          onPackagePinnedRefChange={setPackagePinnedRef}
          publicPreflightPending={publicPreflightMutation.isPending}
          publicPreflightData={publicPreflightMutation.data}
          publicPreflightError={publicPreflightMutation.error}
          publicEnablePending={publicEnableMutation.isPending}
          publicEnableData={publicEnableMutation.data}
          publicEnableError={publicEnableMutation.error}
          onPublicPreflightSubmit={() => publicPreflightMutation.mutate()}
          onPublicEnableSubmit={() => publicEnableMutation.mutate()}
          uploadName={uploadName}
          onUploadNameChange={setUploadName}
          uploadContent={uploadContent}
          onUploadContentChange={setUploadContent}
          uploadInstallPending={uploadInstallMutation.isPending}
          uploadInstallData={uploadInstallMutation.data}
          uploadInstallError={uploadInstallMutation.error}
          onUploadInstallSubmit={() => uploadInstallMutation.mutate()}
          latestPackage={latestPackage}
          packageSource={packageSource}
          onPackageSourceChange={setPackageSource}
          packageAgentId={packageAgentId}
          onPackageAgentIdChange={setPackageAgentId}
          packageManifest={packageManifest}
          onPackageManifestChange={setPackageManifest}
          validationData={validationMutation.data}
          validationPending={validationMutation.isPending}
          onValidatePackage={() => validationMutation.mutate()}
          stagePending={stageMutation.isPending}
          onStagePackage={() => stageMutation.mutate()}
          approvePending={approveMutation.isPending}
          onApproveLatestPackage={() => latestPackage && approveMutation.mutate(latestPackage)}
          attachPending={attachMutation.isPending}
          onAttachLatestPackage={() => latestPackage && attachMutation.mutate(latestPackage)}
          latestAttachmentId={latestAttachmentId}
          disableAttachmentPending={disableAttachmentMutation.isPending}
          onDisableAttachment={() => disableAttachmentMutation.mutate()}
          selectedRollbackVersion={selectedRollbackVersion}
          rollbackVersionId={rollbackVersionId}
          onRollbackVersionIdChange={setRollbackVersionId}
          rollbackPending={rollbackMutation.isPending}
          onRollbackLatestPackage={() => latestPackage && rollbackMutation.mutate(latestPackage)}
          uninstallPending={uninstallMutation.isPending}
          onUninstallLatestPackage={() => latestPackage && uninstallMutation.mutate(latestPackage)}
          lifecycleError={
            validationMutation.error ??
            stageMutation.error ??
            approveMutation.error ??
            attachMutation.error ??
            disableAttachmentMutation.error ??
            rollbackMutation.error ??
            uninstallMutation.error
          }
          testAgentId={testAgentId}
          onTestAgentIdChange={setTestAgentId}
          testToolName={testToolName}
          onTestToolNameChange={setTestToolName}
          invokeInput={invokeInput}
          onInvokeInputChange={setInvokeInput}
          testInvokePending={testInvokeMutation.isPending}
          testInvokeData={testInvokeMutation.data}
          testInvokeError={testInvokeMutation.error}
          onTestInvoke={() => testInvokeMutation.mutate()}
        />
      </div>
    </ConsoleShell>
  );
}
