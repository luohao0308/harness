import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useWorkspaceStore } from "../../../stores/workspaceStore";
import { useChatStream } from "../hooks/useChatStream";

function sseFrame(event: string, payload: Record<string, unknown>): string {
  return `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`;
}

function streamResponse(frames: string): Response {
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(frames));
        controller.close();
      },
    }),
    {
      status: 200,
      headers: { "content-type": "text/event-stream" },
    },
  );
}

function hangingStreamResponse(frames: string): Response {
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(frames));
      },
      cancel() {
        return undefined;
      },
    }),
    {
      status: 200,
      headers: { "content-type": "text/event-stream" },
    },
  );
}

function neverSettlingStreamResponse(): Response {
  return new Response(
    new ReadableStream({
      start() {
        return undefined;
      },
      cancel() {
        return undefined;
      },
    }),
    {
      status: 200,
      headers: { "content-type": "text/event-stream" },
    },
  );
}

describe("useChatStream run lifecycle callbacks", () => {
  beforeEach(() => {
    useWorkspaceStore.getState().reset();
  });

  it("invokes onRunCreated once for a stream that emits run_created and done", async () => {
    const onRunCreated = vi.fn();
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      streamResponse(
        [
          sseFrame("run_created", {
            run_id: "run-once",
            status: "RUNNING",
            step_count: 0,
            message: "started",
          }),
          sseFrame("delta", { content: "hello" }),
          sseFrame("done", {
            run_id: "run-once",
            active_branch_id: "branch",
            status: "COMPLETED",
            step_count: 0,
            message: "done",
            knowledge_grounding: "Local knowledge grounded the answer.",
          }),
        ].join(""),
      ),
    );

    const { result } = renderHook(() =>
      useChatStream({
        agentId: "default",
        workspaceMode: "chat",
        selectedProviderId: "deepseek-flash",
        selectedModelId: "deepseek-v4-flash",
        onRunCreated,
        fetchImpl: fetchMock as unknown as typeof fetch,
      }),
    );

    await act(async () => {
      await result.current.start({
        goal: "hello",
        mode: "chat",
        attachmentNames: ["reference.png"],
      });
    });

    const [, init] = fetchMock.mock.calls[0] ?? [];
    const payload = JSON.parse(String(init?.body));
    expect(payload.model_provider).toBe("deepseek-flash");
    expect(payload.model_name).toBe("deepseek-v4-flash");
    expect(payload.attachment_names).toEqual(["reference.png"]);
    expect(onRunCreated).toHaveBeenCalledTimes(1);
    expect(onRunCreated).toHaveBeenCalledWith("run-once");
    const assistantNode = Object.values(useWorkspaceStore.getState().nodesById).find(
      (node) => node.role === "assistant",
    );
    expect(assistantNode?.metadata.knowledge_grounding).toBe(
      "Local knowledge grounded the answer.",
    );
  });

  it("clears active streaming as soon as a done event arrives even if the HTTP stream stays open", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      hangingStreamResponse(
        [
          sseFrame("run_created", {
            run_id: "run-terminal-open",
            status: "RUNNING",
            step_count: 0,
            message: "started",
          }),
          sseFrame("delta", { content: "finished text" }),
          sseFrame("done", {
            run_id: "run-terminal-open",
            active_branch_id: "branch",
            status: "COMPLETED",
            step_count: 0,
            message: "done",
          }),
        ].join(""),
      ),
    );

    const { result } = renderHook(() =>
      useChatStream({
        agentId: "default",
        workspaceMode: "chat",
        fetchImpl: fetchMock as unknown as typeof fetch,
      }),
    );

    await act(async () => {
      void result.current.start({ goal: "hello", mode: "chat" });
    });

    await waitFor(() => {
      expect(useWorkspaceStore.getState().activeStream).toBeNull();
    });
    const assistantNode = Object.values(useWorkspaceStore.getState().nodesById).find(
      (node) => node.role === "assistant",
    );
    expect(assistantNode?.content).toBe("finished text");
    expect(assistantNode?.state).toBe("done");
  });

  it("stores server-emitted model auth errors as model configuration failures", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      streamResponse(
        [
          sseFrame("run_created", {
            run_id: "run-model-auth",
            status: "RUNNING",
            step_count: 0,
            message: "started",
          }),
          sseFrame("error", {
            kind: "model_auth",
            message:
              'upstream model gateway returned HTTP 401: {"error":{"message":"Authentication Fails, Your api key: ****9b48 is invalid"}}',
            recoverable: true,
            run_id: "run-model-auth",
          }),
        ].join(""),
      ),
    );

    const { result } = renderHook(() =>
      useChatStream({
        agentId: "default",
        workspaceMode: "chat",
        fetchImpl: fetchMock as unknown as typeof fetch,
      }),
    );

    await act(async () => {
      await result.current.start({ goal: "hello", mode: "chat" });
    });

    const assistantNode = Object.values(useWorkspaceStore.getState().nodesById).find(
      (node) => node.role === "assistant",
    );
    expect(assistantNode?.state).toBe("error");
    expect(assistantNode?.run_id).toBe("run-model-auth");
    expect(assistantNode?.metadata.error?.kind).toBe("model_auth");
    expect(assistantNode?.metadata.error?.detail).toContain("****9b48");
  });

  it("classifies legacy server error events with upstream 401 key detail as model auth failures", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      streamResponse(
        [
          sseFrame("run_created", {
            run_id: "run-legacy-model-auth",
            status: "RUNNING",
            step_count: 0,
            message: "started",
          }),
          sseFrame("error", {
            message:
              'upstream model gateway returned HTTP 401: {"error":{"message":"Authentication Fails, Your api key: ****9b48 is invalid"}}',
            recoverable: true,
            run_id: "run-legacy-model-auth",
          }),
        ].join(""),
      ),
    );

    const { result } = renderHook(() =>
      useChatStream({
        agentId: "default",
        workspaceMode: "chat",
        fetchImpl: fetchMock as unknown as typeof fetch,
      }),
    );

    await act(async () => {
      await result.current.start({ goal: "hello", mode: "chat" });
    });

    const assistantNode = Object.values(useWorkspaceStore.getState().nodesById).find(
      (node) => node.role === "assistant",
    );
    expect(assistantNode?.state).toBe("error");
    expect(assistantNode?.run_id).toBe("run-legacy-model-auth");
    expect(assistantNode?.metadata.error?.kind).toBe("model_auth");
  });

  it("stores goal pursuit model auth failures as model configuration errors", async () => {
    const detail =
      'upstream model gateway returned HTTP 401: {"error":{"message":"Authentication Fails, Your api key: ****9b48 is invalid"}}';
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      streamResponse(
        [
          sseFrame("run_created", {
            run_id: "run-goal-model-auth",
            status: "RUNNING",
            step_count: 0,
            message: "started",
          }),
          sseFrame("goal_progress", {
            run_id: "run-goal-model-auth",
            goal: "持续完成目标",
            status: "failed",
            phase: "failed",
            turn: 1,
            step_count: 0,
            message: `目标暂未达成：${detail}`,
            started_at: new Date().toISOString(),
            elapsed_ms: 1250,
          }),
          sseFrame("error", {
            kind: "model_auth",
            message: detail,
            recoverable: true,
            run_id: "run-goal-model-auth",
          }),
        ].join(""),
      ),
    );

    const { result } = renderHook(() =>
      useChatStream({
        agentId: "default",
        workspaceMode: "goal",
        fetchImpl: fetchMock as unknown as typeof fetch,
      }),
    );

    await act(async () => {
      await result.current.start({ goal: "持续完成目标", mode: "goal" });
    });

    const assistantNode = Object.values(useWorkspaceStore.getState().nodesById).find(
      (node) => node.role === "assistant",
    );
    expect(assistantNode?.state).toBe("error");
    expect(assistantNode?.metadata.workspace_mode).toBe("goal");
    expect(assistantNode?.metadata.goal_status).toBe("failed");
    expect(assistantNode?.metadata.goal_message).toBe(detail);
    expect(assistantNode?.metadata.error?.kind).toBe("model_auth");
    expect(assistantNode?.metadata.error?.detail).toBe(detail);
  });

  it("removes an empty assistant placeholder when the user stops before content arrives", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      neverSettlingStreamResponse(),
    );

    const { result } = renderHook(() =>
      useChatStream({
        agentId: "default",
        workspaceMode: "chat",
        fetchImpl: fetchMock as unknown as typeof fetch,
      }),
    );

    await act(async () => {
      void result.current.start({ goal: "hello", mode: "chat" });
    });

    await waitFor(() => {
      expect(useWorkspaceStore.getState().activeStream).not.toBeNull();
    });

    act(() => {
      result.current.pause();
    });

    await waitFor(() => {
      expect(useWorkspaceStore.getState().activeStream).toBeNull();
    });
    const nodes = Object.values(useWorkspaceStore.getState().nodesById);
    expect(nodes.filter((node) => node.role === "assistant")).toHaveLength(0);
    const userNode = nodes.find((node) => node.role === "user");
    expect(userNode?.content).toBe("hello");
    expect(useWorkspaceStore.getState().activeLeafId).toBe(userNode?.id);
  });

  it("keeps an empty goal assistant node when the user pauses goal pursuit", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      hangingStreamResponse(
        [
          sseFrame("run_created", {
            run_id: "run-empty-goal-pause",
            status: "RUNNING",
            step_count: 0,
            message: "goal started",
          }),
          sseFrame("goal_progress", {
            run_id: "run-empty-goal-pause",
            goal: "持续追踪空内容目标",
            status: "running",
            phase: "executing",
            turn: 1,
            step_count: 1,
            message: "目标仍在推进。",
            started_at: new Date().toISOString(),
            elapsed_ms: 0,
          }),
        ].join(""),
      ),
    );

    const { result } = renderHook(() =>
      useChatStream({
        agentId: "default",
        workspaceMode: "goal",
        fetchImpl: fetchMock as unknown as typeof fetch,
      }),
    );

    await act(async () => {
      void result.current.start({ goal: "持续追踪空内容目标", mode: "goal" });
    });

    await waitFor(() => {
      const assistantNode = Object.values(useWorkspaceStore.getState().nodesById).find(
        (node) => node.role === "assistant",
      );
      expect(assistantNode?.metadata.goal_status).toBe("running");
    });

    act(() => {
      result.current.pause();
    });

    await waitFor(() => {
      const assistantNode = Object.values(useWorkspaceStore.getState().nodesById).find(
        (node) => node.role === "assistant",
      );
      expect(assistantNode?.state).toBe("paused");
      expect(assistantNode?.content).toBe("");
      expect(assistantNode?.metadata.goal_status).toBe("paused");
    });
  });

  it("keeps partial assistant content when the user stops after deltas arrive", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      hangingStreamResponse(sseFrame("delta", { content: "partial answer" })),
    );

    const { result } = renderHook(() =>
      useChatStream({
        agentId: "default",
        workspaceMode: "chat",
        fetchImpl: fetchMock as unknown as typeof fetch,
      }),
    );

    await act(async () => {
      void result.current.start({ goal: "hello", mode: "chat" });
    });

    await waitFor(() => {
      const assistantNode = Object.values(useWorkspaceStore.getState().nodesById).find(
        (node) => node.role === "assistant",
      );
      expect(assistantNode?.content).toBe("partial answer");
    });

    act(() => {
      result.current.pause();
    });

    await waitFor(() => {
      const assistantNode = Object.values(useWorkspaceStore.getState().nodesById).find(
        (node) => node.role === "assistant",
      );
      expect(assistantNode?.state).toBe("paused");
      expect(assistantNode?.content).toBe("partial answer");
    });
  });

  it("sends the full active path and leaves token trimming to the backend", async () => {
    useWorkspaceStore.getState().setContextMaxTokens(1);
    const oldNodeId = useWorkspaceStore.getState().appendNode({
      parent_id: "root",
      role: "user",
      content: "older context that exceeds the tiny UI hint",
      state: "done",
      metadata: {},
      tool_calls: [],
      artifacts: [],
    });
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      streamResponse(
        [
          sseFrame("run_created", {
            run_id: "run-full-path",
            status: "RUNNING",
            step_count: 0,
            message: "started",
          }),
          sseFrame("delta", { content: "ok" }),
          sseFrame("done", {
            run_id: "run-full-path",
            active_branch_id: "branch",
            status: "COMPLETED",
            step_count: 0,
            message: "done",
          }),
        ].join(""),
      ),
    );

    const { result } = renderHook(() =>
      useChatStream({
        agentId: "default",
        workspaceMode: "chat",
        selectedProviderId: "deepseek-flash",
        selectedModelId: "deepseek-v4-flash",
        fetchImpl: fetchMock as unknown as typeof fetch,
      }),
    );

    await act(async () => {
      await result.current.start({ goal: "new prompt", mode: "chat" });
    });

    const [, init] = fetchMock.mock.calls[0] ?? [];
    const payload = JSON.parse(String(init?.body));
    expect(typeof payload.context_max_tokens).toBe("number");
    expect(payload.context_max_tokens).toBeGreaterThan(0);
    expect(payload.messages.map((message: { id: string }) => message.id)).toContain(oldNodeId);
  });

  it("sends compression cache status with compressed context", async () => {
    const store = useWorkspaceStore.getState();
    const coveredNodeId = store.appendNode({
      parent_id: "root",
      role: "user",
      content: "covered context for cache status",
      state: "done",
      metadata: {},
      tool_calls: [],
      artifacts: [],
    });
    const branchKey = `${store.currentConversationId}:${store.activeLeafId}`;
    store.setContextCompression(branchKey, {
      branchKey,
      summary: "cached summary",
      coverageNodeIds: [coveredNodeId],
      coveragePathHash: "hash",
      lastCoveredNodeId: coveredNodeId,
      summarySchemaVersion: "workspace-context-summary-v1",
      compressionPromptVersion: "workspace-context-compression-v1",
      compressorProvider: "deepseek-flash",
      compressorModel: "deepseek-v4-flash",
      estimatedOriginalTokens: 100,
      estimatedSummaryTokens: 20,
      estimatedUncoveredTokens: 0,
      status: "ready",
      cacheStatus: "accepted",
      error: null,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      streamResponse(
        [
          sseFrame("run_created", {
            run_id: "run-cache-status",
            status: "RUNNING",
            step_count: 0,
            message: "started",
          }),
          sseFrame("done", {
            run_id: "run-cache-status",
            active_branch_id: "branch",
            status: "COMPLETED",
            step_count: 0,
            message: "done",
          }),
        ].join(""),
      ),
    );

    const { result } = renderHook(() =>
      useChatStream({
        agentId: "default",
        workspaceMode: "chat",
        selectedProviderId: "deepseek-flash",
        selectedModelId: "deepseek-v4-flash",
        fetchImpl: fetchMock as unknown as typeof fetch,
      }),
    );

    await act(async () => {
      await result.current.start({ goal: "new prompt", mode: "chat" });
    });

    const [, init] = fetchMock.mock.calls[0] ?? [];
    const payload = JSON.parse(String(init?.body));
    expect(payload.compressed_context.cache_status).toBe("accepted");
    expect(payload.compressed_context.estimated_original_tokens).toBe(100);
    expect(payload.compressed_context.estimated_summary_tokens).toBe(20);
  });

  it("routes explicit tool mentions through chat mode instead of markdown planning", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      streamResponse(
        [
          sseFrame("run_created", {
            run_id: "run-tool",
            status: "RUNNING",
            step_count: 0,
            message: "tool started",
          }),
          sseFrame("tool_call_requested", {
            tool_call_id: "tool-1",
            tool_name: "list_files",
            source: "builtin",
            input_json: { root: ".", glob: "**/*" },
            status: "running",
          }),
          sseFrame("tool_call_result", {
            tool_call_id: "tool-1",
            tool_name: "list_files",
            output_json: { files: ["pyproject.toml"] },
            output_summary: "文件列表 1 项",
            status: "success",
          }),
          sseFrame("delta", { content: "已列出工作区文件，共 1 项。" }),
          sseFrame("done", {
            run_id: "run-tool",
            active_branch_id: "branch",
            status: "COMPLETED",
            step_count: 0,
            message: "done",
          }),
        ].join(""),
      ),
    );

    const { result } = renderHook(() =>
      useChatStream({
        agentId: "default",
        workspaceMode: "markdown_plan",
        selectedProviderId: "deepseek-flash",
        selectedModelId: "deepseek-v4-flash",
        fetchImpl: fetchMock as unknown as typeof fetch,
      }),
    );

    await act(async () => {
      await result.current.start({ goal: "@list_files", mode: "markdown_plan" });
    });

    const [, init] = fetchMock.mock.calls[0] ?? [];
    const payload = JSON.parse(String(init?.body));
    expect(payload.mode).toBe("chat");
    expect(payload.tool_mentions).toEqual([
      { name: "list_files", source: "builtin", payload: { mention: "@list_files" } },
    ]);
    const assistantNode = Object.values(useWorkspaceStore.getState().nodesById).find(
      (node) => node.role === "assistant",
    );
    expect(assistantNode?.metadata.workspace_mode).toBe("chat");
    expect(assistantNode?.tool_calls).toHaveLength(1);
  });

  it("sends goal pursuit mode to the backend without downgrading to plan mode", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      streamResponse(
        [
          sseFrame("run_created", {
            run_id: "run-goal",
            status: "RUNNING",
            step_count: 0,
            message: "goal started",
          }),
          sseFrame("goal_progress", {
            run_id: "run-goal",
            goal: "持续完成目标",
            status: "running",
            phase: "started",
            turn: 0,
            step_count: 0,
            message: "进行中的目标已启动。",
            started_at: new Date().toISOString(),
            elapsed_ms: 12,
          }),
          sseFrame("delta", { content: "目标正在推进" }),
          sseFrame("done", {
            run_id: "run-goal",
            active_branch_id: "branch",
            status: "COMPLETED",
            step_count: 0,
            message: "done",
          }),
        ].join(""),
      ),
    );

    const { result } = renderHook(() =>
      useChatStream({
        agentId: "default",
        workspaceMode: "goal",
        fetchImpl: fetchMock as unknown as typeof fetch,
      }),
    );

    await act(async () => {
      await result.current.start({ goal: "持续完成目标", mode: "goal" });
    });

    const [, init] = fetchMock.mock.calls[0] ?? [];
    const payload = JSON.parse(String(init?.body));
    expect(payload.mode).toBe("goal");
    expect(payload.orchestration_mode).toBe("auto");
    const assistantNode = Object.values(useWorkspaceStore.getState().nodesById).find(
      (node) => node.role === "assistant",
    );
    expect(assistantNode?.metadata.workspace_mode).toBe("goal");
    expect(assistantNode?.metadata.goal_status).toBe("completed");
    expect(assistantNode?.metadata.goal_text).toBe("持续完成目标");
    expect(assistantNode?.metadata.goal_phase).toBe("completed");
    expect(assistantNode?.content).toBe("目标正在推进");
  });

  it("keeps a server-paused goal resumable after the stream ends", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      streamResponse(
        [
          sseFrame("run_created", {
            run_id: "run-goal-paused",
            status: "RUNNING",
            step_count: 0,
            message: "goal started",
          }),
          sseFrame("goal_progress", {
            run_id: "run-goal-paused",
            goal: "持续完成目标",
            status: "paused",
            phase: "paused",
            turn: 1,
            step_count: 0,
            message: "目标追踪已暂停，恢复后继续。",
            started_at: new Date().toISOString(),
            elapsed_ms: 1000,
          }),
          sseFrame("done", {
            run_id: "run-goal-paused",
            active_branch_id: "branch",
            status: "PAUSED",
            step_count: 0,
            message: "paused",
          }),
        ].join(""),
      ),
    );

    const { result } = renderHook(() =>
      useChatStream({
        agentId: "default",
        workspaceMode: "goal",
        fetchImpl: fetchMock as unknown as typeof fetch,
      }),
    );

    await act(async () => {
      await result.current.start({ goal: "持续完成目标", mode: "goal" });
    });

    const assistantNode = Object.values(useWorkspaceStore.getState().nodesById).find(
      (node) => node.role === "assistant",
    );
    expect(assistantNode?.state).toBe("paused");
    expect(assistantNode?.run_id).toBe("run-goal-paused");
    expect(assistantNode?.metadata.goal_status).toBe("paused");
  });

  it("automatically resumes a goal when the server pauses only because the per-stream guard was reached", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        streamResponse(
          [
            sseFrame("run_created", {
              run_id: "run-goal-guard-1",
              status: "RUNNING",
              step_count: 0,
              message: "goal started",
            }),
            sseFrame("goal_progress", {
              run_id: "run-goal-guard-1",
              goal: "持续推进目标",
              status: "paused",
              phase: "paused",
              turn: 12,
              step_count: 0,
              message: "目标追踪已暂停：本次持续追踪达到单次推进上限，恢复后继续。",
              started_at: new Date().toISOString(),
              elapsed_ms: 1000,
            }),
            sseFrame("done", {
              run_id: "run-goal-guard-1",
              active_branch_id: "branch",
              status: "PAUSED",
              step_count: 0,
              message: "paused",
            }),
          ].join(""),
        ),
      )
      .mockResolvedValueOnce(
        streamResponse(
          [
            sseFrame("goal_progress", {
              run_id: "run-goal-guard-1",
              goal: "持续推进目标",
              status: "running",
              phase: "running",
              turn: 13,
              step_count: 1,
              message: "目标追踪继续执行中。",
              started_at: new Date().toISOString(),
              elapsed_ms: 1200,
            }),
            sseFrame("done", {
              run_id: "run-goal-guard-1",
              active_branch_id: "branch",
              status: "COMPLETED",
              step_count: 1,
              message: "done",
            }),
          ].join(""),
        ),
      );

    const { result } = renderHook(() =>
      useChatStream({
        agentId: "default",
        workspaceMode: "goal",
        fetchImpl: fetchMock as unknown as typeof fetch,
      }),
    );

    await act(async () => {
      await result.current.start({ goal: "持续推进目标", mode: "goal" });
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const assistantNode = Object.values(useWorkspaceStore.getState().nodesById).find(
      (node) => node.role === "assistant",
    );
    expect(assistantNode?.state).toBe("done");
    expect(assistantNode?.metadata.goal_status).toBe("completed");
    vi.useRealTimers();
  });

  it("marks explicit subagent requests for backend auto orchestration", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      streamResponse(
        [
          sseFrame("run_created", {
            run_id: "run-subagent",
            status: "RUNNING",
            step_count: 0,
            message: "started",
          }),
          sseFrame("orchestration", {
            mode: "subagent",
            run_id: "run-subagent",
            subagent_id: "subagent-1",
          }),
          sseFrame("done", {
            run_id: "run-subagent",
            active_branch_id: "branch",
            status: "COMPLETED",
            step_count: 0,
            message: "done",
          }),
        ].join(""),
      ),
    );

    const { result } = renderHook(() =>
      useChatStream({
        agentId: "default",
        workspaceMode: "chat",
        fetchImpl: fetchMock as unknown as typeof fetch,
      }),
    );

    await act(async () => {
      await result.current.start({ goal: "请调用子 Agent 检查发布清单", mode: "chat" });
    });

    const [, init] = fetchMock.mock.calls[0] ?? [];
    const payload = JSON.parse(String(init?.body));
    expect(payload.orchestration_mode).toBe("auto");
    const assistantNode = Object.values(useWorkspaceStore.getState().nodesById).find(
      (node) => node.role === "assistant",
    );
    expect(assistantNode?.metadata.orchestration).toMatchObject({
      mode: "subagent",
      subagent_id: "subagent-1",
    });
  });

  it("keeps follow-up invocation requests on the subagent orchestration path", async () => {
    useWorkspaceStore.getState().appendNode({
      parent_id: "root",
      role: "user",
      content: "我想让子 Agent 处理这个检查",
      state: "done",
      metadata: {},
      tool_calls: [],
      artifacts: [],
    });
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      streamResponse(
        [
          sseFrame("run_created", {
            run_id: "run-follow-up-subagent",
            status: "RUNNING",
            step_count: 0,
            message: "started",
          }),
          sseFrame("done", {
            run_id: "run-follow-up-subagent",
            active_branch_id: "branch",
            status: "COMPLETED",
            step_count: 0,
            message: "done",
          }),
        ].join(""),
      ),
    );

    const { result } = renderHook(() =>
      useChatStream({
        agentId: "default",
        workspaceMode: "chat",
        fetchImpl: fetchMock as unknown as typeof fetch,
      }),
    );

    await act(async () => {
      await result.current.start({ goal: "你现在调用一下", mode: "chat" });
    });

    const [, init] = fetchMock.mock.calls[0] ?? [];
    const payload = JSON.parse(String(init?.body));
    expect(payload.orchestration_mode).toBe("auto");
  });
});
