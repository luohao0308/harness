import {
  CheckCircle2,
  PackagePlus,
  RotateCcw,
  Search,
  ShieldCheck,
  Timer,
} from "lucide-react";

import { Badge } from "../../../../components/ui/badge";
import { Button } from "../../../../components/ui/button";
import { ConfigDialog } from "../../../../components/ui/config-dialog";
import { Input, Textarea } from "../../../../components/ui/input";
import { MenuSelect, type MenuSelectOption } from "../../../../components/ui/menu-select";
import { useI18n } from "../../../../lib/i18n";
import type {
  AgentCapabilityAttachmentSummary,
  CapabilityMarketplaceItem,
  CapabilityMarketplacePreflightPayload,
  CapabilityPackage,
  CapabilitySimpleInstallPayload,
  CapabilitySimpleInstallResponse,
  CapabilityValidationResponse,
  ToolExecuteResult,
} from "../../../tasks/api";

import {
  MarketplaceInstallPanel,
  MarketplaceItemCard,
  MutationError,
  PackageLifecycleSummary,
  SimpleInstallResult,
} from "./components";
import {
  capabilityPackageStatusLabel,
  capabilityReadyStateLabel,
  capabilityValidationModeLabel,
  capabilityValidationStatusLabel,
  detectMarketplaceInstallState,
  findMarketplacePackageForItem,
  isPublicPackageSource,
  marketplaceSourceLabel,
  normalizeMarketplaceInstallPayload,
  toolCallStatusLabel,
} from "./labels";
import type { MarketplaceFilter, MarketplaceInstallState, ToolConfigDialog } from "./types";

type MarketplaceSource = {
  id: string;
  label: string;
  status: string;
  item_count: number;
};

