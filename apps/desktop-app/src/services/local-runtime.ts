import { app, shell } from 'electron'
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { createHash } from 'node:crypto'
import * as fs from 'node:fs'
import * as path from 'node:path'
import { createLocalRuntimeBootstrapSecrets, type LocalRuntimeBootstrapSecrets } from './local-runtime-secrets'
import type {
  LocalRuntimeModelConfigInput,
  LocalRuntimeModelDiscovery,
  LocalRuntimeModelDiscoveryInput,
  LocalRuntimeModelStatus,
} from '../preload-api'

export type LocalRuntimeModelErrorCode =
  | 'INVALID_MODEL_BASE_URL'
  | 'INVALID_MODEL_ID'
  | 'INVALID_MODEL_CATALOG'
  | 'MODEL_API_KEY_REQUIRED'
  | 'MODEL_DISCOVERY_AUTH_ERROR'
  | 'MODEL_DISCOVERY_TIMEOUT'
  | 'MODEL_DISCOVERY_UPSTREAM_ERROR'
  | 'MODEL_DISCOVERY_RESPONSE_TOO_LARGE'
  | 'MODEL_DISCOVERY_INVALID_RESPONSE'

export class LocalRuntimeModelRequestError extends Error {
  constructor(
    readonly code: LocalRuntimeModelErrorCode,
    message: string,
    readonly status: number,
  ) {
    super(`${code}: ${message}`)
    this.name = 'LocalRuntimeModelRequestError'
  }
}

export type HarnessdReadyHandshake = {
  protocol_version: 1
  origin: string
  health_path: string
  desktop_session_path: string
  renderer_path: string
  runtime_version: string
  runtime_checksum?: string
}

export type LocalRuntimeEndpoint = HarnessdReadyHandshake & {
  healthUrl: string
  rendererUrl: string
}

export type LocalRuntimePaths = {
  runtimeDataDir: string
  logDir: string
  runtimeRoot: string
  executablePath: string
  staticDir: string
}

type SpawnRuntime = typeof spawn
type FetchRuntime = typeof fetch

export type LocalRuntimeManagerOptions = {
  userDataPath?: string
  resourcesPath?: string
  executablePath?: string
  spawnRuntime?: SpawnRuntime
  fetchRuntime?: FetchRuntime
  createSecrets?: () => LocalRuntimeBootstrapSecrets
  startupTimeoutMs?: number
  healthPollMs?: number
  shutdownTimeoutMs?: number
  maxRestarts?: number
  initialBackoffMs?: number
  desktopSessionRenewalMs?: number
  desktopSessionRetryMs?: number
  onEndpoint?: (endpoint: LocalRuntimeEndpoint) => void | Promise<void>
  onUnavailable?: (error: Error) => void
  skipRuntimeVerification?: boolean
}

const DEFAULT_STARTUP_TIMEOUT_MS = 30_000
const DEFAULT_HEALTH_POLL_MS = 250
const DEFAULT_SHUTDOWN_TIMEOUT_MS = 5_000
const DEFAULT_DESKTOP_SESSION_RENEWAL_MS = 30 * 60 * 1_000
const DEFAULT_DESKTOP_SESSION_RETRY_MS = 5_000

let verifiedRuntimeEndpoint: LocalRuntimeEndpoint | null = null

export function getVerifiedRuntimeEndpoint(): LocalRuntimeEndpoint | null {
  return verifiedRuntimeEndpoint
}

export function clearVerifiedRuntimeEndpoint(): void {
  verifiedRuntimeEndpoint = null
}

export function shouldStartManagedLocalRuntime(): boolean {
  const mode = process.env.HARNESS_DESKTOP_RUNTIME_MODE
  if (mode === 'remote') return false
  if (app.isPackaged) return mode !== 'dev'
  return mode === 'local' || Boolean(process.env.HARNESSD_DEV_EXECUTABLE)
}

