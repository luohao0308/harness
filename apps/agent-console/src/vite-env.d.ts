/// <reference types="vite/client" />

type DesktopRoutePayload = {
  route: string;
  source: "deep-link" | "notification" | "menu" | "shortcut" | "ipc";
};

type DesktopNotificationOptions = {
  kind?: "completed" | "error" | "conflict" | "info";
  title: string;
  body: string;
  route?: string;
  silent?: boolean;
};

type DesktopUpdateChannel = "stable" | "beta";

type DesktopUpdateState =
  | "idle"
  | "checking"
  | "available"
  | "not-available"
  | "downloading"
  | "downloaded"
  | "error";

type DesktopUpdateProgress = {
  percent?: number;
  bytesPerSecond?: number;
  transferred?: number;
  total?: number;
};

type DesktopUpdateStatus = {
  state: DesktopUpdateState;
  channel: DesktopUpdateChannel;
  currentVersion: string;
  latestVersion?: string | null;
  releaseUrl?: string | null;
  progress?: DesktopUpdateProgress | null;
  files?: string[];
  checkedAt?: string;
  reason?: string | null;
  error?: string | null;
};

type DesktopFeedbackPayload = {
  title: string;
  description: string;
  category?: "bug" | "idea" | "praise" | "support";
  channel?: DesktopUpdateChannel;
  app_version: string;
  platform: string;
  logs?: string[];
  screenshot_data_url?: string | null;
  metadata?: Record<string, unknown>;
};

type DesktopFeedbackResponse = {
  received: boolean;
  feedback_id: string;
  received_at: string;
};

type DesktopMetricsSummary = {
  startup_count: number;
  startup_avg_ms: number | null;
  startup_p95_ms: number | null;
  crash_events: number;
  sync_successes: number;
  sync_failures: number;
  sync_success_rate: number | null;
};

type LocalRuntimeModelDiscoveryInput = {
  baseUrl: string;
  apiKey?: string;
};

type LocalRuntimeModelDiscoveryResult = {
  models: string[];
  durationMs: number;
  latencyMs?: number;
  modelCount?: number;
};

type LocalRuntimeModelConfigurationInput = {
  baseUrl: string;
  model: string;
  apiKey?: string;
};

