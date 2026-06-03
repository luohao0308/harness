const DEFAULT_API_BASE_URL = "/";

function stripTrailingSlash(value: string) {
  return value.replace(/\/$/, "");
}

function isLoopbackHost(hostname: string) {
  const normalized = hostname.toLowerCase().replace(/^\[|\]$/g, "");
  return normalized === "localhost" || normalized === "127.0.0.1" || normalized === "0.0.0.0" || normalized === "::1";
}

function hostForUrl(hostname: string) {
  return hostname.includes(":") && !hostname.startsWith("[") ? `[${hostname}]` : hostname;
}

export function resolveApiBaseUrl(
  configured = import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE_URL,
  pageHostname = typeof window === "undefined" ? null : window.location.hostname,
) {
  const baseUrl = configured.trim() || DEFAULT_API_BASE_URL;
  if (baseUrl.startsWith("/")) {
    return stripTrailingSlash(baseUrl);
  }

  if (!pageHostname) {
    return stripTrailingSlash(baseUrl);
  }

  try {
    const url = new URL(baseUrl);
    const pageHost = pageHostname;
    if (isLoopbackHost(url.hostname) && !isLoopbackHost(pageHost)) {
      url.hostname = hostForUrl(pageHost);
    }
    return stripTrailingSlash(url.toString());
  } catch {
    return stripTrailingSlash(baseUrl);
  }
}

export const API_BASE_URL = resolveApiBaseUrl();
const DEV_BEARER_TOKEN = import.meta.env.VITE_DEV_BEARER_TOKEN ?? "dev-engineer-token";
const DEV_ADMIN_BEARER_TOKEN =
  import.meta.env.VITE_DEV_ADMIN_BEARER_TOKEN ?? "dev-admin-token";
export const KNOWLEDGE_ADMIN_CONTROLS_ENABLED = DEV_ADMIN_BEARER_TOKEN.trim().length > 0;
const KNOWLEDGE_SOURCE_CREATE_TIMEOUT_MS = 12_000;

function authHeaders(token = DEV_BEARER_TOKEN): HeadersInit {
  return {
    Authorization: `Bearer ${token}`,
  };
}

function apiRequestUrls(path: string) {
  const primary = `${API_BASE_URL}${path}`;
  if (!API_BASE_URL || API_BASE_URL.startsWith("/")) {
    return [primary];
  }
  return primary === path ? [primary] : [primary, path];
}

async function fetchApi(path: string, init?: RequestInit) {
  const urls = apiRequestUrls(path);
  let lastError: unknown = null;
  for (const url of urls) {
    try {
      return await fetch(url, init);
    } catch (error) {
      lastError = error;
    }
  }
  throw apiConnectionError(lastError, urls);
}

function apiConnectionError(error: unknown, urls = [API_BASE_URL || "/"]) {
  const detail = error instanceof Error ? error.message : String(error);
  return new Error(`无法连接 API (${urls.join(" -> ")})：${detail}`);
}

export type TaskStatus =
  | "CREATED"
  | "PLANNING"
  | "PLANNED"
  | "RUNNING"
  | "WAITING_SUBAGENTS"
  | "WAITING_APPROVAL"
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

export type AgentPlanPayload = {
  agent_id: string;
  title?: string | null;
  goal: string;
  model_provider: string;
  model_name: string;
  max_runtime_seconds: number;
  max_subagents: number;
  enable_sandbox: boolean;
  enable_network: boolean;
};

export type AgentDefinition = {
  id: string;
  name: string;
  description: string;
  role: string;
  status: string;
  model_provider: string;
  model_name: string;
  system_prompt: string;
  tools_json: string[];
  routing_tags: string[];
  max_parallel_assignments: number;
  capability_attachments?: AgentCapabilityAttachmentSummary[];
  created_at: string;
  updated_at: string;
};

export type AgentCapabilityAttachmentSummary = {
  attachment_id: string;
  capability_id: string;
  capability_key: string;
  capability_version_id: string;
  capability_type: string;
  enabled: boolean;
  priority: number;
  status: string;
};

