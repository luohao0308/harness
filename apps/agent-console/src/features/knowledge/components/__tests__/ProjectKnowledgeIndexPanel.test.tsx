import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  parseProjectIgnorePatterns,
  ProjectKnowledgeIndexPanel,
} from "../ProjectKnowledgeIndexPanel";
import type { ProjectKnowledgeIndex } from "../../../tasks/api";

const apiBaseUrl = "http://127.0.0.1:8000";
const rootIdentity = "a".repeat(64);
const fileSha256 = "b".repeat(64);

function projectIndex(overrides: Partial<ProjectKnowledgeIndex> = {}): ProjectKnowledgeIndex {
  return {
    id: "index-active",
    organization_id: "dev-org",
    agent_id: "default",
    knowledge_source_id: "source-project",
    desktop_profile_id: "profile-a",
    root_identity: rootIdentity,
    name: "Harness 项目",
    description: "自动同步项目文档",
    status: "ACTIVE",
    ignore_patterns: ["docs/archive/**"],
    snapshot_generation: 2,
    snapshot_cursor: "cursor-2",
    file_count: 8,
    indexed_file_count: 7,
    error_file_count: 1,
    last_snapshot_at: "2026-08-18T10:00:00Z",
    last_sync_at: "2026-08-18T10:00:01Z",
    last_error: "one file changed during scan",
    unbound_at: null,
    created_at: "2026-08-18T09:00:00Z",
    updated_at: "2026-08-18T10:00:01Z",
    ...overrides,
  };
}

