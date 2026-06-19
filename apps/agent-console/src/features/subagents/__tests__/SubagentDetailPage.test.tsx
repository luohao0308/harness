import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SubagentDetailPage } from "../pages/SubagentDetailPage";

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

function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/subagents/subagent-1"]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/subagents/:subagentId" element={<SubagentDetailPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SubagentDetailPage", () => {
  it("surfaces worker summary and terminal action state when no specialist output exists", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === "/api/subagents/subagent-1") {
        return jsonResponse({
          id: "subagent-1",
          task_id: "task-1",
          parent_agent_id: null,
          agent_type: "subagent",
          status: "SUCCESS",
          specialist_id: null,
          fanout_batch_id: null,
          fanout_index: null,
          fanout_total: null,
          dynamic_fanout_origin: null,
          dynamic_fanout_requested_by: null,
          dynamic_fanout_reason: null,
          context_json: {
            label: "并行探针",
            step_key: "parallel_subagent_probe",
            result: {
              summary: "子代理已执行：完成并行探针，确认 Harness 子代理 worker 链路可消费任务。",
              tool_results: [],
              artifacts: [],
              react_trace: [
                {
                  round: 1,
                  executed_tool_count: 0,
                  next_tool_count: 0,
                  done: true,
                },
              ],
              context_summary: { total_tool_results: 0 },
            },
          },
          started_at: "2026-06-16T10:03:01Z",
          completed_at: "2026-06-16T10:03:02Z",
          timeout_at: null,
          specialist: null,
          output: null,
        });
      }
      if (path === "/api/tasks/task-1/result") {
        return jsonResponse({
          task_id: "task-1",
          status: "COMPLETED",
          summary: "Parent done",
          execution_plan: null,
          artifacts: [],
          subagent_results: [],
          last_sequence: 4,
          pending: false,
        });
      }
      if (path === "/api/tasks/task-1/fanout-batches") {
        return jsonResponse({ items: [], next_cursor: null });
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    expect(await screen.findByText("并行探针")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /查看所属任务子代理/ })).toHaveAttribute(
      "href",
      "/runs/task-1/subagents",
    );
    expect(screen.queryByRole("button", { name: /取消子代理/ })).not.toBeInTheDocument();
    expect(screen.getByText("终态不可取消")).toBeInTheDocument();
    expect(screen.getByText("执行结果")).toBeInTheDocument();
    expect(
      screen.getAllByText("子代理已执行：完成并行探针，确认 Harness 子代理 worker 链路可消费任务。").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText("这个子代理未绑定专家模板，因此没有结构化专家输出；上方执行结果来自 worker 结果摘要。"),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText("本次子代理没有调用工具；worker 已完成并写入执行结果摘要。").length,
    ).toBeGreaterThan(0);
  });

  it("renders specialist badge, structured output, and budget consumption", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === "/api/subagents/subagent-1") {
        return jsonResponse({
          id: "subagent-1",
          task_id: "task-1",
          parent_agent_id: null,
          agent_type: "subagent",
          status: "SUCCESS",
          specialist_id: "spec-reviewer",
          fanout_batch_id: "fanout-1",
          fanout_index: 0,
          fanout_total: 2,
          dynamic_fanout_origin: null,
          dynamic_fanout_requested_by: null,
          dynamic_fanout_reason: null,
          context_json: {
            label: "Review async step",
            step_key: "review",
            result: {
              summary: "Reviewed patch",
              tool_results: [],
              react_trace: [],
              context_summary: { total_tool_results: 0 },
            },
          },
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
            output_json: {
              summary: "No high severity issues",
              issues: [],
            },
            output_schema_sha256: "abcdef0123456789",
            budget_consumed_json: {
              runtime_seconds: 12,
              prompt_tokens: 100,
              completion_tokens: 40,
              tool_calls: 1,
              cost_usd: 0,
            },
            budget_exceeded_json: [],
            written_at: "2026-05-28T00:01:00Z",
          },
        });
      }
      if (path === "/api/tasks/task-1/result") {
        return jsonResponse({
          task_id: "task-1",
          status: "COMPLETED",
          summary: "Done",
          execution_plan: null,
          artifacts: [],
          subagent_results: [],
          last_sequence: 4,
          pending: false,
        });
      }
      if (path === "/api/tasks/task-1/fanout-batches") {
        return jsonResponse({
          items: [
            {
              fanout_batch_id: "fanout-1",
              task_id: "task-1",
              step_key: "review",
              fanout_total: 2,
              aggregation: "concat",
              statuses: { SUCCESS: 2 },
              members: [
                {
                  id: "subagent-1",
                  status: "SUCCESS",
                  specialist_id: "spec-reviewer",
                  specialist_slug: "code-reviewer",
                  fanout_index: 0,
                  dynamic_fanout_origin: null,
                  dynamic_fanout_requested_by: null,
                  dynamic_fanout_reason: null,
                  output_id: "output-1",
                },
                {
                  id: "subagent-2",
                  status: "SUCCESS",
                  specialist_id: "spec-researcher",
                  specialist_slug: "researcher",
                  fanout_index: 1,
                  dynamic_fanout_origin: "fanout-1",
                  dynamic_fanout_requested_by: "subagent-1",
                  dynamic_fanout_reason: "researcher_found_security_topic",
                  output_id: "output-2",
                },
              ],
              extend_history: [
                {
                  extend_index: 1,
                  reason: "researcher_found_security_topic",
                  requested_by_agent_run_id: "subagent-1",
                },
              ],
            },
          ],
          next_cursor: null,
        });
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    expect(await screen.findByText("Review async step")).toBeInTheDocument();
    expect(screen.getAllByText("code-reviewer").length).toBeGreaterThan(0);
    expect(screen.getByText("结构化专家输出")).toBeInTheDocument();
    expect(screen.getByText(/No high severity issues/)).toBeInTheDocument();
    expect(screen.getByText("runtime")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(await screen.findByText("Fanout 批次")).toBeInTheDocument();
    expect(screen.getByText("concat")).toBeInTheDocument();
    expect(screen.getByText("researcher")).toBeInTheDocument();
    expect(screen.getByText("动态新增")).toBeInTheDocument();
    expect(screen.getByText("动态扩缩 1 次")).toBeInTheDocument();
    await waitFor(() =>
      expect(fetchMock.mock.calls.map(([input]) => requestPath(input as RequestInfo | URL))).toContain(
        "/api/tasks/task-1/result",
      ),
    );
    expect(fetchMock.mock.calls.map(([input]) => requestPath(input as RequestInfo | URL))).toContain(
      "/api/tasks/task-1/fanout-batches",
    );
  });
});
