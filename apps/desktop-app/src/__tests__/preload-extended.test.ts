import * as fs from 'node:fs'
import * as path from 'node:path'
import ts from 'typescript'
import { describe, test, expect, vi, beforeEach } from 'vitest'

// Mock electron modules
const mockIpcRenderer = {
  invoke: vi.fn(),
  sendSync: vi.fn(),
  on: vi.fn(),
  removeListener: vi.fn(),
}

const mockContextBridge = {
  exposeInMainWorld: vi.fn(),
}

vi.mock('electron', () => ({
  ipcRenderer: mockIpcRenderer,
  contextBridge: mockContextBridge,
}))

describe('Preload Script - Extended Coverage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  test('exposes the unified local runtime model-key contract', async () => {
    vi.resetModules()
    await import('../preload')
    const api = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    const status = { state: 'configured', secret_storage: 'persistent' }
    mockIpcRenderer.invoke.mockResolvedValue({ ok: true, value: status })

    await expect(api.localRuntime.setModelApiKey('real-api-key')).resolves.toBe(status)

    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('local-runtime:set-model-api-key', 'real-api-key')
  })

  test('exposes local runtime session renewal without returning credentials', async () => {
    vi.resetModules()
    await import('../preload')
    const api = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    mockIpcRenderer.invoke.mockResolvedValue({ ok: true, value: undefined })

    await expect(api.localRuntime.renewSession()).resolves.toBeUndefined()

    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('local-runtime:renew-session')
  })

  test('exposes model configuration and unsaved discovery IPC', async () => {
    vi.resetModules()
    await import('../preload')
    const api = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    const configuration = {
      baseUrl: 'https://provider.example/v1',
      model: 'provider-model',
      apiKey: 'unsaved-secret',
    }
    const discovery = { models: ['provider-model'], durationMs: 12, latencyMs: 12 }
    mockIpcRenderer.invoke
      .mockResolvedValueOnce({ ok: true, value: { state: 'configured' } })
      .mockResolvedValueOnce({ ok: true, value: discovery })

    await api.localRuntime.saveModelConfiguration(configuration)
    await expect(api.localRuntime.discoverModels({
      baseUrl: configuration.baseUrl,
      apiKey: configuration.apiKey,
    })).resolves.toBe(discovery)

    expect(mockIpcRenderer.invoke).toHaveBeenNthCalledWith(
      1,
      'local-runtime:save-model-configuration',
      configuration,
    )
    expect(mockIpcRenderer.invoke).toHaveBeenNthCalledWith(
      2,
      'local-runtime:discover-models',
      { baseUrl: configuration.baseUrl, apiKey: configuration.apiKey },
    )
  })

  test('restores structured local runtime failures without a rejected main-process handler', async () => {
    vi.resetModules()
    await import('../preload')
    const api = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    mockIpcRenderer.invoke.mockResolvedValue({
      ok: false,
      error: {
        name: 'LocalRuntimeModelRequestError',
        message: 'MODEL_DISCOVERY_UPSTREAM_ERROR: provider unavailable',
        code: 'MODEL_DISCOVERY_UPSTREAM_ERROR',
        status: 502,
      },
    })

    await expect(api.localRuntime.discoverModels({ baseUrl: 'https://provider.example/v1' }))
      .rejects.toMatchObject({
        name: 'LocalRuntimeModelRequestError',
        code: 'MODEL_DISCOVERY_UPSTREAM_ERROR',
        status: 502,
      })
  })

  test('keeps the sandboxed preload free of relative runtime imports', () => {
    const source = fs.readFileSync(path.resolve(process.cwd(), 'src/preload.ts'), 'utf8')
    const sourceFile = ts.createSourceFile('preload.ts', source, ts.ScriptTarget.Latest, true)
    const relativeRuntimeImports = sourceFile.statements.filter((statement) => (
      ts.isImportDeclaration(statement)
      && !statement.importClause?.isTypeOnly
      && ts.isStringLiteral(statement.moduleSpecifier)
      && statement.moduleSpecifier.text.startsWith('.')
    ))

    expect(relativeRuntimeImports).toEqual([])
  })

  test('should expose window namespace methods', async () => {
    vi.resetModules()
    await import('../preload')

    const exposedApi = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    expect(exposedApi).toBeDefined()
    const api = exposedApi!

    mockIpcRenderer.invoke.mockResolvedValue(undefined)

    await api.window.openRun('run-123')
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('window:open-run', 'run-123')

    mockIpcRenderer.invoke.mockResolvedValue({ windows: [] })
    await api.window.list()
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('window:list')

    mockIpcRenderer.invoke.mockResolvedValue({ bounds: {}, isMaximized: false })
    await api.window.getState()
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('window:get-state')
  })

  test('should expose profile namespace methods', async () => {
    vi.resetModules()
    await import('../preload')

    const exposedApi = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    expect(exposedApi).toBeDefined()
    const api = exposedApi!

    mockIpcRenderer.invoke.mockResolvedValue({ profiles: [] })
    await api.profile.list()
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('profile:list')

    const profile = {
      id: 'prof-1',
      label: 'Test Profile',
      apiBaseUrl: 'https://api.example.test',
      authToken: 'token-for-main-only',
    }
    mockIpcRenderer.invoke.mockResolvedValue({
      id: 'prof-1',
      label: 'Test Profile',
      apiBaseUrl: 'https://api.example.test',
      dataPath: '/tmp/prof-1',
      createdAt: '2026-01-01T00:00:00.000Z',
      updatedAt: '2026-01-01T00:00:00.000Z',
      hasCredential: true,
    })
    await api.profile.save(profile)
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('profile:save', profile)

    mockIpcRenderer.invoke.mockResolvedValue(undefined)
    await api.profile.switch('prof-1')
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('profile:switch', 'prof-1')
  })

  test('should expose localModel namespace methods', async () => {
    vi.resetModules()
    await import('../preload')

    const exposedApi = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    expect(exposedApi).toBeDefined()
    const api = exposedApi!

    mockIpcRenderer.invoke.mockResolvedValue({ enabled: false })
    await api.localModel.getSettings()
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('local-model:get-settings')

    const settings = { enabled: true, model: 'llama3' }
    mockIpcRenderer.invoke.mockResolvedValue(undefined)
    await api.localModel.setSettings(settings)
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('local-model:set-settings', settings)

    mockIpcRenderer.invoke.mockResolvedValue({ available: true })
    await api.localModel.testConnection()
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('local-model:test-connection')
  })

  test('should expose offline namespace methods', async () => {
    vi.resetModules()
    await import('../preload')

    const exposedApi = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    expect(exposedApi).toBeDefined()
    const api = exposedApi!

    const task = { goal: 'Test goal' }
    mockIpcRenderer.invoke.mockResolvedValue({ task_id: 'task-1' })
    await api.offline.runSimpleTask(task)
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('offline:run-simple-task', task)

    mockIpcRenderer.invoke.mockResolvedValue({ tasks: [] })
    await api.offline.listTasks()
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('offline:list-tasks')

    mockIpcRenderer.invoke.mockResolvedValue({ task: { id: 'task-1' }, operationId: 42 })
    await expect(api.offline.promoteResultToPendingAgentTask('offline-1')).resolves.toEqual({
      taskId: 'task-1',
      operationId: 42,
    })
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith(
      'offline:promote-result-to-pending-agent-task',
      'offline-1'
    )
  })

  test('should expose sync runtime methods and status listener', async () => {
    vi.resetModules()
    await import('../preload')
    const api = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]!

    mockIpcRenderer.invoke.mockResolvedValue({ state: 'idle' })
    await api.sync.getStatus()
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('sync:get-status')
    await api.sync.runNow()
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('sync:run-now')

    const callback = vi.fn()
    const unsubscribe = api.sync.onStatus(callback)
    const listener = mockIpcRenderer.on.mock.calls.find((call) => call[0] === 'sync:status')?.[1]
    listener?.({}, { state: 'syncing' })
    expect(callback).toHaveBeenCalledWith({ state: 'syncing' })
    unsubscribe()
    expect(mockIpcRenderer.removeListener).toHaveBeenCalledWith('sync:status', listener)
  })

  test('should expose updates namespace methods', async () => {
    vi.resetModules()
    await import('../preload')

    const exposedApi = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    expect(exposedApi).toBeDefined()
    const api = exposedApi!

    mockIpcRenderer.invoke.mockResolvedValue({ available: false })
    await api.updates.getStatus()
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('updates:get-status')

    mockIpcRenderer.invoke.mockResolvedValue({ updateAvailable: true })
    await api.updates.check()
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('updates:check')

    mockIpcRenderer.invoke.mockResolvedValue(undefined)
    await api.updates.download()
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('updates:download')

    mockIpcRenderer.invoke.mockResolvedValue(undefined)
    await api.updates.install()
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('updates:install')
  })

  test('should expose events.onUpdateStatus listener', async () => {
    vi.resetModules()
    await import('../preload')

    const exposedApi = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    expect(exposedApi).toBeDefined()
    const api = exposedApi!
    const callback = vi.fn()

    const unsubscribe = api.events.onUpdateStatus(callback)

    expect(mockIpcRenderer.on).toHaveBeenCalledWith('updates:status', expect.any(Function))

    const listener = mockIpcRenderer.on.mock.calls.find(
      (call) => call[0] === 'updates:status'
    )?.[1]
    const status = { available: true, version: '0.2.0' }
    listener({} as any, status)

    expect(callback).toHaveBeenCalledWith(status)

    unsubscribe()
    expect(mockIpcRenderer.removeListener).toHaveBeenCalledWith('updates:status', listener)
  })

  test('should expose events.onProfileChanged listener', async () => {
    vi.resetModules()
    await import('../preload')

    const exposedApi = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    expect(exposedApi).toBeDefined()
    const api = exposedApi!
    const callback = vi.fn()

    const unsubscribe = api.events.onProfileChanged(callback)

    expect(mockIpcRenderer.on).toHaveBeenCalledWith('profile:changed', expect.any(Function))

    const listener = mockIpcRenderer.on.mock.calls.find(
      (call) => call[0] === 'profile:changed'
    )?.[1]
    const profile = {
      id: 'prof-1',
      label: 'Test Profile',
      apiBaseUrl: 'https://api.example.test',
      dataPath: '/tmp/prof-1',
      createdAt: '2026-01-01T00:00:00.000Z',
      updatedAt: '2026-01-01T00:00:00.000Z',
      hasCredential: true,
    }
    listener({} as any, profile)

    expect(callback).toHaveBeenCalledWith(profile)

    unsubscribe()
    expect(mockIpcRenderer.removeListener).toHaveBeenCalledWith('profile:changed', listener)
  })

  test('should expose file namespace methods', async () => {
    vi.resetModules()
    await import('../preload')

    const exposedApi = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    expect(exposedApi).toBeDefined()
    const api = exposedApi!

    mockIpcRenderer.invoke.mockResolvedValue({ path: '/workspace' })
    await api.file.selectWorkspaceRoot()
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('file:select-workspace-root')

    mockIpcRenderer.invoke.mockResolvedValue('/workspace')
    await api.file.getWorkspaceRoot()
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('file:get-workspace-root')

    mockIpcRenderer.invoke.mockResolvedValue(undefined)
    await api.file.setWorkspaceRoot('/new-workspace')
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('file:set-workspace-root', '/new-workspace')

    mockIpcRenderer.invoke.mockResolvedValue(undefined)
    await api.file.startWatch()
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('file:start-watch')

    mockIpcRenderer.invoke.mockResolvedValue(undefined)
    await api.file.stopWatch()
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('file:stop-watch')

    mockIpcRenderer.invoke.mockResolvedValue({ files: [] })
    await api.file.listFiles('/workspace')
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('file:list-files', '/workspace')

    mockIpcRenderer.invoke.mockResolvedValue({ content: 'file content' })
    await api.file.readFile('/workspace/file.txt')
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('file:read-file', '/workspace/file.txt')

    mockIpcRenderer.invoke.mockResolvedValue(undefined)
    await api.file.writeFile('/workspace/file.txt', 'new content')
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('file:write-file', '/workspace/file.txt', 'new content')
  })

  test('exposes synchronous workspace-only persistence IPC', async () => {
    vi.resetModules()
    await import('../preload')
    const api = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    mockIpcRenderer.sendSync
      .mockReturnValueOnce('stored')
      .mockReturnValueOnce(true)
      .mockReturnValueOnce(true)

    expect(api.storage.getItem('harness.workspace.desktop.v1.registry')).toBe('stored')
    expect(api.storage.setItem('harness.workspace.desktop.v1.registry', '{}')).toBe(true)
    expect(api.storage.removeItem('harness.workspace.desktop.v1.registry')).toBe(true)
    expect(mockIpcRenderer.sendSync).toHaveBeenNthCalledWith(
      1,
      'renderer-workspace-storage:get',
      'harness.workspace.desktop.v1.registry',
    )
  })

  test('should expose file.onChange listener', async () => {
    vi.resetModules()
    await import('../preload')

    const exposedApi = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    expect(exposedApi).toBeDefined()
    const api = exposedApi!
    const callback = vi.fn()

    const unsubscribe = api.file.onChange(callback)

    expect(mockIpcRenderer.on).toHaveBeenCalledWith('file:change', expect.any(Function))

    const listener = mockIpcRenderer.on.mock.calls.find(
      (call) => call[0] === 'file:change'
    )?.[1]
    const change = { path: '/workspace/file.txt', type: 'modified' }
    listener({} as any, change)

    expect(callback).toHaveBeenCalledWith(change)

    unsubscribe()
    expect(mockIpcRenderer.removeListener).toHaveBeenCalledWith('file:change', listener)
  })
})
