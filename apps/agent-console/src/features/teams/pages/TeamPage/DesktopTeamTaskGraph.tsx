import { Bot, Check, CircleAlert, Crown, GitFork, ListTodo } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "../../../../components/ui/badge";
import { cn } from "../../../../lib/utils";
import type { Team, TeamAgent, TeamTask } from "../../../tasks/api";
import { teamTaskStatusLabel, teamTaskStatusTone } from "../../lib/teamLabels";

import type { TextFn } from "./types";

const CARD_WIDTH = 184;
const CARD_HEIGHT = 82;
const HORIZONTAL_GAP = 18;
const VERTICAL_GAP = 34;
const CANVAS_PADDING = 24;

type TaskGraphNode = {
  id: string;
  kind: "goal" | "task";
  level: number;
  x: number;
  y: number;
  task: TeamTask | null;
};

type TaskGraphEdge = {
  id: string;
  sourceId: string;
  targetId: string;
};

type TaskGraphLayout = {
  width: number;
  height: number;
  nodes: TaskGraphNode[];
  edges: TaskGraphEdge[];
  cycleTaskIds: string[];
};

function dependencyEdgeKey(sourceId: string, targetId: string) {
  return `${sourceId}\u0000${targetId}`;
}

function taskSubjects(taskIds: string[], taskById: Map<string, TeamTask>) {
  return taskIds.flatMap((taskId) => {
    const subject = taskById.get(taskId)?.subject;
    return subject ? [subject] : [];
  });
}

function declaredDependenciesByTask(taskById: Map<string, TeamTask>) {
  const dependencies = new Map(
    [...taskById.keys()].map((taskId) => [taskId, new Set<string>()]),
  );
  taskById.forEach((task) => {
    task.blocked_by_json.forEach((dependencyId) => {
      if (taskById.has(dependencyId)) dependencies.get(task.id)?.add(dependencyId);
    });
    task.blocks_json.forEach((targetId) => {
      if (taskById.has(targetId)) dependencies.get(targetId)?.add(task.id);
    });
  });
  return new Map(
    [...dependencies.entries()].map(([taskId, taskDependencies]) => [taskId, [...taskDependencies].sort()]),
  );
}

function findCyclicDependencies(dependenciesByTaskId: Map<string, string[]>) {
  const indexById = new Map<string, number>();
  const lowLinkById = new Map<string, number>();
  const stack: string[] = [];
  const onStack = new Set<string>();
  const cycleTaskIds = new Set<string>();
  const cycleEdgeKeys = new Set<string>();
  const components: string[][] = [];
  let nextIndex = 0;

  const visit = (taskId: string) => {
    indexById.set(taskId, nextIndex);
    lowLinkById.set(taskId, nextIndex);
    nextIndex += 1;
    stack.push(taskId);
    onStack.add(taskId);

    const dependencies = dependenciesByTaskId.get(taskId) ?? [];
    dependencies.forEach((dependencyId) => {
      if (!indexById.has(dependencyId)) {
        visit(dependencyId);
        lowLinkById.set(
          taskId,
          Math.min(lowLinkById.get(taskId)!, lowLinkById.get(dependencyId)!),
        );
      } else if (onStack.has(dependencyId)) {
        lowLinkById.set(
          taskId,
          Math.min(lowLinkById.get(taskId)!, indexById.get(dependencyId)!),
        );
      }
    });

    if (lowLinkById.get(taskId) !== indexById.get(taskId)) return;

    const component: string[] = [];
    while (stack.length > 0) {
      const memberId = stack.pop()!;
      onStack.delete(memberId);
      component.push(memberId);
      if (memberId === taskId) break;
    }
    component.sort();
    components.push(component);
    const componentSet = new Set(component);
    const isCycle =
      component.length > 1 ||
      (component.length === 1 && dependenciesByTaskId.get(component[0])?.includes(component[0]));
    if (!isCycle) return;

    component.forEach((memberId) => cycleTaskIds.add(memberId));
    component.forEach((targetId) => {
      dependenciesByTaskId.get(targetId)?.forEach((sourceId) => {
        if (componentSet.has(sourceId)) {
          cycleEdgeKeys.add(dependencyEdgeKey(sourceId, targetId));
        }
      });
    });
  };

  [...dependenciesByTaskId.keys()].sort().forEach((taskId) => {
    if (!indexById.has(taskId)) visit(taskId);
  });

  components.sort((left, right) => left[0].localeCompare(right[0]));
  return { cycleTaskIds, cycleEdgeKeys, components };
}

