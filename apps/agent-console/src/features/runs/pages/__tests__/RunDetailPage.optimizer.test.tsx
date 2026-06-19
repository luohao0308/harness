import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
      agent_id: "default",
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

function failedOrchestrationWorkspacePayload() {
  const base = workspacePayload();
  return {
    ...base,
    run: {
      ...base.run,
      status: "FAILED",
      max_subagents: 5,
    },
    events: [
      {
        id: "event-failed",
        task_id: "run-1",
        agent_run_id: null,
        sequence: 13,
        event_type: "STEP_FAILED",
        payload_json: {
          step_key: "generate_outline",
          summary: "agent 客服 is not attached to capability read_file",
          tool_call_id: "tool-call-1",
          permission_boundary: "agent_capability_attachment",
        },
        actor_type: "system",
        actor_id: null,
        trace_id: "trace-1",
        created_at: "2026-05-25T00:00:02Z",
      },
      {
        id: "event-agent",
        task_id: "run-1",
        agent_run_id: null,
        sequence: 22,
        event_type: "AGENT_ASSIGNMENT_CREATED",
        payload_json: {
          assignment_id: "assignment-1",
          agent_id: "coder",
          status: "PENDING",
        },
        actor_type: "system",
        actor_id: null,
        trace_id: "trace-1",
        created_at: "2026-05-25T00:00:03Z",
      },
    ],
    assignments: [
      {
        id: "assignment-1",
        run_id: "run-1",
        agent_id: "coder",
        parent_assignment_id: null,
        step_key: null,
        role: "coder",
        status: "PENDING",
        input_json: {},
        output_json: {},
        created_at: "2026-05-25T00:00:03Z",
        started_at: null,
        completed_at: null,
      },
      {
        id: "assignment-2",
        run_id: "run-1",
        agent_id: "reviewer",
        parent_assignment_id: null,
        step_key: null,
        role: "reviewer",
        status: "SUCCESS",
        input_json: {},
        output_json: { summary: "reviewer inspected outputs" },
        created_at: "2026-05-25T00:00:04Z",
        started_at: "2026-05-25T00:00:04Z",
        completed_at: "2026-05-25T00:00:05Z",
      },
    ],
    handoffs: [
      {
        id: "handoff-1",
        run_id: "run-1",
        from_assignment_id: "assignment-1",
        to_assignment_id: "assignment-2",
        handoff_type: "reduce_input",
        status: "COMPLETED",
        payload_json: {},
        created_at: "2026-05-25T00:00:05Z",
        completed_at: "2026-05-25T00:00:05Z",
      },
    ],
  };
}

function renderPage(fetchMock: ReturnType<typeof vi.fn>, initialEntry = "/runs/run-1") {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/runs/:runId" element={<RunDetailPage />} />
          <Route path="/agents/:agentId/workspace" element={<div>workspace target</div>} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
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

  it("shows failure diagnosis and executable multi-agent orchestration evidence", async () => {
    const user = userEvent.setup();
    const executedPayload = failedOrchestrationWorkspacePayload();
    executedPayload.assignments = executedPayload.assignments.map((assignment) => ({
      ...assignment,
      status: "SUCCESS",
    }));
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/agents/runs/run-1/workspace") {
        return jsonResponse(failedOrchestrationWorkspacePayload());
      }
      if (path === "/api/evals/datasets") return jsonResponse({ items: [], next_cursor: null });
      if (path === "/api/agents/runs/run-1/orchestrate/execute" && init?.method === "POST") {
        return jsonResponse({
          run_id: "run-1",
          strategy: "parallel_fanout_reduce",
          routing_reasoning: "coder handles file writes",
          assignments: executedPayload.assignments,
          handoffs: executedPayload.handoffs,
          message: "executed",
        });
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    expect(await screen.findByText("失败原因")).toBeInTheDocument();
    expect(screen.getByText("agent 客服 is not attached to capability read_file")).toBeInTheDocument();
    expect(screen.getByText("步骤 generate_outline")).toBeInTheDocument();
    expect(screen.getByText("多智能体编排")).toBeInTheDocument();
    expect(screen.getAllByText("coder").length).toBeGreaterThan(0);
    expect(screen.getByText("reviewer inspected outputs")).toBeInTheDocument();
    expect(within(screen.getByText(/reduce_input:/).closest("div")!).getByText("已完成")).toBeInTheDocument();
    expect(screen.getByText("0/5")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /执行多智能体/ }));

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/agents/runs/run-1/orchestrate/execute"),
      expect.objectContaining({ method: "POST" }),
    );
    expect((await screen.findAllByText(/executed 当前证据/)).length).toBeGreaterThan(0);
  });

  it("keeps execute orchestration clickable when all assignments are already successful", async () => {
    const user = userEvent.setup();
    const completed = failedOrchestrationWorkspacePayload();
    completed.assignments = completed.assignments.map((assignment) => ({
      ...assignment,
      status: "SUCCESS",
    }));
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/agents/runs/run-1/workspace") return jsonResponse(completed);
      if (path === "/api/evals/datasets") return jsonResponse({ items: [], next_cursor: null });
      if (path === "/api/agents/runs/run-1/orchestrate/execute" && init?.method === "POST") {
        return jsonResponse({
          run_id: "run-1",
          strategy: "parallel_fanout_reduce",
          routing_reasoning: "already complete",
          assignments: completed.assignments,
          handoffs: completed.handoffs,
          message: "already complete",
        });
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    const executeButton = await screen.findByRole("button", { name: /多智能体已完成/ });
    expect(executeButton).not.toBeDisabled();

    await user.click(executeButton);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/agents/runs/run-1/orchestrate/execute"),
      expect.objectContaining({ method: "POST" }),
    );
    expect((await screen.findAllByText(/already complete 当前证据/)).length).toBeGreaterThan(0);
  });

  it("persists the originating workspace target across a Run Detail refresh", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/agents/runs/run-1/workspace") {
        return jsonResponse({
          ...workspacePayload(),
          run: { ...workspacePayload().run, agent_id: "support-agent" },
        });
      }
      if (path === "/api/evals/datasets") return jsonResponse({ items: [], next_cursor: null });
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    const { unmount } = renderPage(
      fetchMock,
      "/runs/run-1?return_to=%2Fagents%2Fsupport-agent%2Fworkspace%3Fconversation_id%3Dconv-42&conversation_id=conv-42",
    );
    expect(await screen.findByRole("link", { name: /回到工作台/ })).toHaveAttribute(
      "href",
      "/agents/support-agent/workspace?conversation_id=conv-42",
    );
    unmount();

    renderPage(fetchMock, "/runs/run-1");

    expect(await screen.findByRole("link", { name: /回到工作台/ })).toHaveAttribute(
      "href",
      "/agents/support-agent/workspace?conversation_id=conv-42",
    );
  });

  it("returns to the originating workspace conversation from query parameters", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/agents/runs/run-1/workspace") {
        return jsonResponse({
          ...workspacePayload(),
          run: { ...workspacePayload().run, agent_id: "support-agent" },
        });
      }
      if (path === "/api/evals/datasets") return jsonResponse({ items: [], next_cursor: null });
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(
      fetchMock,
      "/runs/run-1?return_to=%2Fagents%2Fsupport-agent%2Fworkspace%3Fconversation_id%3Dconv-42&conversation_id=conv-42",
    );

    expect(await screen.findByRole("link", { name: /回到工作台/ })).toHaveAttribute(
      "href",
      "/agents/support-agent/workspace?conversation_id=conv-42",
    );
  });
});
