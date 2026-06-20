import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  Cable,
  Database,
  FilePlus2,
  History,
  Lock,
  PencilLine,
  Plus,
  Power,
  RefreshCw,
  RotateCcw,
  Save,
  Shield,
  Trash2,
  Upload,
} from "lucide-react";

import { Badge, type BadgeTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { ConfigDialog } from "../../../components/ui/config-dialog";
import { EmptyState } from "../../../components/ui/EmptyState";
import { useConfirmDialog } from "../../../components/ui/confirm-dialog";
import { feedbackErrorMessage, notifyFeedback } from "../../../components/ui/feedback-toast";
import { Input, Textarea } from "../../../components/ui/input";
import { MenuSelect } from "../../../components/ui/menu-select";
import { useI18n } from "../../../lib/i18n";
import { useOptionalAuth } from "../../auth/AuthProvider";
import {
  archiveAgentKnowledgeSource,
  changeAgentKnowledgeSourceScope,
  createAgentKnowledgeDocument,
  createAgentKnowledgeDocumentVersion,
  createAgentKnowledgeSource,
  deleteAgentKnowledgeSource,
  disableAgentKnowledgeSource,
  enableAgentKnowledgeSource,
  importAgentKnowledgeDocumentFile,
  importAgentKnowledgeDocumentVersionFile,
  importAgentKnowledgeSourceFile,
  KNOWLEDGE_ADMIN_CONTROLS_ENABLED,
  listAgentKnowledgeDocuments,
  listAgentKnowledgeSources,
  updateAgentKnowledgeSource,
  type KnowledgeDocument,
  type KnowledgeSource,
} from "../../tasks/api";

type KnowledgeManagementPanelProps = {
  agentId: string;
  variant?: "embedded" | "workbench";
  sourceFilter?: KnowledgeSourceFilter;
};

const queryKeyForSources = (agentId: string) => ["agent-knowledge", agentId] as const;
const queryKeyForDocuments = (agentId: string, sourceId: string | null) =>
  ["agent-knowledge-documents", agentId, sourceId] as const;
const knowledgeFileAccept = ".txt,.md,text/plain,text/markdown";
const knowledgeFileMaxBytes = 120_000;

type KnowledgeCreateMode = "document" | "connector";
type ConnectorPresetId = "dify" | "coze" | "langchain" | "ragflow" | "local_dify" | "local_ragflow";
export type KnowledgeSourceFilter = "all" | "local" | "api" | "preview";

function useCanManageOrgKnowledge() {
  const auth = useOptionalAuth();
  const role = auth?.user?.role;
  const permissions = auth?.user?.permissions ?? [];
  return (
    KNOWLEDGE_ADMIN_CONTROLS_ENABLED
    || role === "owner"
    || role === "admin"
    || permissions.includes("org:manage")
  );
}

const connectorPresets: Array<{
  id: ConnectorPresetId;
  label: string;
  placeholder: string;
  secretPlaceholder: string;
  helper: string;
  releaseState: "usable" | "configured-but-unavailable" | "preview-not-counted";
  referenceRequired: boolean;
}> = [
  {
    id: "dify",
    label: "Dify",
    placeholder: "https://api.dify.ai/v1",
    secretPlaceholder: "secret://dify",
    helper: "运行时检索",
    releaseState: "usable",
    referenceRequired: true,
  },
  {
    id: "coze",
    label: "Coze",
    placeholder: "https://api.coze.cn",
    secretPlaceholder: "secret://coze",
    helper: "运行时检索",
    releaseState: "usable",
    referenceRequired: true,
  },
  {
    id: "ragflow",
    label: "RAGFlow",
    placeholder: "https://ragflow.example",
    secretPlaceholder: "secret://ragflow",
    helper: "预览",
    releaseState: "preview-not-counted",
    referenceRequired: true,
  },
  {
    id: "langchain",
    label: "LangChain Retriever",
    placeholder: "langchain://retriever/default",
    secretPlaceholder: "secret://langchain",
    helper: "Retriever grounding",
    releaseState: "configured-but-unavailable",
    referenceRequired: false,
  },
  {
    id: "local_dify",
    label: "Local Dify",
    placeholder: "http://127.0.0.1:5001/v1",
    secretPlaceholder: "secret://local-dify",
    helper: "本地端点",
    releaseState: "preview-not-counted",
    referenceRequired: false,
  },
  {
    id: "local_ragflow",
    label: "Local RAGFlow",
    placeholder: "http://127.0.0.1:9380",
    secretPlaceholder: "secret://local-ragflow",
    helper: "本地端点",
    releaseState: "preview-not-counted",
    referenceRequired: false,
  },
];

type KnowledgeFilePayload = {
  title: string;
  content: string;
  mimeType: "text/plain" | "text/markdown";
};

function readFileText(file: File): Promise<string> {
  if ("text" in file && typeof file.text === "function") {
    return file.text();
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("文件读取失败"));
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.readAsText(file);
  });
}

async function readKnowledgeFile(file: File): Promise<KnowledgeFilePayload> {
  const name = file.name.toLowerCase();
  const isPlainText = name.endsWith(".txt") || file.type === "text/plain";
  const isMarkdown = name.endsWith(".md") || file.type === "text/markdown";
  if (!isPlainText && !isMarkdown) {
    throw new Error("仅支持 .txt / .md 文件");
  }
  if (file.size > knowledgeFileMaxBytes) {
    throw new Error("文件不能超过 120KB");
  }
  const content = await readFileText(file);
  if (!content.trim()) {
    throw new Error("文件内容不能为空");
  }
  return {
    title: file.name.replace(/\.(txt|md)$/i, "") || file.name,
    content,
    mimeType: isPlainText && !isMarkdown ? "text/plain" : "text/markdown",
  };
}

function connectorSeedContent(providerLabel: string, endpoint: string, datasetId: string) {
  const rows = [
    `# ${providerLabel} API 连接器`,
    "",
    `API 地址：${endpoint.trim() || "未配置"}`,
  ];
  if (datasetId.trim()) {
    rows.push(`数据集：${datasetId.trim()}`);
  }
  rows.push("", "该知识源保存外部知识库接入配置，用于预检、运行时检索或 Harness grounding adapter。");
  return rows.join("\n");
}

export function filterKnowledgeSources(
  sources: KnowledgeSource[],
  sourceFilter: KnowledgeSourceFilter,
) {
  if (sourceFilter === "all") {
    return sources;
  }
  if (sourceFilter === "local") {
    return sources.filter((source) => source.source_type !== "connector");
  }
  if (sourceFilter === "api") {
    return sources.filter((source) => source.source_type === "connector");
  }
  return sources.filter(
    (source) =>
      source.source_type === "connector" &&
      source.connector_release_state === "preview-not-counted",
  );
}

