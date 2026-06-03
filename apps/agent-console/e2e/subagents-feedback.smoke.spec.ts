import { expect, test, type Page, type Route } from "@playwright/test";

const API_RE = /http:\/\/(?:127\.0\.0\.1|localhost):(?:8000|5177|15174)\/api\/.*/;
const now = "2026-05-27T03:00:00.000Z";

const subagentListFixture = {
  items: [
    {
      id: "subagent-running-001",
      task_id: "task-subagent-001",
      parent_agent_id: "default",
      agent_type: "researcher",
      status: "RUNNING",
      context_json: {
        label: "检索 MCP 商店反馈",
        step_key: "research-feedback",
        result: {
          context_summary: {
            total_tool_results: 2,
            retained_tool_results: 1,
            omitted_tool_results: 1,
          },
        },
      },
      started_at: now,
      completed_at: null,
      timeout_at: null,
      task_title: "验证商店链路",
      task_status: "RUNNING",
      step_key: "research-feedback",
    },
    {
      id: "subagent-success-002",
      task_id: "task-subagent-002",
      parent_agent_id: "default",
      agent_type: "writer",
      status: "SUCCESS",
      context_json: {
        label: "整理测试结论",
        result: {
          context_summary: {
            total_tool_results: 1,
            retained_tool_results: 1,
            omitted_tool_results: 0,
          },
        },
      },
      started_at: now,
      completed_at: now,
      timeout_at: null,
      task_title: "输出结论",
      task_status: "COMPLETED",
      step_key: "write-summary",
    },
  ],
  next_cursor: null,
};

const subagentDetailFixture = {
  id: "subagent-running-001",
  task_id: "task-subagent-001",
  parent_agent_id: "default",
  agent_type: "researcher",
  status: "RUNNING",
  context_json: {
    label: "检索 MCP 商店反馈",
    step_key: "research-feedback",
    assignment: {
      goal: "检查商店按钮点击后的提示是否清晰",
      risk_level: "low",
    },
    result: {
      summary: "正在整理商店反馈链路",
      context_summary: {
        total_tool_results: 2,
        retained_tool_results: 1,
        omitted_tool_results: 1,
      },
      tool_results: [],
      react_trace: [],
    },
  },
  started_at: now,
  completed_at: null,
  timeout_at: null,
};

const taskResultFixture = {
  task_id: "task-subagent-001",
  status: "RUNNING",
  summary: "子代理仍在运行",
  execution_plan: null,
  artifacts: [],
  subagent_results: [
    {
      id: "subagent-running-001",
      step_key: "research-feedback",
      status: "RUNNING",
      summary: "正在整理商店反馈链路",
      tool_results: [],
      artifacts: [],
      react_trace: [],
      context_summary: {
        total_tool_results: 2,
        retained_tool_results: 1,
        omitted_tool_results: 1,
      },
      completed_at: null,
    },
  ],
  last_sequence: 12,
  pending: true,
};

test.describe("Subagents feedback smoke", () => {
  test.beforeEach(async ({ page }) => {
    await routeSubagentApis(page);
  });

  test("bulk cancel shows visible success feedback", async ({ page }) => {
    await page.goto("/subagents");

    await expect(page.getByText("子代理批量运营")).toBeVisible();
    await page.getByLabel("选择当前页").click();
    await page.getByRole("button", { name: "批量取消" }).click();

    await expect(page.getByRole("status").getByText("批量取消已提交")).toBeVisible();
  });

  test("single subagent cancel shows visible success feedback", async ({ page }) => {
    await page.goto("/subagents/subagent-running-001");

    await expect(page.getByText("检索 MCP 商店反馈")).toBeVisible();
    await page.getByRole("button", { name: "取消子代理" }).click();

    await expect(page.getByRole("status").getByText("子代理已取消")).toBeVisible();
  });

  test("task links point to the concrete run and subagent views", async ({ page }) => {
    await page.goto("/subagents");

    await expect(
      page.getByRole("link", { name: "验证商店链路" }),
    ).toHaveAttribute("href", "/runs/task-subagent-001/subagents");

    await page.goto("/subagents/subagent-running-001");

    await expect(page.locator('a[href="/runs/task-subagent-001"]').first()).toHaveAttribute(
      "href",
      "/runs/task-subagent-001",
    );
    await expect(page.locator('a[href="/runs/task-subagent-001/subagents"]').last()).toHaveAttribute(
      "href",
      "/runs/task-subagent-001/subagents",
    );
  });
});

async function routeSubagentApis(page: Page): Promise<void> {
  await page.route(API_RE, async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    if (path === "/api/subagents" && method === "GET") {
      await fulfillJson(route, subagentListFixture);
      return;
    }

    if (path === "/api/subagents/bulk" && method === "POST") {
      await fulfillJson(route, {
        action: "cancel",
        requested_count: 1,
        succeeded_count: 1,
        failed_count: 0,
        items: [
          {
            id: "subagent-running-001",
            previous_status: "RUNNING",
            status: "CANCELLED",
            action: "cancel",
            success: true,
            error_message: null,
          },
        ],
      });
      return;
    }

    if (path === "/api/subagents/subagent-running-001" && method === "GET") {
      await fulfillJson(route, subagentDetailFixture);
      return;
    }

    if (path === "/api/subagents/subagent-running-001/cancel" && method === "POST") {
      await fulfillJson(route, {
        ...subagentDetailFixture,
        status: "CANCELLED",
      });
      return;
    }

    if (path === "/api/tasks/task-subagent-001/result" && method === "GET") {
      await fulfillJson(route, taskResultFixture);
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `Unhandled e2e route: ${method} ${path}` }),
    });
  });
}

async function fulfillJson(route: Route, payload: unknown): Promise<void> {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}
