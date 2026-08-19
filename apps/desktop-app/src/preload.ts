import { contextBridge, ipcRenderer } from 'electron'
import type {
  DesktopApi,
  DesktopFileChangeEvent,
  DesktopFileListResult,
  DesktopProjectKnowledgeScanOptions,
  DesktopProjectKnowledgeSnapshot,
  DesktopFileReadResult,
  DesktopFileWatchState,
  DesktopFileWriteResult,
  DesktopWorkspaceAuthorization,
  DesktopChangeDiff,
  DesktopChangeMutationInput,
  DesktopChangeMutationResult,
  DesktopChangeReviewStatus,
  LocalAgentConversationBinding,
  LocalAgentSendMessagePayload,
  LocalAgentSendMessageResponse,
  AgentRunWorkspace,
  LocalAgentConnection,
  Task,
  TaskStatus,
  AgentEvent,
  DesktopRoutePayload,
  SseConnectionStatus,
  DesktopUpdateStatus,
  SystemNotificationOptions,
  DesktopFeedbackPayload,
  DesktopFeedbackResponse,
  DesktopMetricSamplePayload,
  DesktopMetricSampleResponse,
  DesktopMetricsSummary,
  DesktopLocalModelSettings,
  DesktopOfflineTask,
  DesktopProfile,
  DesktopProfileSaveInput,
  DesktopWindowSummary,
  DesktopSyncRuntimeStatus,
  DesktopSyncConflictSummary,
  LocalRuntimeModelConfigInput,
  LocalRuntimeModelDiscovery,
  LocalRuntimeModelDiscoveryInput,
  LocalRuntimeModelStatus,
} from './preload-api'

async function invokeLocalRuntime<T>(channel: string, ...args: unknown[]): Promise<T> {
  return unwrapLocalRuntimeIpcResult<T>(await ipcRenderer.invoke(channel, ...args))
}

