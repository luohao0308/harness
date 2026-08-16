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
  sync?: {
    getStatus?: () => Promise<DesktopSyncRuntimeStatus>;
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
    getWorkspaceRoot?: () => Promise<DesktopFileWatchState>;
    setWorkspaceRoot?: (rootPath: string | null) => Promise<DesktopFileWatchState>;
    startWatch?: () => Promise<DesktopFileWatchState>;
    stopWatch?: () => Promise<DesktopFileWatchState>;
    listFiles?: (options?: {
      path?: string;
      maxDepth?: number;
      maxEntries?: number;
    }) => Promise<DesktopFileListResult>;
    readFile?: (path: string) => Promise<DesktopFileReadResult>;
    writeFile?: (path: string, content: string) => Promise<DesktopFileWriteResult>;
    onChange?: (callback: (event: DesktopFileChangeEvent) => void) => (() => void);
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

type DesktopFileListResult = {
  rootPath: string | null;
  entries: DesktopFileEntry[];
  truncated: boolean;
};

interface Window {
  desktopApi?: DesktopApi;
}
