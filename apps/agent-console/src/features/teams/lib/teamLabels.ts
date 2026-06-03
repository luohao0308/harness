import type { TeamAgent, TeamTask } from "../../tasks/api";

export function teamAgentStatusLabel(status: TeamAgent["status"]) {
  const labels: Record<TeamAgent["status"], string> = {
    pending: "待唤醒",
    idle: "待命",
    active: "协作中",
    completed: "已结束",
    failed: "失败",
  };
  return labels[status];
}

export function teamAgentStatusTone(status: TeamAgent["status"]) {
  if (status === "active") return "running";
  if (status === "completed") return "success";
  if (status === "failed") return "failed";
  if (status === "pending") return "pending";
  return "neutral";
}

export function teamTaskStatusLabel(status: TeamTask["status"]) {
  const labels: Record<TeamTask["status"], string> = {
    pending: "待处理",
    in_progress: "进行中",
    completed: "已完成",
    deleted: "已删除",
  };
  return labels[status];
}

export function teamTaskStatusTone(status: TeamTask["status"]) {
  if (status === "in_progress") return "running";
  if (status === "completed") return "success";
  if (status === "deleted") return "neutral";
  return "pending";
}
