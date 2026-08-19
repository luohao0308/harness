import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AttentionCenterPage } from "../AttentionCenterPage";
import {
  approveToolApproval,
  getDesktopAttention,
  rejectToolApproval,
} from "../../../tasks/api";

vi.mock("../../../tasks/api", () => ({
  approveToolApproval: vi.fn(),
  getDesktopAttention: vi.fn(),
  rejectToolApproval: vi.fn(),
}));

const serverAttention = {
  items: [
    {
      id: "approval:approval-1",
      category: "approvals" as const,
      kind: "tool_approval" as const,
      severity: "critical" as const,
      title: "部署任务",
      description: "命令需要审批",
      status: "PENDING",
      occurred_at: "2026-08-17T10:00:00Z",
      target_path: "/runs/run-1",
      task_id: "run-1",
      team_id: null,
      approval_id: "approval-1",
      tool_name: "run_shell",
      risk_level: "high",
      actions: ["approve", "reject", "open"] as const,
    },
    {
      id: "run:run-2",
      category: "runs" as const,
      kind: "run_failed" as const,
      severity: "critical" as const,
      title: "索引任务",
      description: "运行失败，需要检查",
      status: "FAILED",
      occurred_at: "2026-08-17T09:00:00Z",
      target_path: "/runs/run-2",
      task_id: "run-2",
      team_id: null,
      approval_id: null,
      tool_name: null,
      risk_level: null,
      actions: ["open"] as const,
    },
    {
      id: "team:team-1:goal-1",
      category: "teams" as const,
      kind: "team_goal_blocked" as const,
      severity: "critical" as const,
      title: "发布团队",
      description: "目标被阻塞",
      status: "blocked",
      occurred_at: "2026-08-17T08:00:00Z",
      target_path: "/teams/team-1",
      task_id: null,
      team_id: "team-1",
      approval_id: null,
      tool_name: null,
      risk_level: null,
      actions: ["open"] as const,
    },
  ],
  counts: { total: 3, approvals: 1, runs: 1, teams: 1 },
  generated_at: "2026-08-17T10:01:00Z",
  truncated: false,
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/attention"]}>
      <QueryClientProvider client={queryClient}>
        <AttentionCenterPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.mocked(getDesktopAttention).mockResolvedValue(serverAttention);
  vi.mocked(approveToolApproval).mockResolvedValue({ items: [], next_cursor: null });
  vi.mocked(rejectToolApproval).mockResolvedValue({ items: [], next_cursor: null });
  delete window.desktopApi;
});

afterEach(() => {
  delete window.desktopApi;
  vi.clearAllMocks();
});

describe("AttentionCenterPage", () => {
  it("renders mixed server categories and remains usable in a browser", async () => {
    renderPage();

    expect(screen.getByRole("heading", { name: "待处理" })).toBeInTheDocument();
    expect(await screen.findByText("部署任务")).toBeInTheDocument();
    expect(screen.getByText("索引任务")).toBeInTheDocument();
    expect(screen.getByText("发布团队")).toBeInTheDocument();
    expect(screen.queryByText(/桌面本地状态不可用/)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "运行 1" }));
    expect(screen.queryByText("部署任务")).not.toBeInTheDocument();
    expect(screen.getByText("索引任务")).toBeInTheDocument();
  });

  it("approves and rejects from the queue, then refreshes the projection", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("部署任务");
    await user.click(screen.getByRole("button", { name: "批准部署任务" }));
    await waitFor(() => {
      expect(approveToolApproval).toHaveBeenCalledWith("run-1", "approval-1", "通过统一待处理中心批准");
      expect(getDesktopAttention).toHaveBeenCalledTimes(2);
    });

    await user.click(screen.getByRole("button", { name: "拒绝部署任务" }));
    await waitFor(() => {
      expect(rejectToolApproval).toHaveBeenCalledWith("run-1", "approval-1", "通过统一待处理中心拒绝");
    });
  });

  it("merges local conflicts and keeps server items when a local source fails", async () => {
    const runNow = vi.fn().mockResolvedValue({ state: "idle", conflictCount: 0 });
    window.desktopApi = {
      sync: {
        getStatus: vi.fn().mockResolvedValue({
          state: "error",
          online: true,
          lastError: "sync unavailable",
          conflictCount: 1,
        }),
        getConflicts: vi.fn().mockResolvedValue({
          tasks: [{ id: "local-task", title: "本地任务", conflict_detected: true }],
          serverConflicts: [],
        }),
        runNow,
      },
      localRuntime: {
        getModelStatus: vi.fn().mockRejectedValue(new Error("runtime unavailable")),
      },
    };
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("本地任务")).toBeInTheDocument();
    expect(screen.getByText("本地 Runtime 状态读取失败")).toBeInTheDocument();
    expect(screen.getByText("部署任务")).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "立即同步" })[0]);
    await waitFor(() => expect(runNow).toHaveBeenCalledOnce());
  });
});
