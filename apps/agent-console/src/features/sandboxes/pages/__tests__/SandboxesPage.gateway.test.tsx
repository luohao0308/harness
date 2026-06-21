import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SandboxesPage } from "../SandboxesPage";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/sandboxes"]}>
      <QueryClientProvider client={queryClient}>
        <SandboxesPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SandboxesPage API Gateway", () => {
  it("unlocks API Gateway routes and shows the one-time key after create", async () => {
    const user = userEvent.setup();
    let routes: unknown[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.includes("/api/agents/default/gateway-routes") && init?.method === "POST") {
        routes = [
          {
            id: "route-1",
            agent_id: "default",
            slug: "release-review",
            rate_limit: 60,
            enabled: true,
            description: "Release review",
            created_at: "2026-06-21T00:00:00Z",
            updated_at: "2026-06-21T00:00:00Z",
            last_invoked_at: null,
          },
        ];
        return jsonResponse({ route: routes[0], api_key: "hgw_test_key" }, 201);
      }
      if (path.includes("/api/agents/default/gateway-routes")) {
        return jsonResponse({ items: routes });
      }
      if (path.includes("/api/sandboxes/warm-pool/benchmarks")) {
        return jsonResponse({ items: [], next_cursor: null });
      }
      if (path.includes("/api/sandboxes/warm-pool")) {
        return jsonResponse({
          enabled: true,
          min_size: 2,
          max_size: 5,
          idle: 0,
          busy: 0,
          failed: 0,
          hit_total: 0,
          miss_total: 0,
        });
      }
      if (path.includes("/api/sandboxes/quota/usage")) {
        return jsonResponse({
          organization_id: "dev-org",
          configured_memory_mb: 512,
          configured_cpus: "1",
          configured_workspace_quota_mb: 1024,
          configured_network_enabled: false,
          configured_network_allowlist: [],
          sandbox_total: 0,
          running_total: 0,
          destroyed_total: 0,
          memory_limit_mb_total: 0,
          running_memory_limit_mb_total: 0,
          cpu_limit_total: 0,
          running_cpu_limit_total: 0,
          network_enabled_total: 0,
          warm_pool_reused_total: 0,
          latest_created_at: null,
        });
      }
      if (path.includes("/api/sandboxes/quota/history")) {
        return jsonResponse({ items: [], next_cursor: null });
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    expect((await screen.findAllByText("API 网关")).length).toBeGreaterThan(0);
    expect(screen.getByText("接口已接入")).toBeTruthy();
    expect(await screen.findByText("暂无 API Gateway 发布路由")).toBeTruthy();

    await user.type(screen.getByLabelText("路由 slug"), "release-review");
    await user.type(screen.getByLabelText("路由描述"), "Release review");
    await user.click(screen.getByRole("button", { name: /创建发布/ }));

    expect(await screen.findByText("hgw_test_key")).toBeTruthy();
    expect(await screen.findByText("release-review")).toBeTruthy();
    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          String(input).includes("/api/agents/default/gateway-routes") &&
          init?.method === "POST",
      );
      expect(createCall).toBeDefined();
      expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
        slug: "release-review",
        description: "Release review",
        rate_limit: 60,
        enabled: true,
      });
    });
  });
});
