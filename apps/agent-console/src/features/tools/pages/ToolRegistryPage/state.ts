import { useState } from "react";

import type { MarketplaceFilter, ToolConfigDialog } from "./types";

const DEFAULT_PACKAGE_MANIFEST = `{
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
}`;

export function useToolRegistryShellState() {
  const [sourceFilter, setSourceFilter] = useState("all");
  const [activeConfigDialog, setActiveConfigDialog] = useState<ToolConfigDialog>(null);
  const [simpleAgentId, setSimpleAgentId] = useState("default");
  const [schemaAdapterSlug, setSchemaAdapterSlug] = useState<string | null>(null);
  const [codeInput, setCodeInput] = useState('print("hello from sandbox")');

  return {
    sourceFilter,
    setSourceFilter,
    activeConfigDialog,
    setActiveConfigDialog,
    simpleAgentId,
    setSimpleAgentId,
    schemaAdapterSlug,
    setSchemaAdapterSlug,
    codeInput,
    setCodeInput,
  };
}

export function useToolRegistryMarketplaceState() {
  const [marketplaceFilter, setMarketplaceFilter] = useState<MarketplaceFilter>("all");
  const [marketplaceSearch, setMarketplaceSearch] = useState("");
  const [selectedMarketplaceItemId, setSelectedMarketplaceItemId] = useState<string | null>(null);
  const [marketplaceQuickQuery, setMarketplaceQuickQuery] = useState("发布准备情况");
  const [lastDirectAttachedMarketplaceItemId, setLastDirectAttachedMarketplaceItemId] = useState<string | null>(null);
  const [lastAttachedMarketplacePackageId, setLastAttachedMarketplacePackageId] = useState<string | null>(null);

  return {
    marketplaceFilter,
    setMarketplaceFilter,
    marketplaceSearch,
    setMarketplaceSearch,
    selectedMarketplaceItemId,
    setSelectedMarketplaceItemId,
    marketplaceQuickQuery,
    setMarketplaceQuickQuery,
    lastDirectAttachedMarketplaceItemId,
    setLastDirectAttachedMarketplaceItemId,
    lastAttachedMarketplacePackageId,
    setLastAttachedMarketplacePackageId,
  };
}

export function useToolRegistryInstallDraftState() {
  const [trustedUrl, setTrustedUrl] = useState("https://example.com/customer-research.skill");
  const [publicUrl, setPublicUrl] = useState("https://example.com/community-skill.skill");
  const [uploadName, setUploadName] = useState("uploaded-skill");
  const [uploadContent, setUploadContent] = useState("# Uploaded Skill\n\nRun the operator test.");
  const [packageSource, setPackageSource] = useState("git+https://github.com/acme/skill-pack.git");
  const [packagePinnedRef, setPackagePinnedRef] = useState("commit:demo-pinned-commit");
  const [packageAgentId, setPackageAgentId] = useState("default");
  const [rollbackVersionId, setRollbackVersionId] = useState("");
  const [latestAttachmentId, setLatestAttachmentId] = useState<string | null>(null);
  const [packageManifest, setPackageManifest] = useState(DEFAULT_PACKAGE_MANIFEST);

  return {
    trustedUrl,
    setTrustedUrl,
    publicUrl,
    setPublicUrl,
    uploadName,
    setUploadName,
    uploadContent,
    setUploadContent,
    packageSource,
    setPackageSource,
    packagePinnedRef,
    setPackagePinnedRef,
    packageAgentId,
    setPackageAgentId,
    rollbackVersionId,
    setRollbackVersionId,
    latestAttachmentId,
    setLatestAttachmentId,
    packageManifest,
    setPackageManifest,
  };
}

export function useToolRegistryTestDraftState({
  defaultLangGraphManifest,
  defaultLangGraphJson,
  defaultLangChainInvokeInput,
}: {
  defaultLangGraphManifest: string;
  defaultLangGraphJson: string;
  defaultLangChainInvokeInput: string;
}) {
  const [testAgentId, setTestAgentId] = useState("default");
  const [testToolName, setTestToolName] = useState("mcp_context_search");
  const [invokeInput, setInvokeInput] = useState(`{ "query": "release readiness", "limit": 2 }`);
  const [langGraphManifest, setLangGraphManifest] = useState(defaultLangGraphManifest);
  const [langGraphJson, setLangGraphJson] = useState(defaultLangGraphJson);
  const [langGraphAgentId, setLangGraphAgentId] = useState("default");
  const [langChainAgentId, setLangChainAgentId] = useState("default");
  const [langChainToolName, setLangChainToolName] = useState("langchain.invoke_tool");
  const [langChainInvokeInput, setLangChainInvokeInput] = useState(defaultLangChainInvokeInput);

  return {
    testAgentId,
    setTestAgentId,
    testToolName,
    setTestToolName,
    invokeInput,
    setInvokeInput,
    langGraphManifest,
    setLangGraphManifest,
    langGraphJson,
    setLangGraphJson,
    langGraphAgentId,
    setLangGraphAgentId,
    langChainAgentId,
    setLangChainAgentId,
    langChainToolName,
    setLangChainToolName,
    langChainInvokeInput,
    setLangChainInvokeInput,
  };
}
