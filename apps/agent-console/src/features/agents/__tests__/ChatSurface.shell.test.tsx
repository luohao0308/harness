import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type JSX } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useConsoleStore } from "../../../stores/consoleStore";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import { ChatSurface } from "../components/ChatSurface";
import type { ChatStreamController } from "../hooks/useChatStream";
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
    description: "Search GitHub issues",
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

function streamController(): ChatStreamController {
  return {
    isStreaming: false,
    start: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(),
    retry: vi.fn(),
    driveBranch: vi.fn(),
  };
}

function renderSurface(
  overrides: Partial<Parameters<typeof ChatSurface>[0]> = {},
) {
  const baseProps: Parameters<typeof ChatSurface>[0] = {
    agentId: "default",
    agentName: "Default Agent",
    modelLabel: "deepseek-v4-flash",
    modelLabelIsFallback: false,
    workspaceMode: "chat",
    onWorkspaceModeChange: vi.fn(),
    activeRunId: null,
    runStatus: undefined,
    runCreatedAt: undefined,
    pendingApprovalCount: 0,
    metadataUsage: {
      inputTokens: 0,
      outputTokens: 0,
      costUsd: "$0.00",
      durationMs: 0,
      modelCalls: 0,
      toolCalls: 0,
    },
    onOpenInspector: vi.fn(),
    stream: streamController(),
    tools,
    providers,
    selectedProviderId: "deepseek-flash",
    selectedModelId: "deepseek-v4-flash",
    onModelChange: vi.fn(),
    onExport: vi.fn(),
    onClearConversation: vi.fn(),
    onOpenSearch: vi.fn(),
    onOpenShortcut: vi.fn(),
    modelPickerOpenSeq: 0,
    onRequestModelPicker: vi.fn(),
    ...overrides,
  };

  const requestSpy = baseProps.onRequestModelPicker;
  const modelChangeSpy = baseProps.onModelChange;
  const modeChangeSpy = baseProps.onWorkspaceModeChange;

  function ChatSurfaceHarness(): JSX.Element {
    const [workspaceMode, setWorkspaceMode] = useState(baseProps.workspaceMode);
    const [modelPickerOpenSeq, setModelPickerOpenSeq] = useState(
      baseProps.modelPickerOpenSeq,
    );
    const [selectedProviderId, setSelectedProviderId] = useState(
      baseProps.selectedProviderId,
    );
    const [selectedModelId, setSelectedModelId] = useState(baseProps.selectedModelId);
    const modelLabel =
      selectedProviderId !== null && selectedModelId !== null
        ? selectedModelId
        : baseProps.modelLabel;

    return (
      <ChatSurface
        {...baseProps}
        workspaceMode={workspaceMode}
        onWorkspaceModeChange={(mode) => {
          modeChangeSpy(mode);
          setWorkspaceMode(mode);
        }}
        modelLabel={modelLabel}
        selectedProviderId={selectedProviderId}
        selectedModelId={selectedModelId}
        onModelChange={(providerId, modelId) => {
          modelChangeSpy(providerId, modelId);
          setSelectedProviderId(providerId);
          setSelectedModelId(modelId);
        }}
        modelPickerOpenSeq={modelPickerOpenSeq}
        onRequestModelPicker={() => {
          requestSpy();
          setModelPickerOpenSeq((seq) => seq + 1);
        }}
      />
    );
  }

  render(
    <MemoryRouter>
      <div className="h-[900px]">
        <ChatSurfaceHarness />
      </div>
    </MemoryRouter>,
  );

  return baseProps;
}