function taskGraphLevel(
  taskId: string,
  dependenciesByTaskId: Map<string, string[]>,
  memo: Map<string, number>,
): number {
  const memoized = memo.get(taskId);
  if (memoized !== undefined) return memoized;
  const dependencies = dependenciesByTaskId.get(taskId) ?? [];
  const level =
    dependencies.length === 0
      ? 0
      : Math.max(...dependencies.map((dependencyId) => taskGraphLevel(dependencyId, dependenciesByTaskId, memo))) + 1;
  memo.set(taskId, level);
  return level;
}

export function buildTeamTaskGraphLayout(team: Team, tasks: TeamTask[]): TaskGraphLayout {
  const visibleTasks = tasks
    .filter((task) => task.status !== "deleted")
    .sort((left, right) => left.id.localeCompare(right.id));
  const taskById = new Map(visibleTasks.map((task) => [task.id, task]));
  const declaredDependencies = declaredDependenciesByTask(taskById);
  const { cycleTaskIds, cycleEdgeKeys, components } = findCyclicDependencies(declaredDependencies);
  const dependenciesByTaskId = new Map(
    [...declaredDependencies.entries()].map(([taskId, dependencies]) => [
      taskId,
      dependencies
        .filter(
          (dependencyId) =>
            !cycleEdgeKeys.has(dependencyEdgeKey(dependencyId, taskId)),
        )
        .sort(),
    ]),
  );
  const componentIdByTaskId = new Map<string, string>();
  components.forEach((component) => {
    const componentId = component[0];
    component.forEach((taskId) => componentIdByTaskId.set(taskId, componentId));
  });
  const componentDependencySets = new Map(
    components.map((component) => [component[0], new Set<string>()]),
  );
  declaredDependencies.forEach((dependencies, taskId) => {
    const targetComponentId = componentIdByTaskId.get(taskId);
    if (!targetComponentId) return;
    dependencies.forEach((dependencyId) => {
      const sourceComponentId = componentIdByTaskId.get(dependencyId);
      if (sourceComponentId && sourceComponentId !== targetComponentId) {
        componentDependencySets.get(targetComponentId)?.add(sourceComponentId);
      }
    });
  });
  const dependenciesByComponentId = new Map(
    [...componentDependencySets.entries()].map(([componentId, dependencies]) => [
      componentId,
      [...dependencies].sort(),
    ]),
  );
  const levelMemo = new Map<string, number>();
  const hasGoal = Boolean(team.active_goal);
  const taskLevelOffset = hasGoal ? 1 : 0;
  const grouped = new Map<number, TeamTask[]>();

  visibleTasks.forEach((task) => {
    const componentId = componentIdByTaskId.get(task.id)!;
    const level = taskGraphLevel(componentId, dependenciesByComponentId, levelMemo) + taskLevelOffset;
    const layer = grouped.get(level) ?? [];
    layer.push(task);
    grouped.set(level, layer);
  });

  const layers = [...grouped.entries()].sort(([left], [right]) => left - right);
  const maxLayerSize = Math.max(1, ...layers.map(([, layer]) => layer.length));
  const width = Math.max(
    500,
    CANVAS_PADDING * 2 + maxLayerSize * CARD_WIDTH + Math.max(0, maxLayerSize - 1) * HORIZONTAL_GAP,
  );
  const highestLevel = Math.max(hasGoal ? 0 : -1, ...layers.map(([level]) => level));
  const height = Math.max(360, CANVAS_PADDING * 2 + (highestLevel + 1) * CARD_HEIGHT + highestLevel * VERTICAL_GAP);
  const nodes: TaskGraphNode[] = [];

  if (hasGoal) {
    nodes.push({
      id: `goal:${team.active_goal!.id}`,
      kind: "goal",
      level: 0,
      x: (width - CARD_WIDTH) / 2,
      y: CANVAS_PADDING,
      task: null,
    });
  }

  layers.forEach(([level, layer]) => {
    const rowWidth = layer.length * CARD_WIDTH + Math.max(0, layer.length - 1) * HORIZONTAL_GAP;
    const startX = (width - rowWidth) / 2;
    layer.forEach((task, index) => {
      nodes.push({
        id: task.id,
        kind: "task",
        level,
        x: startX + index * (CARD_WIDTH + HORIZONTAL_GAP),
        y: CANVAS_PADDING + level * (CARD_HEIGHT + VERTICAL_GAP),
        task,
      });
    });
  });

  const rootGoalId = team.active_goal ? `goal:${team.active_goal.id}` : null;
  const edges: TaskGraphEdge[] = [];
  visibleTasks.forEach((task) => {
    const dependencies = dependenciesByTaskId.get(task.id) ?? [];
    if (dependencies.length === 0 && rootGoalId) {
      edges.push({ id: `${rootGoalId}:${task.id}`, sourceId: rootGoalId, targetId: task.id });
      return;
    }
    dependencies.forEach((dependencyId) => {
      edges.push({ id: `${dependencyId}:${task.id}`, sourceId: dependencyId, targetId: task.id });
    });
  });

  return { width, height, nodes, edges, cycleTaskIds: [...cycleTaskIds].sort() };
}

