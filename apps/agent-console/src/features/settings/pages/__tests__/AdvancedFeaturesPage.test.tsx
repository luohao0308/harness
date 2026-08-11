import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../../app/ConsoleShell", () => ({
  ConsoleShell: ({ children, title }: { children: React.ReactNode; title: string }) => (
    <main aria-label={title}>{children}</main>
  ),
}));

import { AdvancedFeaturesPage } from "../AdvancedFeaturesPage";

const apiBaseUrl = "http://127.0.0.1:8000";

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

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AdvancedFeaturesPage />
    </QueryClientProvider>,
  );
}

describe("AdvancedFeaturesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    document.documentElement.classList.remove("theme-high-contrast");
    delete window.desktopApi;
  });

  it("installs marketplace plugins and persists custom prompt templates", async () => {
    const installed = new Set<string>();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/plugins/marketplace" && !init?.method) {
        return jsonResponse({
          installed_count: installed.size,
          items: [
            {
              id: "github-tools",
              name: "GitHub 工具集",
              description: "第三方工具接入",
              category: "tool",
              publisher: "Harness",
              version: "1.0.0",
              permissions: ["tool:github.search"],
              install_state: installed.has("github-tools") ? "installed" : "available",
              installed_at: installed.has("github-tools") ? "2026-06-27T00:00:00Z" : null,
              config_json: {},
            },
          ],
        });
      }
      if (path === "/api/plugins/marketplace/github-tools/install" && init?.method === "POST") {
        installed.add("github-tools");
        return jsonResponse({
          id: "github-tools",
          name: "GitHub 工具集",
          description: "第三方工具接入",
          category: "tool",
          publisher: "Harness",
          version: "1.0.0",
          permissions: ["tool:github.search"],
          install_state: "installed",
          installed_at: "2026-06-27T00:00:00Z",
          config_json: {},
        });
      }
      if (path === "/api/plugins/prompt-templates" && !init?.method) {
        return jsonResponse({
          items: [
            {
              id: "release-readiness",
              name: "发布审查",
              description: "检查 Run 证据",
              body: "review",
              tags: ["release"],
              source: "built-in",
              plugin_id: null,
              updated_at: null,
            },
          ],
        });
      }
      if (path === "/api/plugins/prompt-templates" && init?.method === "POST") {
        return jsonResponse({
          id: "custom-release-check",
          name: "自定义发布检查",
          description: "生成发布前检查清单。",
          body: "请基于当前 Run 证据输出阻塞项、风险项和上线后观察项。",
          tags: ["release", "check"],
          source: "custom",
          plugin_id: null,
          updated_at: "2026-06-27T00:00:00Z",
        });
      }
      return jsonResponse({});
    });
    globalThis.fetch = fetchMock;

    renderPage();

    expect(await screen.findByText("GitHub 工具集")).toBeInTheDocument();
    expect(screen.getByText("插件和提示词")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "安装" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/plugins/marketplace/github-tools/install"),
        expect.objectContaining({ method: "POST" }),
      );
    });

    await userEvent.click(screen.getByText("新建提示词模板"));
    await userEvent.click(screen.getByRole("button", { name: "保存模板" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/plugins/prompt-templates"),
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  it("uses the desktop bridge for profiles, offline tasks, and high contrast", async () => {
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === "/api/plugins/marketplace") {
        return jsonResponse({ installed_count: 0, items: [] });
      }
      if (path === "/api/plugins/prompt-templates") {
        return jsonResponse({ items: [] });
      }
      return jsonResponse({});
    });
    const offlineTask: DesktopOfflineTask = {
      id: "offline-1",
      prompt: "整理当前离线工作，列出下一步。",
      result: "离线任务已完成",
      modelSource: "deterministic-local",
      status: "completed",
      createdAt: "2026-06-27T00:00:00Z",
    };
    window.desktopApi = {
      profile: {
        list: vi.fn(async () => ({
          activeProfileId: "default",
          profiles: [
            {
              id: "default",
              label: "默认工作区",
              apiBaseUrl: "http://localhost:8000",
              dataPath: "/tmp/default",
              createdAt: "2026-06-27T00:00:00Z",
              updatedAt: "2026-06-27T00:00:00Z",
              hasCredential: false,
              credentialStorage: "none" as const,
            },
          ],
        })),
        save: vi.fn(async (profile) => ({
          id: profile.id ?? "customer-a",
          label: profile.label,
          apiBaseUrl: profile.apiBaseUrl ?? "http://localhost:8000",
          dataPath: "/tmp/customer-a",
          createdAt: "2026-06-27T00:00:00Z",
          updatedAt: "2026-06-27T00:00:00Z",
          hasCredential: Boolean(profile.authToken),
          credentialStorage: profile.authToken ? ("persistent" as const) : ("none" as const),
        })),
        switch: vi.fn(async (profileId) => ({
          id: profileId,
          label: "Customer A",
          apiBaseUrl: "http://localhost:8000",
          dataPath: "/tmp/customer-a",
          createdAt: "2026-06-27T00:00:00Z",
          updatedAt: "2026-06-27T00:00:00Z",
          hasCredential: true,
          credentialStorage: "persistent" as const,
        })),
      },
      window: {
        list: vi.fn(async () => ({ items: [] })),
        openRun: vi.fn(async (runId) => ({
          id: 1,
          key: `default:run:${runId}`,
          kind: "run" as const,
          runId,
          route: `/runs/${runId}`,
          profileId: "default",
          focused: true,
          visible: true,
        })),
      },
      localModel: {
        getSettings: vi.fn(async () => ({
          enabled: false,
          provider: "ollama" as const,
          baseUrl: "http://127.0.0.1:11434",
          model: "llama3.1",
          updatedAt: "2026-06-27T00:00:00Z",
        })),
        setSettings: vi.fn(async (settings) => ({
          enabled: Boolean(settings.enabled),
          provider: settings.provider ?? ("ollama" as const),
          baseUrl: settings.baseUrl ?? "http://127.0.0.1:11434",
          model: settings.model ?? "llama3.1",
          updatedAt: "2026-06-27T00:00:00Z",
        })),
        testConnection: vi.fn(async () => ({
          available: true,
          checkedAt: "2026-07-12T00:00:00Z",
          durationMs: 12,
          error: null,
        })),
      },
      offline: {
        listTasks: vi.fn(async () => ({ items: [] })),
        runSimpleTask: vi.fn(async () => offlineTask),
        promoteResultToPendingAgentTask: vi.fn(async () => ({ taskId: "task-1", operationId: 1 })),
      },
      sync: {
        getStatus: vi.fn(async () => ({
          state: "idle" as const,
          profileId: "default",
          dataPath: "/tmp/default",
          online: true,
          lastChangeTimestamp: "2026-07-12T00:00:00Z",
          lastStartedAt: null,
          lastCompletedAt: null,
          lastError: null,
          nextRetryAt: null,
          retryAttempt: 0,
          pendingOperations: 0,
          retryableOperations: 0,
          conflictCount: 0,
        })),
        runNow: vi.fn(async () => ({
          state: "idle" as const,
          profileId: "default",
          dataPath: "/tmp/default",
          online: true,
          lastChangeTimestamp: "2026-07-12T00:00:00Z",
          lastStartedAt: null,
          lastCompletedAt: "2026-07-12T00:00:01Z",
          lastError: null,
          nextRetryAt: null,
          retryAttempt: 0,
          pendingOperations: 0,
          retryableOperations: 0,
          conflictCount: 0,
        })),
        onStatus: vi.fn(() => vi.fn()),
      },
      system: {
        getStartupEnabled: vi.fn(async () => false),
        setStartupEnabled: vi.fn(async (enabled) => enabled),
      },
      file: {
        getWorkspaceRoot: vi.fn(async () => ({ rootPath: null, watching: false })),
        selectWorkspaceRoot: vi.fn(async () => ({ rootPath: "/tmp/harness", watching: false })),
        startWatch: vi.fn(async () => ({ rootPath: "/tmp/harness", watching: true })),
        stopWatch: vi.fn(async () => ({ rootPath: "/tmp/harness", watching: false })),
      },
      updates: {
        getStatus: vi.fn(async () => ({
          state: "idle" as const,
          channel: "stable" as const,
          currentVersion: "0.1.0",
          latestVersion: null,
          releaseUrl: null,
          progress: null,
          reason: null,
          error: null,
        })),
      },
      feedback: {
        getMetricsSummary: vi.fn(async () => ({
          startup_count: 0,
          startup_avg_ms: null,
          startup_p95_ms: null,
          crash_events: 0,
          sync_successes: 0,
          sync_failures: 0,
          sync_success_rate: null,
        })),
      },
      events: {
        onProfileChanged: vi.fn(() => vi.fn()),
      },
    };

    renderPage();

    expect(await screen.findByText("桌面设置")).toBeInTheDocument();
    expect(screen.getByText("章节")).toBeInTheDocument();
    expect(screen.getAllByText("默认工作区").length).toBeGreaterThan(0);
    expect(screen.getByText("工作区和窗口")).toBeInTheDocument();
    expect(screen.getAllByText("离线执行").length).toBeGreaterThan(0);

    await userEvent.click(screen.getByText("工作区配置"));
    await userEvent.click(screen.getByRole("button", { name: "保存并切换" }));
    await waitFor(() => expect(window.desktopApi?.profile?.save).toHaveBeenCalled());

    await userEvent.click(screen.getByRole("button", { name: "离线执行" }));
    await waitFor(() => expect(window.desktopApi?.offline?.runSimpleTask).toHaveBeenCalled());

    await userEvent.click(screen.getByText("本地模型设置"));
    await userEvent.click(screen.getByRole("button", { name: "测试连接" }));
    await waitFor(() => expect(window.desktopApi?.localModel?.testConnection).toHaveBeenCalled());
    expect(screen.getByText("连接可用 · 12ms")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "高对比度" }));
    expect(document.documentElement).toHaveClass("theme-high-contrast");
    expect(window.localStorage.getItem("harness.a11y.high_contrast")).toBe("1");
  });

  it("exposes native operations promised by the desktop production guide", async () => {
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === "/api/plugins/marketplace") {
        return jsonResponse({ installed_count: 0, items: [] });
      }
      if (path === "/api/plugins/prompt-templates") {
        return jsonResponse({ items: [] });
      }
      return jsonResponse({});
    });

    window.desktopApi = {
      profile: {
        list: vi.fn(async () => ({ activeProfileId: "default", profiles: [] })),
      },
      window: {
        list: vi.fn(async () => ({ items: [] })),
      },
      localModel: {
        getSettings: vi.fn(async () => ({
          enabled: false,
          provider: "ollama" as const,
          baseUrl: "http://127.0.0.1:11434",
          model: "llama3.1",
          updatedAt: "2026-06-27T00:00:00Z",
        })),
      },
      offline: {
        listTasks: vi.fn(async () => ({ items: [] })),
      },
      system: {
        getStartupEnabled: vi.fn(async () => false),
        setStartupEnabled: vi.fn(async (enabled) => enabled),
      },
      file: {
        getWorkspaceRoot: vi.fn(async () => ({ rootPath: "/tmp/harness", watching: false })),
        selectWorkspaceRoot: vi.fn(async () => ({ rootPath: "/tmp/harness-selected", watching: false })),
        startWatch: vi.fn(async () => ({ rootPath: "/tmp/harness", watching: true })),
        stopWatch: vi.fn(async () => ({ rootPath: "/tmp/harness", watching: false })),
      },
      updates: {
        getStatus: vi.fn(async () => ({
          state: "available" as const,
          channel: "beta" as const,
          currentVersion: "0.1.0",
          latestVersion: "0.2.0-beta.1",
          releaseUrl: "https://example.test/releases/v0.2.0-beta.1",
          progress: null,
          files: ["latest-mac.yml"],
          checkedAt: "2026-07-04T00:00:00Z",
          reason: null,
          error: null,
        })),
        check: vi.fn(async () => ({
          state: "available" as const,
          channel: "beta" as const,
          currentVersion: "0.1.0",
          latestVersion: "0.2.0-beta.1",
          releaseUrl: "https://example.test/releases/v0.2.0-beta.1",
          progress: null,
          files: ["latest-mac.yml"],
          checkedAt: "2026-07-04T00:00:00Z",
          reason: null,
          error: null,
        })),
        download: vi.fn(async () => ({
          state: "downloading" as const,
          channel: "beta" as const,
          currentVersion: "0.1.0",
          latestVersion: "0.2.0-beta.1",
        })),
        install: vi.fn(async () => undefined),
      },
      feedback: {
        submit: vi.fn(async () => ({
          received: true,
          feedback_id: "feedback-1",
          received_at: "2026-07-04T00:00:00Z",
        })),
        getMetricsSummary: vi.fn(async () => ({
          startup_count: 3,
          startup_avg_ms: 1200,
          startup_p95_ms: 1800,
          crash_events: 1,
          sync_successes: 8,
          sync_failures: 2,
          sync_success_rate: 0.8,
        })),
      },
      events: {
        onProfileChanged: vi.fn(() => vi.fn()),
      },
    };

    renderPage();

    await waitFor(() => expect(screen.getAllByText("系统与发布").length).toBeGreaterThan(0));
    expect(screen.getAllByText("harness").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Beta").length).toBeGreaterThan(0);
    expect(screen.getAllByText("0.2.0-beta.1").length).toBeGreaterThan(0);
    expect(screen.queryByText("崩溃 1")).not.toBeInTheDocument();
    expect(screen.getByText("反馈")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "启用开机启动" }));
    await waitFor(() => expect(window.desktopApi?.system?.setStartupEnabled).toHaveBeenCalledWith(true));

    await userEvent.click(screen.getByRole("button", { name: "选择文件根" }));
    await waitFor(() => expect(window.desktopApi?.file?.selectWorkspaceRoot).toHaveBeenCalled());

    await userEvent.click(screen.getByRole("button", { name: "检查更新" }));
    await waitFor(() => expect(window.desktopApi?.updates?.check).toHaveBeenCalled());

    expect(screen.getByRole("button", { name: "下载更新" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "安装更新" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "提交反馈" }));
    await waitFor(() => expect(window.desktopApi?.feedback?.submit).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "桌面工作台反馈",
        channel: "beta",
        app_version: "0.1.0",
        logs: expect.not.arrayContaining([expect.stringContaining("/tmp/harness")]),
      }),
    ));
  });

  it("distinguishes a bridge read failure from a connected desktop bridge", async () => {
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === "/api/plugins/marketplace") return jsonResponse({ installed_count: 0, items: [] });
      if (path === "/api/plugins/prompt-templates") return jsonResponse({ items: [] });
      return jsonResponse({});
    });
    window.desktopApi = {
      profile: { list: vi.fn(async () => { throw new Error("preload unavailable"); }) },
      window: { list: vi.fn(async () => ({ items: [] })) },
      localModel: { getSettings: vi.fn(async () => undefined as never) },
      offline: { listTasks: vi.fn(async () => ({ items: [] })) },
      system: { getStartupEnabled: vi.fn(async () => false) },
      file: { getWorkspaceRoot: vi.fn(async () => ({ rootPath: null, watching: false })) },
      updates: { getStatus: vi.fn(async () => undefined as never) },
      feedback: { getMetricsSummary: vi.fn(async () => undefined as never) },
    };

    renderPage();

    expect((await screen.findAllByText("桥接读取失败")).length).toBeGreaterThan(0);
    expect(screen.queryByText("桌面桥接已连接")).not.toBeInTheDocument();
    expect(screen.getByText("preload unavailable")).toBeInTheDocument();
  });
});
