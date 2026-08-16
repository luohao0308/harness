import { EventEmitter } from 'node:events'
import { PassThrough } from 'node:stream'
import * as fs from 'node:fs'
import * as os from 'node:os'
import * as path from 'node:path'
import { createHash } from 'node:crypto'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

type FakeChild = EventEmitter & {
  stdin: PassThrough
  stdout: PassThrough
  stderr: PassThrough
  exitCode: number | null
  kill: ReturnType<typeof vi.fn>
}

describe('managed local harnessd runtime', () => {
  let root: string
  let executablePath: string
  let openExternal: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.resetModules()
    root = fs.mkdtempSync(path.join(os.tmpdir(), 'harnessd-runtime-'))
    executablePath = path.join(root, process.platform === 'win32' ? 'harnessd.exe' : 'harnessd')
    fs.writeFileSync(executablePath, 'test runtime')
    openExternal = vi.fn(() => Promise.resolve())
    vi.doMock('electron', () => ({
      app: {
        getPath: vi.fn(() => root),
        isPackaged: true,
      },
      ipcMain: { handle: vi.fn() },
      safeStorage: {
        isEncryptionAvailable: vi.fn(() => true),
        encryptString: vi.fn((value: string) => Buffer.from(`encrypted:${value}`)),
        decryptString: vi.fn((value: Buffer) => value.toString().replace(/^encrypted:/, '')),
      },
      shell: { openExternal },
    }))
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    fs.rmSync(root, { recursive: true, force: true })
  })

  test('accepts one versioned ready record only from an explicit IPv4 loopback port', async () => {
    const { validateReadyHandshake } = await import('../local-runtime')
    const valid = validateReadyHandshake(JSON.stringify(readyHandshake()))

    expect(valid.origin).toBe('http://127.0.0.1:43117')
    expect(valid.healthUrl).toBe('http://127.0.0.1:43117/api/health/readiness')
    expect(valid.rendererUrl).toBe('http://127.0.0.1:43117/desktop/')

    for (const origin of [
      'http://localhost:43117',
      'http://0.0.0.0:43117',
      'https://127.0.0.1:43117',
      'http://127.0.0.1',
      'http://user:pass@127.0.0.1:43117',
    ]) {
      expect(() => validateReadyHandshake(JSON.stringify(readyHandshake({ origin })))).toThrow()
    }
  })

  test('spawns with non-secret argv, transfers bootstrap over stdin, polls health, and installs the cookie', async () => {
    const child = fakeChild()
    const spawnRuntime = vi.fn(() => child)
    const fetchRuntime = vi.fn()
      .mockResolvedValueOnce(jsonResponse(200, { status: 'ok', runtime_profile: 'local' }))
      .mockResolvedValueOnce({
        status: 204,
        headers: {
          get: (name: string) => name.toLowerCase() === 'set-cookie'
            ? 'harness_local_session=session-value; Path=/; HttpOnly; SameSite=Strict'
            : null,
        },
      } as Response)
      .mockResolvedValueOnce(jsonResponse(200, { model: 'configured' }))
      .mockResolvedValueOnce(jsonResponse(200, modelStatus('configured')))
      .mockResolvedValueOnce(jsonResponse(200, {
        state: 'configured',
        base_url: 'https://provider.example/v1',
        model: 'deepseek-v4-flash',
      }))
      .mockResolvedValueOnce(jsonResponse(200, modelStatus('configured')))
      .mockResolvedValueOnce(jsonResponse(200, {
        models: ['deepseek-v4-flash', 'deepseek-v4-pro'],
        latency_ms: 27,
      }))
      .mockResolvedValueOnce(jsonResponse(200, { token: 'one time/token' }))
    const bootstrap = {
      session_signing_secret: 'session-secret-value',
      vault_encryption_secret: 'vault-secret-value',
      desktop_bootstrap_token: 'desktop-bootstrap-value',
      model_api_key: 'model-secret-value',
      model_base_url: 'https://provider.example/v1',
      model_name: 'deepseek-v4-flash',
      persistent_secret_storage: true,
    }
    const { LocalRuntimeManager } = await import('../local-runtime')
    const manager = new LocalRuntimeManager({
      userDataPath: root,
      resourcesPath: root,
      executablePath,
      spawnRuntime: spawnRuntime as never,
      fetchRuntime,
      createSecrets: () => bootstrap,
      skipRuntimeVerification: true,
      startupTimeoutMs: 1_000,
      healthPollMs: 1,
      shutdownTimeoutMs: 5,
    })
    let stdin = ''
    child.stdin.on('data', (chunk) => { stdin += chunk.toString() })
    setTimeout(() => child.stdout.write(`${JSON.stringify(readyHandshake())}\n`), 0)

    const endpoint = await manager.start()
    const cookieSet = vi.fn(() => Promise.resolve())
    await manager.installDesktopSession({ cookies: { set: cookieSet } } as never)
    await expect(manager.applyModelApiKey('replacement-key')).resolves.toEqual(modelStatus('configured'))
    await expect(manager.saveModelConfiguration({
      baseUrl: 'https://provider.example/v1',
      model: 'deepseek-v4-flash',
      apiKey: 'configuration-key',
    })).resolves.toEqual(modelStatus('configured'))
    await expect(manager.discoverModels({
      baseUrl: 'https://probe.example/v1',
      apiKey: 'unsaved-probe-key',
    })).resolves.toEqual({
      models: ['deepseek-v4-flash', 'deepseek-v4-pro'],
      durationMs: 27,
      latencyMs: 27,
    })
    expect(await manager.openWebExtension()).toBeUndefined()

    expect(endpoint.origin).toBe('http://127.0.0.1:43117')
    const [, args, spawnOptions] = spawnRuntime.mock.calls[0] as unknown as [
      string,
      string[],
      { env?: NodeJS.ProcessEnv },
    ]
    expect(args).toEqual(['--port', '0', '--static-dir', path.join(root, 'renderer')])
    expect(JSON.stringify(args)).not.toContain('secret-value')
    expect(JSON.stringify(spawnOptions.env)).not.toContain('secret-value')
    expect(stdin).toContain('"desktop_bootstrap_token":"desktop-bootstrap-value"')
    expect(stdin).toContain('"model_api_key":"model-secret-value"')
    expect(stdin).toContain('"model_base_url":"https://provider.example/v1"')
    expect(stdin).toContain('"model_name":"deepseek-v4-flash"')
    expect(fetchRuntime).toHaveBeenNthCalledWith(1, endpoint.healthUrl, { redirect: 'error' })
    expect(fetchRuntime).toHaveBeenNthCalledWith(2, new URL('/api/local-runtime/desktop-session', endpoint.origin), expect.objectContaining({
      method: 'POST',
      headers: { 'X-Harness-Desktop-Bootstrap': 'desktop-bootstrap-value' },
    }))
    expect(cookieSet).toHaveBeenCalledWith(expect.objectContaining({
      url: endpoint.origin,
      name: 'harness_local_session',
      value: 'session-value',
      httpOnly: true,
      sameSite: 'strict',
    }))
    expect(fetchRuntime).toHaveBeenNthCalledWith(3, new URL('/api/local-runtime/model-key', endpoint.origin), expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ api_key: 'replacement-key' }),
    }))
    expect(fetchRuntime).toHaveBeenNthCalledWith(4, new URL('/api/local-runtime/model', endpoint.origin), { redirect: 'error' })
    expect(fetchRuntime).toHaveBeenNthCalledWith(5, new URL('/api/local-runtime/model-config', endpoint.origin), expect.objectContaining({
      method: 'PUT',
      headers: {
        'X-Harness-Desktop-Bootstrap': 'desktop-bootstrap-value',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        base_url: 'https://provider.example/v1',
        model: 'deepseek-v4-flash',
        api_key: 'configuration-key',
      }),
    }))
    expect(fetchRuntime).toHaveBeenNthCalledWith(6, new URL('/api/local-runtime/model', endpoint.origin), { redirect: 'error' })
    expect(fetchRuntime).toHaveBeenNthCalledWith(7, new URL('/api/local-runtime/model-discovery', endpoint.origin), expect.objectContaining({
      method: 'POST',
      headers: {
        'X-Harness-Desktop-Bootstrap': 'desktop-bootstrap-value',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        base_url: 'https://probe.example/v1',
        api_key: 'unsaved-probe-key',
      }),
    }))
    expect(openExternal).toHaveBeenCalledWith(
      'http://127.0.0.1:43117/desktop/#bootstrap=one%20time%2Ftoken',
    )
  })

  test('renews the desktop cookie as a single flight and stops renewal with the runtime', async () => {
    vi.useFakeTimers()
    const child = fakeChild()
    let sessionRequests = 0
    let releaseRenewal: (() => void) | undefined
    const fetchRuntime = vi.fn(async (input: RequestInfo | URL) => {
      const requestUrl = String(input)
      if (requestUrl.endsWith('/api/health/readiness')) {
        return jsonResponse(200, { status: 'ok', runtime_profile: 'local' })
      }
      sessionRequests += 1
      if (sessionRequests === 2) {
        await new Promise<void>((resolve) => { releaseRenewal = resolve })
      }
      return {
        status: 204,
        headers: {
          get: (name: string) => name.toLowerCase() === 'set-cookie'
            ? `harness_local_session=session-${sessionRequests}; Path=/; HttpOnly; SameSite=Strict`
            : null,
        },
      } as Response
    })
    const { LocalRuntimeManager } = await import('../local-runtime')
    const manager = new LocalRuntimeManager({
      userDataPath: root,
      resourcesPath: root,
      executablePath,
      spawnRuntime: vi.fn(() => child) as never,
      fetchRuntime,
      createSecrets: () => ({
        session_signing_secret: 'session',
        vault_encryption_secret: 'vault',
        desktop_bootstrap_token: 'desktop',
        persistent_secret_storage: true,
      }),
      skipRuntimeVerification: true,
      desktopSessionRenewalMs: 100,
      desktopSessionRetryMs: 10,
    })
    setTimeout(() => child.stdout.write(`${JSON.stringify(readyHandshake())}\n`), 0)
    const started = manager.start()
    await vi.advanceTimersByTimeAsync(0)
    await started

    const cookieSet = vi.fn(() => Promise.resolve())
    await manager.installDesktopSession({ cookies: { set: cookieSet } } as never)
    const renewalA = manager.renewDesktopSession()
    const renewalB = manager.renewDesktopSession()

    expect(sessionRequests).toBe(2)
    releaseRenewal?.()
    await Promise.all([renewalA, renewalB])
    expect(cookieSet).toHaveBeenCalledTimes(2)

    await vi.advanceTimersByTimeAsync(100)
    expect(sessionRequests).toBe(3)
    expect(cookieSet).toHaveBeenCalledTimes(3)

    child.exitCode = 0
    await manager.stop()
    await vi.advanceTimersByTimeAsync(500)
    expect(sessionRequests).toBe(3)
  })

  test('keeps runtime stdout and stderr drained after the ready handshake', async () => {
    const child = fakeChild()
    const { LocalRuntimeManager } = await import('../local-runtime')
    const manager = new LocalRuntimeManager({
      userDataPath: root,
      resourcesPath: root,
      executablePath,
      spawnRuntime: vi.fn(() => child) as never,
      fetchRuntime: vi.fn(() => Promise.resolve(jsonResponse(200, { runtime_ready: true }))),
      createSecrets: () => ({
        session_signing_secret: 'session',
        vault_encryption_secret: 'vault',
        desktop_bootstrap_token: 'desktop',
        persistent_secret_storage: true,
      }),
      skipRuntimeVerification: true,
      maxRestarts: 0,
    })
    setTimeout(() => child.stdout.write(`${JSON.stringify(readyHandshake())}\n`), 0)

    await manager.start()
    child.stdout.write(Buffer.alloc(256 * 1024))
    child.stderr.write(Buffer.alloc(256 * 1024))
    await new Promise<void>((resolve) => setImmediate(resolve))

    expect(child.stdout.readableFlowing).toBe(true)
    expect(child.stderr.readableFlowing).toBe(true)
    expect(child.stdout.readableLength).toBe(0)
    expect(child.stderr.readableLength).toBe(0)
  })

  test('parses stable model discovery errors without exposing response bodies', async () => {
    const child = fakeChild()
    const fetchRuntime = vi.fn()
      .mockResolvedValueOnce(jsonResponse(200, { runtime_ready: true }))
      .mockResolvedValueOnce(jsonResponse(502, {
        detail: {
          code: 'MODEL_DISCOVERY_AUTH_ERROR',
          message: 'Provider rejected the supplied credential',
        },
      }))
    const { LocalRuntimeManager, LocalRuntimeModelRequestError } = await import('../local-runtime')
    const manager = new LocalRuntimeManager({
      userDataPath: root,
      resourcesPath: root,
      executablePath,
      spawnRuntime: vi.fn(() => child) as never,
      fetchRuntime,
      createSecrets: () => ({
        session_signing_secret: 'session',
        vault_encryption_secret: 'vault',
        desktop_bootstrap_token: 'desktop',
        persistent_secret_storage: true,
      }),
      skipRuntimeVerification: true,
      maxRestarts: 0,
    })
    setTimeout(() => child.stdout.write(`${JSON.stringify(readyHandshake())}\n`), 0)
    await manager.start()

    const error = await manager.discoverModels({
      baseUrl: 'https://provider.example/v1',
      apiKey: 'credential-not-in-error',
    }).catch((caught) => caught)

    expect(error).toBeInstanceOf(LocalRuntimeModelRequestError)
    expect(error).toMatchObject({ code: 'MODEL_DISCOVERY_AUTH_ERROR', status: 502 })
    expect(error.message).toBe('MODEL_DISCOVERY_AUTH_ERROR: Provider rejected the supplied credential')
    expect(error.message).not.toContain('credential-not-in-error')
  })

  test('restarts once with backoff after a ready child exits and kills the child on full stop', async () => {
    vi.useFakeTimers()
    try {
      const children = [fakeChild(), fakeChild()]
      const bootstrapInputs = ['', '']
      const spawnRuntime = vi.fn(() => {
        const index = spawnRuntime.mock.calls.length - 1
        const child = children[index]
        child.stdin.on('data', (chunk) => { bootstrapInputs[index] += chunk.toString() })
        setTimeout(() => child.stdout.write(`${JSON.stringify(readyHandshake())}\n`), 0)
        return child
      })
      const createSecrets = vi.fn()
        .mockReturnValueOnce({
          session_signing_secret: 'session',
          vault_encryption_secret: 'vault',
          desktop_bootstrap_token: 'desktop',
          persistent_secret_storage: true,
        })
        .mockReturnValueOnce({
          session_signing_secret: 'session-restart',
          vault_encryption_secret: 'vault',
          desktop_bootstrap_token: 'desktop-restart',
          model_api_key: 'restart-key',
          model_base_url: 'https://restart.example/v1',
          model_name: 'restart-model',
          persistent_secret_storage: true,
        })
      const onEndpoint = vi.fn()
      const { LocalRuntimeManager } = await import('../local-runtime')
      const manager = new LocalRuntimeManager({
        userDataPath: root,
        resourcesPath: root,
        executablePath,
        spawnRuntime: spawnRuntime as never,
        fetchRuntime: vi.fn(() => Promise.resolve(jsonResponse(200, { runtime_ready: true }))),
        createSecrets,
        skipRuntimeVerification: true,
        initialBackoffMs: 10,
        maxRestarts: 1,
        startupTimeoutMs: 1_000,
        onEndpoint,
      })

      const started = manager.start()
      await vi.advanceTimersByTimeAsync(0)
      await started
      children[0].exitCode = 17
      children[0].emit('exit', 17, null)
      await vi.advanceTimersByTimeAsync(10)
      await vi.waitFor(() => expect(spawnRuntime).toHaveBeenCalledTimes(2))
      await vi.waitFor(() => expect(onEndpoint).toHaveBeenCalledTimes(2))
      expect(createSecrets).toHaveBeenCalledTimes(2)
      expect(bootstrapInputs[1]).toContain('"model_api_key":"restart-key"')
      expect(bootstrapInputs[1]).toContain('"model_base_url":"https://restart.example/v1"')
      expect(bootstrapInputs[1]).toContain('"model_name":"restart-model"')

      const stop = manager.stop()
      expect(children[1].kill).toHaveBeenCalledWith('SIGTERM')
      children[1].exitCode = 0
      children[1].emit('exit', 0, null)
      await stop
    } finally {
      vi.useRealTimers()
    }
  })

  test('verifies the packaged manifest checksum before spawn and cleans up an invalid ready child', async () => {
    const checksum = createHash('sha256').update(fs.readFileSync(executablePath)).digest('hex')
    fs.writeFileSync(path.join(root, 'runtime-manifest.json'), JSON.stringify({
      schema_version: 1,
      runtime_version: '0.1.0',
      platform: process.platform,
      architecture: process.arch,
      executable: path.basename(executablePath),
      sha256: checksum,
    }))
    const child = fakeChild()
    child.kill.mockImplementation(() => {
      child.exitCode = 1
      queueMicrotask(() => child.emit('exit', 1, null))
      return true
    })
    const spawnRuntime = vi.fn(() => {
      setTimeout(() => child.stdout.write(`${JSON.stringify(readyHandshake({ origin: 'http://0.0.0.0:43117' }))}\n`), 0)
      return child
    })
    const { LocalRuntimeManager } = await import('../local-runtime')
    const manager = new LocalRuntimeManager({
      userDataPath: root,
      resourcesPath: root,
      executablePath,
      spawnRuntime: spawnRuntime as never,
      createSecrets: () => ({
        session_signing_secret: 'session',
        vault_encryption_secret: 'vault',
        desktop_bootstrap_token: 'desktop',
        persistent_secret_storage: true,
      }),
      startupTimeoutMs: 100,
      shutdownTimeoutMs: 10,
      maxRestarts: 0,
    })

    await expect(manager.start()).rejects.toThrow('explicit 127.0.0.1')
    expect(child.kill).toHaveBeenCalledWith('SIGTERM')

    fs.writeFileSync(path.join(root, 'runtime-manifest.json'), JSON.stringify({
      schema_version: 1,
      runtime_version: '0.1.0',
      platform: process.platform,
      architecture: process.arch,
      executable: path.basename(executablePath),
      sha256: '0'.repeat(64),
    }))
    await expect(manager.start()).rejects.toThrow('checksum verification failed')
    expect(spawnRuntime).toHaveBeenCalledTimes(1)
  })

  test('resolves and verifies an exact schema v2 onedir runtime tree', async () => {
    const resourcesPath = path.join(root, 'resources')
    const runtimeRoot = path.join(resourcesPath, 'runtime', process.platform, process.arch)
    const nestedExecutable = path.join(runtimeRoot, 'harnessd', process.platform === 'win32' ? 'harnessd.exe' : 'harnessd')
    const libraryPath = path.join(runtimeRoot, 'harnessd', 'runtime-library.bin')
    fs.mkdirSync(path.dirname(nestedExecutable), { recursive: true })
    fs.writeFileSync(nestedExecutable, 'onedir runtime')
    fs.writeFileSync(libraryPath, 'runtime library')
    writeV2Manifest(runtimeRoot, nestedExecutable, [nestedExecutable, libraryPath])

    const child = fakeChild()
    const spawnRuntime = vi.fn(() => {
      setTimeout(() => child.stdout.write(`${JSON.stringify(readyHandshake())}\n`), 0)
      return child
    })
    const { LocalRuntimeManager, resolveLocalRuntimePaths } = await import('../local-runtime')
    expect(resolveLocalRuntimePaths({ userDataPath: root, resourcesPath }).executablePath).toBe(nestedExecutable)
    const manager = new LocalRuntimeManager({
      userDataPath: root,
      resourcesPath,
      spawnRuntime: spawnRuntime as never,
      fetchRuntime: vi.fn(() => Promise.resolve(jsonResponse(200, { runtime_ready: true }))),
      createSecrets: () => ({
        session_signing_secret: 'session',
        vault_encryption_secret: 'vault',
        desktop_bootstrap_token: 'desktop',
        persistent_secret_storage: true,
      }),
      maxRestarts: 0,
    })

    await manager.start()
    expect(spawnRuntime).toHaveBeenCalledWith(nestedExecutable, expect.any(Array), expect.any(Object))
    child.exitCode = 0
    child.emit('exit', 0, null)

    fs.writeFileSync(path.join(runtimeRoot, 'unexpected.bin'), 'extra')
    await expect(manager.start()).rejects.toThrow('not in the manifest')
    fs.rmSync(path.join(runtimeRoot, 'unexpected.bin'))
    fs.rmSync(libraryPath)
    await expect(manager.start()).rejects.toThrow('file is missing')
  })

  test('rejects traversal and symlinks in schema v2 runtime manifests', async () => {
    const resourcesPath = path.join(root, 'resources')
    const runtimeRoot = path.join(resourcesPath, 'runtime', process.platform, process.arch)
    fs.mkdirSync(runtimeRoot, { recursive: true })
    fs.writeFileSync(path.join(runtimeRoot, 'runtime-manifest.json'), JSON.stringify({
      schema_version: 2,
      runtime_version: '0.1.0',
      platform: process.platform,
      architecture: process.arch,
      executable: '../harnessd',
      sha256: '0'.repeat(64),
      files: { '../harnessd': '0'.repeat(64) },
    }))
    const { LocalRuntimeManager } = await import('../local-runtime')
    expect(() => new LocalRuntimeManager({ userDataPath: root, resourcesPath })).toThrow('manifest path is invalid')

    if (process.platform === 'win32') return
    const nestedExecutable = path.join(runtimeRoot, 'harnessd', 'harnessd')
    fs.mkdirSync(path.dirname(nestedExecutable), { recursive: true })
    fs.writeFileSync(nestedExecutable, 'onedir runtime')
    fs.symlinkSync(nestedExecutable, path.join(runtimeRoot, 'harnessd', 'linked-runtime'))
    writeV2Manifest(runtimeRoot, nestedExecutable, [nestedExecutable])
    const manager = new LocalRuntimeManager({ userDataPath: root, resourcesPath, maxRestarts: 0 })
    await expect(manager.start()).rejects.toThrow('symlink is not allowed')
  })
})

