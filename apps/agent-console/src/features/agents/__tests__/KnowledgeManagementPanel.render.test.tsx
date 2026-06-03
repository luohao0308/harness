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

function setupFetchWith(sampleSource: KnowledgeSource, documents: KnowledgeDocument[]) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
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
      const requestedPaths = fetchMock.mock.calls.map(([input]) => String(input));
      expect(requestedPaths).toContain(
        `${apiBaseUrl}/api/agents/default/knowledge/sources/source-1/archive`,
      );
      expect(requestedPaths).toContain(
        `${apiBaseUrl}/api/agents/default/knowledge/sources/source-1/scope`,
      );
    });
    expect(confirm).toHaveBeenCalledTimes(2);
    const scopeCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/scope"));
    expect(JSON.parse(String(scopeCall?.[1]?.body))).toMatchObject({ scope: "org" });
    expect(scopeCall?.[1]?.headers).toMatchObject({
      Authorization: "Bearer dev-admin-token",
    });
  });

  it("posts add-document and document-version requests from the management surface", async () => {
    const user = userEvent.setup();
    const fetchMock = setupFetch();
    vi.stubGlobal("confirm", vi.fn(() => true));
    renderPanel(fetchMock);

    await screen.findByText("Team Knowledge");
    await user.type(screen.getByLabelText("新增文档内容"), "Additional markdown notes");
    await user.click(screen.getByRole("button", { name: /添加/ }));

    await user.type(screen.getByLabelText("重新导入内容"), "Updated manual v2");
    await user.click(screen.getByRole("button", { name: /创建版本/ }));

    await waitFor(() => {
      const requestedPaths = fetchMock.mock.calls.map(([input]) => String(input));
      expect(requestedPaths).toContain(
        `${apiBaseUrl}/api/agents/default/knowledge/sources/source-1/documents`,
      );
      expect(requestedPaths).toContain(
        `${apiBaseUrl}/api/agents/default/knowledge/sources/source-1/documents/doc-1/versions`,
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

    expect(screen.getByRole("button", { name: /创建版本/ })).toBeDisabled();
  });
});
