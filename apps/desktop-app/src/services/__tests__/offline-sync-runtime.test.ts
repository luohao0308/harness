import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import * as fs from 'node:fs'
import * as os from 'node:os'
import * as path from 'node:path'
import { SQLiteOfflineQueue } from '../../stores/sqlite-offline-queue'
import { SQLiteTaskStore } from '../../stores/sqlite-task-store'
import { SQLiteOfflineAgentStore } from '../../stores/sqlite-offline-agent-store'
import { OfflineAgentRuntime } from '../offline-agent-runtime'
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

  test('coalesces concurrent runNow calls into one in-flight sync', async () => {
    const monitor = new FakeNetworkMonitor(true)
    let resolveSync!: () => void
    const sync = vi.fn(
      () => new Promise<void>(resolve => {
        resolveSync = resolve
      }),
    )
    const { DesktopOfflineSyncRuntime } = await import('../offline-sync-runtime')

    const runtime = new DesktopOfflineSyncRuntime({
      getActiveProfile: () => profile('default', '/tmp/default'),
      networkMonitor: monitor,
      createResources: (desktopProfile) => makeResources(desktopProfile, sync),
    })

    const first = runtime.runNow()
    const second = runtime.runNow()

    expect(second).toBe(first)
    expect(sync).toHaveBeenCalledTimes(1)
    resolveSync()
    await expect(first).resolves.toMatchObject({ state: 'idle' })

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

  test('registers the complete offline Agent IPC surface and executes an approved write', async () => {
    const monitor = new FakeNetworkMonitor(false)
    const workspaceRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'offline-sync-ipc-'))
    const { DesktopOfflineSyncRuntime } = await import('../offline-sync-runtime')
    const runtime = new DesktopOfflineSyncRuntime({
      getActiveProfile: () => profile('default', '/tmp/default'),
      networkMonitor: monitor,
      createResources: (desktopProfile) => makeResources(
        desktopProfile,
        vi.fn(async () => undefined),
        true,
        workspaceRoot,
      ),
    })
    runtime.start()

    expect([...ipcHandlers.keys()]).toEqual(expect.arrayContaining([
      'offline-agent:list-runs',
      'offline-agent:get-run',
      'offline-agent:run',
      'offline-agent:cancel',
      'offline-agent:resume',
      'offline-agent:decide-approval',
    ]))
    const waiting = await ipcHandlers.get('offline-agent:run')?.({}, {
      prompt: 'write offline evidence',
      toolRequest: {
        name: 'workspace.write_text',
        input: { path: 'report.txt', content: 'approved evidence' },
      },
    })
    const snapshot = ipcHandlers.get('offline-agent:get-run')?.({}, waiting.id)
    const run = await ipcHandlers.get('offline-agent:decide-approval')?.(
      {},
      waiting.pendingApprovalId,
      true,
    )
    const listed = ipcHandlers.get('offline-agent:list-runs')?.({}, 20)

    expect(waiting).toMatchObject({ status: 'WAITING_APPROVAL' })
    expect(snapshot.approvals[0]).toMatchObject({
      status: 'PENDING',
      target: { path: 'report.txt', exists: false },
    })
    expect(run).toMatchObject({ status: 'COMPLETED', modelSource: 'deterministic-local' })
    expect(fs.readFileSync(path.join(workspaceRoot, 'report.txt'), 'utf8')).toBe('approved evidence')
    expect(listed.items).toEqual([expect.objectContaining({ id: run.id })])
    expect(runtime.getStatus().pendingOperations).toBe(1)
    runtime.close()
    fs.rmSync(workspaceRoot, { recursive: true, force: true })
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

function makeResources(
  desktopProfile: DesktopProfile,
  sync: ReturnType<typeof vi.fn>,
  withOfflineAgent = false,
  workspaceRoot = '/tmp',
) {
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
  const resources: Record<string, unknown> = {
    profile: desktopProfile,
    dbPath: ':memory:',
    taskStore,
    offlineQueue,
    syncMetadata,
    syncService: { sync },
  }
  if (withOfflineAgent) {
    const offlineAgentStore = new SQLiteOfflineAgentStore(':memory:')
    offlineAgentStore.initialize()
    resources.offlineAgentStore = offlineAgentStore
    resources.offlineAgentRuntime = new OfflineAgentRuntime({
      store: offlineAgentStore,
      getWorkspaceRoot: () => workspaceRoot,
      getLocalModelSettings: () => ({
        enabled: false,
        provider: 'ollama',
        baseUrl: 'http://127.0.0.1:11434',
        model: 'llama3.1',
        updatedAt: '2026-08-19T00:00:00.000Z',
      }),
      onTerminalSnapshot: (snapshot) => {
        offlineQueue.enqueue({
          operation_type: 'CREATE',
          entity_type: 'offline_agent_run',
          entity_id: snapshot.run.id,
          payload_json: JSON.stringify(snapshot),
          client_timestamp: snapshot.run.updatedAt,
        })
      },
    })
  }
  return resources as any
}