type DesktopApi = {
  storage?: {
    getItem: (key: string) => string | null;
    setItem: (key: string, value: string) => boolean;
    removeItem: (key: string) => boolean;
  };
  localRuntime?: {
    getModelStatus?: () => Promise<LocalRuntimeModelStatus>;
    setModelApiKey?: (apiKey: string) => Promise<LocalRuntimeModelStatus>;
    saveModelConfiguration?: (input: LocalRuntimeModelConfigurationInput) => Promise<LocalRuntimeModelStatus>;
    discoverModels?: (input: LocalRuntimeModelDiscoveryInput) => Promise<LocalRuntimeModelDiscoveryResult>;
    deleteModelApiKey?: () => Promise<LocalRuntimeModelStatus>;
    renewSession?: () => Promise<void>;
    testModelConnection?: () => Promise<LocalRuntimeModelStatus>;
    openWebExtension?: () => Promise<void>;
  };
  system?: {
    showWindow?: (route?: string) => Promise<void>;
    hideWindow?: () => Promise<void>;
    getStartupEnabled?: () => Promise<boolean>;
    setStartupEnabled?: (enabled: boolean) => Promise<boolean>;
    notify?: (options: DesktopNotificationOptions) => Promise<void>;
    getPendingRoute?: () => Promise<DesktopRoutePayload | null>;
  };
  window?: {
    openRun?: (runId: string) => Promise<DesktopWindowSummary>;
    list?: () => Promise<{ items: DesktopWindowSummary[] }>;
    getState?: () => Promise<{ profileId: string; items: DesktopWindowSummary[] }>;
  };
  profile?: {
    list?: () => Promise<{ activeProfileId: string; profiles: DesktopProfile[] }>;
    save?: (profile: DesktopProfileSaveInput) => Promise<DesktopProfile>;
    switch?: (profileId: string) => Promise<DesktopProfile>;
  };
  localModel?: {
    getSettings?: () => Promise<DesktopLocalModelSettings>;
    setSettings?: (settings: Partial<DesktopLocalModelSettings>) => Promise<DesktopLocalModelSettings>;
    testConnection?: () => Promise<DesktopLocalModelHealth>;
  };
  offline?: {
    runSimpleTask?: (payload: { prompt: string; useLocalModel?: boolean }) => Promise<DesktopOfflineTask>;
    listTasks?: () => Promise<{ items: DesktopOfflineTask[] }>;
    promoteResultToPendingAgentTask?: (offlineTaskId: string) => Promise<{ taskId: string; operationId: number | null }>;
  };
  offlineAgent?: {
    run?: (input: {
      prompt: string;
      useLocalModel?: boolean;
      toolRequest?: { name: "workspace.list_files" | "workspace.read_text" | "workspace.write_text"; input: Record<string, unknown> } | null;
    }) => Promise<DesktopOfflineAgentRun>;
    listRuns?: (limit?: number) => Promise<{ items: DesktopOfflineAgentRun[] }>;
    getRun?: (runId: string) => Promise<{ approvals: Array<{ status: string; reason: string; decision?: Record<string, unknown>; target?: { path?: string; exists?: boolean; sha256?: string | null; mtimeMs?: number | null; sizeBytes?: number | null }; proposal?: { sha256?: string; sizeBytes?: number } }> }>;
    cancel?: (runId: string) => Promise<DesktopOfflineAgentRun>;
    resume?: (runId: string) => Promise<DesktopOfflineAgentRun>;
    decideApproval?: (approvalId: string, approved: boolean) => Promise<DesktopOfflineAgentRun>;
  };
  sync?: {
    getStatus?: () => Promise<DesktopSyncRuntimeStatus>;
    getConflicts?: () => Promise<DesktopSyncConflictSummary>;
    runNow?: () => Promise<DesktopSyncRuntimeStatus>;
    onStatus?: (callback: (status: DesktopSyncRuntimeStatus) => void) => () => void;
  };
  updates?: {
    getStatus?: () => Promise<DesktopUpdateStatus>;
    check?: () => Promise<DesktopUpdateStatus>;
    download?: () => Promise<DesktopUpdateStatus>;
    install?: () => Promise<void>;
  };
  feedback?: {
    submit?: (payload: DesktopFeedbackPayload) => Promise<DesktopFeedbackResponse>;
    getMetricsSummary?: () => Promise<DesktopMetricsSummary>;
  };
  events?: {
    onOpenRoute?: (callback: (payload: DesktopRoutePayload) => void) => () => void;
    onUpdateStatus?: (callback: (status: DesktopUpdateStatus) => void) => () => void;
    onProfileChanged?: (callback: (profile: DesktopProfile) => void) => () => void;
  };
  file?: {
    selectWorkspaceRoot?: () => Promise<DesktopFileWatchState | null>;
    selectAuthorizedWorkspaceRoot?: () => Promise<DesktopWorkspaceAuthorization | null>;
    getWorkspaceRoot?: () => Promise<DesktopFileWatchState>;
    setWorkspaceRoot?: (rootPath: string | null) => Promise<DesktopFileWatchState>;
    startWatch?: () => Promise<DesktopFileWatchState>;
    stopWatch?: () => Promise<DesktopFileWatchState>;
    listFiles?: (options?: {
      path?: string;
      maxDepth?: number;
      maxEntries?: number;
    }) => Promise<DesktopFileListResult>;
    scanProjectKnowledge?: (
      options?: DesktopProjectKnowledgeScanOptions,
    ) => Promise<DesktopProjectKnowledgeSnapshot>;
    readFile?: (path: string) => Promise<DesktopFileReadResult>;
    writeFile?: (path: string, content: string) => Promise<DesktopFileWriteResult>;
    onChange?: (callback: (event: DesktopFileChangeEvent) => void) => (() => void);
  };
  changeReview?: {
    getStatus?: () => Promise<DesktopChangeReviewStatus>;
    getDiff?: (path: string) => Promise<DesktopChangeDiff>;
    mutate?: (input: DesktopChangeMutationInput) => Promise<DesktopChangeMutationResult>;
  };
};