export function KnowledgeManagementPanel({
  agentId,
  variant = "embedded",
  sourceFilter = "all",
}: KnowledgeManagementPanelProps) {
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [createMode, setCreateMode] = useState<KnowledgeCreateMode | null>(null);
  const sources = useQuery({
    queryKey: queryKeyForSources(agentId),
    queryFn: () => listAgentKnowledgeSources(agentId),
  });
  const selectedSource = useMemo(
    () => sources.data?.items.find((source) => source.id === selectedSourceId) ?? null,
    [selectedSourceId, sources.data?.items],
  );
  const visibleSources = useMemo(
    () => filterKnowledgeSources(sources.data?.items ?? [], sourceFilter),
    [sourceFilter, sources.data?.items],
  );
  const documents = useQuery({
    queryKey: queryKeyForDocuments(agentId, selectedSourceId),
    queryFn: () => listAgentKnowledgeDocuments(agentId, selectedSourceId ?? ""),
    enabled: selectedSourceId !== null,
  });

  useEffect(() => {
    const firstSource = visibleSources[0] ?? null;
    if (!visibleSources.length) {
      setSelectedSourceId(null);
      return;
    }
    if (!visibleSources.some((source) => source.id === selectedSourceId)) {
      setSelectedSourceId(firstSource?.id ?? null);
    }
  }, [selectedSourceId, visibleSources]);

  const refresh = async (sourceId = selectedSourceId) => {
    await queryClient.invalidateQueries({ queryKey: queryKeyForSources(agentId) });
    if (sourceId) {
      await queryClient.invalidateQueries({
        queryKey: queryKeyForDocuments(agentId, sourceId),
      });
    }
  };
  const refreshAfterDelete = async (sourceId: string) => {
    setSelectedSourceId(null);
    queryClient.removeQueries({ queryKey: queryKeyForDocuments(agentId, sourceId) });
    await queryClient.invalidateQueries({ queryKey: queryKeyForSources(agentId) });
  };

  return (
    <section className="grid grid-cols-12 gap-4">
      <Card className="col-span-12 lg:col-span-4">
        <CardHeader className="flex-wrap gap-2">
          <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
            <Database className="h-4 w-4" />
            {text("知识源", "Knowledge Sources")}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="success">{visibleSources.length}</Badge>
            <Button
              type="button"
              variant="secondary"
              onClick={() => setCreateMode("document")}
            >
              <FilePlus2 className="h-3.5 w-3.5" />
              {text("本地文档", "Local Document")}
            </Button>
            <Button
              type="button"
              variant="primary"
              onClick={() => setCreateMode("connector")}
            >
              <Cable className="h-3.5 w-3.5" />
              {text("外部 API", "External API")}
            </Button>
          </div>
        </CardHeader>
        <div className="space-y-3 p-3">
          <KnowledgeSourceList
            isLoading={sources.isLoading}
            sources={visibleSources}
            selectedSourceId={selectedSourceId}
            onSelect={setSelectedSourceId}
            onCreateDocument={() => setCreateMode("document")}
          />
        </div>
        <KnowledgeCreateDialog
          agentId={agentId}
          initialMode={createMode ?? "document"}
          open={createMode !== null}
          onClose={() => setCreateMode(null)}
          onCreated={async (source) => {
            setSelectedSourceId(source.id);
            await refresh(source.id);
          }}
        />
      </Card>
      <Card className="col-span-12 lg:col-span-8">
        <CardHeader>
          <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
            <History className="h-4 w-4" />
            {text("文档与生命周期", "Documents & Lifecycle")}
          </div>
          {selectedSource ? <KnowledgeScopeBadge source={selectedSource} /> : null}
        </CardHeader>
        <div className="space-y-3 p-3">
          {selectedSource ? (
            <KnowledgeSourceDetail
              agentId={agentId}
              source={selectedSource}
              documents={documents.data ?? selectedSource.latest_documents}
              documentsLoading={documents.isLoading}
              onChanged={() => refresh(selectedSource.id)}
              onDeleted={() => refreshAfterDelete(selectedSource.id)}
              compact={variant === "embedded"}
            />
          ) : (
            <>
              <EmptyState
                icon={<Database className="h-4 w-4" />}
                title={text("暂无知识源", "No knowledge sources yet")}
                description={text(
                  "上传本地文档或配置外部 API，智能体即可引用知识库回答问题。",
                  "Upload a local document or configure an external API so agents can answer with knowledge.",
                )}
                action={
                  <Button type="button" variant="primary" onClick={() => setCreateMode("document")}>
                    {text("上传文档", "Upload document")}
                  </Button>
                }
              />
              <span className="sr-only">暂无知识源。</span>
            </>
          )}
        </div>
      </Card>
    </section>
  );
}

