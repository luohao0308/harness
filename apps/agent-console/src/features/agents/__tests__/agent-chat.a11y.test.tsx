/**
 * Accessibility tests for Agent Chat
 *
 * Tests WCAG 2.1 AA compliance using axe-core:
 * - Automated violation detection
 * - Keyboard navigation
 * - ARIA labels and roles
 * - Focus management
 * - Screen reader compatibility
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { describe, test, expect, vi } from "vitest";
import { ChatComposer } from "../components/ChatComposer";
import { ChatMessageBubble } from "../components/ChatMessageBubble";
import type { ConversationNode } from "../../../stores/workspaceStore";

describe("Agent Chat Accessibility", () => {
  describe("ChatComposer", () => {
    const defaultProps = {
      draft: "",
      onDraftChange: vi.fn(),
      onSubmit: vi.fn(),
      onPause: vi.fn(),
      isStreaming: false,
      mode: "chat" as const,
      onChangeMode: vi.fn(),
      placeholder: "Type a message...",
    };

    test("has no axe violations on initial render", async () => {
      const { container } = render(<ChatComposer {...defaultProps} />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    test("has no axe violations with text input", async () => {
      const { container } = render(<ChatComposer {...defaultProps} draft="Hello world" />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    test("has no axe violations when streaming", async () => {
      const { container } = render(<ChatComposer {...defaultProps} isStreaming={true} />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    test("textarea is keyboard accessible", async () => {
      const user = userEvent.setup();
      const onDraftChange = vi.fn();
      render(<ChatComposer {...defaultProps} onDraftChange={onDraftChange} />);

      const textarea = screen.getByPlaceholderText(/Type a message/i);

      await user.click(textarea);
      expect(textarea).toHaveFocus();

      await user.type(textarea, "Hello");
      expect(onDraftChange).toHaveBeenCalled();
    });

    test("submit button is keyboard accessible", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      render(<ChatComposer {...defaultProps} draft="Test message" onSubmit={onSubmit} />);

      const sendButton = screen.getByRole("button", { name: /send|submit|发送/i });
      sendButton.focus();
      expect(sendButton).toHaveFocus();

      await user.keyboard("{Enter}");
      expect(onSubmit).toHaveBeenCalled();
    });

    test("pause button is accessible when streaming", () => {
      render(<ChatComposer {...defaultProps} isStreaming={true} />);

      const pauseButton = screen.getByRole("button", { name: /pause|stop|停止生成/i });
      expect(pauseButton).toBeInTheDocument();
      expect(pauseButton).not.toBeDisabled();
    });

    test("composer maintains focus when typing", async () => {
      const user = userEvent.setup();
      render(<ChatComposer {...defaultProps} />);

      const textarea = screen.getByPlaceholderText(/Type a message/i);
      await user.click(textarea);
      await user.type(textarea, "Test");

      expect(textarea).toHaveFocus();
    });
  });

  describe("ChatMessageBubble", () => {
    const mockNode: ConversationNode = {
      id: "msg-1",
      role: "user",
      content: "Hello, how are you?",
      state: "done",
      parent_id: null,
      children_ids: [],
      metadata: {},
      tool_calls: [],
      artifacts: [],
      created_at: new Date().toISOString(),
    };

    const defaultMessageProps = {
      node: mockNode,
      onOpenInspector: vi.fn(),
      editingNodeId: null,
      onStartEdit: vi.fn(),
      onCancelEdit: vi.fn(),
      onSaveEdit: vi.fn(),
      canRegenerate: false,
      isStreaming: false,
      onCopy: vi.fn(),
      onRegenerate: vi.fn(),
    };

    test("has no axe violations for user message", async () => {
      const { container } = render(<ChatMessageBubble {...defaultMessageProps} />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    test("has no axe violations for assistant message", async () => {
      const assistantNode: ConversationNode = {
        ...mockNode,
        id: "msg-2",
        role: "assistant",
        parent_id: "msg-1",
      };

      const { container } = render(
        <ChatMessageBubble {...defaultMessageProps} node={assistantNode} />,
      );
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    test("message actions are keyboard accessible", async () => {
      const user = userEvent.setup();
      const onCopy = vi.fn().mockResolvedValue(true);
      render(<ChatMessageBubble {...defaultMessageProps} onCopy={onCopy} />);

      // Look for action buttons
      const buttons = screen.getAllByRole("button");

      if (buttons.length > 0) {
        buttons[0].focus();
        expect(buttons[0]).toHaveFocus();
      }
    });

    test("message content is properly exposed to screen readers", () => {
      render(<ChatMessageBubble {...defaultMessageProps} />);

      expect(screen.getByText(/Hello, how are you/i)).toBeInTheDocument();
    });
  });

  describe("Chat Navigation", () => {
    test("composer supports Enter to submit", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      render(
        <ChatComposer
          draft="Test message"
          onDraftChange={vi.fn()}
          onSubmit={onSubmit}
          onPause={vi.fn()}
          isStreaming={false}
          mode="chat"
          onChangeMode={vi.fn()}
          placeholder="Type a message..."
        />,
      );

      const textarea = screen.getByPlaceholderText(/Type a message/i);
      await user.click(textarea);
      await user.keyboard("{Enter}");

      expect(onSubmit).toHaveBeenCalled();
    });

    test("composer supports Shift+Enter for new line", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      const onDraftChange = vi.fn();

      render(
        <ChatComposer
          draft="Test message"
          onDraftChange={onDraftChange}
          onSubmit={onSubmit}
          onPause={vi.fn()}
          isStreaming={false}
          mode="chat"
          onChangeMode={vi.fn()}
          placeholder="Type a message..."
        />,
      );

      const textarea = screen.getByPlaceholderText(/Type a message/i);
      await user.click(textarea);
      await user.keyboard("{Shift>}{Enter}{/Shift}");

      // Should NOT submit on Shift+Enter
      expect(onSubmit).not.toHaveBeenCalled();
    });
  });

  describe("Screen Reader Support", () => {
    test("chat messages have meaningful structure", () => {
      const assistantNode: ConversationNode = {
        id: "msg-1",
        role: "assistant",
        content: "Here is my response",
        state: "done",
        parent_id: null,
        children_ids: [],
        metadata: {},
        tool_calls: [],
        artifacts: [],
        created_at: new Date().toISOString(),
      };

      render(
        <ChatMessageBubble
          node={assistantNode}
          onOpenInspector={vi.fn()}
          editingNodeId={null}
          onStartEdit={vi.fn()}
          onCancelEdit={vi.fn()}
          onSaveEdit={vi.fn()}
          canRegenerate={false}
          isStreaming={false}
          onCopy={vi.fn()}
          onRegenerate={vi.fn()}
        />,
      );

      expect(screen.getByText(/Here is my response/i)).toBeInTheDocument();
    });

    test("composer placeholder provides context", () => {
      render(
        <ChatComposer
          draft=""
          onDraftChange={vi.fn()}
          onSubmit={vi.fn()}
          onPause={vi.fn()}
          isStreaming={false}
          mode="chat"
          onChangeMode={vi.fn()}
          placeholder="Ask me anything..."
        />,
      );

      const textarea = screen.getByPlaceholderText(/Ask me anything/i);
      expect(textarea).toBeInTheDocument();
    });
  });
});
