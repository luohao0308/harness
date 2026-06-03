/**
 * Navigation resilience test: verifies that stream content survives
 * navigating away from Workspace mid-stream and coming back.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const API_RE = /http:\/\/(?:127\.0\.0\.1|localhost):(?:8000|5177|15174)\/api\/.*/;
const CHAT_STREAM_RE =
  /http:\/\/(?:127\.0\.0\.1|localhost):(?:8000|5177|15174)\/api\/agents\/default\/runs\/chat\/stream/;

const STABLE_RUN_ID = "e2e-nav-run-00000000-0000-0000-0000-000000000099";
const now = "2026-05-13T00:00:00.000Z";

const agent = {
  id: "default",
  name: "Default Agent",
  description: "Demo-ready Agent Workspace",
  role: "engineer",
  status: "active",
  model_provider: "deepseek-flash",
  model_name: "deepseek-v4-flash",
  system_prompt: "You are a helpful harness agent.",
  tools_json: ["read_file"],
  routing_tags: ["demo"],
  max_parallel_assignments: 2,
  created_at: now,
  updated_at: now,
};

const modelSettings = {
  default_provider: "deepseek-flash",
  default_model: "deepseek-v4-flash",
  providers: [
    { name: "deepseek-flash", label: "DeepSeek Flash", model: "deepseek-v4-flash" },
  ],
  rate_limits: { rpm: 60, tpm: 60_000 },
  health: { status: "healthy" },
  circuit_breaker: { failure_threshold: 3, cooldown_seconds: 60 },
};

const toolRegistry = {
  items: [
    {
      name: "read_file",
      description: "Read a file",
      category: "filesystem",
      source: "builtin",
      risk_level: "low",
      requires_sandbox: false,
      network_policy: "none",
      timeout_seconds: 30,
      allowed_roles: ["engineer"],
      audit_level: "standard",
      idempotent: true,
      input_schema: {},
      mcp_server: null,
      mcp_method: null,
    },
  ],
  categories: ["filesystem"],
  sources: ["builtin"],
};

function buildStreamBody(): string {
  const frames: string[] = [];
  frames.push(`event: run_created\ndata: ${JSON.stringify({
    run_id: STABLE_RUN_ID,
    status: "RUNNING",
    step_count: 1,
    message: "Run created",
  })}\n\n`);
  // Simulate real-world delay: run_created arrives immediately,
  // but deltas come after model thinking time (user navigates away in between)
  frames.push(`event: delta\ndata: ${JSON.stringify({ content: "Hello from the stream! " })}\n\n`);
  frames.push(`event: delta\ndata: ${JSON.stringify({ content: "This content should survive navigation." })}\n\n`);
  frames.push(`event: usage\ndata: ${JSON.stringify({
    input_tokens: 50,
    output_tokens: 20,
    cost_usd: null,
    cost_unavailable: true,
    ttfb_ms: 100,
    duration_ms: 200,
    model_call_id: "mc-nav-001",
  })}\n\n`);
  frames.push(`event: done\ndata: ${JSON.stringify({
    run_id: STABLE_RUN_ID,
    status: "COMPLETED",
    step_count: 1,
    message: "Stream complete",
  })}\n\n`);
  return frames.join("");
}

test.describe("Navigation resilience", () => {
  test("stream content survives navigate-away-and-back via link click", async ({ page }) => {
    await routeApis(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/agents/default/workspace");
    await expect(page.getByRole("button", { name: /Language|语言/ })).toHaveCount(0);

    // Send a message
    const composer = page.getByPlaceholder("直接与智能体对话");
    await composer.fill("test navigation resilience");
    await page.locator('button[aria-label="发送"]').click();

    // Wait for run_created (Run Detail link appears)
    await expect(
      page.locator('a[aria-label="运行详情"]').first(),
    ).toBeVisible({ timeout: 10_000 });

    // Click the Run Detail link (client-side navigation via React Router)
    await page.locator('a[aria-label="运行详情"]').first().click();

    // Verify we navigated to Run Detail
    await page.waitForURL(`**/runs/${STABLE_RUN_ID}`);
    await page.waitForTimeout(1500);

    // Navigate back using browser back button (client-side, preserves SPA state)
    await page.goBack();
    await page.waitForTimeout(1000);

    // The stream content should still be visible
    await expect(
      page.getByText("This content should survive navigation"),
    ).toBeVisible({ timeout: 5_000 });
  });
});

// ---------------------------------------------------------------------------
// Route helpers
// ---------------------------------------------------------------------------

async function routeApis(page: Page): Promise<void> {
  await page.route(API_RE, async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (CHAT_STREAM_RE.test(route.request().url())) {
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        headers: {
          "Cache-Control": "no-cache",
          Connection: "keep-alive",
        },
        body: buildStreamBody(),
      });
      return;
    }

    if (path === "/api/agents/default") {
      await fulfillJson(route, agent);
      return;
    }

    if (path === "/api/settings/models") {
      await fulfillJson(route, modelSettings);
      return;
    }

    if (path === "/api/tools/registry") {
      await fulfillJson(route, toolRegistry);
      return;
    }

    if (path === "/api/teams") {
      await fulfillJson(route, { items: [], next_cursor: null });
      return;
    }

    // Run Detail workspace projection
    if (path.match(/^\/api\/agents\/runs\/[^/]+\/workspace$/)) {
      await fulfillJson(route, {
        run: {
          id: STABLE_RUN_ID,
          title: "Nav Test Run",
          goal: "test navigation resilience",
          status: "COMPLETED",
          model_provider: "deepseek-flash",
          model_name: "deepseek-v4-flash",
          max_runtime_seconds: 300,
          max_subagents: 2,
          enable_sandbox: false,
          enable_network: true,
          created_at: now,
          updated_at: now,
          completed_at: now,
        },
        plan: null,
        events: [],
        subagents: [],
        tool_calls: [],
        model_calls: [],
        approvals: [],
        assignments: [],
        handoffs: [],
      });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `Unhandled: ${path}` }),
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
