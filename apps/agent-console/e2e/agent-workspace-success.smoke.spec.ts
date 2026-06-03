/**
 * L2 Mocked Browser Test: Workspace Success Path
 *
 * Proves the UI can perceive a successful Agent Run lifecycle through
 * deterministic SSE mocking — run_created, delta, tool_call_requested,
 * tool_call_result, artifact_created, usage, done.
 *
 * Part of the Complete Harness Validation Flow (L2 layer).
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const API_RE = /http:\/\/(?:127\.0\.0\.1|localhost):(?:8000|5177|15174)\/api\/.*/;
const CHAT_STREAM_RE =
  /http:\/\/(?:127\.0\.0\.1|localhost):(?:8000|5177|15174)\/api\/agents\/default\/runs\/chat\/stream/;

const STABLE_RUN_ID = "e2e-success-run-00000000-0000-0000-0000-000000000001";
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
  tools_json: ["read_file", "github_search"],
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
    {
      name: "github_search",
      description: "Search GitHub issues",
      category: "mcp",
      source: "mcp",
      risk_level: "low",
      requires_sandbox: false,
      network_policy: "restricted",
      timeout_seconds: 30,
      allowed_roles: ["engineer"],
      audit_level: "standard",
      idempotent: true,
      input_schema: {},
      mcp_server: "github",
      mcp_method: "search",
    },
  ],
  categories: ["filesystem", "mcp"],
  sources: ["builtin", "mcp"],
};

/**
 * Build a valid SSE frame string from event type and JSON data.
 * The frontend parser expects: event: <type>\ndata: <json>\n\n
 */
function sseFrame(eventType: string, data: Record<string, unknown>): string {
  return `event: ${eventType}\ndata: ${JSON.stringify(data)}\n\n`;
}

/**
 * Build the full SSE response body for a successful Workspace stream.
 */
function buildSuccessStreamBody(): string {
  const frames: string[] = [];

  frames.push(
    sseFrame("run_created", {
      run_id: STABLE_RUN_ID,
      status: "PLANNED",
      step_count: 1,
      message: "Run created",
    }),
  );

  frames.push(
    sseFrame("delta", {
      content: "I'll help you with that. Let me ",
    }),
  );

  frames.push(
    sseFrame("delta", {
      content: "read the file first.",
    }),
  );

  frames.push(
    sseFrame("tool_call_requested", {
      tool_call_id: "tc-001",
      tool_name: "read_file",
      source: "builtin",
      input_json: { path: "README.md" },
      status: "REQUESTED",
      risk: "low",
      sandbox: null,
      approval_id: null,
    }),
  );

  frames.push(
    sseFrame("tool_call_result", {
      tool_call_id: "tc-001",
      tool_name: "read_file",
      output_json: { content: "# AI Harness Platform" },
      output_summary: "File content returned",
      status: "COMPLETED",
      duration_ms: 42,
      trace_id: "trace-e2e-001",
      approval_id: null,
    }),
  );

  frames.push(
    sseFrame("artifact_created", {
      name: "readme-summary.md",
      artifact_type: "text",
      status: "created",
      content: "# Summary\nThe project is an AI Harness Platform.",
      run_id: STABLE_RUN_ID,
    }),
  );

  frames.push(
    sseFrame("usage", {
      input_tokens: 150,
      output_tokens: 80,
      cost_usd: "0.0012",
      cost_unavailable: false,
      ttfb_ms: 320,
      duration_ms: 1200,
      model_call_id: "mc-001",
    }),
  );

  frames.push(
    sseFrame("done", {
      run_id: STABLE_RUN_ID,
      status: "COMPLETED",
      step_count: 1,
      message: "Stream complete",
    }),
  );

  return frames.join("");
}

test.describe("Workspace success-flow browser smoke", () => {
  test.beforeEach(async ({ page }) => {
    await routeSuccessApis(page);
  });

  test("successful stream shows run chip, assistant content, tool evidence, artifact, and usable composer", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/agents/default/workspace");
    await expect(page.getByRole("button", { name: /Language|语言/ })).toHaveCount(0);

    // Verify initial idle state
    await expect(page.getByLabel("运行未创建")).toBeVisible();

    // Type and send a message
    const composer = page.getByPlaceholder("直接与智能体对话");
    await composer.fill("Read the README and summarize it");
    await sendButton(page).click();

    // After run_created: Run chip should show the run link
    // The shell bar shows a Link with aria-label "运行详情" when activeRunId is set
    await expect(
      runDetailLink(page),
    ).toBeVisible({ timeout: 10_000 });

    // After delta frames: assistant content should appear
    await expect(page.getByText("read the file first")).toBeVisible({ timeout: 5_000 });

    // After tool_call_requested + tool_call_result: tool evidence visible
    // The Workspace renders tool calls on the assistant node as buttons
    await expect(
      page.getByRole("button", { name: /@read_file.*COMPLETED/ }),
    ).toBeVisible({ timeout: 5_000 });

    // After artifact_created: artifact evidence visible in the conversation
    await expect(page.getByText("readme-summary.md")).toBeVisible({ timeout: 5_000 });

    // After done: composer should remain usable
    await expect(composer).toBeVisible();
    await expect(composer).toBeEnabled();

    // Inspector runtime section should be available for the created Run
    const inspectorBtn = page.getByRole("button", { name: "运行时" });
    if (await inspectorBtn.isVisible()) {
      await inspectorBtn.click();
      await expect(page.getByText(STABLE_RUN_ID.slice(0, 8))).toBeVisible();
    }
  });

  test("no unhandled API routes are hit during success flow", async ({ page }) => {
    const unhandledRoutes: string[] = [];
    page.on("response", (response) => {
      if (response.status() === 404 && response.url().includes("/api/")) {
        unhandledRoutes.push(response.url());
      }
    });

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/agents/default/workspace");
    await expect(page.getByRole("button", { name: /Language|语言/ })).toHaveCount(0);

    const composer = page.getByPlaceholder("直接与智能体对话");
    await composer.fill("test message");
    await sendButton(page).click();

    // Wait for stream to complete
    await expect(
      runDetailLink(page),
    ).toBeVisible({ timeout: 10_000 });

    // Allow time for any post-stream fetches
    await page.waitForTimeout(1000);

    expect(unhandledRoutes).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Route helpers
// ---------------------------------------------------------------------------

async function routeSuccessApis(page: Page): Promise<void> {
  await page.route(API_RE, async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (CHAT_STREAM_RE.test(route.request().url())) {
      await fulfillSseStream(route);
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

    // Workspace projection query (Inspector open)
    if (path.match(/^\/api\/agents\/runs\/[^/]+\/workspace$/)) {
      await fulfillJson(route, {
        run: {
          id: STABLE_RUN_ID,
          title: "E2E Success Run",
          goal: "Read the README and summarize it",
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

    // Fail-closed: return 404 for any unhandled API route
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `Unhandled e2e API route: ${path}` }),
    });
  });
}

async function fulfillSseStream(route: Route): Promise<void> {
  const body = buildSuccessStreamBody();
  await route.fulfill({
    status: 200,
    contentType: "text/event-stream",
    headers: {
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
    body,
  });
}

function sendButton(page: Page) {
  return page.locator('button[aria-label="发送"]');
}

function runDetailLink(page: Page) {
  return page.locator('a[aria-label="运行详情"]').first();
}

async function fulfillJson(route: Route, payload: unknown): Promise<void> {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}