type LocalRuntimeModelStatus = {
  state: "setup_required" | "configured" | "healthy" | "error";
  provider: string;
  model: string;
  base_url: string;
  secret_storage: "persistent" | "session" | "unavailable";
  message?: string | null;
};

interface ImportMetaEnv {
  readonly VITE_RUNTIME_PROFILE?: "enterprise" | "local";
}

type DesktopProfile = {
  id: string;
  label: string;
  apiBaseUrl: string;
  dataPath: string;
  createdAt: string;
  updatedAt: string;
  hasCredential: boolean;
  credentialStorage: "persistent" | "session" | "none";
};

type DesktopProfileSaveInput = {
  id?: string;
  label: string;
  apiBaseUrl?: string;
  authToken?: string;
  dataPath?: string;
};

type DesktopWindowSummary = {
  id: number;
  key: string;
  kind: "main" | "run";
  runId: string | null;
  route: string;
  profileId: string;
  focused: boolean;
  visible: boolean;
};

type DesktopLocalModelSettings = {
  enabled: boolean;
  provider: "ollama" | "openai-compatible";
  baseUrl: string;
  model: string;
  updatedAt: string;
};

type DesktopLocalModelHealth = {
  available: boolean;
  checkedAt: string;
  durationMs: number;
  error?: string | null;
};

type DesktopOfflineTask = {
  id: string;
  prompt: string;
  result: string;
  modelSource: "deterministic-local" | "local-model";
  status: "completed" | "failed";
  createdAt: string;
  modelRequested?: boolean;
  fallbackReason?: string | null;
  durationMs?: number;
};

type DesktopOfflineAgentStatus = "PENDING" | "RUNNING" | "WAITING_APPROVAL" | "INTERRUPTED" | "COMPLETED" | "FAILED" | "CANCELLED";
type DesktopOfflineAgentRun = {
  id: string;
  prompt: string;
  result: string | null;
  status: DesktopOfflineAgentStatus;
  modelSource: "deterministic-local" | "local-model" | null;
  modelProvider: string;
  modelName: string;
  modelRequested: boolean;
  fallbackReason: string | null;
  errorMessage: string | null;
  toolRequest: { name: "workspace.list_files" | "workspace.read_text" | "workspace.write_text"; input: Record<string, unknown> } | null;
  pendingApprovalId: string | null;
  createdAt: string;
  updatedAt: string;
  startedAt: string | null;
  completedAt: string | null;
  syncRevision: number;
};

type DesktopSyncRuntimeStatus = {
  state: "idle" | "scheduled" | "syncing" | "error" | "closed";
  profileId: string | null;
  dataPath: string | null;
  online: boolean;
  lastChangeTimestamp: string;
  lastStartedAt: string | null;
  lastCompletedAt: string | null;
  lastError: string | null;
  nextRetryAt: string | null;
  retryAttempt: number;
  pendingOperations: number;
  retryableOperations: number;
  conflictCount: number;
};

type DesktopSyncConflictSummary = {
  tasks: Array<{
    id: string;
    title: string;
    status?: string;
    updated_at?: string;
    conflict_detected: boolean;
  }>;
  serverConflicts: Array<{
    entity_id: string;
    entity_type: string;
    server_version: Record<string, unknown>;
    client_version: Record<string, unknown>;
  }>;
};

type DesktopFileEntry = {
  path: string;
  name: string;
  kind: "file" | "directory";
  sizeBytes: number;
  modifiedAt: string;
  depth: number;
  mimeType: string | null;
};