function goalStatusLabel(status: string, text: TextFn) {
  if (status === "active") return text("执行中", "Active");
  if (status === "paused") return text("已暂停", "Paused");
  if (status === "completed") return text("已完成", "Completed");
  if (status === "blocked") return text("受阻", "Blocked");
  return status;
}

export function DesktopTeamTaskGraph({
  team,
  agents,
  tasks,
  activeSlotId,
  text,
  onSelectAgent,
}: {
  team: Team;
  agents: TeamAgent[];
  tasks: TeamTask[];
  activeSlotId: string;
  text: TextFn;
  onSelectAgent: (slotId: string) => void;
}) {
  const visibleTasks = useMemo(() => tasks.filter((task) => task.status !== "deleted"), [tasks]);
  const completedCount = visibleTasks.filter((task) => task.status === "completed").length;
  const progress = visibleTasks.length === 0 ? 0 : (completedCount / visibleTasks.length) * 100;
  const layout = useMemo(() => buildTeamTaskGraphLayout(team, visibleTasks), [team, visibleTasks]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(
    team.active_goal ? `goal:${team.active_goal.id}` : visibleTasks[0]?.id ?? null,
  );
  const agentBySlotId = useMemo(
    () => new Map(agents.map((agent) => [agent.slot_id, agent])),
    [agents],
  );
  const taskById = useMemo(
    () => new Map(visibleTasks.map((task) => [task.id, task])),
    [visibleTasks],
  );
  const dependenciesByTaskId = useMemo(
    () => declaredDependenciesByTask(taskById),
    [taskById],
  );
  const dependentsByTaskId = useMemo(() => {
    const next = new Map<string, TeamTask[]>();
    dependenciesByTaskId.forEach((dependencies, taskId) => {
      const task = taskById.get(taskId);
      if (!task) return;
      dependencies.forEach((dependencyId) => {
        next.set(dependencyId, [...(next.get(dependencyId) ?? []), task]);
      });
    });
    return next;
  }, [dependenciesByTaskId, taskById]);
  const nodeById = useMemo(
    () => new Map(layout.nodes.map((node) => [node.id, node])),
    [layout.nodes],
  );

  useEffect(() => {
    if (selectedNodeId && layout.nodes.some((node) => node.id === selectedNodeId)) return;
    setSelectedNodeId(layout.nodes[0]?.id ?? null);
  }, [layout.nodes, selectedNodeId]);

  const selectedTask = selectedNodeId ? taskById.get(selectedNodeId) ?? null : null;
  const selectedOwner = selectedTask?.owner_slot_id
    ? agentBySlotId.get(selectedTask.owner_slot_id)?.agent_name ?? selectedTask.owner_slot_id
    : text("队长", "Leader");
  const selectedDependencies = selectedTask
    ? taskSubjects(dependenciesByTaskId.get(selectedTask.id) ?? [], taskById)
    : [];

  return (
    <section
      role="region"
      aria-label={text("团队任务图", "Team task graph")}
      className="flex h-full min-h-0 flex-col bg-slate-50/70"
    >
      <header className="shrink-0 border-b border-slate-200 bg-white px-3 py-2.5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <GitFork aria-hidden="true" className="h-4 w-4 text-slate-500" />
              <span>{text("目标与任务", "Goal and tasks")}</span>
            </div>
            <div className="mt-0.5 truncate text-[10px] text-slate-400">
              {team.active_goal?.objective ?? team.name}
            </div>
          </div>
          <div className="shrink-0 text-right">
            <div className="text-[11px] font-semibold tabular-nums text-slate-700">
              {text(`${completedCount}/${visibleTasks.length} 已完成`, `${completedCount}/${visibleTasks.length} completed`)}
            </div>
            <div className="mt-1 h-1.5 w-20 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-blue-500 transition-[width]"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        </div>

        <div className="mt-2 flex min-w-0 items-center gap-2.5">
          <div className="flex shrink-0 items-center gap-1" aria-label={text("选择会话成员", "Select conversation member")}>
            {agents.map((agent) => {
              const Icon = agent.role === "leader" ? Crown : Bot;
              const selected = agent.slot_id === activeSlotId;
              return (
                <button
                  key={agent.slot_id}
                  type="button"
                  aria-pressed={selected}
                  aria-label={agent.agent_name}
                  title={agent.agent_name}
                  onClick={() => onSelectAgent(agent.slot_id)}
                  className={cn(
                    "flex h-6 w-6 items-center justify-center rounded-full border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500",
                    selected
                      ? "border-blue-300 bg-blue-50 text-blue-700"
                      : "border-slate-200 bg-white text-slate-500 hover:border-slate-300 hover:text-slate-800",
                  )}
                >
                  <Icon aria-hidden="true" className="h-3 w-3" />
                </button>
              );
            })}
          </div>
          <div
            className="min-w-0 flex-1 truncate text-[10px] text-slate-500"
            title={
              selectedTask
                ? `${selectedTask.subject} · ${selectedOwner} · ${selectedDependencies.join("、") || text("无依赖", "No dependencies")}`
                : team.active_goal?.objective ?? team.name
            }
          >
            {selectedTask ? (
              <>
                <span className="font-medium text-slate-700">{selectedTask.subject}</span>
                <span> · {selectedOwner} · {text("依赖", "Depends on")} {selectedDependencies.join("、") || text("无", "none")}</span>
              </>
            ) : (
              <span>{text("选择任务查看依赖", "Select a task to inspect dependencies")}</span>
            )}
          </div>
          {layout.cycleTaskIds.length > 0 ? (
            <Badge className="shrink-0 px-1.5 py-0 text-[9px]" tone="warning">
              {text("循环依赖已降级", "Cycle fallback")}
            </Badge>
          ) : null}
        </div>
      </header>

      <div
        className="min-h-0 flex-1 overflow-auto bg-slate-50"
        style={{
          backgroundImage: "radial-gradient(circle, #dbe3ee 1px, transparent 1px)",
          backgroundSize: "18px 18px",
        }}
      >
        {layout.nodes.length > 0 ? (
          <div className="relative mx-auto" style={{ width: layout.width, height: layout.height }}>
            <svg
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 h-full w-full"
              viewBox={`0 0 ${layout.width} ${layout.height}`}
              preserveAspectRatio="none"
            >
              {layout.edges.map((edge) => {
                const source = nodeById.get(edge.sourceId);
                const target = nodeById.get(edge.targetId);
                if (!source || !target) return null;
                const sourceX = source.x + CARD_WIDTH / 2;
                const sourceY = source.y + CARD_HEIGHT;
                const targetX = target.x + CARD_WIDTH / 2;
                const targetY = target.y;
                const bend = Math.max(18, (targetY - sourceY) / 2);
                return (
                  <g key={edge.id}>
                    <path
                      d={`M ${sourceX} ${sourceY} C ${sourceX} ${sourceY + bend}, ${targetX} ${targetY - bend}, ${targetX} ${targetY}`}
                      fill="none"
                      stroke="#94a3b8"
                      strokeWidth="1.25"
                    />
                    <circle cx={sourceX} cy={sourceY} r="2.5" fill="#ffffff" stroke="#3b82f6" strokeWidth="1.25" />
                    <circle cx={targetX} cy={targetY} r="2.5" fill="#ffffff" stroke="#3b82f6" strokeWidth="1.25" />
                  </g>
                );
              })}
            </svg>

            {layout.nodes.map((node) => {
              const selected = selectedNodeId === node.id;
              const nodeStyle = { left: node.x, top: node.y, width: CARD_WIDTH, height: CARD_HEIGHT };
              if (node.kind === "goal") {
                return (
                  <button
                    key={node.id}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => setSelectedNodeId(node.id)}
                    className={cn(
                      "absolute flex flex-col rounded-lg border bg-white p-2 text-left shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500",
                      selected ? "border-blue-400" : "border-slate-200",
                    )}
                    style={nodeStyle}
                  >
                    <span className="flex items-center justify-between gap-1.5">
                      <span className="flex min-w-0 items-center gap-1.5">
                        <Crown aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-slate-500" />
                        <span className="truncate text-[11px] font-semibold text-slate-900">{text("团队目标", "Team goal")}</span>
                      </span>
                      <Badge className="px-1.5 py-0 text-[9px]" tone="running">
                        {goalStatusLabel(team.active_goal?.status ?? "active", text)}
                      </Badge>
                    </span>
                    <span className="mt-1 line-clamp-1 text-[10px] leading-4 text-slate-600">
                      {team.active_goal?.objective ?? team.name}
                    </span>
                    <span className="mt-auto text-[9px] text-slate-400">
                      {text(`${visibleTasks.length} 个任务节点`, `${visibleTasks.length} task nodes`)}
                    </span>
                  </button>
                );
              }

              const task = node.task!;
              const owner = task.owner_slot_id ? agentBySlotId.get(task.owner_slot_id) : null;
              const needsCorrection = Boolean(task.metadata_json?.needs_correction);
              const inCycle = layout.cycleTaskIds.includes(task.id);
              const dependencyNames = taskSubjects(dependenciesByTaskId.get(task.id) ?? [], taskById);
              const dependentNames = (dependentsByTaskId.get(task.id) ?? []).map((candidate) => candidate.subject);
              const detailId = `team-task-graph-detail-${task.id}`;
              return (
                <button
                  key={node.id}
                  type="button"
                  aria-pressed={selected}
                  aria-describedby={detailId}
                  aria-label={text(
                    `${task.subject}，${teamTaskStatusLabel(task.status)}，${dependencyNames.length} 个依赖，${dependentNames.length} 个后续任务`,
                    `${task.subject}, ${teamTaskStatusLabel(task.status)}, ${dependencyNames.length} dependencies, ${dependentNames.length} downstream tasks`,
                  )}
                  onClick={() => {
                    setSelectedNodeId(node.id);
                    if (task.owner_slot_id) onSelectAgent(task.owner_slot_id);
                  }}
                  className={cn(
                    "absolute flex flex-col rounded-lg border bg-white p-2 text-left shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500",
                    needsCorrection
                      ? "border-red-300 bg-red-50/80"
                      : inCycle
                        ? "border-amber-300 bg-amber-50/80"
                        : selected
                          ? "border-blue-400 bg-blue-50/70"
                          : "border-slate-200 hover:border-slate-300",
                  )}
                  style={nodeStyle}
                >
                  <span id={detailId} className="sr-only">
                    {text("描述", "Description")}: {task.description || text("无", "none")}.
                    {text("依赖任务", "Dependencies")}: {dependencyNames.join("、") || text("无", "none")}.
                    {text("后续任务", "Downstream tasks")}: {dependentNames.join("、") || text("无", "none")}.
                    {inCycle ? text("检测到循环依赖，已按稳定顺序降级展示。", "A cyclic dependency was detected and shown with a stable fallback.") : ""}
                  </span>
                  <span className="flex items-start justify-between gap-1.5">
                    <span className="flex min-w-0 items-center gap-1.5">
                      <span
                        aria-hidden="true"
                        className={cn(
                          "flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-white",
                          task.status === "completed"
                            ? "bg-emerald-500"
                            : needsCorrection
                              ? "bg-red-500"
                              : inCycle
                                ? "bg-amber-500"
                                : "bg-slate-600",
                        )}
                      >
                        {task.status === "completed" ? <Check className="h-3 w-3" /> : needsCorrection || inCycle ? <CircleAlert className="h-3 w-3" /> : <ListTodo className="h-3 w-3" />}
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate text-[11px] font-semibold text-slate-900">{task.subject}</span>
                        <span className="block truncate text-[9px] text-slate-400">
                          {owner?.agent_name ?? text("队长", "Leader")}
                        </span>
                      </span>
                    </span>
                    <Badge className="px-1.5 py-0 text-[9px]" tone={needsCorrection ? "failed" : teamTaskStatusTone(task.status)}>
                      {needsCorrection ? text("需纠偏", "Needs fix") : teamTaskStatusLabel(task.status)}
                    </Badge>
                  </span>
                  <span className="mt-0.5 line-clamp-1 text-[10px] leading-4 text-slate-500">
                    {task.description || text("无描述", "No description")}
                  </span>
                  <span className="mt-auto text-[9px] text-slate-400">
                    {text("依赖", "Deps")} {dependencyNames.length} · {text("后续", "Next")} {dependentNames.length}
                    {inCycle ? ` · ${text("循环", "cycle")}` : ""}
                  </span>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="flex h-full min-h-64 items-center justify-center p-6">
            <div className="border border-dashed border-slate-200 bg-white px-5 py-8 text-center text-xs text-slate-400">
              {text("暂无团队任务", "No team tasks")}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
