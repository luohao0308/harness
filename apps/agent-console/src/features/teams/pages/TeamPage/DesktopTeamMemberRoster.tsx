import { Bot, Crown } from "lucide-react";

import { Badge } from "../../../../components/ui/badge";
import { cn } from "../../../../lib/utils";
import type { TeamAgent, TeamTask } from "../../../tasks/api";
import {
  teamAgentStatusLabel,
  teamAgentStatusTone,
  teamTaskStatusLabel,
} from "../../lib/teamLabels";

import type { TextFn } from "./types";

export function DesktopTeamMemberRoster({
  agents,
  tasks,
  activeSlotId,
  statusBySlotId,
  text,
  onSelectAgent,
}: {
  agents: TeamAgent[];
  tasks: TeamTask[];
  activeSlotId: string;
  statusBySlotId: Map<string, TeamAgent["status"]>;
  text: TextFn;
  onSelectAgent: (slotId: string) => void;
}) {
  const visibleTasks = tasks.filter((task) => task.status !== "deleted");
  const completedTaskCount = visibleTasks.filter((task) => task.status === "completed").length;

  return (
    <section
      data-testid="desktop-team-member-roster"
      className="mt-3 w-full max-w-xl border-t border-slate-100 pt-2.5"
    >
      <div className="mb-2 flex items-center justify-between gap-3 px-0.5">
        <div className="text-xs font-semibold text-slate-800">
          {text(`${agents.length} 个协作成员`, `${agents.length} collaborators`)}
        </div>
        <div className="text-[11px] text-slate-400">
          {text(
            `${completedTaskCount}/${visibleTasks.length} 项任务`,
            `${completedTaskCount}/${visibleTasks.length} tasks`,
          )}
        </div>
      </div>

      <div className="space-y-1.5">
        {agents.map((agent) => {
          const status = statusBySlotId.get(agent.slot_id) ?? agent.status;
          const assignedTasks = visibleTasks.filter((task) => task.owner_slot_id === agent.slot_id);
          const completedCount = assignedTasks.filter((task) => task.status === "completed").length;
          const progress = assignedTasks.length === 0 ? 0 : Math.round((completedCount / assignedTasks.length) * 100);
          const currentTask =
            assignedTasks.find((task) => task.status === "in_progress") ??
            assignedTasks.find((task) => task.status === "pending") ??
            assignedTasks[0];
          const selected = activeSlotId === agent.slot_id;
          const AvatarIcon = agent.role === "leader" ? Crown : Bot;

          return (
            <button
              key={agent.slot_id}
              type="button"
              aria-pressed={selected}
              aria-label={text(`打开 ${agent.agent_name} 会话`, `Open ${agent.agent_name} conversation`)}
              onClick={() => onSelectAgent(agent.slot_id)}
              className={cn(
                "grid min-h-[50px] w-full grid-cols-[28px_minmax(0,1fr)_auto] items-center gap-2 rounded-lg border px-2 py-1 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500",
                selected
                  ? "border-blue-300 bg-blue-50/80"
                  : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50",
              )}
            >
              <span
                aria-hidden="true"
                className={cn(
                  "flex h-7 w-7 items-center justify-center rounded-full text-white",
                  agent.role === "leader" ? "bg-slate-900" : "bg-slate-600",
                )}
              >
                <AvatarIcon className="h-3.5 w-3.5" />
              </span>

              <span className="min-w-0">
                <span className="flex min-w-0 items-center gap-1.5">
                  <span className="truncate text-xs font-semibold text-slate-900">{agent.agent_name}</span>
                  <span className="truncate text-[10px] text-slate-400">
                    {agent.role === "leader" ? text("队长", "Leader") : text("成员", "Teammate")}
                  </span>
                </span>
                <span className="mt-0.5 block truncate text-[11px] text-slate-500">
                  {currentTask?.subject ?? text("等待新任务", "Waiting for work")}
                </span>
                <span className="mt-0.5 flex items-center gap-2">
                  <span className="grid w-20 grid-cols-8 gap-0.5" aria-hidden="true">
                    {Array.from({ length: 8 }, (_, index) => (
                      <span
                        key={index}
                        className={cn(
                          "h-1 rounded-sm",
                          index < Math.ceil(progress / 12.5)
                            ? status === "failed"
                              ? "bg-red-500"
                              : "bg-blue-500"
                            : "bg-slate-100",
                        )}
                      />
                    ))}
                  </span>
                  <span className="w-9 text-right text-[10px] tabular-nums text-slate-400">
                    {assignedTasks.length > 0 ? `${completedCount}/${assignedTasks.length}` : "-"}
                  </span>
                </span>
              </span>

              <span className="flex min-w-[50px] flex-col items-end gap-0.5">
                <Badge className="px-1.5 py-0 text-[10px]" tone={teamAgentStatusTone(status)}>
                  {teamAgentStatusLabel(status)}
                </Badge>
                {currentTask ? <span className="text-[9px] text-slate-400">{teamTaskStatusLabel(currentTask.status)}</span> : null}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
