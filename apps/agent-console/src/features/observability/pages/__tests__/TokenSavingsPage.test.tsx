import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TokenSavingsPage } from "../TokenSavingsPage";

const apiBaseUrl = "http://127.0.0.1:8000";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function tokenSavingsPayload() {
  return {
    generated_at: "2026-05-25T00:02:00Z",
    summary: {
      actual_prompt_tokens: 550,
      actual_completion_tokens: 50,
      actual_total_tokens: 600,
      estimated_candidate_tokens: 1000,
      estimated_included_tokens: 600,
      estimated_omitted_tokens: 400,
      estimated_saved_tokens: 400,
      estimated_savings_percent: 40,
      context_manifest_count: 1,
      pruning_manifest_count: 1,
      retrieval_cache_hit_count: 2,
      retrieval_cache_miss_count: 1,
      retrieval_cache_stale_count: 0,
      cache_sources: [
        {
          cache_source: "compression_summary",
          label: "摘要缓存",
          hit_count: 1,
          miss_count: 1,
          stale_count: 0,
          estimated_saved_tokens: 80,
          hit_rate: 50,
          reason: "summary_reused",
        },
        {
          cache_source: "legacy_retrieval_cache",
          label: "上下文缓存",
          hit_count: 2,
          miss_count: 1,
          stale_count: 0,
          estimated_saved_tokens: 0,
          hit_rate: 66.67,
          reason: null,
        },
      ],
      low_cost_route_count: 1,
      optimizer_capability_version_ids: ["balanced-version-1"],
      optimizer_labels: ["均衡"],
      optimizer_decision_count: 1,
    },
    runs: [
      {
        run_id: "run-1",
        agent_id: "default",
        title: "Balanced optimizer run",
        status: "COMPLETED",
        created_at: "2026-05-25T00:00:00Z",
        updated_at: "2026-05-25T00:01:00Z",
        context_manifest_id: "manifest-1",
        estimated_candidate_tokens: 1000,
        estimated_included_tokens: 600,
        estimated_omitted_tokens: 400,
        estimated_saved_tokens: 400,
        estimated_savings_percent: 40,
        actual_prompt_tokens: 550,
        actual_completion_tokens: 50,
        actual_total_tokens: 600,
        included_count: 1,
        omitted_count: 3,
        pruning_applied: true,
        retrieval_cache_hit_count: 2,
        retrieval_cache_miss_count: 1,
        retrieval_cache_stale_count: 0,
        cache_sources: [
          {
            cache_source: "compression_summary",
            label: "摘要缓存",
            hit_count: 1,
            miss_count: 1,
            stale_count: 0,
            estimated_saved_tokens: 80,
            hit_rate: 50,
            reason: "summary_reused",
          },
        ],
        low_cost_routes: [
          {
            model_call_id: "call-1",
            model_name: "cheap-model",
            reason: "balanced summarization under budget",
          },
        ],
        optimizer_capability_version_ids: ["balanced-version-1"],
        optimizer_labels: ["均衡"],
        optimizer_policy_hash: "policy-hash",
        optimizer_decision_count: 1,
        omission_reasons: [
          { reason: "optimizer_section_limit", count: 2 },
          { reason: "optimizer_budget", count: 1 },
        ],
      },
    ],
    next_cursor: null,
  };
}

function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/token-savings"]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/token-savings" element={<TokenSavingsPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("TokenSavingsPage", () => {
  it("renders aggregate token savings and recent run evidence", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/observability/token-savings?limit=50") {
        return jsonResponse(tokenSavingsPayload());
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    expect(await screen.findByText("Balanced optimizer run")).toBeInTheDocument();
    expect(screen.getByText("总 Token")).toBeInTheDocument();
    expect(screen.getByText("缓存命中率")).toBeInTheDocument();
    expect(screen.getAllByText("400").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("550").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("1K").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("40%").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("66.67%").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("2 / 1").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("摘要缓存")).toBeInTheDocument();
    expect(screen.getByText("RAG 检索")).toBeInTheDocument();
    expect(screen.getByText("长期记忆")).toBeInTheDocument();
    expect(screen.queryByText("上下文缓存")).not.toBeInTheDocument();
    expect(screen.getAllByText("均衡").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Balanced optimizer run")).toBeInTheDocument();
    expect(screen.getByText("数量上限 · 2")).toBeInTheDocument();
    expect(screen.getByText("预算裁剪 · 1")).toBeInTheDocument();
    expect(screen.getByText(/balanced summarization under budget/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Balanced optimizer run" })).toHaveAttribute(
      "href",
      "/runs/run-1",
    );
  });
});
