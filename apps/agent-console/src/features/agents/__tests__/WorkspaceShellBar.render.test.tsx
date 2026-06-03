import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { useConsoleStore } from "../../../stores/consoleStore";
import { WorkspaceShellBar } from "../components/WorkspaceShellBar";
import type { ModelOption } from "../components/ModelPicker";
import type { ToolMetadata } from "../../tasks/api";

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

function renderShell(overrides: Partial<Parameters<typeof WorkspaceShellBar>[0]> = {}) {
  const props: Parameters<typeof WorkspaceShellBar>[0] = {
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
    onStop: vi.fn(),
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
  it("keeps the Workspace title controls visible without the old metric row", () => {
    useConsoleStore.getState().setLocale("en-US");
    renderShell();

    expect(screen.getByRole("link", { name: "返回智能体列表" })).toHaveAttribute(
      "href",
      "/agents",
    );
    expect(screen.getByText("Default Agent")).toBeInTheDocument();
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
    expect(screen.getByText("WAITING_APPROVAL")).toBeInTheDocument();
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
    expect(screen.queryByText("Tool capabilities")).not.toBeInTheDocument();
    expect(screen.queryByText("Plugins / MCP")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /@read_file/ }));

    expect(props.onModelChange).not.toHaveBeenCalled();
    expect(props.onInsertToolMention).toHaveBeenCalledWith("read_file");
  });
});
