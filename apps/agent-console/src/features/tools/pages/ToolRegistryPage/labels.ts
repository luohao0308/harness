import type {
  AgentCapabilityAttachmentSummary,
  AgentDefinition,
  CapabilityMarketplaceItem,
  CapabilityMarketplacePreflightPayload,
  CapabilityPackage,
  CapabilitySimpleInstallResponse,
} from "../../../tasks/api";

import type { MarketplaceInstallState } from "./types";
import { mcpGuideFor } from "../../lib/mcpDescriptions";

export function marketplaceInstallStateMeta(state: MarketplaceInstallState) {
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

export function capabilityReadyStateLabel(state: string) {
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

export function capabilityNextStepLabel(label: string) {
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

export function capabilityPackageStatusLabel(status: string) {
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

export function capabilitySourceKindLabel(sourceKind: string) {
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

export function capabilityValidationStatusLabel(status: string) {
  switch (status) {
    case "valid":
      return "通过";
    case "invalid":
      return "失败";
    default:
      return status;
  }
}

export function capabilityValidationModeLabel(mode: string) {
  switch (mode) {
    case "manifest_only_no_execution":
      return "仅校验清单，不执行";
    default:
      return mode;
  }
}

export function toolCallStatusLabel(status: string) {
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

export function toolNetworkPolicyLabel(policy: string) {
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

export function toolAuditLevelLabel(level: string) {
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

export function sandboxReleasePathLabel(value: string) {
  if (value === "no-container") {
    return "本地无容器路径";
  }
  return value;
}

export function marketplaceSourceLabel(label: string) {
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

export function marketplaceBadgeLabel(badge: string) {
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

export function installModeLabel(mode: CapabilityMarketplaceItem["install_mode"], fallback: string) {
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

export function marketplaceNextStepCopy(state: MarketplaceInstallState, kind: CapabilityMarketplaceItem["kind"]) {
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

export function marketplaceSuggestedTestCases(item: CapabilityMarketplaceItem) {
  const primary = mcpGuideFor(item).testQuery;
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

export function detectMarketplaceInstallState({
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

export function packageMatchesMarketplaceItem(item: CapabilityMarketplaceItem, pkg: CapabilityPackage) {
  return findMarketplacePackageForItem(item, [pkg])?.id === pkg.id;
}

export function findMarketplacePackageForItem(
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

export function simpleInstallSuccessSummary(result: CapabilitySimpleInstallResponse, agentId: string) {
  const state = capabilityReadyStateLabel(result.ready_state);
  if (result.attachment) {
    return `${state}，已安装到智能体 ${agentId}，附件 ${result.attachment.attachment_id} 已创建。`;
  }
  return `${state}，下一步：${capabilityNextStepLabel(result.next_step_label)}。`;
}

export function isPublicPackageSource(value: string) {
  const source = value.trim();
  return source.startsWith("git+") || source.startsWith("https://") || source.startsWith("http://");
}

export function parsePackageDraft(value: string) {
  const parsed = JSON.parse(value) as Record<string, unknown>;
  const packageManifest = parsed.package_manifest;
  if (isRecord(packageManifest)) {
    const { package_manifest: _packageManifest, ...content } = parsed;
    return { manifest: packageManifest, content };
  }
  return { manifest: parsed, content: {} };
}

export function normalizeMarketplaceInstallPayload(
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

export function marketplaceToolName(
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

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function agentTargetLabel(agentId: string, agents: AgentDefinition[]) {
  const matched = agents.find((agent) => agent.id === agentId);
  if (matched?.name?.trim()) {
    return matched.name === agentId ? matched.name : `${matched.name}（${agentId}）`;
  }
  if (agentId === "default") {
    return "默认智能体（default）";
  }
  return agentId;
}

function stringInSet(values: Set<string>, value: unknown) {
  return typeof value === "string" && values.has(value);
}

function stringStartsWith(value: unknown, prefix: string) {
  return typeof value === "string" && value.startsWith(prefix);
}