function KnowledgeCreateDialog({
  agentId,
  initialMode,
  open,
  onClose,
  onCreated,
}: {
  agentId: string;
  initialMode: KnowledgeCreateMode;
  open: boolean;
  onClose: () => void;
  onCreated: (source: KnowledgeSource) => Promise<void>;
}) {
  const { text } = useI18n();
  const [mode, setMode] = useState<KnowledgeCreateMode>("document");
  const [connectorPreset, setConnectorPreset] = useState<ConnectorPresetId>("dify");
  const [endpoint, setEndpoint] = useState("");
  const [secretRef, setSecretRef] = useState("secret://dify");
  const [secretValue, setSecretValue] = useState("");
  const [datasetId, setDatasetId] = useState("");
  const secretRefInvalid = mode === "connector" && looksLikeRawSecretRef(secretRef);
  const [name, setName] = useState("默认知识源");
  const [description, setDescription] = useState("");
  const [scope, setScope] = useState<"agent" | "org">("agent");
  const [title, setTitle] = useState("团队手册");
  const [content, setContent] = useState("# 团队手册\n\n使用简洁、带引用的回答。\n");
  const [mimeType, setMimeType] = useState<"text/plain" | "text/markdown">("text/markdown");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const canCreateOrgScope = useCanManageOrgKnowledge();

  useEffect(() => {
    if (!open) {
      return;
    }
    setMode(initialMode);
    setConnectorPreset("dify");
    setEndpoint(initialMode === "connector" ? "https://api.dify.ai/v1" : "");
    setSecretRef("secret://dify");
    setSecretValue("");
    setDatasetId("");
    setName(initialMode === "connector" ? "Dify 知识库" : "默认知识源");
    setDescription("");
    setScope("agent");
    setTitle("团队手册");
    setContent("# 团队手册\n\n使用简洁、带引用的回答。\n");
    setMimeType("text/markdown");
    setSelectedFile(null);
    setFileError(null);
  }, [initialMode, open]);

  useEffect(() => {
    if (!canCreateOrgScope && scope === "org") {
      setScope("agent");
    }
  }, [canCreateOrgScope, scope]);
  useEffect(() => {
    if (mode !== "connector") {
      return;
    }
    const preset = connectorPresets.find((item) => item.id === connectorPreset);
    if (!preset) {
      return;
    }
    if (!name || name === "默认知识源" || connectorPresets.some((item) => name === `${item.label} 知识库`)) {
      setName(`${preset.label} 知识库`);
    }
    if (connectorPresets.some((item) => endpoint === item.placeholder)) {
      setEndpoint(preset.placeholder);
    }
    if (connectorPresets.some((item) => secretRef === item.secretPlaceholder)) {
      setSecretRef(preset.secretPlaceholder);
    }
  }, [connectorPreset, endpoint, mode, name, secretRef]);
  const selectedPreset = connectorPresets.find((item) => item.id === connectorPreset);
  const createSource = useMutation({
    mutationFn: () => {
      if (mode === "connector") {
        const preset = connectorPresets.find((item) => item.id === connectorPreset);
        const providerLabel = preset?.label ?? connectorPreset;
        return createAgentKnowledgeSource(agentId, {
          name: name.trim() || `${providerLabel} 知识库`,
          description: description.trim() || `${providerLabel} API 接入配置`,
          scope,
          source_type: "connector",
          title: `${providerLabel} API 连接器`,
          content: connectorSeedContent(providerLabel, endpoint, datasetId),
          uri: endpoint.trim() || null,
          mime_type: "text/markdown",
          idempotency_key: `connector:${connectorPreset}:${endpoint.trim() || "default"}`,
          connector_secret_value: secretValue.trim() || null,
          connector_settings_json: {
            provider: connectorPreset,
            ...(connectorPreset === "langchain" ? { source_kind: "langchain_connector" } : {}),
            release_state: preset?.releaseState,
            endpoint: endpoint.trim(),
            secret_ref: secretRef.trim(),
            ...(datasetId.trim() ? { dataset_id: datasetId.trim() } : {}),
          },
        });
      }
      if (selectedFile) {
        return importAgentKnowledgeSourceFile(agentId, selectedFile, {
          name,
          description,
          scope,
          title,
        });
      }
      return createAgentKnowledgeSource(agentId, {
        name,
        description,
        scope,
        title,
        content,
        source_type: mimeType === "text/plain" ? "text" : "markdown",
        mime_type: mimeType,
      });
    },
    onSuccess: async (source) => {
      notifyFeedback({
        tone: "success",
        title:
          mode === "connector"
            ? text("外部知识库配置已保存", "External knowledge connector saved")
            : text("知识源已创建", "Knowledge source created"),
        description:
          mode === "connector"
            ? text(
                `知识源“${source.name}”已经保存，可继续用于预检或运行时检索。`,
                `${source.name} is saved and ready for preflight or runtime retrieval.`,
              )
            : text(
                `知识源“${source.name}”已经创建并开始建立索引。`,
                `${source.name} has been created and indexing has started.`,
              ),
      });
      await onCreated(source);
      onClose();
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title:
          mode === "connector"
            ? text("外部知识库配置保存失败", "External knowledge connector save failed")
            : text("知识源创建失败", "Knowledge source creation failed"),
        description: feedbackErrorMessage(
          error,
          mode === "connector"
            ? text("请检查 API 地址、密钥引用和数据集 ID。", "Check the API endpoint, secret reference, and dataset ID.")
            : text("请检查知识源名称、内容或文件格式。", "Check the source name, content, or file format."),
        ),
      });
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    createSource.mutate();
  };

  const importFile = async (file: File | undefined) => {
    if (!file) {
      return;
    }
    try {
      const imported = await readKnowledgeFile(file);
      setSelectedFile(file);
      setTitle(imported.title);
      setContent(imported.content);
      setMimeType(imported.mimeType);
      if (name === "默认知识源") {
        setName(imported.title);
      }
      setFileError(null);
    } catch (error) {
      setSelectedFile(null);
      setFileError(error instanceof Error ? error.message : "文件导入失败");
    }
  };

  if (!open) {
    return null;
  }

  return (
    <KnowledgeModal
      title={mode === "connector" ? text("新增外部 API 接入", "Add External API") : text("新增本地知识", "Add Local Knowledge")}
      description={
        mode === "connector"
          ? text("Dify 和 Coze 可用于运行时检索；LangChain Retriever 保存为 grounding adapter 配置；RAGFlow 和本地端点仍仅保存配置和预检状态。", "Dify and Coze can be used for runtime retrieval; LangChain Retriever is stored as grounding adapter config; RAGFlow and local endpoints store configuration and readiness only.")
          : text("上传 .txt/.md 或直接写入手动文本。", "Upload .txt/.md files or paste manual text.")
      }
      onClose={onClose}
    >
      <form className="space-y-4" onSubmit={submit}>
        <div className="grid grid-cols-2 gap-1 rounded-md bg-slate-100 p-1 text-xs">
          <button
            type="button"
            className={`rounded px-2 py-2 font-medium ${
              mode === "document" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500"
            }`}
            onClick={() => setMode("document")}
          >
            {text("本地文档", "Local Document")}
          </button>
          <button
            type="button"
            className={`rounded px-2 py-2 font-medium ${
              mode === "connector" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500"
            }`}
            onClick={() => setMode("connector")}
          >
            {text("外部 API", "External API")}
          </button>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <label className="space-y-1.5 text-xs font-medium text-slate-600">
            {text("名称", "Name")}
            <Input
              aria-label={text("知识源名称", "Knowledge source name")}
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={text("知识源名称", "Source name")}
            />
          </label>
          <div className="space-y-1.5 text-xs font-medium text-slate-600">
            <span>{text("作用域", "Scope")}</span>
            <MenuSelect
              ariaLabel={text("知识源作用域", "Knowledge source scope")}
              value={scope}
              onChange={(value) => setScope(value as "agent" | "org")}
              placeholder={text("请选择作用域", "Select scope")}
              className="min-w-0"
              buttonClassName="h-9 rounded-md px-3 py-2 shadow-none"
              menuClassName="w-[280px]"
              options={[
                {
                  value: "agent",
                  label: text("智能体作用域", "Agent scope"),
                  description: text("仅当前智能体可见", "Visible only in this agent"),
                },
                {
                  value: "org",
                  label: text("组织作用域", "Org scope"),
                  description: text("组织内共享，管理员可用", "Shared across the org, admin only"),
                  disabled: !canCreateOrgScope,
                },
              ]}
            />
          </div>
        </div>

        <label className="space-y-1.5 text-xs font-medium text-slate-600">
          {text("说明", "Description")}
          <Input
            aria-label={text("知识源说明", "Knowledge source description")}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder={text("说明", "Description")}
          />
        </label>

        {mode === "document" ? (
          <div className="grid gap-3">
            <label className="space-y-1.5 text-xs font-medium text-slate-600">
              {text("初始文档标题", "Initial document title")}
              <Input
                aria-label={text("初始文档标题", "Initial document title")}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder={text("文档标题", "Document title")}
              />
            </label>
            <label className="space-y-1.5 text-xs font-medium text-slate-600">
              {text("初始文档内容", "Initial document content")}
              <Textarea
                aria-label={text("初始文档内容", "Initial document content")}
                value={content}
                onChange={(event) => setContent(event.target.value)}
                className="min-h-40"
              />
            </label>
            <label className="inline-flex h-9 w-fit cursor-pointer items-center justify-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-50">
              <Upload className="h-3.5 w-3.5" />
              {text("导入 .txt / .md", "Import .txt / .md")}
              <input
                aria-label={text("导入初始文件", "Import initial file")}
                className="sr-only"
                type="file"
                accept={knowledgeFileAccept}
                onChange={(event) => importFile(event.target.files?.[0])}
              />
            </label>
          </div>
        ) : (
          <div className="space-y-3 rounded-md border border-slate-100 bg-slate-50 p-3">
            <div className="grid gap-2 sm:grid-cols-3">
              {connectorPresets.map((preset) => (
                <button
                  key={preset.id}
                  type="button"
                  className={`rounded-md border px-3 py-3 text-left text-xs transition ${
                    connectorPreset === preset.id
                      ? "border-slate-900 bg-white text-slate-950 shadow-sm"
                      : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                  }`}
                  onClick={() => setConnectorPreset(preset.id)}
                >
                  <div className="font-semibold">{preset.label}</div>
                  <div className="mt-1 truncate text-[11px] text-slate-500">
                    {preset.helper}
                  </div>
                </button>
              ))}
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="space-y-1.5 text-xs font-medium text-slate-600">
                {text("API 地址", "API endpoint")}
                <Input
                  aria-label={text("外部 API 地址", "External API endpoint")}
                  value={endpoint}
                  onChange={(event) => setEndpoint(event.target.value)}
                  placeholder={connectorPresets.find((item) => item.id === connectorPreset)?.placeholder}
                />
              </label>
              <label className="space-y-1.5 text-xs font-medium text-slate-600">
                {text("密钥引用", "Secret reference")}
                <Input
                  aria-label={text("密钥引用", "Secret reference")}
                  value={secretRef}
                  onChange={(event) => setSecretRef(event.target.value)}
                  placeholder={connectorPresets.find((item) => item.id === connectorPreset)?.secretPlaceholder}
                />
                {secretRefInvalid ? (
                  <span role="alert" className="block text-[11px] text-red-700">
                    {text(
                      "这里填写引用名，例如 secret://dify；真实 API Key 请填到下方密钥值。",
                      "Enter a reference such as secret://dify here; put the real API key in the secret value field below.",
                    )}
                  </span>
                ) : null}
              </label>
            </div>
            <label className="space-y-1.5 text-xs font-medium text-slate-600">
              {text("API Key 密钥值", "API key secret value")}
              <Input
                aria-label={text("API Key 密钥值", "API key secret value")}
                value={secretValue}
                onChange={(event) => setSecretValue(event.target.value)}
                placeholder={text("可选：首次创建或替换密钥时填写", "Optional: enter when creating or replacing the secret")}
                type="password"
                autoComplete="off"
              />
              <span className="block text-[11px] text-slate-500">
                {text(
                  "密钥只保存到后端服务端密钥存储，不会写入知识源配置或接口响应。",
                  "The key is stored only in the backend secret store and is not returned in source configuration or API responses.",
                )}
              </span>
            </label>
            <label className="space-y-1.5 text-xs font-medium text-slate-600">
              {text("数据集或空间 ID", "Dataset or space ID")}
              <Input
                aria-label={text("数据集或空间 ID", "Dataset or space ID")}
                value={datasetId}
                onChange={(event) => setDatasetId(event.target.value)}
                placeholder={
                  selectedPreset?.referenceRequired
                    ? text("必填：dataset / space id", "Required: dataset / space id")
                    : text("可选：dataset / space id", "Optional: dataset / space id")
                }
              />
            </label>
          </div>
        )}

        {fileError ? <div className="text-xs text-red-700">{fileError}</div> : null}
        <MutationError error={createSource.error} />

        <div className="flex items-center justify-end gap-2 border-t border-slate-100 pt-4">
          <Button type="button" variant="ghost" onClick={onClose}>
            {text("取消", "Cancel")}
          </Button>
          <Button
            type="submit"
            variant="primary"
            disabled={
              createSource.isPending
              || !name.trim()
              || (mode === "document" && !content.trim())
              || (mode === "connector" && (!endpoint.trim() || !secretRef.trim()))
              || secretRefInvalid
              || (mode === "connector" && Boolean(selectedPreset?.referenceRequired) && !datasetId.trim())
            }
          >
            {mode === "connector" ? <Cable className="h-3.5 w-3.5" /> : <Plus className="h-3.5 w-3.5" />}
            {createSource.isPending
              ? mode === "connector"
                ? text("保存中", "Saving")
                : text("索引中", "Indexing")
              : mode === "connector"
                ? text("保存配置", "Save Config")
                : text("创建", "Create")}
          </Button>
        </div>
      </form>
    </KnowledgeModal>
  );
}

