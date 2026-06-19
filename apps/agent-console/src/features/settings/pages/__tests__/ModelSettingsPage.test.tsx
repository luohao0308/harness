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

import { ModelSettingsPage } from "../ModelSettingsPage";

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

function modelSettingsPayload() {
  return {
    default_provider: "openai-compatible",
    default_model: "gpt-5.5",
    providers: [
      {
        name: "openai-compatible",
        label: "OpenAI GPT-5.5",
        model: "gpt-5.5",
        api_format: "openai",
        base_url: "https://api.openai.com/v1",
      },
    ],
    rate_limits: { rpm: 600, tpm: 120000 },
    health: {
      status: "healthy",
      updated_at: null,
      mode: "mock",
      latency_ms: 0,
      error_message: null,
    },
    circuit_breaker: { failure_threshold: 3, cooldown_seconds: 60 },
  };
}

function fallbackSummaryPayload() {
  return {
    organization_id: "dev-org",
    fallback_total: 0,
    primary_failure_total: 0,
    providers: [],
    recent_events: [],
  };
}

function pricingSourcesPayload() {
  const now = "2026-05-30T00:00:00Z";
  const source = (
    displayName: string,
    provider: string,
    model: string,
    currency: string,
    input: string | null,
    cached: string | null,
    output: string | null,
    promptUsd: string | null,
    cacheUsd: string | null,
    completionUsd: string | null,
    status: string,
    blocks: boolean,
  ) => ({
    provider,
    model,
    mapped_provider: provider,
    mapped_model: model,
    display_name: displayName,
    official_url:
      provider.startsWith("deepseek")
        ? "https://api-docs.deepseek.com/quick_start/pricing"
        : provider === "openai-compatible"
          ? "https://developers.openai.com/api/docs/pricing"
        : provider === "kimi"
            ? "https://platform.kimi.ai/docs/pricing/chat-k26"
            : "https://docs.z.ai/guides/overview/pricing",
    retrieved_at: now,
    unit: "per_1m_tokens",
    currency,
    input_per_1m: input,
    cached_input_per_1m: cached,
    output_per_1m: output,
    prompt_per_1k_usd: promptUsd,
    cache_prompt_per_1k_usd: cacheUsd,
    completion_per_1k_usd: completionUsd,
    verification_status: status,
    valid_from: now,
    valid_until: null,
    region: blocks ? "official-currency-dependent" : "global",
    token_tier: blocks ? "tiered" : "all",
    mode: provider === "kimi" ? "chat-k26" : "openai-compatible",
    context_window_tokens:
      provider === "openai-compatible" && model.startsWith("gpt-5.")
        ? 272000
        : provider === "kimi"
          ? 262144
          : provider === "z-ai"
            ? 200000
            : 1000000,
    max_output_tokens: provider.startsWith("deepseek") ? 384000 : null,
    source_hash: "a".repeat(64),
    source_excerpt: "Official pricing excerpt",
    notes: "Official source fixture",
    blocks_usd_rollup: blocks,
  });
  return {
    schema_version: "model_pricing_sources.v1",
    retrieved_at: now,
    parser_version: "manual-official-source-2026-05-30",
    blocking_statuses: [
      "missing_pricing",
      "price_unverified",
      "sku_ambiguous",
      "currency_conversion_required",
      "stale",
      "invalid_pricing",
    ],
    items: [
      source("DeepSeek Flash", "deepseek-flash", "deepseek-v4-flash", "USD", "0.14", "0.0028", "0.28", "0.00014", "0.0000028", "0.00028", "verified", false),
      source("DeepSeek Pro", "deepseek-pro", "deepseek-v4-pro", "USD", "0.435", "0.003625", "0.87", "0.000435", "0.000003625", "0.00087", "verified", false),
      source("OpenAI GPT-5.5", "openai-compatible", "gpt-5.5", "USD", "5", "0.5", "30", "0.005", "0.0005", "0.030", "verified", false),
      source("Kimi K2.6", "kimi", "kimi-k2.6", "USD", "0.95", "0.16", "4.00", "0.00095", "0.00016", "0.00400", "verified", false),
      source("Z.AI GLM-5.1", "z-ai", "glm-5.1", "USD", "1.4", "0.26", "4.4", "0.0014", "0.00026", "0.0044", "verified", false),
    ],
  };
}

