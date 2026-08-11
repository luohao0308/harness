import { app, BrowserWindow, ipcMain } from 'electron'
import Database from 'better-sqlite3'
import * as fs from 'fs'
import * as path from 'path'
import type { NetworkMonitor, NetworkStatus } from './network-monitor'
import { getActiveProfile, listOfflineTasks, type DesktopProfile, type OfflineTask } from './phase6-store'
import { SQLiteSyncMetadata } from './sqlite-sync-metadata'
import {
  LAST_SYNC_CONFLICTS_METADATA_KEY,
  SQLiteSyncService,
} from './sqlite-sync-service'
import type { SyncPushConflict } from './sync-service'
import { apiRequest } from '../shared/api-client'
import { SQLiteOfflineQueue } from '../stores/sqlite-offline-queue'
import { SQLiteTaskStore } from '../stores/sqlite-task-store'
import type { OfflineQueue } from '../stores/offline-queue'
import type { TaskStore } from '../stores/task-store'
import type { TaskWithSyncMetadata } from '../stores/types'

export type DesktopSyncRuntimeState =
  | 'idle'
  | 'scheduled'
  | 'syncing'
  | 'error'
  | 'closed'

export type DesktopSyncRuntimeStatus = {
  state: DesktopSyncRuntimeState
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

export type DesktopSyncConflictSummary = {
  tasks: TaskWithSyncMetadata[]
  serverConflicts: SyncPushConflict[]
}

type RuntimeResources = {
  profile: DesktopProfile
  dbPath: string
  taskStore: TaskStore
  offlineQueue: OfflineQueue
  syncMetadata: SQLiteSyncMetadata
  syncService: SQLiteSyncService
}

export type DesktopOfflineSyncRuntimeOptions = {
  getActiveProfile?: () => DesktopProfile
  listOfflineTasks?: () => OfflineTask[]
  networkMonitor?: NetworkMonitor
  createResources?: (profile: DesktopProfile) => RuntimeResources
  initialBackoffMs?: number
  maxBackoffMs?: number
  maxRetryAttempts?: number
}

const DEFAULT_INITIAL_BACKOFF_MS = 1_000
const DEFAULT_MAX_BACKOFF_MS = 30_000
const DEFAULT_MAX_RETRY_ATTEMPTS = 5

export class DesktopOfflineSyncRuntime {
  private resources: RuntimeResources | null = null
  private timer: ReturnType<typeof setTimeout> | null = null
  private state: DesktopSyncRuntimeState = 'idle'
  private lastStartedAt: string | null = null
  private lastCompletedAt: string | null = null
  private lastError: string | null = null
  private nextRetryAt: string | null = null
  private retryAttempt = 0
  private registeredIpc = false
  private closed = false

  private getActiveProfile: () => DesktopProfile
  private listOfflineTasks: () => OfflineTask[]
  private networkMonitor: NetworkMonitor
  private createResources: (profile: DesktopProfile) => RuntimeResources
  private initialBackoffMs: number
  private maxBackoffMs: number
  private maxRetryAttempts: number

  constructor(options: DesktopOfflineSyncRuntimeOptions = {}) {
    this.getActiveProfile = options.getActiveProfile ?? getActiveProfile
    this.listOfflineTasks = options.listOfflineTasks ?? listOfflineTasks
    this.networkMonitor = options.networkMonitor ?? new ElectronPollingNetworkMonitor()
    this.createResources = options.createResources ?? createRuntimeResources
    this.initialBackoffMs = options.initialBackoffMs ?? DEFAULT_INITIAL_BACKOFF_MS
    this.maxBackoffMs = options.maxBackoffMs ?? DEFAULT_MAX_BACKOFF_MS
    this.maxRetryAttempts = options.maxRetryAttempts ?? DEFAULT_MAX_RETRY_ATTEMPTS
  }

  start(): void {
    if (this.closed) return
    this.registerIpcHandlers()
    this.networkMonitor.start(() => {
      this.retryAttempt = 0
      this.scheduleSync(0)
    })
    if (!this.tryEnsureResourcesForActiveProfile()) {
      this.publishStatus()
      return
    }

    if (this.networkMonitor.isOnline()) {
      this.scheduleSync(0)
    }
  }

  registerIpcHandlers(): void {
    if (this.registeredIpc) return
    this.registeredIpc = true

    ipcMain.handle('sync:get-status', () => this.getStatus())
    ipcMain.handle('sync:get-conflicts', () => this.getConflicts())
    ipcMain.handle('sync:run-now', async () => this.runNow())
    ipcMain.handle(
      'offline:promote-result-to-pending-agent-task',
      (_event, offlineTaskId: string) => this.promoteOfflineResultToPendingAgentTask(offlineTaskId)
    )
  }

  async runNow(): Promise<DesktopSyncRuntimeStatus> {
    if (this.closed) return this.getStatus()
    if (!this.networkMonitor.isOnline()) {
      this.lastError = 'network offline'
      this.state = 'error'
      this.publishStatus()
      return this.getStatus()
    }

    this.clearTimer()
    if (!this.tryEnsureResourcesForActiveProfile()) {
      this.publishStatus()
      return this.getStatus()
    }
    const resources = this.requireResources()

    this.state = 'syncing'
    this.lastStartedAt = new Date().toISOString()
    this.nextRetryAt = null
    this.publishStatus()

    try {
      await resources.syncService.sync()
      resources.offlineQueue.cleanup(14)
      this.retryAttempt = 0
      this.lastError = null
      this.lastCompletedAt = new Date().toISOString()
      this.state = 'idle'
    } catch (error) {
      this.lastError = error instanceof Error ? error.message : String(error)
      this.state = 'error'
      this.scheduleRetry()
    }

    this.publishStatus()
    return this.getStatus()
  }

  getStatus(): DesktopSyncRuntimeStatus {
    this.tryEnsureResourcesForActiveProfile()
    const network = this.networkMonitor.getStatus()
    const resources = this.resources

    return {
      state: this.closed ? 'closed' : this.state,
      profileId: resources?.profile.id ?? null,
      dataPath: resources?.profile.dataPath ?? null,
      online: network.online,
      lastChangeTimestamp: network.lastChangeTimestamp,
      lastStartedAt: this.lastStartedAt,
      lastCompletedAt: this.lastCompletedAt,
      lastError: this.lastError,
      nextRetryAt: this.nextRetryAt,
      retryAttempt: this.retryAttempt,
      pendingOperations: resources?.offlineQueue.getPending().length ?? 0,
      retryableOperations: resources?.offlineQueue.getRetryable(5).length ?? 0,
      conflictCount: this.getConflictCount(resources),
    }
  }

  getConflicts(): DesktopSyncConflictSummary {
    this.tryEnsureResourcesForActiveProfile()
    const resources = this.requireResources()
    return {
      tasks: resources.taskStore.query({ limit: 100 }).filter(task => task.conflict_detected),
      serverConflicts: this.getServerConflicts(resources),
    }
  }

  promoteOfflineResultToPendingAgentTask(offlineTaskId: string): {
    task: TaskWithSyncMetadata
    operationId: number | null
  } {
    this.tryEnsureResourcesForActiveProfile()
    const resources = this.requireResources()
    const offlineTask = this.listOfflineTasks().find(item => item.id === offlineTaskId)
    if (!offlineTask) {
      throw new Error('offline task not found')
    }
    if (offlineTask.status !== 'completed') {
      throw new Error('only completed offline tasks can be promoted')
    }

    const task = resources.taskStore.create({
      organization_id: null,
      agent_id: 'default',
      created_by: null,
      title: offlineTask.prompt.slice(0, 120) || 'Desktop offline task',
      goal: [
        offlineTask.prompt,
        '',
        'Desktop offline result:',
        offlineTask.result,
      ].join('\n'),
      status: 'pending',
      model_provider: 'desktop-offline',
      model_name: offlineTask.modelSource,
      max_runtime_seconds: 3600,
      max_subagents: 0,
      enable_sandbox: false,
      enable_network: true,
      capability_snapshot_json: {
        source: 'desktop-offline-simple-task',
        offline_task_id: offlineTask.id,
      },
      completed_at: null,
    })

    const operation = resources.offlineQueue.enqueue({
      operation_type: 'CREATE',
      entity_type: 'task',
      entity_id: task.id,
      payload_json: JSON.stringify({
        title: task.title,
        goal: task.goal,
        status: task.status,
        model_provider: task.model_provider,
        model_name: task.model_name,
      }),
      client_timestamp: new Date().toISOString(),
    })

    this.publishStatus()
    if (this.networkMonitor.isOnline()) {
      this.scheduleSync(0)
    }

    return { task, operationId: operation.id ?? null }
  }

  close(): void {
    this.closed = true
    this.clearTimer()
    this.networkMonitor.stop()
    this.closeResources()
    this.state = 'closed'
  }

  private scheduleRetry(): void {
    if (this.retryAttempt >= this.maxRetryAttempts) {
      this.nextRetryAt = null
      return
    }

    this.retryAttempt += 1
    const delayMs = Math.min(
      this.maxBackoffMs,
      this.initialBackoffMs * (2 ** (this.retryAttempt - 1))
    )
    this.scheduleSync(delayMs)
  }

  private scheduleSync(delayMs: number): void {
    if (this.closed) return
    this.clearTimer()
    this.state = delayMs > 0 ? 'scheduled' : this.state === 'error' ? 'error' : 'scheduled'
    this.nextRetryAt = new Date(Date.now() + delayMs).toISOString()
    this.timer = setTimeout(() => {
      void this.runNow()
    }, delayMs)
    this.publishStatus()
  }

  private clearTimer(): void {
    if (this.timer) {
      clearTimeout(this.timer)
      this.timer = null
    }
  }

  private ensureResourcesForActiveProfile(): void {
    if (this.closed) return
    const profile = this.getActiveProfile()
    if (this.resources?.profile.id === profile.id && this.resources.profile.dataPath === profile.dataPath) {
      return
    }

    this.closeResources()
    this.resources = this.createResources(profile)
  }

  private tryEnsureResourcesForActiveProfile(): boolean {
    try {
      this.ensureResourcesForActiveProfile()
      this.lastError = this.resources ? this.lastError : 'desktop sync runtime is not initialized'
      return Boolean(this.resources)
    } catch (error) {
      this.lastError = error instanceof Error ? error.message : String(error)
      this.state = 'error'
      return false
    }
  }

  private closeResources(): void {
    if (!this.resources) return
    this.resources.offlineQueue.close()
    this.resources.taskStore.close()
    this.resources.syncMetadata.close()
    this.resources = null
  }

  private requireResources(): RuntimeResources {
    if (!this.resources) {
      throw new Error('desktop sync runtime is not initialized')
    }
    return this.resources
  }

  private getConflictCount(resources: RuntimeResources | null): number {
    if (!resources) return 0
    const taskConflicts = resources.taskStore.query({ limit: 100 }).filter(task => task.conflict_detected).length
    return taskConflicts + this.getServerConflicts(resources).length
  }

  private getServerConflicts(resources: RuntimeResources): SyncPushConflict[] {
    const raw = resources.syncMetadata.getMetadata(LAST_SYNC_CONFLICTS_METADATA_KEY)
    if (!raw) return []
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed as SyncPushConflict[] : []
    } catch {
      return []
    }
  }

  private publishStatus(): void {
    const status = this.getStatus()
    const getAllWindows = (BrowserWindow as typeof BrowserWindow & {
      getAllWindows?: () => BrowserWindow[]
    }).getAllWindows
    if (typeof getAllWindows !== 'function') return
    getAllWindows().forEach((window) => {
      window.webContents.send('sync:status', status)
    })
  }
}

