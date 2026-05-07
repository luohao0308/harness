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
  circuit_breaker: Record<string, unknown>;
};

export type ModelFallbackEvent = {
  event_id: string;
  task_id: string;
  sequence: number;
  primary_provider: string | null;
  primary_model: string | null;
  fallback_provider: string;
  fallback_model: string;
  fallback_index: number;
  reason: string | null;
  trace_id: string | null;
  created_at: string;
};

export type ModelFallbackSummary = {
  organization_id: string | null;
  fallback_total: number;
  primary_failure_total: number;
  providers: CountItem[];
  recent_events: ModelFallbackEvent[];
};

export type ModelHealth = {
  provider: string;
  model: string;
  status: string;
  mode: string;
  checked_at: string;
  latency_ms: number;
  error_message: string | null;
  circuit_status: string;
  circuit_open_until: string | null;
  consecutive_failures: number;
};

export type ModelHealthPage = {
  items: ModelHealth[];
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

export type SandboxQuotaUsage = {
  organization_id: string | null;
  configured_memory_mb: number;
  configured_cpus: string;
  configured_workspace_quota_mb: number;
  configured_network_enabled: boolean;
  configured_network_allowlist: string[];
  sandbox_total: number;
  running_total: number;
  destroyed_total: number;
  memory_limit_mb_total: number;
  running_memory_limit_mb_total: number;
  cpu_limit_total: number;
  running_cpu_limit_total: number;
  network_enabled_total: number;
  warm_pool_reused_total: number;
  latest_created_at: string | null;
};

export type SandboxQuotaHistoryItem = {
  id: string;
  task_id: string;
  container_id: string;
  status: string;
  cpu_limit: string;
  cpu_limit_value: number;
  memory_limit_mb: number;
  network_enabled: boolean;
  warm_pool_reused: boolean;
  lifetime_seconds: number | null;
  created_at: string;
  destroyed_at: string | null;
};

export type CountItem = {
  name: string;
  count: number;
};

export type ObservabilitySummary = {
  tasks_by_status: CountItem[];
  subagents_by_status: CountItem[];
  model_calls_by_status: CountItem[];
  tool_calls_by_status: CountItem[];
  sandboxes_by_status: CountItem[];
  subagent_queue: {
    pending: number;
    running: number;
    success: number;
    failed: number;
    timeout: number;
    cancelled: number;
    active_total: number;
    capacity: number;
    available_slots: number;
    utilization_percent: number;
  };
  warm_pool: WarmPool;
  event_total: number;
  task_total: number;
  failed_task_total: number;
  model_call_total: number;
  tool_call_total: number;
  sandbox_total: number;
};

export type ObservabilityLogEntry = {
  timestamp: string;
  level: string;
  service: string;
  message: string;
  trace_id: string | null;
  task_id: string | null;
  agent_run_id: string | null;
  event_type: string | null;
  payload_json: Record<string, unknown>;
  source: string;
};

export type ObservabilityLogs = {
  items: ObservabilityLogEntry[];
  next_cursor: string | null;
  source: string;
  facets: Record<string, CountItem[]>;
};

export type ObservabilityTraceSpan = {
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  name: string;
  service: string;
  start_time: string;
  duration_ms: number;
  attributes: Record<string, unknown>;
  source: string;
};

export type ObservabilityTrace = {
  trace_id: string;
  spans: ObservabilityTraceSpan[];
  source: string;
  service_nodes: Array<{
    service: string;
    span_count: number;
    error_count: number;
    total_duration_ms: number;
  }>;
  service_edges: Array<{
    source: string;
    target: string;
    span_count: number;
    total_duration_ms: number;
  }>;
};

export type GrafanaDashboard = {
  uid: string;
  title: string;
  url: string;
  tags: string[];
  source: string;
};

export type GrafanaDashboards = {
  items: GrafanaDashboard[];
  next_cursor: string | null;
};

export type ObservabilityServiceHealth = {
  name: string;
  status: string;
  url: string;
  latency_ms: number | null;
  error_message: string | null;
  alert_status: string;
  alert_severity: string;
  runbook_url: string;
};

export type ObservabilityServicesHealth = {
  services: ObservabilityServiceHealth[];
};

export type ObservabilityExportItem = {
  name: string;
  title: string;
  description: string;
  method: string;
  url: string;
  format: string;
  required_roles: string[];
};

export type ObservabilityExports = {
  items: ObservabilityExportItem[];
};

export type ObservabilityExportHistoryItem = {
  id: string;
  export_type: string;
  filename: string;
  content_type: string;
  format: string;
  source: string;
  row_count: number;
  filter_json: Record<string, unknown>;
  storage_driver: string;
  size_bytes: number;
  sha256: string;
  download_url: string;
  created_at: string;
};

export type ObservabilityExportHistory = {
  items: ObservabilityExportHistoryItem[];
  next_cursor: string | null;
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

export type SubagentListItem = Subagent & {
  task_title: string;
  task_status: string;
  step_key: string | null;
};

export type SubagentRecoveryResponse = {
  batch_id: string;
  task_id: string | null;
  trigger: string;
  replay_sequence: number;
  stale_after_seconds: number;
  enqueue: boolean;
  scanned_count: number;
  recovered_count: number;
  action_counts: Record<string, number>;
  recovered: Array<{
    id: string;
    previous_status: string;
    status: string;
    action: string;
    reason: string;
    replay_status: string | null;
    takeover_generation: number | null;
    takeover_owner: string | null;
    takeover_at: string | null;
  }>;
  completed_at: string;
};

export type SubagentBulkActionResult = {
  action: string;
  requested_count: number;
  succeeded_count: number;
  failed_count: number;
  items: Array<{
    id: string;
    previous_status: string | null;
    status: string | null;
    action: string;
    success: boolean;
    error_message: string | null;
  }>;
};

export type SubagentRecoveryBatch = SubagentRecoveryResponse & {
  organization_id: string | null;
  lock_acquired: boolean;
  task_count: number;
  recovered_by_task: Array<Record<string, unknown>>;
};

export type SubagentRecoverySummary = {
  organization_id: string | null;
  batch_total: number;
  task_total: number;
  scanned_total: number;
  recovered_total: number;
  lock_skipped_total: number;
  action_counts: Record<string, number>;
  latest_completed_at: string | null;
  tasks: Array<{
    task_id: string;
    scanned_count: number;
    recovered_count: number;
    latest_batch_id: string;
    latest_completed_at: string;
    latest_replay_sequence: number;
  }>;
  recent_batches: SubagentRecoveryBatch[];
};

export type SubagentRecoveryOrganizationSummary = {
  organization_id: string | null;
  batch_total: number;
  task_total: number;
  scanned_total: number;
  recovered_total: number;
  lock_skipped_total: number;
  action_counts: Record<string, number>;
  latest_completed_at: string | null;
};

export type SubagentRecoveryGlobalSummary = {
  organization_count: number;
  batch_total: number;
  task_total: number;
  scanned_total: number;
  recovered_total: number;
  lock_skipped_total: number;
  action_counts: Record<string, number>;
  latest_completed_at: string | null;
  organizations: SubagentRecoveryOrganizationSummary[];
  recent_batches: SubagentRecoveryBatch[];
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
  subagent_results: Array<{
    id: string;
    step_key: string | null;
    status: string;
    summary: string | null;
    tool_results: Array<{
      tool_call_id: string;
      tool_name: string;
      status: string;
      allowed: boolean;
      duration_ms: number;
      input_json: Record<string, unknown>;
      output: Record<string, unknown>;
      error_message: string | null;
    }>;
    artifacts: Array<{
      name: string;
      artifact_type: string;
      source_tool: string;
      description: string;
      status: string;
      preview: string | null;
    }>;
    react_trace: Array<Record<string, unknown>>;
    context_summary: Record<string, unknown>;
    completed_at: string | null;
  }>;
  last_sequence: number;
  pending: boolean;
};

export type TaskPlanStep = {
  step_key: string;
  description: string;
  execution_mode: string;
  requires_sandbox: boolean;
  can_spawn_subagent: boolean;
  tool_hints: string[];
  acceptance_criteria: string[];
  risk_level: string;
  artifact_expectations: string[];
  quality_notes: string[];
  status: string;
  assigned_agent_id: string | null;
  error_message: string | null;
  trace_summary: string | null;
  last_event_sequence: number | null;
  execution_trace: Array<Record<string, unknown>>;
};

export type TaskPlan = {
  id: string;
  task_id: string;
  version: number;
  status: string;
  summary: string | null;
  planner_source: string;
  planner_attempts: number;
  planner_prompt_version: string;
  quality_score: number;
  validation_warnings: string[];
  quality_gates: Record<string, boolean>;
  plan_json: Record<string, unknown>;
  steps: TaskPlanStep[];
  created_at: string;
};

export type TaskPlanVersionSummary = {
  id: string;
  task_id: string;
  version: number;
  status: string;
  summary: string | null;
  planner_source: string;
  planner_attempts: number;
  step_count: number;
  created_at: string;
};

export type TaskPlanDiff = {
  task_id: string;
  from_version: number;
  to_version: number;
  added: number;
  removed: number;
  changed: number;
  unchanged: number;
  step_diffs: Array<{
    step_key: string;
    change_type: string;
    from_step: Record<string, unknown> | null;
    to_step: Record<string, unknown> | null;
  }>;
};

export type TaskStep = {
  id: string;
  task_id: string;
  plan_id: string;
  step_key: string;
  description: string;
  status: string;
  execution_mode: string;
  assigned_agent_id: string | null;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
};

export type ReplayResult = {
  task_id: string;
  sequence: number;
  state_summary: string;
  failure_point: Record<string, unknown> | null;
  diagnosis: string;
  requires_manual_review: boolean;
};

export type StepResumeResult = {
  task_id: string;
  status: TaskStatus;
  plan_id: string;
  resume_mode: string;
  resume_from_step_key: string;
  requested_step_keys: string[];
  skipped_step_keys: string[];
  resumed_step_keys: string[];
  completed_step_keys: string[];
  pending_step_keys: string[];
  failed_step_key: string | null;
  error_message: string | null;
  last_sequence: number;
};

export type ModelCall = {
  id: string;
  task_id: string;
  agent_run_id: string | null;
  trace_id: string | null;
  model_provider: string;
  model_name: string;
  status: string;
  prompt_tokens: number;
  completion_tokens: number;
  duration_ms: number;
  request_json: Record<string, unknown>;
  response_json: Record<string, unknown>;
  error_message: string | null;
  created_at: string;
};

export type ToolCall = {
  id: string;
  task_id?: string;
  agent_run_id?: string | null;
  trace_id?: string | null;
  tool_name: string;
  status: string;
  risk_level: string;
  requires_sandbox: boolean;
  sandbox_id?: string | null;
  duration_ms: number;
  input_json?: Record<string, unknown>;
  output_json?: Record<string, unknown>;
  output_kind: string;
  output_summary: string;
  timeout_category?: string | null;
  error_message?: string | null;
  created_at: string;
};

export type ToolExecutePayload = {
  tool_name: string;
  input_json: Record<string, unknown>;
  sandbox_id?: string | null;
  create_sandbox?: boolean;
};

export type ToolExecuteResult = {
  tool_call: ToolCall;
  allowed: boolean;
  output: Record<string, unknown>;
};

export type ToolCallFilters = {
  tool_name?: string;
  status?: string;
  risk_level?: string;
  trace_id?: string;
  limit?: number;
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

export async function resumeTaskSteps(taskId: string, stepKeys: string[]) {
  return request<StepResumeResult>(`/api/tasks/${taskId}/steps/resume`, {
    method: "POST",
    body: JSON.stringify({ step_keys: stepKeys, resume_mode: "from_first_selected" }),
  });
}

export async function getTaskResult(taskId: string) {
  return request<TaskResult>(`/api/tasks/${taskId}/result`);
}

export async function getTaskPlan(taskId: string) {
  return request<TaskPlan>(`/api/tasks/${taskId}/plan`);
}

export async function listTaskPlanVersions(taskId: string) {
  return request<{ items: TaskPlanVersionSummary[]; next_cursor: string | null }>(
    `/api/tasks/${taskId}/plans`,
  );
}

export async function getTaskPlanDiff(taskId: string, fromVersion: number, toVersion: number) {
  const params = new URLSearchParams({
    from_version: String(fromVersion),
    to_version: String(toVersion),
  });
  return request<TaskPlanDiff>(`/api/tasks/${taskId}/plans/diff?${params.toString()}`);
}

export async function listTaskSteps(taskId: string) {
  return request<{ items: TaskStep[]; next_cursor: string | null }>(
    `/api/tasks/${taskId}/steps`,
  );
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

export async function listSubagents(params?: { status?: string; limit?: number }) {
  const searchParams = new URLSearchParams();
  if (params?.status && params.status !== "ALL") {
    searchParams.set("status", params.status);
  }
  if (params?.limit) {
    searchParams.set("limit", String(params.limit));
  }
  const suffix = searchParams.toString() ? `?${searchParams.toString()}` : "";
  return request<{ items: SubagentListItem[]; next_cursor: string | null }>(
    `/api/subagents${suffix}`,
  );
}

export async function getSubagent(subagentId: string) {
  return request<Subagent>(`/api/subagents/${subagentId}`);
}

export async function cancelSubagent(subagentId: string) {
  return request<Subagent>(`/api/subagents/${subagentId}/cancel`, { method: "POST" });
}

export async function bulkCancelSubagents(subagentIds: string[]) {
  return request<SubagentBulkActionResult>("/api/subagents/bulk", {
    method: "POST",
    body: JSON.stringify({ action: "cancel", subagent_ids: subagentIds }),
  });
}

export async function listTaskSubagentRecoveryBatches(taskId: string) {
  return request<{ items: SubagentRecoveryBatch[]; next_cursor: string | null }>(
    `/api/tasks/${taskId}/subagents/recovery-batches`,
  );
}

export async function recoverTaskSubagents(taskId: string) {
  return request<SubagentRecoveryResponse>(`/api/tasks/${taskId}/subagents/recover`, {
    method: "POST",
    body: JSON.stringify({ stale_after_seconds: 900, enqueue: false }),
  });
}

export async function getSubagentRecoverySummary() {
  return request<SubagentRecoverySummary>("/api/subagents/recovery/summary");
}

export async function getSubagentRecoveryGlobalSummary(limit = 100) {
  return request<SubagentRecoveryGlobalSummary>(
    `/api/subagents/recovery/global-summary?limit=${limit}`,
  );
}

export async function listModelCalls(taskId: string) {
  return request<{ items: ModelCall[]; next_cursor: string | null }>(
    `/api/tasks/${taskId}/model-calls`,
  );
}

export async function listToolCalls(taskId: string, params?: ToolCallFilters) {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== "") {
      searchParams.set(key, String(value));
    }
  }
  const suffix = searchParams.toString() ? `?${searchParams.toString()}` : "";
  return request<{ items: ToolCall[]; next_cursor: string | null }>(
    `/api/tasks/${taskId}/tool-calls${suffix}`,
  );
}

export async function executeTaskTool(taskId: string, payload: ToolExecutePayload) {
  return request<ToolExecuteResult>(`/api/tasks/${taskId}/tools/execute`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function taskEventStreamUrl(taskId: string) {
  const params = new URLSearchParams({ access_token: DEV_BEARER_TOKEN });
  return `${API_BASE_URL}/api/tasks/${taskId}/events/stream?${params.toString()}`;
}

export async function getModelSettings() {
  return request<ModelSettings>("/api/settings/models");
}

export async function getModelHealth() {
  return request<ModelHealthPage>("/api/settings/models/health");
}

export async function getModelFallbackSummary(limit = 20) {
  return request<ModelFallbackSummary>(`/api/settings/models/fallbacks?limit=${limit}`);
}

export async function getPolicySettings() {
  return request<PolicySettings>("/api/settings/policies");
}

export async function getWarmPool() {
  return request<WarmPool>("/api/sandboxes/warm-pool");
}

export async function getSandboxQuotaUsage() {
  return request<SandboxQuotaUsage>("/api/sandboxes/quota/usage");
}

export async function listSandboxQuotaHistory(limit = 100) {
  return request<{ items: SandboxQuotaHistoryItem[]; next_cursor: string | null }>(
    `/api/sandboxes/quota/history?limit=${limit}`,
  );
}

export async function getObservabilitySummary() {
  return request<ObservabilitySummary>("/api/observability/summary");
}

export async function listObservabilityLogs(params?: {
  task_id?: string;
  trace_id?: string;
  service?: string;
  event_type?: string;
  limit?: number;
}) {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== "") {
      searchParams.set(key, String(value));
    }
  }
  const suffix = searchParams.toString() ? `?${searchParams.toString()}` : "";
  return request<ObservabilityLogs>(`/api/observability/logs${suffix}`);
}

export async function getObservabilityTrace(
  traceId: string,
  params?: {
    service?: string;
    span_name?: string;
    attribute_key?: string;
    attribute_value?: string;
  },
) {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== "") {
      searchParams.set(key, String(value));
    }
  }
  const suffix = searchParams.toString() ? `?${searchParams.toString()}` : "";
  return request<ObservabilityTrace>(
    `/api/observability/traces/${encodeURIComponent(traceId)}${suffix}`,
  );
}

export async function listGrafanaDashboards() {
  return request<GrafanaDashboards>("/api/observability/grafana/dashboards");
}

export async function getObservabilityServicesHealth() {
  return request<ObservabilityServicesHealth>("/api/observability/services/health");
}

export async function listObservabilityExports() {
  return request<ObservabilityExports>("/api/observability/exports");
}

export async function listObservabilityExportHistory() {
  return request<ObservabilityExportHistory>("/api/observability/exports/history");
}

export async function downloadObservabilityExport(path: string) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: authHeaders(),
  });
  if (!response.ok) {
    let message = response.statusText;
    try {
      const payload = await response.json();
      message = payload.detail ?? message;
    } catch {
      // Keep the HTTP status text when the export response is not JSON.
    }
    throw new Error(message);
  }
  const disposition = response.headers.get("content-disposition") ?? "";
  return {
    blob: await response.blob(),
    filename: contentDispositionFilename(disposition) ?? "observability-export.json",
  };
}

function contentDispositionFilename(disposition: string) {
  const match = disposition.match(/filename="([^"]+)"/);
  return match?.[1];
}
