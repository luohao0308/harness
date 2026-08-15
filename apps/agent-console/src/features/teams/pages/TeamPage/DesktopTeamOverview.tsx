import { Activity, AlertTriangle, ArrowRight, Bot, CheckCircle2, Circle, Crown, ListTodo, UsersRound } from "lucide-react";

import { Badge } from "../../../../components/ui/badge";
import { cn } from "../../../../lib/utils";
import type { Team, TeamAgent, TeamMailboxMessage, TeamTask } from "../../../tasks/api";
import { teamAgentStatusLabel, teamAgentStatusTone } from "../../lib/teamLabels";

import { agentSessionMessages } from "./teamState";
import type { SettledWakeCutoffs, StreamingWake, TextFn } from "./types";
import { displayAgentStatus } from "./teamState";

function displayName(agent: TeamAgent, text: TextFn) {
  return agent.role === "leader" && agent.agent_name.trim().toLowerCase() === "leader"
    ? text("队长", "Leader")
    : agent.agent_name;
}

function latestResult(agent: TeamAgent, text: TextFn) {
  const message = [...agentSessionMessages(agent)].reverse().find((item) => item.role === "assistant" && item.content.trim());
  return message?.content.trim() || text("暂无结果", "No result yet");
}

function activityTime(value: string | null) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(parsed);
}