export type AgentAssignment = {
  id: string;
  run_id: string;
  agent_id: string;
  parent_assignment_id: string | null;
  step_key: string | null;
  role: string;
  status: string;
  input_json: Record<string, unknown>;
  output_json: Record<string, unknown>;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type AgentHandoff = {
  id: string;
  run_id: string;
  from_assignment_id: string | null;
  to_assignment_id: string;
  handoff_type: string;
  status: string;
  payload_json: Record<string, unknown>;
  created_at: string;
  completed_at: string | null;
};

export type AgentOrchestrateResult = {
  run_id: string;
  strategy: string;
  routing_reasoning: string | null;
  assignments: AgentAssignment[];
  handoffs: AgentHandoff[];
  message: string;
};

export type TeamAgent = {
  id: string;
  team_id: string;
  slot_id: string;
  agent_id: string;
  role: "leader" | "teammate";
  agent_name: string;
  status: "pending" | "idle" | "active" | "completed" | "failed";
  model_provider: string;
  model_name: string;
  conversation_id: string | null;
  session_id: string | null;
  session_messages: AgentMessage[];
  metadata_json: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
};

export type TeamMailboxMessage = {
  id: string;
  team_id: string;
  to_agent_slot_id: string;
  from_agent_slot_id: string;
  type: string;
  content: string;
  summary: string | null;
  read: boolean;
  files_json: string[];
  metadata_json: Record<string, unknown>;
  created_at: string | null;
};

export type TeamTask = {
  id: string;
  team_id: string;
  subject: string;
  description: string;
  owner_slot_id: string | null;
  status: "pending" | "in_progress" | "completed" | "deleted";
  blocked_by_json: string[];
  blocks_json: string[];
  metadata_json: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
};

export type Team = {
  id: string;
  organization_id: string | null;
  name: string;
  status: string;
  workspace: string;
  workspace_mode: "shared" | "isolated";
  leader_slot_id: string;
  created_by: string | null;
  agents: TeamAgent[];
  messages: TeamMailboxMessage[];
  tasks: TeamTask[];
  unread_counts: Record<string, number>;
  team_tools: string[];
  created_at: string | null;
  updated_at: string | null;
};

export type TeamEvent = {
  id: string;
  team_id: string;
  sequence: number;
  event_type: string;
  payload_json: Record<string, unknown>;
  actor_type: string;
  actor_id: string | null;
  created_at: string | null;
};

export type TeamWakeStreamEvent =
  | { type: "status"; agent: TeamAgent }
  | { type: "delta"; slot_id: string; content: string }
  | { type: "done"; agent: TeamAgent; message?: AgentMessage; follow_up_slot_ids?: string[] }
  | { type: "error"; message: string; agent?: TeamAgent; slot_id?: string };

export type TeamMessageMode = "chat" | "markdown_plan" | "plan" | "goal";

export type TeamToolCallPayload = {
  from_agent_slot_id?: string | null;
  args?: Record<string, unknown>;
};

export type TeamToolCallResult = {
  tool_name: string;
  from_agent_slot_id: string | null;
  result: string;
};

export type TeamCreatePayload = {
  name: string;
  workspace?: string;
  workspace_mode?: "shared" | "isolated";
  leader_agent_id?: string;
  leader_name?: string;
  seed_messages?: Array<{
    role: "user" | "assistant" | "system";
    content: string;
    created_at?: string | null;
    metadata_json?: Record<string, unknown>;
  }>;
};

export type TeamAgentCreatePayload = {
  agent_id: string;
  agent_name: string;
  role: "teammate";
  model_provider?: string | null;
  model_name?: string | null;
};

export type TeamAgentUpdatePayload = {
  agent_name?: string | null;
  model_provider?: string | null;
  model_name?: string | null;
};

export type TeamMessageCreatePayload = {
  target: "leader" | "team" | string;
  content: string;
  from_agent_slot_id?: string;
  type?: string;
  summary?: string | null;
  files?: string[];
  mode?: TeamMessageMode;
};

export type TeamTaskCreatePayload = {
  subject: string;
  description?: string;
  owner?: string | null;
  ownerSlotId?: string | null;
  owner_slot_id?: string | null;
  blockedBy?: string[];
  blocked_by?: string[];
};

export type TeamTaskUpdatePayload = {
  status?: "pending" | "in_progress" | "completed" | "deleted";
  owner?: string | null;
  ownerSlotId?: string | null;
  owner_slot_id?: string | null;
  description?: string | null;
  blockedBy?: string[];
  blocked_by?: string[];
};

export type AgentSession = {
  id: string;
  organization_id: string | null;
  agent_id: string;
  created_by: string | null;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type AgentMessage = {
  id: string;
  session_id: string;
  agent_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export type AgentRunCreatePayload = AgentPlanPayload & {
  mode: "plan";
};

export type AgentPlanStreamEvent =
  | { type: "delta"; content: string }
  | {
      type: "run_created";
      run_id: string;
      status: string;
      step_count: number;
      message: string;
      context_assembly?: {
        context_manifest_id: string | null;
        mode: string | null;
        included_count: number;
        omitted_count: number;
        omission_reasons: string[];
      };
    }
  | { type: "error"; message: string };

export type AgentChatStreamMessage = {
  id: string;
  parent_id: string | null;
  children_ids: string[];
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  state: "draft" | "streaming" | "paused" | "done" | "error";
  run_id?: string;
  metadata: Record<string, unknown>;
  tool_calls: Array<Record<string, unknown>>;
  artifacts: Array<Record<string, unknown>>;
  created_at?: string | null;
};

export type ToolMention = {
  name: string;
  source?: string | null;
  payload: Record<string, unknown>;
};

export type AgentAttachmentPayload = {
  name: string;
  mime_type: string;
  size_bytes: number;
  content_text?: string | null;
  content_status: "ready" | "unsupported" | "error";
  truncated?: boolean;
};

export type AgentChatStreamPayload = {
  mode?: "chat" | "markdown_plan" | "plan";
  orchestration_mode?: "auto" | "none" | "multi_agent" | "subagent";
  goal?: string | null;
  model_provider?: string | null;
  model_name?: string | null;
  messages: AgentChatStreamMessage[];
  active_leaf_id?: string | null;
  run_id?: string | null;
  active_branch_id?: string | null;
  pinned_node_ids: string[];
  context_window_turns: number;
  continue_from_node_id?: string | null;
  partial_assistant_content?: string | null;
  tool_mentions?: ToolMention[];
  attachment_names?: string[];
  attachments?: AgentAttachmentPayload[];
  /**
   * UI-side token budget hint. The backend recounts with its estimator and
   * returns omission reasons when authoritative assembly trims context.
   */
  context_max_tokens?: number;
  compressed_context?: AgentCompressedContext | null;
};

export type AgentCompressedContext = {
  summary: string;
  branch_id: string;
  coverage_node_ids: string[];
  coverage_path_hash: string;
  summary_schema_version: string;
  compression_prompt_version: string;
  compressor_provider: string;
  compressor_model: string;
  estimated_original_tokens?: number | null;
  estimated_summary_tokens?: number | null;
  cache_status?: "accepted" | "recomputed" | "stale_rejected" | "error" | null;
};

export type WorkspaceContextCompressionPayload = {
  model_provider?: string | null;
  model_name?: string | null;
  messages: AgentChatStreamMessage[];
  pinned_node_ids: string[];
  existing_summary?: string | null;
  prior_coverage_node_ids?: string[];
  prior_coverage_path_hash?: string | null;
  summary_schema_version: string;
  compression_prompt_version: string;
  compressor_provider?: string | null;
  compressor_model?: string | null;
};

export type WorkspaceContextCompressionResponse = {
  status: "ok" | "stale" | "missing_raw_nodes" | "hash_mismatch" | "provider_error";
  cache_status: "accepted" | "recomputed" | "stale_rejected" | "error";
  summary: string;
  coverage_node_ids: string[];
  coverage_path_hash: string;
  last_covered_node_id: string | null;
  summary_schema_version: string;
  compression_prompt_version: string;
  compressor_provider: string;
  compressor_model: string;
  estimated_original_tokens: number;
  estimated_summary_tokens: number;
  estimated_uncovered_tokens: number;
  created_at: string;
  updated_at: string;
  error?: string | null;
};

export type AgentChatStreamEvent =
  | { type: "delta"; content: string }
  | { type: "think_delta"; content: string }
  | {
      type: "orchestration";
      mode: string;
      run_id: string;
      message: string;
      payload: Record<string, unknown>;
    }
  | {
      type: "run_created";
      run_id: string;
      status: string;
      step_count: number;
      message: string;
      context_assembly?: {
        context_manifest_id: string | null;
        mode: string | null;
        included_count: number;
        omitted_count: number;
        omission_reasons: string[];
      };
    }
  | {
      type: "tool_call_requested";
      tool_call_id: string;
      tool_name: string;
      source: string | null;
      input_json: Record<string, unknown>;
      status: string;
      risk?: string;
      sandbox?: string;
      approval_id?: string | null;
    }
  | {
      type: "tool_call_result";
      tool_call_id: string;
      tool_name: string;
      output_json: Record<string, unknown>;
      output_summary?: string | null;
      status: string;
      duration_ms?: number | null;
      trace_id?: string | null;
      approval_id?: string | null;
    }
  | {
      type: "artifact_created";
      name: string;
      artifact_type: "code" | "json" | "diff" | "chart" | "text";
      status: string;
      content: unknown;
      run_id?: string;
    }
  | {
      type: "usage";
      input_tokens: number;
      output_tokens: number;
      cost_usd: string | null;
      cost_unavailable: boolean;
      ttfb_ms: number;
      duration_ms: number;
      model_call_id?: string | null;
    }
  | {
      type: "done";
      run_id: string;
      active_branch_id?: string | null;
      continue_from_node_id?: string | null;
      status: string;
      step_count: number;
      message: string;
      knowledge_grounding?: string | null;
    }
  | { type: "error"; message: string; recoverable?: boolean };

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

export type WarmPoolBenchmark = {
  id: string;
  organization_id: string | null;
  mode: string;
  status: string;
  target_startup_ms: number;
  iteration_count: number;
  warm_avg_ms: number;
  warm_p95_ms: number;
  cold_avg_ms: number;
  hit_rate: number;
  report_json: Record<string, unknown>;
  created_by: string | null;
  created_at: string;
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
  agent_assignments_by_status: CountItem[];
  model_calls_by_status: CountItem[];
  tool_calls_by_status: CountItem[];
  sandboxes_by_status: CountItem[];
  subagent_queue: {
    pending: number;
    queued: number;
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
  assignment_queue: {
    pending: number;
    queued: number;
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
  token_optimization: Record<string, unknown>;
};

export type TokenSavingsSummary = {
  actual_prompt_tokens: number;
  actual_completion_tokens: number;
  actual_total_tokens: number;
  estimated_candidate_tokens: number;
  estimated_included_tokens: number;
  estimated_omitted_tokens: number;
  estimated_saved_tokens: number;
  estimated_savings_percent: number;
  context_manifest_count: number;
  pruning_manifest_count: number;
  retrieval_cache_hit_count: number;
  retrieval_cache_miss_count: number;
  retrieval_cache_stale_count: number;
  cache_sources: CacheSourceSummary[];
  low_cost_route_count: number;
  optimizer_capability_version_ids: string[];
  optimizer_labels: string[];
  optimizer_decision_count: number;
};

export type CacheSourceSummary = {
  cache_source: string;
  label: string;
  hit_count: number;
  miss_count: number;
  stale_count: number;
  estimated_saved_tokens: number;
  hit_rate: number;
  reason?: string | null;
};

export type TokenSavingsRunItem = {
  run_id: string;
  agent_id: string | null;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
  context_manifest_id: string;
  estimated_candidate_tokens: number;
  estimated_included_tokens: number;
  estimated_omitted_tokens: number;
  estimated_saved_tokens: number;
  estimated_savings_percent: number;
  actual_prompt_tokens: number;
  actual_completion_tokens: number;
  actual_total_tokens: number;
  included_count: number;
  omitted_count: number;
  pruning_applied: boolean;
  retrieval_cache_hit_count: number;
  retrieval_cache_miss_count: number;
  retrieval_cache_stale_count: number;
  cache_sources: CacheSourceSummary[];
  low_cost_routes: Array<{
    model_call_id: string;
    model_name: string;
    reason: string;
  }>;
  optimizer_capability_version_ids: string[];
  optimizer_labels: string[];
  optimizer_policy_hash: string | null;
  optimizer_decision_count: number;
  omission_reasons: Array<{
    reason: string;
    count: number;
  }>;
};

export type TokenSavingsPage = {
  generated_at: string;
  summary: TokenSavingsSummary;
  runs: TokenSavingsRunItem[];
  next_cursor: string | null;
};

export type ObservabilityGroundingQualityItem = {
  eval_run_id: string;
  eval_result_id: string;
  eval_case_id: string;
  task_id: string | null;
  dataset_id: string;
  agent_id: string | null;
  status: string;
  created_at: string;
  grounding_passed: boolean;
  grounding_failures: string[];
  forbidden_evidence_leaked: boolean;
  forbidden_leak_sources: string[];
  fallback_expected: boolean;
  fallback_observed: boolean;
  unsupported_marker_present: boolean;
  citation_keys: string[];
  citation_hit_ids: string[];
  retrieval_session_id: string | null;
  prompt_manifest_id: string | null;
};

export type ObservabilityGroundingQuality = {
  items: ObservabilityGroundingQualityItem[];
  metrics: Record<string, number>;
  failure_facets: CountItem[];
  total: number;
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
  depends_on: string[];
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

export type AgentPlanResult = {
  agent_id: string;
  run_id: string;
  task: Task;
  plan: TaskPlan;
  message: string;
};

export type KnowledgeDocument = {
  id: string;
  source_id: string;
  organization_id: string | null;
  agent_id: string | null;
  title: string;
  uri: string | null;
  content_sha256: string;
  mime_type: string;
  status: string;
  version: number;
  logical_document_id: string | null;
  supersedes_document_id: string | null;
  superseded_at: string | null;
  ingestion_error: string | null;
  metadata_json: Record<string, unknown>;
  idempotency_key: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  indexed_at: string | null;
  chunk_count: number;
};

export type KnowledgeSource = {
  id: string;
  organization_id: string | null;
  agent_id: string | null;
  name: string;
  description: string;
  source_type: string;
  status: string;
  version: number;
  scope: "agent" | "org";
  expires_at: string | null;
  disabled_at: string | null;
  archived_at: string | null;
  last_indexed_at: string | null;
  last_ingestion_error: string | null;
  health_status: string;
  connector_provider?: string | null;
  connector_release_state?: "usable" | "configured-but-unavailable" | "preview-not-counted" | null;
  connector_counts_toward_complete_usable?: boolean | null;
  connector_validation_status?: "ready" | "configured" | "preview" | "invalid";
  connector_validation_messages?: string[];
  connector_secret_configured?: boolean;
  settings_json: Record<string, unknown>;
  metadata_json: Record<string, unknown>;
  idempotency_key: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  latest_documents: KnowledgeDocument[];
};

export type KnowledgeSourceCreatePayload = {
  name: string;
  description?: string;
  scope?: "agent" | "org";
  source_type?: "text" | "markdown" | "document" | "connector";
  title: string;
  content: string;
  uri?: string | null;
  mime_type?: string;
  idempotency_key?: string | null;
  expires_at?: string | null;
  connector_settings_json?: Record<string, unknown>;
  connector_secret_value?: string | null;
};

export type KnowledgeSourceUpdatePayload = {
  name?: string;
  description?: string;
  expires_at?: string | null;
  connector_settings_json?: Record<string, unknown> | null;
  connector_secret_value?: string | null;
};

export type KnowledgeSourceActionPayload = {
  reason?: string | null;
};

export type KnowledgeSourceScopePayload = {
  scope: "agent" | "org";
  reason?: string | null;
};

export type KnowledgeDocumentCreatePayload = {
  title: string;
  content: string;
  uri?: string | null;
  mime_type?: string;
  idempotency_key?: string | null;
};

export type KnowledgeSourcePage = {
  items: KnowledgeSource[];
  next_cursor: string | null;
};

export type KnowledgeRetrievalHit = {
  id: string;
  chunk_id: string | null;
  web_source_id: string | null;
  rank: number;
  score: number;
  source_kind: string;
  document_id: string | null;
  document_version: number | null;
  snippet: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export type KnowledgeCitation = {
  id: string;
  retrieval_hit_id: string;
  citation_key: string;
  source_kind: string;
  chunk_id: string | null;
  web_source_id: string | null;
  claim_text: string | null;
  quoted_text: string | null;
  confidence: number;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export type WebResearchSource = {
  id: string;
  url: string;
  title: string;
  content_sha256: string;
  snippet: string;
  status: string;
  error_message: string | null;
  metadata_json: Record<string, unknown>;
  fetched_at: string;
};

export type PromptAssemblyManifest = {
  id: string;
  retrieval_session_id: string;
  run_id: string | null;
  grounding_correlation_id: string;
  query: string;
  included_retrieval_hit_ids_json: string[];
  omitted_candidates_json: Record<string, unknown>[];
  source_snapshots_json: Record<string, unknown>[];
  token_budget_json: Record<string, unknown>;
  prompt_sections_json: Record<string, unknown>[];
  evidence_text_sha256: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export type KnowledgePolicyAudit = {
  id: string;
  retrieval_session_id: string;
  run_id: string | null;
  decision: string;
  reason: string;
  source_kind: string | null;
  source_ref_id: string | null;
  safe_metadata_json: Record<string, unknown>;
  created_at: string;
};

export type RetrievalSession = {
  id: string;
  query: string;
  mode: string;
  local_status: string;
  vector_capability: string;
  strategy: string;
  min_hits: number;
  min_score: number;
  max_local_chunks: number;
  max_web_results: number;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export type KnowledgeGrounding = {
  retrieval_session: RetrievalSession | null;
  retrieval_hits: KnowledgeRetrievalHit[];
  citations: KnowledgeCitation[];
  prompt_manifest: PromptAssemblyManifest | null;
  policy_audits: KnowledgePolicyAudit[];
  web_sources: WebResearchSource[];
  vector_capability: string;
  local_status: string;
  grounded: boolean;
  grounding_provider: string;
  fixture_grounded: boolean;
  verified_grounded: boolean;
  grounding_verification_reason: string;
  evidence_summary: string;
  evidence_message: string;
  inferred_fallback: boolean;
  fallback_reason: string | null;
  selected_retrieval_session_id: string | null;
  selected_prompt_manifest_id: string | null;
};

export type AgentRunWorkspace = {
  run: Task;
  plan: TaskPlan | null;
  events: AgentEvent[];
  knowledge_grounding: KnowledgeGrounding | null;
  context_assembly: ContextAssemblyManifest | null;
  token_optimization: Record<string, unknown>;
  subagents: Subagent[];
  tool_calls: ToolCall[];
  model_calls: ModelCall[];
  approvals: ToolApproval[];
  assignments: AgentAssignment[];
  handoffs: AgentHandoff[];
};

export type ContextAssemblyManifest = {
  id: string;
  organization_id: string | null;
  agent_id: string;
  run_id: string | null;
  retrieval_session_id: string | null;
  prompt_manifest_id: string | null;
  active_branch_id: string | null;
  active_leaf_id: string | null;
  mode: string;
  token_budget_json: Record<string, unknown>;
  sections_json: Array<Record<string, unknown>>;
  included_refs_json: Array<Record<string, unknown>>;
  omitted_refs_json: Array<Record<string, unknown>>;
  policy_decisions_json: Array<Record<string, unknown>>;
  tombstoned_refs_json: Array<Record<string, unknown>>;
  context_text_sha256: string;
  metadata_json: Record<string, unknown>;
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

export type RunContext = {
  task_id: string;
  generated_at: string;
  working_memory: Record<string, unknown>;
  long_term_memory: Record<string, unknown>;
  artifact_memory: Record<string, unknown>;
  rag_context: Record<string, unknown>;
  trace_memory: Record<string, unknown>;
  context_compression: Record<string, unknown>;
  model_routing: Record<string, unknown>;
  latest_agent_router: Record<string, unknown> | null;
  context_assembly: Record<string, unknown> | null;
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
  grounding_correlation_id: string | null;
  prompt_manifest_id: string | null;
  context_manifest_id: string | null;
  model_request_sha256: string | null;
  model_request_hash_schema_version: number;
  request_message_hashes_json: Array<Record<string, unknown>>;
  request_message_hashes_sha256: string | null;
  hash_recomputability_status: string;
  attempt_index: number;
  terminal_status: string | null;
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
  capability_id?: string | null;
  capability_version_id?: string | null;
  capability_type?: string | null;
  capability_content_sha256?: string | null;
  capability_config_sha256?: string | null;
  capability_schema_version?: number | null;
  capability_snapshot_json?: Record<string, unknown>;
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

export type ToolApproval = {
  id: string;
  task_id: string;
  tool_call_id: string;
  organization_id: string | null;
  requested_by: string | null;
  decided_by: string | null;
  status: string;
  risk_level: string;
  reason: string;
  request_json: Record<string, unknown>;
  decision_json: Record<string, unknown>;
  created_at: string;
  decided_at: string | null;
};

export type ToolMetadata = {
  name: string;
  description: string;
  category: string;
  source: string;
  risk_level: string;
  requires_sandbox: boolean;
  network_policy: string;
  timeout_seconds: number;
  allowed_roles: string[];
  audit_level: string;
  idempotent: boolean;
  input_schema: Record<string, unknown>;
  mcp_server: string | null;
  mcp_method: string | null;
};

export type ToolRegistry = {
  items: ToolMetadata[];
  categories: string[];
  sources: string[];
};

export type CapabilityValidationRequest = {
  content: Record<string, unknown>;
  config: Record<string, unknown>;
};

export type CapabilityValidationResponse = {
  status: string;
  schema_version: number;
  content_sha256: string;
  config_sha256: string;
  redacted_payload: Record<string, unknown>;
  validation_mode?: string;
  activation_allowed?: boolean;
  issues?: Array<Record<string, unknown>>;
  risk_preview?: Record<string, unknown>;
};

export type CapabilityTestInvocationPayload = {
  agent_id: string;
  tool_name: string;
  input_json: Record<string, unknown>;
};

export type CapabilityRuntimeConfigUpdatePayload = {
  agent_id: string;
  tool_name: string;
  transport: "stdio" | "http" | "sse";
  endpoint_url?: string | null;
  command?: string | null;
  args?: string[];
  secret_ref?: string | null;
  secret_value?: string | null;
  timeout_seconds?: number | null;
};

export type CapabilityRuntimeConfig = {
  agent_id: string;
  tool_name: string;
  tool_description: string;
  source: string;
  capability_id: string;
  capability_version_id: string;
  capability_config_sha256: string;
  attachment_id: string;
  attachment_enabled: boolean;
  configured: boolean;
  missing_fields: string[];
  transport: "stdio" | "http" | "sse" | string;
  endpoint_url: string | null;
  command: string | null;
  args: string[];
  secret_ref: string | null;
  secret_configured: boolean;
  timeout_seconds: number;
  config_json: Record<string, unknown>;
  registry_visible: boolean;
  test_input_json: Record<string, unknown>;
};

export type CapabilityRuntimeConfigPage = {
  items: CapabilityRuntimeConfig[];
};

export type CapabilityPackage = {
  id: string;
  organization_id: string | null;
  package_key: string;
  package_type: string;
  source_kind: string;
  source_uri: string | null;
  source_sha256: string;
  pinned_ref: string | null;
  status: string;
  risk_level: string;
  manifest_json: Record<string, unknown>;
  validation_json: Record<string, unknown>;
  provenance_json: Record<string, unknown>;
  audit_json: Record<string, unknown>;
  capability_id: string | null;
  capability_version_id: string | null;
  created_at: string;
  updated_at: string;
  approved_at: string | null;
};

export type CapabilityPackagePage = {
  items: CapabilityPackage[];
};

export type CapabilityPackageStagePayload = {
  manifest: Record<string, unknown>;
  content?: Record<string, unknown>;
};

export type CapabilityMarketplacePreflightPayload = CapabilitySimpleInstallPayload & {
  marketplace_source?: string;
  marketplace_item_id?: string;
};

export type CapabilityPublicPackageStagePayload = CapabilityPackageStagePayload & {
  source_kind: "public_url" | "public_git";
  source_uri: string;
  pinned_ref: string;
};

export type CapabilityPackageAttachPayload = {
  agent_id: string;
  enabled?: boolean;
  priority?: number;
};

export type CapabilitySimpleInstallPayload = {
  source_uri?: string;
  pinned_ref?: string | null;
  package_type?:
    | "agent_template"
    | "skill_pack"
    | "tool_definition"
    | "mcp_server"
    | "prompt_template"
    | "knowledge_connector"
    | "context_optimizer";
  display_name?: string;
  description?: string;
  agent_id?: string | null;
  permissions?: string[];
  secret_refs?: string[];
  manifest?: Record<string, unknown> | null;
  content?: Record<string, unknown>;
};

export type CapabilitySimpleInstallResponse = {
  package: CapabilityPackage;
  validation_summary: Record<string, unknown>;
  ready_state: string;
  next_step_label: string;
  staged_capability_id: string | null;
  capability_id: string | null;
  capability_version_id: string | null;
  attachment: CapabilityPackageAttachment | null;
};

export type CapabilityPackageAttachment = {
  attachment_id: string;
  agent_id: string;
  capability_id: string;
  capability_version_id: string;
  enabled: boolean;
  priority: number;
};

export type CapabilityMarketplaceItem = {
  id: string;
  kind: "mcp" | "skill";
  source: string;
  source_label: string;
  name: string;
  display_name: string;
  description: string;
  categories: string[];
  verified: boolean;
  stars: number | null;
  use_count: number | null;
  quality_score: number | null;
  latest_version: string | null;
  updated_at: string | null;
  homepage_url: string;
  repository_url: string;
  remote_url: string;
  package_type: CapabilitySimpleInstallPayload["package_type"];
  install_mode:
    | "attach_existing"
    | "trusted_install"
    | "public_preflight"
    | "marketplace_preflight"
    | "upload_install";
  install_label: string;
  install_payload: CapabilityMarketplacePreflightPayload & {
    capability_id?: string;
    enabled?: boolean;
    priority?: number;
  };
  badges: string[];
  risk_notes: string[];
  metadata: Record<string, unknown>;
};

export type CapabilityMarketplaceResponse = {
  kind: "all" | "mcp" | "skill";
  query: string;
  items: CapabilityMarketplaceItem[];
  sources: Array<{
    id: string;
    label: string;
    status: string;
    item_count: number;
    url: string;
  }>;
  errors: Array<{ source: string; message: string }>;
};

export type AgentUpsertPayload = {
  id: string;
  name: string;
  description: string;
  role: string;
  model_provider: string;
  model_name: string;
  system_prompt: string;
  tools_json: string[];
  routing_tags: string[];
  max_parallel_assignments: number;
  token_budget?: number;
  template_id?: string | null;
};

export type AgentClonePayload = {
  source_agent_id: string;
  id: string;
  name: string;
};

export type AgentCapabilityAttachmentPayload = {
  capability_id: string;
  capability_version_id?: string | null;
  enabled: boolean;
  priority: number;
};

export type TokenOptimizerPresetId = "off" | "conservative" | "balanced" | "aggressive";

export type TokenOptimizerPreset = {
  preset_id: TokenOptimizerPresetId;
  display_name: string;
  description: string;
  enabled: boolean;
  priority: number | null;
};

export type TokenOptimizerPresetPage = {
  items: TokenOptimizerPreset[];
};

export type TokenOptimizerSelectionResponse = {
  status: string;
  preset_id: TokenOptimizerPresetId;
  attachment_id: string | null;
  capability_id: string | null;
  capability_version_id: string | null;
  enabled: boolean;
  priority: number | null;
};

export type EvalDataset = {
  id: string;
  organization_id: string | null;
  name: string;
  description: string;
  status: string;
  baseline_run_id: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  case_count: number;
};

export type EvalCase = {
  id: string;
  dataset_id: string;
  source_task_id: string | null;
  input_json: Record<string, unknown>;
  expected_json: Record<string, unknown>;
  tags_json: string[];
  created_at: string;
};

export type EvalResult = {
  id: string;
  eval_run_id: string;
  eval_case_id: string;
  task_id: string | null;
  status: string;
  scores_json: Record<string, number>;
  grader_trace_json: Record<string, unknown>;
  latency_ms: number;
  cost_usd: string;
  error_message: string | null;
  created_at: string;
};

export type EvalRun = {
  id: string;
  dataset_id: string;
  organization_id: string | null;
  agent_id: string | null;
  status: string;
  metrics_json: Record<string, number>;
  created_by: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  results: EvalResult[];
};

async function request<T>(
  path: string,
  init?: RequestInit & { timeoutMs?: number },
): Promise<T> {
  const { timeoutMs = 0, signal, headers, ...requestInit } = init ?? {};
  const controller =
    timeoutMs > 0 && !signal ? new AbortController() : null;
  const timeout =
    controller === null
      ? null
      : globalThis.setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetchApi(path, {
      ...requestInit,
      signal: signal ?? controller?.signal,
      headers: { "Content-Type": "application/json", ...authHeaders(), ...headers },
    });
  } catch (error) {
    if (controller?.signal.aborted) {
      throw new Error(`请求超时：API ${Math.round(timeoutMs / 1000)} 秒内未响应`);
    }
    throw error instanceof Error ? error : apiConnectionError(error, apiRequestUrls(path));
  } finally {
    if (timeout !== null) {
      globalThis.clearTimeout(timeout);
    }
  }
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
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

async function requestMultipart<T>(
  path: string,
  body: FormData,
  token = DEV_BEARER_TOKEN,
): Promise<T> {
  let response: Response;
  try {
    response = await fetchApi(path, {
      method: "POST",
      headers: authHeaders(token),
      body,
    });
  } catch (error) {
    throw error instanceof Error ? error : apiConnectionError(error, apiRequestUrls(path));
  }
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

function knowledgeFileFormData(
  file: File,
  payload: {
    title?: string;
    name?: string;
    description?: string;
    scope?: "agent" | "org";
    idempotency_key?: string | null;
  },
) {
  const body = new FormData();
  body.append("file", file);
  for (const [key, value] of Object.entries(payload)) {
    if (value !== undefined && value !== null) {
      body.append(key, value);
    }
  }
  return body;
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

export async function listAgents() {
  return request<{ items: AgentDefinition[]; next_cursor: string | null }>("/api/agents");
}

export async function listTokenOptimizerPresets() {
  return request<TokenOptimizerPresetPage>("/api/agents/token-optimizer/presets");
}

export async function selectAgentTokenOptimizer(
  agentId: string,
  presetId: TokenOptimizerPresetId,
) {
  return request<TokenOptimizerSelectionResponse>(`/api/agents/${agentId}/token-optimizer`, {
    method: "POST",
    body: JSON.stringify({ preset_id: presetId }),
  });
}

export async function listTeams() {
  return request<{ items: Team[]; next_cursor: string | null }>("/api/teams");
}

export async function createTeam(payload: TeamCreatePayload) {
  return request<Team>("/api/teams", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getTeam(teamId: string) {
  return request<Team>(`/api/teams/${teamId}`);
}

export async function renameTeam(teamId: string, name: string) {
  return request<Team>(`/api/teams/${teamId}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export async function archiveTeam(teamId: string) {
  return request<Team>(`/api/teams/${teamId}`, { method: "DELETE" });
}

export async function addTeamAgent(teamId: string, payload: TeamAgentCreatePayload) {
  return request<TeamAgent>(`/api/teams/${teamId}/agents`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateTeamAgent(
  teamId: string,
  slotId: string,
  payload: TeamAgentUpdatePayload,
) {
  return request<TeamAgent>(`/api/teams/${teamId}/agents/${slotId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function renameTeamAgent(teamId: string, slotId: string, agentName: string) {
  return updateTeamAgent(teamId, slotId, { agent_name: agentName });
}

export async function removeTeamAgent(teamId: string, slotId: string) {
  return request<TeamAgent>(`/api/teams/${teamId}/agents/${slotId}`, { method: "DELETE" });
}

export async function wakeTeamAgent(teamId: string, slotId: string) {
  return request<TeamAgent>(`/api/teams/${teamId}/agents/${slotId}/wake`, { method: "POST" });
}

export async function cancelWakeTeamAgent(teamId: string, slotId: string) {
  return request<TeamAgent>(`/api/teams/${teamId}/agents/${slotId}/wake/cancel`, { method: "POST" });
}

export async function sendTeamMessage(teamId: string, payload: TeamMessageCreatePayload) {
  return request<TeamMailboxMessage>(`/api/teams/${teamId}/messages`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function readTeamMailbox(teamId: string, slotId: string) {
  return request<TeamMailboxMessage[]>(`/api/teams/${teamId}/agents/${slotId}/mailbox/read`, {
    method: "POST",
  });
}

export async function callTeamTool(teamId: string, toolName: string, payload: TeamToolCallPayload) {
  return request<TeamToolCallResult>(`/api/teams/${teamId}/tools/${toolName}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listTeamTasks(teamId: string) {
  return request<TeamTask[]>(`/api/teams/${teamId}/tasks`);
}

export async function createTeamTask(teamId: string, payload: TeamTaskCreatePayload) {
  return request<TeamTask>(`/api/teams/${teamId}/tasks`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateTeamTask(teamId: string, taskId: string, payload: TeamTaskUpdatePayload) {
  return request<TeamTask>(`/api/teams/${teamId}/tasks/${taskId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function listTeamEvents(teamId: string, afterSequence?: number) {
  const suffix = afterSequence !== undefined ? `?after_sequence=${afterSequence}` : "";
  return request<TeamEvent[]>(`/api/teams/${teamId}/events${suffix}`);
}

function parseTeamSseFrame(frame: string): TeamEvent | null {
  const dataLine = frame
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line.startsWith("data: "));
  if (!dataLine) return null;
  const payload = dataLine.slice("data: ".length);
  try {
    return JSON.parse(payload) as TeamEvent;
  } catch {
    return null;
  }
}

function parseNamedSseFrame(frame: string): { event: string; payload: Record<string, unknown> } | null {
  const lines = frame.split("\n").map((line) => line.trim());
  const event = lines.find((line) => line.startsWith("event: "))?.slice("event: ".length) ?? "message";
  const dataLine = lines.find((line) => line.startsWith("data: "));
  if (!dataLine) return null;
  try {
    const payload = JSON.parse(dataLine.slice("data: ".length)) as unknown;
    return { event, payload: payload && typeof payload === "object" ? payload as Record<string, unknown> : {} };
  } catch {
    return null;
  }
}

function parseTeamWakeSseFrame(frame: string): TeamWakeStreamEvent | null {
  const parsed = parseNamedSseFrame(frame);
  if (!parsed) return null;
  const { event, payload } = parsed;
  if (event === "status" && payload.agent) {
    return { type: "status", agent: payload.agent as TeamAgent };
  }
  if (event === "delta" && typeof payload.content === "string" && typeof payload.slot_id === "string") {
    return { type: "delta", slot_id: payload.slot_id, content: payload.content };
  }
  if (event === "done" && payload.agent) {
    return {
      type: "done",
      agent: payload.agent as TeamAgent,
      message: payload.message as AgentMessage | undefined,
      follow_up_slot_ids: Array.isArray(payload.follow_up_slot_ids)
        ? payload.follow_up_slot_ids.filter((value): value is string => typeof value === "string")
        : undefined,
    };
  }
  if (event === "error") {
    return {
      type: "error",
      message: typeof payload.message === "string" ? payload.message : "Team wake stream failed",
      agent: payload.agent as TeamAgent | undefined,
      slot_id: typeof payload.slot_id === "string" ? payload.slot_id : undefined,
    };
  }
  return null;
}

function isTerminalTeamWakeEvent(event: TeamWakeStreamEvent) {
  return event.type === "done" || event.type === "error";
}

export async function streamTeamEvents(
  teamId: string,
  onEvent: (event: TeamEvent) => void,
  signal?: AbortSignal,
) {
  let response: Response;
  try {
    const path = `/api/teams/${teamId}/stream`;
    response = await fetchApi(path, {
      method: "GET",
      headers: authHeaders(),
      signal,
    });
  } catch (error) {
    throw error instanceof Error
      ? error
      : apiConnectionError(error, apiRequestUrls(`/api/teams/${teamId}/stream`));
  }
  if (!response.ok || !response.body) {
    throw new Error(`请求失败 ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const event = parseTeamSseFrame(frame);
      if (event) onEvent(event);
    }
  }
  const finalEvent = parseTeamSseFrame(buffer);
  if (finalEvent) onEvent(finalEvent);
}

export async function streamWakeTeamAgent(
  teamId: string,
  slotId: string,
  onEvent: (event: TeamWakeStreamEvent) => void,
  signal?: AbortSignal,
) {
  const path = `/api/teams/${teamId}/agents/${slotId}/wake/stream`;
  let response: Response;
  try {
    response = await fetchApi(path, {
      method: "POST",
      headers: authHeaders(),
      signal,
    });
  } catch (error) {
    throw error instanceof Error ? error : apiConnectionError(error, apiRequestUrls(path));
  }
  if (!response.ok || !response.body) {
    throw new Error(`请求失败 ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const event = parseTeamWakeSseFrame(frame);
      if (!event) continue;
      onEvent(event);
      if (isTerminalTeamWakeEvent(event)) {
        await reader.cancel().catch(() => undefined);
        return;
      }
    }
  }
  const finalEvent = parseTeamWakeSseFrame(buffer);
  if (!finalEvent) return;
  onEvent(finalEvent);
  if (isTerminalTeamWakeEvent(finalEvent)) {
    await reader.cancel().catch(() => undefined);
  }
}

export async function getAgent(agentId: string) {
  return request<AgentDefinition>(`/api/agents/${agentId}`);
}

export async function listAgentKnowledgeSources(agentId: string) {
  return request<KnowledgeSourcePage>(`/api/agents/${agentId}/knowledge/sources`);
}

export async function createAgentKnowledgeSource(
  agentId: string,
  payload: KnowledgeSourceCreatePayload,
) {
  return request<KnowledgeSource>(`/api/agents/${agentId}/knowledge/sources`, {
    method: "POST",
    headers: payload.scope === "org" ? authHeaders(DEV_ADMIN_BEARER_TOKEN) : undefined,
    timeoutMs:
      payload.source_type === "connector" ? KNOWLEDGE_SOURCE_CREATE_TIMEOUT_MS : 0,
    body: JSON.stringify(payload),
  });
}

export async function importAgentKnowledgeSourceFile(
  agentId: string,
  file: File,
  payload: {
    title?: string;
    name?: string;
    description?: string;
    scope?: "agent" | "org";
    idempotency_key?: string | null;
  },
) {
  return requestMultipart<KnowledgeSource>(
    `/api/agents/${agentId}/knowledge/sources/import`,
    knowledgeFileFormData(file, payload),
    payload.scope === "org" ? DEV_ADMIN_BEARER_TOKEN : DEV_BEARER_TOKEN,
  );
}

export async function updateAgentKnowledgeSource(
  agentId: string,
  sourceId: string,
  payload: KnowledgeSourceUpdatePayload,
  options: { admin?: boolean } = {},
) {
  return request<KnowledgeSource>(`/api/agents/${agentId}/knowledge/sources/${sourceId}`, {
    method: "PATCH",
    headers: options.admin ? authHeaders(DEV_ADMIN_BEARER_TOKEN) : undefined,
    body: JSON.stringify(payload),
  });
}

export async function disableAgentKnowledgeSource(
  agentId: string,
  sourceId: string,
  payload: KnowledgeSourceActionPayload = {},
  options: { admin?: boolean } = {},
) {
  return request<KnowledgeSource>(
    `/api/agents/${agentId}/knowledge/sources/${sourceId}/disable`,
    {
      method: "POST",
      headers: options.admin ? authHeaders(DEV_ADMIN_BEARER_TOKEN) : undefined,
      body: JSON.stringify(payload),
    },
  );
}

export async function enableAgentKnowledgeSource(
  agentId: string,
  sourceId: string,
  payload: KnowledgeSourceActionPayload = {},
  options: { admin?: boolean } = {},
) {
  return request<KnowledgeSource>(
    `/api/agents/${agentId}/knowledge/sources/${sourceId}/enable`,
    {
      method: "POST",
      headers: options.admin ? authHeaders(DEV_ADMIN_BEARER_TOKEN) : undefined,
      body: JSON.stringify(payload),
    },
  );
}

export async function archiveAgentKnowledgeSource(
  agentId: string,
  sourceId: string,
  payload: KnowledgeSourceActionPayload = {},
  options: { admin?: boolean } = {},
) {
  return request<KnowledgeSource>(
    `/api/agents/${agentId}/knowledge/sources/${sourceId}/archive`,
    {
      method: "POST",
      headers: options.admin ? authHeaders(DEV_ADMIN_BEARER_TOKEN) : undefined,
      body: JSON.stringify(payload),
    },
  );
}

export async function deleteAgentKnowledgeSource(
  agentId: string,
  sourceId: string,
  options: { admin?: boolean } = {},
) {
  return request<void>(`/api/agents/${agentId}/knowledge/sources/${sourceId}`, {
    method: "DELETE",
    headers: options.admin ? authHeaders(DEV_ADMIN_BEARER_TOKEN) : undefined,
  });
}

export async function changeAgentKnowledgeSourceScope(
  agentId: string,
  sourceId: string,
  payload: KnowledgeSourceScopePayload,
) {
  return request<KnowledgeSource>(`/api/agents/${agentId}/knowledge/sources/${sourceId}/scope`, {
    method: "POST",
    headers: authHeaders(DEV_ADMIN_BEARER_TOKEN),
    body: JSON.stringify(payload),
  });
}

export async function listAgentKnowledgeDocuments(agentId: string, sourceId: string) {
  return request<KnowledgeDocument[]>(
    `/api/agents/${agentId}/knowledge/sources/${sourceId}/documents`,
  );
}

export async function createAgentKnowledgeDocument(
  agentId: string,
  sourceId: string,
  payload: KnowledgeDocumentCreatePayload,
) {
  return request<KnowledgeSource>(
    `/api/agents/${agentId}/knowledge/sources/${sourceId}/documents`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function importAgentKnowledgeDocumentFile(
  agentId: string,
  sourceId: string,
  file: File,
  payload: { title?: string; idempotency_key?: string | null },
) {
  return requestMultipart<KnowledgeSource>(
    `/api/agents/${agentId}/knowledge/sources/${sourceId}/documents/import`,
    knowledgeFileFormData(file, payload),
  );
}

export async function createAgentKnowledgeDocumentVersion(
  agentId: string,
  sourceId: string,
  documentId: string,
  payload: KnowledgeDocumentCreatePayload,
) {
  return request<KnowledgeSource>(
    `/api/agents/${agentId}/knowledge/sources/${sourceId}/documents/${documentId}/versions`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function importAgentKnowledgeDocumentVersionFile(
  agentId: string,
  sourceId: string,
  documentId: string,
  file: File,
  payload: { title?: string; idempotency_key?: string | null },
) {
  return requestMultipart<KnowledgeSource>(
    `/api/agents/${agentId}/knowledge/sources/${sourceId}/documents/${documentId}/versions/import`,
    knowledgeFileFormData(file, payload),
  );
}

export async function compressAgentWorkspaceContext(
  agentId: string,
  payload: WorkspaceContextCompressionPayload,
) {
  return request<WorkspaceContextCompressionResponse>(
    `/api/agents/${agentId}/context/compress`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function createAgentRun(agentId: string, payload: AgentRunCreatePayload) {
  return request<AgentPlanResult>(`/api/agents/${agentId}/runs`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function streamAgentPlanRun(
  agentId: string,
  payload: AgentRunCreatePayload,
  onEvent: (event: AgentPlanStreamEvent) => void,
  signal?: AbortSignal,
) {
  const response = await fetch(`${API_BASE_URL}/api/agents/${agentId}/runs/plan/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ ...payload, mode: "plan" }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`请求失败 ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const event = parseSseFrame(frame);
      if (event) onEvent(event);
    }
  }
  const finalEvent = parseSseFrame(buffer);
  if (finalEvent) onEvent(finalEvent);
}

export async function streamAgentChatRun(
  agentId: string,
  payload: AgentChatStreamPayload,
  onEvent: (event: AgentChatStreamEvent) => void,
  signal?: AbortSignal,
) {
  const response = await fetch(`${API_BASE_URL}/api/agents/${agentId}/runs/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`请求失败 ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const event = parseChatSseFrame(frame);
      if (event) onEvent(event);
    }
  }
  const finalEvent = parseChatSseFrame(buffer);
  if (finalEvent) onEvent(finalEvent);
}

export async function listRuns() {
  return request<{ items: Task[]; next_cursor: string | null }>("/api/agents/runs");
}

export async function getAgentRunWorkspace(
  runId: string,
  selectors: { retrieval_session_id?: string; prompt_manifest_id?: string } = {},
) {
  const params = new URLSearchParams();
  if (selectors.retrieval_session_id) {
    params.set("retrieval_session_id", selectors.retrieval_session_id);
  }
  if (selectors.prompt_manifest_id) {
    params.set("prompt_manifest_id", selectors.prompt_manifest_id);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return request<AgentRunWorkspace>(`/api/agents/runs/${runId}/workspace${suffix}`);
}

export async function planWithAgent(payload: AgentPlanPayload) {
  return request<AgentPlanResult>("/api/agents/plan", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function executeAgentRun(runId: string) {
  return request<Task>(`/api/agents/runs/${runId}/execute`, { method: "POST" });
}

export async function orchestrateAgentRun(runId: string) {
  return request<AgentOrchestrateResult>(`/api/agents/runs/${runId}/orchestrate`, {
    method: "POST",
  });
}

export async function executeAgentOrchestration(runId: string) {
  return request<AgentOrchestrateResult>(`/api/agents/runs/${runId}/orchestrate/execute`, {
    method: "POST",
  });
}

export async function enqueueAgentOrchestration(runId: string) {
  return request<AgentOrchestrateResult>(`/api/agents/runs/${runId}/orchestrate/enqueue`, {
    method: "POST",
  });
}

export async function listAgentRunAssignments(runId: string) {
  return request<AgentAssignment[]>(`/api/agents/runs/${runId}/assignments`);
}

export async function listAgentRunHandoffs(runId: string) {
  return request<AgentHandoff[]>(`/api/agents/runs/${runId}/handoffs`);
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

export async function getTaskContext(taskId: string) {
  return request<RunContext>(`/api/tasks/${taskId}/context`);
}

export async function routeTaskContext(taskId: string) {
  return request<RunContext>(`/api/tasks/${taskId}/context/route`, { method: "POST" });
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

export async function getToolRegistry(
  agentId?: string | { queryKey?: readonly unknown[] },
) {
  const normalizedAgentId = typeof agentId === "string" ? agentId.trim() : "";
  const searchParams = new URLSearchParams();
  if (normalizedAgentId) searchParams.set("agent_id", normalizedAgentId);
  const suffix = searchParams.toString();
  return request<ToolRegistry>(`/api/tools/registry${suffix ? `?${suffix}` : ""}`);
}

export async function validateCapabilityPackage(payload: CapabilityValidationRequest) {
  return request<CapabilityValidationResponse>("/api/tools/capabilities/admin-validate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listCapabilityPackages() {
  return request<CapabilityPackagePage>("/api/tools/capabilities/packages");
}

export async function listCapabilityMarketplace(params?: {
  kind?: "all" | "mcp" | "skill";
  query?: string;
  limit?: number;
}) {
  const searchParams = new URLSearchParams();
  if (params?.kind) searchParams.set("kind", params.kind);
  if (params?.query) searchParams.set("query", params.query);
  if (params?.limit) searchParams.set("limit", String(params.limit));
  const suffix = searchParams.toString();
  return request<CapabilityMarketplaceResponse>(
    `/api/tools/capabilities/marketplace${suffix ? `?${suffix}` : ""}`,
  );
}

export async function stagePrivateCapabilityPackage(payload: CapabilityPackageStagePayload) {
  return request<CapabilityPackage>("/api/tools/capabilities/packages/private", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function stagePublicCapabilityPackage(payload: CapabilityPublicPackageStagePayload) {
  return request<CapabilityPackage>("/api/tools/capabilities/packages/public", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function approveCapabilityPackage(packageId: string, reason: string) {
  return request<CapabilityPackage>(`/api/tools/capabilities/packages/${packageId}/approve`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export async function enableStagedCapability(packageId: string, reason: string) {
  return request<CapabilitySimpleInstallResponse>(`/api/tools/capabilities/staged/${packageId}/enable`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export async function attachCapabilityPackage(packageId: string, payload: CapabilityPackageAttachPayload) {
  return request<CapabilityPackageAttachment>(`/api/tools/capabilities/packages/${packageId}/attachments`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function rollbackCapabilityPackage(packageId: string, capabilityVersionId: string, reason: string) {
  return request<CapabilityPackage>(`/api/tools/capabilities/packages/${packageId}/rollback`, {
    method: "POST",
    body: JSON.stringify({ capability_version_id: capabilityVersionId, reason }),
  });
}

export async function uninstallCapabilityPackage(packageId: string) {
  return request<CapabilityPackage>(`/api/tools/capabilities/packages/${packageId}/uninstall`, {
    method: "POST",
  });
}

export async function updateCapabilityPackageAttachment(attachmentId: string, enabled: boolean) {
  return request<CapabilityPackageAttachment>(`/api/tools/capabilities/attachments/${attachmentId}`, {
    method: "PATCH",
    body: JSON.stringify({ enabled }),
  });
}

export async function installTrustedUrlCapability(payload: CapabilitySimpleInstallPayload) {
  return request<CapabilitySimpleInstallResponse>("/api/tools/capabilities/install/trusted-url", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function preflightPublicUrlCapability(payload: CapabilitySimpleInstallPayload) {
  return request<CapabilitySimpleInstallResponse>("/api/tools/capabilities/preflight/public-url", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function preflightMarketplaceCapability(payload: CapabilityMarketplacePreflightPayload) {
  return request<CapabilitySimpleInstallResponse>("/api/tools/capabilities/preflight/marketplace", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function installUploadedCapability(payload: CapabilitySimpleInstallPayload) {
  return request<CapabilitySimpleInstallResponse>("/api/tools/capabilities/install/upload", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function capabilityDependencyPreflight() {
  return request<Record<string, unknown>>("/api/tools/capabilities/dependency-preflight");
}

export async function listCapabilityRuntimeConfigs(agentId: string) {
  const searchParams = new URLSearchParams({ agent_id: agentId });
  return request<CapabilityRuntimeConfigPage>(
    `/api/tools/capabilities/runtime-configs?${searchParams.toString()}`,
  );
}

export async function getCapabilityRuntimeConfig(agentId: string, toolName: string) {
  const searchParams = new URLSearchParams({ agent_id: agentId, tool_name: toolName });
  return request<CapabilityRuntimeConfig>(
    `/api/tools/capabilities/runtime-config?${searchParams.toString()}`,
  );
}

export async function updateCapabilityRuntimeConfig(payload: CapabilityRuntimeConfigUpdatePayload) {
  return request<CapabilityRuntimeConfig>("/api/tools/capabilities/runtime-config", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function testInvokeCapability(payload: CapabilityTestInvocationPayload) {
  return request<ToolExecuteResult>("/api/tools/capabilities/test-invoke", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function createAgentDefinition(payload: AgentUpsertPayload) {
  return request<AgentDefinition>("/api/agents", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function cloneAgentDefinition(payload: AgentClonePayload) {
  return request<AgentDefinition>(`/api/agents/${payload.source_agent_id}/clone`, {
    method: "POST",
    body: JSON.stringify({ id: payload.id, name: payload.name }),
  });
}

export async function attachAgentCapability(agentId: string, payload: AgentCapabilityAttachmentPayload) {
  return request<{ status: string }>(`/api/agents/${agentId}/capabilities/attachments`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listTaskToolApprovals(taskId: string, params?: { status?: string }) {
  const searchParams = new URLSearchParams();
  if (params?.status) {
    searchParams.set("status", params.status);
  }
  const suffix = searchParams.toString() ? `?${searchParams.toString()}` : "";
  return request<{ items: ToolApproval[]; next_cursor: string | null }>(
    `/api/tasks/${taskId}/tool-approvals${suffix}`,
  );
}

export async function approveToolApproval(taskId: string, approvalId: string, reason: string) {
  return request<{ items: ToolApproval[]; next_cursor: string | null }>(
    `/api/tasks/${taskId}/tool-approvals/${approvalId}/approve`,
    {
      method: "POST",
      headers: authHeaders(DEV_ADMIN_BEARER_TOKEN),
      body: JSON.stringify({ reason }),
    },
  );
}

export async function rejectToolApproval(taskId: string, approvalId: string, reason: string) {
  return request<{ items: ToolApproval[]; next_cursor: string | null }>(
    `/api/tasks/${taskId}/tool-approvals/${approvalId}/reject`,
    {
      method: "POST",
      headers: authHeaders(DEV_ADMIN_BEARER_TOKEN),
      body: JSON.stringify({ reason }),
    },
  );
}

export async function modifyToolApproval(
  taskId: string,
  approvalId: string,
  modifiedInputJson: Record<string, unknown>,
  reason: string,
) {
  return request<{ items: ToolApproval[]; next_cursor: string | null }>(
    `/api/tasks/${taskId}/tool-approvals/${approvalId}/modify`,
    {
      method: "POST",
      headers: authHeaders(DEV_ADMIN_BEARER_TOKEN),
      body: JSON.stringify({ modified_input_json: modifiedInputJson, reason }),
    },
  );
}

export async function listEvalDatasets() {
  return request<{ items: EvalDataset[]; next_cursor: string | null }>("/api/evals/datasets");
}

export async function createEvalDataset(payload: { name: string; description: string }) {
  return request<EvalDataset>("/api/evals/datasets", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listEvalCases(datasetId: string) {
  return request<{ items: EvalCase[]; next_cursor: string | null }>(
    `/api/evals/datasets/${datasetId}/cases`,
  );
}

export async function createEvalCaseFromRun(
  datasetId: string,
  taskId: string,
  payload: { expected_json: Record<string, unknown>; tags_json: string[] },
) {
  return request<EvalCase>(`/api/evals/datasets/${datasetId}/cases/from-run/${taskId}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function createEvalRun(datasetId: string, payload: { agent_id?: string | null }) {
  return request<EvalRun>(`/api/evals/datasets/${datasetId}/runs`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listEvalRuns() {
  return request<{ items: EvalRun[]; next_cursor: string | null }>("/api/evals/runs");
}

export async function getEvalRun(evalRunId: string) {
  return request<EvalRun>(`/api/evals/runs/${evalRunId}`);
}

export type RegressionDelta = {
  baseline_run_id: string;
  current_run_id: string;
  task_success_rate_delta: number;
  tool_selection_accuracy_delta: number;
  avg_latency_ms_delta: number;
  grounding_pass_rate_delta: number;
  citation_coverage_rate_delta: number;
  unsupported_marker_rate_delta: number;
  fallback_mismatch_rate_delta: number;
  forbidden_evidence_leak_rate_delta: number;
  required_evidence_miss_rate_delta: number;
  newly_failing_case_ids: string[];
  newly_passing_case_ids: string[];
  newly_grounding_failing_case_ids: string[];
  newly_forbidden_leak_case_ids: string[];
  is_regression: boolean;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  grounding_sample_count: number;
  low_sample_count: boolean;
  low_sample_caveat: string | null;
};

export async function setEvalBaseline(datasetId: string, evalRunId: string) {
  return request<EvalDataset>(`/api/evals/datasets/${datasetId}/baseline`, {
    method: "PATCH",
    body: JSON.stringify({ eval_run_id: evalRunId }),
  });
}

export async function getEvalRunRegression(evalRunId: string) {
  return request<RegressionDelta | null>(`/api/evals/runs/${evalRunId}/regression`);
}

export function taskEventStreamUrl(taskId: string) {
  const params = new URLSearchParams({ access_token: DEV_BEARER_TOKEN });
  return `${API_BASE_URL}/api/tasks/${taskId}/events/stream?${params.toString()}`;
}

function parseSseFrame(frame: string): AgentPlanStreamEvent | null {
  if (!frame.trim()) return null;
  const eventLine = frame.split("\n").find((line) => line.startsWith("event:"));
  const dataLine = frame.split("\n").find((line) => line.startsWith("data:"));
  if (!eventLine || !dataLine) return null;
  const eventType = eventLine.slice("event:".length).trim();
  const payload = JSON.parse(dataLine.slice("data:".length).trim()) as Record<string, unknown>;
  if (eventType === "delta") {
    return { type: "delta", content: String(payload.content ?? "") };
  }
  if (eventType === "run_created") {
    const contextAssembly = asRecord(payload.context_assembly);
    return {
      type: "run_created",
      run_id: String(payload.run_id),
      status: String(payload.status),
      step_count: Number(payload.step_count ?? 0),
      message: String(payload.message ?? ""),
      context_assembly: {
        context_manifest_id:
          typeof contextAssembly.context_manifest_id === "string"
            ? contextAssembly.context_manifest_id
            : null,
        mode: typeof contextAssembly.mode === "string" ? contextAssembly.mode : null,
        included_count: Number(contextAssembly.included_count ?? 0),
        omitted_count: Number(contextAssembly.omitted_count ?? 0),
        omission_reasons: Array.isArray(contextAssembly.omission_reasons)
          ? contextAssembly.omission_reasons.map(String)
          : [],
      },
    };
  }
  if (eventType === "error") {
    return { type: "error", message: String(payload.message ?? "stream failed") };
  }
  return null;
}

export function parseChatSseFrame(frame: string): AgentChatStreamEvent | null {
  if (!frame.trim()) return null;
  const eventLine = frame.split("\n").find((line) => line.startsWith("event:"));
  const dataLine = frame.split("\n").find((line) => line.startsWith("data:"));
  if (!eventLine || !dataLine) return null;
  const eventType = eventLine.slice("event:".length).trim();
  const payload = JSON.parse(dataLine.slice("data:".length).trim()) as Record<string, unknown>;
  if (eventType === "delta") return { type: "delta", content: String(payload.content ?? "") };
  if (eventType === "think_delta") {
    return { type: "think_delta", content: String(payload.content ?? "") };
  }
  if (eventType === "run_created") {
    const contextAssembly = asRecord(payload.context_assembly);
    return {
      type: "run_created",
      run_id: String(payload.run_id),
      status: String(payload.status),
      step_count: Number(payload.step_count ?? 0),
      message: String(payload.message ?? ""),
      context_assembly: {
        context_manifest_id:
          typeof contextAssembly.context_manifest_id === "string"
            ? contextAssembly.context_manifest_id
            : null,
        mode: typeof contextAssembly.mode === "string" ? contextAssembly.mode : null,
        included_count: Number(contextAssembly.included_count ?? 0),
        omitted_count: Number(contextAssembly.omitted_count ?? 0),
        omission_reasons: Array.isArray(contextAssembly.omission_reasons)
          ? contextAssembly.omission_reasons.map(String)
          : [],
      },
    };
  }
  if (eventType === "orchestration") {
    return {
      type: "orchestration",
      mode: String(payload.mode ?? "unknown"),
      run_id: String(payload.run_id ?? ""),
      message: String(payload.message ?? ""),
      payload,
    };
  }
  if (eventType === "tool_call_requested") {
    return {
      type: "tool_call_requested",
      tool_call_id: String(payload.tool_call_id ?? payload.id ?? ""),
      tool_name: String(payload.tool_name ?? ""),
      source: typeof payload.source === "string" ? payload.source : null,
      input_json: asRecord(payload.input_json),
      status: String(payload.status ?? "preview"),
      risk: typeof payload.risk === "string" ? payload.risk : undefined,
      sandbox: typeof payload.sandbox === "string" ? payload.sandbox : undefined,
      approval_id: typeof payload.approval_id === "string" ? payload.approval_id : null,
    };
  }
  if (eventType === "tool_call_result") {
    return {
      type: "tool_call_result",
      tool_call_id: String(payload.tool_call_id ?? payload.id ?? ""),
      tool_name: String(payload.tool_name ?? ""),
      output_json: asRecord(payload.output_json),
      output_summary:
        typeof payload.output_summary === "string" ? payload.output_summary : null,
      status: String(payload.status ?? ""),
      duration_ms:
        typeof payload.duration_ms === "number" ? payload.duration_ms : null,
      trace_id: typeof payload.trace_id === "string" ? payload.trace_id : null,
      approval_id: typeof payload.approval_id === "string" ? payload.approval_id : null,
    };
  }
  if (eventType === "artifact_created") {
    return {
      type: "artifact_created",
      name: String(payload.name ?? "artifact"),
      artifact_type: artifactType(payload.artifact_type),
      status: String(payload.status ?? "ready"),
      content: payload.content,
      run_id: typeof payload.run_id === "string" ? payload.run_id : undefined,
    };
  }
  if (eventType === "usage") {
    return {
      type: "usage",
      input_tokens: Number(payload.input_tokens ?? 0),
      output_tokens: Number(payload.output_tokens ?? 0),
      cost_usd: payload.cost_usd == null ? null : String(payload.cost_usd),
      cost_unavailable: Boolean(payload.cost_unavailable ?? payload.cost_usd == null),
      ttfb_ms: Number(payload.ttfb_ms ?? 0),
      duration_ms: Number(payload.duration_ms ?? 0),
      model_call_id: typeof payload.model_call_id === "string" ? payload.model_call_id : null,
    };
  }
  if (eventType === "done") {
    return {
      type: "done",
      run_id: String(payload.run_id),
      active_branch_id: typeof payload.active_branch_id === "string" ? payload.active_branch_id : null,
      continue_from_node_id:
        typeof payload.continue_from_node_id === "string" ? payload.continue_from_node_id : null,
      status: String(payload.status),
      step_count: Number(payload.step_count ?? 0),
      message: String(payload.message ?? ""),
      knowledge_grounding:
        typeof payload.knowledge_grounding === "string" ? payload.knowledge_grounding : null,
    };
  }
  if (eventType === "error") {
    return {
      type: "error",
      message: String(payload.message ?? "stream failed"),
      recoverable: Boolean(payload.recoverable ?? false),
    };
  }
  return null;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function artifactType(value: unknown): "code" | "json" | "diff" | "chart" | "text" {
  return ["code", "json", "diff", "chart", "text"].includes(String(value))
    ? (String(value) as "code" | "json" | "diff" | "chart" | "text")
    : "text";
}

export async function getModelSettings() {
  return request<ModelSettings>("/api/settings/models");
}

export async function updateModelSettings(payload: ModelSettings) {
  return request<ModelSettings>("/api/settings/models", {
    method: "PUT",
    headers: authHeaders(DEV_ADMIN_BEARER_TOKEN),
    body: JSON.stringify(payload),
  });
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

export async function runWarmPoolBenchmark(payload = { iterations: 5, target_startup_ms: 50, mode: "projection" }) {
  return request<WarmPoolBenchmark>("/api/sandboxes/warm-pool/benchmark", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listWarmPoolBenchmarks(limit = 20) {
  return request<{ items: WarmPoolBenchmark[]; next_cursor: string | null }>(
    `/api/sandboxes/warm-pool/benchmarks?limit=${limit}`,
  );
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

export async function getTokenSavings(limit = 50) {
  return request<TokenSavingsPage>(`/api/observability/token-savings?limit=${limit}`);
}

export async function getObservabilityGroundingQuality(params?: {
  dataset_id?: string;
  eval_run_id?: string;
  agent_id?: string;
  failure_type?: string;
  grounding_passed?: boolean;
  forbidden_evidence_leaked?: boolean;
  fallback_mismatch?: boolean;
  unsupported_marker_present?: boolean;
  limit?: number;
}) {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== "") {
      searchParams.set(key, String(value));
    }
  }
  const suffix = searchParams.toString() ? `?${searchParams.toString()}` : "";
  return request<ObservabilityGroundingQuality>(`/api/observability/grounding-quality${suffix}`);
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
