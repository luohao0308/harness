import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SubagentSpecialistDetailPage } from "../pages/SubagentSpecialistDetailPage";
import { SubagentSpecialistsPage } from "../pages/SubagentSpecialistsPage";

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

function specialist(overrides: Record<string, unknown> = {}) {
  return {
    id: "spec-reviewer",
    organization_id: null,
    slug: "code-reviewer",
    display_name: "代码审查专家",
    description: "Review patches and files",
    role: "reviewer",
    system_prompt: "Review code with concrete findings.",
    capability_slugs_json: ["shell_read"],
    output_schema_json: {
      type: "object",
      required: ["summary"],
      properties: { summary: { type: "string" } },
    },
    output_schema_sha256: "abcdef0123456789abcdef0123456789",
    budget_json: {
      max_runtime_seconds: 900,
      max_tokens: 8000,
      max_tool_calls: 8,
      max_cost_usd: 2,
    },
    trigger_keywords_json: ["review", "代码"],
    visibility: "system",
    status: "ACTIVE",
    created_by: null,
    created_at: "2026-05-28T00:00:00Z",
    updated_at: "2026-05-28T00:00:00Z",
    ...overrides,
  };
}

function subagent(overrides: Record<string, unknown> = {}) {
  return {
    id: "subagent-1",
    task_id: "task-1",
    parent_agent_id: null,
    agent_type: "subagent",
    status: "SUCCESS",
    specialist_id: "spec-reviewer",
    fanout_batch_id: null,
    fanout_index: null,
    fanout_total: null,
    dynamic_fanout_origin: null,
    dynamic_fanout_requested_by: null,
    dynamic_fanout_reason: null,
    context_json: { step_key: "review" },
    started_at: "2026-05-28T00:00:00Z",
    completed_at: "2026-05-28T00:01:00Z",
    timeout_at: null,
    specialist: {
      id: "spec-reviewer",
      slug: "code-reviewer",
      display_name: "代码审查专家",
      role: "reviewer",
      visibility: "system",
      status: "ACTIVE",
    },
    output: {
      id: "output-1",
      agent_run_id: "subagent-1",
      task_id: "task-1",
      specialist_id: "spec-reviewer",
      output_json: { summary: "No high severity issues" },
      output_schema_sha256: "abcdef0123456789",
      budget_consumed_json: { runtime_seconds: 12, prompt_tokens: 100, completion_tokens: 40, tool_calls: 1, cost_usd: 0 },
      budget_exceeded_json: [],
      written_at: "2026-05-28T00:01:00Z",
    },
    task_title: "Review task",
    task_status: "COMPLETED",
    step_key: "review",
    specialist_slug: "code-reviewer",
    output_summary: "No high severity issues",
    ...overrides,
  };
}

function stats(overrides: Record<string, unknown> = {}) {
  return {
    specialist_id: "spec-reviewer",
    slug: "code-reviewer",
    window: "30d",
    total_invocations: 12,
    success_count: 10,
    failed_count: 2,
    budget_exceeded_count: 1,
    depth_rejected_count: 0,
    success_rate: 0.8333,
    avg_runtime_ms: 1200,
    p95_runtime_ms: 2400,
    avg_cost_usd: "0.001000",
    total_cost_usd: "0.012000",
    avg_tool_calls: 1.5,
    avg_output_size_bytes: 512,
    recent_failure_reasons: [{ reason: "output_schema_violation", count: 2 }],
    ...overrides,
  };
}

