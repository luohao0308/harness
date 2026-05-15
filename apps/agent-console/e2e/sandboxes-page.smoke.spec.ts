/**
 * L2 Mocked Browser Test: Sandboxes Page
 *
 * Proves the Sandboxes page renders WarmPool status (min_ready, max_ready),
 * sandbox instances with lifecycle state, and Tenant Isolation section.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const API_RE = /http:\/\/127\.0\.0\.1:8000\/api\/.*/;

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const warmPoolFixture = {
  idle: 3,
  busy: 1,
  failed: 0,
  min_size: 2,
  max_size: 5,
  hit_total: 87,
  miss_total: 13,
};

const quotaFixture = {
  organization_id: "org-harness-001",
  sandbox_total: 15,
  running_total: 4,
  running_memory_limit_mb_total: 2048,
  running_cpu_limit_total: 4.0,
  configured_memory_mb: 512,
  configured_cpus: "1.0",
  configured_workspace_quota_mb: 1024,
  network_enabled_total: 2,
};

const quotaHistoryFixture = {
  items: [
    {
      id: "sb-instance-001",
      status: "running",
      cpu_limit: "0.5",
      memory_limit_mb: 256,
      network_enabled: true,
      warm_pool_reused: true,
      lifetime_seconds: 120,
      created_at: "2026-05-13T11:00:00.000Z",
    },
    {
      id: "sb-instance-002",
      status: "stopped",
      cpu_limit: "1.0",
      memory_limit_mb: 512,
      network_enabled: false,
      warm_pool_reused: false,
      lifetime_seconds: 45,
      created_at: "2026-05-13T10:30:00.000Z",
    },
    {
      id: "sb-instance-003",
      status: "running",
      cpu_limit: "0.5",
      memory_limit_mb: 256,
      network_enabled: true,
      warm_pool_reused: true,
      lifetime_seconds: 300,
      created_at: "2026-05-13T09:00:00.000Z",
    },
  ],
  next_cursor: null,
};

const benchmarksFixture = {
  items: [
    {
      id: "bench-001",
      status: "COMPLETED",
      warm_avg_ms: 12,
      warm_p95_ms: 28,
      cold_avg_ms: 450,
      hit_rate: 87,
      iteration_count: 50,
      created_at: "2026-05-13T12:00:00.000Z",
    },
  ],
  next_cursor: null,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Sandboxes page mocked smoke tests", () => {
  test.beforeEach(async ({ page }) => {
    await routeSandboxApis(page);
  });

  test("WarmPool status renders (min_ready=2, max_ready=5)", async ({ page }) => {
    await page.goto("/sandboxes");

    // WarmPool section visible
    await expect(page.getByText("WarmPool").first()).toBeVisible();

    // Capacity shows min/max
    await expect(page.getByText("2 / 5").first()).toBeVisible();

    // WarmPool description mentions min_ready=2 and max_ready=5
    await expect(page.getByText("min_ready=2")).toBeVisible();
    await expect(page.getByText("max_ready=5")).toBeVisible();
  });

  test("Sandbox instances render with lifecycle state", async ({ page }) => {
    await page.goto("/sandboxes");

    // Quota History section — Chinese: "配额历史审计"
    await expect(page.getByText("配额历史审计")).toBeVisible();

    // Instance IDs (truncated to 8 chars)
    await expect(page.getByText("sb-insta").first()).toBeVisible();

    // Lifecycle states
    await expect(page.getByText("running").first()).toBeVisible();
    await expect(page.getByText("stopped").first()).toBeVisible();

    // WarmPool reuse indicators — Chinese: "复用" and "冷启动"
    await expect(page.getByText("复用").first()).toBeVisible();
    await expect(page.getByText("冷启动").first()).toBeVisible();
  });

  test("Tenant Isolation section visible", async ({ page }) => {
    await page.goto("/sandboxes");

    // Tenant Isolation tile — Chinese: "多租户隔离"
    await expect(page.getByText("多租户隔离")).toBeVisible();

    // Status shows Chinese API-backed state (because organization_id is present)
    await expect(page.getByText("API 已接入").first()).toBeVisible();

    // Description mentions organization_id scoping
    await expect(page.getByText("organization_id")).toBeVisible();
    await expect(page.getByText("API 网关")).toBeVisible();
    await expect(page.getByText("WarmPool 基准测试")).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Route helpers
// ---------------------------------------------------------------------------

async function routeSandboxApis(page: Page): Promise<void> {
  await page.route(API_RE, async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (path === "/api/sandboxes/warm-pool") {
      await fulfillJson(route, warmPoolFixture);
      return;
    }

    if (path === "/api/sandboxes/quota/usage") {
      await fulfillJson(route, quotaFixture);
      return;
    }

    if (path === "/api/sandboxes/quota/history") {
      await fulfillJson(route, quotaHistoryFixture);
      return;
    }

    if (path === "/api/sandboxes/warm-pool/benchmarks") {
      await fulfillJson(route, benchmarksFixture);
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
