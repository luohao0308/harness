import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useConsoleStore } from "../../../stores/consoleStore";
import { WorkspaceShellBar } from "../components/WorkspaceShellBar";
import type { ModelOption } from "../components/ModelPicker";
import type { AgentDefinition, LocalAgentConnection, ToolMetadata } from "../../tasks/api";

const providers: ModelOption[] = [
  {
    providerId: "deepseek-flash",
    providerLabel: "DeepSeek Flash",
    modelId: "deepseek-v4-flash",
    modelLabel: "deepseek-v4-flash",
  },
  {
    providerId: "deepseek-pro",
    providerLabel: "DeepSeek Pro",
    modelId: "deepseek-v4-pro",
    modelLabel: "deepseek-v4-pro",
  },
];

const tools: ToolMetadata[] = [
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
    description: "Search GitHub",
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
];

function localAgentConnection(overrides: Partial<LocalAgentConnection> = {}): LocalAgentConnection {
  return {
    id: "local-hao",
    agent_id: "default",
    owner_user_id: "dev-engineer",
    pairing_token_id: "pair-1",
    onboarding_confirmed: true,
    display_name: "hao Local Agent",
    adapter_kind: "hao",
    protocol_version: "local-agent-v1",
    bridge_version: "agent-console-test",
    status: "online",
    workspace_root: "/tmp/workspace",
    capabilities_json: {},
    risk_capabilities_json: [],
    last_seen_at: "2026-06-03T00:00:00Z",
    revoked_at: null,
    created_at: "2026-06-03T00:00:00Z",
    updated_at: "2026-06-03T00:00:00Z",
    ...overrides,
  };
}

function agentDefinition(overrides: Partial<AgentDefinition> = {}): AgentDefinition {
  return {
    id: "default",
    name: "Default Agent",
    description: "Default workspace agent",
    role: "planner",
    status: "ACTIVE",
    model_provider: "default",
    model_name: "default",
    system_prompt: "Plan with evidence",
    tools_json: [],
    routing_tags: [],
    max_parallel_assignments: 2,
    capability_attachments: [],
    created_at: "2026-06-03T00:00:00Z",
    updated_at: "2026-06-03T00:00:00Z",
    ...overrides,
  };
}

function renderShell(overrides: Partial<Parameters<typeof WorkspaceShellBar>[0]> = {}) {
  const props: Parameters<typeof WorkspaceShellBar>[0] = {
    workspaceId: "default",
    workspaceOptions: [
      { value: "default", label: "Default Agent", description: "Workspace · ACTIVE" },
      { value: "researcher", label: "Research Agent", description: "Workspace · ACTIVE" },
    ],
    onWorkspaceChange: vi.fn(),
    agentId: "default",
    agentName: "Default Agent",
    activeRunId: null,
    runStatus: undefined,
    tools,
    providers,
    selectedProviderId: "deepseek-flash",
    selectedModelId: "deepseek-v4-flash",
    isStreaming: false,
    onModelChange: vi.fn(),
    onInsertToolMention: vi.fn(),
    onOpenInspector: vi.fn(),
    ...overrides,
  };

  render(
    <MemoryRouter>
      <WorkspaceShellBar {...props} />
    </MemoryRouter>,
  );

  return props;
}