export function resolveLocalRuntimePaths(options: Pick<LocalRuntimeManagerOptions, 'userDataPath' | 'resourcesPath' | 'executablePath'> = {}): LocalRuntimePaths {
  const userDataPath = options.userDataPath || app.getPath('userData')
  const resourcesPath = options.resourcesPath || process.resourcesPath || path.resolve(__dirname, '..', '..')
  const executableName = process.platform === 'win32' ? 'harnessd.exe' : 'harnessd'
  const configuredExecutable = options.executablePath || process.env.HARNESSD_DEV_EXECUTABLE
  const runtimeRoot = configuredExecutable
    ? resolveConfiguredRuntimeRoot(configuredExecutable)
    : path.join(resourcesPath, 'runtime', process.platform, process.arch)
  return {
    runtimeDataDir: path.join(userDataPath, 'runtime'),
    logDir: path.join(userDataPath, 'runtime', 'logs'),
    runtimeRoot,
    executablePath: configuredExecutable || resolveManifestExecutable(runtimeRoot, executableName),
    staticDir: process.env.HARNESSD_STATIC_DIR || path.join(resourcesPath, 'renderer'),
  }
}

export class LocalRuntimeManager {
  private readonly options: Required<Pick<LocalRuntimeManagerOptions,
    'spawnRuntime' | 'fetchRuntime' | 'createSecrets' | 'startupTimeoutMs' | 'healthPollMs' |
    'shutdownTimeoutMs' | 'maxRestarts' | 'initialBackoffMs' | 'desktopSessionRenewalMs' |
    'desktopSessionRetryMs'>> & LocalRuntimeManagerOptions
  private readonly paths: LocalRuntimePaths
  private child: ChildProcessWithoutNullStreams | null = null
  private stopping = false
  private restartCount = 0
  private restartTimer: ReturnType<typeof setTimeout> | null = null
  private secrets: LocalRuntimeBootstrapSecrets | null = null
  private expectedRuntime: { version: string; checksum: string } | null = null
  private desktopCookieSession: Electron.Session | null = null
  private desktopSessionRenewalTimer: ReturnType<typeof setTimeout> | null = null
  private desktopSessionGeneration = 0
  private desktopSessionRenewalInFlight: {
    generation: number
    promise: Promise<void>
  } | null = null

  constructor(options: LocalRuntimeManagerOptions = {}) {
    this.options = {
      ...options,
      spawnRuntime: options.spawnRuntime || spawn,
      fetchRuntime: options.fetchRuntime || fetch,
      createSecrets: options.createSecrets || createLocalRuntimeBootstrapSecrets,
      startupTimeoutMs: options.startupTimeoutMs ?? DEFAULT_STARTUP_TIMEOUT_MS,
      healthPollMs: options.healthPollMs ?? DEFAULT_HEALTH_POLL_MS,
      shutdownTimeoutMs: options.shutdownTimeoutMs ?? DEFAULT_SHUTDOWN_TIMEOUT_MS,
      maxRestarts: options.maxRestarts ?? 3,
      initialBackoffMs: options.initialBackoffMs ?? 500,
      desktopSessionRenewalMs: options.desktopSessionRenewalMs ?? DEFAULT_DESKTOP_SESSION_RENEWAL_MS,
      desktopSessionRetryMs: options.desktopSessionRetryMs ?? DEFAULT_DESKTOP_SESSION_RETRY_MS,
    }
    this.paths = resolveLocalRuntimePaths(options)
  }

  get endpoint(): LocalRuntimeEndpoint | null {
    return verifiedRuntimeEndpoint
  }

  get runtimePaths(): LocalRuntimePaths {
    return { ...this.paths }
  }

