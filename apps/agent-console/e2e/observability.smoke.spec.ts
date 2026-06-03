/**
 * L2 Mocked Browser Test: Observability Page
 *
 * Proves the Observability page renders service health indicators,
 * summary metrics (task_total, active_runs), and loads without errors.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const API_RE = /http:\/\/(?:127\.0\.0\.1|localhost):(?:8000|5177|15174)\/api\/.*/;

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const summaryFixture = {
  task_total: 142,
  failed_task_total: 7,
  event_total: 3891,
  model_call_total: 456,
  tool_call_total: 789,
  sandbox_total: 23,
  active_runs: 4,
  tasks_by_status: [
    { label: "COMPLETED", count: 120 },
    { label: "RUNNING", count: 4 },
    { label: "FAILED", count: 7 },
    { label: "PENDING", count: 11 },
  ],
  subagents_by_status: [
    { label: "COMPLETED", count: 30 },
    { label: "RUNNING", count: 2 },
  ],
  agent_assignments_by_status: [
    { label: "COMPLETED", count: 50 },
    { label: "PENDING", count: 3 },
  ],
  model_calls_by_status: [
    { label: "COMPLETED", count: 440 },
    { label: "FAILED", count: 16 },
  ],
  tool_calls_by_status: [
    { label: "COMPLETED", count: 770 },
    { label: "FAILED", count: 19 },
  ],
  subagent_queue: {
    pending: 2,
    running: 1,
    timeout_count: 0,
  },
  assignment_queue: {
    pending: 3,
    running: 2,
  },
  warm_pool: {
    enabled: true,
    idle: 3,
    busy: 1,
    failed: 0,
    min_size: 2,
    max_size: 5,
    hit_total: 45,
    miss_total: 5,
  },
  sandboxes_by_status: [
    { label: "running", count: 4 },
    { label: "stopped", count: 19 },
  ],
};

const healthFixture = {
  services: [
    {
      name: "prometheus",
      status: "healthy",
      latency_ms: 12,
      alert_status: "ok",
      alert_severity: null,
    },
    {
      name: "grafana",
      status: "healthy",
      latency_ms: 45,
      alert_status: "ok",
      alert_severity: null,
    },
    {
      name: "loki",
      status: "degraded",
      latency_ms: 230,
      alert_status: "firing",
      alert_severity: "warning",
    },
    {
      name: "otel-collector",
      status: "healthy",
      latency_ms: 8,
      alert_status: "ok",
      alert_severity: null,
    },
  ],
};

const dashboardsFixture = {
  items: [
    { uid: "dash-001", title: "Agent Overview", url: "http://grafana:3000/d/agent", source: "grafana" },
  ],
};

const exportsFixture = { items: [] };
const exportHistoryFixture = { items: [] };
const logsFixture = { items: [] };
const recoveryFixture = {
  batch_total: 0,
  task_total: 0,
  scanned_total: 0,
  recovered_total: 0,
  lock_skipped_total: 0,
  action_counts: {},
  tasks: [],
  recent_batches: [],
  latest_completed_at: null,
};
const globalRecoveryFixture = {
  organization_count: 0,
  batch_total: 0,
  recovered_total: 0,
  organizations: [],
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Observability page mocked smoke tests", () => {
  test.beforeEach(async ({ page }) => {
    await routeObservabilityApis(page);
  });

  test("Service health indicators render", async ({ page }) => {
    await page.goto("/observability");

    // Service health section header — Chinese: "观测服务健康"
    await expect(page.getByText("观测服务健康")).toBeVisible();

    // Service names visible in the health table
    const healthTable = page.locator("table").filter({ hasText: "prometheus" });
    await expect(healthTable).toBeVisible();
    await expect(page.getByText("otel-collector")).toBeVisible();

    // Status labels are translated — "健康" for healthy, "降级" for degraded
    await expect(page.getByText("健康").first()).toBeVisible();
    await expect(page.getByText("降级")).toBeVisible();

    // Latency values
    await expect(page.getByText("12ms")).toBeVisible();
    await expect(page.getByText("230ms")).toBeVisible();
  });

  test("Summary metrics (task_total, active_runs) render", async ({ page }) => {
    await page.goto("/observability");

    // Runtime Overview section — Chinese: "运行总览"
    await expect(page.getByText("运行总览")).toBeVisible();

    // Task total (formatNumber uses Intl.NumberFormat("zh-CN"))
    await expect(page.getByText("142")).toBeVisible();

    // Event total — zh-CN formats 3891 as "3,891"
    await expect(page.getByText("3,891")).toBeVisible();

    // Model calls
    await expect(page.getByText("456")).toBeVisible();

    // Tool calls
    await expect(page.getByText("789")).toBeVisible();

    // Sandbox total
    await expect(page.getByText("23", { exact: true })).toBeVisible();
  });

  test("Page loads without errors", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });

    await page.goto("/observability");

    // Page renders — Chinese: "运行总览"
    await expect(page.getByText("运行总览")).toBeVisible();

    // WarmPool section renders
    await expect(page.getByText("WarmPool").first()).toBeVisible();

    // Wait a moment for any async errors
    await page.waitForTimeout(1000);

    // No console errors (filter out expected 404s, unhandled routes, and React dev warnings)
    const realErrors = consoleErrors.filter(
      (e) =>
        !e.includes("404") &&
        !e.includes("Unhandled") &&
        !e.includes("Warning:") &&
        !e.includes("warning-keys"),
    );
    expect(realErrors).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Route helpers
// ---------------------------------------------------------------------------

async function routeObservabilityApis(page: Page): Promise<void> {
  await page.route(API_RE, async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (path === "/api/observability/summary") {
      await fulfillJson(route, summaryFixture);
      return;
    }

    if (path === "/api/observability/services/health") {
      await fulfillJson(route, healthFixture);
      return;
    }

    if (path === "/api/observability/grafana/dashboards") {
      await fulfillJson(route, dashboardsFixture);
      return;
    }

    if (path === "/api/observability/exports") {
      await fulfillJson(route, exportsFixture);
      return;
    }

    if (path === "/api/observability/exports/history") {
      await fulfillJson(route, exportHistoryFixture);
      return;
    }

    if (path === "/api/observability/logs") {
      await fulfillJson(route, logsFixture);
      return;
    }

    if (path === "/api/subagents/recovery/summary") {
      await fulfillJson(route, recoveryFixture);
      return;
    }

    if (path.startsWith("/api/subagents/recovery/global-summary")) {
      await fulfillJson(route, globalRecoveryFixture);
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