export function DesktopTeamOverview({
  team,
  agents,
  tasks,
  messages,
  activeSlotId,
  pendingWakeSlotIds,
  streamingWakes,
  settledWakeCutoffs,
  text,
  onSelectAgent,
}: {
  team: Team;
  agents: TeamAgent[];
  tasks: TeamTask[];
  messages: TeamMailboxMessage[];
  activeSlotId: string;
  pendingWakeSlotIds: string[];
  streamingWakes: StreamingWake[];
  settledWakeCutoffs: SettledWakeCutoffs;
  text: TextFn;
  onSelectAgent: (slotId: string) => void;
}) {
  const visibleTasks = tasks.filter((task) => task.status !== "deleted");
  const completedTasks = visibleTasks.filter((task) => task.status === "completed");
  const activeTasks = visibleTasks.filter((task) => task.status === "in_progress");
  const blockedTasks = visibleTasks.filter((task) => task.blocked_by_json.length > 0 && task.status !== "completed");
  const failedAgents = agents.filter((agent) => agent.status === "failed");
  const recentMessages = [...messages]
    .filter((message) => message.content.trim())
    .sort((left, right) => String(right.created_at ?? "").localeCompare(String(left.created_at ?? "")))
    .slice(0, 4);
  const goal = team.active_goal;
  const goalProgress = goal?.progress_json ?? {};
  const goalCompleted = Number(goalProgress.completed_task_count ?? completedTasks.length);
  const goalTotal = Math.max(
    completedTasks.length + Number(goalProgress.open_task_count ?? visibleTasks.length - completedTasks.length),
    visibleTasks.length,
  );

  return (
    <section
      data-testid="desktop-team-overview"
      aria-label={text("团队概览", "Team overview")}
      className="h-full min-h-0 overflow-auto bg-white"
    >
      <div className="mx-auto flex min-h-full w-full max-w-[1180px] flex-col px-5 py-5 lg:px-8">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-200 pb-5">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
              <UsersRound aria-hidden="true" className="h-4 w-4 text-slate-500" />
              <span>{text("团队概览", "Team overview")}</span>
              <Badge tone={team.status === "ACTIVE" ? "success" : "neutral"}>{team.status === "ACTIVE" ? text("活跃", "Active") : team.status}</Badge>
            </div>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-600">
              {goal?.objective || text("查看团队推进状态，选择成员进入完整对话。", "Scan team progress, then open an Agent for the full conversation.")}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2 text-xs text-slate-500">
            <span>{agents.length} {text("名成员", "members")}</span>
            <span aria-hidden="true" className="text-slate-300">·</span>
            <span>{completedTasks.length}/{visibleTasks.length} {text("项任务完成", "tasks done")}</span>
          </div>
        </div>

        <div className="grid min-h-0 flex-1 gap-8 py-6 lg:grid-cols-[minmax(0,1fr)_280px]">
          <div className="min-w-0 space-y-7">
            <section aria-labelledby="desktop-team-member-progress-heading">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-900">
                  <UsersRound aria-hidden="true" className="h-3.5 w-3.5 text-slate-500" />
                  <h2 id="desktop-team-member-progress-heading">{text("成员进度", "Member progress")}</h2>
                </div>
                <span className="text-[11px] text-slate-500">{text("选择成员查看完整对话", "Select a member for the full conversation")}</span>
              </div>
              <div className="divide-y divide-slate-100 border-y border-slate-100">
                {agents.map((agent) => {
                  const status = displayAgentStatus(agent, pendingWakeSlotIds, streamingWakes, settledWakeCutoffs);
                  const assignedTasks = visibleTasks.filter((task) => task.owner_slot_id === agent.slot_id);
                  const completed = assignedTasks.filter((task) => task.status === "completed").length;
                  const progress = assignedTasks.length ? Math.round((completed / assignedTasks.length) * 100) : 0;
                  const currentTask = assignedTasks.find((task) => task.status === "in_progress") ?? assignedTasks.find((task) => task.status === "pending");
                  const selected = activeSlotId === agent.slot_id;
                  const Icon = agent.role === "leader" ? Crown : Bot;
                  const name = displayName(agent, text);
                  return (
                    <button
                      key={agent.slot_id}
                      type="button"
                      aria-label={text(`进入 ${name} 专注对话`, `Open ${name} focus conversation`)}
                      aria-pressed={selected}
                      onClick={() => onSelectAgent(agent.slot_id)}
                      className={cn(
                        "grid w-full grid-cols-[32px_minmax(0,1fr)_auto_16px] items-center gap-3 px-2 py-3 text-left transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500",
                        selected ? "bg-blue-50/60" : "bg-white",
                      )}
                    >
                      <span className={cn("flex h-8 w-8 items-center justify-center rounded-full text-white", agent.role === "leader" ? "bg-slate-950" : "bg-slate-700")}>
                        <Icon aria-hidden="true" className="h-4 w-4" />
                      </span>
                      <span className="min-w-0">
                        <span className="flex min-w-0 items-center gap-2">
                          <span className="truncate text-xs font-semibold text-slate-950" title={name}>{name}</span>
                          <Badge className="shrink-0 px-1.5 py-0 text-[10px]" tone={teamAgentStatusTone(status)}>{teamAgentStatusLabel(status)}</Badge>
                        </span>
                        <span className="mt-1 block truncate text-[11px] text-slate-500">{currentTask?.subject ?? text("等待新任务", "Waiting for work")}</span>
                        <span className="mt-1 block truncate text-[11px] text-slate-400">{latestResult(agent, text)}</span>
                      </span>
                      <span className="w-24">
                        <span className="mb-1 flex justify-between text-[10px] tabular-nums text-slate-500"><span>{text("阶段进度", "Progress")}</span><span>{assignedTasks.length ? `${progress}%` : "-"}</span></span>
                        <span className="block h-1 overflow-hidden rounded-sm bg-slate-100"><span className={cn("block h-full rounded-sm", status === "failed" ? "bg-red-500" : "bg-blue-500")} style={{ width: `${progress}%` }} /></span>
                      </span>
                      <ArrowRight aria-hidden="true" className="h-4 w-4 text-slate-400" />
                    </button>
                  );
                })}
              </div>
            </section>

            <section aria-labelledby="desktop-team-recent-heading">
              <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-slate-900">
                <Activity aria-hidden="true" className="h-3.5 w-3.5 text-slate-500" />
                <h2 id="desktop-team-recent-heading">{text("最近活动", "Recent activity")}</h2>
              </div>
              {recentMessages.length > 0 ? (
                <div className="divide-y divide-slate-100 border-y border-slate-100">
                  {recentMessages.map((message) => (
                    <div key={message.id} className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 px-2 py-3">
                      <p className="line-clamp-2 text-xs leading-5 text-slate-600">{message.summary || message.content}</p>
                      <span className="text-[10px] tabular-nums text-slate-500">{activityTime(message.created_at)}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="border-y border-slate-100 px-2 py-5 text-xs text-slate-500">{text("暂无最近活动", "No recent activity")}</div>
              )}
            </section>
          </div>

          <aside aria-label={text("团队系统看板", "Team system board")} className="border-l border-slate-100 pl-6">
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-900"><ListTodo aria-hidden="true" className="h-3.5 w-3.5 text-slate-500" />{text("系统看板", "System board")}</div>
            <div className="mt-4 space-y-4 text-xs">
              <div className="border-b border-slate-100 pb-3"><div className="text-[11px] text-slate-500">{text("当前目标", "Current goal")}</div><div className="mt-1 flex items-center justify-between gap-2"><span className="font-semibold text-slate-900">{goal ? goalStatusLabel(goal.status, text) : text("未设置", "Not set")}</span><span className="tabular-nums text-slate-500">{goalTotal ? `${goalCompleted}/${goalTotal}` : "-"}</span></div></div>
              <div className="border-b border-slate-100 pb-3"><div className="text-[11px] text-slate-500">{text("任务", "Tasks")}</div><div className="mt-1 flex items-center justify-between"><span className="text-slate-700">{text("进行中", "In progress")}</span><Badge className="px-1.5 py-0 text-[10px]" tone="running">{activeTasks.length}</Badge></div><div className="mt-1 flex items-center justify-between"><span className="text-slate-700">{text("已完成", "Completed")}</span><Badge className="px-1.5 py-0 text-[10px]" tone="success">{completedTasks.length}</Badge></div></div>
              <div className="border-b border-slate-100 pb-3"><div className="text-[11px] text-slate-500">{text("需要关注", "Needs attention")}</div>{blockedTasks.length || failedAgents.length ? <div className="mt-2 space-y-1.5 text-slate-700"><div className="flex items-center gap-2"><AlertTriangle aria-hidden="true" className="h-3.5 w-3.5 text-amber-500" />{blockedTasks.length} {text("项任务受阻", "blocked tasks")}</div><div className="flex items-center gap-2"><AlertTriangle aria-hidden="true" className="h-3.5 w-3.5 text-red-500" />{failedAgents.length} {text("名成员失败", "failed members")}</div></div> : <div className="mt-2 flex items-center gap-2 text-slate-600"><CheckCircle2 aria-hidden="true" className="h-3.5 w-3.5 text-emerald-500" />{text("暂无异常", "No issues")}</div>}</div>
              <div><div className="text-[11px] text-slate-500">{text("状态说明", "Status legend")}</div><div className="mt-2 space-y-1.5 text-slate-600"><div className="flex items-center gap-2"><Circle aria-hidden="true" className="h-3 w-3 text-blue-500" />{text("执行中 / 待命", "Running / idle")}</div><div className="flex items-center gap-2"><Circle aria-hidden="true" className="h-3 w-3 text-emerald-500" />{text("已完成", "Completed")}</div></div></div>
            </div>
          </aside>
        </div>
      </div>
    </section>
  );
}

function goalStatusLabel(status: string, text: TextFn) {
  if (status === "active") return text("执行中", "Active");
  if (status === "paused") return text("已暂停", "Paused");
  if (status === "completed") return text("已完成", "Completed");
  if (status === "blocked") return text("受阻", "Blocked");
  if (status === "failed") return text("失败", "Failed");
  return status;
}