function KnowledgeSourceList({
  isLoading,
  sources,
  selectedSourceId,
  onSelect,
  onCreateDocument,
}: {
  isLoading: boolean;
  sources: KnowledgeSource[];
  selectedSourceId: string | null;
  onSelect: (sourceId: string) => void;
  onCreateDocument: () => void;
}) {
  const { text } = useI18n();
  if (isLoading) {
    return <div className="py-3 text-sm text-slate-500">{text("加载中...", "Loading...")}</div>;
  }
  return (
    <div className="space-y-2">
      {sources.map((source) => (
        <button
          key={source.id}
          className={`w-full rounded-md border p-3 text-left text-xs transition ${
            source.id === selectedSourceId
              ? "border-slate-900 bg-slate-50"
              : "border-slate-100 bg-white hover:border-slate-300"
          }`}
          type="button"
          onClick={() => onSelect(source.id)}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="truncate font-medium text-slate-900">{source.name}</span>
            <KnowledgeStatusBadge status={source.status} />
          </div>
          <div className="mt-2 flex flex-wrap gap-1">
            <KnowledgeScopeBadge source={source} />
            <KnowledgeHealthBadge source={source} />
            <KnowledgeConnectorBadge source={source} />
            <KnowledgeConnectorValidationBadge source={source} />
          </div>
        </button>
      ))}
      {!sources.length ? (
        <EmptyState
          icon={<Database className="h-4 w-4" />}
          title={text("暂无知识源", "No knowledge sources yet")}
          description={text(
            "上传本地文档或配置外部 API，智能体即可引用知识库回答问题。",
            "Upload a local document or configure an external API so agents can answer with knowledge.",
          )}
          action={
            <Button type="button" variant="primary" onClick={onCreateDocument}>
              {text("上传文档", "Upload document")}
            </Button>
          }
        />
      ) : null}
    </div>
  );
}

function KnowledgeSourceDetail({
  agentId,
  source,
  documents,
  documentsLoading,
  onChanged,
  onDeleted,
  compact,
}: {
  agentId: string;
  source: KnowledgeSource;
  documents: KnowledgeDocument[];
  documentsLoading: boolean;
  onChanged: () => Promise<void>;
  onDeleted: () => Promise<void>;
  compact: boolean;
}) {
  const { text } = useI18n();
  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-[1fr_auto]">
        <KnowledgeSourceSummary agentId={agentId} source={source} onChanged={onChanged} />
        <KnowledgeSourceActions
          agentId={agentId}
          source={source}
          onChanged={onChanged}
          onDeleted={onDeleted}
        />
      </div>
      <div className={compact ? "grid gap-3 xl:grid-cols-[1fr_260px]" : "grid gap-3 2xl:grid-cols-[1fr_280px]"}>
        <KnowledgeDocumentList documents={documents} isLoading={documentsLoading} />
        <div className="space-y-2 rounded-md border border-slate-100 bg-slate-50 p-3">
          <div className="text-sm font-semibold text-slate-900">
            {documents.length
              ? `${documents.length} ${text("个文档版本", "document versions")}`
              : text("暂无文档版本", "No document versions")}
          </div>
          <div className="text-xs text-slate-500">
            {text("文档新增和重新导入都在弹窗中完成。", "Add and reingest documents from dialogs.")}
          </div>
          <KnowledgeDocumentIngestDialog agentId={agentId} source={source} onChanged={onChanged} />
          <KnowledgeDocumentVersionHistory
            agentId={agentId}
            source={source}
            documents={documents}
            onChanged={onChanged}
          />
        </div>
      </div>
    </div>
  );
}

function KnowledgeSourceSummary({
  agentId,
  source,
  onChanged,
}: {
  agentId: string;
  source: KnowledgeSource;
  onChanged: () => Promise<void>;
}) {
  const { text } = useI18n();
  const [editOpen, setEditOpen] = useState(false);
  const isConnector = source.source_type === "connector";

  return (
    <div className="space-y-3 rounded-md border border-slate-100 bg-slate-50 p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-base font-semibold text-slate-950">{source.name}</div>
          <div className="mt-1 text-xs leading-5 text-slate-500">
            {source.description || text("暂无说明", "No description")}
          </div>
        </div>
        <Button type="button" variant="secondary" onClick={() => setEditOpen(true)}>
          <PencilLine className="h-3.5 w-3.5" />
          {text("编辑", "Edit")}
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <KnowledgeStatusBadge status={source.status} />
        <KnowledgeHealthBadge source={source} />
        <KnowledgeConnectorBadge source={source} />
        <KnowledgeConnectorValidationBadge source={source} />
        <span className="font-mono text-[11px] text-slate-500">{source.id}</span>
      </div>
      {source.source_type === "connector" ? (
        <div className="grid gap-2 rounded-md border border-slate-200 bg-white p-3 text-xs text-slate-500 sm:grid-cols-3">
          <div>
            <div className="text-[11px] text-slate-400">{text("提供方", "Provider")}</div>
            <div className="mt-1 font-medium text-slate-700">
              {connectorProviderLabel(source.connector_provider ?? connectorProviderFromSettings(source))}
            </div>
          </div>
          <div>
            <div className="text-[11px] text-slate-400">{text("发布状态", "Release")}</div>
            <div className="mt-1 font-medium text-slate-700">
              {source.connector_release_state ?? connectorReleaseStateFromSettings(source)}
            </div>
          </div>
          <div>
            <div className="text-[11px] text-slate-400">{text("可用于运行", "Usable")}</div>
            <div className="mt-1 font-medium text-slate-700">
              {source.connector_counts_toward_complete_usable ? text("是", "yes") : text("否", "no")}
            </div>
          </div>
          <div>
            <div className="text-[11px] text-slate-400">
              {text("密钥", "Secret")}
            </div>
            <div className="mt-1 font-medium text-slate-700">
              {source.connector_secret_configured
                ? text("已配置", "configured")
                : text("未配置", "missing")}
            </div>
          </div>
          {source.connector_validation_messages?.length ? (
            <div className="sm:col-span-3 text-amber-700">
              {source.connector_validation_messages.join(", ")}
            </div>
          ) : null}
        </div>
      ) : null}
      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <span>{text("最后索引", "Last indexed")}: {formatDateTime(source.last_indexed_at)}</span>
        {source.last_ingestion_error ? (
          <Badge tone="failed">{source.last_ingestion_error}</Badge>
        ) : null}
      </div>
      <KnowledgeSourceEditDialog
        agentId={agentId}
        source={source}
        open={editOpen}
        onClose={() => setEditOpen(false)}
        onChanged={onChanged}
      />
      {isConnector ? null : null}
    </div>
  );
}

