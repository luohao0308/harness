import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentListPage } from "../pages/AgentListPage";

const apiBaseUrl = "http://127.0.0.1:8000";
const localAgentPairCommand =
  "npx -y /Users/luohao/Desktop/agent_workspace/harness/services/api-server bridge pair --api http://127.0.0.1:8000 --pair-token plain-pair-token --pair-code ABC123 --daemon";
const fullLocalAgentRiskCapabilities = ["host_read", "host_write", "shell", "git", "network"];

function assistantLocalAgentCapabilities(overrides: Record<string, unknown> = {}) {
  return {
    supports_resume: false,
    supports_streaming: true,
    supports_cancel: true,
    host_tools_authorized: true,
    permission_defer_supported: true,
    tool_execution_authority: "harness_approved_local_bridge",
    resume_mode: "context_replay_new_session",
    ...overrides,
  };
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function revokedPairingResponse(overrides: Record<string, unknown> = {}) {
  return {
    id: "pair-1",
    agent_id: "default",
    pair_code: "ABC123",
    pair_token: null,
    command: null,
    status: "revoked",
    expires_at: "2026-06-03T00:10:00Z",
    created_at: "2026-06-03T00:00:00Z",
    ...overrides,
  };
}

function agent(overrides: Record<string, unknown> = {}) {
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
    ...overrides,
  };
}

