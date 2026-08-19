// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  listAgentProjectKnowledgeIndexes: vi.fn(),
  listAgents: vi.fn(),
  syncAgentProjectKnowledgeIndex: vi.fn(),
}));

vi.mock("../../features/tasks/api", () => ({
  ...apiMocks,
}));

import {
  installProjectKnowledgeSync,
  projectSnapshotToSyncPayload,
  scanAndSyncProjectKnowledgeIndex,
} from "../project-knowledge-sync";
import type { ProjectKnowledgeIndex } from "../../features/tasks/api";

const rootIdentity = "d".repeat(64);

function projectIndex(overrides: Partial<ProjectKnowledgeIndex> = {}): ProjectKnowledgeIndex {
  return {
    id: "project-index-1",
    organization_id: "dev-org",
    agent_id: "default",
    knowledge_source_id: "source-project-1",
    desktop_profile_id: "profile-a",
    root_identity: rootIdentity,
    name: "Harness",
    description: "",
    status: "ACTIVE",
    ignore_patterns: ["archive/**"],
    snapshot_generation: 1,
    snapshot_cursor: "cursor-1",
    file_count: 1,
    indexed_file_count: 1,
    error_file_count: 0,
    last_snapshot_at: "2026-08-18T10:00:00Z",
    last_sync_at: "2026-08-18T10:00:01Z",
    last_error: null,
    unbound_at: null,
    created_at: "2026-08-18T10:00:00Z",
    updated_at: "2026-08-18T10:00:01Z",
    ...overrides,
  };
}

function snapshot(overrides: Partial<DesktopProjectKnowledgeSnapshot> = {}): DesktopProjectKnowledgeSnapshot {
  return {
    schemaVersion: "desktop-project-knowledge-snapshot-v2",
    defaultIgnoreVersion: "v1",
    rootIdentity,
    snapshotCursor: "cursor-2",
    complete: true,
    truncated: false,
    truncationReason: null,
    files: [],
    errors: [],
    scannedFiles: 0,
    indexedFiles: 0,
    totalBytes: 0,
    startedAt: "2026-08-18T10:01:00Z",
    completedAt: "2026-08-18T10:01:01Z",
    ...overrides,
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  apiMocks.listAgents.mockReset();
  apiMocks.listAgentProjectKnowledgeIndexes.mockReset();
  apiMocks.syncAgentProjectKnowledgeIndex.mockReset();
});

afterEach(() => {
  delete window.desktopApi;
  vi.useRealTimers();
});

