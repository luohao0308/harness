import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useConsoleStore } from "../../stores/consoleStore";
import { ConsoleShell } from "../ConsoleShell";

function renderShell(path: string, title: string, content: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      new Response(JSON.stringify({ items: [], next_cursor: null }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={queryClient}>
        <ConsoleShell title={title}>
          <div>{content}</div>
        </ConsoleShell>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ConsoleShell", () => {
  it("embeds the workspace route inside the normal console frame", () => {
    useConsoleStore.getState().setLocale("en-US");

    renderShell("/agents/default/workspace", "智能体工作台", "工作台内容");

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
    renderShell("/knowledge", "知识库", "知识库内容");

    expect(screen.getByText("知识库内容")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "知识库" })).toHaveAttribute("href", "/knowledge");
  });
});