function KnowledgeSourceEditDialog({
  agentId,
  source,
  open,
  onClose,
  onChanged,
}: {
  agentId: string;
  source: KnowledgeSource;
  open: boolean;
  onClose: () => void;
  onChanged: () => Promise<void>;
}) {
  const { text } = useI18n();
  const isConnector = source.source_type === "connector";
  const [name, setName] = useState(source.name);
  const [description, setDescription] = useState(source.description);
  const [endpoint, setEndpoint] = useState("");
  const [secretRef, setSecretRef] = useState("");
  const [datasetId, setDatasetId] = useState("");
  const [secretValue, setSecretValue] = useState("");
  const provider = source.connector_provider ?? connectorProviderFromSettings(source);
  const providerLabel = connectorProviderLabel(provider);
  const secretRefInvalid = isConnector && looksLikeRawSecretRef(secretRef);
  const endpointHasCredentials = isConnector && endpointIncludesUserinfo(endpoint);
  const datasetRequired = isConnector && connectorReferenceRequired(provider);

  useEffect(() => {
    if (!open) {
      return;
    }
    setName(source.name);
    setDescription(source.description);
    setEndpoint(stringSetting(source, "endpoint") || stringSetting(source, "uri"));
    setSecretRef(stringSetting(source, "secret_ref") || stringSetting(source, "auth_secret_ref"));
    setDatasetId(stringSetting(source, "dataset_id") || stringSetting(source, "space_id"));
    setSecretValue("");
  }, [open, source]);

  const updateSource = useMutation({
    mutationFn: () => {
      const payload = {
        name,
        description,
        ...(isConnector
          ? {
              connector_settings_json: {
                ...source.settings_json,
                provider,
                endpoint: endpoint.trim(),
                secret_ref: secretRef.trim(),
                dataset_id: datasetId.trim() || undefined,
              },
            }
          : {}),
        ...(isConnector && secretValue.trim()
          ? { connector_secret_value: secretValue.trim() }
          : {}),
      };
      return updateAgentKnowledgeSource(agentId, source.id, payload, { admin: source.scope === "org" });
    },
    onSuccess: async () => {
      notifyFeedback({
        tone: "success",
        title: isConnector
          ? text("外部知识库配置已更新", "External knowledge connector updated")
          : text("知识源已更新", "Knowledge source updated"),
        description: isConnector
          ? text("新的 API 接入配置已经生效。", "The updated connector settings are now active.")
          : text(`知识源“${source.name}”的信息已经保存。`, `${source.name} has been updated.`),
      });
      await onChanged();
      onClose();
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: isConnector
          ? text("外部知识库配置更新失败", "External knowledge connector update failed")
          : text("知识源更新失败", "Knowledge source update failed"),
        description: feedbackErrorMessage(
          error,
          isConnector
            ? text("请检查 API 地址、密钥引用或数据集 ID。", "Check the API endpoint, secret reference, or dataset ID.")
            : text("请检查知识源名称和说明。", "Check the source name and description."),
        ),
      });
    },
  });
  const canSave =
    !updateSource.isPending &&
    Boolean(name.trim()) &&
    (!isConnector ||
      (Boolean(endpoint.trim()) &&
        Boolean(secretRef.trim()) &&
        !secretRefInvalid &&
        !endpointHasCredentials &&
        (!datasetRequired || Boolean(datasetId.trim()))));

  if (!open) {
    return null;
  }

  return (
    <KnowledgeModal
      title={
        isConnector
          ? text("编辑外部知识库接入", "Edit External Knowledge Connector")
          : text("编辑本地知识源", "Edit Local Knowledge Source")
      }
      description={
        isConnector
          ? text(
              "更新名称、API 端点、密钥引用、数据集 ID，或替换 API Key。留空 API Key 不会覆盖已保存密钥。",
              "Update the name, API endpoint, secret reference, dataset ID, or replace the API key. Leaving the API key blank keeps the saved secret.",
            )
          : text("更新知识源名称和说明。", "Update the knowledge source name and description.")
      }
      onClose={onClose}
    >
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          updateSource.mutate();
        }}
      >
        {isConnector ? (
          <div className="rounded-md border border-cyan-100 bg-cyan-50/60 p-3 text-xs text-cyan-900">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="info">
                <Cable className="h-3 w-3" />
                {providerLabel}
              </Badge>
              <Badge tone={source.connector_secret_configured ? "success" : "warning"}>
                {source.connector_secret_configured ? text("密钥已保存", "Secret saved") : text("密钥未保存", "Secret missing")}
              </Badge>
              <Badge tone={source.connector_counts_toward_complete_usable ? "success" : "pending"}>
                {source.connector_counts_toward_complete_usable ? text("可用于检索", "Retrieval usable") : text("仅配置预览", "Configuration preview")}
              </Badge>
            </div>
            <div className="mt-2 leading-5">
              {text(
                "Coze 请填写知识库 URL 中 /knowledge/ 后面的 ID；/space/ 后面的 ID 是空间 ID，通常不作为这里的 dataset_id。",
                "For Coze, enter the ID after /knowledge/ in the knowledge URL; the ID after /space/ is the space ID and is usually not the dataset_id here.",
              )}
            </div>
          </div>
        ) : null}

        <section className="space-y-3 rounded-md border border-slate-100 bg-slate-50 p-3">
          <div className="text-xs font-semibold text-slate-900">
            {text("基础信息", "Basic information")}
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1.5 text-xs font-medium text-slate-600">
              {text("名称（可编辑）", "Name (editable)")}
              <Input
                aria-label={text("编辑知识源名称", "Edit knowledge source name")}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <label className="space-y-1.5 text-xs font-medium text-slate-600">
              {text("说明（可编辑）", "Description (editable)")}
              <Input
                aria-label={text("编辑知识源说明", "Edit knowledge source description")}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </label>
          </div>
          <div className="grid gap-2 rounded-md border border-slate-200 bg-white p-3 text-xs text-slate-500 sm:grid-cols-2">
            <ReadOnlyField label={text("知识源 ID", "Source ID")} value={source.id} mono />
            <ReadOnlyField label={text("作用域", "Scope")} value={source.scope} />
          </div>
        </section>

        {isConnector ? (
          <section className="space-y-3 rounded-md border border-slate-100 bg-slate-50 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-xs font-semibold text-slate-900">
                {text("API 接入配置（保存后立即生效）", "API connector configuration")}
              </div>
              <Badge tone={source.connector_validation_status === "ready" ? "success" : "warning"}>
                {source.connector_validation_status ?? "ready"}
              </Badge>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <ReadOnlyField label={text("Provider（只读）", "Provider (read-only)")} value={providerLabel} />
              <label className="space-y-1.5 text-xs font-medium text-slate-600">
                {text("API Endpoint（可编辑）", "API endpoint (editable)")}
                <Input
                  aria-label={text("编辑 API Endpoint", "Edit API endpoint")}
                  value={endpoint}
                  onChange={(event) => setEndpoint(event.target.value)}
                  placeholder={connectorDefaultEndpoint(provider)}
                />
                {endpointHasCredentials ? (
                  <span role="alert" className="block text-[11px] text-red-700">
                    {text("Endpoint 不能包含用户名、密码或 token。", "Endpoint must not include username, password, or token.")}
                  </span>
                ) : null}
              </label>
              <label className="space-y-1.5 text-xs font-medium text-slate-600">
                {text("Secret Ref（可编辑）", "Secret ref (editable)")}
                <Input
                  aria-label={text("编辑 Secret Ref", "Edit secret ref")}
                  value={secretRef}
                  onChange={(event) => setSecretRef(event.target.value)}
                  placeholder={connectorDefaultSecretRef(provider)}
                />
                {secretRefInvalid ? (
                  <span role="alert" className="block text-[11px] text-red-700">
                    {text(
                      "这里填写 secret://coze 这类引用名；真实 API Key 请填到下方替换字段。",
                      "Enter a reference such as secret://coze here; put the real API key in the replacement field below.",
                    )}
                  </span>
                ) : (
                  <span className="block text-[11px] text-slate-500">
                    {text("引用名决定 API Key 保存到哪个后端密钥槽。", "The reference decides which backend secret slot stores the API key.")}
                  </span>
                )}
              </label>
              <label className="space-y-1.5 text-xs font-medium text-slate-600">
                {text("数据集 / 知识库 ID（可编辑）", "Dataset / knowledge ID (editable)")}
                <Input
                  aria-label={text("编辑数据集或知识库 ID", "Edit dataset or knowledge ID")}
                  value={datasetId}
                  onChange={(event) => setDatasetId(event.target.value)}
                  placeholder={
                    provider === "coze"
                      ? "Coze /knowledge/{id}"
                      : text("dataset_id", "dataset_id")
                  }
                />
                <span className="block text-[11px] text-slate-500">
                  {provider === "coze"
                    ? text(
                        "示例：https://www.coze.cn/space/761.../knowledge/762... 中应填 762...。",
                        "Example: in https://www.coze.cn/space/761.../knowledge/762..., enter 762....",
                      )
                    : text("Dify/RAGFlow 填数据集 ID。", "For Dify/RAGFlow, enter the dataset ID.")}
                </span>
              </label>
            </div>
            <label className="space-y-1.5 text-xs font-medium text-slate-600">
              {text("替换 API Key（可选）", "Replace API key (optional)")}
              <Input
                aria-label={text("替换 API Key", "Replace API key")}
                value={secretValue}
                onChange={(event) => setSecretValue(event.target.value)}
                placeholder={
                  source.connector_secret_configured
                    ? text("已配置；留空则不修改密钥", "Configured; leave blank to keep it")
                    : text("未配置；填写后保存到后端密钥存储", "Missing; enter a key to save it")
                }
                type="password"
                autoComplete="off"
              />
              <span className="block text-[11px] text-slate-500">
                {text(
                  "API Key 不会写入知识源配置，也不会在接口响应或弹窗中回显。",
                  "The API key is not written to source configuration and is never returned in API responses or shown in this dialog.",
                )}
              </span>
            </label>
            {source.connector_validation_messages?.length ? (
              <div className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
                {source.connector_validation_messages.join(", ")}
              </div>
            ) : null}
          </section>
        ) : null}
        <MutationError error={updateSource.error} />
        <div className="flex items-center justify-end gap-2 border-t border-slate-100 pt-4">
          <Button type="button" variant="ghost" onClick={onClose}>
            {text("取消", "Cancel")}
          </Button>
          <Button
            type="submit"
            variant="primary"
            disabled={!canSave}
          >
            <Save className="h-3.5 w-3.5" />
            {text("保存", "Save")}
          </Button>
        </div>
      </form>
    </KnowledgeModal>
  );
}