  async start(): Promise<LocalRuntimeEndpoint> {
    this.stopping = false
    this.restartCount = 0
    this.expectedRuntime = this.options.skipRuntimeVerification || process.env.HARNESSD_DEV_EXECUTABLE
      ? null
      : verifyPackagedRuntime(this.paths)
    let lastError: Error | null = null
    for (let attempt = 0; attempt <= this.options.maxRestarts; attempt += 1) {
      try {
        return await this.startChild()
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error))
        if (attempt >= this.options.maxRestarts || this.stopping) break
        await delay(this.options.initialBackoffMs * (2 ** attempt))
      }
    }
    throw lastError || new Error('harnessd failed to start')
  }

  async installDesktopSession(cookieSession: Electron.Session): Promise<void> {
    this.clearDesktopSessionRenewal()
    this.desktopCookieSession = cookieSession
    this.desktopSessionGeneration += 1
    await this.renewDesktopSession()
  }

  async renewDesktopSession(): Promise<void> {
    const cookieSession = this.desktopCookieSession
    if (!cookieSession || this.stopping) throw new Error('desktop cookie session is unavailable')
    const generation = this.desktopSessionGeneration
    const inFlight = this.desktopSessionRenewalInFlight
    if (inFlight?.generation === generation) return inFlight.promise

    const promise = this.refreshDesktopSession(cookieSession, generation)
    this.desktopSessionRenewalInFlight = { generation, promise }
    try {
      await promise
    } finally {
      if (this.desktopSessionRenewalInFlight?.promise === promise) {
        this.desktopSessionRenewalInFlight = null
      }
    }
  }

  private async refreshDesktopSession(
    cookieSession: Electron.Session,
    generation: number,
  ): Promise<void> {
    const endpoint = this.requireEndpoint()
    const bootstrapToken = this.secrets?.desktop_bootstrap_token
    if (!bootstrapToken) throw new Error('desktop bootstrap secret is unavailable')

    const response = await this.options.fetchRuntime(new URL(endpoint.desktop_session_path, endpoint.origin), {
      method: 'POST',
      headers: { 'X-Harness-Desktop-Bootstrap': bootstrapToken },
      redirect: 'error',
    })
    if (response.status !== 204) {
      throw new Error(`desktop session bootstrap failed: ${response.status}`)
    }
    const setCookie = response.headers.get('set-cookie')
    if (!setCookie) throw new Error('desktop session bootstrap did not return a cookie')
    const cookie = parseSetCookie(setCookie)
    if (generation !== this.desktopSessionGeneration || endpoint !== verifiedRuntimeEndpoint || this.stopping) return
    await cookieSession.cookies.set({
      url: endpoint.origin,
      name: cookie.name,
      value: cookie.value,
      httpOnly: true,
      secure: endpoint.origin.startsWith('https:'),
      sameSite: 'strict',
      path: cookie.path,
    })
    if (generation === this.desktopSessionGeneration && endpoint === verifiedRuntimeEndpoint && !this.stopping) {
      this.scheduleDesktopSessionRenewal(generation, this.options.desktopSessionRenewalMs)
    }
  }

  async getModelStatus(): Promise<LocalRuntimeModelStatus> {
    const endpoint = this.requireEndpoint()
    const response = await this.options.fetchRuntime(new URL('/api/local-runtime/model', endpoint.origin), {
      redirect: 'error',
    })
    if (!response.ok) throw new Error(`model status request failed: ${response.status}`)
    return validateModelStatus(await response.json())
  }

  async applyModelApiKey(value: string): Promise<LocalRuntimeModelStatus> {
    return this.writeModelKey('PUT', value)
  }

  async saveModelConfiguration(input: LocalRuntimeModelConfigInput): Promise<LocalRuntimeModelStatus> {
    const endpoint = this.requireEndpoint()
    const response = await this.options.fetchRuntime(new URL('/api/local-runtime/model-config', endpoint.origin), {
      method: 'PUT',
      headers: this.bootstrapHeaders(true),
      body: JSON.stringify({
        base_url: input.baseUrl,
        model: input.model,
        ...(input.models ? { models: input.models } : {}),
        ...(Object.prototype.hasOwnProperty.call(input, 'apiKey') ? { api_key: input.apiKey } : {}),
      }),
      redirect: 'error',
    })
    if (!response.ok) throw await modelRequestError(response, 'model configuration request failed')
    validateModelConfiguration(await response.json())
    return this.getModelStatus()
  }

  async discoverModels(input: LocalRuntimeModelDiscoveryInput): Promise<LocalRuntimeModelDiscovery> {
    const endpoint = this.requireEndpoint()
    const response = await this.options.fetchRuntime(new URL('/api/local-runtime/model-discovery', endpoint.origin), {
      method: 'POST',
      headers: this.bootstrapHeaders(true),
      body: JSON.stringify({
        base_url: input.baseUrl,
        ...(Object.prototype.hasOwnProperty.call(input, 'apiKey') ? { api_key: input.apiKey } : {}),
      }),
      redirect: 'error',
    })
    if (!response.ok) throw await modelRequestError(response, 'model discovery request failed')
    return validateModelDiscovery(await response.json())
  }

  async deleteModelApiKey(): Promise<LocalRuntimeModelStatus> {
    return this.writeModelKey('DELETE')
  }

  async openWebExtension(): Promise<void> {
    const endpoint = this.requireEndpoint()
    const bootstrapToken = this.secrets?.desktop_bootstrap_token
    if (!bootstrapToken) throw new Error('desktop bootstrap secret is unavailable')
    const response = await this.options.fetchRuntime(new URL('/api/local-runtime/web-bootstrap', endpoint.origin), {
      method: 'POST',
      headers: { 'X-Harness-Desktop-Bootstrap': bootstrapToken },
      redirect: 'error',
    })
    if (!response.ok) throw new Error(`Web extension bootstrap failed: ${response.status}`)
    const body = await response.json() as { token?: unknown }
    if (typeof body.token !== 'string' || !body.token) throw new Error('Web extension bootstrap returned no token')
    const url = `${endpoint.rendererUrl}#bootstrap=${encodeURIComponent(body.token)}`
    await shell.openExternal(url)
  }

  async stop(): Promise<void> {
    this.stopping = true
    clearVerifiedRuntimeEndpoint()
    this.secrets = null
    this.desktopSessionGeneration += 1
    this.desktopCookieSession = null
    this.clearDesktopSessionRenewal()
    if (this.restartTimer) {
      clearTimeout(this.restartTimer)
      this.restartTimer = null
    }
    const child = this.child
    this.child = null
    if (!child || child.exitCode !== null) return

    child.kill('SIGTERM')
    const exited = await waitForExit(child, this.options.shutdownTimeoutMs)
    if (!exited && child.exitCode === null) {
      child.kill('SIGKILL')
      await waitForExit(child, 1_000)
    }
  }

  private async startChild(): Promise<LocalRuntimeEndpoint> {
    ensureRuntimeDirectories(this.paths)
    assertExecutable(this.paths.executablePath)
    this.secrets = this.options.createSecrets()
    const child = this.options.spawnRuntime(this.paths.executablePath, [
      '--port', '0',
      '--static-dir', this.paths.staticDir,
    ], {
      env: minimalRuntimeEnvironment(),
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    })
    // The packaged runtime logs to stderr. Leaving this pipe unread eventually
    // blocks every request on Python's logging lock once the OS buffer fills.
    child.stderr.resume()
    this.child = child
    const endpointPromise = this.waitForReady(child)
    child.stdin.end(`${JSON.stringify({
      protocol_version: 1,
      runtime_data_dir: this.paths.runtimeDataDir,
      ...this.secrets,
    })}\n`)

    try {
      const endpoint = await endpointPromise
      this.assertRuntimeIdentity(endpoint)
      await this.pollHealth(endpoint, child)
      verifiedRuntimeEndpoint = endpoint
      await this.options.onEndpoint?.(endpoint)
      child.once('exit', (code, signal) => this.handleUnexpectedExit(child, code, signal))
      return endpoint
    } catch (error) {
      clearVerifiedRuntimeEndpoint()
      if (this.child === child) this.child = null
      await terminateChild(child, this.options.shutdownTimeoutMs)
      throw error
    }
  }

  private waitForReady(child: ChildProcessWithoutNullStreams): Promise<LocalRuntimeEndpoint> {
    return new Promise((resolve, reject) => {
      let stdoutBuffer = ''
      let readySeen = false
      const timeout = setTimeout(() => finish(new Error('harnessd ready handshake timed out')), this.options.startupTimeoutMs)
      const finish = (error?: Error, endpoint?: LocalRuntimeEndpoint) => {
        clearTimeout(timeout)
        child.stdout.off('data', onData)
        child.stdout.resume()
        child.off('error', onError)
        child.off('exit', onEarlyExit)
        if (error) reject(error)
        else resolve(endpoint as LocalRuntimeEndpoint)
      }
      const onError = (error: Error) => finish(error)
      const onEarlyExit = (code: number | null, signal: NodeJS.Signals | null) => {
        finish(new Error(`harnessd exited before ready (${code ?? signal ?? 'unknown'})`))
      }
      const onData = (chunk: Buffer | string) => {
        stdoutBuffer += chunk.toString()
        let newline = stdoutBuffer.indexOf('\n')
        while (newline >= 0) {
          const line = stdoutBuffer.slice(0, newline).trimEnd()
          stdoutBuffer = stdoutBuffer.slice(newline + 1)
          if (line.startsWith('{')) {
            if (readySeen) return finish(new Error('harnessd emitted more than one ready handshake'))
            readySeen = true
            try {
              finish(undefined, validateReadyHandshake(line))
            } catch (error) {
              finish(error instanceof Error ? error : new Error(String(error)))
            }
            return
          }
          newline = stdoutBuffer.indexOf('\n')
        }
      }
      child.stdout.on('data', onData)
      child.once('error', onError)
      child.once('exit', onEarlyExit)
    })
  }

  private async pollHealth(endpoint: LocalRuntimeEndpoint, child: ChildProcessWithoutNullStreams): Promise<void> {
    const deadline = Date.now() + this.options.startupTimeoutMs
    let lastError = 'not ready'
    while (Date.now() < deadline && child.exitCode === null) {
      try {
        const response = await this.options.fetchRuntime(endpoint.healthUrl, { redirect: 'error' })
        const body = await response.json() as {
          ready?: boolean
          runtime_ready?: boolean
          status?: string
          runtime_profile?: string
        }
        const legacyReady = body.runtime_ready === true
        const localProfileReady = body.status === 'ok' && body.runtime_profile === 'local'
        if (response.ok && (legacyReady || localProfileReady)) return
        lastError = `HTTP ${response.status}`
      } catch (error) {
        lastError = error instanceof Error ? error.message : String(error)
      }
      await delay(this.options.healthPollMs)
    }
    throw new Error(`harnessd health check timed out: ${lastError}`)
  }

  private handleUnexpectedExit(child: ChildProcessWithoutNullStreams, code: number | null, signal: NodeJS.Signals | null): void {
    if (this.stopping || child !== this.child) return
    this.child = null
    clearVerifiedRuntimeEndpoint()
    this.desktopSessionGeneration += 1
    this.clearDesktopSessionRenewal()
    if (this.restartCount >= this.options.maxRestarts) {
      this.options.onUnavailable?.(new Error(`harnessd restart limit reached (${code ?? signal ?? 'unknown'})`))
      return
    }
    const delayMs = this.options.initialBackoffMs * (2 ** this.restartCount)
    this.restartCount += 1
    this.restartTimer = setTimeout(() => {
      this.restartTimer = null
      void this.startChild().catch((error: unknown) => {
        this.scheduleRestartAfterFailure(error instanceof Error ? error : new Error(String(error)))
      })
    }, delayMs)
  }

  private scheduleRestartAfterFailure(error: Error): void {
    if (this.stopping) return
    if (this.restartCount >= this.options.maxRestarts) {
      this.options.onUnavailable?.(error)
      return
    }
    const delayMs = this.options.initialBackoffMs * (2 ** this.restartCount)
    this.restartCount += 1
    this.restartTimer = setTimeout(() => {
      this.restartTimer = null
      void this.startChild().catch((nextError: unknown) => {
        this.scheduleRestartAfterFailure(nextError instanceof Error ? nextError : new Error(String(nextError)))
      })
    }, delayMs)
  }

  private scheduleDesktopSessionRenewal(generation: number, delayMs: number): void {
    if (this.stopping || generation !== this.desktopSessionGeneration || !this.desktopCookieSession) return
    this.clearDesktopSessionRenewal()
    this.desktopSessionRenewalTimer = setTimeout(() => {
      this.desktopSessionRenewalTimer = null
      if (this.stopping || generation !== this.desktopSessionGeneration) return
      void this.renewDesktopSession().catch((error: unknown) => {
        if (this.stopping || generation !== this.desktopSessionGeneration) return
        const message = error instanceof Error ? error.message : String(error)
        console.error(`Harness desktop session renewal failed: ${message}`)
        this.scheduleDesktopSessionRenewal(generation, this.options.desktopSessionRetryMs)
      })
    }, Math.max(1, delayMs))
    this.desktopSessionRenewalTimer.unref?.()
  }

  private clearDesktopSessionRenewal(): void {
    if (!this.desktopSessionRenewalTimer) return
    clearTimeout(this.desktopSessionRenewalTimer)
    this.desktopSessionRenewalTimer = null
  }

  private async writeModelKey(method: 'PUT' | 'DELETE', value?: string): Promise<LocalRuntimeModelStatus> {
    const endpoint = this.requireEndpoint()
    const response = await this.options.fetchRuntime(new URL('/api/local-runtime/model-key', endpoint.origin), {
      method,
      headers: {
        ...this.bootstrapHeaders(method === 'PUT'),
        ...(method === 'PUT' ? { 'Content-Type': 'application/json' } : {}),
      },
      ...(method === 'PUT' ? { body: JSON.stringify({ api_key: value }) } : {}),
      redirect: 'error',
    })
    if (!response.ok) throw new Error(`model key update failed: ${response.status}`)
    return this.getModelStatus()
  }

  private bootstrapHeaders(json = false): Record<string, string> {
    const bootstrapToken = this.secrets?.desktop_bootstrap_token
    if (!bootstrapToken) throw new Error('desktop bootstrap secret is unavailable')
    return {
      'X-Harness-Desktop-Bootstrap': bootstrapToken,
      ...(json ? { 'Content-Type': 'application/json' } : {}),
    }
  }

  private requireEndpoint(): LocalRuntimeEndpoint {
    const endpoint = verifiedRuntimeEndpoint
    if (!endpoint) throw new Error('harnessd endpoint is unavailable')
    return endpoint
  }

  private assertRuntimeIdentity(endpoint: LocalRuntimeEndpoint): void {
    if (!this.expectedRuntime) return
    if (endpoint.runtime_version !== this.expectedRuntime.version) {
      throw new Error('harnessd ready version does not match the packaged runtime manifest')
    }
  }
}