type DesktopFileChangeEvent = {
  rootPath: string;
  path: string;
  eventType: "change" | "rename";
  kind: "file" | "directory" | "unknown";
  changedAt: string;
};

type DesktopFileReadResult = {
  path: string;
  content: string;
  sizeBytes: number;
  totalSizeBytes: number;
  mimeType: string;
  truncated: boolean;
  editable: boolean;
};

type DesktopFileWriteResult = {
  path: string;
  bytesWritten: number;
  updatedAt: string;
};

type DesktopFileWatchState = {
  rootPath: string | null;
  watching: boolean;
};

type DesktopWorkspaceAuthorization = {
  authorization: string;
  label: string;
  expiresAt: string;
};

type DesktopFileListResult = {
  rootPath: string | null;
  entries: DesktopFileEntry[];
  truncated: boolean;
};

type DesktopProjectKnowledgeScanOptions = {
  ignorePatterns?: string[];
  maxFiles?: number;
  maxFileBytes?: number;
  maxTotalBytes?: number;
  maxDurationMs?: number;
};

type DesktopProjectKnowledgeSnapshot = {
  schemaVersion: "desktop-project-knowledge-snapshot-v1" | "desktop-project-knowledge-snapshot-v2";
  defaultIgnoreVersion: "v1";
  rootIdentity: string;
  snapshotGeneration?: number;
  snapshotCursor: string;
  complete: boolean;
  truncated: boolean;
  truncationReason: "max_files" | "max_total_bytes" | "max_duration" | "scan_error" | null;
  files: Array<{
    relativePath: string;
    status: "ready" | "skipped";
    content: string | null;
    contentSha256: string | null;
    sizeBytes: number;
    modifiedAt: string;
    mimeType: string | null;
    skipReason: "symlink" | "file_too_large" | "invalid_utf8" | "changed_during_scan" | "read_failed" | null;
  }>;
  errors: Array<{ path: string; reason: string }>;
  scannedFiles: number;
  indexedFiles: number;
  totalBytes: number;
  startedAt: string;
  completedAt: string;
};

type DesktopChangeFile = {
  path: string;
  previousPath: string | null;
  indexStatus: string;
  worktreeStatus: string;
  staged: boolean;
  unstaged: boolean;
  untracked: boolean;
  conflicted: boolean;
};

type DesktopChangeReviewStatus = {
  state: "ready" | "no-workspace" | "not-repository" | "git-unavailable" | "error";
  rootPath: string | null;
  repositoryRoot: string | null;
  branch: string | null;
  upstream: string | null;
  ahead: number;
  behind: number;
  files: DesktopChangeFile[];
  errorCode: string | null;
  message: string | null;
};

type DesktopChangeDiffHunk = {
  id: string;
  header: string;
  oldStart: number;
  oldLines: number;
  newStart: number;
  newLines: number;
  lines: string[];
};

type DesktopChangeDiffSection = {
  mode: "staged" | "worktree";
  kind: "text" | "binary" | "conflict" | "empty" | "too-large";
  headerLines: string[];
  hunks: DesktopChangeDiffHunk[];
  canStage: boolean;
  canUnstage: boolean;
  canRevert: boolean;
  message: string | null;
};

type DesktopChangeDiff = {
  path: string;
  previewToken: string;
  expiresAt: string;
  sections: DesktopChangeDiffSection[];
};

type DesktopChangeMutationInput = {
  action: "stage" | "unstage" | "revert";
  previewToken: string;
  hunkIds: string[];
  auditContext?: {
    taskId?: string;
    runId?: string;
    approvalId?: string;
  };
};

type DesktopChangeMutationResult = {
  action: "stage" | "unstage" | "revert";
  path: string;
  status: "completed";
  updatedAt: string;
  auditId: string;
  eventId: string | null;
};

interface Window {
  desktopApi?: DesktopApi;
}
