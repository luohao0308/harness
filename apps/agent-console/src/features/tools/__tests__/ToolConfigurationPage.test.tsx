import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToolConfigurationPage } from "../pages/ToolConfigurationPage";

const apiBaseUrl = "http://127.0.0.1:8000";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ToolConfigurationPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function runtimeConfigPayload(configured: boolean) {
  return {
    agent_id: "default",
    tool_name: "brave",
    tool_description: "Search the web through Brave Search.",
    source: "mcp",
    capability_id: "cap-brave",
    capability_version_id: configured ? "brave-configured-version" : "brave-original-version",
    capability_config_sha256: configured ? "configuredhash123456" : "originalhash123456",
    attachment_id: "attach-brave",
    attachment_enabled: true,
    configured,
    missing_fields: configured ? [] : ["endpoint_url"],
    transport: "http",
    endpoint_url: configured ? "https://api.search.brave.com/res/v1/web/search" : null,
    command: null,
    args: [],
    secret_ref: configured ? "secret://mcp/default/brave/api-key" : null,
    secret_configured: configured,
    timeout_seconds: 30,
    config_json: {},
    registry_visible: true,
    test_input_json: { query: "MCP 教程", limit: 3 },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ToolConfigurationPage", () => {
  it("saves Brave runtime config and runs a visible case test", async () => {
    let configured = false;
    let savedBody: Record<string, unknown> | null = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/agents" && !init?.method) {
        return jsonResponse({ items: [{ id: "default", name: "默认智能体" }], next_cursor: null });
      }
      if (path.startsWith("/api/tools/capabilities/runtime-configs") && !init?.method) {
        return jsonResponse({ items: [runtimeConfigPayload(configured)] });
      }
      if (path === "/api/tools/capabilities/runtime-config" && init?.method === "PATCH") {
        savedBody = JSON.parse(String(init.body));
        configured = true;
        return jsonResponse(runtimeConfigPayload(true));
      }
      if (path === "/api/tools/capabilities/test-invoke" && init?.method === "POST") {
        return jsonResponse({
          allowed: true,
          output: {
            mcp_server: "brave",
            mcp_method: "search",
            result: {
              source: "brave-search-api",
              items: [
                {
                  id: "https://example.com/mcp",
                  title: "MCP 教程 - Brave result",
                  url: "https://example.com/mcp",
                  snippet: "Model Context Protocol tutorial result",
                },
              ],
            },
          },
          tool_call: {
            id: "tool-call-brave",
            tool_name: "brave",
            status: "SUCCESS",
            risk_level: "low",
            requires_sandbox: false,
            duration_ms: 18,
            output_kind: "json",
            output_summary: "ok",
            created_at: "2026-05-27T00:00:00Z",
          },
        }, 202);
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    const user = userEvent.setup();

    renderPage(fetchMock);

    expect(await screen.findByText("MCP / 技能运行配置")).toBeInTheDocument();
    const braveCard = await screen.findByRole("button", { name: /brave/ });
    expect(within(braveCard).getByText("未配置")).toBeInTheDocument();

    const endpointInput = screen.getByLabelText("MCP 运行端点");
    expect(endpointInput).toHaveValue("https://api.search.brave.com/res/v1/web/search");
    await user.type(screen.getByLabelText("MCP API Key"), "brave-test-token");
    await user.click(screen.getByRole("button", { name: /保存运行配置/ }));

    await waitFor(() => {
      expect(savedBody).toMatchObject({
        agent_id: "default",
        tool_name: "brave",
        transport: "http",
        endpoint_url: "https://api.search.brave.com/res/v1/web/search",
        secret_ref: "secret://mcp/default/brave/api-key",
        secret_value: "brave-test-token",
      });
    });
    expect((await screen.findAllByText("已配置")).length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: /运行案例测试/ }));
    expect(await screen.findByText("MCP 教程 - Brave result")).toBeInTheDocument();
    expect(screen.getByText("真实 Brave API")).toBeInTheDocument();
  });
});
