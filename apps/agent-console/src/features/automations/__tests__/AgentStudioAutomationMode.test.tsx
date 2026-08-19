import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentListPage } from "../../agents/pages/AgentListPage";

function json(payload: unknown) {
  return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
}

afterEach(() => vi.unstubAllGlobals());

describe("Agent Studio automation mode", () => {
  it("renders the trigger panel for desktop_panel=triggers", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = new URL(String(input), "http://local").pathname;
      if (path === "/api/agents") return json({ items: [{
        id: "default", name: "默认智能体", description: "默认入口", role: "planner", status: "ACTIVE",
        model_provider: "default", model_name: "default", system_prompt: "Plan", tools_json: [],
        routing_tags: [], max_parallel_assignments: 1, capability_attachments: [],
        created_at: "2026-08-17T00:00:00Z", updated_at: "2026-08-17T00:00:00Z",
      }, {
        id: "research", name: "研究智能体", description: "研究入口", role: "researcher", status: "ACTIVE",
        model_provider: "default", model_name: "default", system_prompt: "Research", tools_json: [],
        routing_tags: [], max_parallel_assignments: 1, capability_attachments: [],
        created_at: "2026-08-17T00:00:00Z", updated_at: "2026-08-17T00:00:00Z",
      }], next_cursor: null });
      if (path.endsWith("/triggers")) return json({ items: [] });
      if (path === "/api/agents/default/knowledge/sources") return json({ items: [], next_cursor: null });
      if (path === "/api/agents/local-agent/connections") return json({ items: [], next_cursor: null });
      if (path === "/api/agents/token-optimizer/presets") return json({ items: [] });
      return json({ items: [] });
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter initialEntries={["/agents?desktop_panel=triggers"]}>
        <QueryClientProvider client={client}>
          <AgentListPage />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "自动化" })).toBeInTheDocument();
    expect(await screen.findByText("暂无自动化")).toBeInTheDocument();
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => new URL(String(input), "http://local").pathname === "/api/agents/default/triggers")).toBe(true));
    await user.click(screen.getByRole("button", { name: /管理智能体/ }));
    await user.click(screen.getByRole("option", { name: /研究智能体/ }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => new URL(String(input), "http://local").pathname === "/api/agents/research/triggers")).toBe(true));
  });
});