function validateModelStatus(value: unknown): LocalRuntimeModelStatus {
  if (!isRecord(value)
    || !['setup_required', 'configured', 'healthy', 'error'].includes(String(value.state))
    || typeof value.provider !== 'string'
    || typeof value.model !== 'string'
    || typeof value.base_url !== 'string'
    || !['persistent', 'session', 'unavailable'].includes(String(value.secret_storage))
    || (value.message !== undefined && value.message !== null && typeof value.message !== 'string')) {
    throw new Error('harnessd returned an invalid model status')
  }
  return value as LocalRuntimeModelStatus
}

function validateModelConfiguration(value: unknown): {
  state: 'configured' | 'setup_required'
  base_url: string
  model: string
} {
  if (!isRecord(value)
    || !['configured', 'setup_required'].includes(String(value.state))
    || typeof value.base_url !== 'string'
    || typeof value.model !== 'string') {
    throw new Error('harnessd returned an invalid model configuration')
  }
  return value as { state: 'configured' | 'setup_required'; base_url: string; model: string }
}

function validateModelDiscovery(value: unknown): LocalRuntimeModelDiscovery {
  if (!isRecord(value)
    || !Array.isArray(value.models)
    || value.models.some((model) => typeof model !== 'string' || !model)
    || !Number.isInteger(value.latency_ms)
    || Number(value.latency_ms) < 0) {
    throw new Error('harnessd returned an invalid model discovery response')
  }
  const latencyMs = Number(value.latency_ms)
  return { models: value.models as string[], durationMs: latencyMs, latencyMs }
}

