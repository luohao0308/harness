/**
 * Feature: agent-workspace-chat-v4-refine, render-level regression for
 * React error #310 ("rendered more hooks than during the previous render").
 *
 * The bug shipped in the first v4 build placed `useMemo(groupByRole)`
 * **after** the early `return` for the empty-active-path welcome branch,
 * so the second render (path length 0 → ≥1) added an extra hook and
 * React crashed the whole tree.
 *
 * This test locks the hook order by rendering the component twice against
 * the same root with changing `activePath`, and asserts no console.error
 * escapes (React logs error #310 at `console.error` before throwing).
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import { ChatMessageList } from "../components/ChatMessageList";
import type { ConversationNode } from "../../../stores/workspaceStore";
import type { ChatMessageListProps } from "../components/ChatMessageList";

function makeNode(partial: Partial<ConversationNode> & Pick<ConversationNode, "id" | "role">): ConversationNode {
  return {
    parent_id: null,
    children_ids: [],
    content: "",
    state: "done",
    metadata: {},
    tool_calls: [],
    artifacts: [],
    created_at: "2026-01-01T00:00:00.000Z",
    ...partial,
  };
}

function buildProps(activePath: ConversationNode[]): ChatMessageListProps {
  return {
    activePath,
    agentName: "Test Agent",
    modelLabel: "test-model",
    onPickExamplePrompt: () => {},
    onRetry: () => {},
    onOpenInspector: () => {},
    activeRunId: null,
    editingNodeId: null,
    onStartEdit: () => {},
    onCancelEdit: () => {},
    onSaveEdit: () => {},
    onCopy: async () => true,
    onRegenerate: () => {},
    isStreaming: false,
  };
}

describe("ChatMessageList render regression (React error #310)", () => {
  let container: HTMLDivElement;
  let root: Root;
  let errorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("renders empty → non-empty without hook-order errors", async () => {
    // First render: empty activePath → welcome-state branch.
    await act(async () => {
      root.render(<ChatMessageList {...buildProps([])} />);
    });

    // Guard: the welcome branch must mount cleanly.
    expect(errorSpy).not.toHaveBeenCalled();
    expect(container.textContent ?? "").toContain("Test Agent");

    // Second render: one node arrives → message-list branch. This is the
    // transition that previously blew up with "rendered more hooks than
    // during the previous render".
    const firstUserMessage = makeNode({
      id: "u1",
      role: "user",
      content: "hello",
    });
    await act(async () => {
      root.render(<ChatMessageList {...buildProps([firstUserMessage])} />);
    });

    // No react-dom warnings / errors allowed in this transition.
    const errors = errorSpy.mock.calls.map((call) => String(call[0] ?? ""));
    for (const msg of errors) {
      expect(msg).not.toMatch(/rendered more hooks/i);
      expect(msg).not.toMatch(/Minified React error #310/i);
      expect(msg).not.toMatch(/Should have a queue/i);
    }
    expect(container.textContent ?? "").toContain("hello");

    await act(async () => {
      root.unmount();
    });
    container.remove();
    errorSpy.mockRestore();
  });

  it("renders non-empty → empty without hook-order errors", async () => {
    const firstUserMessage = makeNode({
      id: "u1",
      role: "user",
      content: "hi",
    });
    await act(async () => {
      root.render(<ChatMessageList {...buildProps([firstUserMessage])} />);
    });
    expect(errorSpy).not.toHaveBeenCalled();

    // Drop all messages — flip back to welcome branch.
    await act(async () => {
      root.render(<ChatMessageList {...buildProps([])} />);
    });

    const errors = errorSpy.mock.calls.map((call) => String(call[0] ?? ""));
    for (const msg of errors) {
      expect(msg).not.toMatch(/rendered more hooks/i);
      expect(msg).not.toMatch(/Minified React error #310/i);
    }

    await act(async () => {
      root.unmount();
    });
    container.remove();
    errorSpy.mockRestore();
  });

  it("renders streaming deltas on assistant node without hook-order errors", async () => {
    const userNode = makeNode({ id: "u1", role: "user", content: "hi" });
    const assistantNode = makeNode({
      id: "a1",
      role: "assistant",
      state: "streaming",
      content: "",
    });

    await act(async () => {
      root.render(<ChatMessageList {...buildProps([userNode, assistantNode])} />);
    });

    // Simulate streaming delta arrivals.
    for (const next of ["h", "he", "hel", "hell", "hello"]) {
      await act(async () => {
        root.render(
          <ChatMessageList
            {...buildProps([userNode, { ...assistantNode, content: next }])}
          />,
        );
      });
    }

    const errors = errorSpy.mock.calls.map((call) => String(call[0] ?? ""));
    for (const msg of errors) {
      expect(msg).not.toMatch(/rendered more hooks/i);
      expect(msg).not.toMatch(/Minified React error #310/i);
    }

    await act(async () => {
      root.unmount();
    });
    container.remove();
    errorSpy.mockRestore();
  });

  it("renders assistant knowledge grounding metadata as a visible indicator", async () => {
    const userNode = makeNode({ id: "u1", role: "user", content: "what is the fact?" });
    const assistantNode = makeNode({
      id: "a1",
      role: "assistant",
      content: "Grounded answer [1]",
      metadata: { knowledge_grounding: "Local knowledge grounded the answer." },
    });

    await act(async () => {
      root.render(<ChatMessageList {...buildProps([userNode, assistantNode])} />);
    });

    expect(container.textContent ?? "").toContain("Local knowledge grounded the answer.");

    await act(async () => {
      root.unmount();
    });
    container.remove();
    errorSpy.mockRestore();
  });

  it("renders token metadata with Chinese labels", async () => {
    const assistantNode = makeNode({
      id: "a1",
      role: "assistant",
      content: "Token accounting",
      metadata: {
        input_tokens: 12,
        output_tokens: 34,
        cost_usd: "0.01",
        duration_ms: 56,
      },
    });

    await act(async () => {
      root.render(<ChatMessageList {...buildProps([assistantNode])} />);
    });

    const text = container.textContent ?? "";
    expect(text).toContain("12 输入");
    expect(text).toContain("34 输出");
    expect(text).not.toContain("12 in");
    expect(text).not.toContain("34 out");

    await act(async () => {
      root.unmount();
    });
    container.remove();
    errorSpy.mockRestore();
  });

  it("renders local Agent input and output metadata as a visible I/O panel", async () => {
    const assistantNode = makeNode({
      id: "a1",
      role: "assistant",
      content: "检查完成。",
      metadata: {
        orchestration: {
          source: "local_agent",
          local_agent_io: {
            input: {
              adapter_kind: "hao",
              binding_id: "binding-hao-1234567890",
              agent_session_id: "session-hao-1234567890",
              model_provider: "deepseek",
              model_name: "deepseek-v4",
              message: "请检查本地项目",
              conversation_context_count: 2,
              tool_mentions: [{ name: "read_file" }],
              attachments: [{ name: "README.md" }],
            },
            output: {
              bridge_task_id: "bridge-task-hao-1234567890",
              model_call_id: "model-call-hao-1234567890",
              content_preview: "检查完成。",
              prompt_tokens: 41,
              completion_tokens: 9,
              total_tokens: 50,
              duration_ms: 12,
            },
          },
        },
      },
    });

    await act(async () => {
      root.render(<ChatMessageList {...buildProps([assistantNode])} />);
    });

    const text = container.textContent ?? "";
    expect(text).toContain("本地 Agent I/O");
    expect(text).toContain("hao");
    expect(text).toContain("deepseek/deepseek-v4");
    expect(text).toContain("2 条");
    expect(text).toContain("read_file");
    expect(text).toContain("README.md");
    expect(text).toContain("输入 41");
    expect(text).toContain("输出 9");
    expect(text).toContain("总计 50");
    expect(text).toContain("请检查本地项目");
    expect(text).toContain("检查完成。");

    await act(async () => {
      root.unmount();
    });
    container.remove();
    errorSpy.mockRestore();
  });
});
