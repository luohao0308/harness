import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  Database,
  FilePlus2,
  History,
  Lock,
  Plus,
  Power,
  RefreshCw,
  RotateCcw,
  Save,
  Shield,
  Upload,
} from "lucide-react";

import { Badge, type BadgeTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { Input, Textarea } from "../../../components/ui/input";
import { useI18n } from "../../../lib/i18n";
import {
  archiveAgentKnowledgeSource,
  changeAgentKnowledgeSourceScope,
  createAgentKnowledgeDocument,
  createAgentKnowledgeDocumentVersion,
  createAgentKnowledgeSource,
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
};

const queryKeyForSources = (agentId: string) => ["agent-knowledge", agentId] as const;
const queryKeyForDocuments = (agentId: string, sourceId: string | null) =>
  ["agent-knowledge-documents", agentId, sourceId] as const;
const knowledgeFileAccept = ".txt,.md,text/plain,text/markdown";
const knowledgeFileMaxBytes = 120_000;

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

export function KnowledgeManagementPanel({ agentId }: KnowledgeManagementPanelProps) {
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const sources = useQuery({
    queryKey: queryKeyForSources(agentId),
    queryFn: () => listAgentKnowledgeSources(agentId),
  });
  const selectedSource = useMemo(
    () => sources.data?.items.find((source) => source.id === selectedSourceId) ?? null,
    [selectedSourceId, sources.data?.items],
  );
  const documents = useQuery({
    queryKey: queryKeyForDocuments(agentId, selectedSourceId),
    queryFn: () => listAgentKnowledgeDocuments(agentId, selectedSourceId ?? ""),
    enabled: selectedSourceId !== null,
  });

  useEffect(() => {
    const firstSource = sources.data?.items[0] ?? null;
    if (!sources.data?.items.length) {
      setSelectedSourceId(null);
      return;
    }
    if (!sources.data.items.some((source) => source.id === selectedSourceId)) {
      setSelectedSourceId(firstSource?.id ?? null);
    }
  }, [selectedSourceId, sources.data?.items]);

  const refresh = async (sourceId = selectedSourceId) => {
    await queryClient.invalidateQueries({ queryKey: queryKeyForSources(agentId) });
    if (sourceId) {
      await queryClient.invalidateQueries({
        queryKey: queryKeyForDocuments(agentId, sourceId),
      });
    }
  };

  return (
    <section className="grid grid-cols-12 gap-4">
      <Card className="col-span-12 lg:col-span-4">
        <CardHeader>
          <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
            <Database className="h-4 w-4" />
            {text("知识源", "Knowledge Sources")}
          </div>
          <Badge tone="success">{sources.data?.items.length ?? 0}</Badge>
        </CardHeader>
        <div className="space-y-3 p-3">
          <KnowledgeCreateDialog
            agentId={agentId}
            onCreated={async (source) => {
              setSelectedSourceId(source.id);
              await refresh(source.id);
            }}
          />
          <KnowledgeSourceList
            isLoading={sources.isLoading}
            sources={sources.data?.items ?? []}
            selectedSourceId={selectedSourceId}
            onSelect={setSelectedSourceId}
          />
        </div>
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
            />
          ) : (
            <div className="rounded-md border border-dashed border-slate-200 py-8 text-center text-sm text-slate-500">
              {text("暂无知识源。", "No knowledge sources yet.")}
            </div>
          )}
        </div>
      </Card>
    </section>
  );
}