async function modelRequestError(response: Response, fallback: string): Promise<Error> {
  try {
    const body = await response.json() as unknown
    if (isRecord(body) && isRecord(body.detail)
      && isModelErrorCode(body.detail.code)
      && typeof body.detail.message === 'string') {
      return new LocalRuntimeModelRequestError(body.detail.code, body.detail.message, response.status)
    }
  } catch {
    // Fall back to an HTTP-only error without exposing an upstream response body.
  }
  return new Error(`${fallback}: ${response.status}`)
}

function isModelErrorCode(value: unknown): value is LocalRuntimeModelErrorCode {
  return typeof value === 'string' && MODEL_ERROR_CODES.has(value as LocalRuntimeModelErrorCode)
}

const MODEL_ERROR_CODES = new Set<LocalRuntimeModelErrorCode>([
  'INVALID_MODEL_BASE_URL',
  'INVALID_MODEL_ID',
  'INVALID_MODEL_CATALOG',
  'MODEL_API_KEY_REQUIRED',
  'MODEL_DISCOVERY_AUTH_ERROR',
  'MODEL_DISCOVERY_TIMEOUT',
  'MODEL_DISCOVERY_UPSTREAM_ERROR',
  'MODEL_DISCOVERY_RESPONSE_TOO_LARGE',
  'MODEL_DISCOVERY_INVALID_RESPONSE',
])