describe("ChatSurface Workspace shell integration", () => {
  beforeEach(() => {
    useConsoleStore.getState().setLocale("en-US");
    useWorkspaceStore.getState().reset();
    Object.defineProperty(URL, "createObjectURL", {
      value: vi.fn(() => "blob:preview"),
      configurable: true,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      value: vi.fn(),
      configurable: true,
    });
  });

  it("opens icon-only composer settings with plugins but without tool capabilities", async () => {
    const user = userEvent.setup();
    renderSurface();

    expect(screen.queryByRole("button", { name: /^Model:/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Context:/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Tools:/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Open composer settings" }));
    const settingsPanel = screen.getByRole("dialog", { name: "Composer settings" });
    expect(settingsPanel).toBeInTheDocument();
    expect(settingsPanel).not.toHaveTextContent("Composer settings");
    expect(screen.queryByRole("dialog", { name: "Options" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add photos and files" })).toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: "Include IDE context" })).not.toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Plan mode" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Plugins / MCP" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /@read_file/ })).not.toBeInTheDocument();
  });

  it("opens the header model picker and top tools panel from shell chips", async () => {
    const user = userEvent.setup();
    const props = renderSurface();

    await user.click(
      screen.getByRole("button", {
        name: "Current model: deepseek-v4-flash",
      }),
    );
    expect(screen.getByRole("listbox", { name: "Switch model" })).toBeInTheDocument();

    const headerModelList = screen.getByRole("listbox", { name: "Switch model" });
    fireEvent.keyDown(headerModelList, { key: "ArrowDown" });
    fireEvent.keyDown(headerModelList, { key: "Enter" });
    expect(props.onRequestModelPicker).not.toHaveBeenCalled();
    expect(props.onModelChange).toHaveBeenCalledWith("deepseek-pro", "deepseek-v4-pro");
    expect(screen.queryByRole("listbox", { name: "Switch model" })).not.toBeInTheDocument();

    await user.click(
      screen.getByRole("button", {
        name: "Tools/MCP: 2 available",
      }),
    );
    expect(screen.getByRole("dialog", { name: "Tools" })).toBeInTheDocument();
    expect(screen.queryByText("Tool capabilities")).not.toBeInTheDocument();
    expect(screen.queryByText("Plugins / MCP")).not.toBeInTheDocument();
    expect(screen.queryByText("github.search")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /@read_file/ }));
    expect(screen.getByPlaceholderText("Chat with the agent")).toHaveValue("@read_file ");
  });

  it("opens the native file picker from the compact tools panel", async () => {
    const user = userEvent.setup();
    const inputClick = vi
      .spyOn(HTMLInputElement.prototype, "click")
      .mockImplementation(() => undefined);
    renderSurface();

    await user.click(screen.getByRole("button", { name: "Open composer settings" }));
    await user.click(screen.getByRole("button", { name: "Add photos and files" }));

    expect(inputClick).toHaveBeenCalledTimes(1);
    inputClick.mockRestore();
  });

  it("previews selected images and file chips inside the composer", async () => {
    const user = userEvent.setup();
    const stream = streamController();
    renderSurface({ stream });

    const image = new File(["image-bytes"], "diagram.png", { type: "image/png" });
    const file = new File(["hello"], "notes.txt", { type: "text/plain" });

    await user.upload(screen.getByLabelText("Add photos and files"), [image, file]);

    expect(screen.getByAltText("diagram.png")).toHaveAttribute("src", "blob:preview");
    expect(screen.getByText("notes.txt")).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("Chat with the agent"), "read it");
    await user.keyboard("{Enter}");

    await waitFor(() => expect(stream.start).toHaveBeenCalled());
    expect(stream.start).toHaveBeenCalledWith(
      expect.objectContaining({
        attachmentNames: ["diagram.png", "notes.txt"],
        attachments: expect.arrayContaining([
          expect.objectContaining({
            name: "notes.txt",
            content_status: "ready",
            content_text: "hello",
          }),
          expect.objectContaining({
            name: "diagram.png",
            content_status: "unsupported",
            content_text: null,
          }),
        ]),
      }),
    );

    expect(URL.revokeObjectURL).toHaveBeenCalled();
  });

  it("renders usage metadata above the composer and keeps metadata out of Inspector", async () => {
    const user = userEvent.setup();
    renderSurface({
      metadataUsage: {
        inputTokens: 1200,
        outputTokens: 345,
        costUsd: "$0.12",
        durationMs: 1530,
        modelCalls: 2,
        toolCalls: 4,
      },
    });

    const metadata = screen.getByLabelText("Run metadata");
    expect(metadata).toHaveTextContent("In");
    expect(metadata).toHaveTextContent("1.2K");
    expect(metadata).toHaveTextContent("$0.12");
    expect(metadata).toHaveTextContent("1.5s");

    await user.click(screen.getByRole("button", { name: "Inspector" }));
    expect(screen.queryByRole("menuitem", { name: "Metadata" })).not.toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Artifacts" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Runtime" })).toBeInTheDocument();
  });

  it("keeps tools in the top panel and MCP plugins in composer settings", async () => {
    const user = userEvent.setup();
    renderSurface();

    await user.click(screen.getByRole("button", { name: "Tools/MCP: 2 available" }));
    await user.click(screen.getByRole("button", { name: /@read_file/ }));

    expect(screen.getByPlaceholderText("Chat with the agent")).toHaveValue("@read_file ");

    await user.click(screen.getByRole("button", { name: "Open composer settings" }));
    await user.click(screen.getByRole("button", { name: "Plugins / MCP" }));
    expect(screen.getByText("github.search")).toBeInTheDocument();
    const githubButtons = screen.getAllByRole("button", { name: /@github_search/ });
    await user.click(githubButtons[githubButtons.length - 1]);

    expect(screen.getByPlaceholderText("Chat with the agent")).toHaveValue(
      "@read_file @github_search ",
    );
  });

  it("uses markdown planning mode from the compact plan switch", async () => {
    const user = userEvent.setup();
    const stream = streamController();
    const props = renderSurface({ stream });

    await user.click(screen.getByRole("button", { name: "Open composer settings" }));
    const planSwitch = screen.getByRole("switch", { name: "Plan mode" });
    expect(planSwitch).toHaveClass("inline-flex", "shrink-0");
    await user.click(planSwitch);
    expect(props.onWorkspaceModeChange).toHaveBeenCalledWith("markdown_plan");

    await user.type(
      screen.getByPlaceholderText("Describe a goal; returns a markdown plan"),
      "make a plan",
    );
    await user.keyboard("{Enter}");

    expect(stream.start).toHaveBeenCalledWith(
      expect.objectContaining({
        goal: "make a plan",
        mode: "markdown_plan",
        attachmentNames: [],
      }),
    );
  });

  it("opens a working model picker from slash /model", async () => {
    const user = userEvent.setup();
    const props = renderSurface();

    await user.type(screen.getByPlaceholderText("Chat with the agent"), "/model ");
    await user.keyboard("{Enter}");

    expect(screen.getByRole("dialog", { name: "Switch model" })).toBeInTheDocument();
    await user.click(screen.getByRole("option", { name: /DeepSeek Pro/ }));

    expect(props.onRequestModelPicker).not.toHaveBeenCalled();
    expect(props.onModelChange).toHaveBeenCalledWith("deepseek-pro", "deepseek-v4-pro");
    expect(screen.queryByRole("dialog", { name: "Switch model" })).not.toBeInTheDocument();
  });

});