function bundledPricingSourcesPayload() {
  const payload = pricingSourcesPayload();
  return {
    ...payload,
    rows: payload.items,
  };
}

function pricingSourcesWithBlockedRowPayload() {
  const payload = pricingSourcesPayload();
  return {
    ...payload,
    retrieved_at: "2026-06-03T23:59:00Z",
    items: [
      ...payload.items,
      {
        ...payload.items[0],
        provider: "blocked-provider",
        model: "blocked-model",
        mapped_provider: "blocked-provider",
        mapped_model: "blocked-model",
        display_name: "Blocked Pricing Model",
        verification_status: "stale",
        valid_until: "2026-06-03T23:59:00Z",
        blocks_usd_rollup: true,
        region: "official-currency-dependent",
        token_tier: "tiered",
      },
    ],
  };
}

function modelHealthPayload() {
  return {
    items: [
      {
        provider: "openai-compatible",
        model: "gpt-5.5",
        status: "unhealthy",
        mode: "probe",
        checked_at: "2026-06-03T14:40:00Z",
        latency_ms: 732,
        error_message: "401 invalid_api_key",
        circuit_status: "closed",
        circuit_open_until: null,
        consecutive_failures: 1,
      },
    ],
  };
}

function officialStatusPayload() {
  return {
    items: [
      {
        provider: "openai",
        label: "OpenAI",
        status: "operational",
        indicator: "none",
        description: "All Systems Operational",
        page_url: "https://status.openai.com/",
        api_url: "https://status.openai.com/api/v2/status.json",
        checked_at: "2026-06-03T14:40:00Z",
        updated_at: "2026-04-27T15:52:49Z",
        error_message: null,
      },
      {
        provider: "deepseek",
        label: "DeepSeek",
        status: "unknown",
        indicator: "unknown",
        description: "官方状态暂不可查",
        page_url: "https://status.deepseek.com/",
        api_url: "https://status.deepseek.com/",
        checked_at: "2026-06-03T14:40:00Z",
        updated_at: null,
        error_message: "connection reset",
      },
    ],
  };
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

async function findPricingRow(displayName: string) {
  await waitFor(() => {
    expect(screen.getByRole("link", { name: `官方来源 ${displayName}` })).toBeInTheDocument();
  });
  const row = screen.getByRole("link", { name: `官方来源 ${displayName}` }).closest("tr");
  expect(row).not.toBeNull();
  return row as HTMLElement;
}

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("ModelSettingsPage", () => {
  it("puts model switching before gateway status", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === "/api/settings/models") return jsonResponse(modelSettingsPayload());
      if (path === "/api/settings/models/health") return jsonResponse({ items: [] });
      if (path === "/api/settings/models/fallbacks") return jsonResponse(fallbackSummaryPayload());
      if (path === "/api/settings/models/pricing-sources") return jsonResponse(pricingSourcesPayload());
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    renderPage(fetchMock);

    await screen.findByText("模型切换");
    const pageText = document.body.textContent ?? "";

    expect(pageText.indexOf("模型切换")).toBeGreaterThanOrEqual(0);
    expect(pageText.indexOf("模型网关")).toBeGreaterThanOrEqual(0);
    expect(pageText.indexOf("模型切换")).toBeLessThan(pageText.indexOf("模型网关"));
  });

  it("manually refreshes Harness model health and official provider status", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === "/api/settings/models") return jsonResponse(modelSettingsPayload());
      if (path === "/api/settings/models/health") return jsonResponse(modelHealthPayload());
      if (path === "/api/settings/models/official-status") return jsonResponse(officialStatusPayload());
      if (path === "/api/settings/models/fallbacks") return jsonResponse(fallbackSummaryPayload());
      if (path === "/api/settings/models/pricing-sources") return jsonResponse(pricingSourcesPayload());
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    const user = userEvent.setup();
    renderPage(fetchMock);

    await screen.findByText("Harness 探测");
    expect(fetchMock.mock.calls.some(([input]) => requestPath(input) === "/api/settings/models/health")).toBe(false);
    expect(fetchMock.mock.calls.some(([input]) => requestPath(input) === "/api/settings/models/official-status")).toBe(false);

    await user.click(screen.getByRole("button", { name: "刷新模型状态" }));

    expect(await screen.findByText("401 invalid_api_key")).toBeInTheDocument();
    expect(screen.getByText("All Systems Operational")).toBeInTheDocument();
    expect(screen.getByText("官方状态暂不可查")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "OpenAI 官方状态页" })).toHaveAttribute(
      "href",
      "https://status.openai.com/",
    );
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input]) => requestPath(input) === "/api/settings/models/health")).toBe(true);
      expect(fetchMock.mock.calls.some(([input]) => requestPath(input) === "/api/settings/models/official-status")).toBe(true);
    });
  });

  it("requires preset API key configuration before switching and releases after save succeeds", async () => {
    const savedSettings = {
      ...modelSettingsPayload(),
      default_provider: "deepseek-flash",
      default_model: "deepseek-v4-flash",
      providers: [
        ...modelSettingsPayload().providers,
        {
          name: "deepseek-flash",
          label: "DeepSeek Flash",
          model: "deepseek-v4-flash",
          api_format: "openai",
          base_url: "https://api.deepseek.com",
          api_key: "sk-deepseek-test",
        },
      ],
    };
    let settingsGetCount = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/settings/models" && !init?.method) {
        settingsGetCount += 1;
        if (settingsGetCount > 1) {
          return new Promise<Response>(() => undefined);
        }
        return jsonResponse(modelSettingsPayload());
      }
      if (path === "/api/settings/models" && init?.method === "PUT") {
        return jsonResponse(savedSettings);
      }
      if (path === "/api/settings/models/health") {
        return new Promise<Response>(() => undefined);
      }
      if (path === "/api/settings/models/fallbacks") {
        return jsonResponse(fallbackSummaryPayload());
      }
      if (path === "/api/settings/models/pricing-sources") {
        return jsonResponse(pricingSourcesPayload());
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    const user = userEvent.setup();
    renderPage(fetchMock);

    await user.click(await screen.findByRole("button", { name: /DeepSeek.*2 个模型/ }));
    await user.click(await screen.findByRole("button", { name: /deepseek-v4-flash 配置并启用/ }));
    const dialog = await screen.findByRole("dialog", { name: /配置 DeepSeek Flash/ });
    await user.type(within(dialog).getByLabelText(/接口访问密钥/), "sk-deepseek-test");
    await user.click(within(dialog).getByRole("button", { name: /保存并启用/ }));

    expect((await screen.findAllByText("模型配置已保存")).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /deepseek-v4-flash 已启用/ })).toBeInTheDocument();
    expect(screen.queryByText("切换中")).not.toBeInTheDocument();
    await waitFor(() => {
      const saveCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/settings/models" && init?.method === "PUT",
      );
      expect(saveCall).toBeDefined();
      expect(JSON.parse(String(saveCall?.[1]?.body))).toMatchObject({
        default_provider: "deepseek-flash",
        default_model: "deepseek-v4-flash",
        providers: expect.arrayContaining([
          expect.objectContaining({
            name: "openai-compatible",
          }),
          expect.objectContaining({
            name: "deepseek-flash",
            secret_provider: "deepseek",
            api_key: "sk-deepseek-test",
          }),
        ]),
      });
    });
  });

  it("lets the active preset open configuration when its API key is missing", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/settings/models" && !init?.method) return jsonResponse(modelSettingsPayload());
      if (path === "/api/settings/models" && init?.method === "PUT") {
        return jsonResponse(JSON.parse(String(init.body)));
      }
      if (path === "/api/settings/models/health") return jsonResponse({ items: [] });
      if (path === "/api/settings/models/fallbacks") return jsonResponse(fallbackSummaryPayload());
      if (path === "/api/settings/models/pricing-sources") {
        return jsonResponse(pricingSourcesPayload());
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    const user = userEvent.setup();
    renderPage(fetchMock);

    await screen.findByRole("button", { name: /gpt-5\.5 配置并启用/ });
    expect(screen.queryByRole("button", { name: /gpt-5\.5 已启用/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /gpt-5\.5 配置并启用/ }));

    expect(await screen.findByRole("dialog", { name: /配置 OpenAI GPT-5.5/ })).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("OpenAI · openai");
  });

  it("treats stored model secrets as configured without exposing raw API keys", async () => {
    const settings = {
      ...modelSettingsPayload(),
      providers: [
        {
          ...modelSettingsPayload().providers[0],
          api_key_configured: true,
          api_key_source: "stored_secret_org",
          api_key_secret_id: "secret-openai",
        },
      ],
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/settings/models" && !init?.method) return jsonResponse(settings);
      if (path === "/api/settings/models" && init?.method === "PUT") {
        return jsonResponse(JSON.parse(String(init.body)));
      }
      if (path === "/api/settings/models/health") return jsonResponse({ items: [] });
      if (path === "/api/settings/models/fallbacks") return jsonResponse(fallbackSummaryPayload());
      if (path === "/api/settings/models/pricing-sources") return jsonResponse(pricingSourcesPayload());
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    renderPage(fetchMock);

    await screen.findAllByText("组织密钥");
    expect(screen.getAllByText("已配置").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /gpt-5\.5 已启用/ })).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("sk-");
  });

  it("reuses a configured DeepSeek key when switching between DeepSeek models", async () => {
    const settings = {
      ...modelSettingsPayload(),
      default_provider: "deepseek-flash",
      default_model: "deepseek-v4-flash",
      providers: [
        {
          name: "deepseek-flash",
          label: "DeepSeek Flash",
          model: "deepseek-v4-flash",
          model_kind: "文本模型",
          api_format: "openai",
          base_url: "https://api.deepseek.com",
          api_key_configured: true,
          api_key_source: "stored_secret_org",
          api_key_secret_id: "secret-deepseek",
        },
      ],
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/settings/models" && !init?.method) return jsonResponse(settings);
      if (path === "/api/settings/models" && init?.method === "PUT") {
        return jsonResponse(JSON.parse(String(init.body)));
      }
      if (path === "/api/settings/models/health") return jsonResponse({ items: [] });
      if (path === "/api/settings/models/fallbacks") return jsonResponse(fallbackSummaryPayload());
      if (path === "/api/settings/models/pricing-sources") return jsonResponse(pricingSourcesPayload());
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    const user = userEvent.setup();
    renderPage(fetchMock);

    const proSwitch = await screen.findByRole("button", { name: /deepseek-v4-pro 切换/ });
    expect(screen.queryByRole("button", { name: /deepseek-v4-pro 配置并启用/ })).not.toBeInTheDocument();

    await user.click(proSwitch);

    await waitFor(() => {
      const saveCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/settings/models" && init?.method === "PUT",
      );
      expect(saveCall).toBeDefined();
      expect(JSON.parse(String(saveCall?.[1]?.body))).toMatchObject({
        default_provider: "deepseek-pro",
        default_model: "deepseek-v4-pro",
        providers: expect.arrayContaining([
          expect.objectContaining({
            name: "deepseek-flash",
            api_key_configured: true,
            api_key_source: "stored_secret_org",
            api_key_secret_id: "secret-deepseek",
          }),
          expect.objectContaining({
            name: "deepseek-pro",
            model: "deepseek-v4-pro",
            api_key: "",
            api_key_configured: true,
            api_key_source: "stored_secret_org",
            api_key_secret_id: "secret-deepseek",
          }),
        ]),
      });
    });
    expect(document.body).not.toHaveTextContent("sk-");
  });

  it("adds another model under a configured provider without resending the raw key or changing default", async () => {
    const settings = {
      ...modelSettingsPayload(),
      default_provider: "openai-compatible",
      default_model: "gpt-5.5",
      providers: [
        {
          ...modelSettingsPayload().providers[0],
          secret_provider: "openai",
          api_key_configured: true,
          api_key_source: "stored_secret_org",
          api_key_secret_id: "secret-openai",
        },
      ],
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/settings/models" && !init?.method) return jsonResponse(settings);
      if (path === "/api/settings/models" && init?.method === "PUT") {
        return jsonResponse(JSON.parse(String(init.body)));
      }
      if (path === "/api/settings/models/health") return jsonResponse({ items: [] });
      if (path === "/api/settings/models/fallbacks") return jsonResponse(fallbackSummaryPayload());
      if (path === "/api/settings/models/pricing-sources") return jsonResponse(pricingSourcesPayload());
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    const user = userEvent.setup();
    renderPage(fetchMock);

    const sparkAdd = await screen.findByRole("button", {
      name: /gpt-5\.3-codex-spark 添加/,
    });
    await user.click(sparkAdd);
    const dialog = await screen.findByRole("dialog", { name: /添加模型 gpt-5\.3-codex-spark/ });
    expect(within(dialog).getByLabelText("共享密钥标识")).toHaveValue("openai");
    expect(within(dialog).getByLabelText(/接口访问密钥/)).not.toBeRequired();
    await user.click(within(dialog).getByRole("button", { name: /保存模型/ }));

    await waitFor(() => {
      const saveCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/settings/models" && init?.method === "PUT",
      );
      expect(saveCall).toBeDefined();
      const body = JSON.parse(String(saveCall?.[1]?.body));
      expect(body).toMatchObject({
        default_provider: "openai-compatible",
        default_model: "gpt-5.5",
        providers: expect.arrayContaining([
          expect.objectContaining({
            name: "openai-compatible",
            model: "gpt-5.5",
            secret_provider: "openai",
          }),
          expect.objectContaining({
            name: "openai-gpt-5-3-codex-spark",
            model: "gpt-5.3-codex-spark",
            secret_provider: "openai",
            api_key: "",
            api_key_configured: true,
            api_key_source: "stored_secret_org",
            api_key_secret_id: "secret-openai",
          }),
        ]),
      });
      expect(String(saveCall?.[1]?.body)).not.toContain("sk-");
    });
  });

  it("filters the provider rail and model rows by provider or model search", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === "/api/settings/models") return jsonResponse(modelSettingsPayload());
      if (path === "/api/settings/models/health") return jsonResponse({ items: [] });
      if (path === "/api/settings/models/fallbacks") return jsonResponse(fallbackSummaryPayload());
      if (path === "/api/settings/models/pricing-sources") return jsonResponse(pricingSourcesPayload());
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    const user = userEvent.setup();
    renderPage(fetchMock);

    expect(await screen.findByRole("button", { name: /OpenAI.*2 个模型/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /DeepSeek.*2 个模型/ })).toBeInTheDocument();

    const search = screen.getByLabelText("搜索供应商或模型");
    await user.type(search, "qwen");

    expect(screen.getByRole("button", { name: /Qwen.*1 个模型/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /OpenAI.*2 个模型/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /qwen-max-latest 配置并启用/ })).toBeInTheDocument();

    await user.clear(search);
    await user.type(search, "spark");

    expect(screen.getByRole("button", { name: /OpenAI.*2 个模型/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /gpt-5\.3-codex-spark 配置并启用/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /gpt-5\.5 配置并启用/ })).not.toBeInTheDocument();
  });

  it("opens custom model configuration from the quick action instead of rendering the form inline", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/settings/models" && !init?.method) return jsonResponse(modelSettingsPayload());
      if (path === "/api/settings/models" && init?.method === "PUT") {
        return jsonResponse(JSON.parse(String(init.body)));
      }
      if (path === "/api/settings/models/health") return jsonResponse({ items: [] });
      if (path === "/api/settings/models/fallbacks") return jsonResponse(fallbackSummaryPayload());
      if (path === "/api/settings/models/pricing-sources") {
        return jsonResponse(pricingSourcesPayload());
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    const user = userEvent.setup();
    renderPage(fetchMock);

    await screen.findByText("模型切换");
    expect(screen.queryByLabelText("供应商标识")).not.toBeInTheDocument();

    await user.click(screen.getByLabelText("打开快捷操作"));
    await user.click(screen.getAllByRole("button", { name: "添加自定义模型" })[0]);

    const dialog = await screen.findByRole("dialog", { name: "添加自定义供应商" });
    expect(within(dialog).getByLabelText("共享密钥标识")).toBeInTheDocument();
    await user.clear(within(dialog).getByLabelText("供应商标识"));
    await user.type(within(dialog).getByLabelText("供应商标识"), "custom-llm");
    await user.clear(within(dialog).getByLabelText("显示名称"));
    await user.type(within(dialog).getByLabelText("显示名称"), "Custom LLM");
    await user.clear(within(dialog).getByLabelText("模型名称"));
    await user.type(within(dialog).getByLabelText("模型名称"), "custom-model");
    await user.type(within(dialog).getByLabelText(/接口基础地址/), "https://api.example.com/v1");
    await user.type(within(dialog).getByLabelText(/接口访问密钥/), "sk-custom-test");
    await user.click(within(dialog).getByRole("button", { name: /保存并启用/ }));

    await waitFor(() => {
      const saveCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/settings/models" && init?.method === "PUT",
      );
      expect(saveCall).toBeDefined();
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
  });

  it("renders official-source built-in model pricing and blocking gates", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === "/api/settings/models") return jsonResponse(modelSettingsPayload());
      if (path === "/api/settings/models/health") return jsonResponse({ items: [] });
      if (path === "/api/settings/models/fallbacks") return jsonResponse(fallbackSummaryPayload());
      if (path === "/api/settings/models/pricing-sources") {
        return jsonResponse(pricingSourcesPayload());
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    renderPage(fetchMock);

    await screen.findByText("内置模型成本");
    expect(within(await findPricingRow("DeepSeek Flash")).getByText("deepseek-v4-flash")).toBeInTheDocument();
    expect(within(await findPricingRow("OpenAI GPT-5.5")).getByText("gpt-5.5")).toBeInTheDocument();
    expect(within(await findPricingRow("Kimi K2.6")).getByText("kimi-k2.6")).toBeInTheDocument();
    expect(within(await findPricingRow("Z.AI GLM-5.1")).getByText("glm-5.1")).toBeInTheDocument();
    expect(screen.getAllByText("已验证")).toHaveLength(5);
    const deepSeekProRow = await findPricingRow("DeepSeek Pro");
    expect(within(deepSeekProRow).getByText("输入 USD 0.435")).toBeInTheDocument();
    expect(within(deepSeekProRow).queryByText("已过期")).not.toBeInTheDocument();
    expect(within(deepSeekProRow).queryByText(/有效至/)).not.toBeInTheDocument();
    const kimiRow = await findPricingRow("Kimi K2.6");
    expect(within(kimiRow).getByText("输入 USD 0.95")).toBeInTheDocument();
    expect(within(kimiRow).getByText("已验证")).toBeInTheDocument();
    expect(screen.queryByText("USD 汇总已阻塞")).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("openai-compatible/gpt");
  });

  it("softens blocked pricing rows and renders timestamps in 24-hour time", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === "/api/settings/models") return jsonResponse(modelSettingsPayload());
      if (path === "/api/settings/models/health") return jsonResponse({ items: [] });
      if (path === "/api/settings/models/fallbacks") return jsonResponse(fallbackSummaryPayload());
      if (path === "/api/settings/models/pricing-sources") {
        return jsonResponse(pricingSourcesWithBlockedRowPayload());
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    renderPage(fetchMock);

    const row = (await screen.findByText("Blocked Pricing Model")).closest("tr");

    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText("已过期")).toBeInTheDocument();
    expect(within(row as HTMLElement).getByText("不计入汇总")).toBeInTheDocument();
    expect(within(row as HTMLElement).getByText(/有效至/).textContent).toMatch(/\d{2}:\d{2}:\d{2}/);
    expect(document.body).not.toHaveTextContent("USD 汇总已阻塞");
    expect(document.body).not.toHaveTextContent(/\b(?:AM|PM)\b/);
  });

  it("falls back to bundled official pricing when the backend pricing endpoint is missing", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === "/api/settings/models") return jsonResponse(modelSettingsPayload());
      if (path === "/api/settings/models/health") return jsonResponse({ items: [] });
      if (path === "/api/settings/models/fallbacks") return jsonResponse(fallbackSummaryPayload());
      if (path === "/api/settings/models/pricing-sources") {
        return jsonResponse({ detail: "Not Found" }, 404);
      }
      if (path === "/model_pricing_sources.json") {
        return jsonResponse(bundledPricingSourcesPayload());
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    renderPage(fetchMock);

    expect(within(await findPricingRow("DeepSeek Flash")).getByText("deepseek-v4-flash")).toBeInTheDocument();
    expect(within(await findPricingRow("OpenAI GPT-5.5")).getByText("gpt-5.5")).toBeInTheDocument();
    expect(within(await findPricingRow("Kimi K2.6")).getByText("kimi-k2.6")).toBeInTheDocument();
    expect(within(await findPricingRow("Z.AI GLM-5.1")).getByText("glm-5.1")).toBeInTheDocument();
    expect(screen.queryByText("成本来源暂不可用")).not.toBeInTheDocument();
    expect(screen.queryByText(/价格来源接口返回 404/)).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("404: Not Found");
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input]) => requestPath(input) === "/model_pricing_sources.json")).toBe(true);
    });
  });

  it("shows model ids as switch card titles with model type and one OpenAI built-in preset", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === "/api/settings/models") return jsonResponse(modelSettingsPayload());
      if (path === "/api/settings/models/health") return jsonResponse({ items: [] });
      if (path === "/api/settings/models/fallbacks") return jsonResponse(fallbackSummaryPayload());
      if (path === "/api/settings/models/pricing-sources") {
        return jsonResponse(pricingSourcesPayload());
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    renderPage(fetchMock);

    const openAiPresetButtons = await screen.findAllByRole("button", { name: /gpt-5\.5 (配置并启用|切换|已启用)/ });
    const gpt55Card = openAiPresetButtons[0].closest("[class*='min-h-']");

    expect(gpt55Card).not.toBeNull();
    expect(openAiPresetButtons).toHaveLength(1);
    await waitFor(() => {
      expect(within(gpt55Card as HTMLElement).getByText("gpt-5.5")).toBeInTheDocument();
      expect(within(gpt55Card as HTMLElement).getByText("推理模型")).toBeInTheDocument();
      expect(within(gpt55Card as HTMLElement).queryByText("OpenAI · openai")).not.toBeInTheDocument();
      expect(gpt55Card as HTMLElement).not.toHaveTextContent("https://api.openai.com/v1");
    });
  });

  it("shows preset supplier rows with clickable endpoint links even before provider configuration", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === "/api/settings/models") return jsonResponse(modelSettingsPayload());
      if (path === "/api/settings/models/health") return jsonResponse({ items: [] });
      if (path === "/api/settings/models/fallbacks") return jsonResponse(fallbackSummaryPayload());
      if (path === "/api/settings/models/pricing-sources") {
        return jsonResponse(pricingSourcesPayload());
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    renderPage(fetchMock);

    const kimiRow = (await screen.findAllByText("Kimi"))
      .find((node) => node.closest("tr"))
      ?.closest("tr");
    const zaiRow = (await screen.findAllByText("Z.AI"))
      .find((node) => node.closest("tr"))
      ?.closest("tr");

    expect(kimiRow).not.toBeNull();
    expect(zaiRow).not.toBeNull();
    expect(within(kimiRow as HTMLElement).getAllByText("kimi-k2.6").length).toBeGreaterThan(0);
    expect(within(kimiRow as HTMLElement).getByRole("link", { name: /https:\/\/api\.moonshot\.cn\/v1/ })).toHaveAttribute(
      "href",
      "https://api.moonshot.cn/v1",
    );
    expect(within(zaiRow as HTMLElement).getAllByText("glm-5.1").length).toBeGreaterThan(0);
    expect(within(zaiRow as HTMLElement).getByRole("link", { name: /https:\/\/api\.z\.ai\/api\/paas\/v4/ })).toHaveAttribute(
      "href",
      "https://api.z.ai/api/paas/v4",
    );
    expect(within(kimiRow as HTMLElement).queryByRole("button", { name: "删除：kimi-k2.6" })).not.toBeInTheDocument();
    expect(within(zaiRow as HTMLElement).queryByRole("button", { name: "删除：glm-5.1" })).not.toBeInTheDocument();
  });

  it("groups DeepSeek models under one provider row while listing existing models", async () => {
    const settings = {
      ...modelSettingsPayload(),
      default_provider: "deepseek-pro",
      default_model: "deepseek-v4-pro",
      providers: [
        {
          name: "deepseek-flash",
          label: "DeepSeek Flash",
          model: "deepseek-v4-flash",
          model_kind: "文本模型",
          api_format: "openai",
          base_url: "https://api.deepseek.com",
          api_key_configured: true,
          api_key_source: "stored_secret_user",
        },
        {
          name: "deepseek-pro",
          label: "DeepSeek Pro",
          model: "deepseek-v4-pro",
          model_kind: "推理模型",
          api_format: "openai",
          base_url: "https://api.deepseek.com",
          api_key_configured: true,
          api_key_source: "stored_secret_user",
        },
      ],
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === "/api/settings/models") return jsonResponse(settings);
      if (path === "/api/settings/models/health") return jsonResponse({ items: [] });
      if (path === "/api/settings/models/fallbacks") return jsonResponse(fallbackSummaryPayload());
      if (path === "/api/settings/models/pricing-sources") {
        return jsonResponse(pricingSourcesPayload());
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    renderPage(fetchMock);

    const providerRows = await screen.findAllByText("DeepSeek");
    const deepSeekRow = providerRows.find((node) => node.closest("tr"))?.closest("tr");

    expect(deepSeekRow).not.toBeNull();
    expect(screen.getAllByText("DeepSeek").filter((node) => node.closest("tr"))).toHaveLength(1);
    expect(within(deepSeekRow as HTMLElement).getAllByText("deepseek-v4-flash").length).toBeGreaterThan(0);
    expect(within(deepSeekRow as HTMLElement).getAllByText("deepseek-v4-pro").length).toBeGreaterThan(0);
    expect(within(deepSeekRow as HTMLElement).getByText("文本模型")).toBeInTheDocument();
    expect(within(deepSeekRow as HTMLElement).getByText("推理模型")).toBeInTheDocument();
    expect(within(deepSeekRow as HTMLElement).queryByText("2 个模型")).not.toBeInTheDocument();
    expect(within(deepSeekRow as HTMLElement).queryByText("含默认")).not.toBeInTheDocument();
  });

  it("shows partial provider key state without leaking missing secret sources", async () => {
    const settings = {
      ...modelSettingsPayload(),
      default_provider: "deepseek-flash",
      default_model: "deepseek-v4-flash",
      providers: [
        {
          name: "deepseek-flash",
          label: "DeepSeek Flash",
          model: "deepseek-v4-flash",
          model_kind: "text",
          api_format: "openai",
          base_url: "https://api.deepseek.com",
          api_key_configured: true,
          api_key_source: "stored_secret_user",
          rate_limit_rpm: 300,
          rate_limit_tpm: 1000000,
        },
        {
          name: "deepseek-pro",
          label: "DeepSeek Pro",
          model: "deepseek-v4-pro",
          model_kind: "reasoning",
          api_format: "openai",
          base_url: "https://api.deepseek.com",
          api_key_configured: false,
          api_key_source: "missing",
          rate_limit_rpm: 120,
          rate_limit_tpm: 500000,
        },
      ],
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === "/api/settings/models") return jsonResponse(settings);
      if (path === "/api/settings/models/health") return jsonResponse({ items: [] });
      if (path === "/api/settings/models/fallbacks") return jsonResponse(fallbackSummaryPayload());
      if (path === "/api/settings/models/pricing-sources") {
        return jsonResponse(pricingSourcesPayload());
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    renderPage(fetchMock);

    const deepSeekRow = (await screen.findAllByText("DeepSeek"))
      .find((node) => node.closest("tr"))
      ?.closest("tr");

    expect(deepSeekRow).not.toBeNull();
    await waitFor(() => {
      expect(within(deepSeekRow as HTMLElement).getByText("已配置")).toBeInTheDocument();
      expect(within(deepSeekRow as HTMLElement).queryByText("部分已配置")).not.toBeInTheDocument();
      expect(within(deepSeekRow as HTMLElement).queryByText("未配置")).not.toBeInTheDocument();
      expect(within(deepSeekRow as HTMLElement).getByText("文本模型")).toBeInTheDocument();
      expect(within(deepSeekRow as HTMLElement).getByText("推理模型")).toBeInTheDocument();
      expect(within(deepSeekRow as HTMLElement).getByText(/300 rpm/)).toBeInTheDocument();
      expect(within(deepSeekRow as HTMLElement).getByText(/120 rpm/)).toBeInTheDocument();
      expect(within(deepSeekRow as HTMLElement).queryByRole("button", { name: "删除：deepseek-v4-pro" })).not.toBeInTheDocument();
      expect(within(deepSeekRow as HTMLElement).getByRole("button", { name: "切换：deepseek-v4-pro" })).toBeInTheDocument();
    });
    expect(document.body).not.toHaveTextContent(/\bmissing\b/);
  });
});