export function validateReadyHandshake(raw: string): LocalRuntimeEndpoint {
  let value: unknown
  try {
    value = JSON.parse(raw)
  } catch {
    throw new Error('harnessd ready handshake is not valid JSON')
  }
  if (!isRecord(value) || value.protocol_version !== 1) throw new Error('unsupported harnessd ready protocol')
  const origin = requireString(value, 'origin')
  const parsedOrigin = new URL(origin)
  if (parsedOrigin.protocol !== 'http:' || parsedOrigin.hostname !== '127.0.0.1' || parsedOrigin.port === '') {
    throw new Error('harnessd ready origin must be an explicit 127.0.0.1 HTTP port')
  }
  if (parsedOrigin.pathname !== '/' || parsedOrigin.search || parsedOrigin.hash || parsedOrigin.username || parsedOrigin.password) {
    throw new Error('harnessd ready origin must not contain credentials or a path')
  }
  const healthPath = requireAbsolutePath(value, 'health_path')
  const rendererPath = requireAbsolutePath(value, 'renderer_path')
  const desktopSessionPath = requireAbsolutePath(value, 'desktop_session_path')
  const handshake: HarnessdReadyHandshake = {
    protocol_version: 1,
    origin: parsedOrigin.origin,
    health_path: healthPath,
    desktop_session_path: desktopSessionPath,
    renderer_path: rendererPath,
    runtime_version: requireString(value, 'runtime_version'),
    ...(typeof value.runtime_checksum === 'string' ? { runtime_checksum: value.runtime_checksum } : {}),
  }
  return {
    ...handshake,
    healthUrl: new URL(healthPath, handshake.origin).toString(),
    rendererUrl: new URL(rendererPath, handshake.origin).toString(),
  }
}

