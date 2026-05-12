import { expect, test, type Locator, type Page, type Route } from "@playwright/test";

const API_RE = /http:\/\/127\.0\.0\.1:8000\/api\/.*/;
const CHAT_STREAM_RE =
  /http:\/\/127\.0\.0\.1:8000\/api\/agents\/default\/runs\/chat\/stream/;

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
    {
      name: "deepseek-flash",
      label: "DeepSeek Flash",
      model: "deepseek-v4-flash",
    },
    {
      name: "deepseek-pro",
      label: "DeepSeek Pro",
      model: "deepseek-v4-pro",
    },
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

test.describe("Agent Workspace browser smoke", () => {
  test.beforeEach(async ({ page }) => {
    await routeWorkspaceApis(page);
  });

  test("desktop workspace controls stay distinct and usable", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openWorkspaceInEnglish(page);

    await expect(page.getByText("Model + Harness = Agent")).toBeVisible();
    await expect(page.getByText("Default Agent").first()).toBeVisible();
    await expect(composer(page)).toBeVisible();
    await expect(page.getByLabel("No run yet")).toBeVisible();

    await page.getByRole("button", { name: "Current model: deepseek-v4-flash" }).click();
    const headerModelList = page.getByRole("listbox", { name: "Switch model" });
    await expect(headerModelList).toBeVisible();
    await headerModelList.press("ArrowDown");
    await headerModelList.press("Enter");
    await expect(
      page.getByRole("button", { name: "Current model: deepseek-v4-pro" }),
    ).toBeVisible();
    await expect(headerModelList).toBeHidden();

    await page.getByRole("button", { name: "Tools/MCP: 2 available" }).click();
    const toolsDialog = page.getByRole("dialog", { name: "Tools" });
    await expect(toolsDialog).toBeVisible();
    await expect(toolsDialog.getByRole("button", { name: /@read_file/ })).toBeVisible();
    await expect(toolsDialog.getByText("Plugins / MCP")).toHaveCount(0);
    await expect(toolsDialog.getByText("github.search")).toHaveCount(0);
    await page.mouse.click(20, 20);
    await expect(toolsDialog).toBeHidden();

    await openComposerSettings(page);
    const settingsDialog = page.getByRole("dialog", { name: "Composer settings" });
    await expect(settingsDialog).toBeVisible();
    await expect(settingsDialog.getByText("Composer settings")).toHaveCount(0);
    await expect(
      settingsDialog.getByRole("button", { name: "Add photos and files" }),
    ).toBeVisible();
    await expect(settingsDialog.getByRole("switch", { name: "Plan mode" })).toBeVisible();
    await expect(settingsDialog.getByRole("button", { name: "Plugins / MCP" })).toBeVisible();
    await expect(settingsDialog.getByRole("button", { name: /close/i })).toHaveCount(0);
    await page.mouse.click(20, 20);
    await expect(settingsDialog).toBeHidden();

    await openComposerSettings(page);
    await page.getByRole("button", { name: "Plugins / MCP" }).click();
    await expect(page.getByText("github.search")).toBeVisible();
    await page.getByRole("button", { name: /@github_search/ }).click();
    await expect(composer(page)).toHaveValue("@github_search ");

    await composer(page).fill("/model ");
    await composer(page).press("Enter");
    const bottomModelDialog = page.getByRole("dialog", { name: "Switch model" });
    await expect(bottomModelDialog).toBeVisible();
    await expect(page.getByRole("dialog", { name: "Tools" })).toHaveCount(0);
    await bottomModelDialog.getByRole("option", { name: /deepseek-v4-flash/ }).click();
    await expect(
      page.getByRole("button", { name: "Current model: deepseek-v4-flash" }),
    ).toBeVisible();

    await openComposerSettings(page);
    await page.getByRole("switch", { name: "Plan mode" }).click();
    await expect(page.getByPlaceholder("Describe a goal; returns a markdown plan")).toBeVisible();

    await page.getByPlaceholder("Describe a goal; returns a markdown plan").fill("draft a plan");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByRole("alert")).toContainText("Cannot reach Harness backend");
    await expect(composer(page)).toBeVisible();
  });

  test("narrow workspace keeps compact popovers inside the viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openWorkspaceInEnglish(page);

    await expect(composer(page)).toBeVisible();
    await expect(page.getByRole("button", { name: "Send" })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Current model: deepseek-v4-flash" }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Tools/MCP: 2 available" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Open composer settings" })).toBeVisible();

    expect(await hasNoHorizontalOverflow(page)).toBe(true);

    await page.getByRole("button", { name: "Current model: deepseek-v4-flash" }).click();
    await expect(page.getByRole("listbox", { name: "Switch model" })).toBeVisible();
    await expect(
      locatorInsideViewport(page, page.getByRole("listbox", { name: "Switch model" })),
    ).resolves.toBe(true);
    await page.mouse.click(20, 20);

    await page.getByRole("button", { name: "Tools/MCP: 2 available" }).click();
    await expect(page.getByRole("dialog", { name: "Tools" })).toBeVisible();
    await expect(
      locatorInsideViewport(page, page.getByRole("dialog", { name: "Tools" })),
    ).resolves.toBe(true);
    await page.mouse.click(20, 20);

    await openComposerSettings(page);
    await expect(page.getByRole("dialog", { name: "Composer settings" })).toBeVisible();
    await expect(
      locatorInsideViewport(page, page.getByRole("dialog", { name: "Composer settings" })),
    ).resolves.toBe(true);
    await composer(page).fill("mobile smoke");
    await expect(composer(page)).toHaveValue("mobile smoke");
  });
});

async function routeWorkspaceApis(page: Page): Promise<void> {
  await page.route(API_RE, async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (CHAT_STREAM_RE.test(route.request().url())) {
      await route.abort("failed");
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

    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `Unhandled e2e API route: ${path}` }),
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

async function openWorkspaceInEnglish(page: Page): Promise<void> {
  await page.goto("/agents/default/workspace");
  await page.getByRole("button", { name: "语言" }).click();
  await expect(page.getByRole("button", { name: "Language" })).toBeVisible();
}

function composer(page: Page): Locator {
  return page.getByPlaceholder(/Chat with the agent|Describe a goal; returns a markdown plan/);
}

async function openComposerSettings(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Open composer settings" }).click();
}

async function hasNoHorizontalOverflow(page: Page): Promise<boolean> {
  return page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
  );
}

async function locatorInsideViewport(page: Page, locator: Locator): Promise<boolean> {
  const box = await locator.boundingBox();
  if (box === null) return false;
  const viewport = page.viewportSize();
  if (viewport === null) return false;
  return (
    box.width > 0 &&
    box.height > 0 &&
    box.x >= 0 &&
    box.y >= 0 &&
    box.x + box.width <= viewport.width + 1 &&
    box.y + box.height <= viewport.height + 1
  );
}
