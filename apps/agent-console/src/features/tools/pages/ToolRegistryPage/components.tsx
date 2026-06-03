import type { ReactNode } from "react";
import {
  CheckCircle2,
  Download,
  ExternalLink,
  FileCheck2,
  GitBranch,
  PackagePlus,
  ShieldCheck,
  SlidersHorizontal,
  Timer,
} from "lucide-react";

import { Badge } from "../../../../components/ui/badge";
import { Button } from "../../../../components/ui/button";
import { Card } from "../../../../components/ui/card";
import { Input } from "../../../../components/ui/input";
import { MenuSelect, type MenuSelectOption } from "../../../../components/ui/menu-select";
import { useI18n } from "../../../../lib/i18n";
import { AdapterHealthBadge } from "../../components/AdapterHealthBadge";
import { mcpGuideFor } from "../../lib/mcpDescriptions";
import type {
  AdapterMetadata,
  CapabilityMarketplaceItem,
  CapabilityMarketplacePreflightPayload,
  CapabilityPackage,
  CapabilitySimpleInstallPayload,
  CapabilitySimpleInstallResponse,
  ToolExecuteResult,
} from "../../../tasks/api";

import {
  capabilityNextStepLabel,
  capabilityPackageStatusLabel,
  capabilityReadyStateLabel,
  capabilitySourceKindLabel,
  installModeLabel,
  isRecord,
  marketplaceBadgeLabel,
  marketplaceInstallStateMeta,
  marketplaceNextStepCopy,
  marketplaceSourceLabel,
  marketplaceSuggestedTestCases,
  marketplaceToolName,
  toolCallStatusLabel,
} from "./labels";
import type { MarketplaceInstallState } from "./types";

export function HarnessTile({
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

export function Metric({ label, value }: { label: ReactNode; value: number }) {
  return (
    <Card className="p-4">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="mt-1 font-mono text-2xl text-slate-900">{value}</div>
    </Card>
  );
}

export function AdapterCell({
  adapter,
  agentId,
  onOpen,
}: {
  adapter: AdapterMetadata;
  agentId: string;
  onOpen: () => void;
}) {
  return (
    <div className="grid gap-1.5">
      <AdapterHealthBadge slug={adapter.slug} agentId={agentId} compact />
      <Button type="button" variant="ghost" className="h-7 px-2" onClick={onOpen}>
        <FileCheck2 className="h-3.5 w-3.5" />
        Schema
      </Button>
    </div>
  );
}

export function MarketStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50 px-3 py-2">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="mt-0.5 font-mono text-base text-slate-900">{value}</div>
    </div>
  );
}

export function MarketplaceItemCard({
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

export function MarketplaceInstallPanel({
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
          <Badge tone={installStateMeta.tone}>{installStateMeta.label}</Badge>
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

export function PackageLifecycleSummary({ pkg }: { pkg: CapabilityPackage }) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50 p-2 font-mono text-[11px] text-slate-600">
      <div>{pkg.package_key} · {capabilityPackageStatusLabel(pkg.status)} · {capabilitySourceKindLabel(pkg.source_kind)}</div>
      <div>能力包 {pkg.id}</div>
      <div>来源哈希 {pkg.source_sha256.slice(0, 12)}{pkg.pinned_ref ? ` · ${pkg.pinned_ref}` : ""}</div>
      <div>能力 {pkg.capability_id ?? "--"} / {pkg.capability_version_id ?? "--"}</div>
    </div>
  );
}

export function SimpleInstallResult({ result }: { result?: CapabilitySimpleInstallResponse }) {
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

export function QuickTestResult({ result }: { result: ToolExecuteResult }) {
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

export function MutationError({ error }: { error: unknown }) {
  if (!(error instanceof Error)) return null;
  return (
    <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs leading-5 text-red-800">
      {error.message}
    </div>
  );
}
