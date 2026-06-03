import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SubagentMarketplacePage } from "../pages/SubagentMarketplacePage";

const apiBaseUrl = "http://127.0.0.1:8000";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function requestPath(input: RequestInfo | URL) {
  const url = String(input);
  return url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
}

function listing(overrides: Record<string, unknown> = {}) {
  return {
    id: "listing-1",
    slug: "release-reviewer-pack",
    display_name: "发布审查专家",
    description: "Shared release reviewer",
    author_org_id: "author-org",
    author_name: "QA Team",
    version: "1.0.0",
    manifest_json: { slug: "release-reviewer" },
    signature: "hmac-sha256:abcdef",
    verified: true,
    download_count: 2,
    installed: false,
    installed_specialist_id: null,
    created_at: "2026-05-30T00:00:00Z",
    updated_at: "2026-05-30T00:00:00Z",
    ...overrides,
  };
}

function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/subagent-marketplace"]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/subagent-marketplace" element={<SubagentMarketplacePage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SubagentMarketplacePage", () => {
  it("renders listings and installs a verified specialist", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/subagent-marketplace/listings?include_unverified=true" && !init?.method) {
        return jsonResponse({ items: [listing()], next_cursor: null });
      }
      if (path === "/api/subagent-marketplace/listings/listing-1/install" && init?.method === "POST") {
        return jsonResponse({
          id: "installation-1",
          listing_id: "listing-1",
          installed_org_id: "dev-org",
          installed_specialist_id: "spec-release",
          installed_version: "1.0.0",
          auto_update_enabled: false,
          installed_at: "2026-05-30T00:00:00Z",
          specialist: { slug: "release-reviewer" },
        }, 201);
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    expect(await screen.findByText("发布审查专家")).toBeInTheDocument();
    expect(screen.getByText("release-reviewer-pack")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /安装/ }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(
        ([input, init]) =>
          requestPath(input as RequestInfo | URL) === "/api/subagent-marketplace/listings/listing-1/install" &&
          init?.method === "POST",
      )).toBe(true);
    });
  });
});
