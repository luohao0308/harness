import { expect, test, type Page, type Route } from "@playwright/test";

const API_RE = /http:\/\/(?:127\.0\.0\.1|localhost):\d+\/api\/.*/;
const now = "2026-05-27T02:00:00.000Z";

function knowledgeDocument(overrides: Record<string, unknown> = {}) {
  return {
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
    logical_document_id: "document-handbook",
    supersedes_document_id: null,
    superseded_at: null,
    ingestion_error: null,
    metadata_json: {},
    idempotency_key: null,
    created_by: null,
    created_at: now,
    updated_at: now,
    indexed_at: now,
    chunk_count: 3,
    ...overrides,
  };
}

function knowledgeSource(overrides: Record<string, unknown> = {}) {
  return {
    id: "knowledge-default",
    organization_id: null,
    agent_id: "default",
    name: "团队手册",
    description: "运行规范和响应准则",
    source_type: "markdown",
    status: "ACTIVE",
    version: 1,
    scope: "agent",
    expires_at: null,
    disabled_at: null,
    archived_at: null,
    last_indexed_at: now,
    last_ingestion_error: null,
    health_status: "HEALTHY",
    settings_json: {},
    metadata_json: {},
    idempotency_key: null,
    created_by: null,
    created_at: now,
    updated_at: now,
    latest_documents: [knowledgeDocument()],
    ...overrides,
  };
}

test.describe("Agent Studio feedback smoke", () => {
  test.beforeEach(async ({ page }) => {
    await routeAgentStudioApis(page);
  });

  test("Agent Studio create, clone, attach, and token plan actions show visible feedback", async ({ page }) => {
    await page.goto("/agents");

    await expect(page.getByRole("heading", { name: "智能体工作室" })).toBeVisible();
    await page.getByRole("button", { name: "创建智能体" }).click();
    await expect(page.getByText("智能体创建成功")).toBeVisible();

    await page.getByRole("button", { name: "克隆当前智能体" }).click();
    await expect(page.getByText("智能体克隆成功")).toBeVisible();

    await page.getByRole("button", { name: "配置能力附件" }).click();
    const capabilityDialog = page.getByRole("dialog", { name: "配置能力附件" });
    await expect(capabilityDialog).toBeVisible();
    await capabilityDialog.getByRole("button", { name: "附加到当前智能体" }).click();
    await expect(page.getByText("能力附件已保存")).toBeVisible();

    await page.getByRole("button", { name: /强力省 Token/ }).click();
    await expect(page.getByText("Token 方案已切换")).toBeVisible();
  });

  test("Model settings save shows success feedback in browser", async ({ page }) => {
    await page.goto("/settings/models");

    await expect(page.getByText("DeepSeek Flash")).toBeVisible();
    await page.getByRole("button", { name: /添加并切换/ }).nth(0).click();
    await expect(page.getByRole("status").getByText("模型配置已保存")).toBeVisible();
  });

  test("Knowledge source creation shows visible feedback", async ({ page }) => {
    await page.goto("/agents");

    await page.getByRole("button", { name: "本地文档" }).click();
    const createDialog = page.getByRole("dialog", { name: "新增本地知识" });
    await createDialog.getByLabel("知识源名称").fill("客户支持手册");
    await createDialog.getByLabel("初始文档内容").fill("这里是客户支持手册内容。");
    await createDialog.getByRole("button", { name: "创建" }).click();

    await expect(page.getByRole("status").getByText("知识源已创建")).toBeVisible();
  });

  test("Knowledge edit, add document, and reingest actions show visible feedback", async ({
    page,
  }) => {
    await page.goto("/agents");

    await expect(page.getByText("团队手册").first()).toBeVisible();

    await page.getByRole("button", { name: "编辑" }).click();
    const editDialog = page.getByRole("dialog", { name: "编辑本地知识源" });
    await editDialog.getByLabel("编辑知识源说明").fill("更新后的说明");
    await editDialog.getByRole("button", { name: "保存" }).click();
    await expect(page.getByRole("status").getByText("知识源已更新")).toBeVisible();

    await page.getByRole("button", { name: "新增文档" }).click();
    const addDialog = page.getByRole("dialog", { name: "新增文档" });
    await addDialog.getByLabel("新增文档内容").fill("新增知识文档内容。");
    await addDialog.getByRole("button", { name: "添加" }).click();
    await expect(page.getByRole("status").getByText("文档已添加")).toBeVisible();

    await page.getByRole("button", { name: "重新导入" }).click();
    const reingestDialog = page.getByRole("dialog", { name: "重新导入" });
    await reingestDialog.getByLabel("重新导入内容").fill("团队手册 v2 内容。");
    await reingestDialog.getByRole("button", { name: "创建版本" }).click();
    const confirmDialog = page.getByRole("dialog", { name: "重新导入文档" });
    await confirmDialog.getByRole("button", { name: "确认创建版本" }).click();
    await expect(page.getByRole("status").getByText("文档新版本已创建")).toBeVisible();
  });
});

