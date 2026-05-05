const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const DEV_BEARER_TOKEN = import.meta.env.VITE_DEV_BEARER_TOKEN ?? "dev-engineer-token";

function authHeaders(): HeadersInit {
  return {
    Authorization: `Bearer ${DEV_BEARER_TOKEN}`,
  };
}

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

export type ModelSettings = {
  default_provider: string;
  default_model: string;
  providers: Array<Record<string, unknown>>;
  rate_limits: Record<string, unknown>;
  health: Record<string, unknown>;
};

export type PolicySettings = {
  risk_levels: Array<Record<string, unknown>>;
  approvals: Record<string, unknown>;
  sandbox: Record<string, unknown>;
  audit: Record<string, unknown>;
};

export type WarmPool = {
  enabled: boolean;
  min_size: number;
  max_size: number;
  idle: number;
  busy: number;
  failed: number;
  hit_total: number;
  miss_total: number;
};

export type Subagent = {
  id: string;
  task_id: string;
  parent_agent_id: string | null;
  agent_type: string;
  status: string;
  context_json: Record<string, unknown>;
  started_at: string | null;
  completed_at: string | null;
  timeout_at: string | null;
};

export type TaskResult = {
  task_id: string;
  status: TaskStatus;
  summary: string | null;
  execution_plan: Record<string, unknown> | null;
  artifacts: Array<{
    name: string;
    artifact_type: string;
    description: string;
    status: string;
  }>;
  last_sequence: number;
  pending: boolean;
};

export type ReplayResult = {
  task_id: string;
  sequence: number;
  state_summary: string;
  failure_point: Record<string, unknown> | null;
  diagnosis: string;
  requires_manual_review: boolean;
};

export type ModelCall = {
  id: string;
  model_provider: string;
  model_name: string;
  status: string;
  prompt_tokens: number;
  completion_tokens: number;
  duration_ms: number;
  created_at: string;
};

export type ToolCall = {
  id: string;
  tool_name: string;
  status: string;
  risk_level: string;
  requires_sandbox: boolean;
  duration_ms: number;
  created_at: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...authHeaders(), ...init?.headers },
    ...init,
  });
  if (!response.ok) {
    let detail = "";
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail ? `：${payload.detail}` : "";
    } catch {
      detail = "";
    }
    throw new Error(`请求失败 ${response.status}${detail}`);
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

export async function cancelTask(taskId: string) {
  return request<Task>(`/api/tasks/${taskId}/cancel`, { method: "POST" });
}

export async function resumeTask(taskId: string) {
  return request<Task>(`/api/tasks/${taskId}/resume`, { method: "POST" });
}

export async function getTaskResult(taskId: string) {
  return request<TaskResult>(`/api/tasks/${taskId}/result`);
}

export async function replayTask(taskId: string, sequence?: number) {
  return request<ReplayResult>(`/api/tasks/${taskId}/replay`, {
    method: "POST",
    body: JSON.stringify({ sequence }),
  });
}

export async function listTaskEvents(taskId: string) {
  return request<{ items: AgentEvent[]; next_cursor: string | null }>(
    `/api/tasks/${taskId}/events`,
  );
}

export async function listTaskSubagents(taskId: string) {
  return request<{ items: Subagent[]; next_cursor: string | null }>(
    `/api/tasks/${taskId}/subagents`,
  );
}

export async function listModelCalls(taskId: string) {
  return request<{ items: ModelCall[]; next_cursor: string | null }>(
    `/api/tasks/${taskId}/model-calls`,
  );
}

export async function listToolCalls(taskId: string) {
  return request<{ items: ToolCall[]; next_cursor: string | null }>(
    `/api/tasks/${taskId}/tool-calls`,
  );
}

export function taskEventStreamUrl(taskId: string) {
  const params = new URLSearchParams({ access_token: DEV_BEARER_TOKEN });
  return `${API_BASE_URL}/api/tasks/${taskId}/events/stream?${params.toString()}`;
}

export async function getModelSettings() {
  return request<ModelSettings>("/api/settings/models");
}

export async function getPolicySettings() {
  return request<PolicySettings>("/api/settings/policies");
}

export async function getWarmPool() {
  return request<WarmPool>("/api/sandboxes/warm-pool");
}
