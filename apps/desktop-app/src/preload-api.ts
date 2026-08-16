/**
 * Type-safe IPC API definitions for desktop app
 * Exposed to renderer via contextBridge in preload.ts
 */

export type TaskStatus =
  | 'CREATED'
  | 'PLANNING'
  | 'PLANNED'
  | 'RUNNING'
  | 'WAITING_SUBAGENTS'
  | 'WAITING_APPROVAL'
  | 'FAILED'
  | 'COMPLETED'
  | 'CANCELLED'

export type Task = {
  id: string
  agent_id?: string | null
  title: string
  goal: string
  status: TaskStatus
  model_provider: string
  model_name: string
  max_runtime_seconds: number
  max_subagents: number
  enable_sandbox: boolean
  enable_network: boolean
  created_at: string
  updated_at: string
  completed_at: string | null
}

export type LocalAgentConversationBinding = {
  id: string
  connection_id: string
  agent_id: string
  agent_session_id: string
  adapter_session_id: string | null
  resume_mode: string
  status: string
  created_at: string
  updated_at: string
}

export type LocalAgentSendMessagePayload = {
  content: string
  client_message_id: string
  resume_of_client_message_id?: string | null
  resume_of_user_message_id?: string | null
  workspace_context_provided?: boolean
  workspace_mode?: 'chat' | 'plan'
  model_provider?: string | null
  model_name?: string | null
}

export type LocalAgentSendMessageResponse = {
  bridge_task_id: string
  run_id: string
  agent_session_id: string
  user_message_id: string
  status: string
}

export type AgentEvent = {
  id: string
  agent_run_id: string | null
  event_type: string
  payload_json: Record<string, unknown>
  created_at: string
}

export type AgentRunWorkspace = {
  run: Task
  plan: unknown | null
  events: AgentEvent[]
  knowledge_grounding: unknown | null
  context_assembly: unknown | null
  token_optimization: Record<string, unknown>
  subagents: unknown[]
  tool_calls: unknown[]
  model_calls: unknown[]
  approvals: unknown[]
  assignments: unknown[]
  handoffs: unknown[]
}

export type SseConnectionStatus = 'connecting' | 'open' | 'closed' | 'retrying' | 'failed'

export type LocalAgentConnection = {
  id: string
  agent_id: string
  display_name: string
  adapter_kind: string
  status: string
}

export type DesktopRoutePayload = {
  route: string
  source: 'deep-link' | 'notification' | 'menu' | 'shortcut' | 'ipc'
}

export type SystemNotificationOptions = {
  kind?: 'completed' | 'error' | 'conflict' | 'info'
  title: string
  body: string
  route?: string
  silent?: boolean
}

export type DesktopUpdateChannel = 'stable' | 'beta'

export type DesktopUpdateState =
  | 'idle'
  | 'checking'
  | 'available'
  | 'not-available'
  | 'downloading'
  | 'downloaded'
  | 'error'

export type DesktopUpdateProgress = {
  percent?: number
  bytesPerSecond?: number
  transferred?: number
  total?: number
}

export type DesktopUpdateStatus = {
  state: DesktopUpdateState
  channel: DesktopUpdateChannel
  currentVersion: string
  latestVersion?: string | null
  releaseUrl?: string | null
  progress?: DesktopUpdateProgress | null
  files?: string[]
  checkedAt?: string
  reason?: string | null
  error?: string | null
}

export type DesktopUpdateCheckResponse = {
  update_available: boolean
  channel: DesktopUpdateChannel
  current_version: string
  latest_version: string
  platform: string
  arch: string
  release_url: string
  feed_url: string
  metadata_url: string
  checked_at: string
  notes?: string | null
}

export type DesktopFeedbackPayload = {
  title: string
  description: string
  category?: 'bug' | 'idea' | 'praise' | 'support'
  channel?: DesktopUpdateChannel
  app_version: string
  platform: string
  logs?: string[]
  screenshot_data_url?: string | null
  metadata?: Record<string, unknown>
}

export type DesktopFeedbackResponse = {
  received: boolean
  feedback_id: string
  received_at: string
}

export type DesktopMetricName = 'startup_time_ms' | 'crash_event' | 'sync_success' | 'sync_failure'

export type DesktopMetricSamplePayload = {
  metric_name: DesktopMetricName
  channel?: DesktopUpdateChannel
  app_version: string
  platform: string
  value?: number
  metadata?: Record<string, unknown>
}