function KnowledgeSourceActions({
  agentId,
  source,
  onChanged,
  onDeleted,
}: {
  agentId: string;
  source: KnowledgeSource;
  onChanged: () => Promise<void>;
  onDeleted: () => Promise<void>;
}) {
  const { text } = useI18n();
  const { confirm, confirmDialog } = useConfirmDialog();
  const requiresAdmin = source.scope === "org";
  const canUseAdminControls = useCanManageOrgKnowledge();
  const nextScopeLabel = source.scope === "org" ? "智能体" : "组织";
  const disableSource = useMutation({
    mutationFn: () =>
      disableAgentKnowledgeSource(
        agentId,
        source.id,
        { reason: "studio" },
        { admin: requiresAdmin },
      ),
    onSuccess: async () => {
      notifyFeedback({
        tone: "warning",
        title: "知识源已停用",
        description: "停用后该知识源不会再参与检索。",
      });
      await onChanged();
    },
  });
  const enableSource = useMutation({
    mutationFn: () =>
      enableAgentKnowledgeSource(
        agentId,
        source.id,
        { reason: "studio" },
        { admin: requiresAdmin },
      ),
    onSuccess: async () => {
      notifyFeedback({
        tone: "success",
        title: "知识源已启用",
        description: "该知识源已恢复参与检索。",
      });
      await onChanged();
    },
  });
  const archiveSource = useMutation({
    mutationFn: () =>
      archiveAgentKnowledgeSource(
        agentId,
        source.id,
        { reason: "studio" },
        { admin: requiresAdmin },
      ),
    onSuccess: async () => {
      notifyFeedback({
        tone: "warning",
        title: "知识源已归档",
        description: "归档后的知识源会保留历史记录，但不会继续被检索。",
      });
      await onChanged();
    },
  });
  const deleteSource = useMutation({
    mutationFn: () =>
      deleteAgentKnowledgeSource(agentId, source.id, {
        admin: requiresAdmin,
      }),
    onSuccess: async () => {
      notifyFeedback({
        tone: "warning",
        title: "知识源已删除",
        description: `已删除知识源“${source.name}”。`,
      });
      await onDeleted();
    },
  });
  const scopeChange = useMutation({
    mutationFn: () =>
      changeAgentKnowledgeSourceScope(agentId, source.id, {
        scope: source.scope === "org" ? "agent" : "org",
        reason: "studio",
      }),
    onSuccess: async () => {
      notifyFeedback({
        tone: "info",
        title: "知识源作用域已更新",
        description: `当前作用域已切换为${nextScopeLabel}。`,
      });
      await onChanged();
    },
  });

  const confirmArchive = async () => {
    const confirmed = await confirm({
      title: "归档知识源",
      description: "归档后该知识源不会再参与检索，但历史记录会保留。",
      confirmText: "确认归档",
      variant: "danger",
    });
    if (confirmed) {
      archiveSource.mutate();
    }
  };
  const confirmDelete = async () => {
    const confirmed = await confirm({
      title: "永久删除知识源",
      description: `将永久删除“${source.name}”，此操作不可撤销。`,
      confirmText: "确认删除",
      variant: "danger",
    });
    if (confirmed) {
      deleteSource.mutate();
    }
  };
  const confirmScopeChange = async () => {
    const nextScope = source.scope === "org" ? "agent" : "org";
    const nextScopeText = nextScope === "org" ? "组织作用域" : "智能体作用域";
    const confirmed = await confirm({
      title: "切换知识源作用域",
      description: `作用域会改变知识源的可见范围。确认切换为${nextScopeText}吗？`,
      confirmText: "确认切换",
    });
    if (confirmed) {
      scopeChange.mutate();
    }
  };

  return (
    <div className="flex flex-wrap content-start gap-2 rounded-md border border-slate-100 bg-white p-3 md:max-w-56">
      {source.status === "ACTIVE" ? (
        <Button
          type="button"
          onClick={() => disableSource.mutate()}
          disabled={requiresAdmin && !canUseAdminControls}
        >
          <Power className="h-3.5 w-3.5" />
          {text("停用", "Disable")}
        </Button>
      ) : source.status === "DISABLED" ? (
        <Button
          type="button"
          onClick={() => enableSource.mutate()}
          disabled={requiresAdmin && !canUseAdminControls}
        >
          <RotateCcw className="h-3.5 w-3.5" />
          {text("启用", "Enable")}
        </Button>
      ) : null}
      <Button
        type="button"
        variant="secondary"
        onClick={confirmScopeChange}
        disabled={source.status === "ARCHIVED" || scopeChange.isPending || !canUseAdminControls}
      >
        <Shield className="h-3.5 w-3.5" />
        {source.scope === "org" ? "切到智能体" : "切到组织"}
      </Button>
      <Button
        type="button"
        variant="danger"
        onClick={confirmArchive}
        disabled={
          source.status === "ARCHIVED"
          || archiveSource.isPending
          || (requiresAdmin && !canUseAdminControls)
        }
      >
        <Archive className="h-3.5 w-3.5" />
        {text("归档", "Archive")}
      </Button>
      <Button
        type="button"
        variant="danger"
        onClick={confirmDelete}
        disabled={deleteSource.isPending || (requiresAdmin && !canUseAdminControls)}
      >
        <Trash2 className="h-3.5 w-3.5" />
        {text("删除", "Delete")}
      </Button>
      <MutationError
        error={
          disableSource.error
          ?? enableSource.error
          ?? archiveSource.error
          ?? deleteSource.error
          ?? scopeChange.error
        }
      />
      {confirmDialog}
    </div>
  );
}

function KnowledgeDocumentList({
  documents,
  isLoading,
}: {
  documents: KnowledgeDocument[];
  isLoading: boolean;
}) {
  const { text } = useI18n();
  if (isLoading) {
    return <div className="py-3 text-sm text-slate-500">{text("加载中...", "Loading...")}</div>;
  }
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
        <History className="h-4 w-4" />
        {text("版本", "Versions")}
      </div>
      {documents.map((document) => (
        <div key={document.id} className="rounded-md border border-slate-100 bg-white p-3 text-xs">
          <div className="flex items-center justify-between gap-2">
            <span className="truncate font-medium text-slate-900">{document.title}</span>
            <Badge tone={document.status === "INDEXED" ? "success" : "neutral"}>
              v{document.version} · {document.status}
            </Badge>
          </div>
          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-slate-500">
            <span>{document.chunk_count} 个分块</span>
            <span>{formatDateTime(document.indexed_at)}</span>
            <span className="font-mono">{document.content_sha256.slice(0, 10)}</span>
          </div>
          {document.ingestion_error ? (
            <div className="mt-2 text-red-700">{document.ingestion_error}</div>
          ) : null}
        </div>
      ))}
      {!documents.length ? (
        <div className="rounded-md border border-dashed border-slate-200 py-6 text-center text-sm text-slate-500">
          {text("暂无文档。", "No documents yet.")}
        </div>
      ) : null}
    </div>
  );
}