function snapshot(): DesktopProjectKnowledgeSnapshot {
  return {
    schemaVersion: "desktop-project-knowledge-snapshot-v1",
    defaultIgnoreVersion: "v1",
    rootIdentity,
    snapshotCursor: "cursor-3",
    complete: true,
    truncated: false,
    truncationReason: null,
    files: [
      {
        relativePath: "docs/guide.md",
        status: "ready",
        content: "# Guide",
        contentSha256: fileSha256,
        sizeBytes: 7,
        modifiedAt: "2026-08-18T10:02:00Z",
        mimeType: "text/markdown",
        skipReason: null,
      },
    ],
    errors: [],
    scannedFiles: 1,
    indexedFiles: 1,
    totalBytes: 7,
    startedAt: "2026-08-18T10:02:00Z",
    completedAt: "2026-08-18T10:02:01Z",
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

function renderPanel(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ProjectKnowledgeIndexPanel agentId="default" />
    </QueryClientProvider>,
  );
}

function installDesktopApi(options: {
  onProfileChanged?: (callback: (profile: DesktopProfile) => void) => () => void;
} = {}) {
  const selectWorkspaceRoot = vi.fn(async () => ({
    rootPath: "/Users/private/workspace/harness",
    watching: true,
  }));
  const scanProjectKnowledge = vi.fn(async () => snapshot());
  window.desktopApi = {
    profile: {
      list: vi.fn(async () => ({ activeProfileId: "profile-a", profiles: [] })),
    },
    file: {
      selectWorkspaceRoot,
      scanProjectKnowledge,
      getWorkspaceRoot: vi.fn(async () => ({
        rootPath: "/Users/private/workspace/harness",
        watching: true,
      })),
    },
    events: options.onProfileChanged ? {
      onProfileChanged: options.onProfileChanged,
    } : undefined,
  };
  return { selectWorkspaceRoot, scanProjectKnowledge };
}

afterEach(() => {
  vi.unstubAllGlobals();
  delete window.desktopApi;
});

describe("ProjectKnowledgeIndexPanel", () => {
  it("deduplicates additional ignore patterns without weakening defaults", () => {
    expect(parseProjectIgnorePatterns(" dist/**\n\n*.generated.md\r\ndist/** ")).toEqual([
      "dist/**",
      "*.generated.md",
    ]);
  });

  it("shows API-backed status in browsers while keeping Desktop binding unavailable", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ items: [projectIndex({ status: "ERROR" })] }));
    renderPanel(fetchMock);

    expect(await screen.findByText("Harness 项目")).toBeInTheDocument();
    expect(screen.getByText("有错误")).toBeInTheDocument();
    expect(screen.getByText("当前可查看索引状态；目录绑定与本机重扫需要在 Harness Desktop 中操作。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "绑定目录" })).not.toBeInTheDocument();
    expect(screen.queryByText("/Users/private/workspace/harness")).not.toBeInTheDocument();
    expect(screen.getByText(`root:${rootIdentity.slice(0, 12)}...`)).toBeInTheDocument();
  });

  it("selects, scans, creates, and performs the first sync without rendering the absolute path", async () => {
    const user = userEvent.setup();
    const { selectWorkspaceRoot, scanProjectKnowledge } = installDesktopApi();
    let items: ProjectKnowledgeIndex[] = [];
    const created = projectIndex({ snapshot_generation: 0, snapshot_cursor: null });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/agents/default/knowledge/project-indexes" && !init?.method) {
        return jsonResponse({ items });
      }
      if (path === "/api/agents/default/knowledge/project-indexes" && init?.method === "POST") {
        return jsonResponse(created, 201);
      }
      if (path === "/api/agents/default/knowledge/project-indexes/index-active/sync" && init?.method === "POST") {
        items = [projectIndex({ snapshot_generation: 1, snapshot_cursor: "cursor-3" })];
        return jsonResponse(items[0]);
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    renderPanel(fetchMock);

    await user.click(await screen.findByRole("button", { name: "绑定目录" }));
    await user.type(screen.getByLabelText("索引名称"), "Harness 项目");
    await user.type(screen.getByLabelText("附加忽略规则"), "docs/archive/**\n*.generated.md\ndocs/archive/**");
    await user.click(screen.getByRole("button", { name: "选择目录" }));
    expect(selectWorkspaceRoot).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("/Users/private/workspace/harness")).not.toBeInTheDocument();
    expect(screen.getByText(/纳入索引的文本内容、相对路径、内容哈希/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "绑定并首次同步" }));

    await waitFor(() => {
      expect(scanProjectKnowledge).toHaveBeenCalledWith({
        ignorePatterns: ["docs/archive/**", "*.generated.md"],
      });
      expect(items).toHaveLength(1);
    });
    const createCall = fetchMock.mock.calls.find(
      ([input, init]) => requestPath(input) === "/api/agents/default/knowledge/project-indexes" && init?.method === "POST",
    );
    expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
      name: "Harness 项目",
      desktop_profile_id: "profile-a",
      root_identity: rootIdentity,
      ignore_patterns: ["docs/archive/**", "*.generated.md"],
    });
    const syncCall = fetchMock.mock.calls.find(
      ([input, init]) => requestPath(input).endsWith("/index-active/sync") && init?.method === "POST",
    );
    expect(JSON.parse(String(syncCall?.[1]?.body))).toMatchObject({
      desktop_profile_id: "profile-a",
      root_identity: rootIdentity,
      files: [{ relative_path: "docs/guide.md", content_sha256: fileSha256 }],
    });
  });

  it("cancels initial linking when the Profile changes after the scan checks", async () => {
    const user = userEvent.setup();
    let profileChange: ((profile: DesktopProfile) => void) | null = null;
    const unsubscribeProfile = vi.fn();
    installDesktopApi({
      onProfileChanged: (callback) => {
        profileChange = callback;
        return unsubscribeProfile;
      },
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/agents/default/knowledge/project-indexes" && !init?.method) {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/agents/default/knowledge/project-indexes" && init?.method === "POST") {
        profileChange?.({ id: "profile-b" } as DesktopProfile);
        if (init.signal?.aborted) throw new DOMException("Aborted", "AbortError");
        return jsonResponse(projectIndex(), 201);
      }
      if (path === "/api/agents/default/knowledge/project-indexes/index-active/unbind" && init?.method === "POST") {
        return jsonResponse(projectIndex({ status: "UNBOUND", unbound_at: "2026-08-19T00:00:00Z" }));
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    renderPanel(fetchMock);

    await user.click(await screen.findByRole("button", { name: "绑定目录" }));
    await user.type(screen.getByLabelText("索引名称"), "Harness 项目");
    await user.click(screen.getByRole("button", { name: "选择目录" }));
    await user.click(screen.getByRole("button", { name: "绑定并首次同步" }));

    expect(await screen.findByText("绑定期间 Desktop Profile 已切换，请重新绑定")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(
      ([input, init]) => requestPath(input).endsWith("/index-active/sync") && init?.method === "POST",
    )).toBe(false);
    expect(fetchMock.mock.calls.filter(
      ([input, init]) => requestPath(input) === "/api/agents/default/knowledge/project-indexes" && init?.method === "POST",
    )).toHaveLength(2);
    const cleanupCall = fetchMock.mock.calls.find(
      ([input, init]) => requestPath(input).endsWith("/index-active/unbind") && init?.method === "POST",
    );
    expect(JSON.parse(String(cleanupCall?.[1]?.body))).toEqual({
      reason: "desktop_profile_changed_during_initial_link",
    });
    expect(unsubscribeProfile).toHaveBeenCalledTimes(1);
  });

  it("supports rescan, pause, resume, and confirmed unbind actions", async () => {
    const user = userEvent.setup();
    const { scanProjectKnowledge } = installDesktopApi();
    const items = [
      projectIndex(),
      projectIndex({ id: "index-paused", name: "暂停项目", status: "PAUSED" }),
    ];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/agents/default/knowledge/project-indexes" && !init?.method) {
        return jsonResponse({ items });
      }
      if (path.endsWith("/sync") && init?.method === "POST") return jsonResponse(items[0]);
      if (path.endsWith("/pause") && init?.method === "POST") return jsonResponse(items[0]);
      if (path.endsWith("/resume") && init?.method === "POST") return jsonResponse(items[1]);
      if (path.endsWith("/unbind") && init?.method === "POST") {
        return jsonResponse(projectIndex({ status: "UNBOUND", unbound_at: "2026-08-18T11:00:00Z" }));
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    renderPanel(fetchMock);

    const activeRow = (await screen.findByText("Harness 项目")).closest("article")!;
    await user.click(within(activeRow).getByRole("button", { name: "重扫" }));
    await waitFor(() => expect(scanProjectKnowledge).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(within(activeRow).getByRole("button", { name: "暂停" })).toBeEnabled());
    await user.click(within(activeRow).getByRole("button", { name: "暂停" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(
      ([input, init]) => requestPath(input).endsWith("/index-active/pause") && init?.method === "POST",
    )).toBe(true));

    const pausedRow = screen.getByText("暂停项目").closest("article")!;
    await waitFor(() => expect(within(pausedRow).getByRole("button", { name: "恢复" })).toBeEnabled());
    await user.click(within(pausedRow).getByRole("button", { name: "恢复" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(
      ([input, init]) => requestPath(input).endsWith("/index-paused/resume") && init?.method === "POST",
    )).toBe(true));

    await waitFor(() => expect(within(activeRow).getByRole("button", { name: "解绑" })).toBeEnabled());
    await user.click(within(activeRow).getByRole("button", { name: "解绑" }));
    const dialog = screen.getByRole("dialog", { name: "解绑项目索引" });
    expect(within(dialog).getByText(/历史引用证据仍会保留/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "确认解绑" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(
      ([input, init]) => requestPath(input).endsWith("/index-active/unbind") && init?.method === "POST",
    )).toBe(true));
  });
});