export type DesktopMetricSampleResponse = {
  received: boolean
  metric_name: DesktopMetricName
  recorded_at: string
}

export type DesktopMetricsSummary = {
  startup_count: number
  startup_avg_ms: number | null
  startup_p95_ms: number | null
  crash_events: number
  sync_successes: number
  sync_failures: number
  sync_success_rate: number | null
}

export type DesktopFileEntry = {
  path: string
  name: string
  kind: 'file' | 'directory'
  sizeBytes: number
  modifiedAt: string
  depth: number
  mimeType: string | null
}

export type DesktopFileChangeEvent = {
  rootPath: string
  path: string
  eventType: 'change' | 'rename'
  kind: 'file' | 'directory' | 'unknown'
  changedAt: string
}

export type DesktopFileReadResult = {
  path: string
  content: string
  sizeBytes: number
  totalSizeBytes: number
  mimeType: string
  truncated: boolean
  editable: boolean
}

export type DesktopFileWriteResult = {
  path: string
  bytesWritten: number
  updatedAt: string
}

export type DesktopFileWatchState = {
  rootPath: string | null
  watching: boolean
}

export type DesktopFileListResult = {
  rootPath: string | null
  entries: DesktopFileEntry[]
  truncated: boolean
}

export type DesktopProfile = {
  id: string
  label: string
  apiBaseUrl: string
  dataPath: string
  createdAt: string
  updatedAt: string
  hasCredential: boolean
  credentialStorage: 'persistent' | 'session' | 'none'
}

export type DesktopProfileSaveInput = {
  id?: string
  label: string
  apiBaseUrl?: string
  authToken?: string
  dataPath?: string
}

export type DesktopWindowSummary = {
  id: number
  key: string
  kind: 'main' | 'run'
  runId: string | null
  route: string
  profileId: string
  focused: boolean
  visible: boolean
}

export type DesktopLocalModelSettings = {
  enabled: boolean
  provider: 'ollama' | 'openai-compatible'
  baseUrl: string
  model: string
  updatedAt: string
}

export type DesktopLocalModelHealth = {
  available: boolean
  checkedAt: string
  durationMs: number
  error?: string | null
}

export type LocalRuntimeModelStatus = {
  state: 'setup_required' | 'configured' | 'healthy' | 'error'
  provider: string
  model: string
  base_url: string
  secret_storage: 'persistent' | 'session' | 'unavailable'
  message?: string | null
}

export type LocalRuntimeModelConfigInput = {
  baseUrl: string
  model: string
  models?: string[]
  apiKey?: string
}

export type LocalRuntimeModelDiscoveryInput = {
  baseUrl: string
  apiKey?: string
}

export type LocalRuntimeModelDiscovery = {
  models: string[]
  durationMs: number
  latencyMs: number
}

export type DesktopOfflineTask = {
  id: string
  prompt: string
  result: string
  modelSource: 'deterministic-local' | 'local-model'
  status: 'completed' | 'failed'
  createdAt: string
  modelRequested?: boolean
  fallbackReason?: string | null
  durationMs?: number
}

export type DesktopSyncRuntimeStatus = {
  state: 'idle' | 'scheduled' | 'syncing' | 'error' | 'closed'
  profileId: string | null
  dataPath: string | null
  online: boolean
  lastChangeTimestamp: string
  lastStartedAt: string | null
  lastCompletedAt: string | null
  lastError: string | null
  nextRetryAt: string | null
  retryAttempt: number
  pendingOperations: number
  retryableOperations: number
  conflictCount: number
}

/**
 * Desktop API exposed to renderer process
 */
export interface DesktopApi {
  storage: {
    getItem: (key: string) => string | null
    setItem: (key: string, value: string) => boolean
    removeItem: (key: string) => boolean
  }

  localRuntime: {
    getModelStatus: () => Promise<LocalRuntimeModelStatus>
    saveModelConfiguration: (input: LocalRuntimeModelConfigInput) => Promise<LocalRuntimeModelStatus>
    discoverModels: (input: LocalRuntimeModelDiscoveryInput) => Promise<LocalRuntimeModelDiscovery>
    setModelApiKey: (apiKey: string) => Promise<LocalRuntimeModelStatus>
    deleteModelApiKey: () => Promise<LocalRuntimeModelStatus>
    renewSession: () => Promise<void>
    openWebExtension: () => Promise<void>
  }

