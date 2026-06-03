import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RunDetailPage } from "../RunDetailPage";

const apiBaseUrl = "http://127.0.0.1:8000";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function workspacePayload() {
  return {
    run: {
      id: "run-1",
      title: "Optimizer run",
      goal: "Use token optimizer",
      status: "COMPLETED",
      model_provider: "default",
      model_name: "default",
      max_runtime_seconds: 1800,
      max_subagents: 2,
      enable_sandbox: true,
      enable_network: false,
      created_at: "2026-05-25T00:00:00Z",
      updated_at: "2026-05-25T00:01:00Z",
      completed_at: "2026-05-25T00:01:00Z",
    },
    plan: null,
    events: [],
    knowledge_grounding: null,
    context_assembly: {
      id: "manifest-1",
      organization_id: "dev-org",
      agent_id: "default",
      run_id: "run-1",
      retrieval_session_id: null,
      prompt_manifest_id: null,
      active_branch_id: null,
      active_leaf_id: null,
      mode: "authoritative",
      token_budget_json: {
        requested_max_tokens: 1000,
        estimator: "chars_div_4",
      },
      sections_json: [],
      included_refs_json: [],
      omitted_refs_json: [],
      policy_decisions_json: [],
      tombstoned_refs_json: [],
      context_text_sha256: "sha256",
      metadata_json: {},
      created_at: "2026-05-25T00:00:00Z",
    },
    token_optimization: {
      requested_max_tokens: 1000,
      estimated_candidate_tokens: 900,
      estimated_included_tokens: 500,
      estimated_saved_tokens: 400,
      estimated_savings_percent: 44.44,
      actual_prompt_tokens: 480,
      actual_completion_tokens: 80,
      included_count: 5,
      omitted_count: 3,
      pruning_applied: true,
      retrieval_cache: { hit_count: 1 },
      low_cost_routes: [],
      optimizer_capability_version_ids: ["optimizer-version-1"],
      optimizer_policy_hash: "abcdef1234567890abcdef",
      optimizer_decisions: [{ decision: "optimizer_applied" }],
      effective_strategy: { low_cost_route_hint: "summarization under budget" },
    },
    subagents: [],
    tool_calls: [],
    model_calls: [],
    approvals: [],
    assignments: [],
    handoffs: [],
  };
}

function langGraphWorkspacePayload() {
  const base = workspacePayload();
  return {
    ...base,
    plan: {
      id: "plan-1",
      task_id: "run-1",
      version: 1,
      status: "COMPLETED",
      summary: "LangGraph workflow plan",
      planner_source: "llm",
      planner_attempts: 1,
      planner_prompt_version: "planner-v1",
      quality_score: 1,
      validation_warnings: [],
      quality_gates: {},
      plan_json: {},
      created_at: "2026-05-25T00:00:00Z",
      steps: [
        {
          step_key: "graph_step",
          description: "Run approved LangGraph workflow node",
          depends_on: [],
          execution_mode: "langgraph_node",
          requires_sandbox: true,
          can_spawn_subagent: false,
          recommended_specialist_slug: null,
          fanout_specialist_slugs: [],
          fanout_aggregation: "none",
          tool_hints: [],
          acceptance_criteria: [],
          risk_level: "medium",
          artifact_expectations: [],
          quality_notes: [],
          status: "COMPLETED",
          assigned_agent_id: null,
          error_message: null,
          trace_summary: null,
          last_event_sequence: 3,
          execution_trace: [],
        },
      ],
    },
    events: [
      {
        id: "event-1",
        task_id: "run-1",
        agent_run_id: "run-1",
        sequence: 1,
        event_type: "LANGGRAPH_WORKFLOW_STARTED",
        payload_json: { workflow_name: "support-flow", graph_id: "triage" },
        actor_type: "system",
        actor_id: null,
        trace_id: "trace-1",
        created_at: "2026-05-25T00:00:00Z",
      },
      {
        id: "event-2",
        task_id: "run-1",
        agent_run_id: "run-1",
        sequence: 2,
        event_type: "LANGGRAPH_NODE_COMPLETED",
        payload_json: { graph_id: "triage", node_id: "classify" },
        actor_type: "system",
        actor_id: null,
        trace_id: "trace-1",
        created_at: "2026-05-25T00:00:01Z",
      },
      {
        id: "event-3",
        task_id: "run-1",
        agent_run_id: "run-1",
        sequence: 3,
        event_type: "LANGGRAPH_TOOL_NODE_DENIED",
        payload_json: { graph_id: "triage", node_id: "lookup", tool_name: "raw_network", denial_code: "bridge_required" },
        actor_type: "system",
        actor_id: null,
        trace_id: "trace-1",
        created_at: "2026-05-25T00:00:02Z",
      },
    ],
  };
}

function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/runs/run-1"]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/runs/:runId" element={<RunDetailPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("RunDetailPage token optimizer evidence", () => {
  it("renders context optimizer versions and policy hash", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/agents/runs/run-1/workspace") return jsonResponse(workspacePayload());
      if (path === "/api/evals/datasets") return jsonResponse({ items: [], next_cursor: null });
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    expect(await screen.findByText("上下文优化器")).toBeInTheDocument();
    expect(screen.getByText("权威组装")).toBeInTheDocument();
    expect(screen.getByText("字符数/4")).toBeInTheDocument();
    expect(screen.getByText("optimizer-version-1")).toBeInTheDocument();
    expect(screen.getByText("abcdef1234567890")).toBeInTheDocument();
    expect(screen.getByText("1 条决策")).toBeInTheDocument();
  });

  it("renders LangGraph plan mode and EventStore evidence in Run Detail", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/agents/runs/run-1/workspace") return jsonResponse(langGraphWorkspacePayload());
      if (path === "/api/evals/datasets") return jsonResponse({ items: [], next_cursor: null });
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    expect(await screen.findByText("LangGraph 证据")).toBeInTheDocument();
    expect(await screen.findByText("LangGraph 节点")).toBeInTheDocument();
    expect((await screen.findAllByText("LangGraph 工具节点拒绝")).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/graph: triage/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/tool: raw_network/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/denial: bridge_required/).length).toBeGreaterThan(0);
  });
});
