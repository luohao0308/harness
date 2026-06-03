import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { KnowledgeManagementPanel } from "../components/KnowledgeManagementPanel";
import type { KnowledgeDocument, KnowledgeSource } from "../../tasks/api";

const apiBaseUrl = "http://127.0.0.1:8000";

function document(overrides: Partial<KnowledgeDocument> = {}): KnowledgeDocument {
  const base: KnowledgeDocument = {
    id: "doc-1",
    source_id: "source-1",
    organization_id: "org-1",
    agent_id: "default",
    title: "Engineering Manual",
    uri: "local://engineering-manual",
    content_sha256: "0123456789abcdef",
    mime_type: "text/markdown",
    status: "INDEXED",
    version: 1,
    logical_document_id: "logical-doc-1",
    supersedes_document_id: null,
    superseded_at: null,
    ingestion_error: null,
    metadata_json: {},
    idempotency_key: null,
    created_by: "user-1",
    created_at: "2026-05-17T08:00:00Z",
    updated_at: "2026-05-17T08:00:00Z",
    indexed_at: "2026-05-17T08:00:00Z",
    chunk_count: 3,
  };
  return Object.assign(base, overrides);
}

function source(overrides: Partial<KnowledgeSource> = {}): KnowledgeSource {
  const latestDocument = document();
  const base: KnowledgeSource = {
    id: "source-1",
    organization_id: "org-1",
    agent_id: "default",
    name: "Team Knowledge",
    description: "Runbook and operating notes",
    source_type: "markdown",
    status: "ACTIVE",
    version: 1,
    scope: "agent",
    expires_at: null,
    disabled_at: null,
    archived_at: null,
    last_indexed_at: "2026-05-17T08:00:00Z",
    last_ingestion_error: null,
    health_status: "HEALTHY",
    connector_provider: "uploaded_file",
    connector_release_state: "usable",
    connector_counts_toward_complete_usable: true,
    settings_json: {},
    metadata_json: {},
    idempotency_key: null,
    created_by: "user-1",
    created_at: "2026-05-17T08:00:00Z",
    updated_at: "2026-05-17T08:00:00Z",
    latest_documents: [latestDocument],
  };
  return Object.assign(base, overrides);
}

function renderPanel(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <KnowledgeManagementPanel agentId="default" />
    </QueryClientProvider>,
  );
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function requestPath(input: RequestInfo | URL) {
  const url = String(input);
  return new URL(url.startsWith("http") ? url : `${apiBaseUrl}${url}`).pathname;
}

function setupFetchWith(sampleSource: KnowledgeSource, documents: KnowledgeDocument[]) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = requestPath(input);
    if (path === "/api/agents/default/knowledge/sources" && !init?.method) {
      return jsonResponse({ items: [sampleSource], next_cursor: null });
    }
    if (path === "/api/agents/default/knowledge/sources/source-1/documents" && !init?.method) {
      return jsonResponse(documents);
    }
    if (path.startsWith("/api/agents/default/knowledge/sources/source-1")) {
      return jsonResponse(sampleSource);
    }
    return jsonResponse({ detail: `unexpected request ${path}` }, 404);
  });
}