async function routeAgentStudioApis(page: Page): Promise<void> {
  const sources = [knowledgeSource()];
  const documentsBySourceId = new Map<string, Array<Record<string, unknown>>>([
    ["knowledge-default", [knowledgeDocument()]],
  ]);

  await page.route(API_RE, async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname + url.search;
    const method = route.request().method();

    if (path === "/api/agents" && method === "GET") {
      await fulfillJson(route, {
        items: [
          {
            id: "default",
            name: "默认智能体",
            description: "默认入口智能体",
            role: "planner",
            status: "ACTIVE",
            model_provider: "default",
            model_name: "default",
            system_prompt: "Plan with evidence",
            tools_json: ["mcp_context_search"],
            routing_tags: ["default"],
            max_parallel_assignments: 2,
            capability_attachments: [
              {
                attachment_id: "attachment-optimizer",
                capability_id: "cap-optimizer",
                capability_key: "builtin:context-optimizer:balanced",
                capability_version_id: "builtin-balanced-version-1",
                capability_type: "context_optimizer",
                enabled: true,
                priority: 5,
                status: "active",
              },
            ],
            created_at: "2026-05-18T00:00:00Z",
            updated_at: "2026-05-18T00:00:00Z",
          },
        ],
        next_cursor: null,
      });
      return;
    }

    if (path === "/api/agents/token-optimizer/presets" && method === "GET") {
      await fulfillJson(route, {
        items: [
          { preset_id: "off", display_name: "关闭", description: "不启用额外 Token Optimizer。", enabled: false, priority: null },
          { preset_id: "conservative", display_name: "保守省 Token", description: "轻量裁剪低相关证据。", enabled: true, priority: 5 },
          { preset_id: "balanced", display_name: "均衡", description: "推荐默认方案。", enabled: true, priority: 5 },
          { preset_id: "aggressive", display_name: "强力省 Token", description: "更积极限制候选上下文。", enabled: true, priority: 5 },
        ],
      });
      return;
    }

    if (path === "/api/agents/default/knowledge/sources" && method === "GET") {
      await fulfillJson(route, { items: sources, next_cursor: null });
      return;
    }

    if (path === "/api/agents/default/knowledge/sources" && method === "POST") {
      const created = knowledgeSource({
        id: "knowledge-created",
        name: "客户支持手册",
        description: "这里是客户支持手册内容。",
        latest_documents: [
          knowledgeDocument({
            id: "document-created",
            source_id: "knowledge-created",
            title: "团队手册",
          }),
        ],
      });
      sources.unshift(created);
      documentsBySourceId.set("knowledge-created", created.latest_documents);
      await fulfillJson(route, created, 201);
      return;
    }

    if (path === "/api/agents/default/knowledge/sources/knowledge-default" && method === "PATCH") {
      sources[0] = {
        ...sources[0],
        description: "更新后的说明",
        updated_at: now,
      };
      await fulfillJson(route, sources[0]);
      return;
    }

    if (path === "/api/agents/default/knowledge/sources/knowledge-default/documents" && method === "GET") {
      await fulfillJson(route, documentsBySourceId.get("knowledge-default") ?? []);
      return;
    }

    if (path === "/api/agents/default/knowledge/sources/knowledge-created/documents" && method === "GET") {
      await fulfillJson(route, documentsBySourceId.get("knowledge-created") ?? []);
      return;
    }

    if (path === "/api/agents/default/knowledge/sources/knowledge-default/documents" && method === "POST") {
      const documents = documentsBySourceId.get("knowledge-default") ?? [];
      const nextDocument = knowledgeDocument({
        id: `document-${documents.length + 1}`,
        version: documents.length + 1,
        title: "补充文档",
      });
      documentsBySourceId.set("knowledge-default", [nextDocument, ...documents]);
      sources[0] = {
        ...sources[0],
        latest_documents: documentsBySourceId.get("knowledge-default"),
      };
      await fulfillJson(route, sources[0], 201);
      return;
    }

    if (
      /^\/api\/agents\/default\/knowledge\/sources\/knowledge-default\/documents\/[^/]+\/versions$/.test(path) &&
      method === "POST"
    ) {
      const documents = documentsBySourceId.get("knowledge-default") ?? [];
      const nextVersion = knowledgeDocument({
        id: "document-handbook-v2",
        version: 2,
        logical_document_id: "document-handbook",
        supersedes_document_id: "document-handbook",
        title: "团队手册",
      });
      documentsBySourceId.set("knowledge-default", [nextVersion, ...documents]);
      sources[0] = {
        ...sources[0],
        latest_documents: documentsBySourceId.get("knowledge-default"),
      };
      await fulfillJson(route, sources[0], 201);
      return;
    }

    if (path === "/api/agents" && method === "POST") {
      await fulfillJson(route, { id: "research-agent", name: "研究智能体" });
      return;
    }

    if (path === "/api/agents/default/clone" && method === "POST") {
      await fulfillJson(route, { id: "default-clone", name: "默认智能体克隆副本" });
      return;
    }

    if (path === "/api/agents/default/capabilities/attachments" && method === "POST") {
      await fulfillJson(route, { status: "attached" });
      return;
    }

    if (path === "/api/agents/default/token-optimizer" && method === "POST") {
      await fulfillJson(route, {
        status: "selected",
        preset_id: "aggressive",
        attachment_id: "attachment-aggressive",
        capability_id: "cap-aggressive",
        capability_version_id: "version-aggressive",
        enabled: true,
        priority: 5,
      });
      return;
    }

    if (path === "/api/settings/models" && method === "GET") {
      await fulfillJson(route, {
        default_provider: "openai-compatible",
        default_model: "default",
        providers: [],
        rate_limits: { rpm: 600, tpm: 120000 },
        health: {
          status: "healthy",
          updated_at: null,
          mode: "mock",
          latency_ms: 0,
          error_message: null,
        },
        circuit_breaker: { failure_threshold: 3, cooldown_seconds: 60 },
      });
      return;
    }

    if (path === "/api/settings/models" && method === "PUT") {
      await fulfillJson(route, {
        default_provider: "deepseek-flash",
        default_model: "deepseek-v4-flash",
        providers: [
          {
            name: "deepseek-flash",
            label: "DeepSeek Flash",
            model: "deepseek-v4-flash",
            api_format: "openai",
            base_url: "https://api.deepseek.com",
            api_key: "replace-me",
          },
        ],
        rate_limits: { rpm: 600, tpm: 120000 },
        health: {
          status: "healthy",
          updated_at: null,
          mode: "mock",
          latency_ms: 0,
          error_message: null,
        },
        circuit_breaker: { failure_threshold: 3, cooldown_seconds: 60 },
      });
      return;
    }

    if (path === "/api/settings/models/health" && method === "GET") {
      await fulfillJson(route, { items: [] });
      return;
    }

    if (path === "/api/settings/models/fallbacks?limit=20" && method === "GET") {
      await fulfillJson(route, {
        organization_id: "dev-org",
        fallback_total: 0,
        primary_failure_total: 0,
        providers: [],
        recent_events: [],
      });
      return;
    }

    await fulfillJson(route, { detail: `unexpected ${method} ${path}` }, 404);
  });
}

async function fulfillJson(route: Route, payload: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}
