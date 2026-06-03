import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { KnowledgePage } from "../KnowledgePage";
import type { AgentDefinition, KnowledgeDocument, KnowledgeSource } from "../../../tasks/api";

const apiBaseUrl = "http://127.0.0.1:8000";

function agent(overrides: Partial<AgentDefinition> = {}): AgentDefinition {
  return {
    id: "default",
    name: "默认智能体",
    description: "默认入口智能体",
    role: "executor",
    status: "ACTIVE",
    model_provider: "default",
    model_name: "default",
    system_prompt: "",
    tools_json: [],
    routing_tags: [],
    max_parallel_assignments: 1,
    capability_attachments: [],
    created_at: "2026-05-26T00:00:00Z",
    updated_at: "2026-05-26T00:00:00Z",
    ...overrides,
  };
}

function document(overrides: Partial<KnowledgeDocument> = {}): KnowledgeDocument {
  return {
    id: "doc-1",
    source_id: "source-1",
    organization_id: "dev-org",
    agent_id: "default",
    title: "Team Manual",
    uri: "manual.md",
    content_sha256: "abcdef0123456789",
    mime_type: "text/markdown",
    status: "INDEXED",
    version: 1,
    logical_document_id: "logical-doc-1",
    supersedes_document_id: null,
    superseded_at: null,
    ingestion_error: null,
    metadata_json: {},
    idempotency_key: null,
    created_by: "dev-engineer",
    created_at: "2026-05-26T00:00:00Z",
    updated_at: "2026-05-26T00:00:00Z",
    indexed_at: "2026-05-26T00:00:00Z",
    chunk_count: 2,
    ...overrides,
  };
}

