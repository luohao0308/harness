const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export type TaskStatus =
  | "CREATED"
  | "PLANNING"
  | "RUNNING"
  | "WAITING_SUBAGENTS"
  | "FAILED"
  | "COMPLETED"
  | "CANCELLED";

export type Task = {
  id: string;
  title: string;
  goal: string;
  status: TaskStatus;
  model_provider: string;
  model_name: string;
  max_runtime_seconds: number;
  max_subagents: number;
  enable_sandbox: boolean;
  enable_network: boolean;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

export type TaskCreatePayload = {
  title: string;
  goal: string;
  model_provider: string;
  model_name: string;
  max_runtime_seconds: number;
  max_subagents: number;
  enable_sandbox: boolean;
  enable_network: boolean;
};

export type AgentEvent = {
  id: string;
  task_id: string;
  agent_run_id: string | null;
  sequence: number;
  event_type: string;
  payload_json: Record<string, unknown>;
  actor_type: string;
  actor_id: string | null;
  trace_id: string | null;
  created_at: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function listTasks() {
  return request<{ items: Task[]; next_cursor: string | null }>("/api/tasks");
}

export async function createTask(payload: TaskCreatePayload) {
  return request<Task>("/api/tasks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getTask(taskId: string) {
  return request<Task>(`/api/tasks/${taskId}`);
}

export async function startTask(taskId: string) {
  return request<Task>(`/api/tasks/${taskId}/start`, { method: "POST" });
}

export async function listTaskEvents(taskId: string) {
  return request<{ items: AgentEvent[]; next_cursor: string | null }>(
    `/api/tasks/${taskId}/events`,
  );
}

export function taskEventStreamUrl(taskId: string) {
  return `${API_BASE_URL}/api/tasks/${taskId}/events/stream`;
}