type ToolRegistryDialogsProps = {
  activeConfigDialog: ToolConfigDialog;
  onClose: () => void;
  agentOptions: MenuSelectOption[];
  simpleAgentId: string;
  onSimpleAgentIdChange: (value: string) => void;
  selectedAgentDisplayLabel: string;

  marketplaceSearch: string;
  onMarketplaceSearchChange: (value: string) => void;
  marketplaceFilter: MarketplaceFilter;
  onMarketplaceFilterChange: (value: MarketplaceFilter) => void;
  marketplaceItems: CapabilityMarketplaceItem[];
  marketplaceSources: MarketplaceSource[];
  marketplaceHasErrors: boolean;
  marketplaceLoading: boolean;
  marketplaceError: unknown;
  selectedMarketplaceItem: CapabilityMarketplaceItem | null;
  selectedMarketplacePayload: CapabilityMarketplacePreflightPayload | null;
  selectedMarketplacePackage: CapabilityPackage | null;
  selectedMarketplaceInstallState: MarketplaceInstallState;
  selectedAgentAttachments: AgentCapabilityAttachmentSummary[];
  packages: CapabilityPackage[];
  packagesLoading: boolean;
  packagesError: unknown;
  lastDirectAttachedMarketplaceItemId: string | null;
  lastAttachedMarketplacePackageId: string | null;
  onSelectMarketplaceItem: (id: string) => void;
  onAttachMarketplaceExisting: (item: CapabilityMarketplaceItem) => void;
  onMarketplacePreflight: (payload: CapabilityMarketplacePreflightPayload) => void;
  onMarketplacePublicPreflight: (payload: CapabilitySimpleInstallPayload) => void;
  onMarketplaceTrustedInstall: (payload: CapabilitySimpleInstallPayload) => void;
  onMarketplaceUploadInstall: (payload: CapabilitySimpleInstallPayload) => void;
  onApproveMarketplacePackage: (pkg: CapabilityPackage) => void;
  onAttachMarketplacePackage: (pkg: CapabilityPackage) => void;
  onMarketplaceQuickTest: (toolName: string) => void;
  marketplacePreflightResult?: CapabilitySimpleInstallResponse;
  marketplaceQuickQuery: string;
  onMarketplaceQuickQueryChange: (value: string) => void;
  marketplaceQuickResult?: ToolExecuteResult;
  marketplaceQuickTesting: boolean;
  attachMarketplaceExistingPending: boolean;
  attachMarketplaceExistingVariables?: CapabilityMarketplaceItem;
  marketplacePreflighting: boolean;
  marketplaceTrustedInstalling: boolean;
  marketplaceUploadInstalling: boolean;
  marketplaceApproving: boolean;
  marketplaceAttaching: boolean;
  marketplaceDialogError: unknown;

  trustedUrl: string;
  onTrustedUrlChange: (value: string) => void;
  trustedInstallPending: boolean;
  trustedInstallData?: CapabilitySimpleInstallResponse;
  trustedInstallError: unknown;
  onTrustedInstallSubmit: () => void;

  publicUrl: string;
  onPublicUrlChange: (value: string) => void;
  packagePinnedRef: string;
  onPackagePinnedRefChange: (value: string) => void;
  publicPreflightPending: boolean;
  publicPreflightData?: CapabilitySimpleInstallResponse;
  publicPreflightError: unknown;
  publicEnablePending: boolean;
  publicEnableData?: CapabilitySimpleInstallResponse;
  publicEnableError: unknown;
  onPublicPreflightSubmit: () => void;
  onPublicEnableSubmit: () => void;

  uploadName: string;
  onUploadNameChange: (value: string) => void;
  uploadContent: string;
  onUploadContentChange: (value: string) => void;
  uploadInstallPending: boolean;
  uploadInstallData?: CapabilitySimpleInstallResponse;
  uploadInstallError: unknown;
  onUploadInstallSubmit: () => void;

  latestPackage: CapabilityPackage | null;
  packageSource: string;
  onPackageSourceChange: (value: string) => void;
  packageAgentId: string;
  onPackageAgentIdChange: (value: string) => void;
  packageManifest: string;
  onPackageManifestChange: (value: string) => void;
  validationData?: CapabilityValidationResponse;
  validationPending: boolean;
  onValidatePackage: () => void;
  stagePending: boolean;
  onStagePackage: () => void;
  approvePending: boolean;
  onApproveLatestPackage: () => void;
  attachPending: boolean;
  onAttachLatestPackage: () => void;
  latestAttachmentId: string | null;
  disableAttachmentPending: boolean;
  onDisableAttachment: () => void;
  selectedRollbackVersion: string;
  rollbackVersionId: string;
  onRollbackVersionIdChange: (value: string) => void;
  rollbackPending: boolean;
  onRollbackLatestPackage: () => void;
  uninstallPending: boolean;
  onUninstallLatestPackage: () => void;
  lifecycleError: unknown;

  testAgentId: string;
  onTestAgentIdChange: (value: string) => void;
  testToolName: string;
  onTestToolNameChange: (value: string) => void;
  invokeInput: string;
  onInvokeInputChange: (value: string) => void;
  testInvokePending: boolean;
  testInvokeData?: ToolExecuteResult;
  testInvokeError: unknown;
  onTestInvoke: () => void;
};

