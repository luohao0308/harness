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

function registryPayload() {
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
    ],
    categories: ["knowledge"],
    sources: ["mcp"],
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ToolRegistryPage marketplace controls", () => {
  it("keeps MCP and Skill configuration behind click-open dialogs by default", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/tools/registry" && !init?.method) return jsonResponse(registryPayload());
      if (path === "/api/tools/capabilities/packages" && !init?.method) {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/tools/capabilities/dependency-preflight" && !init?.method) {
        return jsonResponse({ local_release_path: "no-container" });
      }
      if (path === "/api/agents/default/capabilities/attachments" && init?.method === "POST") {
        return jsonResponse({ status: "attached" });
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    const user = userEvent.setup();

    renderPage(fetchMock);

    expect(await screen.findByText("常用预置能力")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /上下文搜索/ })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("预置能力目标 Agent")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /安装到 Agent|Install to Agent/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /上下文搜索/ }));
    const presetDialog = await screen.findByRole("dialog", { name: /配置上下文搜索/ });
    expect(within(presetDialog).getByLabelText("预置能力目标 Agent")).toBeInTheDocument();
    await user.click(within(presetDialog).getByRole("button", { name: /启用能力/ }));
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
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).endsWith("/api/tools/capabilities/packages"),
      ),
    ).toBe(false);
    expect(screen.getByRole("button", { name: /可信 URL/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /生命周期/ })).toBeInTheDocument();
    expect(screen.queryByLabelText("可信 URL 安装")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /生命周期/ }));
    const lifecycleDialog = await screen.findByRole("dialog", { name: "高级生命周期" });
    expect(within(lifecycleDialog).getByRole("button", { name: /安装到 Agent|Install to Agent/ })).toBeInTheDocument();
    expect(within(lifecycleDialog).getByLabelText("能力包清单")).toBeInTheDocument();
  });

  it("uses backend package lifecycle APIs before Agent-scoped test invoke", async () => {
    const user = userEvent.setup();
    let packagePayload: Record<string, unknown> | null = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/tools/registry" && !init?.method) return jsonResponse(registryPayload());
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
    await user.click(screen.getByRole("button", { name: /生命周期/ }));
    const lifecycleDialog = await screen.findByRole("dialog", { name: "高级生命周期" });
    await user.click(within(lifecycleDialog).getByRole("button", { name: /仅校验|Validate only/ }));
    expect(await within(lifecycleDialog).findByText(/manifest_only_no_execution/)).toBeInTheDocument();
    await user.click(within(lifecycleDialog).getByRole("button", { name: /暂存包|Stage package/ }));
    expect(await within(lifecycleDialog).findByText(/pkg-1/)).toBeInTheDocument();
    await user.click(within(lifecycleDialog).getByRole("button", { name: /审批版本|Approve version/ }));
    expect(await within(lifecycleDialog).findByText(/version-1/)).toBeInTheDocument();
    await user.click(within(lifecycleDialog).getByRole("button", { name: /安装到 Agent|Install to Agent/ }));
    expect(await within(lifecycleDialog).findByText(/attachment-1/)).toBeInTheDocument();
    await user.click(within(lifecycleDialog).getByRole("button", { name: /回滚|Rollback/ }));
    await user.click(within(lifecycleDialog).getByRole("button", { name: /停用附件|Disable attachment/ }));
    await user.click(within(lifecycleDialog).getByRole("button", { name: /卸载|Uninstall/ }));
    expect((await within(lifecycleDialog).findAllByText(/uninstalled/)).length).toBeGreaterThan(0);
    await user.click(within(lifecycleDialog).getByRole("button", { name: "关闭" }));
    await user.click(screen.getByRole("button", { name: /测试调用|Test invoke/ }));
    const testDialog = await screen.findByRole("dialog", { name: "Agent 作用域测试调用" });
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
});
