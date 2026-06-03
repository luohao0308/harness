import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdapterHealthBadge, adapterHealthState } from "../components/AdapterHealthBadge";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderBadge(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AdapterHealthBadge slug="github.list_issues" agentId="default" />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AdapterHealthBadge", () => {
  it("renders healthy adapter state", async () => {
    renderBadge(
      vi.fn(async () =>
        jsonResponse({
          slug: "github.list_issues",
          ok: true,
          latency_ms: 12,
          message: "GitHub API reachable",
          sample: {},
          last_checked_at: "2026-05-28T00:00:00Z",
        }),
      ),
    );

    expect(await screen.findByText("健康 · 12ms")).toBeInTheDocument();
  });

  it("renders degraded adapter state", async () => {
    renderBadge(
      vi.fn(async () =>
        jsonResponse({
          slug: "github.list_issues",
          ok: false,
          latency_ms: 0,
          message: "GitHub token is not configured",
          sample: {},
          last_checked_at: "2026-05-28T00:00:00Z",
        }),
      ),
    );

    expect(await screen.findByText("需配置")).toBeInTheDocument();
  });

  it("maps request failures to unknown state", () => {
    const state = adapterHealthState(undefined, false, true);

    expect(state.label).toBe("健康未知");
    expect(state.tone).toBe("warning");
  });
});
