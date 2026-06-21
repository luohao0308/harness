import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToolRegistryPage } from "../pages/ToolRegistryPage";

const apiBaseUrl = "http://127.0.0.1:8000";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ToolRegistryPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function registryPayload(extraItems: Array<Record<string, unknown>> = []) {
  return {
    items: [
      {
        name: "mcp_context_search",
        description: "Search context",
        category: "knowledge",
        source: "mcp",
        risk_level: "low",
        requires_sandbox: false,
        network_policy: "disabled",
        timeout_seconds: 10,
        allowed_roles: ["engineer"],
        audit_level: "standard",
        idempotent: true,
        input_schema: { type: "object" },
        mcp_server: "local-context",
        mcp_method: "context.search",
      },
      ...extraItems,
    ],
    categories: ["knowledge"],
    sources: ["mcp"],
  };
}

function marketplacePayload() {
  return {
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
}

function emptyMarketplacePayload() {
  return { kind: "all", query: "", sources: [], errors: [], items: [] };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ToolRegistryPage marketplace controls", () => {
  it("renders API-backed webhook triggers and creates a one-time secret", async () => {
    const user = userEvent.setup();
    let triggers: Array<Record<string, unknown>> = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path.startsWith("/api/tools/registry") && !init?.method) return jsonResponse(registryPayload());
      if (path === "/api/agents" && !init?.method) {
        return jsonResponse({ items: [{ id: "default", name: "默认智能体", capability_attachments: [] }], next_cursor: null });
      }
      if (path === "/api/agents/default/triggers" && !init?.method) {
        return jsonResponse({ items: triggers });
      }
      if (path === "/api/agents/default/triggers" && init?.method === "POST") {
        triggers = [
          {
            id: "trigger-1",
            agent_id: "default",
            type: "webhook",
            endpoint_path: "release-check",
            enabled: true,
            created_at: "2026-06-21T00:00:00Z",
            updated_at: "2026-06-21T00:00:00Z",
            last_triggered_at: null,
          },
        ];
        return jsonResponse({ trigger: triggers[0], secret: "htrg_test_secret" }, 201);
      }
      if (path.startsWith("/api/tools/capabilities/marketplace") && !init?.method) {
        return jsonResponse(emptyMarketplacePayload());
      }
      if (path === "/api/tools/capabilities/dependency-preflight" && !init?.method) {
        return jsonResponse({ local_release_path: "no-container" });
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    expect((await screen.findAllByText("触发器")).length).toBeGreaterThan(0);
    expect(await screen.findByText("暂无 webhook 触发器")).toBeInTheDocument();
    await user.type(screen.getByLabelText("触发器路径"), "release-check");
    await user.click(screen.getByRole("button", { name: /创建触发器/ }));

    expect(await screen.findByText("htrg_test_secret")).toBeInTheDocument();
    expect((await screen.findAllByText(/\/api\/webhook\/trigger\/release-check/)).length).toBeGreaterThan(0);
    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          String(input).endsWith("/api/agents/default/triggers") && init?.method === "POST",
      );
      expect(createCall).toBeDefined();
      expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
        type: "webhook",
        endpoint_path: "release-check",
        enabled: true,
      });
    });
  });

  it("opens a MCP / Skill marketplace panel and routes installs through Harness gates", async () => {
    let packagePayload: Record<string, unknown> | null = null;
    let marketplaceToolInstalled = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path.startsWith("/api/tools/registry") && !init?.method) {
        return jsonResponse(
          registryPayload(
            marketplaceToolInstalled
              ? [
                  {
                    name: "io-github-example-search",
                    description: "Search external systems.",
                    category: "mcp",
                    source: "mcp",
                    risk_level: "low",
                    requires_sandbox: false,
                    network_policy: "restricted",
                    timeout_seconds: 30,
                    allowed_roles: ["engineer"],
                    audit_level: "standard",
                    idempotent: true,
                    input_schema: { type: "object" },
                    mcp_server: "io.github.example/search",
                    mcp_method: "search",
                  },
                ]
              : [],
          ),
        );
      }
      if (path === "/api/agents" && !init?.method) {
        return jsonResponse({ items: [{ id: "default", name: "默认智能体", capability_attachments: [] }], next_cursor: null });
      }
      if (path === "/api/agents/default/triggers" && !init?.method) {
        return jsonResponse({ items: [] });
      }
      if (path.startsWith("/api/tools/capabilities/marketplace") && !init?.method) {
        return jsonResponse(marketplacePayload());
      }
      if (path === "/api/tools/capabilities/packages" && !init?.method) {
        return jsonResponse({ items: packagePayload ? [packagePayload] : [] });
      }
      if (path === "/api/tools/capabilities/dependency-preflight" && !init?.method) {
        return jsonResponse({ local_release_path: "no-container" });
      }
      if (path === "/api/agents/default/capabilities/attachments" && init?.method === "POST") {
        return jsonResponse({ status: "attached" });
      }
      if (path === "/api/tools/capabilities/preflight/marketplace" && init?.method === "POST") {
        packagePayload = {
          id: "pkg-market-1",
          organization_id: "dev-org",
          package_key: "example-search",
          package_type: "mcp_server",
          source_kind: "marketplace_preflight",
          source_uri: "https://mcp.example.com",
          source_sha256: "abcdef1234567890",
          pinned_ref: "marketplace-sha256:abc",
          status: "staged",
          risk_level: "medium",
          manifest_json: {},
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
        return jsonResponse({
          package: packagePayload,
          validation_summary: { status: "staged" },
          ready_state: "staged",
          next_step_label: "Approve marketplace version",
          staged_capability_id: "pkg-market-1",
          capability_id: null,
          capability_version_id: null,
          attachment: null,
        }, 201);
      }
      if (path === "/api/tools/capabilities/packages/pkg-market-1/approve" && init?.method === "POST") {
        packagePayload = {
          ...(packagePayload ?? {}),
          id: "pkg-market-1",
          status: "approved",
          capability_id: "cap-market-1",
          capability_version_id: "cap-version-1",
        };
        return jsonResponse(packagePayload);
      }
      if (path === "/api/tools/capabilities/packages/pkg-market-1/attachments" && init?.method === "POST") {
        marketplaceToolInstalled = true;
        return jsonResponse({
          attachment_id: "attach-market-1",
          agent_id: "default",
          capability_id: "cap-market-1",
          capability_version_id: "cap-version-1",
          enabled: true,
          priority: 10,
        }, 201);
      }
      if (path === "/api/tools/capabilities/test-invoke" && init?.method === "POST") {
        return jsonResponse({
          allowed: true,
          output: {
            mcp_server: "io.github.example/search",
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
            tool_name: "io-github-example-search",
            status: "SUCCESS",
            risk_level: "low",
            requires_sandbox: false,
            duration_ms: 12,
            output_kind: "json",
            output_summary: "ok",
            created_at: "2026-05-18T00:00:00Z",
          },
        });
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    const user = userEvent.setup();

    renderPage(fetchMock);

    expect(await screen.findByText("MCP / 技能商店")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /打开安装向导/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /上下文搜索/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Example Search/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Review Skill/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("搜索 MCP 和技能商店")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("市场侧栏安装目标智能体")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /安装到智能体|Install to Agent/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /打开安装向导/ }));
    const marketplaceDialog = await screen.findByRole("dialog", { name: "MCP / 技能商店" });
    expect(within(marketplaceDialog).getByLabelText("搜索 MCP 和技能商店")).toBeInTheDocument();
    expect(within(marketplaceDialog).getByRole("button", { name: /上下文搜索/ })).toBeInTheDocument();
    expect(within(marketplaceDialog).getByRole("button", { name: /Example Search/ })).toBeInTheDocument();
    expect(within(marketplaceDialog).getByRole("button", { name: /Review Skill/ })).toBeInTheDocument();
    await user.click(within(marketplaceDialog).getByRole("button", { name: /上下文搜索/ }));
    expect(within(marketplaceDialog).getByLabelText(/^市场侧栏安装目标智能体/)).toBeInTheDocument();
    const marketplaceWorkbench = within(marketplaceDialog).getByRole("complementary", { name: "商店安装工作台" });
    await user.click(within(marketplaceWorkbench).getByRole("button", { name: /^直接启用$/ }));
    await waitFor(() => {
      const attachCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          String(input).endsWith("/api/agents/default/capabilities/attachments") &&
          init?.method === "POST",
      );
      expect(attachCall).toBeDefined();
      expect(JSON.parse(String(attachCall?.[1]?.body))).toMatchObject({
        capability_id: "mcp_context_search",
        enabled: true,
      });
    });
    expect(await within(marketplaceDialog).findByText(/已启用到目标智能体/)).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).endsWith("/api/tools/capabilities/packages"),
      ),
    ).toBe(true);
    await user.click(within(marketplaceDialog).getByRole("button", { name: /Example Search/ }));
    await user.click(within(marketplaceWorkbench).getByRole("button", { name: /^登记预检$/ }));
    await waitFor(() => {
      const preflightCall = fetchMock.mock.calls.find(([input]) =>
        String(input).endsWith("/api/tools/capabilities/preflight/marketplace"),
      );
      expect(preflightCall).toBeDefined();
      expect(JSON.parse(String(preflightCall?.[1]?.body))).toMatchObject({
        source_uri: "https://mcp.example.com",
        package_type: "mcp_server",
        agent_id: "default",
        marketplace_source: "official_mcp_registry",
        marketplace_item_id: "official-mcp::io.github.example/search@1.0.0",
        manifest: { name: "io-github-example-search", transport: "http" },
      });
    });
    expect(await within(marketplaceDialog).findByText(/登记包已就绪/)).toBeInTheDocument();
    expect(within(marketplaceDialog).getByText(/商店登记/)).toBeInTheDocument();
    await user.click(within(marketplaceDialog).getByRole("button", { name: /审批版本/ }));
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            String(input).endsWith("/api/tools/capabilities/packages/pkg-market-1/approve") &&
            init?.method === "POST",
        ),
      ).toBe(true);
    });
    await user.click(within(marketplaceWorkbench).getByRole("button", { name: /^安装到智能体$/ }));
    await waitFor(() => {
      const attachPackageCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          String(input).endsWith("/api/tools/capabilities/packages/pkg-market-1/attachments") &&
          init?.method === "POST",
      );
      expect(attachPackageCall).toBeDefined();
      expect(JSON.parse(String(attachPackageCall?.[1]?.body))).toMatchObject({
        agent_id: "default",
        enabled: true,
      });
    });
    expect(await screen.findByText("io-github-example-search")).toBeInTheDocument();
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([input]) =>
          String(input).includes("/api/tools/registry?agent_id=default"),
        ),
      ).toBe(true);
    });
    const quickTestInput = within(marketplaceDialog).getByLabelText("市场快速测试查询");
    await user.clear(quickTestInput);
    await user.type(quickTestInput, "OpenAI latest news");
    await user.click(within(marketplaceDialog).getByRole("button", { name: /一键测试|Run test/ }));
    expect(await within(marketplaceDialog).findByText(/Example Search result/)).toBeInTheDocument();
    await waitFor(() => {
      const testCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          String(input).endsWith("/api/tools/capabilities/test-invoke") &&
          init?.method === "POST",
      );
      expect(testCall).toBeDefined();
      expect(JSON.parse(String(testCall?.[1]?.body))).toMatchObject({
        agent_id: "default",
        tool_name: "io-github-example-search",
        input_json: { query: "OpenAI latest news", limit: 3 },
      });
    });
    await user.click(within(marketplaceDialog).getByRole("button", { name: "关闭" }));
    expect(screen.getByRole("button", { name: /可信 URL/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /生命周期/ })).toBeInTheDocument();
    expect(screen.queryByLabelText("可信 URL 安装")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /生命周期/ }));
    const lifecycleDialog = await screen.findByRole("dialog", { name: "高级生命周期" });
    expect(within(lifecycleDialog).getByRole("button", { name: /安装到智能体|Install to Agent/ })).toBeInTheDocument();
    expect(within(lifecycleDialog).getByLabelText("能力包清单")).toBeInTheDocument();
  });

  it("uses backend package lifecycle APIs before Agent-scoped test invoke", async () => {
    const user = userEvent.setup();
    let packagePayload: Record<string, unknown> | null = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path.startsWith("/api/tools/registry") && !init?.method) return jsonResponse(registryPayload());
      if (path === "/api/agents" && !init?.method) {
        return jsonResponse({ items: [{ id: "default", name: "默认智能体", capability_attachments: [] }], next_cursor: null });
      }
      if (path === "/api/agents/default/triggers" && !init?.method) {
        return jsonResponse({ items: [] });
      }
      if (path.startsWith("/api/tools/capabilities/marketplace") && !init?.method) {
        return jsonResponse(emptyMarketplacePayload());
      }
      if (path === "/api/tools/capabilities/packages" && !init?.method) {
        return jsonResponse({ items: packagePayload ? [packagePayload] : [] });
      }
      if (path === "/api/tools/capabilities/admin-validate" && init?.method === "POST") {
        return jsonResponse({
          status: "valid",
          schema_version: 1,
          content_sha256: "abcdef1234567890",
          config_sha256: "fedcba0987654321",
          redacted_payload: {},
          validation_mode: "manifest_only_no_execution",
          activation_allowed: false,
          issues: [],
          risk_preview: { requires_approval: true },
        });
      }
      if (path === "/api/tools/capabilities/packages/public" && init?.method === "POST") {
        packagePayload = {
          id: "pkg-1",
          organization_id: "dev-org",
          package_key: "conservative-token-saver",
          package_type: "context_optimizer",
          source_kind: "public_git",
          source_uri: "git+https://github.com/acme/skill-pack.git",
          source_sha256: "abcdef1234567890",
          pinned_ref: "commit:demo-pinned-commit",
          status: "staged",
          risk_level: "low",
          manifest_json: {},
          validation_json: {},
          provenance_json: {},
          audit_json: {},
          capability_id: null,
          capability_version_id: null,
          created_at: "2026-05-18T00:00:00Z",
          updated_at: "2026-05-18T00:00:00Z",
          approved_at: null,
        };
        return jsonResponse(packagePayload, 201);
      }
      if (path === "/api/tools/capabilities/packages/pkg-1/approve" && init?.method === "POST") {
        packagePayload = {
          ...packagePayload,
          status: "approved",
          capability_id: "cap-1",
          capability_version_id: "version-1",
          approved_at: "2026-05-18T00:01:00Z",
        };
        return jsonResponse(packagePayload);
      }
      if (path === "/api/tools/capabilities/packages/pkg-1/attachments" && init?.method === "POST") {
        return jsonResponse({
          attachment_id: "attachment-1",
          agent_id: "default",
          capability_id: "cap-1",
          capability_version_id: "version-1",
          enabled: true,
          priority: 10,
        }, 201);
      }
      if (path === "/api/tools/capabilities/packages/pkg-1/rollback" && init?.method === "POST") {
        return jsonResponse({
          ...packagePayload,
          status: "approved",
          capability_id: "cap-1",
          capability_version_id: "version-1",
        });
      }
      if (path === "/api/tools/capabilities/attachments/attachment-1" && init?.method === "PATCH") {
        return jsonResponse({
          attachment_id: "attachment-1",
          agent_id: "default",
          capability_id: "cap-1",
          capability_version_id: "version-1",
          enabled: false,
          priority: 10,
        });
      }
      if (path === "/api/tools/capabilities/packages/pkg-1/uninstall" && init?.method === "POST") {
        packagePayload = { ...packagePayload, status: "uninstalled" };
        return jsonResponse(packagePayload);
      }
      if (path === "/api/tools/capabilities/test-invoke" && init?.method === "POST") {
        return jsonResponse({
          allowed: true,
          output: { result: { items: ["hit"] } },
          tool_call: {
            id: "tool-call-1",
            tool_name: "mcp_context_search",
            status: "SUCCESS",
            risk_level: "low",
            requires_sandbox: false,
            duration_ms: 1,
            output_kind: "json",
            output_summary: "ok",
            created_at: "2026-05-18T00:00:00Z",
          },
        });
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    expect(await screen.findByText("mcp_context_search")).toBeInTheDocument();
    expect(screen.getByText("搜索工作区上下文。")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /生命周期/ }));
    const lifecycleDialog = await screen.findByRole("dialog", { name: "高级生命周期" });
    await user.click(within(lifecycleDialog).getByRole("button", { name: /仅校验|Validate only/ }));
    expect(await within(lifecycleDialog).findByText(/仅校验清单，不执行/)).toBeInTheDocument();
    await user.click(within(lifecycleDialog).getByRole("button", { name: /暂存包|Stage package/ }));
    expect(await within(lifecycleDialog).findByText(/pkg-1/)).toBeInTheDocument();
    await user.click(within(lifecycleDialog).getByRole("button", { name: /审批版本|Approve version/ }));
    expect(await within(lifecycleDialog).findByText(/version-1/)).toBeInTheDocument();
    await user.click(within(lifecycleDialog).getByRole("button", { name: /安装到智能体|Install to Agent/ }));
    expect(await within(lifecycleDialog).findByText(/attachment-1/)).toBeInTheDocument();
    await user.click(within(lifecycleDialog).getByRole("button", { name: /回滚|Rollback/ }));
    await user.click(within(lifecycleDialog).getByRole("button", { name: /停用附件|Disable attachment/ }));
    await user.click(within(lifecycleDialog).getByRole("button", { name: /卸载|Uninstall/ }));
    expect((await within(lifecycleDialog).findAllByText(/已卸载/)).length).toBeGreaterThan(0);
    await user.click(within(lifecycleDialog).getByRole("button", { name: "关闭" }));
    await user.click(screen.getByRole("button", { name: /测试调用|Test invoke/ }));
    const testDialog = await screen.findByRole("dialog", { name: "智能体范围测试调用" });
    await user.click(within(testDialog).getByRole("button", { name: /测试调用|Test invoke/ }));
    expect(await within(testDialog).findByText(/hit/)).toBeInTheDocument();

    await waitFor(() => {
      const paths = fetchMock.mock.calls.map(([input]) => String(input));
      expect(paths).toContain("/api/tools/capabilities/admin-validate");
      expect(paths).toContain("/api/tools/capabilities/packages/public");
      expect(paths).toContain("/api/tools/capabilities/packages/pkg-1/approve");
      expect(paths).toContain("/api/tools/capabilities/packages/pkg-1/attachments");
      expect(paths).toContain("/api/tools/capabilities/packages/pkg-1/rollback");
      expect(paths).toContain("/api/tools/capabilities/attachments/attachment-1");
      expect(paths).toContain("/api/tools/capabilities/packages/pkg-1/uninstall");
      expect(paths).toContain("/api/tools/capabilities/test-invoke");
    });
    const validationCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/admin-validate"));
    expect(JSON.parse(String(validationCall?.[1]?.body))).toMatchObject({
      config: { source_type: "public_git", commit: "commit:demo-pinned-commit" },
    });
    const stageCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/packages/public"));
    expect(JSON.parse(String(stageCall?.[1]?.body))).toMatchObject({
      source_kind: "public_git",
      source_uri: "git+https://github.com/acme/skill-pack.git",
      pinned_ref: "commit:demo-pinned-commit",
      manifest: { name: "conservative-token-saver", package_type: "context_optimizer" },
    });
    const attachCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/pkg-1/attachments"));
    expect(JSON.parse(String(attachCall?.[1]?.body))).toMatchObject({
      agent_id: "default",
      enabled: true,
      priority: 10,
    });
    const rollbackCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/pkg-1/rollback"));
    expect(JSON.parse(String(rollbackCall?.[1]?.body))).toMatchObject({
      capability_version_id: "version-1",
    });
  });

  it("shows installed state from existing Agent attachments and localizes external marketplace copy", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path.startsWith("/api/tools/registry") && !init?.method) return jsonResponse(registryPayload());
      if (path === "/api/agents" && !init?.method) {
        return jsonResponse({
          items: [
            {
              id: "default",
              name: "默认智能体",
              capability_attachments: [
                {
                  attachment_id: "attachment-context",
                  capability_id: "cap-context",
                  capability_key: "tool:mcp_context_search",
                  capability_version_id: "mcp_context_search:a54e7fa10e179e14:3fab371f",
                  capability_type: "mcp_tool",
                  enabled: true,
                  priority: 10,
                  status: "active",
                },
                {
                  attachment_id: "attachment-brave",
                  capability_id: "cap-brave",
                  capability_key: "package-brave",
                  capability_version_id: "brave-9693b089e19e2135-3e429fc2",
                  capability_type: "mcp_tool",
                  enabled: true,
                  priority: 10,
                  status: "active",
                },
              ],
            },
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/default/triggers" && !init?.method) {
        return jsonResponse({ items: [] });
      }
      if (path.startsWith("/api/tools/capabilities/marketplace") && !init?.method) {
        return jsonResponse({
          ...marketplacePayload(),
          items: [
            marketplacePayload().items[0],
            {
              ...marketplacePayload().items[1],
              id: "smithery-mcp::brave",
              source: "smithery_mcp",
              source_label: "Smithery MCP 服务库",
              name: "brave",
              display_name: "Brave Search",
              description: "Search the web with Brave's independent index.",
              install_payload: {
                ...marketplacePayload().items[1].install_payload,
                manifest: { name: "brave", package_type: "mcp_server" },
              },
              badges: ["MCP", "verified", "remote"],
            },
          ],
        });
      }
      if (path === "/api/tools/capabilities/packages" && !init?.method) {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/tools/capabilities/dependency-preflight" && !init?.method) {
        return jsonResponse({ local_release_path: "no-container" });
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    const user = userEvent.setup();

    renderPage(fetchMock);

    await user.click(await screen.findByRole("button", { name: /打开安装向导/ }));
    const marketplaceDialog = await screen.findByRole("dialog", { name: "MCP / 技能商店" });

    const contextCard = within(marketplaceDialog).getByRole("button", { name: /上下文搜索/ });
    expect(within(contextCard).getAllByText("已安装").length).toBeGreaterThan(0);

    await user.click(within(marketplaceDialog).getByRole("button", { name: /Brave Search/ }));
    expect(within(marketplaceDialog).getAllByText("已安装").length).toBeGreaterThan(0);
    expect(
      within(marketplaceDialog).getAllByText(/使用 Brave 独立索引进行网页、新闻、图片和视频搜索/).length,
    ).toBeGreaterThan(0);
    expect(within(marketplaceDialog).getAllByText("已验证").length).toBeGreaterThan(0);
    expect(within(marketplaceDialog).getAllByText("远程").length).toBeGreaterThan(0);
  });

  it("surfaces LangGraph workflow import and LangChain adapter paths without making workflows test-invoke tools", async () => {
    const user = userEvent.setup();
    let packagePayload: Record<string, unknown> | null = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path.startsWith("/api/tools/registry") && !init?.method) return jsonResponse(registryPayload());
      if (path === "/api/agents" && !init?.method) {
        return jsonResponse({ items: [{ id: "default", name: "默认智能体", capability_attachments: [] }], next_cursor: null });
      }
      if (path === "/api/agents/default/triggers" && !init?.method) {
        return jsonResponse({ items: [] });
      }
      if (path.startsWith("/api/tools/capabilities/marketplace") && !init?.method) {
        return jsonResponse(emptyMarketplacePayload());
      }
      if (path === "/api/tools/capabilities/packages" && !init?.method) {
        return jsonResponse({ items: packagePayload ? [packagePayload] : [] });
      }
      if (path === "/api/tools/capabilities/dependency-preflight" && !init?.method) {
        return jsonResponse({ local_release_path: "no-container" });
      }
      if (path === "/api/tools/capabilities/admin-validate" && init?.method === "POST") {
        return jsonResponse({
          status: "valid",
          schema_version: 1,
          content_sha256: "langgraphcontenthash",
          config_sha256: "langgraphconfighash",
          redacted_payload: {},
          validation_mode: "manifest_only_no_execution",
          errors: [],
          warnings: [],
        });
      }
      if (path === "/api/tools/capabilities/packages/private" && init?.method === "POST") {
        packagePayload = {
          id: "pkg-langgraph-1",
          organization_id: "dev-org",
          package_key: "demo-langgraph-workflow",
          package_type: "langgraph_workflow",
          source_kind: "private_upload",
          source_uri: null,
          source_sha256: "sha256-langgraph",
          pinned_ref: null,
          status: "staged",
          risk_level: "medium",
          manifest_json: { package_type: "langgraph_workflow" },
          validation_json: {},
          provenance_json: {},
          audit_json: {},
          capability_id: null,
          capability_version_id: null,
          created_at: "2026-06-02T00:00:00Z",
          updated_at: "2026-06-02T00:00:00Z",
          approved_at: null,
        };
        return jsonResponse(packagePayload, 201);
      }
      if (path === "/api/tools/capabilities/packages/pkg-langgraph-1/approve" && init?.method === "POST") {
        packagePayload = {
          ...(packagePayload ?? {}),
          id: "pkg-langgraph-1",
          status: "approved",
          capability_id: "cap-langgraph-1",
          capability_version_id: "version-langgraph-1",
          approved_at: "2026-06-02T00:01:00Z",
        };
        return jsonResponse(packagePayload);
      }
      if (path === "/api/tools/capabilities/packages/pkg-langgraph-1/attachments" && init?.method === "POST") {
        return jsonResponse({
          attachment_id: "attach-langgraph-1",
          agent_id: "default",
          capability_id: "cap-langgraph-1",
          capability_version_id: "version-langgraph-1",
          enabled: true,
          priority: 20,
        }, 201);
      }
      if (path === "/api/tools/capabilities/test-invoke" && init?.method === "POST") {
        return jsonResponse({
          allowed: true,
          output: { result: { status: "success" }, metadata: { source: "mcp" } },
          tool_call: {
            id: "tool-call-langchain-1",
            tool_name: "langchain.invoke_tool",
            status: "SUCCESS",
            risk_level: "low",
            requires_sandbox: false,
            duration_ms: 3,
            output_kind: "json",
            output_summary: "ok",
            created_at: "2026-06-02T00:00:00Z",
          },
        });
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    await user.click(await screen.findByRole("button", { name: /LangGraph Workflow/ }));
    const langGraphDialog = await screen.findByRole("dialog", { name: "LangGraph Workflow" });
    expect(within(langGraphDialog).getByText(/非 ToolRunner 能力/)).toBeInTheDocument();

    await user.click(within(langGraphDialog).getByRole("button", { name: /仅校验|Validate only/ }));
    await waitFor(() => {
      const validationCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/admin-validate"));
      expect(validationCall).toBeDefined();
      expect(JSON.parse(String(validationCall?.[1]?.body))).toMatchObject({
        content: {
          package_manifest: { package_type: "langgraph_workflow" },
          langgraph_json: { graphs: { main: "./agent.py:graph" } },
        },
        config: { package_type: "langgraph_workflow" },
      });
    });
    await user.click(within(langGraphDialog).getByRole("button", { name: /暂存 Workflow/ }));
    expect(await within(langGraphDialog).findByText(/pkg-langgraph-1/)).toBeInTheDocument();
    const stageCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/packages/private"));
    expect(JSON.parse(String(stageCall?.[1]?.body))).toMatchObject({
      manifest: { package_type: "langgraph_workflow" },
      content: { langgraph_json: { graphs: { main: "./agent.py:graph" } } },
    });
    await user.click(within(langGraphDialog).getByRole("button", { name: /审批版本|Approve version/ }));
    expect(await within(langGraphDialog).findByText(/version-langgraph-1/)).toBeInTheDocument();
    await user.click(within(langGraphDialog).getByRole("button", { name: /挂载到智能体|Attach to Agent/ }));
    await waitFor(() => {
      const attachCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/pkg-langgraph-1/attachments"));
      expect(JSON.parse(String(attachCall?.[1]?.body))).toMatchObject({
        agent_id: "default",
        enabled: true,
        priority: 20,
      });
    });
    expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith("/test-invoke")).length).toBe(0);

    await user.click(within(langGraphDialog).getByRole("button", { name: "关闭" }));
    await user.click(screen.getByRole("button", { name: /LangChain Adapter/ }));
    const langChainDialog = await screen.findByRole("dialog", { name: "LangChain Adapter" });
    expect(within(langChainDialog).getByText(/ToolMetadata\(source="mcp"\)/)).toBeInTheDocument();
    await user.click(within(langChainDialog).getByRole("button", { name: /通过 ToolRunner 测试/ }));
    expect(await within(langChainDialog).findByText(/"source": "mcp"/)).toBeInTheDocument();
    await waitFor(() => {
      const testCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/test-invoke"));
      expect(testCall).toBeDefined();
      expect(JSON.parse(String(testCall?.[1]?.body))).toMatchObject({
        agent_id: "default",
        tool_name: "langchain.invoke_tool",
        input_json: {
          tool_name: "example_tool",
          arguments: { query: "release readiness" },
        },
      });
    });
  });
});
