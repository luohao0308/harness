import { act, renderHook } from "@testing-library/react";
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
});
