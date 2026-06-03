/**
 * L2 Mocked Browser Test: Tools Page
 *
 * Covers registry rendering, default install paths, and the MCP / Skill
 * marketplace flows with Chinese-first feedback and concrete validation cases.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const API_RE = /http:\/\/(?:127\.0\.0\.1|localhost):\d+\/api\/.*/;

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

const exampleSearchToolFixture = {
  name: "io-github-example-search",
  description: "Search external systems.",
  source: "mcp",
  category: "network",
  risk_level: "medium",
  requires_sandbox: false,
  network_policy: "allow",
  timeout_seconds: 30,
  allowed_roles: ["operator", "admin"],
  audit_level: "standard",
  mcp_server: "io.github.example/search",
  mcp_method: "search",
  input_schema: { type: "object", properties: { query: { type: "string" } } },
};

function braveRuntimeConfigFixture(configured: boolean) {
  return {
    agent_id: "default",
    tool_name: "brave",
    tool_description: "Search the web through Brave Search.",
    source: "mcp",
    capability_id: "cap-brave",
    capability_version_id: configured ? "brave-configured-version" : "brave-original-version",
    capability_config_sha256: configured ? "configuredhash123456" : "originalhash123456",
    attachment_id: "attachment-brave",
    attachment_enabled: true,
    configured,
    missing_fields: configured ? [] : ["endpoint_url"],
    transport: "http",
    endpoint_url: configured ? "https://api.search.brave.com/res/v1/web/search" : null,
    command: null,
    args: [],
    secret_ref: configured ? "secret://mcp/default/brave/api-key" : null,
    secret_configured: configured,
    timeout_seconds: 30,
    config_json: {},
    registry_visible: true,
    test_input_json: { query: "MCP 教程", limit: 3 },
  };
}

const marketplaceFixture = {
  kind: "all",
  query: "",
  sources: [
    { id: "harness_curated", label: "平台推荐", status: "ready", item_count: 1, url: "" },
    { id: "official_mcp_registry", label: "官方 MCP 注册表", status: "ready", item_count: 1, url: "https://registry.modelcontextprotocol.io" },
    { id: "smithery_skills", label: "Smithery 技能库", status: "ready", item_count: 1, url: "https://smithery.ai" },
  ],
  errors: [],
  items: [
    {
      id: "harness::mcp_context_search",
      kind: "mcp",
      source: "harness_curated",
      source_label: "平台推荐",
      name: "mcp_context_search",
      display_name: "上下文搜索",
      description: "让智能体检索工作区上下文。",
      categories: ["MCP"],
      verified: true,
      stars: null,
      use_count: null,
      quality_score: 1,
      latest_version: "built-in",
      updated_at: null,
      homepage_url: "",
      repository_url: "",
      remote_url: "",
      package_type: "mcp_server",
      install_mode: "attach_existing",
      install_label: "直接启用",
      install_payload: {
        capability_id: "mcp_context_search",
        agent_id: "default",
        enabled: true,
        priority: 10,
      },
      badges: ["本地", "MCP", "可直接启用"],
      risk_notes: ["本地内置能力，启用后仍受策略约束。"],
      metadata: {},
    },
    {
      id: "official-mcp::io.github.example/search@1.0.0",
      kind: "mcp",
      source: "official_mcp_registry",
      source_label: "官方 MCP 注册表",
      name: "io.github.example/search",
      display_name: "Example Search",
      description: "Search external systems.",
      categories: ["MCP"],
      verified: true,
      stars: null,
      use_count: null,
      quality_score: null,
      latest_version: "1.0.0",
      updated_at: "2026-04-01T00:00:00Z",
      homepage_url: "",
      repository_url: "https://github.com/example/search-mcp",
      remote_url: "https://mcp.example.com",
      package_type: "mcp_server",
      install_mode: "marketplace_preflight",
      install_label: "登记预检",
      install_payload: {
        source_uri: "https://mcp.example.com",
        pinned_ref: "marketplace-sha256:abc",
        package_type: "mcp_server",
        display_name: "Example Search",
        description: "Search external systems.",
        marketplace_source: "official_mcp_registry",
        marketplace_item_id: "official-mcp::io.github.example/search@1.0.0",
        permissions: ["mcp:remote"],
        secret_refs: [],
        manifest: {
          name: "io-github-example-search",
          version: "1.0.0",
          description: "Search external systems.",
          package_type: "mcp_server",
          permissions: ["mcp:remote"],
          transport: "http",
        },
        content: { marketplace: { source: "official_mcp_registry" } },
      },
      badges: ["MCP", "latest", "active"],
      risk_notes: ["远程 MCP 服务器会引入外部网络边界。"],
      metadata: {},
    },
    {
      id: "smithery-skill::acme/review",
      kind: "skill",
      source: "smithery_skills",
      source_label: "Smithery 技能库",
      name: "acme/review",
      display_name: "Review Skill",
      description: "Review code with policy.",
      categories: ["Coding"],
      verified: false,
      stars: 42,
      use_count: 7,
      quality_score: 0.9,
      latest_version: null,
      updated_at: "2026-02-02T00:00:00Z",
      homepage_url: "https://smithery.ai/skills/acme/review",
      repository_url: "https://github.com/acme/review/tree/main/skill",
      remote_url: "",
      package_type: "skill_pack",
      install_mode: "marketplace_preflight",
      install_label: "登记预检",
      install_payload: {
        source_uri: "https://github.com/acme/review/tree/main/skill",
        pinned_ref: "marketplace-sha256:def",
        package_type: "skill_pack",
        display_name: "Review Skill",
        description: "Review code with policy.",
        marketplace_source: "smithery_skills",
        marketplace_item_id: "smithery-skill::acme/review",
        permissions: ["skill:prompt"],
        secret_refs: [],
        manifest: {
          name: "acme-review",
          version: "1.0.0",
          description: "Review code with policy.",
          package_type: "skill_pack",
          permissions: ["skill:prompt"],
        },
        content: { marketplace: { source: "smithery_skills" } },
      },
      badges: ["Skill", "Coding"],
      risk_notes: ["Skill 会改变智能体指令边界。"],
      metadata: {},
    },
  ],
};