function indexedKnowledgeSource(overrides: Record<string, unknown> = {}) {
  return {
    id: "source-1",
    agent_id: "default",
    organization_id: "org-dev",
    scope: "agent",
    name: "默认知识源",
    description: "Indexed docs",
    status: "ACTIVE",
    health_status: "HEALTHY",
    metadata_json: {},
    settings_json: {},
    latest_documents: [
      {
        id: "doc-1",
        source_id: "source-1",
        title: "Runbook",
        uri: "memory://runbook",
        content_sha256: "0123456789abcdef",
        mime_type: "text/markdown",
        version: 1,
        logical_document_id: "logical-doc-1",
        supersedes_document_id: null,
        superseded_at: null,
        ingestion_error: null,
        metadata_json: {},
        idempotency_key: null,
        created_by: "user-1",
        chunk_count: 2,
        status: "INDEXED",
        created_at: "2026-06-05T00:00:00Z",
        updated_at: "2026-06-05T00:00:00Z",
        indexed_at: "2026-06-05T00:01:00Z",
      },
    ],
    created_at: "2026-06-05T00:00:00Z",
    updated_at: "2026-06-05T00:00:00Z",
    ...overrides,
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
    pairing_token_id: null,
    onboarding_confirmed: true,
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
    expect(await screen.findByRole("img", { name: /默认智能体 · 就绪: 1\/3/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "打开 默认智能体" })).toHaveAttribute("href", "/agents/default/workspace");
    expect(within(screen.getByRole("group", { name: "默认智能体 配置卡" })).getByRole("button", { name: "当前配置" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("link", { name: /模型 模型配置 接口已接入/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /工具 MCP（模型上下文协议） 接口已接入/ })).toBeInTheDocument();
    expect(screen.getByText("RAG 知识检索")).toBeInTheDocument();
    expect(screen.getByText("编排")).toBeInTheDocument();
    expect(screen.getByText("Token 优化")).toBeInTheDocument();
    expect(screen.getByText("提示词")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /沙箱 隔离运行环境 接口已接入/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /策略 审批与审计 接口已接入/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /展开更多能力|收起更多能力/ })).not.toBeInTheDocument();
    expect(screen.queryByText("模板")).not.toBeInTheDocument();
    const knowledgeToggle = screen.getByRole("button", { name: /知识管理/ });
    expect(knowledgeToggle).toHaveAttribute("aria-expanded", "true");
    await user.click(knowledgeToggle);
    expect(knowledgeToggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("暂无知识源。")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /配置 Token 方案|Configure token plan/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /强力省 Token/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("能力名称")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /配置模板|Configure template/ }));
    const templateDialog = await screen.findByRole("dialog", { name: "选择职业模板" });
    await user.click(within(templateDialog).getByRole("button", { name: /使用此模板|Use template/ }));
    expect(await screen.findByText("智能体创建成功")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /配置模板|Configure template/ }));
    const cloneTemplateDialog = await screen.findByRole("dialog", { name: "选择职业模板" });
    await user.click(within(cloneTemplateDialog).getByRole("button", { name: /克隆当前智能体|Clone selected Agent/ }));
    expect(await screen.findByText("智能体克隆成功")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /配置能力附件|Configure attachment/ }));
    const capabilityDialog = await screen.findByRole("dialog", { name: "配置能力附件" });
    expect(within(capabilityDialog).getByLabelText("能力名称")).toBeInTheDocument();
    await user.click(within(capabilityDialog).getByRole("button", { name: /附加到当前智能体|Attach to selected Agent/ }));
    expect(await screen.findByText("能力附件已保存")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /配置 Token 方案|Configure token plan/ }));
    const tokenDialog = await screen.findByRole("dialog", { name: "Token 省用方案" });
    const tokenPlanGroup = within(tokenDialog).getByRole("group", { name: "Token 省用方案" });
    expect(within(tokenPlanGroup).getByRole("button", { name: /均衡/ })).toHaveAttribute("aria-pressed", "true");
    expect(within(tokenPlanGroup).getByRole("button", { name: /关闭/ })).toBeInTheDocument();
    expect(within(tokenPlanGroup).getByRole("button", { name: /保守省 Token/ })).toBeInTheDocument();
    await user.click(within(tokenPlanGroup).getByRole("button", { name: /强力省 Token/ }));
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
    expect(await screen.findByText(/知识 0 · 本地 0/)).toBeInTheDocument();
    expect(screen.getByText(/待配置|Needs setup/)).toBeInTheDocument();
  });

  it("counts indexed knowledge and local connections in the Agent readiness ring", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/agents" && !init?.method) return jsonResponse({ items: [agent()], next_cursor: null });
      if (path === "/api/agents/token-optimizer/presets" && !init?.method) return jsonResponse(tokenOptimizerPresets());
      if (path === "/api/agents/default/knowledge/sources" && !init?.method) return jsonResponse({ items: [indexedKnowledgeSource()], next_cursor: null });
      if (path === "/api/agents/local-agent/connections" && !init?.method) {
        return jsonResponse({
          items: [
            localAgentConnection({
              display_name: "hao Local Agent",
              adapter_kind: "hao",
            }),
          ],
          next_cursor: null,
        });
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    expect(await screen.findByRole("img", { name: /默认智能体 · 就绪: 3\/3/ })).toBeInTheDocument();
    expect(await screen.findByText(/1 个知识源/)).toBeInTheDocument();
  });

  it("does not count fake local bridges as user-facing readiness", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/agents" && !init?.method) return jsonResponse({ items: [agent()], next_cursor: null });
      if (path === "/api/agents/token-optimizer/presets" && !init?.method) return jsonResponse(tokenOptimizerPresets());
      if (path === "/api/agents/default/knowledge/sources" && !init?.method) return jsonResponse({ items: [indexedKnowledgeSource()], next_cursor: null });
      if (path === "/api/agents/local-agent/connections" && !init?.method) return jsonResponse({ items: [localAgentConnection()], next_cursor: null });
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    expect(await screen.findByRole("img", { name: /默认智能体 · 就绪: 2\/3/ })).toBeInTheDocument();
    expect(await screen.findByText(/知识 1 · 本地 0/)).toBeInTheDocument();
    expect(await screen.findByText(/0 个本地连接/)).toBeInTheDocument();
  });

  it("shows per-agent readiness and lets top cards switch the configuration target", async () => {
    const user = userEvent.setup();
    const researchAgent = agent({
      id: "research-agent",
      name: "研究智能体",
      description: "研究配置目标",
      tools_json: ["mcp_research"],
      routing_tags: ["research"],
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/agents" && !init?.method) return jsonResponse({ items: [agent(), researchAgent], next_cursor: null });
      if (path === "/api/agents/token-optimizer/presets" && !init?.method) return jsonResponse(tokenOptimizerPresets());
      if (path === "/api/agents/default/knowledge/sources" && !init?.method) return jsonResponse({ items: [], next_cursor: null });
      if (path === "/api/agents/research-agent/knowledge/sources" && !init?.method) {
        return jsonResponse({
          items: [indexedKnowledgeSource({ id: "source-research", agent_id: "research-agent" })],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/local-agent/connections" && !init?.method) {
        return jsonResponse({
          items: [
            localAgentConnection({
              id: "local-research",
              agent_id: "research-agent",
              display_name: "hao Local Agent",
              adapter_kind: "hao",
            }),
          ],
          next_cursor: null,
        });
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    expect(await screen.findByRole("img", { name: /默认智能体 · 就绪: 1\/3/ })).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: /研究智能体 · 就绪: 3\/3/ })).toBeInTheDocument();
    const defaultCard = screen.getByRole("group", { name: "默认智能体 配置卡" });
    const researchCard = screen.getByRole("group", { name: "研究智能体 配置卡" });
    expect(within(defaultCard).getByRole("button", { name: "当前配置" })).toHaveAttribute("aria-pressed", "true");
    expect(within(researchCard).getByRole("button", { name: "设为配置" })).toHaveAttribute("aria-pressed", "false");
    await user.click(within(researchCard).getByRole("button", { name: "设为配置" }));
    expect(within(researchCard).getByRole("button", { name: "当前配置" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/知识 1 · 本地 1/)).toBeInTheDocument();
    expect(screen.getByText("mcp_research")).toBeInTheDocument();
  });

  it("generates a local Agent pairing command, discovers local bridges, and revokes one", async () => {
    const user = userEvent.setup();
    const pairingBodies: Array<Record<string, unknown>> = [];
    const revokedConnectionIds = new Set<string>();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/agents" && !init?.method) return jsonResponse({ items: [agent()], next_cursor: null });
      if (path === "/api/agents/token-optimizer/presets" && !init?.method) return jsonResponse(tokenOptimizerPresets());
      if (path === "/api/agents/default/knowledge/sources" && !init?.method) return jsonResponse({ items: [], next_cursor: null });
      if (path === "/api/agents/local-agent/connections" && !init?.method) {
        return jsonResponse({
          items: [
            localAgentConnection({
              pairing_token_id: "pair-1",
              onboarding_confirmed: false,
              display_name: "Codex CLI",
              adapter_kind: "codex",
              status: revokedConnectionIds.has("local-1") ? "revoked" : "online",
              revoked_at: revokedConnectionIds.has("local-1") ? "2026-06-03T00:01:00Z" : null,
              capabilities_json: assistantLocalAgentCapabilities(),
              risk_capabilities_json: fullLocalAgentRiskCapabilities,
            }),
            localAgentConnection({
              id: "local-claude-v5",
              pairing_token_id: "pair-1",
              onboarding_confirmed: false,
              display_name: "Claude Code",
              adapter_kind: "claude_code",
              capabilities_json: assistantLocalAgentCapabilities({
                execution_mode: "headless_harness_tool_bridge",
              }),
              risk_capabilities_json: fullLocalAgentRiskCapabilities,
            }),
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/local-agent/pairing-tokens" && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        pairingBodies.push(body);
        return jsonResponse({
          id: "pair-1",
          agent_id: "default",
          pair_code: "ABC123",
          pair_token: "plain-pair-token",
          command: localAgentPairCommand,
          status: "active",
          expires_at: "2026-06-03T00:10:00Z",
          created_at: "2026-06-03T00:00:00Z",
        }, 201);
      }
      if (path === "/api/agents/local-agent/connections/local-1" && init?.method === "PATCH") {
        return jsonResponse(localAgentConnection({
          display_name: (JSON.parse(String(init.body)) as { display_name: string }).display_name,
        }));
      }
      if (path === "/api/agents/local-agent/connections/local-claude-v5" && init?.method === "PATCH") {
        return jsonResponse(localAgentConnection({
          id: "local-claude-v5",
          display_name: (JSON.parse(String(init.body)) as { display_name: string }).display_name,
          adapter_kind: "claude_code",
        }));
      }
      if (path === "/api/agents/local-agent/pairing-tokens/pair-1/revoke" && init?.method === "POST") {
        return jsonResponse(revokedPairingResponse());
      }
      if (path === "/api/agents/local-agent/connections/local-1/revoke" && init?.method === "POST") {
        revokedConnectionIds.add("local-1");
        return jsonResponse(localAgentConnection({ status: "revoked", revoked_at: "2026-06-03T00:01:00Z" }));
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    expect(await screen.findByText("接入本地 Agent")).toBeInTheDocument();
    expect(screen.queryByText("新建云端 Agent")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /打开接入向导|Open connection wizard/ }));
    const dialog = await screen.findByRole("dialog", { name: "接入本地 Agent" });
    expect(within(dialog).getByText(/自动识别 hao \/ Codex CLI \/ Claude Code/)).toBeInTheDocument();
    expect(within(dialog).getByText(/自动识别 hao、Codex CLI 和 Claude Code/)).toBeInTheDocument();
    expect(within(dialog).getAllByText("Codex CLI").length).toBeGreaterThan(0);
    expect(within(dialog).getAllByText("Claude Code").length).toBeGreaterThan(0);
    expect(within(dialog).queryByRole("button", { name: /本地 Agent 类型|Local Agent adapter/ })).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: /生成连接命令|Generate command/ }));
    expect((await within(dialog).findAllByText(/ABC123/)).length).toBeGreaterThan(0);
    expect(pairingBodies[0]).toMatchObject({
      agent_id: "default",
      scope: { executable: true, adapters: ["hao", "codex", "claude_code"] },
    });
    expect(within(dialog).queryByText(/--adapter codex/)).not.toBeInTheDocument();
    expect(within(dialog).queryByText(/--adapter claude_code/)).not.toBeInTheDocument();
    expect(within(dialog).queryByText(/--permission-bridge sdk/)).not.toBeInTheDocument();
    expect(within(dialog).queryByText(/V6 权限桥|V6 permission bridge/)).not.toBeInTheDocument();
    expect(within(dialog).queryByText(/本地工具需审批|Host tools need approval/)).not.toBeInTheDocument();
    expect(within(dialog).getAllByText("待确认").length).toBeGreaterThanOrEqual(2);
    expect(within(dialog).getAllByText("未接入").length).toBeGreaterThanOrEqual(2);
    expect(within(dialog).getAllByText(/勾选并保存后才会接入工作台/).length).toBeGreaterThanOrEqual(2);
    expect(within(dialog).getAllByText(/上下文重放/).length).toBeGreaterThan(0);
    expect(within(dialog).queryByText(/平台工具 \+ 只读 CLI/)).not.toBeInTheDocument();
    expect(within(dialog).queryByText(/平台工具 \+ 对话模式/)).not.toBeInTheDocument();
    expect(within(dialog).queryByText(/本地工具禁用|Host tools disabled/)).not.toBeInTheDocument();
    expect(within(dialog).queryByText("Fake Local Agent")).not.toBeInTheDocument();
    expect(within(dialog).getByText(/已发现 2 个待确认 Agent，已选择 0 个。/)).toBeInTheDocument();
    expect((within(dialog).getByRole("checkbox", { name: /选择 Codex CLI/ }) as HTMLInputElement).checked).toBe(false);
    const claudeCheckbox = within(dialog).getByRole("checkbox", { name: /选择 Claude Code/ }) as HTMLInputElement;
    expect(claudeCheckbox.checked).toBe(false);
    await user.click(claudeCheckbox);
    expect(await within(dialog).findByText(/已发现 2 个待确认 Agent，已选择 1 个。/)).toBeInTheDocument();
    const fakeInput = within(dialog).queryByLabelText(/本地 Agent 名称 Fake Local Agent/);
    expect(fakeInput).not.toBeInTheDocument();
    await user.click(within(dialog).getAllByRole("button", { name: /撤销|Revoke/ })[0]);
    expect(await screen.findByText("本地 Agent 已撤销")).toBeInTheDocument();
    expect(await within(dialog).findByText(/已发现 1 个待确认 Agent，已选择 1 个。/)).toBeInTheDocument();
    await user.clear(within(dialog).getByLabelText(/本地 Agent 名称 Claude Code/));
    await user.type(within(dialog).getByLabelText(/本地 Agent 名称 Claude Code/), "本机 Claude");
    await user.click(within(dialog).getByRole("button", { name: /接入 1 个 Agent|Connect 1 Agent/ }));
    expect((await screen.findAllByText("本地 Agent 已接入")).length).toBeGreaterThan(0);

    await waitFor(() => {
      const paths = fetchMock.mock.calls.map(([input]) => String(input));
      expect(paths).toContain("/api/agents/local-agent/pairing-tokens");
      expect(paths).toContain("/api/agents/local-agent/pairing-tokens/pair-1/revoke");
      expect(paths).not.toContain("/api/agents/local-agent/connections/local-1");
      expect(paths).toContain("/api/agents/local-agent/connections/local-claude-v5");
      expect(paths).toContain("/api/agents/local-agent/connections/local-1/revoke");
      expect(paths).not.toContain("/api/agents/local-agent/connections/register");
    });
  });

  it("disconnects unchecked detected local Agents when saving the connection wizard", async () => {
    const user = userEvent.setup();
    const revokedConnectionIds = new Set<string>();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/agents" && !init?.method) return jsonResponse({ items: [agent()], next_cursor: null });
      if (path === "/api/agents/token-optimizer/presets" && !init?.method) return jsonResponse(tokenOptimizerPresets());
      if (path === "/api/agents/default/knowledge/sources" && !init?.method) return jsonResponse({ items: [], next_cursor: null });
      if (path === "/api/agents/local-agent/connections" && !init?.method) {
        return jsonResponse({
          items: [
            localAgentConnection({
              pairing_token_id: "pair-1",
              onboarding_confirmed: false,
              display_name: "Codex CLI",
              adapter_kind: "codex",
              capabilities_json: assistantLocalAgentCapabilities(),
              risk_capabilities_json: fullLocalAgentRiskCapabilities,
            }),
            localAgentConnection({
              id: "local-claude-v5",
              pairing_token_id: "pair-1",
              onboarding_confirmed: false,
              display_name: "Claude Code",
              adapter_kind: "claude_code",
              status: revokedConnectionIds.has("local-claude-v5") ? "revoked" : "online",
              revoked_at: revokedConnectionIds.has("local-claude-v5") ? "2026-06-03T00:02:00Z" : null,
              capabilities_json: assistantLocalAgentCapabilities({
                execution_mode: "headless_harness_tool_bridge",
              }),
              risk_capabilities_json: fullLocalAgentRiskCapabilities,
            }),
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/local-agent/pairing-tokens" && init?.method === "POST") {
        return jsonResponse({
          id: "pair-1",
          agent_id: "default",
          pair_code: "ABC123",
          pair_token: "plain-pair-token",
          command: localAgentPairCommand,
          status: "active",
          expires_at: "2026-06-03T00:10:00Z",
          created_at: "2026-06-03T00:00:00Z",
        }, 201);
      }
      if (path === "/api/agents/local-agent/connections/local-1" && init?.method === "PATCH") {
        return jsonResponse(localAgentConnection({
          display_name: (JSON.parse(String(init.body)) as { display_name: string }).display_name,
          adapter_kind: "codex",
        }));
      }
      if (path === "/api/agents/local-agent/pairing-tokens/pair-1/revoke" && init?.method === "POST") {
        return jsonResponse(revokedPairingResponse());
      }
      if (path === "/api/agents/local-agent/connections/local-claude-v5/revoke" && init?.method === "POST") {
        revokedConnectionIds.add("local-claude-v5");
        return jsonResponse(localAgentConnection({
          id: "local-claude-v5",
          display_name: "Claude Code",
          adapter_kind: "claude_code",
          status: "revoked",
          revoked_at: "2026-06-03T00:02:00Z",
        }));
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    await user.click(await screen.findByRole("button", { name: /打开接入向导|Open connection wizard/ }));
    const dialog = await screen.findByRole("dialog", { name: "接入本地 Agent" });
    await user.click(within(dialog).getByRole("button", { name: /生成连接命令|Generate command/ }));
    await within(dialog).findByText(/已发现 2 个待确认 Agent，已选择 0 个。/);
    await user.click(within(dialog).getByRole("checkbox", { name: /选择 Codex CLI/ }));
    await within(dialog).findByText(/已发现 2 个待确认 Agent，已选择 1 个。/);
    await user.click(within(dialog).getByRole("button", { name: /接入 1 个 Agent|Connect 1 Agent/ }));

    expect((await screen.findAllByText("本地 Agent 已接入")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/未勾选的连接已断开/)).length).toBeGreaterThan(0);
    await waitFor(() => {
      const paths = fetchMock.mock.calls.map(([input]) => String(input));
      expect(paths).toContain("/api/agents/local-agent/pairing-tokens/pair-1/revoke");
      expect(paths).toContain("/api/agents/local-agent/connections/local-1");
      expect(paths).toContain("/api/agents/local-agent/connections/local-claude-v5/revoke");
      expect(paths).not.toContain("/api/agents/local-agent/connections/local-claude-v5");
    });
  });

  it("allows saving with no detected local Agents selected and disconnects them all", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/agents" && !init?.method) return jsonResponse({ items: [agent()], next_cursor: null });
      if (path === "/api/agents/token-optimizer/presets" && !init?.method) return jsonResponse(tokenOptimizerPresets());
      if (path === "/api/agents/default/knowledge/sources" && !init?.method) return jsonResponse({ items: [], next_cursor: null });
      if (path === "/api/agents/local-agent/connections" && !init?.method) {
        return jsonResponse({
          items: [
            localAgentConnection({
              pairing_token_id: "pair-1",
              onboarding_confirmed: false,
              display_name: "Codex CLI",
              adapter_kind: "codex",
              capabilities_json: assistantLocalAgentCapabilities(),
              risk_capabilities_json: fullLocalAgentRiskCapabilities,
            }),
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/local-agent/pairing-tokens" && init?.method === "POST") {
        return jsonResponse({
          id: "pair-1",
          agent_id: "default",
          pair_code: "ABC123",
          pair_token: "plain-pair-token",
          command: localAgentPairCommand,
          status: "active",
          expires_at: "2026-06-03T00:10:00Z",
          created_at: "2026-06-03T00:00:00Z",
        }, 201);
      }
      if (path === "/api/agents/local-agent/pairing-tokens/pair-1/revoke" && init?.method === "POST") {
        return jsonResponse(revokedPairingResponse());
      }
      if (path === "/api/agents/local-agent/connections/local-1/revoke" && init?.method === "POST") {
        return jsonResponse(localAgentConnection({
          display_name: "Codex CLI",
          adapter_kind: "codex",
          status: "revoked",
          revoked_at: "2026-06-03T00:02:00Z",
        }));
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    await user.click(await screen.findByRole("button", { name: /打开接入向导|Open connection wizard/ }));
    const dialog = await screen.findByRole("dialog", { name: "接入本地 Agent" });
    await user.click(within(dialog).getByRole("button", { name: /生成连接命令|Generate command/ }));
    await within(dialog).findByText(/已发现 1 个待确认 Agent，已选择 0 个。/);
    await user.click(within(dialog).getByRole("button", { name: /不接入，断开全部|Disconnect all/ }));

    expect(await screen.findByText("未接入本地 Agent")).toBeInTheDocument();
    expect((await screen.findAllByText(/已断开所有未勾选的本地 Agent/)).length).toBeGreaterThan(0);
    await waitFor(() => {
      const paths = fetchMock.mock.calls.map(([input]) => String(input));
      expect(paths).toContain("/api/agents/local-agent/pairing-tokens/pair-1/revoke");
      expect(paths).toContain("/api/agents/local-agent/connections/local-1/revoke");
      expect(paths).not.toContain("/api/agents/local-agent/connections/local-1");
    });
  });

  it("disconnects Codex when it is unchecked while keeping other selected local Agents", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/agents" && !init?.method) return jsonResponse({ items: [agent()], next_cursor: null });
      if (path === "/api/agents/token-optimizer/presets" && !init?.method) return jsonResponse(tokenOptimizerPresets());
      if (path === "/api/agents/default/knowledge/sources" && !init?.method) return jsonResponse({ items: [], next_cursor: null });
      if (path === "/api/agents/local-agent/connections" && !init?.method) {
        return jsonResponse({
          items: [
            localAgentConnection({
              id: "local-hao",
              pairing_token_id: "pair-1",
              onboarding_confirmed: false,
              display_name: "hao Local Agent",
              adapter_kind: "hao",
            }),
            localAgentConnection({
              id: "local-codex",
              pairing_token_id: "pair-1",
              onboarding_confirmed: false,
              display_name: "Codex CLI",
              adapter_kind: "codex",
              capabilities_json: assistantLocalAgentCapabilities(),
              risk_capabilities_json: fullLocalAgentRiskCapabilities,
            }),
            localAgentConnection({
              id: "local-claude",
              pairing_token_id: "pair-1",
              onboarding_confirmed: false,
              display_name: "Claude Code",
              adapter_kind: "claude_code",
              capabilities_json: assistantLocalAgentCapabilities({
                execution_mode: "headless_harness_tool_bridge",
              }),
              risk_capabilities_json: fullLocalAgentRiskCapabilities,
            }),
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/local-agent/pairing-tokens" && init?.method === "POST") {
        return jsonResponse({
          id: "pair-1",
          agent_id: "default",
          pair_code: "ABC123",
          pair_token: "plain-pair-token",
          command: localAgentPairCommand,
          status: "active",
          expires_at: "2026-06-03T00:10:00Z",
          created_at: "2026-06-03T00:00:00Z",
        }, 201);
      }
      if (path === "/api/agents/local-agent/connections/local-hao" && init?.method === "PATCH") {
        return jsonResponse(localAgentConnection({
          id: "local-hao",
          display_name: (JSON.parse(String(init.body)) as { display_name: string }).display_name,
          adapter_kind: "hao",
        }));
      }
      if (path === "/api/agents/local-agent/connections/local-claude" && init?.method === "PATCH") {
        return jsonResponse(localAgentConnection({
          id: "local-claude",
          display_name: (JSON.parse(String(init.body)) as { display_name: string }).display_name,
          adapter_kind: "claude_code",
        }));
      }
      if (path === "/api/agents/local-agent/pairing-tokens/pair-1/revoke" && init?.method === "POST") {
        return jsonResponse(revokedPairingResponse());
      }
      if (path === "/api/agents/local-agent/connections/local-codex/revoke" && init?.method === "POST") {
        return jsonResponse(localAgentConnection({
          id: "local-codex",
          display_name: "Codex CLI",
          adapter_kind: "codex",
          status: "revoked",
          revoked_at: "2026-06-03T00:02:00Z",
        }));
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    await user.click(await screen.findByRole("button", { name: /打开接入向导|Open connection wizard/ }));
    const dialog = await screen.findByRole("dialog", { name: "接入本地 Agent" });
    await user.click(within(dialog).getByRole("button", { name: /生成连接命令|Generate command/ }));
    await within(dialog).findByText(/已发现 3 个待确认 Agent，已选择 0 个。/);
    await user.click(within(dialog).getByRole("checkbox", { name: /选择 hao Local Agent/ }));
    await user.click(within(dialog).getByRole("checkbox", { name: /选择 Claude Code/ }));
    await within(dialog).findByText(/已发现 3 个待确认 Agent，已选择 2 个。/);
    await user.click(within(dialog).getByRole("button", { name: /接入 2 个 Agent|Connect 2 Agent/ }));

    expect((await screen.findAllByText("本地 Agent 已接入")).length).toBeGreaterThan(0);
    await waitFor(() => {
      const paths = fetchMock.mock.calls.map(([input]) => String(input));
      expect(paths).toContain("/api/agents/local-agent/pairing-tokens/pair-1/revoke");
      expect(paths).toContain("/api/agents/local-agent/connections/local-hao");
      expect(paths).toContain("/api/agents/local-agent/connections/local-claude");
      expect(paths).toContain("/api/agents/local-agent/connections/local-codex/revoke");
      expect(paths).not.toContain("/api/agents/local-agent/connections/local-codex");
    });
  });

  it("preserves detected local Agent choices across discovery polling", async () => {
    const user = userEvent.setup();
    let discoveredConnections = [
      localAgentConnection({
        onboarding_confirmed: false,
        display_name: "Codex CLI",
        adapter_kind: "codex",
        capabilities_json: assistantLocalAgentCapabilities(),
        risk_capabilities_json: fullLocalAgentRiskCapabilities,
      }),
    ];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/agents" && !init?.method) return jsonResponse({ items: [agent()], next_cursor: null });
      if (path === "/api/agents/token-optimizer/presets" && !init?.method) return jsonResponse(tokenOptimizerPresets());
      if (path === "/api/agents/default/knowledge/sources" && !init?.method) return jsonResponse({ items: [], next_cursor: null });
      if (path === "/api/agents/local-agent/connections" && !init?.method) return jsonResponse({ items: discoveredConnections, next_cursor: null });
      if (path === "/api/agents/local-agent/pairing-tokens" && init?.method === "POST") {
        return jsonResponse({
          id: "pair-1",
          agent_id: "default",
          pair_code: "ABC123",
          pair_token: "plain-pair-token",
          command: localAgentPairCommand,
          status: "active",
          expires_at: "2026-06-03T00:10:00Z",
          created_at: "2026-06-03T00:00:00Z",
        }, 201);
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    await user.click(await screen.findByRole("button", { name: /打开接入向导|Open connection wizard/ }));
    const dialog = await screen.findByRole("dialog", { name: "接入本地 Agent" });
    await user.click(within(dialog).getByRole("button", { name: /生成连接命令|Generate command/ }));
    const codexCheckbox = within(dialog).getByRole("checkbox", { name: /选择 Codex CLI/ });
    expect((codexCheckbox as HTMLInputElement).checked).toBe(false);
    const codexNameInput = within(dialog).getByRole("textbox", {
      name: /本地 Agent 名称 Codex CLI/,
    }) as HTMLInputElement;
    expect(codexNameInput).toBeDisabled();
    await user.click(codexCheckbox);
    expect((codexCheckbox as HTMLInputElement).checked).toBe(true);
    await user.clear(codexNameInput);
    await user.type(codexNameInput, "我的 Codex");
    await user.click(codexCheckbox);
    expect((codexCheckbox as HTMLInputElement).checked).toBe(false);

    discoveredConnections = [
      localAgentConnection({
        onboarding_confirmed: false,
        display_name: "Codex CLI Remote",
        adapter_kind: "codex",
        capabilities_json: assistantLocalAgentCapabilities(),
        risk_capabilities_json: fullLocalAgentRiskCapabilities,
      }),
      localAgentConnection({
        id: "local-hao",
        onboarding_confirmed: false,
        display_name: "hao Local Agent",
        adapter_kind: "hao",
      }),
    ];
    await user.click(within(dialog).getByRole("button", { name: /我已执行，刷新识别|I ran it, refresh discovery/ }));

    const refreshedCodexCheckbox = await within(dialog).findByRole("checkbox", { name: /选择 Codex CLI Remote/ }) as HTMLInputElement;
    expect(refreshedCodexCheckbox.checked).toBe(false);
    expect(
      (within(dialog).getByRole("textbox", {
        name: /本地 Agent 名称 Codex CLI Remote/,
      }) as HTMLInputElement).value,
    ).toBe("我的 Codex");
    expect((within(dialog).getByRole("checkbox", { name: /选择 hao Local Agent/ }) as HTMLInputElement).checked).toBe(false);

    discoveredConnections = [
      localAgentConnection({
        id: "local-hao",
        onboarding_confirmed: false,
        display_name: "hao Local Agent",
        adapter_kind: "hao",
      }),
    ];
    await user.click(within(dialog).getByRole("button", { name: /我已执行，刷新识别|I ran it, refresh discovery/ }));

    await waitFor(() => {
      expect(within(dialog).queryByText("Codex CLI Remote")).not.toBeInTheDocument();
      expect(within(dialog).getByText(/已发现 1 个待确认 Agent，已选择 0 个。/)).toBeInTheDocument();
    });
  });

  it("does not auto-connect an already confirmed Codex when the user selects only hao", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/agents" && !init?.method) return jsonResponse({ items: [agent()], next_cursor: null });
      if (path === "/api/agents/token-optimizer/presets" && !init?.method) return jsonResponse(tokenOptimizerPresets());
      if (path === "/api/agents/default/knowledge/sources" && !init?.method) return jsonResponse({ items: [], next_cursor: null });
      if (path === "/api/agents/local-agent/connections" && !init?.method) {
        return jsonResponse({
          items: [
            localAgentConnection({
              id: "local-hao",
              pairing_token_id: "pair-1",
              onboarding_confirmed: false,
              display_name: "hao Local Agent",
              adapter_kind: "hao",
            }),
            localAgentConnection({
              id: "local-codex",
              pairing_token_id: "old-pair",
              onboarding_confirmed: true,
              display_name: "Codex CLI",
              adapter_kind: "codex",
              capabilities_json: assistantLocalAgentCapabilities(),
              risk_capabilities_json: fullLocalAgentRiskCapabilities,
            }),
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/local-agent/pairing-tokens" && init?.method === "POST") {
        return jsonResponse({
          id: "pair-1",
          agent_id: "default",
          pair_code: "ABC123",
          pair_token: "plain-pair-token",
          command: localAgentPairCommand,
          status: "active",
          expires_at: "2026-06-03T00:10:00Z",
          created_at: "2026-06-03T00:00:00Z",
        }, 201);
      }
      if (path === "/api/agents/local-agent/connections/local-hao" && init?.method === "PATCH") {
        return jsonResponse(localAgentConnection({
          id: "local-hao",
          display_name: (JSON.parse(String(init.body)) as { display_name: string }).display_name,
          adapter_kind: "hao",
        }));
      }
      if (path === "/api/agents/local-agent/pairing-tokens/pair-1/revoke" && init?.method === "POST") {
        return jsonResponse(revokedPairingResponse());
      }
      if (path === "/api/agents/local-agent/connections/local-codex/revoke" && init?.method === "POST") {
        return jsonResponse(localAgentConnection({
          id: "local-codex",
          display_name: "Codex CLI",
          adapter_kind: "codex",
          status: "revoked",
          revoked_at: "2026-06-03T00:02:00Z",
        }));
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    await user.click(await screen.findByRole("button", { name: /打开接入向导|Open connection wizard/ }));
    const dialog = await screen.findByRole("dialog", { name: "接入本地 Agent" });
    await user.click(within(dialog).getByRole("button", { name: /生成连接命令|Generate command/ }));
    await within(dialog).findByText(/已发现 2 个待确认 Agent，已选择 0 个。/);
    expect((within(dialog).getByRole("checkbox", { name: /选择 Codex CLI/ }) as HTMLInputElement).checked).toBe(false);
    await user.click(within(dialog).getByRole("checkbox", { name: /选择 hao Local Agent/ }));
    await within(dialog).findByText(/已发现 2 个待确认 Agent，已选择 1 个。/);
    await user.click(within(dialog).getByRole("button", { name: /接入 1 个 Agent|Connect 1 Agent/ }));

    expect((await screen.findAllByText("本地 Agent 已接入")).length).toBeGreaterThan(0);
    await waitFor(() => {
      const paths = fetchMock.mock.calls.map(([input]) => String(input));
      expect(paths).toContain("/api/agents/local-agent/pairing-tokens/pair-1/revoke");
      expect(paths).toContain("/api/agents/local-agent/connections/local-hao");
      expect(paths).toContain("/api/agents/local-agent/connections/local-codex/revoke");
      expect(paths).not.toContain("/api/agents/local-agent/connections/local-codex");
    });
  });

  it("revokes a late Codex registration from the same pairing token when only hao is selected", async () => {
    const user = userEvent.setup();
    let includeLateCodex = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/agents" && !init?.method) return jsonResponse({ items: [agent()], next_cursor: null });
      if (path === "/api/agents/token-optimizer/presets" && !init?.method) return jsonResponse(tokenOptimizerPresets());
      if (path === "/api/agents/default/knowledge/sources" && !init?.method) return jsonResponse({ items: [], next_cursor: null });
      if (path === "/api/agents/local-agent/connections" && !init?.method) {
        return jsonResponse({
          items: [
            localAgentConnection({
              id: "local-hao",
              pairing_token_id: "pair-1",
              onboarding_confirmed: false,
              display_name: "hao Local Agent",
              adapter_kind: "hao",
            }),
            ...(includeLateCodex
              ? [
                  localAgentConnection({
                    id: "local-codex-late",
                    pairing_token_id: "pair-1",
                    onboarding_confirmed: false,
                    display_name: "Codex CLI",
                    adapter_kind: "codex",
                    capabilities_json: assistantLocalAgentCapabilities(),
                    risk_capabilities_json: fullLocalAgentRiskCapabilities,
                  }),
                ]
              : []),
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/local-agent/pairing-tokens" && init?.method === "POST") {
        return jsonResponse({
          id: "pair-1",
          agent_id: "default",
          pair_code: "ABC123",
          pair_token: "plain-pair-token",
          command: localAgentPairCommand,
          status: "active",
          expires_at: "2026-06-03T00:10:00Z",
          created_at: "2026-06-03T00:00:00Z",
        }, 201);
      }
      if (path === "/api/agents/local-agent/pairing-tokens/pair-1/revoke" && init?.method === "POST") {
        includeLateCodex = true;
        return jsonResponse(revokedPairingResponse());
      }
      if (path === "/api/agents/local-agent/connections/local-hao" && init?.method === "PATCH") {
        return jsonResponse(localAgentConnection({
          id: "local-hao",
          display_name: (JSON.parse(String(init.body)) as { display_name: string }).display_name,
          adapter_kind: "hao",
        }));
      }
      if (path === "/api/agents/local-agent/connections/local-codex-late/revoke" && init?.method === "POST") {
        return jsonResponse(localAgentConnection({
          id: "local-codex-late",
          display_name: "Codex CLI",
          adapter_kind: "codex",
          status: "revoked",
          revoked_at: "2026-06-03T00:02:00Z",
        }));
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    await user.click(await screen.findByRole("button", { name: /打开接入向导|Open connection wizard/ }));
    const dialog = await screen.findByRole("dialog", { name: "接入本地 Agent" });
    await user.click(within(dialog).getByRole("button", { name: /生成连接命令|Generate command/ }));
    await within(dialog).findByText(/已发现 1 个待确认 Agent，已选择 0 个。/);
    await user.click(within(dialog).getByRole("checkbox", { name: /选择 hao Local Agent/ }));
    await user.click(within(dialog).getByRole("button", { name: /接入 1 个 Agent|Connect 1 Agent/ }));

    expect((await screen.findAllByText("本地 Agent 已接入")).length).toBeGreaterThan(0);
    await waitFor(() => {
      const paths = fetchMock.mock.calls.map(([input]) => String(input));
      expect(paths).toContain("/api/agents/local-agent/pairing-tokens/pair-1/revoke");
      expect(paths).toContain("/api/agents/local-agent/connections/local-hao");
      expect(paths).toContain("/api/agents/local-agent/connections/local-codex-late/revoke");
      expect(paths).not.toContain("/api/agents/local-agent/connections/local-codex-late");
      expect(
        paths.indexOf("/api/agents/local-agent/pairing-tokens/pair-1/revoke"),
      ).toBeLessThan(paths.indexOf("/api/agents/local-agent/connections/local-codex-late/revoke"));
    });
  });

  it("does not revoke late registrations from a different pairing token while saving", async () => {
    const user = userEvent.setup();
    let includeLateOtherTokenCodex = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.startsWith(apiBaseUrl) ? url.slice(apiBaseUrl.length) : url;
      if (path === "/api/agents" && !init?.method) return jsonResponse({ items: [agent()], next_cursor: null });
      if (path === "/api/agents/token-optimizer/presets" && !init?.method) return jsonResponse(tokenOptimizerPresets());
      if (path === "/api/agents/default/knowledge/sources" && !init?.method) return jsonResponse({ items: [], next_cursor: null });
      if (path === "/api/agents/local-agent/connections" && !init?.method) {
        return jsonResponse({
          items: [
            localAgentConnection({
              id: "local-hao",
              pairing_token_id: "pair-1",
              onboarding_confirmed: false,
              display_name: "hao Local Agent",
              adapter_kind: "hao",
            }),
            ...(includeLateOtherTokenCodex
              ? [
                  localAgentConnection({
                    id: "local-codex-other-token",
                    pairing_token_id: "other-pair",
                    onboarding_confirmed: false,
                    display_name: "Codex CLI",
                    adapter_kind: "codex",
                    capabilities_json: assistantLocalAgentCapabilities(),
                    risk_capabilities_json: fullLocalAgentRiskCapabilities,
                  }),
                ]
              : []),
          ],
          next_cursor: null,
        });
      }
      if (path === "/api/agents/local-agent/pairing-tokens" && init?.method === "POST") {
        return jsonResponse({
          id: "pair-1",
          agent_id: "default",
          pair_code: "ABC123",
          pair_token: "plain-pair-token",
          command: localAgentPairCommand,
          status: "active",
          expires_at: "2026-06-03T00:10:00Z",
          created_at: "2026-06-03T00:00:00Z",
        }, 201);
      }
      if (path === "/api/agents/local-agent/pairing-tokens/pair-1/revoke" && init?.method === "POST") {
        includeLateOtherTokenCodex = true;
        return jsonResponse(revokedPairingResponse());
      }
      if (path === "/api/agents/local-agent/connections/local-hao" && init?.method === "PATCH") {
        return jsonResponse(localAgentConnection({
          id: "local-hao",
          display_name: (JSON.parse(String(init.body)) as { display_name: string }).display_name,
          adapter_kind: "hao",
        }));
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });

    renderPage(fetchMock);

    await user.click(await screen.findByRole("button", { name: /打开接入向导|Open connection wizard/ }));
    const dialog = await screen.findByRole("dialog", { name: "接入本地 Agent" });
    await user.click(within(dialog).getByRole("button", { name: /生成连接命令|Generate command/ }));
    await within(dialog).findByText(/已发现 1 个待确认 Agent，已选择 0 个。/);
    await user.click(within(dialog).getByRole("checkbox", { name: /选择 hao Local Agent/ }));
    await user.click(within(dialog).getByRole("button", { name: /接入 1 个 Agent|Connect 1 Agent/ }));

    expect((await screen.findAllByText("本地 Agent 已接入")).length).toBeGreaterThan(0);
    await waitFor(() => {
      const paths = fetchMock.mock.calls.map(([input]) => String(input));
      expect(paths).toContain("/api/agents/local-agent/pairing-tokens/pair-1/revoke");
      expect(paths).toContain("/api/agents/local-agent/connections/local-hao");
      expect(paths).not.toContain("/api/agents/local-agent/connections/local-codex-other-token/revoke");
      expect(paths).not.toContain("/api/agents/local-agent/connections/local-codex-other-token");
    });
  });
});
