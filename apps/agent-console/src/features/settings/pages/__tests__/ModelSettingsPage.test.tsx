import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../../components/ui/feedback-toast", () => ({
  FeedbackToastViewport: () => null,
  feedbackErrorMessage: (error: unknown, fallback: string) =>
    error instanceof Error ? error.message : fallback,
  notifyFeedback: vi.fn(),
}));

import { modelCatalog } from "../../modelCatalog";
import { ModelSettingsPage } from "../ModelSettingsPage";

const apiBaseUrl = "http://127.0.0.1:8000";
const managedProvider = "chybenzun-openai-compatible";

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

function modelSettingsPayload(apiKeyConfigured = true) {
  return {
    default_provider: managedProvider,
    default_model: "minimax-m3",
    providers: [
      {
        name: managedProvider,
        label: "MiniMax M3",
        provider_id: managedProvider,
        catalog_provider: managedProvider,
        secret_provider: managedProvider,
        model: "minimax-m3",
        api_format: "openai",
        base_url: "https://ai.112102.xyz/v1",
        api_key_env: "AI_PROVIDER_API_KEY",
        api_key_configured: apiKeyConfigured,
        api_key_source: apiKeyConfigured ? "env_platform" : "missing",
        managed_by_platform: true,
      },
    ],
    rate_limits: { rpm: 600, tpm: 120000 },
    health: { status: "healthy", updated_at: null, mode: "configured", latency_ms: 0, error_message: null },
    circuit_breaker: { failure_threshold: 3, cooldown_seconds: 60 },
  };
}

function fallbackSummaryPayload() {
  return { organization_id: "dev-org", fallback_total: 0, primary_failure_total: 0, providers: [], recent_events: [] };
}

function pricingSourcesPayload() {
  const now = "2026-05-30T00:00:00Z";
  return {
    schema_version: "model_pricing_sources.v1",
    retrieved_at: now,
    parser_version: "manual-official-source-2026-05-30",
    blocking_statuses: [],
    items: [
      {
        provider: "deepseek-flash",
        model: "deepseek-v4-flash",
        mapped_provider: "deepseek-flash",
        mapped_model: "deepseek-v4-flash",
        display_name: "DeepSeek Flash",
        official_url: "https://api-docs.deepseek.com/quick_start/pricing",
        retrieved_at: now,
        unit: "per_1m_tokens",
        currency: "USD",
        input_per_1m: "0.14",
        cached_input_per_1m: "0.0028",
        output_per_1m: "0.28",
        prompt_per_1k_usd: "0.00014",
        cache_prompt_per_1k_usd: "0.0000028",
        completion_per_1k_usd: "0.00028",
        verification_status: "verified",
        valid_from: now,
        valid_until: null,
        region: "global",
        token_tier: "all",
        mode: "openai-compatible",
        context_window_tokens: 1000000,
        max_output_tokens: 384000,
        source_hash: "a".repeat(64),
        source_excerpt: "Official pricing excerpt",
        notes: "Official source fixture",
        blocks_usd_rollup: false,
      },
    ],
  };
}

function fetchForSettings(settings: Record<string, unknown>) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = requestPath(input);
    if (path === "/api/settings/models" && !init?.method) return jsonResponse(settings);
    if (path === "/api/settings/models" && init?.method === "PUT") return jsonResponse(JSON.parse(String(init.body)));
    if (path === "/api/settings/models/health") return jsonResponse({ items: [] });
    if (path === "/api/settings/models/fallbacks") return jsonResponse(fallbackSummaryPayload());
    if (path === "/api/settings/models/pricing-sources") return jsonResponse(pricingSourcesPayload());
    return jsonResponse({ detail: `unexpected ${path}` }, 404);
  });
}

