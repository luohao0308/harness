import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'

describe('desktop phase 6 services', () => {
  let userDataRoot: string
  let mockIpcMain: { handle: ReturnType<typeof vi.fn> }
  let mockWindows: Array<{ webContents: { send: ReturnType<typeof vi.fn> } }>
  let mockSafeStorage: {
    isEncryptionAvailable: ReturnType<typeof vi.fn>
    encryptString: ReturnType<typeof vi.fn>
    decryptString: ReturnType<typeof vi.fn>
  }

  beforeEach(() => {
    vi.resetModules()
    userDataRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'desktop-phase6-'))
    mockIpcMain = { handle: vi.fn() }
    mockWindows = [{ webContents: { send: vi.fn() } }]
    mockSafeStorage = {
      isEncryptionAvailable: vi.fn(() => true),
      encryptString: vi.fn((value: string) => Buffer.from(`encrypted:${value}`)),
      decryptString: vi.fn((value: Buffer) => value.toString('utf-8').replace(/^encrypted:/, '')),
    }
    vi.doMock('electron', () => ({
      app: {
        getPath: vi.fn(() => userDataRoot),
      },
      BrowserWindow: {
        getAllWindows: vi.fn(() => mockWindows),
      },
      ipcMain: mockIpcMain,
      safeStorage: mockSafeStorage,
    }))
    global.fetch = vi.fn()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    fs.rmSync(userDataRoot, { recursive: true, force: true })
  })

  test('persists encrypted profiles and exposes only sanitized metadata to the renderer', async () => {
    const { registerPhase6Handlers } = await import('../services/phase6-service')
    const { getApiBaseUrl, getAuthToken } = await import('../shared/api-client')
    registerPhase6Handlers()

    const save = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'profile:save')?.[1]
    const list = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'profile:list')?.[1]
    const switchProfile = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'profile:switch')?.[1]

    const profile = save?.({}, {
      id: 'customer-a',
      label: 'Customer A',
      apiBaseUrl: 'https://customer-a.example.test',
      authToken: 'token-a',
    })

    expect(profile).toMatchObject({
      id: 'customer-a',
      label: 'Customer A',
      apiBaseUrl: 'https://customer-a.example.test',
      hasCredential: true,
    })
    expect(profile).not.toHaveProperty('authToken')

    expect(list?.({})).toMatchObject({
      activeProfileId: 'default',
      profiles: expect.arrayContaining([
        expect.objectContaining({ id: 'customer-a', hasCredential: true }),
      ]),
    })
    expect(list?.({}).profiles.find((item: { id: string }) => item.id === 'customer-a')).not.toHaveProperty('authToken')

    expect(switchProfile?.({ sender: { send: vi.fn() } }, 'customer-a')).toMatchObject({
      id: 'customer-a',
      hasCredential: true,
    })
    expect(mockWindows[0].webContents.send).toHaveBeenCalledWith(
      'profile:changed',
      expect.objectContaining({ id: 'customer-a', hasCredential: true })
    )
    expect(getApiBaseUrl()).toBe('https://customer-a.example.test')
    expect(getAuthToken()).toBe('token-a')
    const stateFile = path.join(userDataRoot, 'phase6-state.json')
    const persisted = fs.readFileSync(stateFile, 'utf-8')
    expect(persisted).toContain('"schemaVersion": 2')
    expect(persisted).toContain('"kind": "safeStorage"')
    expect(persisted).not.toContain('"authToken"')
    expect(persisted).not.toContain('token-a')
    expect(mockSafeStorage.encryptString).toHaveBeenCalledWith('token-a')
    expect(mockSafeStorage.decryptString).toHaveBeenCalled()
  })

  test('migrates legacy plaintext profile tokens to encrypted v2 state', async () => {
    fs.writeFileSync(
      path.join(userDataRoot, 'phase6-state.json'),
      JSON.stringify({
        activeProfileId: 'legacy',
        profiles: [
          {
            id: 'legacy',
            label: 'Legacy',
            apiBaseUrl: 'https://legacy.example.test',
            authToken: 'legacy-token',
            dataPath: '/tmp/legacy',
            createdAt: '2026-01-01T00:00:00.000Z',
            updatedAt: '2026-01-01T00:00:00.000Z',
          },
        ],
      })
    )
    const { readPhase6State, listProfiles, getActiveProfileCredential } = await import('../services/phase6-store')

    readPhase6State()

    expect(listProfiles()).toMatchObject({
      activeProfileId: 'legacy',
      profiles: [expect.objectContaining({ id: 'legacy', hasCredential: true })],
    })
    expect(listProfiles().profiles[0]).not.toHaveProperty('authToken')
    expect(getActiveProfileCredential()).toBe('legacy-token')
    const persisted = fs.readFileSync(path.join(userDataRoot, 'phase6-state.json'), 'utf-8')
    expect(persisted).toContain('"schemaVersion": 2')
    expect(persisted).not.toContain('"authToken"')
    expect(persisted).not.toContain('legacy-token')
  })

  test('runs simple offline tasks with deterministic fallback when local model is disabled', async () => {
    const { registerPhase6Handlers } = await import('../services/phase6-service')
    registerPhase6Handlers()

    const run = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'offline:run-simple-task')?.[1]
    const list = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'offline:list-tasks')?.[1]

    const result = await run?.({}, {
      prompt: '整理离线发布检查\n确认测试证据',
      useLocalModel: true,
    })

    expect(result).toMatchObject({
      modelSource: 'deterministic-local',
      status: 'completed',
    })
    expect(result.result).toContain('离线任务已完成')
    expect(list?.({}).items[0].id).toBe(result.id)
  })

  test('uses optional local model settings when enabled', async () => {
    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      json: async () => ({ response: 'local model answer' }),
    } as Response)
    const { registerPhase6Handlers } = await import('../services/phase6-service')
    registerPhase6Handlers()

    const setSettings = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'local-model:set-settings')?.[1]
    const run = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'offline:run-simple-task')?.[1]

    setSettings?.({}, {
      enabled: true,
      provider: 'ollama',
      baseUrl: 'http://127.0.0.1:11434',
      model: 'llama3.1',
    })

    const result = await run?.({}, { prompt: 'hello local model', useLocalModel: true })

    expect(result).toMatchObject({
      modelSource: 'local-model',
      result: 'local model answer',
    })
    expect(global.fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:11434/api/generate',
      expect.objectContaining({ method: 'POST', signal: expect.any(AbortSignal) })
    )
  })

  test('rejects remote local-model endpoints unless explicitly allowed', async () => {
    const { registerPhase6Handlers } = await import('../services/phase6-service')
    registerPhase6Handlers()
    const setSettings = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'local-model:set-settings')?.[1]

    expect(() => setSettings?.({}, {
      enabled: true,
      provider: 'openai-compatible',
      baseUrl: 'https://models.example.test/v1',
      model: 'private-model',
    })).toThrow('local model endpoint must be on this device')
  })

  test('reports local-model health and records an explicit fallback reason', async () => {
    vi.mocked(global.fetch).mockRejectedValue(new Error('connection refused'))
    const { registerPhase6Handlers } = await import('../services/phase6-service')
    registerPhase6Handlers()
    const setSettings = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'local-model:set-settings')?.[1]
    const testConnection = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'local-model:test-connection')?.[1]
    const run = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'offline:run-simple-task')?.[1]

    setSettings?.({}, {
      enabled: true,
      provider: 'ollama',
      baseUrl: 'http://127.0.0.1:11434',
      model: 'llama3.1',
    })

    await expect(testConnection?.({})).resolves.toMatchObject({
      available: false,
      error: 'connection refused',
    })
    await expect(run?.({}, { prompt: 'fallback please', useLocalModel: true })).resolves.toMatchObject({
      modelSource: 'deterministic-local',
      modelRequested: true,
      fallbackReason: 'connection refused',
      durationMs: expect.any(Number),
    })
  })
})