function ensureRuntimeDirectories(paths: LocalRuntimePaths): void {
  fs.mkdirSync(paths.runtimeDataDir, { recursive: true, mode: 0o700 })
  fs.mkdirSync(paths.logDir, { recursive: true, mode: 0o700 })
}

function assertExecutable(executablePath: string): void {
  if (!fs.existsSync(executablePath)) throw new Error(`packaged harnessd is missing: ${executablePath}`)
}

function verifyPackagedRuntime(paths: LocalRuntimePaths): { version: string; checksum: string } {
  const manifestPath = path.join(paths.runtimeRoot, 'runtime-manifest.json')
  let manifest: unknown
  try {
    manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'))
  } catch {
    throw new Error(`packaged harnessd manifest is missing or invalid: ${manifestPath}`)
  }
  if (!isRecord(manifest)
    || (manifest.schema_version !== 1 && manifest.schema_version !== 2)
    || typeof manifest.runtime_version !== 'string'
    || manifest.platform !== process.platform
    || manifest.architecture !== process.arch
    || typeof manifest.executable !== 'string'
    || resolveRuntimePath(paths.runtimeRoot, manifest.executable) !== paths.executablePath
    || typeof manifest.sha256 !== 'string'
    || !/^[a-f0-9]{64}$/.test(manifest.sha256)) {
    throw new Error('packaged harnessd manifest schema is invalid')
  }
  const checksum = manifest.schema_version === 2
    ? verifyRuntimeTree(paths.runtimeRoot, manifest, manifestPath)
    : hashFile(paths.executablePath)
  if (checksum !== manifest.sha256) throw new Error('packaged harnessd checksum verification failed')
  return { version: manifest.runtime_version, checksum }
}

function resolveManifestExecutable(runtimeRoot: string, fallbackName: string): string {
  const manifestPath = path.join(runtimeRoot, 'runtime-manifest.json')
  try {
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8')) as unknown
    if (isRecord(manifest) && typeof manifest.executable === 'string') {
      return resolveRuntimePath(runtimeRoot, manifest.executable)
    }
  } catch (error) {
    if (error instanceof Error && error.message.includes('manifest path is invalid')) throw error
  }
  return path.join(runtimeRoot, fallbackName)
}

function resolveConfiguredRuntimeRoot(executablePath: string): string {
  const executableDirectory = path.dirname(executablePath)
  const candidates = [executableDirectory, path.dirname(executableDirectory)]
  return candidates.find((candidate) => fs.existsSync(path.join(candidate, 'runtime-manifest.json')))
    || executableDirectory
}

function verifyRuntimeTree(runtimeRoot: string, manifest: Record<string, unknown>, manifestPath: string): string {
  if (!isRecord(manifest.files)) throw new Error('packaged harnessd manifest schema is invalid')
  const expected = new Map<string, string>()
  for (const [relativePath, checksum] of Object.entries(manifest.files)) {
    if (typeof checksum !== 'string' || !/^[a-f0-9]{64}$/.test(checksum)) {
      throw new Error('packaged harnessd manifest schema is invalid')
    }
    resolveRuntimePath(runtimeRoot, relativePath)
    expected.set(relativePath, checksum)
  }
  if (typeof manifest.executable !== 'string'
    || expected.get(manifest.executable) !== manifest.sha256) {
    throw new Error('packaged harnessd manifest schema is invalid')
  }

  const actual = listRuntimeFiles(runtimeRoot, manifestPath)
  for (const relativePath of expected.keys()) {
    if (!actual.has(relativePath)) throw new Error(`packaged harnessd file is missing: ${relativePath}`)
  }
  for (const relativePath of actual) {
    if (!expected.has(relativePath)) throw new Error(`packaged harnessd file is not in the manifest: ${relativePath}`)
  }
  let executableChecksum = ''
  for (const [relativePath, checksum] of expected) {
    const actualChecksum = hashFile(resolveRuntimePath(runtimeRoot, relativePath))
    if (actualChecksum !== checksum) {
      throw new Error(`packaged harnessd checksum verification failed: ${relativePath}`)
    }
    if (relativePath === manifest.executable) executableChecksum = actualChecksum
  }
  return executableChecksum
}