function renderWithRouter(path: string, element: ReactNode, fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/subagent-specialists" element={element} />
          <Route path="/subagent-specialists/:specialistId" element={element} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SubagentSpecialistsPage", () => {
  it("renders system templates and creates an org specialist through the API", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/subagent-specialists?include_archived=true" && !init?.method) {
        return jsonResponse({ items: [specialist()], next_cursor: null });
      }
      if (path === "/api/subagent-specialists/spec-reviewer/stats?window=30d" && !init?.method) {
        return jsonResponse(stats());
      }
      if (path === "/api/subagent-specialists" && init?.method === "POST") {
        return jsonResponse(specialist({ id: "spec-security", slug: "security-reviewer", display_name: "安全审查专家", visibility: "org" }), 201);
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderWithRouter("/subagent-specialists", <SubagentSpecialistsPage />, fetchMock);

    expect(await screen.findByText("代码审查专家")).toBeInTheDocument();
    expect(screen.getByText("code-reviewer")).toBeInTheDocument();
    expect(await screen.findByText("83.3%")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /创建专家|Create Specialist/ }));
    const dialog = await screen.findByRole("dialog", { name: "创建子代理专家" });
    await user.type(within(dialog).getByLabelText("Slug"), "security-reviewer");
    await user.type(within(dialog).getByLabelText("名称"), "安全审查专家");
    await user.clear(within(dialog).getByLabelText("角色"));
    await user.type(within(dialog).getByLabelText("角色"), "checker");
    await user.type(within(dialog).getByLabelText("说明"), "审查安全风险");
    await user.type(within(dialog).getByLabelText("系统提示词"), "Check security risks.");
    await user.type(within(dialog).getByLabelText("触发关键词"), "安全, risk");
    await user.click(within(dialog).getByRole("button", { name: /创建专家|Create Specialist/ }));

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input as RequestInfo | URL) === "/api/subagent-specialists" && init?.method === "POST",
      );
      expect(createCall).toBeTruthy();
      expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
        slug: "security-reviewer",
        display_name: "安全审查专家",
        role: "checker",
        trigger_keywords_json: ["安全", "risk"],
      });
    });
  });

  it("runs detail preflight and displays invocation history", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/subagent-specialists/spec-reviewer" && !init?.method) {
        return jsonResponse(specialist());
      }
      if (path === "/api/subagents?limit=500" && !init?.method) {
        return jsonResponse({ items: [subagent()], next_cursor: null });
      }
      if (path === "/api/subagent-specialists/spec-reviewer/stats?window=30d" && !init?.method) {
        return jsonResponse(stats());
      }
      if (path === "/api/subagent-specialists/calibration?window=30d" && !init?.method) {
        return jsonResponse({
          organization_id: "dev-org",
          window: "30d",
          decision_count: 1,
          low_sample: true,
          ece: null,
          buckets: [
            { bucket: "[0.0-0.2)", min_confidence: 0, max_confidence: 0.2, decision_count: 0, success_count: 0, success_rate: null, avg_confidence: null, ece_contribution: null },
            { bucket: "[0.2-0.4)", min_confidence: 0.2, max_confidence: 0.4, decision_count: 0, success_count: 0, success_rate: null, avg_confidence: null, ece_contribution: null },
            { bucket: "[0.4-0.6)", min_confidence: 0.4, max_confidence: 0.6, decision_count: 0, success_count: 0, success_rate: null, avg_confidence: null, ece_contribution: null },
            { bucket: "[0.6-0.8)", min_confidence: 0.6, max_confidence: 0.8, decision_count: 0, success_count: 0, success_rate: null, avg_confidence: null, ece_contribution: null },
            { bucket: "[0.8-1.0]", min_confidence: 0.8, max_confidence: 1, decision_count: 1, success_count: 1, success_rate: 1, avg_confidence: 0.9, ece_contribution: 0.1 },
          ],
        });
      }
      if (path === "/api/subagent-specialists/spec-reviewer/preflight" && init?.method === "POST") {
        return jsonResponse({
          status: "passed",
          output_schema_sha256: "abcdef0123456789",
          budget_json: { max_runtime_seconds: 900 },
          errors: [],
        });
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderWithRouter(
      "/subagent-specialists/spec-reviewer",
      <SubagentSpecialistDetailPage />,
      fetchMock,
    );

    expect(await screen.findByText("代码审查专家")).toBeInTheDocument();
    expect(screen.getByText("No high severity issues")).toBeInTheDocument();
    expect(await screen.findByText("历史表现")).toBeInTheDocument();
    expect(screen.getByText("83.3%")).toBeInTheDocument();
    expect(screen.getByText("output_schema_violation")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /运行预检|Run Preflight/ }));
    expect(await screen.findByText("预检通过")).toBeInTheDocument();

    await waitFor(() => {
      const preflightCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input as RequestInfo | URL).endsWith("/preflight") && init?.method === "POST",
      );
      expect(JSON.parse(String(preflightCall?.[1]?.body))).toMatchObject({
        sample_output: { summary: "样例输出" },
      });
    });
  });
});