export function registerOfflineSyncRuntimeHandlers(runtime: DesktopOfflineSyncRuntime): void {
  runtime.start()
}

export function createRuntimeResources(profile: DesktopProfile): RuntimeResources {
  fs.mkdirSync(profile.dataPath, { recursive: true })
  const dbPath = path.join(profile.dataPath, 'offline-sync.sqlite')
  const taskStore = new SQLiteTaskStore(dbPath)
  const offlineQueue = new SQLiteOfflineQueue(dbPath)
  const metadataDb = new Database(dbPath)
  const syncMetadata = new SQLiteSyncMetadata(metadataDb)

  taskStore.initialize()
  offlineQueue.initialize()
  syncMetadata.initialize()

  return {
    profile,
    dbPath,
    taskStore,
    offlineQueue,
    syncMetadata,
    syncService: new SQLiteSyncService('', offlineQueue, taskStore, syncMetadata, {
      requestJson: apiRequest,
    }),
  }
}

class ElectronPollingNetworkMonitor implements NetworkMonitor {
  private interval: ReturnType<typeof setInterval> | null = null
  private lastOnline = this.readOnline()
  private lastChangeTimestamp = new Date().toISOString()

  getStatus(): NetworkStatus {
    return {
      online: this.isOnline(),
      lastChangeTimestamp: this.lastChangeTimestamp,
    }
  }

