import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChangeReviewPage } from "../ChangeReviewPage";

const getStatus = vi.fn();
const getDiff = vi.fn();
const mutate = vi.fn();
const selectWorkspaceRoot = vi.fn();

const readyStatus = {
  state: "ready" as const,
  files: [
    {
      path: "src/app.ts",
      previousPath: null,
      indexStatus: "M",
      worktreeStatus: "M",
      staged: true,
      unstaged: true,
      untracked: false,
      conflicted: false,
    },
    {
      path: "public/logo.png",
      previousPath: null,
      indexStatus: "?",
      worktreeStatus: "?",
      staged: false,
      unstaged: false,
      untracked: true,
      conflicted: false,
    },
  ],
};

const textDiff = {
  path: "src/app.ts",
  previewToken: "preview-1",
  expiresAt: "2026-08-17T12:00:00Z",
  sections: [
    {
      mode: "staged" as const,
      kind: "text" as const,
      headerLines: ["diff --git a/src/app.ts b/src/app.ts"],
      hunks: [
        {
          id: "staged-hunk",
          header: "@@ -1,1 +1,1 @@",
          oldStart: 1,
          oldLines: 1,
          newStart: 1,
          newLines: 1,
          lines: ["-const state = 'old';", "+const state = 'new';"],
        },
      ],
      canStage: false,
      canUnstage: true,
      canRevert: false,
      message: null,
    },
    {
      mode: "worktree" as const,
      kind: "text" as const,
      headerLines: ["diff --git a/src/app.ts b/src/app.ts"],
      hunks: [
        {
          id: "worktree-hunk",
          header: "@@ -4,1 +4,2 @@",
          oldStart: 4,
          oldLines: 1,
          newStart: 4,
          newLines: 2,
          lines: [" const ready = true;", "+const reviewed = true;"],
        },
      ],
      canStage: true,
      canUnstage: false,
      canRevert: true,
      message: null,
    },
  ],
};

function installDesktopApi() {
  (window as unknown as { desktopApi: unknown }).desktopApi = {
    changeReview: { getStatus, getDiff, mutate },
    file: { selectWorkspaceRoot },
  };
}

function renderPage(path = "/changes") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={queryClient}>
        <ChangeReviewPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  getStatus.mockResolvedValue(readyStatus);
  getDiff.mockImplementation(async (path: string) =>
    path === "src/app.ts"
      ? textDiff
      : {
          path,
          previewToken: "preview-binary",
          expiresAt: "2026-08-17T12:00:00Z",
          sections: [
            {
              mode: "worktree",
              kind: "binary",
              headerLines: [],
              hunks: [],
              canStage: true,
              canUnstage: false,
              canRevert: false,
              message: "二进制文件不提供文本预览",
            },
          ],
        },
  );
  mutate.mockResolvedValue({
    action: "stage",
    path: "src/app.ts",
    status: "applied",
    updatedAt: "2026-08-17T11:00:00Z",
    auditId: "audit-1",
    eventId: "event-1",
  });
  selectWorkspaceRoot.mockResolvedValue({ rootPath: "/workspace", watching: true });
  installDesktopApi();
});

afterEach(() => {
  delete (window as unknown as { desktopApi?: unknown }).desktopApi;
  vi.clearAllMocks();
});

