import { GripVertical, Pencil } from "lucide-react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";

import { Badge } from "../../../../components/ui/badge";
import { Input } from "../../../../components/ui/input";
import { cn } from "../../../../lib/utils";
import type { Team, TeamAgent, TeamTask } from "../../../tasks/api";
import { teamAgentStatusLabel, teamAgentStatusTone } from "../../lib/teamLabels";

import { displayAgentStatus } from "./teamState";
import type { SettledWakeCutoffs, StreamingWake, TextFn } from "./types";

export function TeamAgentTabs({
  activeTeam,
  orderedAgents,
  tasks,
  activeSlotId,
  editingSlotId,
  editingAgentName,
  dragSourceSlotId,
  dragOverSlotId,
  pendingWakeSlotIds,
  streamingWakes,
  settledWakeCutoffs,
  text,
  onActiveSlotChange,
  onStartEditingAgent,
  onEditingAgentNameChange,
  onCommitEditingAgent,
  onCancelEditingAgent,
  onDragSourceChange,
  onDragOverChange,
  onDropAgentTab,
}: {
  activeTeam: Team;
  orderedAgents: TeamAgent[];
  tasks: TeamTask[];
  activeSlotId: string;
  editingSlotId: string | null;
  editingAgentName: string;
  dragSourceSlotId: string | null;
  dragOverSlotId: string | null;
  pendingWakeSlotIds: string[];
  streamingWakes: StreamingWake[];
  settledWakeCutoffs: SettledWakeCutoffs;
  text: TextFn;
  onActiveSlotChange: (slotId: string) => void;
  onStartEditingAgent: (agent: TeamAgent) => void;
  onEditingAgentNameChange: (name: string) => void;
  onCommitEditingAgent: () => void;
  onCancelEditingAgent: () => void;
  onDragSourceChange: (slotId: string | null) => void;
  onDragOverChange: (slotId: string | null) => void;
  onDropAgentTab: (slotId: string) => void;
}) {
  return (
    <div className="relative flex h-10 min-h-10 items-center gap-2 border-b border-slate-200 bg-white px-0 after:pointer-events-none after:absolute after:inset-y-0 after:right-0 after:w-5 after:bg-gradient-to-l after:from-white after:to-transparent md:after:hidden">
      <div
        role="tablist"
        data-testid="team-tab-bar"
        aria-label={text("代理切换", "Agent switcher")}
        className="flex h-full min-w-0 flex-1 items-center overflow-x-auto [scrollbar-width:none]"
      >
        {orderedAgents.map((agent) => {
          const unreadCount = activeTeam.unread_counts[agent.slot_id] ?? 0;
          const assignedTaskCount =
            agent.role === "leader"
              ? tasks.length
              : tasks.filter((task) => task.owner_slot_id === agent.slot_id).length;
          const status = displayAgentStatus(agent, pendingWakeSlotIds, streamingWakes, settledWakeCutoffs);
          const isActive = activeSlotId === agent.slot_id;
          const isEditing = editingSlotId === agent.slot_id;
          const agentDisplayName = agent.role === "leader" && agent.agent_name.trim().toLowerCase() === "leader"
            ? text("队长", "Leader")
            : agent.agent_name;
          return (
            <div
              key={agent.slot_id}
              role="tab"
              tabIndex={0}
              aria-selected={isActive}
              title={agentDisplayName}
              draggable={agent.role !== "leader" && !isEditing}
              onClick={() => {
                if (!isEditing) onActiveSlotChange(agent.slot_id);
              }}
              onKeyDown={(event: ReactKeyboardEvent<HTMLDivElement>) => {
                if (isEditing) return;
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onActiveSlotChange(agent.slot_id);
                }
              }}
              onDoubleClick={() => onStartEditingAgent(agent)}
              onDragStart={(event) => {
                if (agent.role === "leader") return;
                event.dataTransfer.effectAllowed = "move";
                onDragSourceChange(agent.slot_id);
              }}
              onDragOver={(event) => {
                if (!dragSourceSlotId || agent.role === "leader") return;
                event.preventDefault();
                event.dataTransfer.dropEffect = "move";
                onDragOverChange(agent.slot_id);
              }}
              onDrop={(event) => {
                event.preventDefault();
                onDropAgentTab(agent.slot_id);
              }}
              onDragEnd={() => {
                onDragSourceChange(null);
                onDragOverChange(null);
              }}
              className={cn(
                "group inline-flex h-full max-w-60 shrink-0 cursor-pointer items-center gap-1.5 border-r border-slate-100 px-3 text-xs transition-colors",
                isActive
                  ? "border-t-2 border-t-slate-900 bg-slate-100 text-slate-950"
                  : "border-t-2 border-t-transparent bg-white text-slate-600 hover:bg-slate-50 hover:text-slate-900",
                dragOverSlotId === agent.slot_id ? "border-l-4 border-l-slate-900" : "",
              )}
            >
              {agent.role !== "leader" ? (
                <GripVertical
                  className="h-3 w-3 shrink-0 text-slate-300 opacity-0 transition-opacity group-hover:opacity-100"
                  aria-hidden="true"
                />
              ) : null}
              {isEditing ? (
                <Input
                  autoFocus
                  value={editingAgentName}
                  onClick={(event) => event.stopPropagation()}
                  onChange={(event) => onEditingAgentNameChange(event.target.value)}
                  onBlur={onCommitEditingAgent}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      onCommitEditingAgent();
                    }
                    if (event.key === "Escape") {
                      onCancelEditingAgent();
                    }
                  }}
                  aria-label={text("代理名称", "Agent name")}
                  className="h-6 w-28 border-0 bg-transparent px-0 text-xs focus:ring-0"
                />
              ) : (
                <span className="max-w-28 truncate">{agentDisplayName}</span>
              )}
              <Badge tone={teamAgentStatusTone(status)} className="px-1.5">
                {teamAgentStatusLabel(status)}
              </Badge>
              {assignedTaskCount > 0 ? (
                <Badge tone="info" className="px-1.5">
                  {assignedTaskCount}
                </Badge>
              ) : null}
              {unreadCount > 0 ? (
                <Badge tone="warning" className="px-1.5">
                  {unreadCount}
                </Badge>
              ) : null}
              {!isEditing ? (
                <Pencil
                  className="h-3 w-3 shrink-0 text-slate-300 opacity-0 transition-opacity group-hover:opacity-100"
                  aria-hidden="true"
                />
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