  isOnline(): boolean {
    return this.readOnline()
  }

  start(onOnline: () => void): void {
    if (this.interval) return
    this.interval = setInterval(() => {
      const online = this.readOnline()
      if (online !== this.lastOnline) {
        this.lastOnline = online
        this.lastChangeTimestamp = new Date().toISOString()
        if (online) onOnline()
      }
    }, 5_000)
  }

  stop(): void {
    if (!this.interval) return
    clearInterval(this.interval)
    this.interval = null
  }

  private readOnline(): boolean {
    let candidate: { isOnline?: () => boolean } | undefined
    try {
      candidate = (require('electron') as { net?: { isOnline?: () => boolean } }).net
    } catch {
      candidate = undefined
    }
    if (candidate && typeof candidate.isOnline === 'function') {
      return candidate.isOnline()
    }
    return true
  }
}

let offlineSyncRuntime: DesktopOfflineSyncRuntime | null = null

export function startDesktopOfflineSyncRuntime(): DesktopOfflineSyncRuntime {
  if (!offlineSyncRuntime) {
    offlineSyncRuntime = new DesktopOfflineSyncRuntime()
    offlineSyncRuntime.start()
    app.on('before-quit', () => {
      offlineSyncRuntime?.close()
      offlineSyncRuntime = null
    })
  }
  return offlineSyncRuntime
}

export function stopDesktopOfflineSyncRuntime(): void {
  offlineSyncRuntime?.close()
  offlineSyncRuntime = null
}