function KnowledgeCreateDialog({
  agentId,
  onCreated,
}: {
  agentId: string;
  onCreated: (source: KnowledgeSource) => Promise<void>;
}) {
  const { text } = useI18n();
  const [name, setName] = useState("默认知识源");
  const [description, setDescription] = useState("");
  const [scope, setScope] = useState<"agent" | "org">("agent");
  const [title, setTitle] = useState("团队手册");
  const [content, setContent] = useState("# 团队手册\n\n使用简洁、带引用的回答。\n");
  const [mimeType, setMimeType] = useState<"text/plain" | "text/markdown">("text/markdown");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const canCreateOrgScope = KNOWLEDGE_ADMIN_CONTROLS_ENABLED;
  useEffect(() => {
    if (!canCreateOrgScope && scope === "org") {
      setScope("agent");
    }
  }, [canCreateOrgScope, scope]);
  const createSource = useMutation({
    mutationFn: () => {
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
    onSuccess: onCreated,
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

  return (
    <form className="space-y-2" onSubmit={submit}>
      <div className="grid grid-cols-2 gap-2">
        <Input
          aria-label={text("知识源名称", "Knowledge source name")}
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder={text("知识源名称", "Source name")}
        />
        <select
          aria-label={text("知识源作用域", "Knowledge source scope")}
          className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          value={scope}
          onChange={(event) => setScope(event.target.value as "agent" | "org")}
        >
          <option value="agent">agent</option>
          <option value="org" disabled={!canCreateOrgScope}>
            org
          </option>
        </select>
      </div>
      <Input
        aria-label={text("知识源说明", "Knowledge source description")}
        value={description}
        onChange={(event) => setDescription(event.target.value)}
        placeholder={text("说明", "Description")}
      />
      <Input
        aria-label={text("初始文档标题", "Initial document title")}
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        placeholder={text("文档标题", "Document title")}
      />
      <Textarea
        aria-label={text("初始文档内容", "Initial document content")}
        value={content}
        onChange={(event) => setContent(event.target.value)}
      />
      <label className="inline-flex h-8 cursor-pointer items-center justify-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-50">
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
      <Button type="submit" disabled={createSource.isPending || !name.trim() || !content.trim()}>
        <Plus className="h-3.5 w-3.5" />
        {createSource.isPending ? text("索引中", "Indexing") : text("创建", "Create")}
      </Button>
      {fileError ? <div className="text-xs text-red-700">{fileError}</div> : null}
      <MutationError error={createSource.error} />
    </form>
  );
}

function KnowledgeSourceList({
  isLoading,
  sources,
  selectedSourceId,
  onSelect,
}: {
  isLoading: boolean;
  sources: KnowledgeSource[];
  selectedSourceId: string | null;
  onSelect: (sourceId: string) => void;
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
          </div>
        </button>
      ))}
      {!sources.length ? (
        <div className="rounded-md border border-dashed border-slate-200 py-6 text-center text-sm text-slate-500">
          {text("暂无知识源。", "No knowledge sources yet.")}
        </div>
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
}: {
  agentId: string;
  source: KnowledgeSource;
  documents: KnowledgeDocument[];
  documentsLoading: boolean;
  onChanged: () => Promise<void>;
}) {
  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-[1fr_auto]">
        <KnowledgeSourceSummary agentId={agentId} source={source} onChanged={onChanged} />
        <KnowledgeSourceActions agentId={agentId} source={source} onChanged={onChanged} />
      </div>
      <div className="grid gap-3 xl:grid-cols-2">
        <KnowledgeDocumentList documents={documents} isLoading={documentsLoading} />
        <div className="space-y-3">
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
  const [name, setName] = useState(source.name);
  const [description, setDescription] = useState(source.description);

  useEffect(() => {
    setName(source.name);
    setDescription(source.description);
  }, [source.description, source.name]);

  const updateSource = useMutation({
    mutationFn: () =>
      updateAgentKnowledgeSource(agentId, source.id, {
        name,
        description,
      }, { admin: source.scope === "org" }),
    onSuccess: onChanged,
  });

  return (
    <div className="space-y-2 rounded-md border border-slate-100 bg-slate-50 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <KnowledgeStatusBadge status={source.status} />
        <KnowledgeHealthBadge source={source} />
        <span className="font-mono text-[11px] text-slate-500">{source.id}</span>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <Input
          aria-label={text("编辑知识源名称", "Edit knowledge source name")}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <Input
          aria-label={text("编辑知识源说明", "Edit knowledge source description")}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <span>{text("最后索引", "Last indexed")}: {formatDateTime(source.last_indexed_at)}</span>
        {source.last_ingestion_error ? (
          <Badge tone="failed">{source.last_ingestion_error}</Badge>
        ) : null}
      </div>
      <Button
        type="button"
        onClick={() => updateSource.mutate()}
        disabled={updateSource.isPending || !name.trim()}
      >
        <Save className="h-3.5 w-3.5" />
        {text("保存", "Save")}
      </Button>
      <MutationError error={updateSource.error} />
    </div>
  );
}

function KnowledgeSourceActions({
  agentId,
  source,
  onChanged,
}: {
  agentId: string;
  source: KnowledgeSource;
  onChanged: () => Promise<void>;
}) {
  const { text } = useI18n();
  const requiresAdmin = source.scope === "org";
  const canUseAdminControls = KNOWLEDGE_ADMIN_CONTROLS_ENABLED;
  const disableSource = useMutation({
    mutationFn: () =>
      disableAgentKnowledgeSource(
        agentId,
        source.id,
        { reason: "studio" },
        { admin: requiresAdmin },
      ),
    onSuccess: onChanged,
  });
  const enableSource = useMutation({
    mutationFn: () =>
      enableAgentKnowledgeSource(
        agentId,
        source.id,
        { reason: "studio" },
        { admin: requiresAdmin },
      ),
    onSuccess: onChanged,
  });
  const archiveSource = useMutation({
    mutationFn: () =>
      archiveAgentKnowledgeSource(
        agentId,
        source.id,
        { reason: "studio" },
        { admin: requiresAdmin },
      ),
    onSuccess: onChanged,
  });
  const scopeChange = useMutation({
    mutationFn: () =>
      changeAgentKnowledgeSourceScope(agentId, source.id, {
        scope: source.scope === "org" ? "agent" : "org",
        reason: "studio",
      }),
    onSuccess: onChanged,
  });

  const confirmArchive = () => {
    if (window.confirm(text("归档后不会被检索。", "Archived sources are not retrieved."))) {
      archiveSource.mutate();
    }
  };
  const confirmScopeChange = () => {
    if (window.confirm(text("作用域会改变可见范围。", "Scope changes alter visibility."))) {
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
        {source.scope === "org" ? "agent" : "org"}
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
      <MutationError
        error={
          disableSource.error ?? enableSource.error ?? archiveSource.error ?? scopeChange.error
        }
      />
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
            <span>{document.chunk_count} chunks</span>
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
  const [title, setTitle] = useState("补充文档");
  const [content, setContent] = useState("");
  const [mimeType, setMimeType] = useState<"text/plain" | "text/markdown">("text/markdown");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
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
    onSuccess: onChanged,
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
    <form className="space-y-2 rounded-md border border-slate-100 bg-slate-50 p-3" onSubmit={submit}>
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
        <FilePlus2 className="h-4 w-4" />
        {text("新增文档", "Add Document")}
      </div>
      <Input
        aria-label={text("新增文档标题", "New document title")}
        value={title}
        onChange={(event) => setTitle(event.target.value)}
      />
      <Textarea
        aria-label={text("新增文档内容", "New document content")}
        value={content}
        onChange={(event) => setContent(event.target.value)}
      />
      <label className="inline-flex h-8 cursor-pointer items-center justify-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-50">
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
      <Button type="submit" disabled={addDocument.isPending || !title.trim() || !content.trim()}>
        <Plus className="h-3.5 w-3.5" />
        {text("添加", "Add")}
      </Button>
      {fileError ? <div className="text-xs text-red-700">{fileError}</div> : null}
      <MutationError error={addDocument.error} />
    </form>
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
  const [documentId, setDocumentId] = useState(indexedDocuments[0]?.id ?? "");
  const [title, setTitle] = useState(indexedDocuments[0]?.title ?? "");
  const [content, setContent] = useState("");
  const [mimeType, setMimeType] = useState<"text/plain" | "text/markdown">("text/markdown");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  useEffect(() => {
    const activeDocument = indexedDocuments[0];
    setDocumentId(activeDocument?.id ?? "");
    setTitle(activeDocument?.title ?? "");
    setContent("");
    setMimeType("text/markdown");
    setSelectedFile(null);
    setFileError(null);
  }, [source.id]);

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
    onSuccess: onChanged,
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (window.confirm(text("重新导入会创建新版本。", "Reingest creates a new version."))) {
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
    <form className="space-y-2 rounded-md border border-slate-100 bg-white p-3" onSubmit={submit}>
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
        <RefreshCw className="h-4 w-4" />
        {text("重新导入", "Reingest")}
      </div>
      <select
        aria-label={text("选择重新导入文档", "Select document to reingest")}
        className="h-9 w-full rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
        value={documentId}
        onChange={(event) => {
          const nextId = event.target.value;
          setDocumentId(nextId);
          setTitle(indexedDocuments.find((document) => document.id === nextId)?.title ?? "");
          setSelectedFile(null);
          setContent("");
        }}
      >
        {indexedDocuments.map((document) => (
          <option key={document.id} value={document.id}>
            {document.title} · v{document.version}
          </option>
        ))}
      </select>
      <Input
        aria-label={text("重新导入标题", "Reingest title")}
        value={title}
        onChange={(event) => setTitle(event.target.value)}
      />
      <Textarea
        aria-label={text("重新导入内容", "Reingest content")}
        value={content}
        onChange={(event) => setContent(event.target.value)}
      />
      <label className="inline-flex h-8 cursor-pointer items-center justify-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-50">
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
      <Button
        type="submit"
        disabled={reingestDocument.isPending || !documentId || !title.trim() || !content.trim()}
      >
        <RefreshCw className="h-3.5 w-3.5" />
        {text("创建版本", "Create Version")}
      </Button>
      {fileError ? <div className="text-xs text-red-700">{fileError}</div> : null}
      <MutationError error={reingestDocument.error} />
    </form>
  );
}

function KnowledgeStatusBadge({ status }: { status: string }) {
  const tone: BadgeTone =
    status === "ACTIVE" ? "success" : status === "ARCHIVED" ? "neutral" : "warning";
  return <Badge tone={tone}>{status}</Badge>;
}

function KnowledgeHealthBadge({ source }: { source: KnowledgeSource }) {
  const tone: BadgeTone =
    source.health_status === "HEALTHY"
      ? "success"
      : source.health_status === "ERROR"
        ? "failed"
        : "warning";
  return <Badge tone={tone}>{source.health_status}</Badge>;
}

function KnowledgeScopeBadge({ source }: { source: KnowledgeSource }) {
  return (
    <Badge tone={source.scope === "org" ? "purple" : "info"}>
      {source.scope === "org" ? <Lock className="h-3 w-3" /> : <Shield className="h-3 w-3" />}
      {source.scope}
    </Badge>
  );
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
  }).format(new Date(value));
}
