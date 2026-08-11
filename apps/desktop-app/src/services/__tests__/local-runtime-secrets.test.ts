import * as fs from 'node:fs'
import * as os from 'node:os'
import * as path from 'node:path'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

describe('local runtime secret storage', () => {
  let root: string
  let ipcHandlers: Map<string, (...args: any[]) => any>

  beforeEach(() => {
    vi.resetModules()
    root = fs.mkdtempSync(path.join(os.tmpdir(), 'harness-runtime-secrets-'))
    ipcHandlers = new Map()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    fs.rmSync(root, { recursive: true, force: true })
  })

  test('persists only safeStorage ciphertext and never exposes the key through status', async () => {
    mockElectron(true)
    const secrets = await import('../local-runtime-secrets')

    const status = secrets.setLocalRuntimeModelApiKey('model-key-plaintext')
    const bootstrap = secrets.createLocalRuntimeBootstrapSecrets()
    const persisted = fs.readFileSync(path.join(root, 'secrets.json'), 'utf8')

    expect(status).toEqual({
      persistentStorageAvailable: true,
      modelKeyConfigured: true,
      modelKeyStorage: 'persistent',
    })
    expect(status).not.toHaveProperty('modelApiKey')
    expect(bootstrap.model_api_key).toBe('model-key-plaintext')
    expect(persisted).not.toContain('model-key-plaintext')
    expect(persisted).toContain(Buffer.from('cipher:model-key-plaintext').toString('base64'))
  })

  test('migrates schema v1 and restores model configuration in restart bootstrap', async () => {
    fs.writeFileSync(path.join(root, 'secrets.json'), JSON.stringify({
      schemaVersion: 1,
      modelApiKey: Buffer.from('cipher:legacy-key').toString('base64'),
      vaultKey: Buffer.from('cipher:legacy-vault').toString('base64'),
    }))
    mockElectron(true)
    const secrets = await import('../local-runtime-secrets')
    secrets.persistLocalRuntimeModelConfiguration(modelStatus(), {})

    vi.resetModules()
    mockElectron(true)
    const restarted = await import('../local-runtime-secrets')
    const bootstrap = restarted.createLocalRuntimeBootstrapSecrets()
    const persisted = JSON.parse(fs.readFileSync(path.join(root, 'secrets.json'), 'utf8'))

    expect(persisted).toMatchObject({
      schemaVersion: 2,
      modelBaseUrl: 'https://provider.example/v1',
      modelName: 'provider-model',
    })
    expect(bootstrap).toMatchObject({
      model_api_key: 'legacy-key',
      model_base_url: 'https://provider.example/v1',
      model_name: 'provider-model',
      persistent_secret_storage: true,
    })
  })

  test('uses session memory only when safeStorage is unavailable', async () => {
    mockElectron(false)
    const secrets = await import('../local-runtime-secrets')

    expect(secrets.setLocalRuntimeModelApiKey('session-key')).toMatchObject({
      modelKeyConfigured: true,
      modelKeyStorage: 'session',
      persistentStorageAvailable: false,
    })
    expect(secrets.createLocalRuntimeBootstrapSecrets()).toMatchObject({
      model_api_key: 'session-key',
      persistent_secret_storage: false,
    })
    expect(fs.existsSync(path.join(root, 'secrets.json'))).toBe(false)

    vi.resetModules()
    mockElectron(false)
    const afterRestart = await import('../local-runtime-secrets')
    expect(afterRestart.getLocalRuntimeSecretStatus()).toMatchObject({
      modelKeyConfigured: false,
      modelKeyStorage: 'none',
    })
  })

  test('completes renderer IPC through harnessd before returning model status', async () => {
    mockElectron(true)
    const secrets = await import('../local-runtime-secrets')
    const status = {
      state: 'configured' as const,
      provider: 'openai-compatible',
      model: 'deepseek-v4-flash',
      base_url: 'https://provider.example/v1',
      secret_storage: 'persistent' as const,
      message: null,
    }
    const applyModelApiKey = vi.fn(() => Promise.resolve(status))
    secrets.registerLocalRuntimeSecretHandlers({ applyModelApiKey })
    const handler = ipcHandlers.get('local-runtime:set-model-api-key')

    await expect(handler?.(trustedEvent(), 'ipc-model-key')).resolves.toEqual({ ok: true, value: status })

    expect(applyModelApiKey).toHaveBeenCalledWith('ipc-model-key')
    expect(fs.readFileSync(path.join(root, 'secrets.json'), 'utf8')).not.toContain('ipc-model-key')
  })

  test('persists normalized configuration only after backend success', async () => {
    mockElectron(true)
    const secrets = await import('../local-runtime-secrets')
    const saveModelConfiguration = vi.fn(() => Promise.resolve(modelStatus()))
    secrets.registerLocalRuntimeSecretHandlers({ saveModelConfiguration })
    const handler = ipcHandlers.get('local-runtime:save-model-configuration')
    const input = {
      baseUrl: 'https://input.example/v1',
      model: 'input-model',
      apiKey: 'configuration-secret',
    }

    await expect(handler?.(trustedEvent(), input)).resolves.toEqual({ ok: true, value: modelStatus() })

    const persisted = fs.readFileSync(path.join(root, 'secrets.json'), 'utf8')
    expect(saveModelConfiguration).toHaveBeenCalledWith(input)
    expect(persisted).toContain('https://provider.example/v1')
    expect(persisted).toContain('provider-model')
    expect(persisted).not.toContain('configuration-secret')
    expect(secrets.createLocalRuntimeBootstrapSecrets()).toMatchObject({
      model_api_key: 'configuration-secret',
      model_base_url: 'https://provider.example/v1',
      model_name: 'provider-model',
    })
  })

  test('does not persist failed saves or unsaved discovery probes', async () => {
    mockElectron(true)
    const secrets = await import('../local-runtime-secrets')
    const saveModelConfiguration = vi.fn(() => Promise.reject(new Error('backend rejected configuration')))
    const discoverModels = vi.fn(() => Promise.resolve({
      models: ['probe-model'],
      durationMs: 18,
      latencyMs: 18,
    }))
    secrets.registerLocalRuntimeSecretHandlers({ saveModelConfiguration, discoverModels })
    const save = ipcHandlers.get('local-runtime:save-model-configuration')
    const discover = ipcHandlers.get('local-runtime:discover-models')

    await expect(save?.(trustedEvent(), {
      baseUrl: 'https://failed.example/v1',
      model: 'failed-model',
      apiKey: 'failed-secret',
    })).resolves.toEqual({
      ok: false,
      error: { name: 'Error', message: 'backend rejected configuration' },
    })
    await expect(discover?.(trustedEvent(), {
      baseUrl: 'https://probe.example/v1',
      apiKey: 'probe-secret',
    })).resolves.toMatchObject({ ok: true, value: { models: ['probe-model'] } })

    expect(fs.existsSync(path.join(root, 'secrets.json'))).toBe(false)
    expect(discoverModels).toHaveBeenCalledWith({
      baseUrl: 'https://probe.example/v1',
      apiKey: 'probe-secret',
    })
  })

  test('keeps the existing trusted sender boundary for new handlers', async () => {
    mockElectron(true)
    const secrets = await import('../local-runtime-secrets')
    const saveModelConfiguration = vi.fn(() => Promise.resolve(modelStatus()))
    const discoverModels = vi.fn(() => Promise.resolve({ models: [], durationMs: 0, latencyMs: 0 }))
    const renewSession = vi.fn(() => Promise.resolve())
    secrets.registerLocalRuntimeSecretHandlers({ saveModelConfiguration, discoverModels, renewSession })
    const untrusted = {
      senderFrame: { url: 'https://untrusted.example/' },
      sender: { getURL: () => 'https://untrusted.example/' },
    }

    await expect(ipcHandlers.get('local-runtime:save-model-configuration')?.(untrusted, {
      baseUrl: 'https://provider.example/v1',
      model: 'provider-model',
    })).rejects.toThrow('local runtime secret IPC is unavailable')
    await expect(ipcHandlers.get('local-runtime:discover-models')?.(untrusted, {
      baseUrl: 'https://provider.example/v1',
    })).rejects.toThrow('local runtime secret IPC is unavailable')
    await expect(ipcHandlers.get('local-runtime:renew-session')?.(untrusted))
      .rejects.toThrow('local runtime secret IPC is unavailable')
    expect(saveModelConfiguration).not.toHaveBeenCalled()
    expect(discoverModels).not.toHaveBeenCalled()
    expect(renewSession).not.toHaveBeenCalled()
  })

  test('renews the desktop session only for a trusted runtime sender', async () => {
    mockElectron(true)
    const secrets = await import('../local-runtime-secrets')
    const renewSession = vi.fn(() => Promise.resolve())
    secrets.registerLocalRuntimeSecretHandlers({ renewSession })

    await expect(ipcHandlers.get('local-runtime:renew-session')?.(trustedEvent()))
      .resolves.toEqual({ ok: true, value: undefined })
    expect(renewSession).toHaveBeenCalledOnce()
  })

  function mockElectron(encryptionAvailable: boolean): void {
    vi.doMock('electron', () => ({
      app: { getPath: vi.fn(() => root) },
      ipcMain: { handle: vi.fn((channel: string, handler: (...args: any[]) => any) => ipcHandlers.set(channel, handler)) },
      safeStorage: {
        isEncryptionAvailable: vi.fn(() => encryptionAvailable),
        encryptString: vi.fn((value: string) => Buffer.from(`cipher:${value}`)),
        decryptString: vi.fn((value: Buffer) => value.toString().replace(/^cipher:/, '')),
      },
    }))
  }


  function trustedEvent() {
    return {
      senderFrame: { url: 'harness-app://renderer/index.html' },
      sender: { getURL: () => 'harness-app://renderer/index.html' },
    }
  }

  function modelStatus() {
    return {
      state: 'configured' as const,
      provider: 'openai-compatible',
      model: 'provider-model',
      base_url: 'https://provider.example/v1',
      secret_storage: 'persistent' as const,
      message: null,
    }
  }
})