function source(overrides: Partial<KnowledgeSource> = {}): KnowledgeSource {
  return {
    id: "source-1",
    organization_id: "dev-org",
    agent_id: "default",
    name: "本地手册",
    description: "Local handbook",
    source_type: "markdown",
    status: "ACTIVE",
    version: 1,
    scope: "agent",
    expires_at: null,
    disabled_at: null,
    archived_at: null,
    last_indexed_at: "2026-05-26T00:00:00Z",
    last_ingestion_error: null,
    health_status: "HEALTHY",
    connector_provider: "uploaded_file",
    connector_release_state: "usable",
    connector_counts_toward_complete_usable: true,
    connector_validation_status: "ready",
    connector_validation_messages: [],
    settings_json: {},
    metadata_json: {},
    idempotency_key: null,
    created_by: "dev-engineer",
    created_at: "2026-05-26T00:00:00Z",
    updated_at: "2026-05-26T00:00:00Z",
    latest_documents: [document()],
    ...overrides,
  };
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

function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/knowledge"]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/knowledge" element={<KnowledgePage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("KnowledgePage", () => {
  it("renders workbench stats, filters API sources, and switches agents", async () => {
    const localSource = source();
    const apiSource = source({
      id: "connector-1",
      name: "Dify 知识库",
      source_type: "connector",
      connector_provider: "dify",
      connector_release_state: "usable",
      connector_counts_toward_complete_usable: true,
      settings_json: {
        connector_provider: "dify",
        connector_release_state: "usable",
        endpoint: "https://api.dify.ai/v1",
      },
      latest_documents: [
        document({
          id: "connector-doc-1",
          source_id: "connector-1",
          title: "Dify API 连接器",
          metadata_json: { connector_config_only: true, retrieval_eligible: false },
        }),
      ],
    });
    const researcherSource = source({
      id: "research-source",
      agent_id: "researcher",
      name: "研究资料",
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/agents" && !init?.method) {
        return jsonResponse({
          items: [
            agent(),
            agent({ id: "researcher", name: "研究智能体", description: "研究作用域" }),
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/default/knowledge/sources" && !init?.method) {
        return jsonResponse({ items: [apiSource, localSource], next_cursor: null });
      }
      if (path === "/api/agents/researcher/knowledge/sources" && !init?.method) {
        return jsonResponse({ items: [researcherSource], next_cursor: null });
      }
      if (path.endsWith("/documents") && !init?.method) {
        return jsonResponse([document()]);
      }
      return jsonResponse({ detail: `unexpected request ${path}` }, 404);
    });
    const user = userEvent.setup();
    renderPage(fetchMock);

    expect(await screen.findByRole("heading", { name: "知识库" })).toBeInTheDocument();
    expect(await screen.findByText("本地手册")).toBeInTheDocument();
    expect((await screen.findAllByText("Dify 知识库")).length).toBeGreaterThan(0);
    expect(screen.getByText("API 配置")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^API Coze \/ Dify \/ LangChain \/ RAGFlow$/ }));
    expect(screen.queryByText("本地手册")).not.toBeInTheDocument();
    expect(screen.getAllByText("Dify 知识库").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: /^全部 本地文档和 API 配置$/ }));
    await user.click(screen.getByRole("button", { name: /知识库智能体/ }));
    await user.click(await screen.findByText("研究智能体"));
    expect((await screen.findAllByText("研究资料")).length).toBeGreaterThan(0);
  });

  it("creates a local RAGFlow endpoint connector from the API preset", async () => {
    const user = userEvent.setup();
    let created = false;
    const createdSource = source({
      id: "local-ragflow-1",
      name: "Local RAGFlow 知识库",
      source_type: "connector",
      connector_provider: "local_ragflow",
      connector_release_state: "preview-not-counted",
      connector_counts_toward_complete_usable: false,
      connector_validation_status: "preview",
      connector_validation_messages: ["preview_connector_not_counted_as_usable"],
      settings_json: {
        connector_provider: "local_ragflow",
        connector_release_state: "preview-not-counted",
        endpoint: "http://127.0.0.1:9380",
      },
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/agents" && !init?.method) {
        return jsonResponse({ items: [agent()], next_cursor: null });
      }
      if (path === "/api/agents/default/knowledge/sources" && !init?.method) {
        return jsonResponse({ items: created ? [createdSource] : [], next_cursor: null });
      }
      if (path === "/api/agents/default/knowledge/sources" && init?.method === "POST") {
        created = true;
        return jsonResponse(createdSource, 201);
      }
      if (path === "/api/agents/default/knowledge/sources/local-ragflow-1/documents" && !init?.method) {
        return jsonResponse(createdSource.latest_documents);
      }
      return jsonResponse({ detail: `unexpected request ${path}` }, 404);
    });
    renderPage(fetchMock);

    await screen.findByText("暂无知识源。");
    await user.click(screen.getByRole("button", { name: "外部 API" }));
    await user.click(screen.getByRole("button", { name: /Local RAGFlow/ }));
    await user.click(screen.getByRole("button", { name: /保存配置/ }));

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/agents/default/knowledge/sources" && init?.method === "POST",
      );
      expect(createCall).toBeDefined();
      expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
        name: "Local RAGFlow 知识库",
        source_type: "connector",
        uri: "http://127.0.0.1:9380",
        connector_settings_json: {
          provider: "local_ragflow",
          endpoint: "http://127.0.0.1:9380",
          secret_ref: "secret://local-ragflow",
          release_state: "preview-not-counted",
        },
      });
    });
    expect((await screen.findAllByText("Local RAGFlow 知识库")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("preview").length).toBeGreaterThan(0);
  });

  it("creates a LangChain Retriever grounding connector with source_kind evidence settings", async () => {
    const user = userEvent.setup();
    let created = false;
    const createdSource = source({
      id: "langchain-retriever-1",
      name: "LangChain Retriever 知识库",
      source_type: "connector",
      connector_provider: "langchain",
      connector_release_state: "configured-but-unavailable",
      connector_counts_toward_complete_usable: false,
      connector_validation_status: "configured",
      connector_validation_messages: ["configured_but_unavailable"],
      settings_json: {
        provider: "langchain",
        source_kind: "langchain_connector",
        release_state: "configured-but-unavailable",
        endpoint: "langchain://retriever/default",
        secret_ref: "secret://langchain",
      },
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/agents" && !init?.method) {
        return jsonResponse({ items: [agent()], next_cursor: null });
      }
      if (path === "/api/agents/default/knowledge/sources" && !init?.method) {
        return jsonResponse({ items: created ? [createdSource] : [], next_cursor: null });
      }
      if (path === "/api/agents/default/knowledge/sources" && init?.method === "POST") {
        created = true;
        return jsonResponse(createdSource, 201);
      }
      if (path === "/api/agents/default/knowledge/sources/langchain-retriever-1/documents" && !init?.method) {
        return jsonResponse([]);
      }
      return jsonResponse({ detail: `unexpected request ${path}` }, 404);
    });
    renderPage(fetchMock);

    await screen.findByText("暂无知识源。");
    await user.click(screen.getByRole("button", { name: "外部 API" }));
    await user.click(screen.getByRole("button", { name: /LangChain Retriever/ }));
    await user.click(screen.getByRole("button", { name: /保存配置/ }));

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/agents/default/knowledge/sources" && init?.method === "POST",
      );
      expect(createCall).toBeDefined();
      expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
        name: "LangChain Retriever 知识库",
        source_type: "connector",
        uri: "langchain://retriever/default",
        connector_settings_json: {
          provider: "langchain",
          source_kind: "langchain_connector",
          endpoint: "langchain://retriever/default",
          secret_ref: "secret://langchain",
          release_state: "configured-but-unavailable",
        },
      });
    });
    expect((await screen.findAllByText("LangChain Retriever 知识库")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("configured").length).toBeGreaterThan(0);
  });
});
