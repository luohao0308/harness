/**
 * L2 Mocked Browser Test: Tools Page
 *
 * Proves the Tool Registry page renders tool names with risk levels,
 * MCP tools section, and Policy section.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const API_RE = /http:\/\/(?:127\.0\.0\.1|localhost):(?:8000|5177|15174)\/api\/.*/;

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
    await expect(page.getByText("no-container")).toBeVisible();
  });

  test("Default install paths render and invoke backend APIs", async ({ page }) => {
    await page.goto("/tools");

    await expect(page.getByText("可信 URL 一键安装")).toBeVisible();
    await expect(page.getByText("公网 URL 预检")).toBeVisible();
    await expect(page.getByText("上传文件安装")).toBeVisible();
    await page.getByRole("button", { name: /下载、安装并启用|Download, install, and enable/ }).click();
    await expect(page.getByText("attachment-trusted").first()).toBeVisible();
    await page.getByRole("button", { name: /下载并预检|Download and preflight/ }).click();
    await expect(page.getByText("pkg-public").first()).toBeVisible();
    await expect(page.getByText(/staged_capability_id/)).toBeVisible();
    await page.getByRole("button", { name: "Enable" }).click();
    await expect(page.getByText("ver-public")).toBeVisible();
    await page.getByRole("button", { name: /上传并安装|Upload and install/ }).click();
    await expect(page.getByText("attachment-upload").first()).toBeVisible();
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

    if (path === "/api/tools/capabilities/packages") {
      await fulfillJson(route, { items: [] });
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

    if (path === "/api/tools/capabilities/install/trusted-url" && route.request().method() === "POST") {
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

    if (path === "/api/tools/capabilities/preflight/public-url" && route.request().method() === "POST") {
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

    if (path === "/api/tools/capabilities/staged/pkg-public/enable" && route.request().method() === "POST") {
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

    if (path === "/api/tools/capabilities/install/upload" && route.request().method() === "POST") {
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