function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/settings/models"]}>
      <QueryClientProvider client={queryClient}>
        <ModelSettingsPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("ModelSettingsPage", () => {
  it("uses the platform-managed allowlist in the documented order and default", () => {
    const [platform, ollama, custom] = modelCatalog;
    expect(platform).toMatchObject({
      providerId: managedProvider,
      baseUrl: "https://ai.112102.xyz/v1",
      apiFormat: "openai",
      apiKeyEnv: "AI_PROVIDER_API_KEY",
      managedByPlatform: true,
    });
    expect(platform.models.map((model) => model.model)).toEqual([
      "deepseek-v4-flash", "gpt-oss-120b", "mimo-v2.5", "minimax-m3", "nvidia-gpt-oss",
    ]);
    expect(ollama.providerId).toBe("ollama");
    expect(custom.providerId).toBe("custom");
  });

  it("shows server-managed status and disables switching when the server API key is missing", async () => {
    renderPage(fetchForSettings(modelSettingsPayload(false)));

    expect(await screen.findByRole("button", { name: /平台托管模型.*1 个模型/ })).toBeInTheDocument();
    const unavailable = await screen.findByRole("button", { name: /minimax-m3 服务端未配置/ });
    expect(unavailable).toBeDisabled();
    expect(screen.getAllByText("服务端托管").length).toBeGreaterThan(0);
    expect(screen.queryByLabelText(/接口访问密钥/)).not.toBeInTheDocument();
  });

  it("switches among platform models after the backend reports its key configured", async () => {
    const settings = modelSettingsPayload(true);
    settings.providers.push({
      ...settings.providers[0],
      label: "GPT OSS 120B",
      model: "gpt-oss-120b",
    });
    const fetchMock = fetchForSettings(settings);
    const user = userEvent.setup();
    renderPage(fetchMock);

    await user.click(await screen.findByRole("button", { name: /gpt-oss-120b 切换/ }));
    await waitFor(() => {
      const saveCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input) === "/api/settings/models" && init?.method === "PUT",
      );
      expect(saveCall).toBeDefined();
      expect(JSON.parse(String(saveCall?.[1]?.body))).toMatchObject({
        default_provider: managedProvider,
        default_model: "gpt-oss-120b",
        providers: expect.arrayContaining([
          expect.objectContaining({
            name: managedProvider,
            model: "gpt-oss-120b",
            managed_by_platform: true,
          }),
        ]),
      });
      expect(String(saveCall?.[1]?.body)).not.toContain("sk-");
    });
  });

  it("only offers platform models returned by the server allowlist", async () => {
    renderPage(fetchForSettings(modelSettingsPayload(true)));

    expect(await screen.findByRole("button", { name: /平台托管模型.*1 个模型/ })).toBeInTheDocument();
    expect(screen.getAllByText("minimax-m3").length).toBeGreaterThan(0);
    expect(screen.queryByText("gpt-oss-120b")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /gpt-oss-120b 切换/ })).not.toBeInTheDocument();
  });

  it("renders an allowed runtime model even when it is absent from the static catalog", async () => {
    const settings = modelSettingsPayload(true);
    settings.default_model = "runtime-only-model";
    settings.providers[0].model = "runtime-only-model";
    settings.providers[0].label = "runtime-only-model";
    renderPage(fetchForSettings(settings));

    expect(await screen.findByRole("button", { name: /平台托管模型.*1 个模型/ })).toBeInTheDocument();
    expect(screen.getAllByText("runtime-only-model").length).toBeGreaterThan(0);
  });

  it("does not advertise platform models before the backend allowlist loads", () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (requestPath(input) === "/api/settings/models") {
        return new Promise<Response>(() => undefined);
      }
      return Promise.resolve(jsonResponse({ detail: "not ready" }, 503));
    });

    renderPage(fetchMock);

    expect(screen.getByRole("button", { name: /平台托管模型.*0 个模型/ })).toBeInTheDocument();
    expect(screen.queryByText("deepseek-v4-flash")).not.toBeInTheDocument();
    expect(screen.queryByText("gpt-oss-120b")).not.toBeInTheDocument();
  });

  it("keeps the platform catalog empty when the backend allowlist fails", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (requestPath(input) === "/api/settings/models") {
        return jsonResponse({ detail: "model settings unavailable" }, 503);
      }
      return jsonResponse({ detail: "not ready" }, 503);
    });

    renderPage(fetchMock);

    expect(await screen.findByText("平台模型列表暂不可用，恢复服务端连接后会自动同步。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /平台托管模型.*0 个模型/ })).toBeInTheDocument();
    expect(screen.queryByText("deepseek-v4-flash")).not.toBeInTheDocument();
  });

  it("refreshes both Harness health and official status on demand", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/settings/models" && !init?.method) return jsonResponse(modelSettingsPayload());
      if (path === "/api/settings/models/health") {
        return jsonResponse({
          items: [{ provider: managedProvider, model: "deepseek-v4-flash", status: "healthy", mode: "configured", latency_ms: 42, error_message: null }],
        });
      }
      if (path === "/api/settings/models/official-status") {
        return jsonResponse({
          items: [{ provider: "platform", label: "Platform Status", status: "operational", description: "All systems operational", page_url: "https://status.example.com", api_url: "https://status.example.com/api", checked_at: "2026-05-30T00:00:00Z", updated_at: null, error_message: null }],
        });
      }
      if (path === "/api/settings/models/fallbacks") return jsonResponse(fallbackSummaryPayload());
      if (path === "/api/settings/models/pricing-sources") return jsonResponse(pricingSourcesPayload());
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    const user = userEvent.setup();
    renderPage(fetchMock);

    await user.click(await screen.findByRole("button", { name: "刷新模型状态" }));

    expect(await screen.findByText("All systems operational")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Platform Status 官方状态页" })).toHaveAttribute("href", "https://status.example.com");
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input]) => requestPath(input) === "/api/settings/models/health")).toBe(true);
      expect(fetchMock.mock.calls.some(([input]) => requestPath(input) === "/api/settings/models/official-status")).toBe(true);
    });
  });

  it("aggregates configured platform models into one provider row", async () => {
    const settings = modelSettingsPayload(true);
    settings.providers.push({
      ...settings.providers[0],
      label: "GPT OSS 120B",
      model: "gpt-oss-120b",
    });
    renderPage(fetchForSettings(settings));

    expect(await screen.findByRole("button", { name: /平台托管模型.*2 个模型/ })).toBeInTheDocument();
    const providerRows = await screen.findAllByText("平台托管模型");
    expect(providerRows.filter((node) => node.closest("tr"))).toHaveLength(1);
    const row = providerRows.find((node) => node.closest("tr"))?.closest("tr");
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).queryByText("env_platform")).not.toBeInTheDocument();
    expect(within(row as HTMLElement).getByText("服务端托管")).toBeInTheDocument();
    expect(within(row as HTMLElement).getAllByText("minimax-m3")).toHaveLength(2);
    expect(within(row as HTMLElement).getAllByText("gpt-oss-120b")).toHaveLength(2);
  });

  it("lets the Ollama local provider switch without requiring an API key", async () => {
    const settings = {
      ...modelSettingsPayload(true),
      providers: [
        ...modelSettingsPayload(true).providers,
        {
          name: "ollama",
          label: "Ollama / Local",
          provider_id: "ollama",
          model: "llama3.1",
          api_format: "openai",
          base_url: "http://127.0.0.1:11434/v1",
          api_key_env: "",
          secret_provider: "ollama",
          isLocal: true,
          api_key_configured: false,
        },
      ],
    };
    const fetchMock = fetchForSettings(settings);
    const user = userEvent.setup();
    renderPage(fetchMock);

    await user.click(await screen.findByRole("button", { name: /Ollama \/ Local/ }));
    await user.click(await screen.findByRole("button", { name: /llama3\.1 启用/ }));
    expect(screen.queryByRole("dialog", { name: /配置 Ollama/ })).not.toBeInTheDocument();
    await waitFor(() => {
      const saveCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input) === "/api/settings/models" && init?.method === "PUT",
      );
      expect(JSON.parse(String(saveCall?.[1]?.body))).toMatchObject({ default_provider: "ollama", default_model: "llama3.1" });
    });
  });

  it("keeps custom provider configuration available", async () => {
    const fetchMock = fetchForSettings(modelSettingsPayload(true));
    const user = userEvent.setup();
    renderPage(fetchMock);

    await user.click(await screen.findByLabelText("打开快捷操作"));
    await user.click(screen.getAllByRole("button", { name: "添加自定义模型" })[0]);
    const dialog = await screen.findByRole("dialog", { name: "添加自定义供应商" });
    await user.clear(within(dialog).getByLabelText("供应商标识"));
    await user.type(within(dialog).getByLabelText("供应商标识"), "custom-llm");
    await user.clear(within(dialog).getByLabelText("模型名称"));
    await user.type(within(dialog).getByLabelText("模型名称"), "custom-model");
    await user.type(within(dialog).getByLabelText(/接口基础地址/), "https://api.example.com/v1");
    await user.type(within(dialog).getByLabelText(/接口访问密钥/), "sk-custom-test");
    await user.click(within(dialog).getByRole("button", { name: /保存并启用/ }));

    await waitFor(() => {
      const saveCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input) === "/api/settings/models" && init?.method === "PUT",
      );
      expect(JSON.parse(String(saveCall?.[1]?.body))).toMatchObject({
        default_provider: "custom-llm",
        default_model: "custom-model",
        providers: expect.arrayContaining([
          expect.objectContaining({
            name: "custom-llm",
            secret_provider: "custom-llm",
            api_key: "sk-custom-test",
          }),
        ]),
      });
    });
  }, 10_000);

  it("requires a key before a custom provider can be saved", async () => {
    const fetchMock = fetchForSettings(modelSettingsPayload(true));
    const user = userEvent.setup();
    renderPage(fetchMock);

    await user.click(await screen.findByLabelText("打开快捷操作"));
    await user.click(screen.getAllByRole("button", { name: "添加自定义模型" })[0]);
    const dialog = await screen.findByRole("dialog", { name: "添加自定义供应商" });
    await user.clear(within(dialog).getByLabelText("供应商标识"));
    await user.type(within(dialog).getByLabelText("供应商标识"), "key-required");
    await user.clear(within(dialog).getByLabelText("模型名称"));
    await user.type(within(dialog).getByLabelText("模型名称"), "key-required-model");
    await user.type(within(dialog).getByLabelText(/接口基础地址/), "https://api.example.com/v1");
    expect(within(dialog).getByLabelText(/接口访问密钥/)).toBeRequired();
    await user.click(within(dialog).getByRole("button", { name: /保存并启用/ }));

    expect(fetchMock.mock.calls.some(([input, init]) => requestPath(input) === "/api/settings/models" && init?.method === "PUT")).toBe(false);
  }, 10_000);

  it("keeps independent pricing source rendering", async () => {
    renderPage(fetchForSettings(modelSettingsPayload(true)));
    expect(await screen.findByRole("link", { name: "官方来源 DeepSeek Flash" })).toBeInTheDocument();
    expect(screen.getAllByText("deepseek-v4-flash").length).toBeGreaterThan(0);
    expect(screen.getByText("已验证")).toBeInTheDocument();
  });

  it("uses bundled pricing sources when an older backend does not expose the endpoint", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/settings/models" && !init?.method) return jsonResponse(modelSettingsPayload());
      if (path === "/api/settings/models/health") return jsonResponse({ items: [] });
      if (path === "/api/settings/models/fallbacks") return jsonResponse(fallbackSummaryPayload());
      if (path === "/api/settings/models/pricing-sources") return jsonResponse({ detail: "Not Found" }, 404);
      if (path === "/model_pricing_sources.json") {
        return jsonResponse({ ...pricingSourcesPayload(), rows: pricingSourcesPayload().items });
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    renderPage(fetchMock);

    expect(await screen.findByRole("link", { name: "官方来源 DeepSeek Flash" })).toBeInTheDocument();
    expect(screen.queryByText("成本来源暂不可用")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input]) => requestPath(input) === "/model_pricing_sources.json")).toBe(true);
    });
  });
});