function KnowledgeDocumentIngestDialog({
  agentId,
  source,
  onChanged,
}: {
  agentId: string;
  source: KnowledgeSource;
  onChanged: () => Promise<void>;
}) {
  const { text } = useI18n();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("补充文档");
  const [content, setContent] = useState("");
  const [mimeType, setMimeType] = useState<"text/plain" | "text/markdown">("text/markdown");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    setTitle("补充文档");
    setContent("");
    setMimeType("text/markdown");
    setSelectedFile(null);
    setFileError(null);
  }, [open, source.id]);

  const addDocument = useMutation({
    mutationFn: () => {
      if (selectedFile) {
        return importAgentKnowledgeDocumentFile(agentId, source.id, selectedFile, { title });
      }
      return createAgentKnowledgeDocument(agentId, source.id, {
        title,
        content,
        mime_type: mimeType,
      });
    },
    onSuccess: async () => {
      notifyFeedback({
        tone: "success",
        title: text("文档已添加", "Document added"),
        description: text(
          `知识源“${source.name}”已收到新文档并开始索引。`,
          `A new document was added to ${source.name} and indexing has started.`,
        ),
      });
      await onChanged();
      setOpen(false);
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("文档添加失败", "Document add failed"),
        description: feedbackErrorMessage(
          error,
          text("请检查文档标题、内容或导入文件格式。", "Check the title, content, or imported file format."),
        ),
      });
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    addDocument.mutate();
  };

  const importFile = async (file: File | undefined) => {
    if (!file) {
      return;
    }
    try {
      const imported = await readKnowledgeFile(file);
      setSelectedFile(file);
      setTitle(imported.title);
      setContent(imported.content);
      setMimeType(imported.mimeType);
      setFileError(null);
    } catch (error) {
      setSelectedFile(null);
      setFileError(error instanceof Error ? error.message : "文件导入失败");
    }
  };

  return (
    <>
      <Button type="button" variant="secondary" className="w-full" onClick={() => setOpen(true)}>
        <FilePlus2 className="h-3.5 w-3.5" />
        {text("新增文档", "Add Document")}
      </Button>
      {open ? (
        <KnowledgeModal
          title={text("新增文档", "Add Document")}
          description={source.name}
          onClose={() => setOpen(false)}
        >
          <form className="space-y-4" onSubmit={submit}>
            <label className="space-y-1.5 text-xs font-medium text-slate-600">
              {text("标题", "Title")}
              <Input
                aria-label={text("新增文档标题", "New document title")}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
              />
            </label>
            <label className="space-y-1.5 text-xs font-medium text-slate-600">
              {text("内容", "Content")}
              <Textarea
                aria-label={text("新增文档内容", "New document content")}
                value={content}
                onChange={(event) => setContent(event.target.value)}
                className="min-h-40"
              />
            </label>
            <label className="inline-flex h-9 w-fit cursor-pointer items-center justify-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-50">
              <Upload className="h-3.5 w-3.5" />
              {text("导入 .txt / .md", "Import .txt / .md")}
              <input
                aria-label={text("导入新增文档文件", "Import new document file")}
                className="sr-only"
                type="file"
                accept={knowledgeFileAccept}
                onChange={(event) => importFile(event.target.files?.[0])}
              />
            </label>
            {fileError ? <div className="text-xs text-red-700">{fileError}</div> : null}
            <MutationError error={addDocument.error} />
            <div className="flex items-center justify-end gap-2 border-t border-slate-100 pt-4">
              <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
                {text("取消", "Cancel")}
              </Button>
              <Button
                type="submit"
                variant="primary"
                disabled={addDocument.isPending || !title.trim() || !content.trim()}
              >
                <Plus className="h-3.5 w-3.5" />
                {text("添加", "Add")}
              </Button>
            </div>
          </form>
        </KnowledgeModal>
      ) : null}
    </>
  );
}

function KnowledgeDocumentVersionHistory({
  agentId,
  source,
  documents,
  onChanged,
}: {
  agentId: string;
  source: KnowledgeSource;
  documents: KnowledgeDocument[];
  onChanged: () => Promise<void>;
}) {
  const { text } = useI18n();
  const indexedDocuments = useMemo(
    () => documents.filter((document) => document.status === "INDEXED"),
    [documents],
  );
  const [open, setOpen] = useState(false);
  const [documentId, setDocumentId] = useState(indexedDocuments[0]?.id ?? "");
  const [title, setTitle] = useState(indexedDocuments[0]?.title ?? "");
  const [content, setContent] = useState("");
  const [mimeType, setMimeType] = useState<"text/plain" | "text/markdown">("text/markdown");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const { confirm, confirmDialog } = useConfirmDialog();

  useEffect(() => {
    if (!open) {
      return;
    }
    const activeDocument = indexedDocuments[0];
    setDocumentId(activeDocument?.id ?? "");
    setTitle(activeDocument?.title ?? "");
    setContent("");
    setMimeType("text/markdown");
    setSelectedFile(null);
    setFileError(null);
  }, [indexedDocuments, open, source.id]);

  useEffect(() => {
    const activeDocument = indexedDocuments[0];
    if (!activeDocument) {
      setDocumentId("");
      setTitle("");
      return;
    }
    if (activeDocument && !indexedDocuments.some((document) => document.id === documentId)) {
      setDocumentId(activeDocument.id);
      setTitle(activeDocument.title);
    }
  }, [documentId, indexedDocuments]);

  const reingestDocument = useMutation({
    mutationFn: () => {
      if (selectedFile) {
        return importAgentKnowledgeDocumentVersionFile(
          agentId,
          source.id,
          documentId,
          selectedFile,
          { title },
        );
      }
      return createAgentKnowledgeDocumentVersion(agentId, source.id, documentId, {
        title,
        content,
        mime_type: mimeType,
      });
    },
    onSuccess: async () => {
      notifyFeedback({
        tone: "success",
        title: text("文档新版本已创建", "Document version created"),
        description: text(
          `知识源“${source.name}”的重新导入已完成。`,
          `Reingest completed for ${source.name}.`,
        ),
      });
      await onChanged();
      setOpen(false);
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("重新导入失败", "Reingest failed"),
        description: feedbackErrorMessage(
          error,
          text("请检查文档选择、标题、内容或导入文件。", "Check the selected document, title, content, or imported file."),
        ),
      });
    },
  });

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const confirmed = await confirm({
      title: "重新导入文档",
      description: "重新导入会创建新版本，并保留旧版本历史。",
      confirmText: "确认创建版本",
    });
    if (confirmed) {
      reingestDocument.mutate();
    }
  };

  const importFile = async (file: File | undefined) => {
    if (!file) {
      return;
    }
    try {
      const imported = await readKnowledgeFile(file);
      setSelectedFile(file);
      setTitle(imported.title);
      setContent(imported.content);
      setMimeType(imported.mimeType);
      setFileError(null);
    } catch (error) {
      setSelectedFile(null);
      setFileError(error instanceof Error ? error.message : "文件导入失败");
    }
  };

  return (
    <>
      <Button
        type="button"
        variant="secondary"
        className="w-full"
        disabled={indexedDocuments.length === 0}
        onClick={() => setOpen(true)}
      >
        <RefreshCw className="h-3.5 w-3.5" />
        {text("重新导入", "Reingest")}
      </Button>
      {open ? (
        <KnowledgeModal
          title={text("重新导入", "Reingest")}
          description={text("重新导入会创建新版本。", "Reingest creates a new version.")}
          onClose={() => setOpen(false)}
        >
          <form className="space-y-4" onSubmit={submit}>
            <div className="space-y-1.5 text-xs font-medium text-slate-600">
              <span>{text("文档", "Document")}</span>
              <MenuSelect
                ariaLabel={text("选择重新导入文档", "Select document to reingest")}
                value={documentId}
                onChange={(nextId) => {
                  setDocumentId(nextId);
                  setTitle(indexedDocuments.find((document) => document.id === nextId)?.title ?? "");
                  setSelectedFile(null);
                  setContent("");
                }}
                placeholder={text("暂无可选文档", "No documents available")}
                className="w-full"
                buttonClassName="h-9 rounded-md px-3 py-2 shadow-none"
                menuClassName="w-full"
                disabled={indexedDocuments.length === 0}
                options={indexedDocuments.map((document) => ({
                  value: document.id,
                  label: document.title,
                  description: text(`版本 ${document.version}`, `Version ${document.version}`),
                  meta: `v${document.version}`,
                }))}
              />
            </div>
            <label className="space-y-1.5 text-xs font-medium text-slate-600">
              {text("标题", "Title")}
              <Input
                aria-label={text("重新导入标题", "Reingest title")}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
              />
            </label>
            <label className="space-y-1.5 text-xs font-medium text-slate-600">
              {text("内容", "Content")}
              <Textarea
                aria-label={text("重新导入内容", "Reingest content")}
                value={content}
                onChange={(event) => setContent(event.target.value)}
                className="min-h-40"
              />
            </label>
            <label className="inline-flex h-9 w-fit cursor-pointer items-center justify-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-50">
              <Upload className="h-3.5 w-3.5" />
              {text("导入 .txt / .md", "Import .txt / .md")}
              <input
                aria-label={text("导入重新导入文件", "Import reingest file")}
                className="sr-only"
                type="file"
                accept={knowledgeFileAccept}
                onChange={(event) => importFile(event.target.files?.[0])}
              />
            </label>
            {fileError ? <div className="text-xs text-red-700">{fileError}</div> : null}
            <MutationError error={reingestDocument.error} />
            <div className="flex items-center justify-end gap-2 border-t border-slate-100 pt-4">
              <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
                {text("取消", "Cancel")}
              </Button>
              <Button
                type="submit"
                variant="primary"
                disabled={reingestDocument.isPending || !documentId || !title.trim() || !content.trim()}
              >
                <RefreshCw className="h-3.5 w-3.5" />
                {text("创建版本", "Create Version")}
              </Button>
            </div>
          </form>
        </KnowledgeModal>
      ) : null}
      {confirmDialog}
    </>
  );
}

