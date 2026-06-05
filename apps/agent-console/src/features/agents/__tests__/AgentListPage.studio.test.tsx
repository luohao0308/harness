import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentListPage } from "../pages/AgentListPage";

const apiBaseUrl = "http://127.0.0.1:8000";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function agent() {
  return {
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
  };
}

function tokenOptimizerPresets() {
  return {
    items: [
      {
        preset_id: "off",
        display_name: "关闭",
        description: "不启用额外 Token Optimizer，只使用默认上下文策略。",
        enabled: false,
        priority: null,
      },
      {
        preset_id: "conservative",
        display_name: "保守省 Token",
        description: "轻量裁剪低相关证据，优先保持最近对话和记忆。",
        enabled: true,
        priority: 5,
      },
      {
        preset_id: "balanced",
        display_name: "均衡",
        description: "推荐默认方案，在上下文质量和成本之间取得平衡。",
        enabled: true,
        priority: 5,
      },
      {
        preset_id: "aggressive",
        display_name: "强力省 Token",
        description: "更积极限制候选上下文，适合长对话和成本敏感任务。",
        enabled: true,
        priority: 5,
      },
    ],
  };
}

function localAgentConnection(overrides: Record<string, unknown> = {}) {
  return {
    id: "local-1",
    agent_id: "default",
    owner_user_id: "dev-engineer",
    display_name: "Fake Local Agent",
    adapter_kind: "fake",
    protocol_version: "local-agent-v1",
    bridge_version: "agent-console-test",
    status: "online",
    workspace_root: ".../agent-console/test",
    capabilities_json: {
      supports_resume: true,
      supports_streaming: true,
      supports_cancel: false,
    },
    risk_capabilities_json: [],
    last_seen_at: "2026-06-03T00:00:00Z",
    revoked_at: null,
    created_at: "2026-06-03T00:00:00Z",
    updated_at: "2026-06-03T00:00:00Z",
    ...overrides,
  };
}

