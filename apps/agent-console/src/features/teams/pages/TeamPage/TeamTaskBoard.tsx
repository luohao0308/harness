import { ClipboardList, X } from "lucide-react";

import { Badge } from "../../../../components/ui/badge";
import { cn } from "../../../../lib/utils";
import type { Team, TeamAgent, TeamTask } from "../../../tasks/api";
import { teamTaskStatusLabel, teamTaskStatusTone } from "../../lib/teamLabels";

import type { TextFn } from "./types";

export function TeamTaskBoard({
  team,
  agents,
  tasks,
  text,
  onClose,
}: {
  team: Team;
  agents: TeamAgent[];
  tasks: TeamTask[];
  text: TextFn;
  onClose: () => void;
}) {
  const agentNames = new Map(agents.map((agent) => [agent.slot_id, agent.agent_name]));
  const statuses: TeamTask["status"][] = ["pending", "in_progress", "completed"];
  const visibleTasks = tasks.filter((task) => task.status !== "deleted");

  return (
    <div
      role="dialog"
      aria-label={text("团队任务板", "Team task board")}
      className="absolute right-1 top-full z-40 mt-2 w-[min(360px,calc(100vw-1rem))] overflow-hidden rounded-lg border border-slate-200 bg-white text-left shadow-none"
    >
      <div className="flex items-center justify-between gap-2 border-b border-slate-200 px-3 py-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 text-sm font-semibold text-slate-950">
            <ClipboardList className="h-4 w-4" />
            <span>{text("任务板", "Task board")}</span>
            <Badge tone="neutral">{visibleTasks.length}</Badge>
          </div>
          <div className="mt-0.5 truncate text-[11px] text-slate-500">{team.name}</div>
        </div>
        <button
          type="button"
          aria-label={text("关闭任务板", "Close task board")}
          onClick={onClose}
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-950"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="max-h-[64vh] overflow-auto px-3 py-2">
        {visibleTasks.length === 0 ? (
          <div className="rounded-md border border-dashed border-slate-200 bg-slate-50/60 px-3 py-6 text-center text-xs text-slate-500">
            {text("暂无团队任务", "No team tasks yet")}
          </div>
        ) : (
          <div className="space-y-3">
            {statuses.map((status) => {
              const scopedTasks = visibleTasks.filter((task) => task.status === status);
              if (scopedTasks.length === 0) return null;
              return (
                <section key={status} aria-label={teamTaskStatusLabel(status)}>
                  <div className="mb-1.5 flex items-center justify-between">
                    <div className="text-[11px] font-semibold uppercase text-slate-500">
                      {teamTaskStatusLabel(status)}
                    </div>
                    <Badge tone={teamTaskStatusTone(status)}>{scopedTasks.length}</Badge>
                  </div>
                  <div className="overflow-hidden rounded-md border border-slate-200 bg-white">
                    {scopedTasks.map((task, index) => (
                      <div
                        key={task.id}
                        className={cn(
                          "px-3 py-2",
                          index > 0 ? "border-t border-slate-100" : "",
                        )}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="truncate text-xs font-medium text-slate-900">{task.subject}</div>
                            <div className="mt-0.5 line-clamp-2 text-[11px] leading-4 text-slate-500">
                              {task.description || text("无描述", "No description")}
                            </div>
                          </div>
                          <Badge tone={teamTaskStatusTone(task.status)}>
                            {teamTaskStatusLabel(task.status)}
                          </Badge>
                        </div>
                        <div className="mt-1.5 flex items-center justify-between gap-2 text-[11px] text-slate-400">
                          <span className="truncate">
                            {text("负责人", "Owner")} ·{" "}
                            {task.owner_slot_id
                              ? agentNames.get(task.owner_slot_id) ?? task.owner_slot_id
                              : text("队长", "Leader")}
                          </span>
                          {task.blocked_by_json.length > 0 ? (
                            <span>{text("依赖", "Deps")} {task.blocked_by_json.length}</span>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
