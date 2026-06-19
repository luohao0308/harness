import { act, render, screen, waitFor, within } from "@testing-library/react";
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
    vi.unstubAllGlobals();
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

    await user.click(screen.getByRole("button", { name: "打开输入设置" }));
    const settingsPanel = screen.getByRole("dialog", { name: "输入设置" });
    expect(settingsPanel).toBeInTheDocument();
    expect(settingsPanel).toHaveTextContent("输入设置");
    expect(screen.getByRole("button", { name: "关闭输入设置" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Options" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "添加照片和文件" })).toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: "Include IDE context" })).not.toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "计划模式" })).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "追踪目标模式" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "追求目标模式" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "插件 / MCP（模型上下文协议）" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /@read_file/ })).not.toBeInTheDocument();
  });

  it("keeps the composer primary action as Send instead of Resume after a paused answer", () => {
    const store = useWorkspaceStore.getState();
    const userNodeId = store.appendNode({
      parent_id: store.rootNodeId,
      role: "user",
      content: "hello",
      state: "done",
      metadata: {},
      tool_calls: [],
      artifacts: [],
    });
    store.appendNode({
      parent_id: userNodeId,
      role: "assistant",
      content: "partial",
      state: "paused",
      run_id: "run-paused",
      metadata: {},
      tool_calls: [],
      artifacts: [],
    });

    renderSurface();

    expect(screen.getByRole("button", { name: "发送" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "继续生成" })).not.toBeInTheDocument();
  });

  it("renders a Codex-style active goal row above the composer", async () => {
    const user = userEvent.setup();
    const stream = { ...streamController(), isStreaming: true };
    const store = useWorkspaceStore.getState();
    const userNodeId = store.appendNode({
      parent_id: store.rootNodeId,
      role: "user",
      content: "写一个完整结局的短篇",
      state: "done",
      metadata: {},
      tool_calls: [],
      artifacts: [],
    });
    const assistantNodeId = store.appendNode({
      parent_id: userNodeId,
      role: "assistant",
      content: "",
      state: "streaming",
      run_id: "run-goal-row",
      metadata: {
        workspace_mode: "goal",
        goal_status: "running",
        goal_text: "写一个完整结局的短篇",
        goal_phase: "executing",
        goal_elapsed_ms: 4200,
        goal_run_id: "run-goal-row",
      },
      tool_calls: [],
      artifacts: [],
    });
    store.setActiveStream({
      node_id: assistantNodeId,
      controller: new AbortController(),
      started_at: performance.now(),
    });

    const props = renderSurface({ stream });

    const goalStatus = screen
      .getAllByRole("status")
      .find((element) => element.textContent?.includes("进行中的目标"));
    expect(goalStatus).toBeDefined();
    expect(goalStatus).toHaveTextContent("进行中的目标");
    expect(goalStatus).toHaveTextContent("写一个完整结局的短篇");
    expect(goalStatus).toHaveTextContent("4s");
    expect(goalStatus).not.toHaveTextContent("已推进");
    expect(goalStatus).not.toHaveTextContent("Run Detail");
    expect(goalStatus?.className).toContain("w-[calc(100%-56px)]");
    expect(goalStatus?.className).toContain("py-1.5");

    await user.click(goalStatus!.querySelectorAll("button")[1]);
    expect(stream.pause).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "编辑目标" }));
    const dialog = screen.getByRole("dialog", { name: "编辑目标" });
    expect(dialog).toBeInTheDocument();
    expect(dialog.className).toContain("max-w-lg");
    expect(dialog.className).toContain("bg-white");
    expect(within(dialog).queryByText("目标模型")).not.toBeInTheDocument();
    expect(within(dialog).getByRole("textbox", { name: "编辑目标" })).toHaveValue(
      "写一个完整结局的短篇",
    );
    expect(within(dialog).getByRole("button", { name: "保存目标" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "取消编辑目标" })).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "取消编辑目标" }));

    await user.click(screen.getByRole("button", { name: "清除目标" }));
    expect(screen.queryByText("进行中的目标")).not.toBeInTheDocument();
  });

  it("ticks active goal elapsed time locally between server progress events", async () => {
    vi.useFakeTimers();
    const baseNow = new Date("2026-06-19T00:00:00.000Z");
    vi.setSystemTime(baseNow);
    try {
      const stream = { ...streamController(), isStreaming: true };
      const store = useWorkspaceStore.getState();
      const userNodeId = store.appendNode({
        parent_id: store.rootNodeId,
        role: "user",
        content: "持续写完目标",
        state: "done",
        metadata: {},
        tool_calls: [],
        artifacts: [],
      });
      const assistantNodeId = store.appendNode({
        parent_id: userNodeId,
        role: "assistant",
        content: "",
        state: "streaming",
        run_id: "run-goal-timer",
        metadata: {
          workspace_mode: "goal",
          goal_status: "running",
          goal_text: "持续写完目标",
          goal_phase: "executing",
          goal_started_at: new Date(baseNow.getTime() - 1500).toISOString(),
          goal_elapsed_ms: 0,
          goal_run_id: "run-goal-timer",
        },
        tool_calls: [],
        artifacts: [],
      });
      store.setActiveStream({
        node_id: assistantNodeId,
        controller: new AbortController(),
        started_at: performance.now(),
      });

      renderSurface({ stream });

      const statusBefore = screen
        .getAllByRole("status")
        .find((element) => element.textContent?.includes("进行中的目标"));
      expect(statusBefore).toBeDefined();
      expect(statusBefore!).toHaveTextContent("2s");

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });

      const statusAfter = screen
        .getAllByRole("status")
        .find((element) => element.textContent?.includes("进行中的目标"));
      expect(statusAfter).toBeDefined();
      expect(statusAfter!).toHaveTextContent("3s");
    } finally {
      vi.useRealTimers();
    }
  });

  it("resumes a paused active goal from the progress row", async () => {
    const user = userEvent.setup();
    const stream = streamController();
    const store = useWorkspaceStore.getState();
    const userNodeId = store.appendNode({
      parent_id: store.rootNodeId,
      role: "user",
      content: "继续目标",
      state: "done",
      metadata: {},
      tool_calls: [],
      artifacts: [],
    });
    const assistantNodeId = store.appendNode({
      parent_id: userNodeId,
      role: "assistant",
      content: "partial",
      state: "paused",
      run_id: "run-paused-goal-row",
      metadata: {
        workspace_mode: "goal",
        goal_status: "paused",
        goal_text: "继续目标",
        goal_phase: "paused",
        goal_elapsed_ms: 1000,
        goal_run_id: "run-paused-goal-row",
      },
      tool_calls: [],
      artifacts: [],
    });

    renderSurface({ stream });

    await user.click(screen.getByRole("button", { name: "恢复目标" }));
    expect(stream.resume).toHaveBeenCalledWith(assistantNodeId);
  });

  it("keeps the goal row visible after a completed goal instead of falling back to run summary affordances", () => {
    const store = useWorkspaceStore.getState();
    const userNodeId = store.appendNode({
      parent_id: store.rootNodeId,
      role: "user",
      content: "写个故事直到主角出现",
      state: "done",
      metadata: {},
      tool_calls: [],
      artifacts: [],
    });
    store.appendNode({
      parent_id: userNodeId,
      role: "assistant",
      content: "目标已达成。",
      state: "done",
      run_id: "run-complete",
      metadata: {
        workspace_mode: "goal",
        goal_status: "completed",
        goal_text: "写个故事直到主角出现",
        goal_phase: "completed",
        goal_elapsed_ms: 6400,
        goal_message: "目标已达成。",
        goal_run_id: "run-complete",
      },
      tool_calls: [],
      artifacts: [],
    });

    renderSurface({
      activeRunId: "run-complete",
      runStatus: "COMPLETED",
      runCreatedAt: "2026-06-18T07:54:48Z",
    });

    expect(screen.getByText("目标已完成")).toBeInTheDocument();
    expect(screen.getAllByText("写个故事直到主角出现").length).toBeGreaterThan(0);
    expect(screen.queryByText(/已推进/)).not.toBeInTheDocument();
    expect(screen.queryByText("查看运行详情")).not.toBeInTheDocument();
  });

  it("keeps the local Agent draft when submit reports not sent", async () => {
    const user = userEvent.setup();
    const onLocalAgentSubmit = vi.fn(() => false);
    renderSurface({ onLocalAgentSubmit });

    const composer = screen.getByPlaceholderText("直接与智能体对话");
    await user.type(composer, "keep this draft");
    await user.click(screen.getByRole("button", { name: "发送" }));

    expect(onLocalAgentSubmit).toHaveBeenCalledWith(
      "keep this draft",
      expect.objectContaining({
        workspace_mode: "chat",
        mode: "chat",
        model_provider: "deepseek-flash",
        model_name: "deepseek-v4-flash",
        messages: expect.any(Array),
        pinned_node_ids: expect.any(Array),
        tool_mentions: expect.any(Array),
        attachment_names: expect.any(Array),
        attachments: expect.any(Array),
      }),
    );
    expect(composer).toHaveValue("keep this draft");
  });

  it("does not clear newer typing or duplicate submit while async submit is pending", async () => {
    const user = userEvent.setup();
    let resolveSubmit!: (value: boolean) => void;
    const submitPromise = new Promise<boolean>((resolve) => {
      resolveSubmit = resolve;
    });
    const onLocalAgentSubmit = vi.fn(() => submitPromise);
    renderSurface({ onLocalAgentSubmit });

    const composer = screen.getByPlaceholderText("直接与智能体对话");
    await user.type(composer, "first draft");
    await user.keyboard("{Enter}");
    await waitFor(() => expect(onLocalAgentSubmit).toHaveBeenCalledTimes(1));

    await user.keyboard("{Enter}");
    expect(onLocalAgentSubmit).toHaveBeenCalledTimes(1);

    await user.type(composer, " plus more");
    await act(async () => {
      resolveSubmit(true);
      await submitPromise;
    });

    await waitFor(() => expect(composer).toHaveValue("first draft plus more"));
  });

  it("keeps the model picker beside send and top tools panel in the shell", async () => {
    const user = userEvent.setup();
    renderSurface();

    expect(
      screen.queryByRole("button", {
        name: "Current model: deepseek-v4-flash",
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "deepseek-v4-flash",
      }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "deepseek-v4-flash" }));
    expect(screen.getByRole("listbox", { name: "切换模型" })).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", {
        name: "工具/MCP（模型上下文协议）: 2 个可用",
      }),
    );
    expect(screen.getByRole("dialog", { name: "工具" })).toBeInTheDocument();
    expect(screen.getByText("工具快捷插入")).toBeInTheDocument();
    expect(screen.queryByText("Tool capabilities")).not.toBeInTheDocument();
    expect(screen.queryByText("插件 / MCP")).not.toBeInTheDocument();
    expect(screen.queryByText("github.search")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /@read_file/ }));
    expect(screen.getByPlaceholderText("直接与智能体对话")).toHaveValue("@read_file ");
  });

  it("opens the native file picker from the compact tools panel", async () => {
    const user = userEvent.setup();
    const inputClick = vi
      .spyOn(HTMLInputElement.prototype, "click")
      .mockImplementation(() => undefined);
    renderSurface();

    await user.click(screen.getByRole("button", { name: "打开输入设置" }));
    await user.click(screen.getByRole("button", { name: "添加照片和文件" }));

    expect(inputClick).toHaveBeenCalledTimes(1);
    inputClick.mockRestore();
  });

  it("previews selected images and file chips inside the composer", async () => {
    const user = userEvent.setup();
    const stream = streamController();
    renderSurface({ stream });

    const image = new File(["image-bytes"], "diagram.png", { type: "image/png" });
    const file = new File(["hello"], "notes.txt", { type: "text/plain" });

    await user.upload(screen.getByLabelText("添加照片和文件"), [image, file]);

    expect(screen.getByAltText("diagram.png")).toHaveAttribute("src", "blob:preview");
    expect(screen.getByText("notes.txt")).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "read it");
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

    const metadata = screen.getByLabelText("运行元数据");
    expect(metadata).toHaveTextContent("输入");
    expect(metadata).toHaveTextContent("1.2K");
    expect(metadata).toHaveTextContent("$0.12");
    expect(metadata).toHaveTextContent("1.5s");

    await user.click(screen.getByRole("button", { name: "检查器" }));
    expect(screen.queryByRole("menuitem", { name: "Metadata" })).not.toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "产物" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "运行时" })).toBeInTheDocument();
  });

  it("keeps tools in the top panel and MCP plugins in composer settings", async () => {
    const user = userEvent.setup();
    renderSurface();

    await user.click(screen.getByRole("button", { name: "工具/MCP（模型上下文协议）: 2 个可用" }));
    await user.click(screen.getByRole("button", { name: /@read_file/ }));

    expect(screen.getByPlaceholderText("直接与智能体对话")).toHaveValue("@read_file ");

    await user.click(screen.getByRole("button", { name: "打开输入设置" }));
    await user.click(screen.getByRole("button", { name: "插件 / MCP（模型上下文协议）" }));
    expect(screen.getByText("github.search")).toBeInTheDocument();
    const githubButtons = screen.getAllByRole("button", { name: /@github_search/ });
    await user.click(githubButtons[githubButtons.length - 1]);

    expect(screen.getByPlaceholderText("直接与智能体对话")).toHaveValue(
      "@read_file @github_search ",
    );
  });

  it("uses markdown planning mode from the compact plan switch", async () => {
    const user = userEvent.setup();
    const stream = streamController();
    const props = renderSurface({ stream });

    await user.click(screen.getByRole("button", { name: "打开输入设置" }));
    const planSwitch = screen.getByRole("switch", { name: "计划模式" });
    expect(planSwitch).toHaveClass("inline-flex", "shrink-0");
    await user.click(planSwitch);
    expect(props.onWorkspaceModeChange).toHaveBeenCalledWith("markdown_plan");

    await user.type(
      screen.getByPlaceholderText("描述目标，返回 markdown 规划"),
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

  it("uses goal pursuit mode from the compact settings switch", async () => {
    const user = userEvent.setup();
    const stream = streamController();
    const props = renderSurface({ stream });

    await user.click(screen.getByRole("button", { name: "打开输入设置" }));
    const goalSwitch = screen.getByRole("switch", { name: "追踪目标模式" });
    expect(goalSwitch).toHaveClass("inline-flex", "shrink-0");
    await user.click(goalSwitch);
    expect(props.onWorkspaceModeChange).toHaveBeenCalledWith("goal");

    await user.type(
      screen.getByPlaceholderText("描述目标，持续规划并推进执行"),
      "ship the goal",
    );
    await user.keyboard("{Enter}");

    expect(stream.start).toHaveBeenCalledWith(
      expect.objectContaining({
        goal: "ship the goal",
        mode: "goal",
      }),
    );
    expect(screen.queryByRole("dialog", { name: "进入追求目标模式" })).not.toBeInTheDocument();
  });

  it("submits executable run mode without a second confirmation dialog", async () => {
    const user = userEvent.setup();
    const stream = streamController();
    renderSurface({ stream, workspaceMode: "plan" });

    await user.type(
      screen.getByPlaceholderText("描述目标，创建规划后执行运行"),
      "run the task",
    );
    await user.keyboard("{Enter}");

    expect(stream.start).toHaveBeenCalledWith(
      expect.objectContaining({
        goal: "run the task",
        mode: "plan",
      }),
    );
    expect(screen.queryByRole("dialog", { name: "创建规划后执行运行" })).not.toBeInTheDocument();
  });

  it("opens a working model picker from slash /model", async () => {
    const user = userEvent.setup();
    const props = renderSurface();

    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "/model ");
    await user.keyboard("{Enter}");

    expect(screen.getByRole("dialog", { name: "切换模型" })).toBeInTheDocument();
    await user.click(screen.getByRole("option", { name: /DeepSeek Pro/ }));

    expect(props.onRequestModelPicker).not.toHaveBeenCalled();
    expect(props.onModelChange).toHaveBeenCalledWith("deepseek-pro", "deepseek-v4-pro");
    expect(screen.queryByRole("dialog", { name: "切换模型" })).not.toBeInTheDocument();
  });

  it("lists available MCP tools from slash /mcp", async () => {
    const user = userEvent.setup();
    renderSurface();

    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "/mcp ");
    await user.keyboard("{Enter}");

    expect(screen.getByRole("dialog", { name: "可用 MCP" })).toBeInTheDocument();
    expect(screen.getByText("github.search")).toBeInTheDocument();

    const githubButtons = screen.getAllByRole("button", { name: /@github_search/ });
    await user.click(githubButtons[githubButtons.length - 1]);

    expect(screen.getByPlaceholderText("直接与智能体对话")).toHaveValue("@github_search ");
  });

  it("dispatches slash commands when menu items are clicked with the mouse", async () => {
    const user = userEvent.setup();
    const props = renderSurface();

    await user.type(screen.getByPlaceholderText("直接与智能体对话"), "/");
    await user.click(screen.getByRole("option", { name: /\/search/ }));

    expect(props.onOpenSearch).toHaveBeenCalledTimes(1);
  });

  it("approves a markdown plan by creating a Plan-Act run from the original goal", async () => {
    const user = userEvent.setup();
    const store = useWorkspaceStore.getState();
    const userNodeId = store.appendNode({
      parent_id: store.rootNodeId,
      role: "user",
      content: "build run observability",
      state: "done",
      metadata: {},
      tool_calls: [],
      artifacts: [],
    });
    store.appendNode({
      parent_id: userNodeId,
      role: "assistant",
      content: "1. Inspect\n2. Implement\n3. Verify",
      state: "done",
      metadata: { workspace_mode: "markdown_plan" },
      tool_calls: [],
      artifacts: [],
    });
    const stream = streamController();
    renderSurface({ stream });

    await user.click(screen.getByRole("button", { name: "批准并执行" }));

    await waitFor(() => expect(stream.driveBranch).toHaveBeenCalledTimes(1));
    expect(stream.driveBranch).toHaveBeenCalledWith(
      expect.objectContaining({
        goal: "build run observability",
        mode: "plan",
      }),
    );
  });

  it("creates a sibling assistant branch and switches between branches", async () => {
    const user = userEvent.setup();
    const store = useWorkspaceStore.getState();
    const userNodeId = store.appendNode({
      parent_id: store.rootNodeId,
      role: "user",
      content: "explain branches",
      state: "done",
      metadata: {},
      tool_calls: [],
      artifacts: [],
    });
    const firstAssistantId = useWorkspaceStore.getState().appendNode({
      parent_id: userNodeId,
      role: "assistant",
      content: "first answer",
      state: "done",
      metadata: { workspace_mode: "chat" },
      tool_calls: [],
      artifacts: [],
    });
    const stream = streamController();
    renderSurface({ stream });

    expect(screen.getByText("first answer")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "分支" }));

    await waitFor(() => expect(stream.driveBranch).toHaveBeenCalledTimes(1));
    const siblings = useWorkspaceStore
      .getState()
      .getSiblings(firstAssistantId)
      .filter((node) => node.role === "assistant");
    expect(siblings).toHaveLength(2);
    expect(stream.driveBranch).toHaveBeenCalledWith({
      assistantNodeId: siblings[1].id,
      goal: "explain branches",
      mode: "chat",
    });
    expect(screen.getByText("2/2")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "上一个分支" }));
    expect(screen.getByText("1/2")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "下一个分支" }));
    expect(screen.getByText("2/2")).toBeInTheDocument();
  });

  it("compresses context from the usage ring without mutating the token budget", async () => {
    const user = userEvent.setup();
    let compressedNodeId = "";
    let resolveCompression!: () => void;
    const compressionPending = new Promise<void>((resolve) => {
      resolveCompression = resolve;
    });
    const fetchMock = vi.fn(async () => {
      await compressionPending;
      return new Response(
        JSON.stringify({
          status: "ok",
          cache_status: "recomputed",
          summary: "compressed summary",
          coverage_node_ids: [compressedNodeId],
          coverage_path_hash: "a".repeat(64),
          last_covered_node_id: compressedNodeId,
          summary_schema_version: "workspace-context-summary-v1",
          compression_prompt_version: "workspace-context-compression-v1",
          compressor_provider: "deepseek-flash",
          compressor_model: "deepseek-v4-flash",
          estimated_original_tokens: 20,
          estimated_summary_tokens: 4,
          estimated_uncovered_tokens: 0,
          created_at: "2026-05-14T00:00:00Z",
          updated_at: "2026-05-14T00:00:00Z",
          error: null,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    useWorkspaceStore.getState().setContextMaxTokens(1_000_000);
    compressedNodeId = useWorkspaceStore.getState().appendNode({
      parent_id: "root",
      role: "user",
      content: "node that should be compressed",
      state: "done",
      metadata: {},
      tool_calls: [],
      artifacts: [],
    });
    renderSurface();

    await user.click(
      screen.getByRole("button", {
        name: /背景信息窗口：1% 已用，预计发送 7 标记，共 1m/,
      }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(screen.getByText("正在压缩上下文...")).toBeInTheDocument();
    expect(screen.getByText("摘要中")).toBeInTheDocument();
    resolveCompression();
    expect(useWorkspaceStore.getState().contextMaxTokens).toBe(1_000_000);
    await waitFor(() =>
      expect(Object.values(useWorkspaceStore.getState().contextCompressions)[0]).toMatchObject({
        summary: "compressed summary",
        status: "ready",
      }),
    );
    await waitFor(() =>
      expect(screen.queryByText("正在压缩上下文...")).not.toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", {
          name: /背景信息窗口：1% 已用，预计发送 5 标记，共 1m/,
        }),
      ).toBeInTheDocument(),
    );
  });

  it("compresses context from the slash command menu", async () => {
    const user = userEvent.setup();
    let compressedNodeId = "";
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          status: "ok",
          cache_status: "recomputed",
          summary: "slash compressed summary",
          coverage_node_ids: [compressedNodeId],
          coverage_path_hash: "c".repeat(64),
          last_covered_node_id: compressedNodeId,
          summary_schema_version: "workspace-context-summary-v1",
          compression_prompt_version: "workspace-context-compression-v1",
          compressor_provider: "deepseek-flash",
          compressor_model: "deepseek-v4-flash",
          estimated_original_tokens: 20,
          estimated_summary_tokens: 4,
          estimated_uncovered_tokens: 0,
          created_at: "2026-05-14T00:00:00Z",
          updated_at: "2026-05-14T00:00:00Z",
          error: null,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    compressedNodeId = useWorkspaceStore.getState().appendNode({
      parent_id: "root",
      role: "user",
      content: "node compressed by slash",
      state: "done",
      metadata: {},
      tool_calls: [],
      artifacts: [],
    });
    renderSurface();

    await user.type(screen.getByRole("textbox"), "/compress{Enter}");

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(Object.values(useWorkspaceStore.getState().contextCompressions)[0]).toMatchObject({
      summary: "slash compressed summary",
      status: "ready",
    });
  });

  it("keeps a compression result for its original branch after the active branch changes", async () => {
    const user = userEvent.setup();
    let resolveFetch!: (response: Response) => void;
    const fetchMock = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          resolveFetch = resolve;
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const compressedNodeId = useWorkspaceStore.getState().appendNode({
      parent_id: "root",
      role: "user",
      content: "node that should survive a branch switch",
      state: "done",
      metadata: {},
      tool_calls: [],
      artifacts: [],
    });
    renderSurface();

    await user.click(
      screen.getByRole("button", {
        name: /背景信息窗口：.*点击压缩上下文/,
      }),
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(Object.values(useWorkspaceStore.getState().contextCompressions)[0]).toMatchObject({
      status: "pending",
    });

    act(() => {
      useWorkspaceStore.getState().appendNode({
        parent_id: "root",
        role: "user",
        content: "new active branch",
        state: "done",
        metadata: {},
        tool_calls: [],
        artifacts: [],
      });
    });
    resolveFetch(
      new Response(
        JSON.stringify({
          status: "ok",
          cache_status: "recomputed",
          summary: "compressed after branch switch",
          coverage_node_ids: [compressedNodeId],
          coverage_path_hash: "b".repeat(64),
          last_covered_node_id: compressedNodeId,
          summary_schema_version: "workspace-context-summary-v1",
          compression_prompt_version: "workspace-context-compression-v1",
          compressor_provider: "deepseek-flash",
          compressor_model: "deepseek-v4-flash",
          estimated_original_tokens: 12,
          estimated_summary_tokens: 4,
          estimated_uncovered_tokens: 0,
          created_at: "2026-05-14T00:00:00Z",
          updated_at: "2026-05-14T00:00:00Z",
          error: null,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await waitFor(() =>
      expect(
        Object.values(useWorkspaceStore.getState().contextCompressions).some(
          (summary) =>
            summary.summary === "compressed after branch switch" &&
            summary.status === "ready",
        ),
      ).toBe(true),
    );
  });

});
