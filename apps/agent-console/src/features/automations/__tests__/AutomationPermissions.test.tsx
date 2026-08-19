import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

let authUser: { role: string; permissions: string[] } | null = null;

vi.mock("../../auth/AuthProvider", () => ({
  useOptionalAuth: () => authUser ? { user: authUser, currentOrganization: { role: authUser.role } } : null,
}));

import { AutomationPanel } from "../components/AutomationPanel";

const trigger = {
  id: "trigger-1",
  agent_id: "default",
  type: "schedule",
  name: "定时巡检",
  config_json: { interval_seconds: 300 },
  endpoint_path: null,
  enabled: true,
  created_at: "2026-08-17T12:00:00Z",
  updated_at: "2026-08-17T12:00:00Z",
  last_triggered_at: null,
};

function renderWithPermissions(role: string, permissions: string[]) {
  authUser = { role, permissions };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [trigger] }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <AutomationPanel agentId="default" agentLabel="默认智能体" />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  authUser = null;
  vi.unstubAllGlobals();
});

describe("Automation permissions", () => {
  it("keeps Viewer read-only while preserving history access", async () => {
    renderWithPermissions("viewer", ["agent:read", "run:read"]);
    expect(await screen.findByText("定时巡检")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "新建自动化" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "暂停 定时巡检" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "删除 定时巡检" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "查看 定时巡检 的最近运行" })).toBeInTheDocument();
  });

  it("allows Member create and update but hides delete", async () => {
    renderWithPermissions("member", ["agent:read", "agent:create", "run:read"]);
    expect(await screen.findByText("定时巡检")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "新建自动化" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "暂停 定时巡检" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "删除 定时巡检" })).not.toBeInTheDocument();
  });
});