export function ToolRegistryDialogs(props: ToolRegistryDialogsProps) {
  const { text } = useI18n();
  const {
    activeConfigDialog,
    onClose,
    agentOptions,
    simpleAgentId,
    onSimpleAgentIdChange,
    selectedAgentDisplayLabel,
    marketplaceItems,
    selectedMarketplaceItem,
    selectedMarketplacePayload,
    selectedMarketplacePackage,
    selectedMarketplaceInstallState,
    selectedAgentAttachments,
    packages,
    packagesLoading,
    lastDirectAttachedMarketplaceItemId,
    lastAttachedMarketplacePackageId,
  } = props;

  return (
    <>
      <ConfigDialog
        open={activeConfigDialog === "marketplace"}
        title={text("MCP / 技能商店", "MCP / Skill Marketplace")}
        description={text("左侧挑选条目，右侧按步骤完成登记预检、审批版本、安装到智能体，并用案例测试。", "Pick an entry on the left, then register, approve, attach, and test it on the right.")}
        onClose={onClose}
        className="max-w-6xl"
      >
        <div className="grid gap-4 text-xs">
          <div className="grid gap-3 border-b border-slate-100 pb-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
            <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
              <label className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
                <Input
                  aria-label={text("搜索 MCP 和技能商店", "Search MCP and Skill marketplace")}
                  value={props.marketplaceSearch}
                  onChange={(event) => props.onMarketplaceSearchChange(event.target.value)}
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
                      props.marketplaceFilter === filter
                        ? "bg-white text-slate-950 shadow-sm"
                        : "text-slate-500 hover:text-slate-800",
                    ].join(" ")}
                    onClick={() => props.onMarketplaceFilterChange(filter)}
                  >
                    {filter === "all" ? text("全部", "All") : filter === "mcp" ? "MCP" : "技能"}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-slate-500">
              <Badge tone="neutral">目标智能体 · {selectedAgentDisplayLabel}</Badge>
              {props.marketplaceSources.map((source) => (
                <Badge key={source.id} tone={source.status === "ready" ? "success" : "warning"}>
                  {marketplaceSourceLabel(source.label)} · {source.item_count}
                </Badge>
              ))}
            </div>
          </div>
          {props.marketplaceHasErrors ? (
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
                      props.attachMarketplaceExistingPending &&
                      props.attachMarketplaceExistingVariables?.id === item.id
                    }
                    installState={detectMarketplaceInstallState({
                      item,
                      payload: normalizeMarketplaceInstallPayload(item),
                      agentAttachments: selectedAgentAttachments,
                      matchedPackage: findMarketplacePackageForItem(item, packages),
                      attachedExisting: lastDirectAttachedMarketplaceItemId === item.id,
                      attachedPackage: false,
                    })}
                    onSelect={() => props.onSelectMarketplaceItem(item.id)}
                  />
                ))}
                {props.marketplaceLoading ? (
                  <div className="rounded-md border border-slate-100 bg-white p-4 text-slate-500">
                    {text("正在同步市场...", "Syncing marketplace...")}
                  </div>
                ) : null}
                {!props.marketplaceLoading && marketplaceItems.length === 0 ? (
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
              loading={packagesLoading}
              installPayload={selectedMarketplacePayload}
              installState={selectedMarketplaceInstallState}
              preflightResult={props.marketplacePreflightResult}
              onAgentIdChange={onSimpleAgentIdChange}
              onAttachExisting={props.onAttachMarketplaceExisting}
              onMarketplacePreflight={(payload) =>
                props.onMarketplacePreflight({ ...payload, agent_id: simpleAgentId })
              }
              onPublicPreflight={(payload) =>
                props.onMarketplacePublicPreflight({ ...payload, agent_id: simpleAgentId })
              }
              onTrustedInstall={(payload) =>
                props.onMarketplaceTrustedInstall({ ...payload, agent_id: simpleAgentId })
              }
              onUploadInstall={(payload) =>
                props.onMarketplaceUploadInstall({ ...payload, agent_id: simpleAgentId })
              }
              onApprove={props.onApproveMarketplacePackage}
              onAttach={props.onAttachMarketplacePackage}
              onQuickTest={props.onMarketplaceQuickTest}
              quickTestQuery={props.marketplaceQuickQuery}
              onQuickTestQueryChange={props.onMarketplaceQuickQueryChange}
              quickTestResult={props.marketplaceQuickResult}
              quickTesting={props.marketplaceQuickTesting}
              attachingExisting={props.attachMarketplaceExistingPending}
              preflighting={props.marketplacePreflighting}
              trustedInstalling={props.marketplaceTrustedInstalling}
              uploadInstalling={props.marketplaceUploadInstalling}
              approving={props.marketplaceApproving}
              attaching={props.marketplaceAttaching}
              attachedExisting={lastDirectAttachedMarketplaceItemId === selectedMarketplaceItem?.id}
              attachedPackage={lastAttachedMarketplacePackageId === selectedMarketplacePackage?.id}
            />
          </div>
          <MutationError error={props.marketplaceDialogError ?? props.marketplaceError} />
        </div>
      </ConfigDialog>

      <ConfigDialog
        open={activeConfigDialog === "trusted-url"}
        title={text("可信 URL 一键安装", "Trusted URL one-click install")}
        description={text("从可信来源下载技能或能力包，并安装到目标智能体。", "Download a Skill or capability package from a trusted source and attach it to the target Agent.")}
        onClose={onClose}
      >
        <div className="grid gap-3 text-xs">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium text-slate-600">{text("当前状态", "Current status")}</span>
            <Badge tone={props.trustedInstallData?.ready_state === "attached" ? "success" : "info"}>
              {props.trustedInstallData ? capabilityReadyStateLabel(props.trustedInstallData.ready_state) : text("等待安装", "v1 gate")}
            </Badge>
          </div>
          <label className="grid gap-1">
            <span className="font-medium text-slate-600">{text("可信来源 URL", "Trusted source URL")}</span>
            <Input aria-label="可信 URL 安装" value={props.trustedUrl} onChange={(event) => props.onTrustedUrlChange(event.target.value)} />
          </label>
          <label className="grid gap-1">
            <span className="font-medium text-slate-600">目标智能体</span>
            <MenuSelect
              ariaLabel="可信 URL 目标智能体"
              value={simpleAgentId}
              onChange={onSimpleAgentIdChange}
              options={agentOptions}
              placeholder={text("选择目标智能体", "Select target agent")}
              size="compact"
            />
          </label>
          <Button onClick={props.onTrustedInstallSubmit} disabled={props.trustedInstallPending || !props.trustedUrl.trim()}>
            <CheckCircle2 className="h-3.5 w-3.5" /> {text("下载、安装并启用", "Download, install, and enable")}
          </Button>
          <SimpleInstallResult result={props.trustedInstallData} />
          <MutationError error={props.trustedInstallError} />
        </div>
      </ConfigDialog>

      <ConfigDialog
        open={activeConfigDialog === "public-url"}
        title={text("公网 URL 预检", "Public URL preflight")}
        description={text("公网来源只做下载预检和暂存，验证后再手动启用。", "Public sources are downloaded, preflighted, and staged; enable them manually after validation.")}
        onClose={onClose}
      >
        <div className="grid gap-3 text-xs">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium text-slate-600">{text("当前状态", "Current status")}</span>
            <Badge tone={props.publicPreflightData?.staged_capability_id ? "warning" : "neutral"}>
              {props.publicPreflightData?.staged_capability_id ? text("等待启用", "Enable required") : text("不自动启用", "No auto-enable")}
            </Badge>
          </div>
          <label className="grid gap-1">
            <span className="font-medium text-slate-600">{text("公网 HTTPS URL", "Public HTTPS URL")}</span>
            <Input aria-label="公网 URL 预检" value={props.publicUrl} onChange={(event) => props.onPublicUrlChange(event.target.value)} />
          </label>
          <label className="grid gap-1">
            <span className="font-medium text-slate-600">{text("可选固定引用", "Optional pinned ref")}</span>
            <Input aria-label="公网 URL 固定引用" value={props.packagePinnedRef} onChange={(event) => props.onPackagePinnedRefChange(event.target.value)} />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button onClick={props.onPublicPreflightSubmit} disabled={props.publicPreflightPending || !props.publicUrl.trim()}>
              <ShieldCheck className="h-3.5 w-3.5" /> {text("下载并预检", "Download and preflight")}
            </Button>
            <Button onClick={props.onPublicEnableSubmit} disabled={!props.publicPreflightData?.staged_capability_id || props.publicEnablePending}>
              <CheckCircle2 className="h-3.5 w-3.5" /> {text("启用", "Enable")}
            </Button>
          </div>
          {props.publicPreflightData?.staged_capability_id ? (
            <div className="rounded-md border border-amber-100 bg-amber-50 p-2 text-amber-800">
              {text("已生成暂存包标识，完成验证后再点击“启用”才能进入运行链路。", "staged_capability_id created; Enable is required before runtime attachment.")}{" "}
              <span className="font-mono">{props.publicPreflightData.staged_capability_id}</span>
            </div>
          ) : null}
          <SimpleInstallResult result={props.publicPreflightData} />
          <SimpleInstallResult result={props.publicEnableData} />
          <MutationError error={props.publicPreflightError ?? props.publicEnableError} />
        </div>
      </ConfigDialog>

      <ConfigDialog
        open={activeConfigDialog === "upload"}
        title={text("上传文件安装", "Upload file install")}
        description={text("上传技能说明文件（SKILL.md）并安装到目标智能体。", "Upload SKILL.md content and attach it to the target Agent.")}
        onClose={onClose}
      >
        <div className="grid gap-3 text-xs">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium text-slate-600">{text("当前状态", "Current status")}</span>
            <Badge tone={props.uploadInstallData?.ready_state === "attached" ? "success" : "info"}>
              {props.uploadInstallData ? capabilityReadyStateLabel(props.uploadInstallData.ready_state) : text("无需编辑清单", "No manifest editing")}
            </Badge>
          </div>
          <label className="grid gap-1">
            <span className="font-medium text-slate-600">{text("包名称", "Package name")}</span>
            <Input aria-label="上传包名称" value={props.uploadName} onChange={(event) => props.onUploadNameChange(event.target.value)} />
          </label>
          <label className="grid gap-1">
            <span className="font-medium text-slate-600">技能说明文件内容（SKILL.md）</span>
            <Textarea aria-label="上传 SKILL.md 内容" value={props.uploadContent} onChange={(event) => props.onUploadContentChange(event.target.value)} className="font-mono text-xs" />
          </label>
          <Button onClick={props.onUploadInstallSubmit} disabled={props.uploadInstallPending || !props.uploadName.trim()}>
            <PackagePlus className="h-3.5 w-3.5" /> {text("上传并安装", "Upload and install")}
          </Button>
          <SimpleInstallResult result={props.uploadInstallData} />
          <MutationError error={props.uploadInstallError} />
        </div>
      </ConfigDialog>

      <ConfigDialog
        open={activeConfigDialog === "lifecycle"}
        title={text("高级生命周期", "Advanced lifecycle")}
        description={text("自定义能力包的校验、暂存、审批、安装、停用、回滚和卸载。", "Validate, stage, approve, install, disable, roll back, and uninstall custom capability packages.")}
        onClose={onClose}
        className="max-w-4xl"
      >
        <div className="grid gap-3 text-xs">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium text-slate-600">{text("当前包状态", "Current package status")}</span>
            <Badge tone={props.latestPackage?.status === "approved" ? "success" : "warning"}>
              {props.latestPackage ? capabilityPackageStatusLabel(props.latestPackage.status) : text("未暂存", "Not staged")}
            </Badge>
          </div>
          <label className="grid gap-1">
            <span className="font-medium text-slate-600">{text("来源：留空或 private 表示私有包", "Source: blank or private for private packages")}</span>
            <Input aria-label="能力包来源" value={props.packageSource} onChange={(event) => props.onPackageSourceChange(event.target.value)} />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="grid gap-1">
              <span className="font-medium text-slate-600">{text("公共来源固定引用", "Pinned public ref")}</span>
              <Input aria-label="能力包固定引用" value={props.packagePinnedRef} onChange={(event) => props.onPackagePinnedRefChange(event.target.value)} disabled={!isPublicPackageSource(props.packageSource)} />
            </label>
            <label className="grid gap-1">
              <span className="font-medium text-slate-600">目标智能体</span>
              <MenuSelect
                ariaLabel="能力包安装目标智能体"
                value={props.packageAgentId}
                onChange={props.onPackageAgentIdChange}
                options={agentOptions}
                placeholder={text("选择目标智能体", "Select target agent")}
                size="compact"
              />
            </label>
          </div>
          <label className="grid gap-1">
            <span className="font-medium text-slate-600">{text("包清单", "Package manifest")}</span>
            <Textarea aria-label="能力包清单" value={props.packageManifest} onChange={(event) => props.onPackageManifestChange(event.target.value)} className="min-h-56 font-mono text-xs" />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button onClick={props.onValidatePackage} disabled={props.validationPending}>
              <ShieldCheck className="h-3.5 w-3.5" /> {text("仅校验", "Validate only")}
            </Button>
            <Button onClick={props.onStagePackage} disabled={props.stagePending || (isPublicPackageSource(props.packageSource) && !props.packagePinnedRef.trim())}>
              <PackagePlus className="h-3.5 w-3.5" /> {text("暂存包", "Stage package")}
            </Button>
            <Button onClick={props.onApproveLatestPackage} disabled={!props.latestPackage || props.latestPackage.status !== "staged" || props.approvePending}>
              <CheckCircle2 className="h-3.5 w-3.5" /> {text("审批版本", "Approve version")}
            </Button>
            <Button onClick={props.onAttachLatestPackage} disabled={!props.latestPackage || props.latestPackage.status !== "approved" || !props.packageAgentId.trim() || props.attachPending}>
              {text("安装到智能体", "Install to Agent")}
            </Button>
            <Button onClick={props.onDisableAttachment} disabled={!props.latestAttachmentId || props.disableAttachmentPending}>
              {text("停用附件", "Disable attachment")}
            </Button>
            <Button onClick={props.onRollbackLatestPackage} disabled={!props.latestPackage?.capability_id || !props.selectedRollbackVersion || props.rollbackPending}>
              <RotateCcw className="h-3.5 w-3.5" /> {text("回滚", "Rollback")}
            </Button>
            <Button onClick={props.onUninstallLatestPackage} disabled={!props.latestPackage || props.latestPackage.status === "uninstalled" || props.uninstallPending}>
              {text("卸载", "Uninstall")}
            </Button>
          </div>
          <label className="grid gap-1">
            <span className="font-medium text-slate-600">{text("回滚目标版本", "Rollback target version")}</span>
            <Input aria-label="回滚目标版本" value={props.rollbackVersionId} onChange={(event) => props.onRollbackVersionIdChange(event.target.value)} placeholder={props.latestPackage?.capability_version_id ?? ""} />
          </label>
          {props.latestPackage ? (
            <PackageLifecycleSummary pkg={props.latestPackage} />
          ) : props.packagesLoading ? (
            <div className="rounded-md border border-slate-100 bg-slate-50 p-2 text-slate-500">
              {text("正在加载能力包...", "Loading capability packages...")}
            </div>
          ) : null}
          {props.validationData ? (
            <div className="rounded-md border border-slate-100 bg-slate-50 p-2 font-mono text-[11px] text-slate-600">
              {text("校验状态", "Validation")} {capabilityValidationStatusLabel(props.validationData.status)} · {capabilityValidationModeLabel(props.validationData.validation_mode ?? "manifest_only_no_execution")}
              <br />
              sha {props.validationData.content_sha256.slice(0, 12)} / {props.validationData.config_sha256.slice(0, 12)}
            </div>
          ) : null}
          {props.latestAttachmentId ? (
            <div className="rounded-md border border-emerald-100 bg-emerald-50 p-2 font-mono text-[11px] text-emerald-700">
              {text("最近附件", "Latest attachment")} {props.latestAttachmentId}
            </div>
          ) : null}
          <MutationError error={props.lifecycleError ?? props.packagesError} />
        </div>
      </ConfigDialog>

      <ConfigDialog
        open={activeConfigDialog === "test-invoke"}
        title={text("智能体范围测试调用", "Agent-scoped test invoke")}
        description={text("使用智能体范围执行一次工具测试，验证附件和策略链路。", "Run one Agent-scoped tool test to validate attachment and policy routing.")}
        onClose={onClose}
      >
        <div className="grid gap-3 text-xs">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium text-slate-600">{text("当前状态", "Current status")}</span>
            <Badge tone={props.testInvokeData?.allowed ? "success" : "neutral"}>
              {props.testInvokeData ? toolCallStatusLabel(props.testInvokeData.tool_call.status) : text("待测试", "Ready")}
            </Badge>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <label className="grid gap-1">
              <span className="font-medium text-slate-600">目标智能体</span>
              <MenuSelect
                ariaLabel="测试目标智能体"
                value={props.testAgentId}
                onChange={props.onTestAgentIdChange}
                options={agentOptions}
                placeholder={text("选择目标智能体", "Select target agent")}
                size="compact"
              />
            </label>
            <label className="grid gap-1">
              <span className="font-medium text-slate-600">{text("工具名", "Tool name")}</span>
              <Input aria-label="测试工具名" value={props.testToolName} onChange={(event) => props.onTestToolNameChange(event.target.value)} />
            </label>
          </div>
          <Textarea aria-label="测试输入 JSON" value={props.invokeInput} onChange={(event) => props.onInvokeInputChange(event.target.value)} className="font-mono text-xs" />
          <div className="rounded-md border border-cyan-100 bg-cyan-50 p-2 text-cyan-900">
            建议案例：将工具名设置为 <code className="font-mono">mcp_context_search</code>，输入{" "}
            <code className="font-mono">{'{"query":"发布准备情况","limit":2}'}</code>
            ，确认工具调用返回命中结果。
          </div>
          <Button onClick={props.onTestInvoke} disabled={props.testInvokePending}>
            <Timer className="h-3.5 w-3.5" /> {text("测试调用", "Test invoke")}
          </Button>
          {props.testInvokeData ? (
            <pre className="max-h-32 overflow-auto rounded border border-slate-100 bg-slate-50 p-2 font-mono text-[10px] text-slate-600">
              {JSON.stringify(props.testInvokeData.output, null, 2)}
            </pre>
          ) : null}
          {props.testInvokeError instanceof Error ? <div className="text-red-700">{props.testInvokeError.message}</div> : null}
        </div>
      </ConfigDialog>
    </>
  );
}