function setupFetch() {
  return setupFetchWith(source(), [
    document(),
    document({ id: "doc-0", status: "SUPERSEDED", version: 0 }),
  ]);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("KnowledgeManagementPanel", () => {
  it("renders source lifecycle, health, scope, and document versions", async () => {
    renderPanel(setupFetch());

    expect(await screen.findByText("Team Knowledge")).toBeInTheDocument();
    expect(screen.getAllByText("ACTIVE").length).toBeGreaterThan(0);
    expect(screen.getAllByText("HEALTHY").length).toBeGreaterThan(0);
    expect(screen.getAllByText("agent").length).toBeGreaterThan(0);
    await screen.findAllByText("Engineering Manual");
    expect(screen.getAllByText("Engineering Manual").length).toBeGreaterThan(0);
    expect(await screen.findByText("v1 · INDEXED", { selector: "span" })).toBeInTheDocument();
    expect(screen.getAllByText("0123456789").length).toBeGreaterThan(0);
  });

  it("confirms archive and scope changes before calling lifecycle APIs", async () => {
    const user = userEvent.setup();
    const fetchMock = setupFetch();
    const confirm = vi.fn(() => true);
    vi.stubGlobal("confirm", confirm);
    renderPanel(fetchMock);

    await screen.findByText("Team Knowledge");
    await user.click(screen.getByRole("button", { name: /归档/ }));
    await user.click(screen.getByRole("button", { name: "org" }));

    await waitFor(() => {
      const requestedPaths = fetchMock.mock.calls.map(([input]) => requestPath(input));
      expect(requestedPaths).toContain(
        "/api/agents/default/knowledge/sources/source-1/archive",
      );
      expect(requestedPaths).toContain(
        "/api/agents/default/knowledge/sources/source-1/scope",
      );
    });
    expect(confirm).toHaveBeenCalledTimes(2);
    const scopeCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/scope"));
    expect(JSON.parse(String(scopeCall?.[1]?.body))).toMatchObject({ scope: "org" });
    expect(scopeCall?.[1]?.headers).toMatchObject({
      Authorization: "Bearer dev-admin-token",
    });
  });

  it("confirms permanent deletion before removing a knowledge source", async () => {
    const user = userEvent.setup();
    let deleted = false;
    const confirm = vi.fn(() => true);
    vi.stubGlobal("confirm", confirm);
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/agents/default/knowledge/sources" && !init?.method) {
        return jsonResponse({ items: deleted ? [] : [source()], next_cursor: null });
      }
      if (
        path === "/api/agents/default/knowledge/sources/source-1"
        && init?.method === "DELETE"
      ) {
        deleted = true;
        return new Response(null, { status: 204 });
      }
      if (path === "/api/agents/default/knowledge/sources/source-1/documents" && !init?.method) {
        return jsonResponse(deleted ? [] : [document()]);
      }
      return jsonResponse({ detail: `unexpected request ${path}` }, 404);
    });
    renderPanel(fetchMock);

    await screen.findByText("Team Knowledge");
    await user.click(screen.getByRole("button", { name: "删除" }));

    await waitFor(() => {
      const deleteCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/agents/default/knowledge/sources/source-1"
          && init?.method === "DELETE",
      );
      expect(deleteCall).toBeDefined();
    });
    expect(confirm).toHaveBeenCalledWith("确定永久删除该知识源？此操作不可撤销。");
    await waitFor(() => {
      expect(screen.getAllByText("暂无知识源。").length).toBeGreaterThan(0);
    });
  });

  it("posts add-document and document-version requests from the management surface", async () => {
    const user = userEvent.setup();
    const fetchMock = setupFetch();
    vi.stubGlobal("confirm", vi.fn(() => true));
    renderPanel(fetchMock);

    await screen.findByText("Team Knowledge");
    await user.click(screen.getByRole("button", { name: /新增文档/ }));
    await user.type(screen.getByLabelText("新增文档内容"), "Additional markdown notes");
    await user.click(screen.getByRole("button", { name: /添加/ }));

    await user.click(screen.getByRole("button", { name: /重新导入/ }));
    await user.type(screen.getByLabelText("重新导入内容"), "Updated manual v2");
    await user.click(screen.getByRole("button", { name: /创建版本/ }));

    await waitFor(() => {
      const requestedPaths = fetchMock.mock.calls.map(([input]) => requestPath(input));
      expect(requestedPaths).toContain(
        "/api/agents/default/knowledge/sources/source-1/documents",
      );
      expect(requestedPaths).toContain(
        "/api/agents/default/knowledge/sources/source-1/documents/doc-1/versions",
      );
    });
    const addDocumentCall = fetchMock.mock.calls.find(
      ([input, init]) => String(input).endsWith("/documents") && init?.method === "POST",
    );
    expect(JSON.parse(String(addDocumentCall?.[1]?.body))).toMatchObject({
      title: "补充文档",
      content: "Additional markdown notes",
    });
  });

  it("imports a text file into the add-document form before posting", async () => {
    const user = userEvent.setup();
    const fetchMock = setupFetch();
    renderPanel(fetchMock);

    await screen.findByText("Team Knowledge");
    await user.click(screen.getByRole("button", { name: /新增文档/ }));
    await user.upload(
      screen.getByLabelText("导入新增文档文件"),
      new File(["plain file notes"], "ops-notes.txt", { type: "text/plain" }),
    );
    await waitFor(() => {
      expect(screen.getByLabelText("新增文档标题")).toHaveValue("ops-notes");
      expect(screen.getByLabelText("新增文档内容")).toHaveValue("plain file notes");
    });
    await user.click(screen.getByRole("button", { name: /添加/ }));

    await waitFor(() => {
      const addDocumentCall = fetchMock.mock.calls.find(
        ([input, init]) => String(input).endsWith("/documents/import") && init?.method === "POST",
      );
      const body = addDocumentCall?.[1]?.body as FormData;
      expect(body.get("title")).toBe("ops-notes");
      expect((body.get("file") as File).name).toBe("ops-notes.txt");
    });
  });

  it("rejects unsupported add-document file imports before posting", async () => {
    const user = userEvent.setup();
    const fetchMock = setupFetch();
    renderPanel(fetchMock);

    await screen.findByText("Team Knowledge");
    await user.click(screen.getByRole("button", { name: /新增文档/ }));
    fireEvent.change(screen.getByLabelText("导入新增文档文件"), {
      target: {
        files: [new File(["%PDF-1.7"], "contract.pdf", { type: "application/pdf" })],
      },
    });

    expect(await screen.findByText("仅支持 .txt / .md 文件")).toBeInTheDocument();
    expect(screen.getByLabelText("新增文档内容")).toHaveValue("");
    expect(screen.getByRole("button", { name: /添加/ })).toBeDisabled();
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) => String(input).endsWith("/documents") && init?.method === "POST",
      ),
    ).toBe(false);
  });

  it("rejects oversized add-document file imports before posting", async () => {
    const user = userEvent.setup();
    const fetchMock = setupFetch();
    renderPanel(fetchMock);

    await screen.findByText("Team Knowledge");
    await user.click(screen.getByRole("button", { name: /新增文档/ }));
    await user.upload(
      screen.getByLabelText("导入新增文档文件"),
      new File(["x".repeat(120_001)], "too-large.md", { type: "text/markdown" }),
    );

    expect(await screen.findByText("文件不能超过 120KB")).toBeInTheDocument();
    expect(screen.getByLabelText("新增文档标题")).toHaveValue("补充文档");
    expect(screen.getByLabelText("新增文档内容")).toHaveValue("");
    expect(screen.getByRole("button", { name: /添加/ })).toBeDisabled();
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) => String(input).endsWith("/documents") && init?.method === "POST",
      ),
    ).toBe(false);
  });

  it("disables reingest when the selected source has no indexed documents", async () => {
    renderPanel(setupFetchWith(source({ latest_documents: [] }), []));

    await screen.findByText("Team Knowledge");

    expect(screen.getByRole("button", { name: /重新导入/ })).toBeDisabled();
  });

  it("creates an external API connector from a built-in preset", async () => {
    const user = userEvent.setup();
    const createdSource = source({
      id: "connector-1",
      name: "Coze 知识库",
      source_type: "connector",
      connector_provider: "coze",
      connector_release_state: "usable",
      connector_counts_toward_complete_usable: true,
      settings_json: {
        connector_provider: "coze",
        connector_release_state: "usable",
      },
      latest_documents: [document({ source_id: "connector-1" })],
    });
    let connectorCreated = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/agents/default/knowledge/sources" && !init?.method) {
        return jsonResponse({
          items: connectorCreated ? [createdSource] : [],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/default/knowledge/sources" && init?.method === "POST") {
        connectorCreated = true;
        return jsonResponse(createdSource, 201);
      }
      if (path === "/api/agents/default/knowledge/sources/connector-1/documents" && !init?.method) {
        return jsonResponse(createdSource.latest_documents);
      }
      return jsonResponse({ detail: `unexpected request ${path}` }, 404);
    });
    renderPanel(fetchMock);

    await screen.findByText("暂无知识源。");
    await user.click(screen.getByRole("button", { name: "外部 API" }));
    await user.click(screen.getByRole("button", { name: /Coze/ }));
    await user.clear(screen.getByLabelText("数据集或空间 ID"));
    await user.type(screen.getByLabelText("数据集或空间 ID"), "space-123");
    await user.click(screen.getByRole("button", { name: /保存配置/ }));

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/agents/default/knowledge/sources" && init?.method === "POST",
      );
      expect(createCall).toBeDefined();
      expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
        name: "Coze 知识库",
        source_type: "connector",
        uri: "https://api.coze.cn",
        connector_settings_json: {
          provider: "coze",
          endpoint: "https://api.coze.cn",
          secret_ref: "secret://coze",
          dataset_id: "space-123",
          release_state: "usable",
        },
      });
    });
    expect((await screen.findAllByText("Coze 知识库")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("coze").length).toBeGreaterThan(0);
  });

  it("stores a Coze API key through the server-side connector secret field", async () => {
    const user = userEvent.setup();
    const createdSource = source({
      id: "connector-1",
      name: "Coze 知识库",
      source_type: "connector",
      connector_provider: "coze",
      connector_release_state: "usable",
      connector_counts_toward_complete_usable: true,
      connector_secret_configured: true,
      settings_json: {
        connector_provider: "coze",
        connector_release_state: "usable",
        secret_ref: "secret://coze",
      },
      latest_documents: [document({ source_id: "connector-1" })],
    });
    let connectorCreated = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/agents/default/knowledge/sources" && !init?.method) {
        return jsonResponse({
          items: connectorCreated ? [createdSource] : [],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/default/knowledge/sources" && init?.method === "POST") {
        connectorCreated = true;
        return jsonResponse(createdSource, 201);
      }
      if (path === "/api/agents/default/knowledge/sources/connector-1/documents" && !init?.method) {
        return jsonResponse(createdSource.latest_documents);
      }
      return jsonResponse({ detail: `unexpected request ${path}` }, 404);
    });
    renderPanel(fetchMock);

    await screen.findByText("暂无知识源。");
    await user.click(screen.getByRole("button", { name: "外部 API" }));
    await user.click(screen.getByRole("button", { name: /Coze/ }));
    await user.clear(screen.getByLabelText("数据集或空间 ID"));
    await user.type(screen.getByLabelText("数据集或空间 ID"), "dataset-123");
    await user.type(screen.getByLabelText("API Key 密钥值"), "frontend-coze-key");
    await user.click(screen.getByRole("button", { name: /保存配置/ }));

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/agents/default/knowledge/sources" && init?.method === "POST",
      );
      expect(createCall).toBeDefined();
      expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
        source_type: "connector",
        connector_secret_value: "frontend-coze-key",
        connector_settings_json: {
          provider: "coze",
          endpoint: "https://api.coze.cn",
          secret_ref: "secret://coze",
          dataset_id: "dataset-123",
        },
      });
    });
    expect(await screen.findByText("已配置")).toBeInTheDocument();
  });

  it("stores a Dify API key through the server-side connector secret field", async () => {
    const user = userEvent.setup();
    const createdSource = source({
      id: "connector-1",
      name: "Dify 知识库",
      source_type: "connector",
      connector_provider: "dify",
      connector_release_state: "usable",
      connector_counts_toward_complete_usable: true,
      connector_secret_configured: true,
      settings_json: {
        connector_provider: "dify",
        connector_release_state: "usable",
        secret_ref: "secret://dify",
      },
      latest_documents: [document({ source_id: "connector-1" })],
    });
    let connectorCreated = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/agents/default/knowledge/sources" && !init?.method) {
        return jsonResponse({
          items: connectorCreated ? [createdSource] : [],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/default/knowledge/sources" && init?.method === "POST") {
        connectorCreated = true;
        return jsonResponse(createdSource, 201);
      }
      if (path === "/api/agents/default/knowledge/sources/connector-1/documents" && !init?.method) {
        return jsonResponse(createdSource.latest_documents);
      }
      return jsonResponse({ detail: `unexpected request ${path}` }, 404);
    });
    renderPanel(fetchMock);

    await screen.findByText("暂无知识源。");
    await user.click(screen.getByRole("button", { name: "外部 API" }));
    await user.clear(screen.getByLabelText("数据集或空间 ID"));
    await user.type(screen.getByLabelText("数据集或空间 ID"), "dataset-123");
    await user.type(screen.getByLabelText("API Key 密钥值"), "frontend-dify-key");
    await user.click(screen.getByRole("button", { name: /保存配置/ }));

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/agents/default/knowledge/sources" && init?.method === "POST",
      );
      expect(createCall).toBeDefined();
      expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
        source_type: "connector",
        connector_secret_value: "frontend-dify-key",
        connector_settings_json: {
          provider: "dify",
          endpoint: "https://api.dify.ai/v1",
          secret_ref: "secret://dify",
          dataset_id: "dataset-123",
        },
      });
    });
    expect(await screen.findByText("已配置")).toBeInTheDocument();
  });

  it("edits connector endpoint, secret ref, dataset id, and replacement key from the edit dialog", async () => {
    const user = userEvent.setup();
    const connectorSource = source({
      id: "connector-1",
      name: "Coze 知识库",
      description: "Coze API 接入配置",
      source_type: "connector",
      connector_provider: "coze",
      connector_release_state: "usable",
      connector_counts_toward_complete_usable: true,
      connector_validation_status: "ready",
      connector_secret_configured: true,
      settings_json: {
        connector_provider: "coze",
        connector_release_state: "usable",
        provider: "coze",
        endpoint: "https://api.coze.cn",
        secret_ref: "secret://coze",
        dataset_id: "7618108220116893732",
      },
      latest_documents: [document({ source_id: "connector-1" })],
    });
    let currentSource = connectorSource;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/agents/default/knowledge/sources" && !init?.method) {
        return jsonResponse({ items: [currentSource], next_cursor: null });
      }
      if (path === "/api/agents/default/knowledge/sources/connector-1/documents" && !init?.method) {
        return jsonResponse(currentSource.latest_documents);
      }
      if (
        path === "/api/agents/default/knowledge/sources/connector-1"
        && init?.method === "PATCH"
      ) {
        const payload = JSON.parse(String(init.body));
        currentSource = {
          ...currentSource,
          name: payload.name,
          description: payload.description,
          settings_json: {
            ...currentSource.settings_json,
            ...payload.connector_settings_json,
          },
        };
        return jsonResponse(currentSource);
      }
      return jsonResponse({ detail: `unexpected request ${path}` }, 404);
    });
    renderPanel(fetchMock);

    await screen.findByText("Coze 知识库");
    await user.click(screen.getByRole("button", { name: "编辑" }));

    expect(await screen.findByText("编辑外部知识库接入")).toBeInTheDocument();
    expect(screen.getByText(/\/knowledge\/ 后面的 ID/)).toBeInTheDocument();
    expect(screen.getByLabelText("编辑 API Endpoint")).toHaveValue("https://api.coze.cn");
    expect(screen.getByLabelText("编辑 Secret Ref")).toHaveValue("secret://coze");
    expect(screen.getByLabelText("编辑数据集或知识库 ID")).toHaveValue(
      "7618108220116893732",
    );

    await user.clear(screen.getByLabelText("编辑数据集或知识库 ID"));
    await user.type(screen.getByLabelText("编辑数据集或知识库 ID"), "7629341424630448134");
    await user.type(screen.getByLabelText("替换 API Key"), "new-coze-api-key");
    await user.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => {
      const updateCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/agents/default/knowledge/sources/connector-1"
          && init?.method === "PATCH",
      );
      expect(updateCall).toBeDefined();
      expect(JSON.parse(String(updateCall?.[1]?.body))).toMatchObject({
        name: "Coze 知识库",
        description: "Coze API 接入配置",
        connector_secret_value: "new-coze-api-key",
        connector_settings_json: {
          provider: "coze",
          endpoint: "https://api.coze.cn",
          secret_ref: "secret://coze",
          dataset_id: "7629341424630448134",
        },
      });
    });
  });

  it("rejects raw API keys in connector secret reference", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/agents/default/knowledge/sources" && !init?.method) {
        return jsonResponse({ items: [], next_cursor: null });
      }
      return jsonResponse({ detail: `unexpected request ${path}` }, 404);
    });
    renderPanel(fetchMock);

    await screen.findByText("暂无知识源。");
    await user.click(screen.getByRole("button", { name: "外部 API" }));
    const secretRef = screen.getByLabelText("密钥引用");
    await user.clear(secretRef);
    await user.type(secretRef, "dataset-NAyAfpTA8FHF6fNktg2F7RnI");

    expect(
      await screen.findByText(/这里填写引用名/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /保存配置/ })).toBeDisabled();
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          requestPath(input) === "/api/agents/default/knowledge/sources" && init?.method === "POST",
      ),
    ).toBe(false);
  });
});