function KnowledgeModal({
  title,
  description,
  open = true,
  onClose,
  children,
}: {
  title: string;
  description?: string;
  open?: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <ConfigDialog open={open} title={title} description={description} onClose={onClose} className="max-w-2xl">
      {children}
    </ConfigDialog>
  );
}

function ReadOnlyField({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] font-medium text-slate-400">{label}</div>
      <div className={`mt-1 truncate text-xs font-medium text-slate-700 ${mono ? "font-mono" : ""}`}>
        {value || "未提供"}
      </div>
    </div>
  );
}

function KnowledgeStatusBadge({ status }: { status: string }) {
  const { text } = useI18n();
  const tone: BadgeTone =
    status === "ACTIVE" ? "success" : status === "ARCHIVED" ? "neutral" : "warning";
  const label =
    status === "ACTIVE"
      ? text("已启用", "Active")
      : status === "ARCHIVED"
        ? text("已归档", "Archived")
        : status === "DISABLED"
          ? text("已停用", "Disabled")
          : status;
  return <Badge tone={tone}>{label}</Badge>;
}

function KnowledgeHealthBadge({ source }: { source: KnowledgeSource }) {
  const { text } = useI18n();
  const tone: BadgeTone =
    source.health_status === "HEALTHY"
      ? "success"
      : source.health_status === "ERROR"
        ? "failed"
        : "warning";
  const label =
    source.health_status === "HEALTHY"
      ? text("健康", "Healthy")
      : source.health_status === "ERROR"
        ? text("异常", "Error")
        : source.health_status === "DEGRADED"
          ? text("降级", "Degraded")
          : source.health_status;
  return <Badge tone={tone}>{label}</Badge>;
}

function KnowledgeScopeBadge({ source }: { source: KnowledgeSource }) {
  const { text } = useI18n();
  return (
    <Badge tone={source.scope === "org" ? "purple" : "info"}>
      {source.scope === "org" ? <Lock className="h-3 w-3" /> : <Shield className="h-3 w-3" />}
      {source.scope === "org" ? text("组织", "Org") : text("智能体", "Agent")}
    </Badge>
  );
}

function KnowledgeConnectorBadge({ source }: { source: KnowledgeSource }) {
  const provider = source.connector_provider ?? connectorProviderFromSettings(source);
  if (!provider || provider === "uploaded_file" || source.source_type !== "connector") {
    return null;
  }
  const releaseState =
    source.connector_release_state ?? connectorReleaseStateFromSettings(source);
  const tone: BadgeTone =
    releaseState === "usable"
      ? "success"
      : releaseState === "configured-but-unavailable"
        ? "warning"
        : "pending";
  return (
    <Badge tone={tone}>
      <Cable className="h-3 w-3" />
      {connectorProviderLabel(provider)}
      <span className="sr-only">{provider}</span>
    </Badge>
  );
}

function KnowledgeConnectorValidationBadge({ source }: { source: KnowledgeSource }) {
  if (source.source_type !== "connector") {
    return null;
  }
  const status = source.connector_validation_status ?? "ready";
  const tone: BadgeTone =
    status === "ready"
      ? "success"
      : status === "invalid"
        ? "failed"
        : status === "configured"
          ? "warning"
          : "pending";
  return <Badge tone={tone}>{status}</Badge>;
}

function connectorProviderFromSettings(source: KnowledgeSource) {
  const value =
    source.settings_json.connector_provider ??
    source.settings_json.provider ??
    source.metadata_json.connector_provider;
  return typeof value === "string" ? value : "";
}

function connectorReleaseStateFromSettings(source: KnowledgeSource) {
  const value =
    source.settings_json.connector_release_state ??
    source.settings_json.release_state ??
    source.metadata_json.connector_release_state;
  return typeof value === "string" ? value : "";
}

function stringSetting(source: KnowledgeSource, key: string) {
  const value = source.settings_json[key] ?? source.metadata_json[key];
  return typeof value === "string" ? value : "";
}

function connectorProviderLabel(provider: string) {
  const labels: Record<string, string> = {
    coze: "Coze",
    dify: "Dify",
    langchain: "LangChain Retriever",
    ragflow: "RAGFlow",
    local_dify: "Local Dify",
    local_ragflow: "Local RAGFlow",
  };
  return labels[provider] ?? (provider || "connector");
}

function connectorDefaultEndpoint(provider: string) {
  const preset = connectorPresets.find((item) => item.id === provider);
  return preset?.placeholder ?? "https://api.example";
}

function connectorDefaultSecretRef(provider: string) {
  const preset = connectorPresets.find((item) => item.id === provider);
  return preset?.secretPlaceholder ?? "secret://provider";
}

function connectorReferenceRequired(provider: string) {
  return provider === "coze" || provider === "dify" || provider === "ragflow";
}

function endpointIncludesUserinfo(value: string) {
  return /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\/[^/@]+@/.test(value.trim());
}

function looksLikeRawSecretRef(value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    return false;
  }
  if (/^(secret|env):\/\//i.test(trimmed)) {
    return false;
  }
  if (/^[A-Z][A-Z0-9_]{2,}$/.test(trimmed)) {
    return false;
  }
  if (/(token|secret|apikey|api_key)/i.test(trimmed)) {
    return true;
  }
  return trimmed.length >= 24 && /^[A-Za-z0-9._=-]+$/.test(trimmed);
}

function MutationError({ error }: { error: unknown }) {
  if (!error) {
    return null;
  }
  return (
    <div role="alert" className="text-xs text-red-700">
      {error instanceof Error ? error.message : "Request failed"}
    </div>
  );
}

function formatDateTime(value: string | null) {
  if (!value) {
    return "n/a";
  }
  return new Intl.DateTimeFormat(undefined, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}
