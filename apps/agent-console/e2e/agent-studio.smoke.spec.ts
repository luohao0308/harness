/**
 * L2 Mocked Browser Test: Agent Studio Page
 *
 * Proves the Agent Studio page renders Model, Tools/MCP, Prompt, RAG,
 * Templates, and Orchestration surfaces, shows model provider info,
 * and displays API-pending state for disabled surfaces.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const API_RE = /http:\/\/127\.0\.0\.1:8000\/api\/.*/;

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const agentsFixture = {
  items: [
    {
      id: "default",
      name: "Default Agent",
      description: "Primary agent for task execution with full harness capabilities",
      status: "active",
      role: "executor",
      model_name: "deepseek-v4-flash",
      model_provider: "deepseek-flash",
      max_parallel_assignments: 3,
      tools_json: ["read_file", "write_file", "shell_exec", "web_search"],
      routing_tags: ["general", "code"],
    },
    {
      id: "reviewer",
      name: "Code Reviewer",
      description: "Specialized agent for code review and quality checks",
      status: "active",
      role: "reviewer",
      model_name: "deepseek-v4-flash",
      model_provider: "deepseek-flash",
      max_parallel_assignments: 2,
      tools_json: ["read_file", "grep_search"],
      routing_tags: ["review", "quality"],
    },
  ],
  next_cursor: null,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Agent Studio page mocked smoke tests", () => {
  test.beforeEach(async ({ page }) => {
    await routeAgentStudioApis(page);
  });

  test("Agent Studio renders Model, Tools/MCP, Prompt, RAG, Templates, Orchestration surfaces", async ({
    page,
  }) => {
    await page.goto("/agents");

    // Page title
    await expect(page.getByText("Agent Studio").first()).toBeVisible();

    // All 6 capability surfaces — uses text(zh, en) so Chinese labels
    await expect(page.getByText("Model").first()).toBeVisible();
    await expect(page.getByText("Tools / MCP").first()).toBeVisible();
    await expect(page.getByText("Prompt").first()).toBeVisible();
    await expect(page.getByText("RAG").first()).toBeVisible();
    // Templates in Chinese is "模板"
    await expect(page.getByText("模板").first()).toBeVisible();
    // Orchestration in Chinese is "编排"
    await expect(page.getByText("编排").first()).toBeVisible();
  });

  test("Model provider info visible", async ({ page }) => {
    await page.goto("/agents");

    // Model provider info from agent cards
    await expect(page.getByText("deepseek-v4-flash").first()).toBeVisible();

    // Agent names visible
    await expect(page.getByText("Default Agent")).toBeVisible();
    await expect(page.getByText("Code Reviewer")).toBeVisible();

    // API-backed status — Chinese: "API 已接入"
    await expect(page.getByText("API 已接入").first()).toBeVisible();
  });

  test("Disabled surfaces (RAG, Templates) show API-pending state", async ({ page }) => {
    await page.goto("/agents");

    // RAG surface visible
    await expect(page.getByText("RAG").first()).toBeVisible();

    // Templates surface — Chinese: "模板"
    await expect(page.getByText("模板").first()).toBeVisible();

    // Both disabled surfaces have "未启用" (Disabled) status badges
    await expect(page.getByText("未启用").first()).toBeVisible();

    // Verify disabled description text for RAG — Chinese
    await expect(
      page.getByText("知识库入口保留禁用态"),
    ).toBeVisible();

    // Verify disabled description text for Templates — Chinese
    await expect(
      page.getByText("模板市场保留禁用态"),
    ).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Route helpers
// ---------------------------------------------------------------------------

async function routeAgentStudioApis(page: Page): Promise<void> {
  await page.route(API_RE, async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (path === "/api/agents" && route.request().method() === "GET") {
      await fulfillJson(route, agentsFixture);
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
