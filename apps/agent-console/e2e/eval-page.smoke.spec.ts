/**
 * L2 Mocked Browser Test: Eval Harness Page
 *
 * Proves the Eval page renders datasets with case counts and baseline badges,
 * case lists with source run links, and eval run results with regression delta.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const API_RE = /http:\/\/127\.0\.0\.1:8000\/api\/.*/;

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const datasetsFixture = {
  items: [
    {
      id: "ds-001",
      name: "Regression Suite Alpha",
      description: "Primary regression dataset",
      case_count: 12,
      baseline_run_id: "eval-run-baseline-001",
      created_at: "2026-05-13T10:00:00.000Z",
    },
    {
      id: "ds-002",
      name: "Edge Cases",
      description: "Boundary condition tests",
      case_count: 5,
      baseline_run_id: null,
      created_at: "2026-05-13T11:00:00.000Z",
    },
  ],
  next_cursor: null,
};

const casesFixture = {
  items: [
    {
      id: "case-001",
      dataset_id: "ds-001",
      source_task_id: "run-source-task-001",
      input_json: { goal: "Validate harness chain" },
      expected_json: { status: "COMPLETED" },
      tags_json: ["regression", "saved-run"],
      created_at: "2026-05-13T10:30:00.000Z",
    },
    {
      id: "case-002",
      dataset_id: "ds-001",
      source_task_id: null,
      input_json: { goal: "Test tool selection" },
      expected_json: {},
      tags_json: ["tool-accuracy"],
      created_at: "2026-05-13T10:45:00.000Z",
    },
  ],
  next_cursor: null,
};

const evalRunsFixture = {
  items: [
    {
      id: "eval-run-001",
      dataset_id: "ds-001",
      agent_id: "default",
      status: "COMPLETED",
      metrics_json: {
        case_total: 12,
        passed_total: 10,
        task_success_rate: 0.83,
        tool_selection_accuracy: 0.91,
        avg_latency_ms: 1200,
      },
      results: [
        {
          id: "result-001",
          status: "PASSED",
          task_id: "run-source-task-001",
          scores_json: { task_success: 1 },
          grader_trace_json: { grader: "trace-v1" },
        },
        {
          id: "result-002",
          status: "FAILED",
          task_id: null,
          scores_json: { task_success: 0 },
          grader_trace_json: {},
        },
      ],
      created_at: "2026-05-13T12:00:00.000Z",
    },
  ],
  next_cursor: null,
};

const regressionFixture = {
  task_success_rate_delta: -0.15,
  tool_selection_accuracy_delta: -0.05,
  avg_latency_ms_delta: 200,
  is_regression: true,
  newly_failing_case_ids: ["case-002"],
  newly_passing_case_ids: [],
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Eval Harness page mocked smoke tests", () => {
  test.beforeEach(async ({ page }) => {
    await routeEvalApis(page);
  });

  test("Dataset list renders with case counts and baseline badge", async ({ page }) => {
    await page.goto("/evals");

    // Dataset names visible
    await expect(page.getByText("Regression Suite Alpha")).toBeVisible();
    await expect(page.getByText("Edge Cases")).toBeVisible();

    // Case counts visible
    await expect(page.getByText("12 个用例")).toBeVisible();
    await expect(page.getByText("5 个用例")).toBeVisible();

    // Baseline badge visible for first dataset
    await expect(page.getByText("基线", { exact: true })).toBeVisible();
  });

  test("Case list shows source run links", async ({ page }) => {
    await page.goto("/evals");

    // Wait for cases to load
    await expect(page.getByText("用例队列")).toBeVisible();

    // Source run links visible (truncated IDs — source_task_id.slice(0, 8))
    await expect(page.getByText("run-sour").first()).toBeVisible();
    await expect(page.getByText("手动录入").first()).toBeVisible();
    await expect(page.getByText("自定义").first()).toBeVisible();
  });

  test("Eval Run results display with regression delta", async ({ page }) => {
    await page.goto("/evals");

    // Latest eval run section
    await expect(page.getByText("最近评测运行").first()).toBeVisible();
    await expect(page.getByText("COMPLETED").first()).toBeVisible();

    // Regression delta section — Chinese: "回归对比"
    await expect(page.getByText("回归对比")).toBeVisible();
    await expect(page.getByText("回归门禁")).toBeVisible();
    await expect(page.getByText("API 已接入").first()).toBeVisible();
    await expect(page.getByText("已启用").first()).toBeVisible();

    // Regression warning with data-regression attribute
    const regressionEl = page.locator("[data-regression='true']");
    await expect(regressionEl).toBeVisible();

    // Newly failing cases count — Chinese: "新增失败"
    await expect(page.getByText("新增失败")).toBeVisible();
    await expect(page.getByText("手动录入").first()).toBeVisible();
    await expect(page.getByText("未知评分器")).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Route helpers
// ---------------------------------------------------------------------------

async function routeEvalApis(page: Page): Promise<void> {
  await page.route(API_RE, async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    // Dataset list
    if (path === "/api/evals/datasets" && method === "GET") {
      await fulfillJson(route, datasetsFixture);
      return;
    }

    // Cases for dataset
    if (path.match(/^\/api\/evals\/datasets\/[^/]+\/cases$/) && method === "GET") {
      await fulfillJson(route, casesFixture);
      return;
    }

    // Eval runs list
    if (path === "/api/evals/runs" && method === "GET") {
      await fulfillJson(route, evalRunsFixture);
      return;
    }

    // Regression delta
    if (path.match(/^\/api\/evals\/runs\/[^/]+\/regression$/) && method === "GET") {
      await fulfillJson(route, regressionFixture);
      return;
    }

    // Create eval run
    if (path.match(/^\/api\/evals\/datasets\/[^/]+\/runs$/) && method === "POST") {
      await fulfillJson(route, evalRunsFixture.items[0]);
      return;
    }

    // Fallback 404
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `Unhandled e2e route: ${path}` }),
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
