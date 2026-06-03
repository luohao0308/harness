import { ArrowLeft, ClipboardList, Plus, UsersRound, Wrench } from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "../../../../components/ui/badge";
import { Button } from "../../../../components/ui/button";
import { statusLabel } from "../../../../lib/labels";
import type { Team, TeamAgent, TeamTask } from "../../../tasks/api";

import { TeamTaskBoard } from "./TeamTaskBoard";
import type { TextFn } from "./types";

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
}) {
  return (
    <header className="relative z-30 shrink-0 border-b border-slate-200 bg-white/95 px-3 py-2 backdrop-blur sm:px-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex min-w-[220px] flex-1 items-center gap-2">
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
              <span className="truncate">{activeTeam.name}</span>
              <Badge tone={activeTeam.status === "ACTIVE" ? "success" : "neutral"}>
                {statusLabel(activeTeam.status)}
              </Badge>
            </span>
            <div className="hidden text-[11px] leading-4 text-slate-500 sm:block">
              {text("团队模式工作台", "Team Mode workspace")}
              <span className="mx-1 text-slate-300">·</span>
              {activeTeam.workspace_mode}
              <span className="mx-1 text-slate-300">·</span>
              {agents.length} {text("名成员", "members")}
            </div>
          </div>
        </div>

        <div className="flex min-w-0 flex-wrap items-center justify-end gap-1.5">
          <span
            className="inline-flex h-8 max-w-[12rem] items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2 text-xs font-medium text-slate-700"
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
            className="h-8 px-2"
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
        </div>
      </div>
    </header>
  );
}