test.describe("Tools page mocked smoke tests", () => {
  test.beforeEach(async ({ page }) => {
    await routeToolsApis(page);
  });

  test("Tool Registry list renders with tool names and risk levels", async ({ page }) => {
    await page.goto("/tools");

    await expect(page.getByText("read_file").first()).toBeVisible();
    await expect(page.getByText("shell_exec")).toBeVisible();
    await expect(page.getByText("web_search")).toBeVisible();
    await expect(page.getByText("db_query")).toBeVisible();

    await expect(page.getByText("低风险").first()).toBeVisible();
    await expect(page.getByText("高风险").first()).toBeVisible();
    await expect(page.getByText("中风险").first()).toBeVisible();
    await expect(page.getByText("关键风险").first()).toBeVisible();
  });

  test("MCP tools section renders", async ({ page }) => {
    await page.goto("/tools");

    await expect(page.getByText("MCP").first()).toBeVisible();
    await expect(page.getByText("2 已注册")).toBeVisible();
    await expect(page.getByRole("button", { name: "MCP Servers" })).toBeVisible();
    await expect(page.getByText("web-tools.search")).toBeVisible();
    await expect(page.getByText("db-adapter.query")).toBeVisible();
  });

  test("Policy section renders", async ({ page }) => {
    await page.goto("/tools");

    await expect(page.getByText("策略").first()).toBeVisible();
    await expect(page.getByText("2 高风险")).toBeVisible();
    await expect(page.getByText("沙箱").first()).toBeVisible();
    await expect(page.getByText("本地无容器路径")).toBeVisible();
  });

  test("Default install paths render and invoke backend APIs", async ({ page }) => {
    await page.goto("/tools");

    await expect(page.getByLabel("可信 URL 安装")).toBeHidden();
    await page.getByRole("button", { name: "可信 URL" }).click();
    const trustedDialog = page.getByRole("dialog", { name: "可信 URL 一键安装" });
    await expect(trustedDialog).toBeVisible();
    await trustedDialog.getByRole("button", { name: /下载、安装并启用|Download, install, and enable/ }).click();
    await expect(page.getByText("可信来源安装成功")).toBeVisible();
    await expect(page.getByText("attachment-trusted").first()).toBeVisible();
    await trustedDialog.getByRole("button", { name: "关闭" }).click();

    await page.getByRole("button", { name: "公网预检" }).click();
    const publicDialog = page.getByRole("dialog", { name: "公网 URL 预检" });
    await expect(publicDialog).toBeVisible();
    await publicDialog.getByRole("button", { name: /下载并预检|Download and preflight/ }).click();
    await expect(page.getByText("公网包已完成预检")).toBeVisible();
    await expect(page.getByText("pkg-public").first()).toBeVisible();
    await expect(page.getByText(/完成验证后再点击“启用”/)).toBeVisible();
    await publicDialog.getByRole("button", { name: /启用|Enable/ }).click();
    await expect(page.getByText("公网包已启用")).toBeVisible();
    await expect(page.getByText("ver-public")).toBeVisible();
    await publicDialog.getByRole("button", { name: "关闭" }).click();

    await page.getByRole("button", { name: "上传技能" }).click();
    const uploadDialog = page.getByRole("dialog", { name: "上传文件安装" });
    await expect(uploadDialog).toBeVisible();
    await uploadDialog.getByRole("button", { name: /上传并安装|Upload and install/ }).click();
    await expect(page.getByText("本地技能安装成功")).toBeVisible();
    await expect(page.getByText("attachment-upload").first()).toBeVisible();
  });

  test("Marketplace MCP flow shows Chinese status, success feedback, and concrete test cases", async ({ page }) => {
    await page.goto("/tools");

    await page.getByRole("button", { name: "打开安装向导" }).click();
    let marketplaceDialog = page.getByRole("dialog", { name: "MCP / 技能商店" });
    await expect(marketplaceDialog).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(marketplaceDialog).toBeHidden();

    await page.getByRole("button", { name: "打开安装向导" }).click();
    marketplaceDialog = page.getByRole("dialog", { name: "MCP / 技能商店" });
    await expect(marketplaceDialog).toBeVisible();
    await expect(marketplaceDialog.getByLabel("搜索 MCP 和技能商店")).toBeVisible();
    await expect(marketplaceDialog.getByText("目标智能体 · 默认智能体（default）")).toBeVisible();
    await expect(marketplaceDialog.getByRole("button", { name: "上下文搜索" })).toBeVisible();
    await expect(marketplaceDialog.getByRole("button", { name: "Example Search" })).toBeVisible();

    const workbench = marketplaceDialog.getByRole("complementary", { name: "商店安装工作台" });
    await expect(workbench.getByText("未安装").first()).toBeVisible();

    await marketplaceDialog.getByRole("button", { name: "上下文搜索" }).click();
    await workbench.getByRole("button", { name: "直接启用" }).click();
    await expect(page.getByText("内置能力已启用")).toBeVisible();
    await expect(workbench.getByText("已安装").first()).toBeVisible();
    await expect(workbench.getByText("已启用到目标智能体。")).toBeVisible();

    await marketplaceDialog.getByRole("button", { name: "Example Search" }).click();
    await workbench.getByRole("button", { name: "登记预检" }).click();
    await expect(page.getByText("商店条目已登记预检")).toBeVisible();
    await expect(workbench.getByText("登记包已就绪，下一步请审批版本。")).toBeVisible();
    await expect(workbench.getByText("待审批").first()).toBeVisible();

    await workbench.getByRole("button", { name: "审批版本" }).click();
    await expect(page.getByText("商店版本审批通过")).toBeVisible();
    await expect(workbench.getByText("待安装").first()).toBeVisible();

    await workbench.getByRole("button", { name: "安装到智能体" }).click();
    await expect(page.getByText("商店能力已安装到智能体")).toBeVisible();
    await expect(workbench.getByText("已安装").first()).toBeVisible();
    await expect(workbench.getByText("已安装到目标智能体。")).toBeVisible();
    await expect(page.getByText("io-github-example-search", { exact: true })).toBeVisible();
    await expect(page.getByText("io.github.example/search.search")).toBeVisible();

    await workbench.getByRole("button", { name: "案例：OpenAI 最新动态" }).click();
    await workbench.getByRole("button", { name: "一键测试" }).click();
    await expect(page.getByText("商店案例测试通过")).toBeVisible();
    await expect(workbench.getByText("Example Search result")).toBeVisible();
  });

  test("Marketplace Skill flow shows install guidance and success feedback", async ({ page }) => {
    await page.goto("/tools");

    await page.getByRole("button", { name: "打开安装向导" }).click();
    const marketplaceDialog = page.getByRole("dialog", { name: "MCP / 技能商店" });
    await expect(marketplaceDialog).toBeVisible();
    await marketplaceDialog.getByRole("button", { name: "Review Skill" }).click();

    const workbench = marketplaceDialog.getByRole("complementary", { name: "商店安装工作台" });
    await expect(workbench.getByText("未安装").first()).toBeVisible();
    await expect(workbench.getByText("建议验证案例")).toBeVisible();

    await workbench.getByRole("button", { name: "登记预检" }).click();
    await expect(page.getByText("商店条目已登记预检")).toBeVisible();
    await expect(workbench.getByText("待审批").first()).toBeVisible();

    await workbench.getByRole("button", { name: "审批版本" }).click();
    await expect(page.getByText("商店版本审批通过")).toBeVisible();
    await expect(workbench.getByText("待安装").first()).toBeVisible();

    await workbench.getByRole("button", { name: "安装到智能体" }).click();
    await expect(page.getByText("商店能力已安装到智能体")).toBeVisible();
    await expect(workbench.getByText("已安装").first()).toBeVisible();
    await expect(workbench.getByText("完成安装后，确认顶部状态变为“已安装”。")).toBeVisible();
  });

  test("Runtime configuration page saves Brave config and runs a visible case", async ({ page }) => {
    await page.goto("/tools");

    await page.getByRole("button", { name: "运行配置" }).click();
    await expect(page).toHaveURL(/\/tools\/config$/);
    await expect(page.getByText("MCP / 技能运行配置")).toBeVisible();
    await expect(page.getByRole("button", { name: /brave/ })).toBeVisible();
    await expect(page.getByLabel("MCP 运行端点")).toHaveValue(
      "https://api.search.brave.com/res/v1/web/search",
    );

    await page.getByLabel("MCP API Key").fill("brave-test-token");
    await page.getByRole("button", { name: "保存运行配置" }).click();
    await expect(page.getByText("运行配置已保存")).toBeVisible();
    await expect(page.getByText("密钥已保存").first()).toBeVisible();
    await expect(page.getByText("已配置").first()).toBeVisible();

    await page.getByRole("button", { name: "运行案例测试" }).click();
    await expect(page.getByText("案例测试成功")).toBeVisible();
    await expect(page.getByText("真实 Brave API")).toBeVisible();
    await expect(page.getByText("MCP 教程 - Brave result")).toBeVisible();
  });
});