function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <AgentListPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AgentListPage Studio controls", () => {
  it("renders create/clone/readiness controls and calls Agent capability APIs", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/agents" && !init?.method) return jsonResponse({ items: [agent()], next_cursor: null });
      if (path === "/api/agents/token-optimizer/presets" && !init?.method) return jsonResponse(tokenOptimizerPresets());
      if (path === "/api/agents/default/knowledge/sources" && !init?.method) return jsonResponse({ items: [], next_cursor: null });
      if (path === "/api/agents/local-agent/connections" && !init?.method) return jsonResponse({ items: [], next_cursor: null });
      if (path === "/api/agents" && init?.method === "POST") return jsonResponse({ ...agent(), id: "research-agent", name: "研究智能体" });
      if (path === "/api/agents/default/clone" && init?.method === "POST") return jsonResponse({ ...agent(), id: "default-clone", name: "默认智能体克隆副本" });
      if (path === "/api/agents/default/capabilities/attachments" && init?.method === "POST") return jsonResponse({ status: "attached" });
      if (path === "/api/agents/default/token-optimizer" && init?.method === "POST") {
        return jsonResponse({
          status: "selected",
          preset_id: "aggressive",
          attachment_id: "attachment-aggressive",
          capability_id: "cap-aggressive",
          capability_version_id: "version-aggressive",
          enabled: true,
          priority: 5,
        });
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    expect((await screen.findAllByText("默认智能体")).length).toBeGreaterThan(0);
    expect(screen.getByText("能力附件与就绪检查")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /均衡/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /关闭/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /保守省 Token/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /强力省 Token/ })).toBeInTheDocument();
    expect(screen.queryByLabelText("能力名称")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /创建智能体|Create Agent/ }));
    expect(await screen.findByText("智能体创建成功")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /克隆当前智能体|Clone selected Agent/ }));
    expect(await screen.findByText("智能体克隆成功")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /配置能力附件|Configure attachment/ }));
    const capabilityDialog = await screen.findByRole("dialog", { name: "配置能力附件" });
    expect(within(capabilityDialog).getByLabelText("能力名称")).toBeInTheDocument();
    await user.click(within(capabilityDialog).getByRole("button", { name: /附加到当前智能体|Attach to selected Agent/ }));
    expect(await screen.findByText("能力附件已保存")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /强力省 Token/ }));
    expect(await screen.findByText("Token 方案已切换")).toBeInTheDocument();

    await waitFor(() => {
      const paths = fetchMock.mock.calls.map(([input]) => String(input));
      expect(paths).toContain("/api/agents");
      expect(paths).toContain("/api/agents/default/clone");
      expect(paths).toContain("/api/agents/default/capabilities/attachments");
      expect(paths).toContain("/api/agents/default/token-optimizer");
    });
    const createCall = fetchMock.mock.calls.find(
      ([input, init]) => String(input) === "/api/agents" && init?.method === "POST",
    );
    expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
      id: "research-agent",
      token_budget: 4096,
      tools_json: ["mcp_context_search"],
    });
    const attachCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/capabilities/attachments"));
    expect(JSON.parse(String(attachCall?.[1]?.body))).toMatchObject({
      capability_id: "mcp_context_search",
      enabled: true,
    });
    const optimizerCall = fetchMock.mock.calls.find(
      ([input, init]) => String(input) === "/api/agents/default/token-optimizer" && init?.method === "POST",
    );
    expect(JSON.parse(String(optimizerCall?.[1]?.body))).toEqual({
      preset_id: "aggressive",
    });
  });

  it("does not mark the knowledge connector ready without indexed sources", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/agents" && !init?.method) return jsonResponse({ items: [agent()], next_cursor: null });
      if (path === "/api/agents/token-optimizer/presets" && !init?.method) return jsonResponse(tokenOptimizerPresets());
      if (path === "/api/agents/default/knowledge/sources" && !init?.method) return jsonResponse({ items: [], next_cursor: null });
      if (path === "/api/agents/local-agent/connections" && !init?.method) return jsonResponse({ items: [], next_cursor: null });
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    expect((await screen.findAllByText("默认智能体")).length).toBeGreaterThan(0);
    expect(await screen.findByText(/没有已索引知识源|No indexed knowledge source/)).toBeInTheDocument();
    expect(screen.getByText(/待配置|Needs setup/)).toBeInTheDocument();
  });

  it("generates a local Agent pairing command, discovers local bridges, and revokes one", async () => {
    const user = userEvent.setup();
    const pairingBodies: Array<Record<string, unknown>> = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/agents" && !init?.method) return jsonResponse({ items: [agent()], next_cursor: null });
      if (path === "/api/agents/token-optimizer/presets" && !init?.method) return jsonResponse(tokenOptimizerPresets());
      if (path === "/api/agents/default/knowledge/sources" && !init?.method) return jsonResponse({ items: [], next_cursor: null });
      if (path === "/api/agents/local-agent/connections" && !init?.method) {
        return jsonResponse({
          items: [
            localAgentConnection(),
            localAgentConnection({
              id: "local-claude-v6",
              display_name: "Claude Code",
              adapter_kind: "claude_code",
              capabilities_json: {
                supports_resume: false,
                supports_streaming: true,
                supports_cancel: true,
                host_tools_authorized: true,
                permission_bridge: "harness_local_tool_request_v1",
                execution_mode: "agent_sdk_intent_capture_harness_executor",
                permission_bridge_execution: "harness_owned_executor",
                sdk_native_tool_execution_enabled: false,
              },
              risk_capabilities_json: ["shell_approval_required", "pending_change"],
            }),
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/local-agent/pairing-tokens" && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        pairingBodies.push(body);
        const scope = body.scope as { adapters?: string[]; permission_bridge?: string[] } | undefined;
        const adapterKind = scope?.adapters?.[0] ?? "hao";
        return jsonResponse({
          id: "pair-1",
          agent_id: "default",
          pair_code: "ABC123",
          pair_token: "plain-pair-token",
          command: [
            "hao bridge pair --api http://127.0.0.1:8000 --pair-token plain-pair-token --pair-code ABC123",
            adapterKind !== "hao" ? `--adapter ${adapterKind}` : "",
            scope?.permission_bridge?.[0] === "sdk" ? "--permission-bridge sdk" : "",
          ].filter(Boolean).join(" "),
          status: "active",
          expires_at: "2026-06-03T00:10:00Z",
          created_at: "2026-06-03T00:00:00Z",
        }, 201);
      }
      if (path === "/api/agents/local-agent/connections/local-1/revoke" && init?.method === "POST") {
        return jsonResponse(localAgentConnection({ status: "revoked", revoked_at: "2026-06-03T00:01:00Z" }));
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    expect(await screen.findByText("接入本地 Agent")).toBeInTheDocument();
    expect(screen.queryByText("新建云端 Agent")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /打开接入向导|Open connection wizard/ }));
    const dialog = await screen.findByRole("dialog", { name: "接入本地 Agent" });
    expect(within(dialog).getByText("Codex CLI")).toBeInTheDocument();
    expect(within(dialog).getAllByText("Claude Code").length).toBeGreaterThan(0);
    await user.click(within(dialog).getByRole("button", { name: /生成连接命令|Generate command/ }));
    expect((await within(dialog).findAllByText(/ABC123/)).length).toBeGreaterThan(0);
    expect(pairingBodies[0]).toMatchObject({
      agent_id: "default",
      scope: { executable: true, adapters: ["hao"] },
    });
    expect(within(dialog).queryByText(/--adapter codex/)).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: /本地 Agent 类型|Local Agent adapter/ }));
    await user.click(await screen.findByRole("option", { name: /Codex CLI/ }));
    await user.click(within(dialog).getByRole("button", { name: /生成连接命令|Generate command/ }));
    await waitFor(() => expect(pairingBodies).toHaveLength(2));
    expect(pairingBodies[1]).toMatchObject({
      agent_id: "default",
      scope: { executable: true, adapters: ["codex"] },
    });
    expect(await within(dialog).findByText(/--adapter codex/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: /本地 Agent 类型|Local Agent adapter/ }));
    await user.click(await screen.findByRole("option", { name: /Claude Code V6/ }));
    await user.click(within(dialog).getByRole("button", { name: /生成连接命令|Generate command/ }));
    await waitFor(() => expect(pairingBodies).toHaveLength(3));
    expect(pairingBodies[2]).toMatchObject({
      agent_id: "default",
      scope: { executable: true, adapters: ["claude_code"], permission_bridge: ["sdk"] },
    });
    expect(await within(dialog).findByText(/--adapter claude_code/)).toBeInTheDocument();
    expect(await within(dialog).findByText(/--permission-bridge sdk/)).toBeInTheDocument();
    expect(within(dialog).getAllByText(/V6 权限桥|V6 permission bridge/).length).toBeGreaterThan(0);
    expect(within(dialog).getAllByText(/本地工具需审批|Host tools need approval/).length).toBeGreaterThan(0);
    expect(within(dialog).getByText("Fake Local Agent")).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: /接入 fake bridge|Connect fake bridge/ })).not.toBeInTheDocument();
    await user.click(within(dialog).getAllByRole("button", { name: /撤销|Revoke/ })[0]);
    expect(await screen.findByText("本地 Agent 已撤销")).toBeInTheDocument();

    await waitFor(() => {
      const paths = fetchMock.mock.calls.map(([input]) => String(input));
      expect(paths).toContain("/api/agents/local-agent/pairing-tokens");
      expect(paths).toContain("/api/agents/local-agent/connections/local-1/revoke");
      expect(paths).not.toContain("/api/agents/local-agent/connections/register");
    });
  });
});