  // Agent operations
  agent: {
    bindConversation: (
      connectionId: string,
      payload?: {
        agent_session_id?: string | null
        title?: string | null
        adapter_session_id?: string | null
        resume_mode?: 'native_resume' | 'context_replay_new_session'
      }
    ) => Promise<LocalAgentConversationBinding>

    sendMessage: (
      bindingId: string,
      payload: LocalAgentSendMessagePayload
    ) => Promise<LocalAgentSendMessageResponse>

    getWorkspace: (
      runId: string,
      selectors?: { retrieval_session_id?: string; prompt_manifest_id?: string }
    ) => Promise<AgentRunWorkspace>

    listConnections: () => Promise<{ items: LocalAgentConnection[] }>
  }

  // Task operations
  task: {
    get: (taskId: string) => Promise<Task>
    cancel: (taskId: string) => Promise<void>
    list: (filters?: { status?: TaskStatus }) => Promise<{ items: Task[] }>
  }

  // Native app/system integration
  system: {
    showWindow: (route?: string) => Promise<void>
    hideWindow: () => Promise<void>
    getStartupEnabled: () => Promise<boolean>
    setStartupEnabled: (enabled: boolean) => Promise<boolean>
    notify: (options: SystemNotificationOptions) => Promise<void>
    getPendingRoute: () => Promise<DesktopRoutePayload | null>
  }

  window: {
    openRun: (runId: string) => Promise<DesktopWindowSummary>
    list: () => Promise<{ items: DesktopWindowSummary[] }>
    getState: () => Promise<{ profileId: string; items: DesktopWindowSummary[] }>
  }

  profile: {
    list: () => Promise<{ activeProfileId: string; profiles: DesktopProfile[] }>
    save: (profile: DesktopProfileSaveInput) => Promise<DesktopProfile>
    switch: (profileId: string) => Promise<DesktopProfile>
  }

  localModel: {
    getSettings: () => Promise<DesktopLocalModelSettings>
    setSettings: (settings: Partial<DesktopLocalModelSettings>) => Promise<DesktopLocalModelSettings>
    testConnection: () => Promise<DesktopLocalModelHealth>
  }

  offline: {
    runSimpleTask: (payload: { prompt: string; useLocalModel?: boolean }) => Promise<DesktopOfflineTask>
    listTasks: () => Promise<{ items: DesktopOfflineTask[] }>
    promoteResultToPendingAgentTask: (offlineTaskId: string) => Promise<{ taskId: string; operationId: number | null }>
  }

  sync: {
    getStatus: () => Promise<DesktopSyncRuntimeStatus>
    runNow: () => Promise<DesktopSyncRuntimeStatus>
    onStatus: (callback: (status: DesktopSyncRuntimeStatus) => void) => () => void
  }

  updates: {
    getStatus: () => Promise<DesktopUpdateStatus>
    check: () => Promise<DesktopUpdateStatus>
    download: () => Promise<DesktopUpdateStatus>
    install: () => Promise<void>
  }

  feedback: {
    submit: (payload: DesktopFeedbackPayload) => Promise<DesktopFeedbackResponse>
    recordMetric: (payload: DesktopMetricSamplePayload) => Promise<DesktopMetricSampleResponse>
    getMetricsSummary: () => Promise<DesktopMetricsSummary>
  }

  file: {
    selectWorkspaceRoot: () => Promise<DesktopFileWatchState | null>
    getWorkspaceRoot: () => Promise<DesktopFileWatchState>
    setWorkspaceRoot: (rootPath: string | null) => Promise<DesktopFileWatchState>
    startWatch: () => Promise<DesktopFileWatchState>
    stopWatch: () => Promise<DesktopFileWatchState>
    listFiles: (options?: { path?: string; maxDepth?: number; maxEntries?: number }) => Promise<DesktopFileListResult>
    readFile: (path: string) => Promise<DesktopFileReadResult>
    writeFile: (path: string, content: string) => Promise<DesktopFileWriteResult>
    onChange: (callback: (event: DesktopFileChangeEvent) => void) => (() => void)
  }

  // SSE event listeners
  events: {
    onMessageStream: (callback: (event: AgentEvent) => void) => () => void
    onConnectionStatus: (callback: (status: SseConnectionStatus) => void) => () => void
    onTaskStatusChange: (callback: (task: Task) => void) => () => void
    onOpenRoute: (callback: (payload: DesktopRoutePayload) => void) => () => void
    onUpdateStatus: (callback: (status: DesktopUpdateStatus) => void) => () => void
    onProfileChanged: (callback: (profile: DesktopProfile) => void) => () => void
  }
}