function listRuntimeFiles(runtimeRoot: string, manifestPath: string): Set<string> {
  const files = new Set<string>()
  const visit = (directory: string) => {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const absolutePath = path.join(directory, entry.name)
      if (entry.isSymbolicLink()) throw new Error(`packaged harnessd symlink is not allowed: ${absolutePath}`)
      if (entry.isDirectory()) {
        visit(absolutePath)
      } else if (entry.isFile() && absolutePath !== manifestPath) {
        files.add(path.relative(runtimeRoot, absolutePath).split(path.sep).join('/'))
      }
    }
  }
  visit(runtimeRoot)
  return files
}

function resolveRuntimePath(runtimeRoot: string, relativePath: string): string {
  if (!relativePath
    || relativePath.includes('\\')
    || path.posix.isAbsolute(relativePath)
    || path.posix.normalize(relativePath) !== relativePath
    || relativePath.split('/').some((part) => part === '' || part === '.' || part === '..')) {
    throw new Error(`packaged harnessd manifest path is invalid: ${relativePath}`)
  }
  const resolved = path.resolve(runtimeRoot, ...relativePath.split('/'))
  if (resolved === runtimeRoot || !resolved.startsWith(`${runtimeRoot}${path.sep}`)) {
    throw new Error(`packaged harnessd manifest path is invalid: ${relativePath}`)
  }
  return resolved
}

function hashFile(filePath: string): string {
  return createHash('sha256').update(fs.readFileSync(filePath)).digest('hex')
}

function minimalRuntimeEnvironment(): NodeJS.ProcessEnv {
  const allowed = ['PATH', 'SystemRoot', 'WINDIR', 'TMP', 'TEMP', 'TMPDIR', 'LANG', 'LC_ALL']
  return Object.fromEntries(allowed.flatMap((key) => process.env[key] ? [[key, process.env[key]]] : []))
}

function requireString(value: Record<string, unknown>, key: string): string {
  const result = value[key]
  if (typeof result !== 'string' || !result.trim()) throw new Error(`harnessd ready handshake is missing ${key}`)
  return result
}

function requireAbsolutePath(value: Record<string, unknown>, key: string): string {
  const result = requireString(value, key)
  if (!result.startsWith('/') || result.startsWith('//')) throw new Error(`harnessd ready ${key} is invalid`)
  return result
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function parseSetCookie(header: string): { name: string; value: string; path: string } {
  const [pair, ...attributes] = header.split(';').map((part) => part.trim())
  const separator = pair.indexOf('=')
  if (separator <= 0) throw new Error('desktop session cookie is malformed')
  const pathAttribute = attributes.find((attribute) => attribute.toLowerCase().startsWith('path='))
  return {
    name: pair.slice(0, separator),
    value: pair.slice(separator + 1),
    path: pathAttribute?.slice(5) || '/',
  }
}

function waitForExit(child: ChildProcessWithoutNullStreams, timeoutMs: number): Promise<boolean> {
  if (child.exitCode !== null) return Promise.resolve(true)
  return new Promise((resolve) => {
    const timeout = setTimeout(() => {
      child.off('exit', onExit)
      resolve(false)
    }, timeoutMs)
    const onExit = () => {
      clearTimeout(timeout)
      resolve(true)
    }
    child.once('exit', onExit)
  })
}

async function terminateChild(child: ChildProcessWithoutNullStreams, timeoutMs: number): Promise<void> {
  if (child.exitCode !== null) return
  child.kill('SIGTERM')
  const exited = await waitForExit(child, timeoutMs)
  if (!exited && child.exitCode === null) {
    child.kill('SIGKILL')
    await waitForExit(child, 1_000)
  }
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
