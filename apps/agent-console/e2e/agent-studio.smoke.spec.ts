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

const knowledgeFixture = {
  items: [
    {
      id: "knowledge-default",
      organization_id: null,
      agent_id: "default",
      name: "团队手册",
      description: "运行规范和响应准则",
      source_type: "markdown",
      status: "ACTIVE",
      version: 1,
      settings_json: {},
      metadata_json: {},
      idempotency_key: null,
      created_by: null,
      created_at: "2026-05-15T00:00:00Z",
      updated_at: "2026-05-15T00:00:00Z",
      latest_documents: [
        {
          id: "document-handbook",
          source_id: "knowledge-default",
          organization_id: null,
          agent_id: "default",
          title: "团队手册",
          uri: null,
          content_sha256: "sha256",
          mime_type: "text/markdown",
          status: "INDEXED",
          version: 1,
          supersedes_document_id: null,
          ingestion_error: null,
          metadata_json: {},
          idempotency_key: null,
          created_by: null,
          created_at: "2026-05-15T00:00:00Z",
          updated_at: "2026-05-15T00:00:00Z",
          indexed_at: "2026-05-15T00:00:00Z",
          chunk_count: 3,
        },
      ],
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
    await expect(page.getByText("智能体工作室").first()).toBeVisible();

    // All 6 capability surfaces — uses text(zh, en) so Chinese labels
    await expect(page.getByText("模型").first()).toBeVisible();
    await expect(page.getByText("工具 / MCP").first()).toBeVisible();
    await expect(page.getByText("Prompt 提示词").first()).toBeVisible();
    await expect(page.getByText("RAG 知识检索").first()).toBeVisible();
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
    await expect(page.getByText("Default Agent", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Code Reviewer", { exact: true }).first()).toBeVisible();

    // API-backed status — Chinese: "API 已接入"
    await expect(page.getByText("API 已接入").first()).toBeVisible();
  });

  test("Disabled surfaces (RAG, Templates) show API-pending state", async ({ page }) => {
    await page.goto("/agents");

    // RAG surface visible
    await expect(page.getByText("RAG 知识检索").first()).toBeVisible();

    // Templates surface — Chinese: "模板"
    await expect(page.getByText("模板").first()).toBeVisible();

    // Both disabled surfaces have "未启用" (Disabled) status badges
    await expect(page.getByText("未启用").first()).toBeVisible();

    // Verify RAG description text
    await expect(
      page.getByText("RAG 指检索增强生成"),
    ).toBeVisible();

    // Verify disabled description text for Templates — Chinese
    await expect(
      page.getByText("模板市场保留禁用态"),
    ).toBeVisible();
  });

  test("Knowledge source metadata uses Chinese units", async ({ page }) => {
    await page.goto("/agents");

    await expect(page.getByPlaceholder("知识源名称")).toHaveValue("默认知识源");
    await expect(page.getByPlaceholder("文档标题")).toHaveValue("团队手册");
    await expect(page.locator("textarea")).toHaveValue("# 团队手册\n\n使用简洁、带引用的回答。\n");
    await expect(page.getByText("1 个来源")).toBeVisible();
    await expect(page.getByText("3 个分片 · INDEXED")).toBeVisible();
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

    if (path === "/api/agents/default/knowledge/sources" && route.request().method() === "GET") {
      await fulfillJson(route, knowledgeFixture);
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
