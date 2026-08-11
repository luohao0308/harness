export type TaskStatus =
  | "CREATED"
  | "PLANNING"
  | "PLANNED"
  | "RUNNING"
  | "WAITING_SUBAGENTS"
  | "WAITING_APPROVAL"
  | "FAILED"
  | "COMPLETED"
  | "CANCELLED"
  | "pending"
  | "in_progress"
  | "completed";

export interface Task {
  id: string;
  organization_id: string | null;
  agent_id: string | null;
  created_by: string | null;
  title: string;
  goal: string;
  status: TaskStatus | string;
  model_provider: string;
  model_name: string;
  max_runtime_seconds: number;
  max_subagents: number;
  enable_sandbox: boolean;
  enable_network: boolean;
  capability_snapshot_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface TaskWithSyncMetadata extends Task {
  sync_version: number;
  last_synced_at: string | null;
  server_updated_at: string | null;
  is_local_only: boolean;
  has_local_changes: boolean;
  conflict_detected: boolean;
}

export type SyncOperationType = "CREATE" | "UPDATE" | "DELETE";
export type OperationStatus = "PENDING" | "IN_PROGRESS" | "FAILED" | "COMPLETED";

export interface SyncOperation {
  id: string;
  operation_type: SyncOperationType;
  entity_type: "task";
  entity_id: string;
  payload_json: string;
  client_timestamp: string;
  retry_count: number;
  last_retry_at: string | null;
  status: OperationStatus;
  error_message: string | null;
  created_at: string;
}

export interface TaskQueryOptions {
  status?: string;
  agent_id?: string;
  since?: string;
  limit?: number;
}

export interface DesktopTaskSyncResponse {
  id: string;
  title: string;
  goal: string;
  status: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  model_provider: string;
  model_name: string;
}

export interface DesktopSyncResponse {
  tasks: DesktopTaskSyncResponse[];
  server_timestamp: string;
}

export interface DesktopConflictInfo {
  entity_id: string;
  entity_type: string;
  server_version: Record<string, unknown>;
  client_version: Record<string, unknown>;
}

export interface DesktopSyncOperationsResponse {
  applied: number;
  conflicts: DesktopConflictInfo[];
}

export interface DesktopSyncOperation {
  type: "create" | "update" | "delete";
  entity_type: "task";
  entity_id: string;
  data: Record<string, unknown> | null;
  timestamp: string;
}

export interface SyncSnapshot {
  tasks: TaskWithSyncMetadata[];
  pendingOperations: number;
  conflicts: DesktopConflictInfo[];
  lastSyncAt: string | null;
  offline: boolean;
}

export const DEFAULT_TASK_FIELDS = {
  organization_id: null,
  agent_id: null,
  created_by: null,
  max_runtime_seconds: 3600,
  max_subagents: 2,
  enable_sandbox: true,
  enable_network: false,
  capability_snapshot_json: {},
} as const;

export function normalizeDesktopTask(task: DesktopTaskSyncResponse): Task {
  return {
    ...DEFAULT_TASK_FIELDS,
    id: task.id,
    title: task.title,
    goal: task.goal,
    status: task.status,
    model_provider: task.model_provider,
    model_name: task.model_name,
    created_at: task.created_at,
    updated_at: task.updated_at,
    completed_at: task.completed_at,
  };
}

export function taskStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    CREATED: "已创建",
    PLANNING: "规划中",
    PLANNED: "已规划",
    RUNNING: "运行中",
    WAITING_SUBAGENTS: "等待子 Agent",
    WAITING_APPROVAL: "待审批",
    FAILED: "失败",
    COMPLETED: "已完成",
    CANCELLED: "已取消",
    pending: "待处理",
    in_progress: "运行中",
    completed: "已完成",
  };
  return labels[status] ?? status;
}

export function isTerminalStatus(status: string): boolean {
  return ["FAILED", "COMPLETED", "CANCELLED", "completed"].includes(status);
}