async function routeToolsApis(page: Page): Promise<void> {
  const agentAttachments: Array<Record<string, unknown>> = [];
  const marketplacePackages = new Map<string, Record<string, unknown>>();
  let braveRuntimeConfigured = false;

  await page.route(API_RE, async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    if (path === "/api/tools/registry") {
      const hasExampleSearch = agentAttachments.some(
        (attachment) => attachment.capability_key === "io-github-example-search",
      );
      const items = hasExampleSearch
        ? [...toolRegistryFixture.items, exampleSearchToolFixture]
        : toolRegistryFixture.items;
      await fulfillJson(route, {
        ...toolRegistryFixture,
        items,
        categories: Array.from(new Set(items.map((item) => item.category))),
        sources: Array.from(new Set(items.map((item) => item.source))),
      });
      return;
    }

    if (path === "/api/agents") {
      await fulfillJson(route, {
        items: [{ id: "default", name: "默认智能体", capability_attachments: agentAttachments }],
        next_cursor: null,
      });
      return;
    }

    if (path === "/api/tools/capabilities/packages") {
      await fulfillJson(route, { items: Array.from(marketplacePackages.values()).reverse() });
      return;
    }

    if (path === "/api/tools/capabilities/marketplace") {
      await fulfillJson(route, {
        ...marketplaceFixture,
        kind: url.searchParams.get("kind") ?? "all",
        query: url.searchParams.get("query") ?? "",
      });
      return;
    }

    if (path === "/api/tools/capabilities/dependency-preflight") {
      await fulfillJson(route, {
        required_v1: {},
        optional_v2: {},
        feature_flags: ["trusted_url_install"],
        trusted_hosts: ["example.com"],
        mcp_remote_allowed_hosts: [],
        local_release_path: "no-container",
        docker_private_smoke: "optional",
      });
      return;
    }

    if (path === "/api/tools/capabilities/runtime-configs") {
      await fulfillJson(route, { items: [braveRuntimeConfigFixture(braveRuntimeConfigured)] });
      return;
    }

    if (path === "/api/tools/capabilities/runtime-config" && method === "PATCH") {
      braveRuntimeConfigured = true;
      await fulfillJson(route, braveRuntimeConfigFixture(true));
      return;
    }

    if (path === "/api/agents/default/capabilities/attachments" && method === "POST") {
      const payload = route.request().postDataJSON() as Record<string, unknown>;
      agentAttachments.push({
        attachment_id: "attachment-builtin-1",
        agent_id: "default",
        capability_id: String(payload.capability_id ?? ""),
        capability_key: String(payload.capability_id ?? ""),
        capability_version_id: payload.capability_version_id ? String(payload.capability_version_id) : null,
        enabled: Boolean(payload.enabled ?? true),
        priority: Number(payload.priority ?? 10),
      });
      await fulfillJson(route, { status: "attached" });
      return;
    }

    if (path === "/api/tools/capabilities/preflight/marketplace" && method === "POST") {
      const payload = route.request().postDataJSON() as Record<string, unknown>;
      const itemId = String(payload.marketplace_item_id ?? "");
      const isSkill = itemId === "smithery-skill::acme/review";
      const packageId = isSkill ? "pkg-market-skill" : "pkg-market-mcp";
      const capabilityKey = isSkill ? "acme-review" : "io-github-example-search";
      const pkg = {
        id: packageId,
        organization_id: "dev-org",
        package_key: capabilityKey,
        package_type: isSkill ? "skill_pack" : "mcp_server",
        source_kind: "marketplace_preflight",
        source_uri: String(payload.source_uri ?? ""),
        source_sha256: isSkill ? "sha256-skill" : "sha256-mcp",
        pinned_ref: String(payload.pinned_ref ?? ""),
        status: "staged",
        risk_level: isSkill ? "low" : "medium",
        manifest_json: payload.manifest ?? {},
        validation_json: {
          marketplace_preflight: true,
          source_resolution: "registry_metadata_only_no_url_fetch",
        },
        provenance_json: { marketplace_registry_metadata_only: true },
        audit_json: { marketplace_preflight: { no_source_download: true } },
        capability_id: null,
        capability_version_id: null,
        created_at: "2026-05-18T00:00:00Z",
        updated_at: "2026-05-18T00:00:00Z",
        approved_at: null,
      };
      marketplacePackages.set(packageId, pkg);
      await fulfillJson(route, {
        package: pkg,
        validation_summary: { status: "staged" },
        ready_state: "staged",
        next_step_label: "Approve marketplace version",
        staged_capability_id: packageId,
        capability_id: null,
        capability_version_id: null,
        attachment: null,
      });
      return;
    }

    const approveMatch = path.match(/^\/api\/tools\/capabilities\/packages\/([^/]+)\/approve$/);
    if (approveMatch && method === "POST") {
      const packageId = approveMatch[1];
      const current = marketplacePackages.get(packageId);
      if (!current) {
        await fulfillJson(route, { detail: "missing package" }, 404);
        return;
      }
      const isSkill = packageId === "pkg-market-skill";
      const approved = {
        ...current,
        status: "approved",
        capability_id: isSkill ? "cap-market-skill" : "cap-market-mcp",
        capability_version_id: isSkill ? "ver-market-skill" : "ver-market-mcp",
        approved_at: "2026-05-18T00:01:00Z",
        updated_at: "2026-05-18T00:01:00Z",
      };
      marketplacePackages.set(packageId, approved);
      await fulfillJson(route, approved);
      return;
    }

    const attachPackageMatch = path.match(/^\/api\/tools\/capabilities\/packages\/([^/]+)\/attachments$/);
    if (attachPackageMatch && method === "POST") {
      const packageId = attachPackageMatch[1];
      const current = marketplacePackages.get(packageId);
      if (!current) {
        await fulfillJson(route, { detail: "missing package" }, 404);
        return;
      }
      const payload = route.request().postDataJSON() as Record<string, unknown>;
      const attachment = {
        attachment_id: packageId === "pkg-market-skill" ? "attachment-market-skill" : "attachment-market-mcp",
        agent_id: String(payload.agent_id ?? "default"),
        capability_id: String(current.capability_id ?? ""),
        capability_key: String(current.package_key ?? ""),
        capability_version_id: String(current.capability_version_id ?? ""),
        enabled: Boolean(payload.enabled ?? true),
        priority: Number(payload.priority ?? 10),
      };
      agentAttachments.push(attachment);
      await fulfillJson(route, attachment, 201);
      return;
    }

    if (path === "/api/tools/capabilities/install/trusted-url" && method === "POST") {
      await fulfillJson(route, {
        package: {
          ...toolRegistryFixture.items[0],
          id: "pkg-trusted",
          organization_id: "dev-org",
          package_key: "trusted-skill",
          package_type: "skill_pack",
          source_kind: "trusted_url",
          source_uri: "https://example.com/customer-research.skill",
          source_sha256: "sha256-trusted",
          pinned_ref: "sha256:trusted",
          status: "approved",
          risk_level: "low",
          manifest_json: { name: "trusted-skill", package_type: "skill_pack" },
          validation_json: { status: "valid" },
          provenance_json: {},
          audit_json: {},
          capability_id: "cap-trusted",
          capability_version_id: "ver-trusted",
          created_at: "2026-05-18T00:00:00Z",
          updated_at: "2026-05-18T00:00:00Z",
          approved_at: "2026-05-18T00:00:00Z",
        },
        validation_summary: {},
        ready_state: "attached",
        next_step_label: "Open Agent attachment",
        staged_capability_id: null,
        capability_id: "cap-trusted",
        capability_version_id: "ver-trusted",
        attachment: {
          attachment_id: "attachment-trusted",
          agent_id: "default",
          capability_id: "cap-trusted",
          capability_version_id: "ver-trusted",
          enabled: true,
          priority: 10,
        },
      });
      return;
    }

    if (path === "/api/tools/capabilities/preflight/public-url" && method === "POST") {
      await fulfillJson(route, {
        package: {
          ...toolRegistryFixture.items[0],
          id: "pkg-public",
          organization_id: "dev-org",
          package_key: "public-skill",
          package_type: "skill_pack",
          source_kind: "public_url",
          source_uri: "https://example.com/public.skill",
          source_sha256: "sha256-public",
          pinned_ref: "sha256:public",
          status: "staged",
          risk_level: "medium",
          manifest_json: { name: "public-skill", package_type: "skill_pack" },
          validation_json: { status: "valid" },
          provenance_json: {},
          audit_json: {},
          capability_id: null,
          capability_version_id: null,
          created_at: "2026-05-18T00:00:00Z",
          updated_at: "2026-05-18T00:00:00Z",
          approved_at: null,
        },
        validation_summary: {},
        ready_state: "staged",
        next_step_label: "Enable after validation",
        staged_capability_id: "pkg-public",
        capability_id: null,
        capability_version_id: null,
        attachment: null,
      });
      return;
    }

    if (path === "/api/tools/capabilities/staged/pkg-public/enable" && method === "POST") {
      await fulfillJson(route, {
        package: {
          ...toolRegistryFixture.items[0],
          id: "pkg-public",
          organization_id: "dev-org",
          package_key: "public-skill",
          package_type: "skill_pack",
          source_kind: "public_url",
          source_uri: "https://example.com/public.skill",
          source_sha256: "sha256-public",
          pinned_ref: "sha256:public",
          status: "approved",
          risk_level: "medium",
          manifest_json: { name: "public-skill", package_type: "skill_pack" },
          validation_json: { status: "valid" },
          provenance_json: {},
          audit_json: {},
          capability_id: "cap-public",
          capability_version_id: "ver-public",
          created_at: "2026-05-18T00:00:00Z",
          updated_at: "2026-05-18T00:00:00Z",
          approved_at: "2026-05-18T00:00:00Z",
        },
        validation_summary: {},
        ready_state: "ready",
        next_step_label: "Attach to Agent",
        staged_capability_id: null,
        capability_id: "cap-public",
        capability_version_id: "ver-public",
        attachment: null,
      });
      return;
    }

    if (path === "/api/tools/capabilities/install/upload" && method === "POST") {
      await fulfillJson(route, {
        package: {
          ...toolRegistryFixture.items[0],
          id: "pkg-upload",
          organization_id: "dev-org",
          package_key: "upload-skill",
          package_type: "skill_pack",
          source_kind: "private_upload",
          source_uri: null,
          source_sha256: "sha256-upload",
          pinned_ref: null,
          status: "approved",
          risk_level: "low",
          manifest_json: { name: "upload-skill", package_type: "skill_pack" },
          validation_json: { status: "valid" },
          provenance_json: {},
          audit_json: {},
          capability_id: "cap-upload",
          capability_version_id: "ver-upload",
          created_at: "2026-05-18T00:00:00Z",
          updated_at: "2026-05-18T00:00:00Z",
          approved_at: "2026-05-18T00:00:00Z",
        },
        validation_summary: {},
        ready_state: "attached",
        next_step_label: "Open Agent attachment",
        staged_capability_id: null,
        capability_id: "cap-upload",
        capability_version_id: "ver-upload",
        attachment: {
          attachment_id: "attachment-upload",
          agent_id: "default",
          capability_id: "cap-upload",
          capability_version_id: "ver-upload",
          enabled: true,
          priority: 10,
        },
      });
      return;
    }

    if (path === "/api/tools/capabilities/test-invoke" && method === "POST") {
      const payload = route.request().postDataJSON() as Record<string, unknown>;
      const toolName = String(payload.tool_name ?? "");
      if (toolName === "brave") {
        await fulfillJson(route, {
          allowed: true,
          output: {
            mcp_server: "brave",
            mcp_method: "search",
            result: {
              source: "brave-search-api",
              items: [
                {
                  id: "https://example.com/mcp",
                  title: "MCP 教程 - Brave result",
                  url: "https://example.com/mcp",
                  snippet: "Model Context Protocol tutorial result",
                },
              ],
            },
          },
          tool_call: {
            id: "tool-call-brave",
            tool_name: "brave",
            status: "SUCCESS",
            risk_level: "low",
            requires_sandbox: false,
            duration_ms: 18,
            output_kind: "json",
            output_summary: "ok",
            created_at: "2026-05-27T00:00:00Z",
          },
        }, 202);
        return;
      }
      await fulfillJson(route, {
        allowed: true,
        output: {
          mcp_server: toolName.includes("search") ? "io.github.example/search" : toolName,
          mcp_method: "search",
          result: {
            items: [
              {
                id: "search-result-1",
                title: "Example Search result",
                snippet: "OpenAI latest news",
              },
            ],
            source: "mcp-marketplace-adapter",
          },
        },
        tool_call: {
          id: "tool-call-market-1",
          tool_name: toolName || "io-github-example-search",
          status: "SUCCESS",
          risk_level: "low",
          requires_sandbox: false,
          duration_ms: 12,
          output_kind: "json",
          output_summary: "ok",
          created_at: "2026-05-18T00:00:00Z",
        },
      });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `Unhandled e2e route: ${path}` }),
    });
  });
}

async function fulfillJson(route: Route, payload: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}
