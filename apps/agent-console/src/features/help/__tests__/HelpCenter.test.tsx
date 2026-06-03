import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HelpCenterPage } from "../pages/HelpCenterPage";

function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <HelpCenterPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HelpCenterPage", () => {
  it("loads the help index, searches docs, renders markdown, and records feedback", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/help/index.json") {
        return new Response(
          JSON.stringify({
            categories: ["快速开始", "子智能体"],
            docs: [
              {
                id: "getting-started.quickstart",
                title: "快速开始",
                category: "快速开始",
                path: "/help/getting-started/quickstart.md",
                keywords: ["Docker", "智能体"],
              },
              {
                id: "subagents.specialists",
                title: "专家模板",
                category: "子智能体",
                path: "/help/subagents/specialists.md",
                keywords: ["专家", "契约", "清单"],
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (path === "/help/getting-started/quickstart.md") {
        return new Response("# 快速开始\n\n使用 Docker 启动智能体控制台，并从工作区运行第一条智能体任务。", { status: 200 });
      }
      if (path === "/help/subagents/specialists.md") {
        return new Response("# 专家模板\n\n专家是带有契约、清单、输出 schema 和预算的子智能体模板。", { status: 200 });
      }
      return new Response("missing", { status: 404 });
    });

    renderPage(fetchMock);

    expect(await screen.findByRole("heading", { name: "快速开始" })).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText("搜索 专家、清单、留存..."), "专家");
    await user.click(await screen.findByRole("button", { name: "专家模板" }));
    expect(await screen.findByRole("heading", { name: "专家模板" })).toBeInTheDocument();
    expect(screen.getByText(/子智能体模板/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "有帮助" }));
    expect(screen.getByRole("button", { name: /有帮助/ })).toHaveClass("bg-slate-900");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/help/subagents/specialists.md"));
  });
});
