import { ArrowLeft, ClipboardList, MoreHorizontal, Plus, UsersRound, Wrench } from "lucide-react";
import { Link } from "react-router-dom";
import { useRef, useState } from "react";

import { Badge } from "../../../../components/ui/badge";
import { Button } from "../../../../components/ui/button";
import { statusLabel } from "../../../../lib/labels";
import { useOutsideClick } from "../../../agents/hooks/useOutsideClick";
import type { Team, TeamAgent, TeamTask } from "../../../tasks/api";

import { TeamTaskBoard } from "./TeamTaskBoard";
import { DesktopTeamViewSwitch, type TeamWorkspaceView } from "./DesktopTeamViewSwitch";
import type { TextFn } from "./types";

function goalTone(status: string) {
  switch (status) {
    case "active":
      return "running" as const;
    case "paused":
      return "warning" as const;
    case "completed":
      return "success" as const;
    case "blocked":
    case "failed":
      return "failed" as const;
    default:
      return "neutral" as const;
  }
}

function goalStatusLabel(status: string, text: TextFn) {
  if (status === "active") return text("执行中", "Active");
  if (status === "paused") return text("已暂停", "Paused");
  if (status === "completed") return text("已完成", "Completed");
  if (status === "blocked") return text("受阻", "Blocked");
  if (status === "failed") return text("失败", "Failed");
  return status;
}