function unwrapLocalRuntimeIpcResult<T>(value: unknown): T {
  if (!isRecord(value) || typeof value.ok !== 'boolean') {
    throw new Error('desktop IPC returned an invalid response')
  }
  if (value.ok) {
    if (!Object.prototype.hasOwnProperty.call(value, 'value')) {
      throw new Error('desktop IPC returned an invalid response')
    }
    return value.value as T
  }
  if (!isRecord(value.error)
    || typeof value.error.name !== 'string'
    || typeof value.error.message !== 'string') {
    throw new Error('desktop IPC returned an invalid error response')
  }

  const error = new Error(value.error.message) as Error & { code?: string; status?: number }
  error.name = value.error.name
  if (typeof value.error.code === 'string') error.code = value.error.code
  if (typeof value.error.status === 'number') error.status = value.error.status
  throw error
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

const desktopApi: DesktopApi = {
  storage: {
    getItem: (key: string): string | null => {
      return ipcRenderer.sendSync('renderer-workspace-storage:get', key) as string | null
    },
    setItem: (key: string, value: string): boolean => {
      return ipcRenderer.sendSync('renderer-workspace-storage:set', key, value) === true
    },
    removeItem: (key: string): boolean => {
      return ipcRenderer.sendSync('renderer-workspace-storage:remove', key) === true
    },
  },
  localRuntime: {
    getModelStatus: (): Promise<LocalRuntimeModelStatus> => {
      return invokeLocalRuntime('local-runtime:get-model-status')
    },
    saveModelConfiguration: (input: LocalRuntimeModelConfigInput): Promise<LocalRuntimeModelStatus> => {
      return invokeLocalRuntime('local-runtime:save-model-configuration', input)
    },
    discoverModels: (input: LocalRuntimeModelDiscoveryInput): Promise<LocalRuntimeModelDiscovery> => {
      return invokeLocalRuntime('local-runtime:discover-models', input)
    },
    setModelApiKey: (apiKey: string): Promise<LocalRuntimeModelStatus> => {
      return invokeLocalRuntime('local-runtime:set-model-api-key', apiKey)
    },
    deleteModelApiKey: (): Promise<LocalRuntimeModelStatus> => {
      return invokeLocalRuntime('local-runtime:delete-model-api-key')
    },
    renewSession: (): Promise<void> => {
      return invokeLocalRuntime('local-runtime:renew-session')
    },
    openWebExtension: (): Promise<void> => {
      return invokeLocalRuntime('local-runtime:open-web-extension')
    },
  },
  agent: {
    bindConversation: (
      connectionId: string,
      payload: {
        agent_session_id?: string | null
        title?: string | null
        adapter_session_id?: string | null
        resume_mode?: 'native_resume' | 'context_replay_new_session'
      } = {}
    ): Promise<LocalAgentConversationBinding> => {
      return ipcRenderer.invoke('agent:bind-conversation', connectionId, payload)
    },
    sendMessage: (
      bindingId: string,
      payload: LocalAgentSendMessagePayload
    ): Promise<LocalAgentSendMessageResponse> => {
      return ipcRenderer.invoke('agent:send-message', bindingId, payload)
    },
    getWorkspace: (
      runId: string,
      selectors?: { retrieval_session_id?: string; prompt_manifest_id?: string }
    ): Promise<AgentRunWorkspace> => {
      return ipcRenderer.invoke('agent:get-workspace', runId, selectors)
    },
    listConnections: (): Promise<{ items: LocalAgentConnection[] }> => {
      return ipcRenderer.invoke('agent:list-connections')
    },
  },
  task: {
    get: (taskId: string): Promise<Task> => {
      return ipcRenderer.invoke('task:get', taskId)
    },
    cancel: (taskId: string): Promise<void> => {
      return ipcRenderer.invoke('task:cancel', taskId)
    },
    list: (filters?: { status?: TaskStatus }): Promise<{ items: Task[] }> => {
      return ipcRenderer.invoke('task:list', filters)
    },
  },
  system: {
    showWindow: (route?: string): Promise<void> => {
      return ipcRenderer.invoke('system:show-window', route)
    },
    hideWindow: (): Promise<void> => {
      return ipcRenderer.invoke('system:hide-window')
    },
    getStartupEnabled: (): Promise<boolean> => {
      return ipcRenderer.invoke('system:get-startup-enabled')
    },
    setStartupEnabled: (enabled: boolean): Promise<boolean> => {
      return ipcRenderer.invoke('system:set-startup-enabled', enabled)
    },
    notify: (options: SystemNotificationOptions): Promise<void> => {
      return ipcRenderer.invoke('system:notify', options)
    },
    getPendingRoute: (): Promise<DesktopRoutePayload | null> => {
      return ipcRenderer.invoke('system:get-pending-route')
    },
  },
  window: {
    openRun: (runId: string): Promise<DesktopWindowSummary> => {
      return ipcRenderer.invoke('window:open-run', runId)
    },
    list: (): Promise<{ items: DesktopWindowSummary[] }> => {
      return ipcRenderer.invoke('window:list')
    },
    getState: (): Promise<{ profileId: string; items: DesktopWindowSummary[] }> => {
      return ipcRenderer.invoke('window:get-state')
    },
  },
  profile: {
    list: (): Promise<{ activeProfileId: string; profiles: DesktopProfile[] }> => {
      return ipcRenderer.invoke('profile:list')
    },
    save: (profile: DesktopProfileSaveInput): Promise<DesktopProfile> => {
      return ipcRenderer.invoke('profile:save', profile)
    },
    switch: (profileId: string): Promise<DesktopProfile> => {
      return ipcRenderer.invoke('profile:switch', profileId)
    },
  },
  localModel: {
    getSettings: (): Promise<DesktopLocalModelSettings> => {
      return ipcRenderer.invoke('local-model:get-settings')
    },
    setSettings: (
      settings: Partial<DesktopLocalModelSettings>
    ): Promise<DesktopLocalModelSettings> => {
      return ipcRenderer.invoke('local-model:set-settings', settings)
    },
    testConnection: () => {
      return ipcRenderer.invoke('local-model:test-connection')
    },
  },
  offline: {
    runSimpleTask: (payload: {
      prompt: string
      useLocalModel?: boolean
    }): Promise<DesktopOfflineTask> => {
      return ipcRenderer.invoke('offline:run-simple-task', payload)
    },
    listTasks: (): Promise<{ items: DesktopOfflineTask[] }> => {
      return ipcRenderer.invoke('offline:list-tasks')
    },
    promoteResultToPendingAgentTask: async (offlineTaskId: string): Promise<{ taskId: string; operationId: number | null }> => {
      const result = await ipcRenderer.invoke('offline:promote-result-to-pending-agent-task', offlineTaskId)
      return { taskId: result.task.id, operationId: result.operationId ?? null }
    },
  },
  offlineAgent: {
    run: (input) => ipcRenderer.invoke('offline-agent:run', input),
    listRuns: (limit) => ipcRenderer.invoke('offline-agent:list-runs', limit),
    getRun: (runId) => ipcRenderer.invoke('offline-agent:get-run', runId),
    cancel: (runId) => ipcRenderer.invoke('offline-agent:cancel', runId),
    resume: (runId) => ipcRenderer.invoke('offline-agent:resume', runId),
    decideApproval: (approvalId, approved) => {
      return ipcRenderer.invoke('offline-agent:decide-approval', approvalId, approved)
    },
  },
  sync: {
    getStatus: (): Promise<DesktopSyncRuntimeStatus> => {
      return ipcRenderer.invoke('sync:get-status')
    },
    getConflicts: (): Promise<DesktopSyncConflictSummary> => {
      return ipcRenderer.invoke('sync:get-conflicts')
    },
    runNow: (): Promise<DesktopSyncRuntimeStatus> => {
      return ipcRenderer.invoke('sync:run-now')
    },
    onStatus: (callback: (status: DesktopSyncRuntimeStatus) => void): (() => void) => {
      const listener = (_event: Electron.IpcRendererEvent, status: DesktopSyncRuntimeStatus) => {
        callback(status)
      }
      ipcRenderer.on('sync:status', listener)
      return () => {
        ipcRenderer.removeListener('sync:status', listener)
      }
    },
  },
  updates: {
    getStatus: (): Promise<DesktopUpdateStatus> => {
      return ipcRenderer.invoke('updates:get-status')
    },
    check: (): Promise<DesktopUpdateStatus> => {
      return ipcRenderer.invoke('updates:check')
    },
    download: (): Promise<DesktopUpdateStatus> => {
      return ipcRenderer.invoke('updates:download')
    },
    install: (): Promise<void> => {
      return ipcRenderer.invoke('updates:install')
    },
  },
  feedback: {
    submit: (payload: DesktopFeedbackPayload): Promise<DesktopFeedbackResponse> => {
      return ipcRenderer.invoke('feedback:submit', payload)
    },
    recordMetric: (
      payload: DesktopMetricSamplePayload
    ): Promise<DesktopMetricSampleResponse> => {
      return ipcRenderer.invoke('feedback:record-metric', payload)
    },
    getMetricsSummary: (): Promise<DesktopMetricsSummary> => {
      return ipcRenderer.invoke('feedback:get-metrics-summary')
    },
  },
  file: {
    selectWorkspaceRoot: (): Promise<DesktopFileWatchState | null> => {
      return ipcRenderer.invoke('file:select-workspace-root')
    },
    selectAuthorizedWorkspaceRoot: (): Promise<DesktopWorkspaceAuthorization | null> => {
      return ipcRenderer.invoke('file:select-authorized-workspace-root')
    },
    getWorkspaceRoot: (): Promise<DesktopFileWatchState> => {
      return ipcRenderer.invoke('file:get-workspace-root')
    },
    setWorkspaceRoot: (rootPath: string | null): Promise<DesktopFileWatchState> => {
      return ipcRenderer.invoke('file:set-workspace-root', rootPath)
    },
    startWatch: (): Promise<DesktopFileWatchState> => {
      return ipcRenderer.invoke('file:start-watch')
    },
    stopWatch: (): Promise<DesktopFileWatchState> => {
      return ipcRenderer.invoke('file:stop-watch')
    },
    listFiles: (options?: {
      path?: string
      maxDepth?: number
      maxEntries?: number
    }): Promise<DesktopFileListResult> => {
      return ipcRenderer.invoke('file:list-files', options)
    },
    scanProjectKnowledge: (
      options?: DesktopProjectKnowledgeScanOptions
    ): Promise<DesktopProjectKnowledgeSnapshot> => {
      return ipcRenderer.invoke('file:scan-project-knowledge', options)
    },
    readFile: (path: string): Promise<DesktopFileReadResult> => {
      return ipcRenderer.invoke('file:read-file', path)
    },
    writeFile: (path: string, content: string): Promise<DesktopFileWriteResult> => {
      return ipcRenderer.invoke('file:write-file', path, content)
    },
    onChange: (callback: (event: DesktopFileChangeEvent) => void): (() => void) => {
      const listener = (_event: Electron.IpcRendererEvent, payload: DesktopFileChangeEvent) => {
        callback(payload)
      }
      ipcRenderer.on('file:change', listener)
      return () => {
        ipcRenderer.removeListener('file:change', listener)
      }
    },
  },
  changeReview: {
    getStatus: (): Promise<DesktopChangeReviewStatus> => {
      return ipcRenderer.invoke('change-review:get-status')
    },
    getDiff: (path: string): Promise<DesktopChangeDiff> => {
      return ipcRenderer.invoke('change-review:get-diff', path)
    },
    mutate: (input: DesktopChangeMutationInput): Promise<DesktopChangeMutationResult> => {
      return ipcRenderer.invoke('change-review:mutate', input)
    },
  },
  events: {
    onMessageStream: (callback: (event: AgentEvent) => void): (() => void) => {
      const listener = (_event: Electron.IpcRendererEvent, data: AgentEvent) => {
        callback(data)
      }
      ipcRenderer.on('agent:message-stream', listener)
      return () => {
        ipcRenderer.removeListener('agent:message-stream', listener)
      }
    },
    onConnectionStatus: (callback: (status: SseConnectionStatus) => void): (() => void) => {
      const listener = (_event: Electron.IpcRendererEvent, status: SseConnectionStatus) => {
        callback(status)
      }
      ipcRenderer.on('agent:connection-status', listener)
      return () => {
        ipcRenderer.removeListener('agent:connection-status', listener)
      }
    },
    onTaskStatusChange: (callback: (task: Task) => void): (() => void) => {
      const listener = (_event: Electron.IpcRendererEvent, task: Task) => {
        callback(task)
      }
      ipcRenderer.on('task:status-change', listener)
      return () => {
        ipcRenderer.removeListener('task:status-change', listener)
      }
    },
    onOpenRoute: (callback: (payload: DesktopRoutePayload) => void): (() => void) => {
      const listener = (_event: Electron.IpcRendererEvent, payload: DesktopRoutePayload) => {
        callback(payload)
      }
      ipcRenderer.on('system:open-route', listener)
      return () => {
        ipcRenderer.removeListener('system:open-route', listener)
      }
    },
    onUpdateStatus: (callback: (status: DesktopUpdateStatus) => void): (() => void) => {
      const listener = (_event: Electron.IpcRendererEvent, status: DesktopUpdateStatus) => {
        callback(status)
      }
      ipcRenderer.on('updates:status', listener)
      return () => {
        ipcRenderer.removeListener('updates:status', listener)
      }
    },
    onProfileChanged: (callback: (profile: DesktopProfile) => void): (() => void) => {
      const listener = (_event: Electron.IpcRendererEvent, profile: DesktopProfile) => {
        callback(profile)
      }
      ipcRenderer.on('profile:changed', listener)
      return () => {
        ipcRenderer.removeListener('profile:changed', listener)
      }
    },
  },
}

export function selectDesktopApiForUrl(rawUrl: string): DesktopApi | Pick<DesktopApi, 'localRuntime'> {
  try {
    const url = new URL(rawUrl)
    if (url.protocol === 'harness-app:' && url.hostname === 'renderer') {
      return { localRuntime: desktopApi.localRuntime }
    }
  } catch {
    // Development/test renderers retain the established bridge.
  }
  return desktopApi
}

const preloadLocation = (globalThis as { location?: { href?: string } }).location?.href || ''
contextBridge.exposeInMainWorld('desktopApi', selectDesktopApiForUrl(preloadLocation))
