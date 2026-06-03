import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

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
    default_model: "default",
    providers: [],
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
  vi.unstubAllGlobals();
});

describe("ModelSettingsPage", () => {
  it("releases Add & Switch after the save request succeeds even when refetches are slow", async () => {
    const savedSettings = {
      ...modelSettingsPayload(),
      default_provider: "deepseek-flash",
      default_model: "deepseek-v4-flash",
      providers: [
        {
          name: "deepseek-flash",
          label: "DeepSeek Flash",
          model: "deepseek-v4-flash",
          api_format: "openai",
          base_url: "https://api.deepseek.com",
          api_key: "replace-me",
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
      if (path === "/api/settings/models/fallbacks?limit=20") {
        return jsonResponse(fallbackSummaryPayload());
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    const user = userEvent.setup();
    renderPage(fetchMock);

    await screen.findByText("DeepSeek Flash");
    await user.click(screen.getAllByRole("button", { name: /添加并切换/ })[0]);

    expect(await screen.findByText("模型配置已保存")).toBeInTheDocument();
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
      });
    });
  });
});