function writeV2Manifest(runtimeRoot: string, executable: string, files: string[]): void {
  const relativeExecutable = path.relative(runtimeRoot, executable).split(path.sep).join('/')
  const hashes = Object.fromEntries(files.map((file) => [
    path.relative(runtimeRoot, file).split(path.sep).join('/'),
    createHash('sha256').update(fs.readFileSync(file)).digest('hex'),
  ]))
  fs.writeFileSync(path.join(runtimeRoot, 'runtime-manifest.json'), JSON.stringify({
    schema_version: 2,
    runtime_version: '0.1.0',
    platform: process.platform,
    architecture: process.arch,
    executable: relativeExecutable,
    sha256: hashes[relativeExecutable],
    files: hashes,
  }))
}

function readyHandshake(overrides: Record<string, unknown> = {}) {
  return {
    protocol_version: 1,
    origin: 'http://127.0.0.1:43117',
    health_path: '/api/health/readiness',
    desktop_session_path: '/api/local-runtime/desktop-session',
    renderer_path: '/desktop/',
    runtime_version: '0.1.0',
    ...overrides,
  }
}

function modelStatus(state: 'setup_required' | 'configured') {
  return {
    state,
    provider: 'openai-compatible',
    model: 'deepseek-v4-flash',
    base_url: 'https://provider.example/v1',
    secret_storage: 'persistent',
    message: null,
  }
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function fakeChild(): FakeChild {
  const child = new EventEmitter() as FakeChild
  child.stdin = new PassThrough()
  child.stdout = new PassThrough()
  child.stderr = new PassThrough()
  child.exitCode = null
  child.kill = vi.fn(() => true)
  return child
}