describe("ChangeReviewPage", () => {
  it("shows a desktop-only fallback in a browser", () => {
    delete (window as unknown as { desktopApi?: unknown }).desktopApi;
    renderPage();

    expect(screen.getByRole("heading", { name: "本地变更" })).toBeInTheDocument();
    expect(screen.getByText("请在桌面应用中审查本地变更")).toBeInTheDocument();
    expect(getStatus).not.toHaveBeenCalled();
  });

  it("renders a continuous file list and staged plus working tree diffs", async () => {
    renderPage();

    expect(await screen.findByRole("button", { name: /src\/app.ts/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /public\/logo.png/ })).toBeInTheDocument();
    expect(await screen.findByText("已暂存")).toBeInTheDocument();
    expect(screen.getByText("工作区")).toBeInTheDocument();
    expect(screen.getByText("+const reviewed = true;")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /public\/logo.png/ }));
    expect(await screen.findByText("二进制文件不提供文本预览")).toBeInTheDocument();
  });

  it("selects a workspace from the empty state and reloads status", async () => {
    getStatus
      .mockResolvedValueOnce({ state: "no-workspace", files: [] })
      .mockResolvedValueOnce(readyStatus);
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "选择工作区" }));

    await waitFor(() => {
      expect(selectWorkspaceRoot).toHaveBeenCalledTimes(1);
      expect(getStatus).toHaveBeenCalledTimes(2);
    });
    expect(await screen.findByRole("button", { name: /src\/app.ts/ })).toBeInTheDocument();
  });

  it("moves file focus with arrow keys and opens the diff with Enter", async () => {
    const user = userEvent.setup();
    renderPage();
    const first = await screen.findByRole("button", { name: /src\/app.ts/ });
    await waitFor(() => expect(getDiff).toHaveBeenCalledTimes(1));
    first.focus();

    await user.keyboard("{ArrowDown}");

    const second = screen.getByRole("button", { name: /public\/logo.png/ });
    expect(second).toHaveFocus();
    expect(getDiff).toHaveBeenCalledTimes(1);

    await user.keyboard("{Enter}");

    await waitFor(() => expect(getDiff).toHaveBeenLastCalledWith("public/logo.png"));
  });

  it("does not mutate after the confirmation dialog is cancelled", async () => {
    const user = userEvent.setup();
    renderPage();

    const hunk = await screen.findByRole("checkbox", { name: /选择工作区分块/ });
    await user.click(hunk);
    await user.click(screen.getByRole("button", { name: "暂存所选" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "取消" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(mutate).not.toHaveBeenCalled();
  });

  it("requires confirmation, forwards audit context, and refreshes after staging a hunk", async () => {
    const user = userEvent.setup();
    renderPage("/changes?task_id=task-1&run_id=run-1&approval_id=approval-1");

    const hunk = await screen.findByRole("checkbox", { name: /选择工作区分块/ });
    await user.click(hunk);
    await user.click(screen.getByRole("button", { name: "暂存所选" }));

    const dialog = screen.getByRole("dialog", { name: "确认暂存所选分块" });
    expect(within(dialog).getByText(/执行前会再次校验预览/)).toBeInTheDocument();
    expect(mutate).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "确认暂存" }));

    await waitFor(() => {
      expect(mutate).toHaveBeenCalledWith({
        previewToken: "preview-1",
        hunkIds: ["worktree-hunk"],
        action: "stage",
        auditContext: {
          taskId: "task-1",
          runId: "run-1",
          approvalId: "approval-1",
        },
      });
      expect(getStatus).toHaveBeenCalledTimes(2);
      expect(getDiff).toHaveBeenCalledTimes(2);
    });
  });

  it("selects and stages every hunk for an untracked file", async () => {
    const user = userEvent.setup();
    getStatus.mockResolvedValueOnce({
      state: "ready",
      files: [readyStatus.files[1]],
    });
    getDiff.mockResolvedValueOnce({
      path: "public/logo.png",
      previewToken: "preview-untracked",
      expiresAt: "2026-08-17T12:00:00Z",
      sections: [
        {
          mode: "worktree",
          kind: "text",
          headerLines: ["diff --git a/public/logo.png b/public/logo.png"],
          hunks: [
            {
              id: "untracked-hunk-1",
              header: "@@ -0,0 +1,1 @@",
              oldStart: 0,
              oldLines: 0,
              newStart: 1,
              newLines: 1,
              lines: ["+first"],
            },
            {
              id: "untracked-hunk-2",
              header: "@@ -0,0 +3,1 @@",
              oldStart: 0,
              oldLines: 0,
              newStart: 3,
              newLines: 1,
              lines: ["+second"],
            },
          ],
          canStage: true,
          canUnstage: false,
          canRevert: true,
          message: null,
        },
      ],
    });
    renderPage();

    const checkboxes = await screen.findAllByRole("checkbox", { name: /选择工作区分块/ });
    await user.click(checkboxes[0]);

    expect(checkboxes[0]).toBeChecked();
    expect(checkboxes[1]).toBeChecked();
    expect(screen.getAllByText("未跟踪文件将整份暂存")).toHaveLength(2);
    await user.click(screen.getByRole("button", { name: "暂存整文件" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "确认暂存" }));

    await waitFor(() => {
      expect(mutate).toHaveBeenCalledWith({
        previewToken: "preview-untracked",
        hunkIds: ["untracked-hunk-1", "untracked-hunk-2"],
        action: "stage",
      });
    });
  });

  it("shows conflict and repository error states without hiding the file list", async () => {
    getStatus.mockResolvedValueOnce({
      state: "ready",
      files: [
        {
          path: "src/conflicted.ts",
          previousPath: null,
          indexStatus: "U",
          worktreeStatus: "U",
          staged: false,
          unstaged: false,
          untracked: false,
          conflicted: true,
        },
      ],
    });
    getDiff.mockResolvedValueOnce({
      path: "src/conflicted.ts",
      previewToken: "preview-conflict",
      expiresAt: "2026-08-17T12:00:00Z",
      sections: [
        {
          mode: "worktree",
          kind: "conflict",
          headerLines: [],
          hunks: [],
          canStage: false,
          canUnstage: false,
          canRevert: false,
          message: "文件包含未解决冲突",
        },
      ],
    });
    const first = renderPage();
    expect(await screen.findByText("文件包含未解决冲突")).toBeInTheDocument();
    expect(screen.getByText("冲突")).toBeInTheDocument();
    first.unmount();

    getStatus.mockResolvedValueOnce({ state: "not-repository", files: [] });
    renderPage();
    expect(await screen.findByText("当前工作区不是 Git 仓库")).toBeInTheDocument();
  });
});
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
