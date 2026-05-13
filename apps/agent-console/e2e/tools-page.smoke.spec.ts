/**
 * L2 Mocked Browser Test: Tools Page
 *
 * Proves the Tool Registry page renders tool names with risk levels,
 * MCP tools section, and Policy section.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const API_RE = /http:\/\/127\.0\.0\.1:8000\/api\/.*/;

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const toolRegistryFixture = {
  items: [
    {
      name: "read_file",
      description: "Read a file from the workspace",
      source: "builtin",
      category: "filesystem",
      risk_level: "low",
      requires_sandbox: false,
      network_policy: "deny",
      timeout_seconds: 30,
      allowed_roles: ["operator", "admin"],
      audit_level: "standard",
      mcp_server: null,
      mcp_method: null,
      input_schema: { type: "object", properties: { path: { type: "string" } } },
    },
    {
      name: "shell_exec",
      description: "Execute a shell command in sandbox",
      source: "builtin",
      category: "execution",
      risk_level: "high",
      requires_sandbox: true,
      network_policy: "sandbox-only",
      timeout_seconds: 60,
      allowed_roles: ["admin"],
      audit_level: "full",
      mcp_server: null,
      mcp_method: null,
      input_schema: { type: "object", properties: { command: { type: "string" } } },
    },
    {
      name: "web_search",
      description: "Search the web via MCP adapter",
      source: "mcp",
      category: "network",
      risk_level: "medium",
      requires_sandbox: false,
      network_policy: "allow",
      timeout_seconds: 15,
      allowed_roles: ["operator", "admin"],
      audit_level: "standard",
      mcp_server: "web-tools",
      mcp_method: "search",
      input_schema: { type: "object", properties: { query: { type: "string" } } },
    },
    {
      name: "db_query",
      description: "Execute a database query via MCP",
      source: "mcp",
      category: "data",
      risk_level: "critical",
      requires_sandbox: true,
      network_policy: "deny",
      timeout_seconds: 45,
      allowed_roles: ["admin"],
      audit_level: "full",
      mcp_server: "db-adapter",
      mcp_method: "query",
      input_schema: { type: "object", properties: { sql: { type: "string" } } },
    },
  ],
  categories: ["filesystem", "execution", "network", "data"],
  sources: ["builtin", "mcp"],
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Tools page mocked smoke tests", () => {
  test.beforeEach(async ({ page }) => {
    await routeToolsApis(page);
  });

  test("Tool Registry list renders with tool names and risk levels", async ({ page }) => {
    await page.goto("/tools");

    // Tool names visible
    await expect(page.getByText("read_file").first()).toBeVisible();
    await expect(page.getByText("shell_exec")).toBeVisible();
    await expect(page.getByText("web_search")).toBeVisible();
    await expect(page.getByText("db_query")).toBeVisible();

    // Risk level badges visible — labels are translated to Chinese
    // low → "低风险", high → "高风险", medium → "中风险", critical → "关键风险"
    await expect(page.getByText("低风险").first()).toBeVisible();
    await expect(page.getByText("高风险").first()).toBeVisible();
    await expect(page.getByText("中风险").first()).toBeVisible();
    await expect(page.getByText("关键风险").first()).toBeVisible();
  });

  test("MCP tools section renders", async ({ page }) => {
    await page.goto("/tools");

    // MCP tile — Chinese: "2 已注册"
    await expect(page.getByText("MCP").first()).toBeVisible();
    await expect(page.getByText("2 已注册")).toBeVisible();

    // MCP source filter button
    await expect(page.getByRole("button", { name: "mcp" })).toBeVisible();

    // MCP tool details visible in table
    await expect(page.getByText("web-tools.search")).toBeVisible();
    await expect(page.getByText("db-adapter.query")).toBeVisible();
  });

  test("Policy section renders", async ({ page }) => {
    await page.goto("/tools");

    // Policy tile — Chinese: "策略" with "2 高风险"
    await expect(page.getByText("策略").first()).toBeVisible();
    await expect(page.getByText("2 高风险")).toBeVisible();

    // Sandbox tile — Chinese: "沙箱" with "2 需要隔离"
    await expect(page.getByText("沙箱").first()).toBeVisible();
    await expect(page.getByText("2 需要隔离")).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Route helpers
// ---------------------------------------------------------------------------

async function routeToolsApis(page: Page): Promise<void> {
  await page.route(API_RE, async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (path === "/api/tools/registry") {
      await fulfillJson(route, toolRegistryFixture);
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
