import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useConsoleStore } from "../../../stores/consoleStore";
import { ConversationHistoryPanel } from "../components/ConversationHistoryPanel";
import type { ConversationSummary } from "../lib/conversationHistory";

function conversation(id: string, title: string, updatedAt: string): ConversationSummary {
  return {
    id,
    title,
    created_at: updatedAt,
    updated_at: updatedAt,
    nodesById: {},
    rootNodeId: "root",
    activeLeafId: "root",
    pinnedNodeIds: [],
    dismissedPlanNodeIds: [],
    draft: "",
    contextWindowTurns: 6,
    contextCompressions: {},
  };
}

describe("ConversationHistoryPanel", () => {
  afterEach(() => {
    delete window.desktopApi;
  });

  it("keeps history controls reachable by accessible name", async () => {
    useConsoleStore.getState().setLocale("en-US");
    const user = userEvent.setup();
    const onNewConversation = vi.fn();
    const onSelectConversation = vi.fn();
    const onDeleteConversation = vi.fn();
    const onToggleCollapsed = vi.fn();

    render(
      <MemoryRouter initialEntries={["/agents/default/workspace"]}>
        <ConversationHistoryPanel
          collapsed={false}
          conversations={[
            conversation("one", "First workspace pass", "2026-05-11T20:00:00Z"),
            conversation("two", "Second workspace pass", "2026-05-11T20:10:00Z"),
          ]}
          currentConversationId="two"
          onNewConversation={onNewConversation}
          onSelectConversation={onSelectConversation}
          onDeleteConversation={onDeleteConversation}
          onToggleCollapsed={onToggleCollapsed}
        />
      </MemoryRouter>,
    );

    await user.click(screen.getByRole("button", { name: "新建对话" }));
    expect(onNewConversation).toHaveBeenCalledTimes(1);

    const active = screen.getByRole("button", { name: "Second workspace pass" });
    expect(active).toHaveAttribute("aria-current", "page");

    await user.click(screen.getByRole("button", { name: "First workspace pass" }));
    expect(onSelectConversation).toHaveBeenCalledWith("one");

    await user.click(screen.getAllByRole("button", { name: "删除对话" })[0]);
    expect(onDeleteConversation).toHaveBeenCalledWith("two");

    await user.click(screen.getByRole("button", { name: "收起历史对话" }));
    expect(onToggleCollapsed).toHaveBeenCalledTimes(1);
  });

  it("adds only the essential task and utility navigation in desktop runtime", () => {
    window.desktopApi = {};

    render(
      <MemoryRouter initialEntries={["/agents/default/workspace"]}>
        <ConversationHistoryPanel
          collapsed={false}
          conversations={[conversation("one", "Inspect repository", "2026-05-11T20:00:00Z")]}
          currentConversationId="one"
          onNewConversation={vi.fn()}
          onSelectConversation={vi.fn()}
          onDeleteConversation={vi.fn()}
          onToggleCollapsed={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("Harness")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "新建任务" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "团队" })).toHaveAttribute("href", "/teams");
    expect(screen.getByRole("link", { name: "终端" })).toHaveAttribute("href", "/terminal");
    expect(screen.getByRole("link", { name: "文件" })).toHaveAttribute(
      "href",
      "/agents/default/workspace?desktop_panel=files",
    );
    expect(screen.getByRole("link", { name: "审批" })).toHaveAttribute(
      "href",
      "/agents/default/workspace?desktop_panel=approvals",
    );
    expect(screen.getByRole("link", { name: "设置" })).toHaveAttribute("href", "/desktop");
    expect(screen.queryByText("Dashboard")).not.toBeInTheDocument();
  });
});
