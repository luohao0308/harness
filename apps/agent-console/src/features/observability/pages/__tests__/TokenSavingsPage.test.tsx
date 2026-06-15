import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
        model_names: ["cheap-model"],
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
      {
        run_id: "run-2",
        agent_id: "reviewer",
        model_names: ["expensive-model"],
        title: "Reviewer baseline run",
        status: "COMPLETED",
        created_at: "2026-04-01T00:00:00Z",
        updated_at: "2026-04-01T00:01:00Z",
        context_manifest_id: "manifest-2",
        estimated_candidate_tokens: 500,
        estimated_included_tokens: 500,
        estimated_omitted_tokens: 0,
        estimated_saved_tokens: 0,
        estimated_savings_percent: 0,
        actual_prompt_tokens: 300,
        actual_completion_tokens: 20,
        actual_total_tokens: 320,
        included_count: 2,
        omitted_count: 0,
        pruning_applied: false,
        retrieval_cache_hit_count: 0,
        retrieval_cache_miss_count: 1,
        retrieval_cache_stale_count: 0,
        cache_sources: [],
        low_cost_routes: [],
        optimizer_capability_version_ids: [],
        optimizer_labels: [],
        optimizer_policy_hash: null,
        optimizer_decision_count: 0,
        omission_reasons: [],
      },
    ],
    next_cursor: null,
  };
}

function tokenSavingsPayloadWithSummaryDrift() {
  const payload = tokenSavingsPayload();
  return {
    ...payload,
    summary: {
      ...payload.summary,
      actual_prompt_tokens: 1_500,
      actual_completion_tokens: 100,
      actual_total_tokens: 1_600,
      estimated_candidate_tokens: 2_000,
      estimated_saved_tokens: 800,
      estimated_savings_percent: 40,
      retrieval_cache_hit_count: 5,
      retrieval_cache_miss_count: 2,
      low_cost_route_count: 2,
    },
    runs: [
      {
        ...payload.runs[0],
        model_names: ["all"],
        low_cost_routes: [
          {
            model_call_id: "call-all",
            model_name: "all",
            reason: "literal all model name",
          },
        ],
      },
      payload.runs[1],
    ],
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

async function chooseMenuOption(user: ReturnType<typeof userEvent.setup>, triggerName: RegExp, listboxName: string, optionName: RegExp) {
  await user.click(screen.getByRole("button", { name: triggerName }));
  const listbox = screen.getByRole("listbox", { name: listboxName });
  await user.click(within(listbox).getByRole("option", { name: optionName }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("TokenSavingsPage", () => {
  it("renders token savings as a filterable evidence table", async () => {
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
    expect(screen.getByText("Reviewer baseline run")).toBeInTheDocument();
    expect(screen.getByText("Token 节省明细")).toBeInTheDocument();
    expect(screen.getByText("总 Token")).toBeInTheDocument();
    expect(screen.getByText("缓存命中率")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "时间范围：全部时间" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "模型：全部模型" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Agent：全部 Agent" })).toBeInTheDocument();
    expect(screen.getAllByText("cheap-model").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("expensive-model").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("default").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("reviewer").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("40%").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("2 / 1").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/摘要缓存 50%/)).toBeInTheDocument();
    expect(screen.getAllByText(/RAG 检索 0%/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/长期记忆 0%/).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("上下文缓存")).not.toBeInTheDocument();
    expect(screen.getAllByText("均衡").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("数量上限 · 2")).toBeInTheDocument();
    expect(screen.getByText("预算裁剪 · 1")).toBeInTheDocument();
    expect(screen.getByText(/balanced summarization under budget/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Balanced optimizer run" })).toHaveAttribute(
      "href",
      "/runs/run-1",
    );
  });

  it("filters token savings rows by model, agent, and time range", async () => {
    const user = userEvent.setup();
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
    expect(screen.getByText("Reviewer baseline run")).toBeInTheDocument();

    await chooseMenuOption(user, /模型：全部模型/, "模型", /cheap-model/);
    expect(screen.getByText("Balanced optimizer run")).toBeInTheDocument();
    expect(screen.queryByText("Reviewer baseline run")).not.toBeInTheDocument();
    expect(screen.getByText("1 / 2 条")).toBeInTheDocument();

    await chooseMenuOption(user, /Agent：全部 Agent/, "Agent", /reviewer/);
    expect(screen.queryByText("Balanced optimizer run")).not.toBeInTheDocument();
    expect(screen.getByText("当前筛选没有匹配的节省证据。")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "重置" }));
    expect(screen.getByText("Balanced optimizer run")).toBeInTheDocument();
    expect(screen.getByText("Reviewer baseline run")).toBeInTheDocument();

    await chooseMenuOption(user, /时间范围：全部时间/, "时间范围", /最近 7 天/);
    expect(screen.getByText("Balanced optimizer run")).toBeInTheDocument();
    expect(screen.queryByText("Reviewer baseline run")).not.toBeInTheDocument();
  });

  it("uses backend summary for the all-time strip and still filters a literal all model name", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/observability/token-savings?limit=50") {
        return jsonResponse(tokenSavingsPayloadWithSummaryDrift());
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    expect(await screen.findByText("Balanced optimizer run")).toBeInTheDocument();
    expect(screen.getAllByText("1.6K").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("5 / 2")).toBeInTheDocument();

    await chooseMenuOption(user, /模型：全部模型/, "模型", /^all$/);

    expect(screen.getByText("Balanced optimizer run")).toBeInTheDocument();
    expect(screen.queryByText("Reviewer baseline run")).not.toBeInTheDocument();
    expect(screen.getByText("1 / 2 条")).toBeInTheDocument();
    expect(screen.getAllByText("600").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("2 / 1").length).toBeGreaterThanOrEqual(1);
  });
});