export function TeamHeader({
  activeTeam,
  agents,
  orderedAgents,
  tasks,
  openTaskCount,
  taskBoardOpen,
  text,
  onAddMember,
  onToggleTaskBoard,
  onCloseTaskBoard,
  onPauseGoal,
  onResumeGoal,
  onEditGoal,
  workspaceView,
  onWorkspaceViewChange,
}: {
  activeTeam: Team;
  agents: TeamAgent[];
  orderedAgents: TeamAgent[];
  tasks: TeamTask[];
  openTaskCount: number;
  taskBoardOpen: boolean;
  text: TextFn;
  onAddMember: () => void;
  onToggleTaskBoard: () => void;
  onCloseTaskBoard: () => void;
  onPauseGoal: () => void;
  onResumeGoal: () => void;
  onEditGoal: () => void;
  workspaceView?: TeamWorkspaceView;
  onWorkspaceViewChange?: (view: TeamWorkspaceView) => void;
}) {
  const [moreOpen, setMoreOpen] = useState(false);
  const moreMenuRef = useRef<HTMLDivElement | null>(null);
  useOutsideClick(moreMenuRef, () => setMoreOpen(false), moreOpen);
  const compactGoal = Boolean(workspaceView && workspaceView !== "columns");
  const goalOpenTaskCount = Number(activeTeam.active_goal?.progress_json.open_task_count ?? 0);
  const goalCompletedTaskCount = Number(activeTeam.active_goal?.progress_json.completed_task_count ?? 0);
  const workspaceModeLabel = activeTeam.workspace_mode === "shared"
    ? text("共享工作区", "Shared workspace")
    : text("独立工作区", "Isolated workspace");

  return (
    <header className="relative z-30 shrink-0 border-b border-slate-200 bg-white/95 px-3 py-2 backdrop-blur sm:px-4">
      <div className="flex min-w-0 items-center gap-2">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <Link
            to="/teams"
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
            aria-label={text("返回团队列表", "Back to teams")}
            title={text("返回团队列表", "Back to teams")}
          >
            <ArrowLeft aria-hidden="true" className="h-4 w-4" />
          </Link>
          <div className="min-w-0">
            <span className="inline-flex min-w-0 items-center gap-1.5 text-sm font-semibold text-slate-900">
              <UsersRound aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-500" />
              <span className="truncate" title={activeTeam.name}>{activeTeam.name}</span>
              <Badge tone={activeTeam.status === "ACTIVE" ? "success" : "neutral"}>
                {statusLabel(activeTeam.status)}
              </Badge>
            </span>
            <div className="hidden text-[11px] leading-4 text-slate-500 sm:block">
              {text("团队模式工作台", "Team Mode workspace")}
              <span className="mx-1 text-slate-300">·</span>
              {workspaceModeLabel}
              <span className="mx-1 text-slate-300">·</span>
              {agents.length} {text("名成员", "members")}
            </div>
          </div>
        </div>

        <div className="flex min-w-0 shrink-0 items-center justify-end gap-1.5">
          {workspaceView && onWorkspaceViewChange ? (
            <DesktopTeamViewSwitch value={workspaceView} text={text} onChange={onWorkspaceViewChange} />
          ) : null}
          {activeTeam.active_goal ? (
            <div className="hidden min-w-0 max-w-[14rem] items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] text-slate-700 xl:flex">
              <Badge className="shrink-0 whitespace-nowrap" tone={goalTone(activeTeam.active_goal.status)}>
                {goalStatusLabel(activeTeam.active_goal.status, text)}
              </Badge>
              <span className="max-w-[14rem] truncate font-medium">
                {activeTeam.active_goal.objective}
              </span>
              <Badge className="shrink-0 whitespace-nowrap" tone="info">
                {goalCompletedTaskCount}/{goalCompletedTaskCount + goalOpenTaskCount}
              </Badge>
              {!compactGoal ? (
                <>
                  <span className="text-slate-500">
                    {text("当前目标", "Current goal")}
                  </span>
                </>
              ) : null}
            </div>
          ) : null}
          <span
            className="hidden h-8 max-w-32 items-center gap-1.5 rounded-md px-2 text-xs font-medium text-slate-700 2xl:inline-flex"
            aria-label={text(
              `团队工具: ${activeTeam.team_tools.length} 个可用`,
              `Team tools: ${activeTeam.team_tools.length} available`,
            )}
            title={activeTeam.team_tools.join(", ")}
          >
            <Wrench aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-slate-500" />
            <span className="min-w-0 truncate">
              {activeTeam.team_tools[0] ?? text("无工具", "No tools")}
              {activeTeam.team_tools.length > 1 ? ` +${activeTeam.team_tools.length - 1}` : ""}
            </span>
          </span>
          <Button
            type="button"
            variant="ghost"
            onClick={onAddMember}
            aria-label={text("添加成员", "Add member")}
            title={text("添加成员", "Add member")}
            className="hidden h-8 px-2"
          >
            <Plus aria-hidden="true" className="h-3.5 w-3.5" />
            <span className="hidden lg:inline">{text("添加成员", "Add member")}</span>
          </Button>
          <div className="relative">
            <Button
              type="button"
              variant={taskBoardOpen ? "secondary" : "ghost"}
              aria-label={text("任务板", "Task board")}
              aria-expanded={taskBoardOpen}
              onClick={onToggleTaskBoard}
              className="h-8 px-2"
            >
              <ClipboardList aria-hidden="true" className="h-3.5 w-3.5" />
              <span className="hidden lg:inline">{text("任务板", "Tasks")}</span>
              <Badge tone={openTaskCount > 0 ? "info" : "neutral"} className="px-1.5">
                {openTaskCount}
              </Badge>
            </Button>
            {taskBoardOpen ? (
              <TeamTaskBoard
                team={activeTeam}
                agents={orderedAgents}
                tasks={tasks}
                text={text}
                onClose={onCloseTaskBoard}
              />
            ) : null}
          </div>
          <div ref={moreMenuRef} className="relative">
            <Button
              type="button"
              variant={moreOpen ? "secondary" : "ghost"}
              aria-label={text("更多团队操作", "More team actions")}
              aria-expanded={moreOpen}
              title={text("更多团队操作", "More team actions")}
              onClick={() => setMoreOpen((open) => !open)}
              className="h-8 w-8 px-0"
            >
              <MoreHorizontal aria-hidden="true" className="h-4 w-4" />
            </Button>
            {moreOpen ? (
              <div
                role="menu"
                aria-label={text("更多团队操作", "More team actions")}
                className="absolute right-0 top-full z-50 mt-2 w-52 rounded-lg border border-slate-200 bg-white p-1.5 text-left shadow-sm"
              >
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setMoreOpen(false);
                    onAddMember();
                  }}
                  className="flex h-8 w-full items-center gap-2 rounded-md px-2 text-xs text-slate-700 hover:bg-slate-50"
                >
                  <Plus aria-hidden="true" className="h-3.5 w-3.5 text-slate-500" />
                  {text("添加成员", "Add member")}
                </button>
                {activeTeam.active_goal ? (
                  <>
                    <div className="my-1 border-t border-slate-100" />
                    <div
                      role="group"
                      aria-label={text("目标详情", "Goal details")}
                      className="grid grid-cols-3 gap-2 px-2 py-1.5 text-[10px] text-slate-500"
                    >
                      <span>
                        <strong className="block text-xs font-semibold text-slate-800">
                          {Number(activeTeam.active_goal.progress_json.drift_count ?? 0)}
                        </strong>
                        {text("偏差", "Drift")}
                      </span>
                      <span>
                        <strong className="block text-xs font-semibold text-slate-800">
                          {Number(activeTeam.active_goal.progress_json.intervention_count ?? 0)}
                        </strong>
                        {text("纠偏", "Fixes")}
                      </span>
                      <span>
                        <strong className="block text-xs font-semibold text-slate-800">
                          {Number(activeTeam.active_goal.progress_json.budget_remaining ?? 0)}
                        </strong>
                        {text("预算", "Budget")}
                      </span>
                    </div>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setMoreOpen(false);
                        if (activeTeam.active_goal?.status === "paused") onResumeGoal();
                        else onPauseGoal();
                      }}
                      className="flex h-8 w-full items-center justify-between rounded-md px-2 text-xs text-slate-700 hover:bg-slate-50"
                    >
                      <span>{activeTeam.active_goal.status === "paused" ? text("继续目标", "Resume goal") : text("暂停目标", "Pause goal")}</span>
                      <Badge tone={goalTone(activeTeam.active_goal.status)}>{goalStatusLabel(activeTeam.active_goal.status, text)}</Badge>
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setMoreOpen(false);
                        onEditGoal();
                      }}
                      className="flex h-8 w-full items-center gap-2 rounded-md px-2 text-xs text-slate-700 hover:bg-slate-50"
                    >
                      {text("编辑目标", "Edit goal")}
                    </button>
                  </>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </header>
  );
}
