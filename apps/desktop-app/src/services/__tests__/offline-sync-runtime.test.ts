import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { SQLiteOfflineQueue } from '../../stores/sqlite-offline-queue'
import { SQLiteTaskStore } from '../../stores/sqlite-task-store'
import type { NetworkMonitor, NetworkStatus } from '../network-monitor'
import type { DesktopProfile, OfflineTask } from '../phase6-store'

class FakeNetworkMonitor implements NetworkMonitor {
  private callback: (() => void) | null = null
  stopped = false

  constructor(public online = true) {}

  getStatus(): NetworkStatus {
    return { online: this.online, lastChangeTimestamp: '2026-07-12T00:00:00.000Z' }
  }

  isOnline(): boolean {
    return this.online
  }

  start(onOnline: () => void): void {
    this.callback = onOnline
  }

  stop(): void {
    this.stopped = true
  }

  reconnect(): void {
    this.online = true
    this.callback?.()
  }
}

describe('DesktopOfflineSyncRuntime', () => {
  let ipcHandlers: Map<string, (...args: any[]) => any>
  let sendStatus: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.resetModules()
    vi.useFakeTimers()
    ipcHandlers = new Map()
    sendStatus = vi.fn()
    vi.doMock('electron', () => ({
      app: { on: vi.fn() },
      BrowserWindow: {
        getAllWindows: vi.fn(() => [{ webContents: { send: sendStatus } }]),
      },
      ipcMain: {
        handle: vi.fn((channel: string, handler: (...args: any[]) => any) => {
          ipcHandlers.set(channel, handler)
        }),
      },
      net: {
        isOnline: vi.fn(() => true),
      },
    }))
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  test('starts with the active profile data path and runs an initial sync', async () => {
    const monitor = new FakeNetworkMonitor(true)
    const sync = vi.fn(async () => undefined)
    const { DesktopOfflineSyncRuntime } = await import('../offline-sync-runtime')

    const runtime = new DesktopOfflineSyncRuntime({
      getActiveProfile: () => profile('customer-a', '/tmp/customer-a'),
      networkMonitor: monitor,
      createResources: (desktopProfile) => makeResources(desktopProfile, sync),
    })

    runtime.start()
    await vi.runOnlyPendingTimersAsync()

    expect(sync).toHaveBeenCalledTimes(1)
    expect(runtime.getStatus()).toMatchObject({
      profileId: 'customer-a',
      dataPath: '/tmp/customer-a',
      state: 'idle',
    })
    expect(ipcHandlers.has('sync:get-status')).toBe(true)
    expect(ipcHandlers.has('sync:get-conflicts')).toBe(true)

    runtime.close()
  })

  test('auto-syncs on reconnect and schedules bounded retry backoff after failures', async () => {
    const monitor = new FakeNetworkMonitor(false)
    const sync = vi
      .fn()
      .mockRejectedValueOnce(new Error('backend unavailable'))
      .mockResolvedValueOnce(undefined)
    const { DesktopOfflineSyncRuntime } = await import('../offline-sync-runtime')

    const runtime = new DesktopOfflineSyncRuntime({
      getActiveProfile: () => profile('default', '/tmp/default'),
      networkMonitor: monitor,
      createResources: (desktopProfile) => makeResources(desktopProfile, sync),
      initialBackoffMs: 100,
      maxBackoffMs: 100,
      maxRetryAttempts: 1,
    })

    runtime.start()
    expect(sync).not.toHaveBeenCalled()

    monitor.reconnect()
    await vi.runOnlyPendingTimersAsync()
    await vi.advanceTimersByTimeAsync(100)

    expect(sync).toHaveBeenCalledTimes(2)
    expect(runtime.getStatus()).toMatchObject({
      state: 'idle',
      retryAttempt: 0,
      lastError: null,
    })

    runtime.close()
  })

  test('promotes a completed offline result into a pending SQLite task operation', async () => {
    const monitor = new FakeNetworkMonitor(false)
    const offlineTask: OfflineTask = {
      id: 'offline-1',
      prompt: '整理离线发布检查',
      result: '检查完成',
      modelSource: 'deterministic-local',
      status: 'completed',
      createdAt: '2026-07-12T00:00:00.000Z',
    }
    const { DesktopOfflineSyncRuntime } = await import('../offline-sync-runtime')

    const runtime = new DesktopOfflineSyncRuntime({
      getActiveProfile: () => profile('default', '/tmp/default'),
      listOfflineTasks: () => [offlineTask],
      networkMonitor: monitor,
      createResources: (desktopProfile) => makeResources(desktopProfile, vi.fn(async () => undefined)),
    })

    runtime.start()
    const result = runtime.promoteOfflineResultToPendingAgentTask('offline-1')

    expect(result.task).toMatchObject({
      title: '整理离线发布检查',
      has_local_changes: true,
    })
    expect(runtime.getStatus()).toMatchObject({
      pendingOperations: 1,
    })

    runtime.close()
  })

  test('closes network and SQLite resources on shutdown', async () => {
    const monitor = new FakeNetworkMonitor(true)
    const sync = vi.fn(async () => undefined)
    const { DesktopOfflineSyncRuntime } = await import('../offline-sync-runtime')
    const runtime = new DesktopOfflineSyncRuntime({
      getActiveProfile: () => profile('default', '/tmp/default'),
      networkMonitor: monitor,
      createResources: (desktopProfile) => makeResources(desktopProfile, sync),
    })

    runtime.start()
    runtime.close()

    expect(monitor.stopped).toBe(true)
    expect(runtime.getStatus().state).toBe('closed')
  })
})

function profile(id: string, dataPath: string): DesktopProfile {
  return {
    id,
    label: id,
    apiBaseUrl: 'http://localhost:8000',
    dataPath,
    hasCredential: false,
    credentialStorage: 'none',
    createdAt: '2026-07-12T00:00:00.000Z',
    updatedAt: '2026-07-12T00:00:00.000Z',
  }
}

function makeResources(desktopProfile: DesktopProfile, sync: ReturnType<typeof vi.fn>) {
  const taskStore = new SQLiteTaskStore(':memory:')
  const offlineQueue = new SQLiteOfflineQueue(':memory:')
  taskStore.initialize()
  offlineQueue.initialize()
  const metadata = new Map<string, string>()
  const syncMetadata = {
    initialize: vi.fn(),
    getLastSyncTimestamp: vi.fn(() => metadata.get('last_sync_timestamp') ?? null),
    setLastSyncTimestamp: vi.fn((timestamp: string) => {
      metadata.set('last_sync_timestamp', timestamp)
    }),
    getMetadata: vi.fn((key: string) => metadata.get(key) ?? null),
    setMetadata: vi.fn((key: string, value: string) => {
      metadata.set(key, value)
    }),
    deleteMetadata: vi.fn((key: string) => {
      metadata.delete(key)
    }),
    close: vi.fn(),
  }
  return {
    profile: desktopProfile,
    dbPath: ':memory:',
    taskStore,
    offlineQueue,
    syncMetadata,
    syncService: { sync },
  } as any
}
