import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { useConsoleStore } from "../../stores/consoleStore";
import { ConsoleShell } from "../ConsoleShell";

describe("ConsoleShell", () => {
  it("embeds the workspace route inside the normal console frame", () => {
    useConsoleStore.getState().setLocale("en-US");

    render(
      <MemoryRouter initialEntries={["/agents/default/workspace"]}>
        <ConsoleShell title="智能体工作台">
          <div>工作台内容</div>
        </ConsoleShell>
      </MemoryRouter>,
    );

    expect(screen.getByText("工作台内容")).toBeInTheDocument();
    expect(screen.getByText("控制台")).toBeInTheDocument();
    expect(screen.getByText("智能体工作台")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Language|语言/ })).not.toBeInTheDocument();
    const sidebarToggle = screen.getByLabelText("侧边栏已收起");
    expect(sidebarToggle).toBeInTheDocument();
    expect(sidebarToggle).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByLabelText("搜索")).toBeInTheDocument();
  });

  it("shows the knowledge base navigation item", () => {
    render(
      <MemoryRouter initialEntries={["/knowledge"]}>
        <ConsoleShell title="知识库">
          <div>知识库内容</div>
        </ConsoleShell>
      </MemoryRouter>,
    );

    expect(screen.getByText("知识库内容")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "知识库" })).toHaveAttribute("href", "/knowledge");
  });
});
