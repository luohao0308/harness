/**
 * TeamActivity event schema
 * Represents real-time activity stream events for team collaboration
 */

export type TeamActivityAction =
  | "terminal_created"
  | "terminal_shared"
  | "comment_added"
  | "agent_spawned"
  | "agent_completed"
  | "task_assigned"
  | "task_completed";

export interface TeamActivity {
  id: string;
  userId: string;
  userName: string;
  action: TeamActivityAction;
  terminalId?: string;
  terminalName?: string;
  agentSlotId?: string;
  agentName?: string;
  taskId?: string;
  taskSubject?: string;
  comment?: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

/**
 * Type guard for TeamActivity
 */
export function isTeamActivity(value: unknown): value is TeamActivity {
  if (!value || typeof value !== "object") return false;
  const activity = value as Record<string, unknown>;

  return (
    typeof activity.id === "string" &&
    typeof activity.userId === "string" &&
    typeof activity.userName === "string" &&
    typeof activity.action === "string" &&
    typeof activity.timestamp === "string"
  );
}
