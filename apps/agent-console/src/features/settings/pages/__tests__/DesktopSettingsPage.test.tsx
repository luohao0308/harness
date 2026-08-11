import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../../app/ConsoleShell", () => ({
  ConsoleShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const apiMock = vi.hoisted(() => ({
  getLocalRuntimeModelStatus: vi.fn(),
}));

vi.mock("../../../tasks/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../tasks/api")>()),
  getLocalRuntimeModelStatus: apiMock.getLocalRuntimeModelStatus,
}));

import { DesktopSettingsPage } from "../DesktopSettingsPage";

function renderPage(entry = "/desktop") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <DesktopSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DesktopSettingsPage", () => {
  beforeEach(() => {
    apiMock.getLocalRuntimeModelStatus.mockReset();
    apiMock.getLocalRuntimeModelStatus.mockResolvedValue({
      state: "setup_required",
      provider: "shipped-provider",
      model: "shipped-model",
      base_url: "https://models.example/v1",
      secret_storage: "persistent",
    });
    window.desktopApi = {
      system: {
        getStartupEnabled: vi.fn(async () => false),
        setStartupEnabled: vi.fn(async (enabled) => enabled),
      },
      localRuntime: {
        saveModelConfiguration: vi.fn(async ({ baseUrl, model }) => ({
          state: "healthy" as const,
          provider: "shipped-provider",
          model,
          base_url: baseUrl,
          secret_storage: "persistent" as const,
        })),
        discoverModels: vi.fn(async () => ({
          models: ["model-alpha", "model-beta"],
          durationMs: 128,
        })),
        deleteModelApiKey: vi.fn(async () => ({
          state: "setup_required" as const,
          provider: "shipped-provider",
          model: "shipped-model",
          base_url: "https://models.example/v1",
          secret_storage: "persistent" as const,
        })),
        openWebExtension: vi.fn(async () => undefined),
      },
      file: {
        getWorkspaceRoot: vi.fn(async () => ({ rootPath: null, watching: false })),
        selectWorkspaceRoot: vi.fn(async () => ({ rootPath: "/tmp/workspace", watching: false })),
      },
      updates: {
        getStatus: vi.fn(async () => ({ state: "idle" as const, channel: "stable" as const, currentVersion: "1.0.0" })),
        check: vi.fn(async () => ({ state: "not-available" as const, channel: "stable" as const, currentVersion: "1.0.0" })),
      },
    };
  });

  afterEach(() => {
    delete window.desktopApi;
  });

  it("offers searchable compact desktop categories", async () => {
    renderPage();

    expect(screen.getByRole("navigation", { name: "桌面设置分类" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /模型与密钥/ })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("搜索设置"), "终端");
    expect(screen.getByRole("button", { name: /终端/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /常规/ })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "终端" })).toBeInTheDocument();
  });

  it("returns directly to the main workspace without an operation rail", () => {
    renderPage();
    expect(screen.getByRole("link", { name: "返回应用" })).toHaveAttribute("href", "/agents/default/workspace");
    expect(screen.getByTestId("desktop-settings-space")).toBeInTheDocument();
    expect(screen.queryByTestId("desktop-operation-shell")).not.toBeInTheDocument();
  });

  it("confirms before deleting the model key and refreshes status", async () => {
    renderPage("/desktop?section=models");
    await userEvent.click(await screen.findByRole("button", { name: "清除" }));
    const dialog = screen.getByRole("dialog", { name: "清除模型 API Key？" });
    await userEvent.click(within(dialog).getByRole("button", { name: "清除" }));

    await waitFor(() => {
      expect(window.desktopApi?.localRuntime?.deleteModelApiKey).toHaveBeenCalledOnce();
      expect(apiMock.getLocalRuntimeModelStatus).toHaveBeenCalledTimes(2);
    });
  });

  it("explains session-only secure storage", async () => {
    apiMock.getLocalRuntimeModelStatus.mockResolvedValue({
      state: "configured",
      provider: "shipped-provider",
      model: "shipped-model",
      base_url: "https://models.example/v1",
      secret_storage: "session",
    });
    renderPage("/desktop?section=models");
    expect(await screen.findByText(/仅保留在本次会话中/)).toBeInTheDocument();
    expect(screen.getByText("已配置")).toBeInTheDocument();
  });

  it("tests the connection with the current unsaved Base URL and API Key", async () => {
    renderPage("/desktop?section=models");

    const baseUrl = await screen.findByDisplayValue("https://models.example/v1");
    await userEvent.clear(baseUrl);
    await userEvent.type(baseUrl, "https://draft.example/v1/");
    await userEvent.type(screen.getByLabelText("API Key"), "sk-draft");
    await userEvent.click(screen.getByRole("button", { name: "检测连接" }));

    await waitFor(() => {
      expect(window.desktopApi?.localRuntime?.discoverModels).toHaveBeenCalledWith({
        baseUrl: "https://draft.example/v1",
        apiKey: "sk-draft",
      });
    });
    expect(screen.getByRole("status")).toHaveTextContent("连接成功，用时 128 毫秒，获取到 2 个模型");
  });

  it("refreshes and fills the editable model list from current inputs", async () => {
    renderPage("/desktop?section=models");

    await screen.findByDisplayValue("shipped-model");
    await userEvent.click(screen.getByRole("button", { name: "获取模型列表" }));

    await waitFor(() => expect(window.desktopApi?.localRuntime?.discoverModels).toHaveBeenCalledWith({
      baseUrl: "https://models.example/v1",
    }));
    expect(document.querySelector('datalist#desktop-discovered-models option[value="model-alpha"]')).not.toBeNull();
    expect(document.querySelector('datalist#desktop-discovered-models option[value="model-beta"]')).not.toBeNull();
  });

  it("saves a discovered model and backfills the returned configuration", async () => {
    renderPage("/desktop?section=models");

    await screen.findByDisplayValue("shipped-model");
    await userEvent.click(screen.getByRole("button", { name: "获取模型列表" }));
    const model = screen.getByRole("combobox", { name: "默认模型" });
    await userEvent.clear(model);
    await userEvent.type(model, "model-beta");
    await userEvent.type(screen.getByLabelText("API Key"), "sk-replacement");
    await userEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(window.desktopApi?.localRuntime?.saveModelConfiguration).toHaveBeenCalledWith({
      baseUrl: "https://models.example/v1",
      model: "model-beta",
      apiKey: "sk-replacement",
    }));
    expect(screen.getByLabelText("API Key")).toHaveValue("");
    expect(screen.getByRole("status")).toHaveTextContent("模型配置已保存");
  });

  it("omits an empty API Key so saving preserves the existing secret", async () => {
    renderPage("/desktop?section=models");

    await screen.findByDisplayValue("shipped-model");
    await userEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(window.desktopApi?.localRuntime?.saveModelConfiguration).toHaveBeenCalledWith({
      baseUrl: "https://models.example/v1",
      model: "shipped-model",
    }));
  });

  it("maps model discovery failures to stable Chinese guidance", async () => {
    vi.mocked(window.desktopApi!.localRuntime!.discoverModels!).mockRejectedValueOnce(
      new Error("MODEL_DISCOVERY_AUTH_ERROR: The model provider rejected the API key"),
    );
    renderPage("/desktop?section=models");

    await screen.findByDisplayValue("shipped-model");
    await userEvent.click(screen.getByRole("button", { name: "检测连接" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("API Key 验证失败，请检查密钥是否有效");
  });

  it("maps invalid discovery responses by their Electron error code", async () => {
    vi.mocked(window.desktopApi!.localRuntime!.discoverModels!).mockRejectedValueOnce(
      new Error("MODEL_DISCOVERY_INVALID_RESPONSE: invalid model list"),
    );
    renderPage("/desktop?section=models");

    await screen.findByDisplayValue("shipped-model");
    await userEvent.click(screen.getByRole("button", { name: "获取模型列表" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("模型列表格式不兼容");
  });

  it("rejects non-loopback HTTP Base URLs before invoking Electron", async () => {
    renderPage("/desktop?section=models");

    const baseUrl = await screen.findByDisplayValue("https://models.example/v1");
    await userEvent.clear(baseUrl);
    await userEvent.type(baseUrl, "http://models.example/v1");
    await userEvent.click(screen.getByRole("button", { name: "检测连接" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Base URL 无效");
    expect(window.desktopApi?.localRuntime?.discoverModels).not.toHaveBeenCalled();
  });

  it("opens the authenticated Web Extension through Desktop IPC", async () => {
    renderPage("/desktop?section=web");
    await userEvent.click(screen.getByRole("button", { name: "打开" }));
    expect(window.desktopApi?.localRuntime?.openWebExtension).toHaveBeenCalledOnce();
  });
});
