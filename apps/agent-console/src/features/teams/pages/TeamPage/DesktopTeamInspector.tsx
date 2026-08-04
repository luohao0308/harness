import { Activity, Bot, CheckCircle2, Crown, Inbox, ListTodo } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "../../../../components/ui/badge";
import { cn } from "../../../../lib/utils";
import type { Team, TeamAgent, TeamMailboxMessage, TeamTask } from "../../../tasks/api";
import {
  teamAgentStatusLabel,
  teamAgentStatusTone,
  teamTaskStatusLabel,
  teamTaskStatusTone,
} from "../../lib/teamLabels";

import type { TextFn } from "./types";

type InspectorTab = "activity" | "tasks";

type TeamActivityItem =
  | {
      id: string;
      kind: "message";
      actor: string;
      target: string;
      content: string;
      timestamp: string | null;
    }
  | {
      id: string;
      kind: "task";
      actor: string;
      content: string;
      status: TeamTask["status"];
      timestamp: string | null;
    };

function activityTimestamp(timestamp: string | null) {
  if (!timestamp) return "";
  const value = new Date(timestamp);
  if (Number.isNaN(value.getTime())) return "";
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(value);
}

export function DesktopTeamInspector({
  team,
  agents,
  selectedAgent,
  tasks,
  messages,
  status,
  text,
  onSelectAgent,
}: {
  team: Team;
  agents: TeamAgent[];
  selectedAgent: TeamAgent | null;
  tasks: TeamTask[];
  messages: TeamMailboxMessage[];
  status: TeamAgent["status"] | null;
  text: TextFn;
  onSelectAgent: (slotId: string) => void;
}) {
  const [tab, setTab] = useState<InspectorTab>("activity");
  const agentNames = useMemo(
    () => new Map(agents.map((agent) => [agent.slot_id, agent.agent_name])),
    [agents],
  );
  const assignedTasks = useMemo(
    () =>
      tasks.filter(
        (task) => task.status !== "deleted" && task.owner_slot_id === selectedAgent?.slot_id,
      ),
    [selectedAgent?.slot_id, tasks],
  );
  const activityItems = useMemo<TeamActivityItem[]>(() => {
    const messageItems: TeamActivityItem[] = messages.map((message) => ({
      id: `message:${message.id}`,
      kind: "message",
      actor: agentNames.get(message.from_agent_slot_id) ?? message.from_agent_slot_id,
      target: agentNames.get(message.to_agent_slot_id) ?? message.to_agent_slot_id,
      content: message.summary || message.content,
      timestamp: message.created_at,
    }));
    const taskItems: TeamActivityItem[] = tasks
      .filter((task) => task.status !== "deleted")
      .map((task) => ({
        id: `task:${task.id}`,
        kind: "task",
        actor: task.owner_slot_id
          ? agentNames.get(task.owner_slot_id) ?? task.owner_slot_id
          : text("未分配", "Unassigned"),
        content: task.subject,
        status: task.status,
        timestamp: task.updated_at,
      }));

    return [...messageItems, ...taskItems]
      .sort((left, right) => {
        const byTime = String(right.timestamp ?? "").localeCompare(String(left.timestamp ?? ""));
        return byTime || left.id.localeCompare(right.id);
      })
      .slice(0, 12);
  }, [agentNames, messages, tasks, text]);
  const completedTaskCount = assignedTasks.filter((task) => task.status === "completed").length;

  return (
    <aside
      role="complementary"
      aria-label={text("团队检查器", "Team inspector")}
      className="flex h-full min-h-0 flex-col bg-slate-50/50"
    >
      <div className="shrink-0 border-b border-slate-200 bg-white px-3 py-2.5">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2 text-sm font-semibold text-slate-900">
            <Activity aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-500" />
            <span>{text("团队动态", "Team activity")}</span>
          </div>
          <span className="truncate text-[10px] text-slate-400">{team.name}</span>
        </div>

        <div className="mt-2 flex items-center gap-1.5" aria-label={text("选择团队成员", "Select teammate")}>
          {agents.map((agent) => {
            const active = agent.slot_id === selectedAgent?.slot_id;
            const AgentIcon = agent.role === "leader" ? Crown : Bot;
            return (
              <button
                key={agent.slot_id}
                type="button"
                aria-pressed={active}
                aria-label={agent.agent_name}
                title={agent.agent_name}
                onClick={() => onSelectAgent(agent.slot_id)}
                className={cn(
                  "flex h-7 w-7 items-center justify-center rounded-full border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500",
                  active
                    ? "border-blue-400 bg-blue-50 text-blue-700"
                    : "border-slate-200 bg-white text-slate-500 hover:border-slate-300 hover:text-slate-800",
                )}
              >
                <AgentIcon aria-hidden="true" className="h-3.5 w-3.5" />
              </button>
            );
          })}
        </div>

        {selectedAgent ? (
          <div className="mt-2 flex items-center justify-between gap-2 border-t border-slate-100 pt-2">
            <div className="flex min-w-0 items-center gap-1.5">
              <span className="truncate text-[11px] font-semibold text-slate-800">{selectedAgent.agent_name}</span>
              {status ? (
                <Badge className="px-1.5 py-0 text-[10px]" tone={teamAgentStatusTone(status)}>
                  {teamAgentStatusLabel(status)}
                </Badge>
              ) : null}
            </div>
            <span className="shrink-0 text-[10px] tabular-nums text-slate-400">
              {text(
                `${assignedTasks.length} 项 / ${completedTaskCount} 完成`,
                `${assignedTasks.length} / ${completedTaskCount} done`,
              )}
            </span>
          </div>
        ) : null}
      </div>

      <div
        role="tablist"
        aria-label={text("检查器内容", "Inspector content")}
        className="flex h-9 shrink-0 border-b border-slate-200 bg-white px-2.5"
      >
        {([
          { id: "activity" as const, label: text("动态", "Activity"), icon: Inbox },
          { id: "tasks" as const, label: text("任务", "Tasks"), icon: ListTodo },
        ]).map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={tab === item.id}
              onClick={() => setTab(item.id)}
              className={cn(
                "relative inline-flex items-center gap-1.5 px-2 text-[11px] font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500",
                tab === item.id ? "text-blue-700" : "text-slate-500 hover:text-slate-800",
              )}
            >
              <Icon aria-hidden="true" className="h-3.5 w-3.5" />
              {item.label}
              {tab === item.id ? <span className="absolute inset-x-1 bottom-0 h-0.5 bg-blue-500" /> : null}
            </button>
          );
        })}
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-2.5">
        {tab === "activity" ? (
          activityItems.length > 0 ? (
            <div className="space-y-1.5">
              {activityItems.map((item) => {
                const ItemIcon = item.kind === "task" && item.status === "completed" ? CheckCircle2 : item.kind === "task" ? ListTodo : Inbox;
                return (
                  <article key={item.id} className="rounded-md border border-slate-200 bg-white px-2.5 py-2">
                    <div className="flex items-center gap-2">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-500">
                        <ItemIcon aria-hidden="true" className="h-3.5 w-3.5" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-1.5 text-[10px] text-slate-400">
                          <span className="truncate">
                            {item.actor}
                            {item.kind === "message" ? ` → ${item.target}` : ` · ${text("任务更新", "Task update")}`}
                          </span>
                          <span className="shrink-0 tabular-nums">{activityTimestamp(item.timestamp)}</span>
                        </div>
                        <p className="mt-0.5 line-clamp-3 text-[11px] leading-4 text-slate-600">{item.content}</p>
                      </div>
                    </div>
                    {item.kind === "task" ? (
                      <div className="mt-1.5 flex justify-end">
                        <Badge className="px-1.5 py-0 text-[10px]" tone={teamTaskStatusTone(item.status)}>
                          {teamTaskStatusLabel(item.status)}
                        </Badge>
                      </div>
                    ) : null}
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="border border-dashed border-slate-200 bg-white px-3 py-6 text-center text-xs text-slate-400">
              {text("暂无成员动态", "No member activity")}
            </div>
          )
        ) : assignedTasks.length > 0 ? (
          <div className="space-y-1.5">
            {assignedTasks.map((task) => (
              <article key={task.id} className="rounded-md border border-slate-200 bg-white px-2.5 py-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate text-[11px] font-semibold text-slate-900">{task.subject}</div>
                    <p className="mt-0.5 line-clamp-3 text-[10px] leading-4 text-slate-500">
                      {task.description || text("无描述", "No description")}
                    </p>
                  </div>
                  <Badge className="px-1.5 py-0 text-[10px]" tone={teamTaskStatusTone(task.status)}>
                    {teamTaskStatusLabel(task.status)}
                  </Badge>
                </div>
                <div className="mt-1.5 flex items-center gap-1 text-[10px] text-slate-400">
                  {task.status === "completed" ? <CheckCircle2 aria-hidden="true" className="h-3 w-3 text-emerald-500" /> : null}
                  <span>{text("依赖", "Dependencies")} {task.blocked_by_json.length}</span>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="border border-dashed border-slate-200 bg-white px-3 py-6 text-center text-xs text-slate-400">
            {text("暂无负责的任务", "No assigned tasks")}
          </div>
        )}
      </div>
    </aside>
  );
}
