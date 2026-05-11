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
    const fetchImpl = vi.fn(async () =>
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
          }),
        ].join(""),
      ),
    ) as typeof fetch;

    const { result } = renderHook(() =>
      useChatStream({
        agentId: "default",
        workspaceMode: "chat",
        onRunCreated,
        fetchImpl,
      }),
    );

    await act(async () => {
      await result.current.start({ goal: "hello", mode: "chat" });
    });

    expect(onRunCreated).toHaveBeenCalledTimes(1);
    expect(onRunCreated).toHaveBeenCalledWith("run-once");
  });
});
