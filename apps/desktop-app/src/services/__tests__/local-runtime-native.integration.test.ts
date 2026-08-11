import * as fs from 'node:fs'
import * as os from 'node:os'
import * as path from 'node:path'
import * as http from 'node:http'
import { afterAll, beforeAll, describe, expect, test, vi } from 'vitest'

const desktopRoot = path.resolve(__dirname, '..', '..', '..')
const executableName = process.platform === 'win32' ? 'harnessd.exe' : 'harnessd'
const runtimeRoot = path.join(desktopRoot, 'resources', 'runtime', process.platform, process.arch)
const executablePath = resolveNativeExecutable(runtimeRoot, executableName)
const hasNativeRuntime = fs.existsSync(executablePath)
const roots: string[] = []

vi.mock('electron', () => ({
  app: {
    getPath: vi.fn(() => roots[0] || os.tmpdir()),
    isPackaged: true,
  },
  ipcMain: { handle: vi.fn() },
  safeStorage: {
    isEncryptionAvailable: vi.fn(() => false),
  },
  shell: { openExternal: vi.fn(() => Promise.resolve()) },
}))

describe.skipIf(!hasNativeRuntime)('native harnessd desktop contract', () => {
  let userDataPath: string
  let resourcesPath: string

  beforeAll(() => {
    userDataPath = fs.mkdtempSync(path.join(os.tmpdir(), 'harnessd-native-user-data-'))
    resourcesPath = fs.mkdtempSync(path.join(os.tmpdir(), 'harnessd-native-resources-'))
    roots.push(userDataPath, resourcesPath)
    fs.mkdirSync(path.join(resourcesPath, 'renderer'), { recursive: true })
    fs.writeFileSync(path.join(resourcesPath, 'renderer', 'index.html'), '<!doctype html><title>Harness</title>')
  })

  afterAll(() => {
    for (const root of roots) fs.rmSync(root, { recursive: true, force: true })
  })

  test('sets and deletes the first model key through the supervised native runtime', async () => {
    const { LocalRuntimeManager } = await import('../local-runtime')
    const manager = new LocalRuntimeManager({
      userDataPath,
      resourcesPath,
      executablePath,
      fetchRuntime: nodeFetch,
      startupTimeoutMs: 45_000,
      healthPollMs: 100,
      shutdownTimeoutMs: 10_000,
      maxRestarts: 0,
      createSecrets: () => ({
        session_signing_secret: 'native-session-signing-secret-at-least-32-characters',
        vault_encryption_secret: 'native-vault-encryption-secret-at-least-32-characters',
        desktop_bootstrap_token: 'native-desktop-bootstrap-token-at-least-32-characters',
        persistent_secret_storage: false,
      }),
    })

    try {
      await manager.start()
      await expect(manager.getModelStatus()).resolves.toMatchObject({ state: 'setup_required' })
      await expect(manager.applyModelApiKey('native-integration-model-key')).resolves.toMatchObject({
        state: 'configured',
        secret_storage: 'session',
      })
      await expect(manager.deleteModelApiKey()).resolves.toMatchObject({ state: 'setup_required' })
    } finally {
      await manager.stop()
    }

    expect(fs.existsSync(path.join(userDataPath, 'runtime', 'harness.sqlite3'))).toBe(true)
  }, 60_000)
})

function nodeFetch(input: string | URL | Request, init: RequestInit = {}): Promise<Response> {
  const url = new URL(typeof input === 'string' || input instanceof URL ? input.toString() : input.url)
  return new Promise((resolve, reject) => {
    const request = http.request(url, {
      method: init.method || 'GET',
      headers: init.headers as http.OutgoingHttpHeaders | undefined,
    }, (response) => {
      const chunks: Buffer[] = []
      response.on('data', (chunk) => chunks.push(Buffer.from(chunk)))
      response.on('end', () => {
        resolve(new Response(Buffer.concat(chunks), {
          status: response.statusCode || 500,
          headers: response.headers as HeadersInit,
        }))
      })
    })
    request.on('error', reject)
    if (init.body) request.write(init.body)
    request.end()
  })
}

function resolveNativeExecutable(root: string, fallbackName: string): string {
  try {
    const manifest = JSON.parse(fs.readFileSync(path.join(root, 'runtime-manifest.json'), 'utf8')) as { executable?: unknown }
    if (typeof manifest.executable === 'string'
      && !manifest.executable.startsWith('/')
      && !manifest.executable.includes('..')
      && !manifest.executable.includes('\\')) {
      return path.join(root, ...manifest.executable.split('/'))
    }
  } catch {
    // The integration test is skipped when no native runtime has been built.
  }
  return path.join(root, fallbackName)
}