describe("project knowledge sync", () => {
  it("maps trusted Desktop snapshots to the API contract", () => {
    const payload = projectSnapshotToSyncPayload(snapshot({
      files: [
        {
          relativePath: "docs/guide.md",
          status: "ready",
          content: "guide",
          contentSha256: "e".repeat(64),
          sizeBytes: 5,
          modifiedAt: "2026-08-18T10:01:00Z",
          mimeType: "text/markdown",
          skipReason: null,
        },
      ],
    }), "profile-a");

    expect(payload).toMatchObject({
      schema_version: "desktop-project-knowledge-snapshot-v2",
      default_ignore_version: "v1",
      desktop_profile_id: "profile-a",
      root_identity: rootIdentity,
      snapshot_cursor: "cursor-2",
      files: [{ relative_path: "docs/guide.md", content_sha256: "e".repeat(64) }],
    });
  });

  it("rejects Profile and root identity mismatches before syncing", async () => {
    window.desktopApi = {
      profile: { list: vi.fn(async () => ({ activeProfileId: "profile-b", profiles: [] })) },
      file: { scanProjectKnowledge: vi.fn(async () => snapshot()) },
    };
    await expect(scanAndSyncProjectKnowledgeIndex("default", projectIndex())).rejects.toThrow(
      "请先切换到该项目索引绑定的 Desktop Profile",
    );

    window.desktopApi.profile!.list = vi.fn(async () => ({ activeProfileId: "profile-a", profiles: [] }));
    window.desktopApi.file!.scanProjectKnowledge = vi.fn(async () => snapshot({ rootIdentity: "f".repeat(64) }));
    await expect(scanAndSyncProjectKnowledgeIndex("default", projectIndex())).rejects.toThrow(
      "当前工作区与项目知识索引绑定目录不一致",
    );
    expect(apiMocks.syncAgentProjectKnowledgeIndex).not.toHaveBeenCalled();
  });

  it("cancels an upload when the Profile or workspace root changes during scanning", async () => {
    const profileList = vi.fn()
      .mockResolvedValueOnce({ activeProfileId: "profile-a", profiles: [] })
      .mockResolvedValueOnce({ activeProfileId: "profile-b", profiles: [] });
    window.desktopApi = {
      profile: { list: profileList },
      file: {
        getWorkspaceRoot: vi.fn(async () => ({ rootPath: "/workspace/a", watching: true })),
        scanProjectKnowledge: vi.fn(async () => snapshot()),
      },
    };
    await expect(scanAndSyncProjectKnowledgeIndex("default", projectIndex())).rejects.toThrow(
      "扫描期间 Desktop Profile 已切换",
    );

    window.desktopApi.profile!.list = vi.fn(async () => ({ activeProfileId: "profile-a", profiles: [] }));
    window.desktopApi.file!.getWorkspaceRoot = vi.fn()
      .mockResolvedValueOnce({ rootPath: "/workspace/a", watching: true })
      .mockResolvedValueOnce({ rootPath: "/workspace/b", watching: true });
    await expect(scanAndSyncProjectKnowledgeIndex("default", projectIndex())).rejects.toThrow(
      "扫描期间项目目录已切换",
    );
    expect(apiMocks.syncAgentProjectKnowledgeIndex).not.toHaveBeenCalled();
  });

  it("syncs on startup and debounced file/Profile changes, then disposes listeners", async () => {
    const fileChange: { current: (() => void) | null } = { current: null };
    const profileChange: { current: (() => void) | null } = { current: null };
    const unsubscribeFile = vi.fn();
    const unsubscribeProfile = vi.fn();
    const scanProjectKnowledge = vi.fn(async () => snapshot());
    window.desktopApi = {
      profile: { list: vi.fn(async () => ({ activeProfileId: "profile-a", profiles: [] })) },
      file: {
        scanProjectKnowledge,
        getWorkspaceRoot: vi.fn(async () => ({ rootPath: "/private/workspace", watching: true })),
        startWatch: vi.fn(async () => ({ rootPath: "/private/workspace", watching: true })),
        onChange: vi.fn((callback) => {
          fileChange.current = callback;
          return unsubscribeFile;
        }),
      },
      events: {
        onProfileChanged: vi.fn((callback) => {
          profileChange.current = () => callback({} as DesktopProfile);
          return unsubscribeProfile;
        }),
      },
    };
    apiMocks.listAgents.mockResolvedValue({ items: [{ id: "default" }] });
    apiMocks.listAgentProjectKnowledgeIndexes.mockResolvedValue({ items: [projectIndex()] });
    apiMocks.syncAgentProjectKnowledgeIndex.mockResolvedValue(projectIndex());

    const dispose = installProjectKnowledgeSync();
    await vi.advanceTimersByTimeAsync(750);
    expect(apiMocks.syncAgentProjectKnowledgeIndex).toHaveBeenCalledTimes(1);

    fileChange.current?.();
    fileChange.current?.();
    await vi.advanceTimersByTimeAsync(749);
    expect(apiMocks.syncAgentProjectKnowledgeIndex).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(apiMocks.syncAgentProjectKnowledgeIndex).toHaveBeenCalledTimes(2);

    profileChange.current?.();
    await vi.advanceTimersByTimeAsync(750);
    expect(apiMocks.syncAgentProjectKnowledgeIndex).toHaveBeenCalledTimes(3);

    dispose();
    expect(unsubscribeFile).toHaveBeenCalledTimes(1);
    expect(unsubscribeProfile).toHaveBeenCalledTimes(1);
  });

  it("stays inert outside Desktop", async () => {
    const dispose = installProjectKnowledgeSync();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(apiMocks.listAgents).not.toHaveBeenCalled();
    dispose();
  });
});
