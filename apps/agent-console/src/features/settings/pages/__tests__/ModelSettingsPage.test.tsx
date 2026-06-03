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
      provider === "deepseek-flash"
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

    await screen.findByText("DeepSeek Flash");
    await user.click(screen.getByRole("button", { name: /DeepSeek Flash 配置并启用/ }));
    const dialog = await screen.findByRole("dialog", { name: /配置 DeepSeek Flash/ });
    await user.type(within(dialog).getByLabelText(/接口访问密钥/), "sk-deepseek-test");
    await user.click(within(dialog).getByRole("button", { name: /保存并启用/ }));

    expect((await screen.findAllByText("模型配置已保存")).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /已启用/ })).toBeInTheDocument();
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

    await screen.findByText("OpenAI GPT-5.5");
    expect(screen.queryByRole("button", { name: /OpenAI GPT-5.5 已启用/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /OpenAI GPT-5.5 配置并启用/ }));

    expect(await screen.findByRole("dialog", { name: /配置 OpenAI GPT-5.5/ })).toBeInTheDocument();
    expect(screen.getAllByText("需配置密钥").length).toBeGreaterThan(0);
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

    const dialog = await screen.findByRole("dialog", { name: "添加自定义模型" });
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
    expect(await screen.findByText("DeepSeek Flash")).toBeInTheDocument();
    expect(screen.getAllByText("OpenAI GPT-5.5").length).toBeGreaterThan(0);
    expect(screen.getByText("kimi-k2.6")).toBeInTheDocument();
    expect(screen.getByText("glm-5.1")).toBeInTheDocument();
    expect(screen.getAllByText("已验证")).toHaveLength(4);
    const kimiRow = screen.getByText("kimi-k2.6").closest("tr");
    expect(kimiRow).not.toBeNull();
    expect(within(kimiRow as HTMLElement).getByText("输入 USD 0.95")).toBeInTheDocument();
    expect(within(kimiRow as HTMLElement).getByText("已验证")).toBeInTheDocument();
    expect(screen.queryByText("USD 汇总已阻塞")).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("openai-compatible/gpt");
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

    expect(await screen.findByText("DeepSeek Flash")).toBeInTheDocument();
    expect(screen.getAllByText("OpenAI GPT-5.5").length).toBeGreaterThan(0);
    expect(screen.getByText("Kimi K2.6")).toBeInTheDocument();
    expect(screen.getByText("Z.AI GLM-5.1")).toBeInTheDocument();
    expect(screen.queryByText("成本来源暂不可用")).not.toBeInTheDocument();
    expect(screen.queryByText(/价格来源接口返回 404/)).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("404: Not Found");
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input]) => requestPath(input) === "/model_pricing_sources.json")).toBe(true);
    });
  });

  it("shows model names as preset titles and exposes only one OpenAI built-in preset", async () => {
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

    const gpt55Card = (await screen.findByText(/gpt-5\.5 · openai · https:\/\/api\.openai\.com\/v1/)).closest(".rounded-md");
    const openAiPresetCards = screen
      .getAllByText(/https:\/\/api\.openai\.com\/v1/)
      .map((node) => node.closest(".rounded-md"));

    expect(gpt55Card).not.toBeNull();
    expect(openAiPresetCards.filter(Boolean)).toHaveLength(1);
    await waitFor(() => {
      expect(within(gpt55Card as HTMLElement).getByText("OpenAI GPT-5.5")).toBeInTheDocument();
      expect(within(gpt55Card as HTMLElement).getByText("当前默认")).toBeInTheDocument();
    });
  });

  it("removing a sibling model on the same provider keeps the current default", async () => {
    const settings = {
      ...modelSettingsPayload(),
      providers: [
        ...modelSettingsPayload().providers,
        {
          name: "openai-compatible",
          label: "OpenAI 自定义分析模型",
          model: "gpt-custom-analysis",
          api_format: "openai",
          base_url: "https://api.openai.com/v1",
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
      if (path === "/api/settings/models/pricing-sources") {
        return jsonResponse(pricingSourcesPayload());
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    const user = userEvent.setup();
    renderPage(fetchMock);

    const siblingRow = (await screen.findByText("gpt-custom-analysis")).closest("tr");
    expect(siblingRow).not.toBeNull();
    await user.click(within(siblingRow as HTMLElement).getByTitle("删除"));

    await waitFor(() => {
      const saveCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input) === "/api/settings/models" && init?.method === "PUT",
      );
      expect(saveCall).toBeDefined();
      expect(JSON.parse(String(saveCall?.[1]?.body))).toMatchObject({
        default_provider: "openai-compatible",
        default_model: "gpt-5.5",
        providers: [
          expect.objectContaining({
            name: "openai-compatible",
            model: "gpt-5.5",
          }),
        ],
      });
    });
  });
});
