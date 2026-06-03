import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdapterSchemaDrawer } from "../components/AdapterSchemaDrawer";
import type { AdapterMetadata } from "../../tasks/api";

const adapter: AdapterMetadata = {
  slug: "github.list_issues",
  server_label: "github",
  method: "list_issues",
  description: "List issues",
  version: "v1-2026-05-29",
  adapter_module: "app.tools.adapters.github_adapter",
  adapter_sha256: "a".repeat(64),
  input_schema_sha256: "b".repeat(64),
  output_schema_sha256: "c".repeat(64),
  input_schema: {
    type: "object",
    properties: { repo: { type: "string" } },
    required: ["repo"],
  },
  output_schema: { type: "object", properties: { items: { type: "array" } } },
  requires_secret: true,
  risk_level: "low",
};

function renderDrawer(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AdapterSchemaDrawer adapter={adapter} agentId="default" open onClose={vi.fn()} />
    </QueryClientProvider>,
  );
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AdapterSchemaDrawer", () => {
  it("renders input and output schemas with audit hashes", () => {
    renderDrawer(vi.fn());

    const dialog = screen.getByRole("dialog", { name: "github.list_issues" });
    expect(within(dialog).getByText("Input Schema")).toBeInTheDocument();
    expect(within(dialog).getByText("Output Schema")).toBeInTheDocument();
    expect(within(dialog).getByText("sha aaaaaaaa")).toBeInTheDocument();
    expect(within(dialog).getByText(/adapter a{64}/)).toBeInTheDocument();
  });

  it("runs try-it through capability test invoke", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input).replace("http://127.0.0.1:8000", "");
      if (path === "/api/tools/capabilities/test-invoke" && init?.method === "POST") {
        return jsonResponse({
          allowed: true,
          output: { result: { items: [{ title: "Issue 1" }] } },
          tool_call: {
            id: "tool-call-1",
            tool_name: "github.list_issues",
            status: "SUCCESS",
            risk_level: "low",
            requires_sandbox: false,
            duration_ms: 10,
            output_kind: "json",
            output_summary: "ok",
            created_at: "2026-05-28T00:00:00Z",
          },
        }, 202);
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    const user = userEvent.setup();
    renderDrawer(fetchMock);

    await user.click(screen.getByRole("button", { name: "试调" }));

    expect(await screen.findByText(/Issue 1/)).toBeInTheDocument();
    const request = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(request.tool_name).toBe("github.list_issues");
    expect(request.input_json.repo).toBe("owner/repo");
  });
});