describe("WorkspaceShellBar", () => {
  beforeEach(() => {
    delete window.desktopApi;
  });

  afterEach(() => {
    delete window.desktopApi;
  });

  it("keeps the Workspace title controls visible without the old metric row", () => {
    useConsoleStore.getState().setLocale("en-US");
    renderShell();

    expect(screen.getByRole("link", { name: "返回智能体列表" })).toHaveAttribute(
      "href",
      "/agents",
    );
    expect(
      screen.getByRole("button", {
        name: "切换工作区：Default Agent",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/模型加运行平台组成智能体/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", {
        name: "Current model: deepseek-v4-flash",
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "工具/MCP（模型上下文协议）: 2 个可用",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Model:/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Context:/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Tools:/ })).not.toBeInTheDocument();
    expect(screen.getByLabelText("运行未创建")).toBeInTheDocument();
  });

  it("renders the workspace switcher in the shell header", () => {
    useConsoleStore.getState().setLocale("en-US");
    renderShell();

    expect(
      screen.getByRole("button", {
        name: "切换工作区：Default Agent",
      }),
    ).toBeInTheDocument();
  });

  it("renders a compact Codex-style action bar in desktop runtime", () => {
    window.desktopApi = {};
    renderShell();

    expect(screen.getByTestId("desktop-workspace-header")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "返回智能体列表" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "切换工作区：Default Agent" })).not.toBeInTheDocument();
    expect(screen.queryByText("模型加运行平台组成智能体")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("运行未创建")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "工具/MCP（模型上下文协议）: 2 个可用" }),
    ).toHaveClass("w-8");
  });

  it("opens an active run in a separate window only in desktop runtime", () => {
    const openRun = vi.fn(async () => ({} as never));
    window.desktopApi = { window: { openRun } };
    renderShell({ activeRunId: "run-123" });

    fireEvent.click(screen.getByRole("button", { name: "在独立窗口打开运行" }));

    expect(openRun).toHaveBeenCalledWith("run-123");
  });

  it("links to Run Detail after a run exists", () => {
    useConsoleStore.getState().setLocale("en-US");

    renderShell({
      activeRunId: "run-123",
      runStatus: "WAITING_APPROVAL",
    });

    expect(screen.getByRole("link", { name: "运行详情" })).toHaveAttribute(
      "href",
      "/runs/run-123",
    );
    expect(screen.getByText("待审批")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "在独立窗口打开运行" }),
    ).not.toBeInTheDocument();
  });

  it("includes the active conversation return target in Run Detail links", () => {
    useConsoleStore.getState().setLocale("en-US");

    renderShell({
      activeRunId: "run-123",
      runStatus: "WAITING_APPROVAL",
      runReturnTarget: {
        agentId: "support-agent",
        conversationId: "conv-42",
      },
    });

    expect(screen.getByRole("link", { name: "运行详情" })).toHaveAttribute(
      "href",
      "/runs/run-123?return_to=%2Fagents%2Fsupport-agent%2Fworkspace%3Fconversation_id%3Dconv-42&conversation_id=conv-42",
    );
  });

  it("does not render unconfirmed or revoked local Agents in the target picker", () => {
    useConsoleStore.getState().setLocale("zh-CN");
    renderShell({
      agents: [agentDefinition()],
      onAgentChange: vi.fn(),
      onLocalAgentTargetChange: vi.fn(),
      localAgentEnabled: true,
      selectedLocalConnectionId: "local-hao",
      localAgentConnections: [
        localAgentConnection(),
        localAgentConnection({
          id: "local-codex-unconfirmed",
          onboarding_confirmed: false,
          display_name: "Codex CLI",
          adapter_kind: "codex",
        }),
        localAgentConnection({
          id: "local-codex-pending-status",
          onboarding_confirmed: true,
          display_name: "Codex Pending",
          adapter_kind: "codex",
          status: "pending_confirmation",
        }),
        {
          ...localAgentConnection({
            id: "local-codex-missing-confirmation",
            display_name: "Codex Missing Confirmation",
            adapter_kind: "codex",
          }),
          onboarding_confirmed: undefined,
        } as unknown as LocalAgentConnection,
        localAgentConnection({
          id: "local-claude-revoked",
          display_name: "Claude Code",
          adapter_kind: "claude_code",
          status: "revoked",
          revoked_at: "2026-06-03T00:01:00Z",
        }),
      ],
    });

    fireEvent.click(screen.getByRole("button", { name: /切换智能体或本地 Agent/ }));

    expect(screen.getAllByText("hao Local Agent").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("Codex CLI")).not.toBeInTheDocument();
    expect(screen.queryByText("Codex Pending")).not.toBeInTheDocument();
    expect(screen.queryByText("Codex Missing Confirmation")).not.toBeInTheDocument();
    expect(screen.queryByText("Claude Code")).not.toBeInTheDocument();
  });

  it("opens tools capabilities from the lightweight proof chip", () => {
    useConsoleStore.getState().setLocale("en-US");
    const props = renderShell();

    fireEvent.click(
      screen.getByRole("button", {
        name: "工具/MCP（模型上下文协议）: 2 个可用",
      }),
    );
    expect(screen.getByRole("dialog", { name: "工具" })).toBeInTheDocument();
    expect(screen.getByText("工具快捷插入")).toBeInTheDocument();
    expect(screen.queryByText("Tool capabilities")).not.toBeInTheDocument();
    expect(screen.queryByText("Plugins / MCP")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /@read_file/ }));

    expect(props.onModelChange).not.toHaveBeenCalled();
    expect(props.onInsertToolMention).toHaveBeenCalledWith("read_file");
  });

  it("shows the Team Mode launcher when supplied by the workspace page", () => {
    useConsoleStore.getState().setLocale("en-US");
    const onCreateTeamFromConversation = vi.fn();
    renderShell({ onCreateTeamFromConversation });

    fireEvent.click(screen.getByRole("button", { name: "新开团队模式" }));

    expect(onCreateTeamFromConversation).toHaveBeenCalledTimes(1);
  });
});
