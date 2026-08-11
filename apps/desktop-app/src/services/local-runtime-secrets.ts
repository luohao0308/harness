import { app, ipcMain, safeStorage } from 'electron'
import { randomBytes } from 'node:crypto'
import * as fs from 'node:fs'
import * as path from 'node:path'
import type {
  LocalRuntimeModelConfigInput,
  LocalRuntimeModelDiscovery,
  LocalRuntimeModelDiscoveryInput,
  LocalRuntimeModelStatus,
} from '../preload-api'
import { captureIpcResult } from '../shared/ipc-result'

type PersistedSecrets = {
  schemaVersion: 2
  vaultKey?: string
  modelApiKey?: string
  modelBaseUrl?: string
  modelName?: string
}

export type LocalRuntimeSecretStatus = {
  persistentStorageAvailable: boolean
  modelKeyConfigured: boolean
  modelKeyStorage: 'persistent' | 'session' | 'none'
}

export type LocalRuntimeBootstrapSecrets = {
  session_signing_secret: string
  vault_encryption_secret: string
  desktop_bootstrap_token: string
  model_api_key?: string
  model_base_url?: string
  model_name?: string
  persistent_secret_storage: boolean
}

const SECRET_SCHEMA_VERSION = 2
const sessionSecrets = new Map<'vaultKey' | 'modelApiKey', string>()
let handlersRegistered = false
let trustedRuntimeOrigin: string | null = null

export function setTrustedRuntimeSecretOrigin(origin: string | null): void {
  trustedRuntimeOrigin = origin
}

export function getLocalRuntimeSecretStatus(): LocalRuntimeSecretStatus {
  const persisted = readPersistedSecrets()
  const persistentStorageAvailable = encryptionAvailable()
  const hasPersistentModelKey = Boolean(persisted.modelApiKey && persistentStorageAvailable)
  const hasSessionModelKey = sessionSecrets.has('modelApiKey')
  return {
    persistentStorageAvailable,
    modelKeyConfigured: hasPersistentModelKey || hasSessionModelKey,
    modelKeyStorage: hasPersistentModelKey ? 'persistent' : hasSessionModelKey ? 'session' : 'none',
  }
}

export function setLocalRuntimeModelApiKey(value: string): LocalRuntimeSecretStatus {
  const modelApiKey = value.trim()
  if (!modelApiKey) throw new Error('model API key is required')

  if (!encryptionAvailable()) {
    sessionSecrets.set('modelApiKey', modelApiKey)
    return getLocalRuntimeSecretStatus()
  }

  const persisted = readPersistedSecrets()
  persisted.modelApiKey = encrypt(modelApiKey)
  writePersistedSecrets(persisted)
  sessionSecrets.delete('modelApiKey')
  return getLocalRuntimeSecretStatus()
}

export function persistLocalRuntimeModelConfiguration(
  status: LocalRuntimeModelStatus,
  input: Pick<LocalRuntimeModelConfigInput, 'apiKey'>,
): LocalRuntimeSecretStatus {
  const persisted = readPersistedSecrets()
  persisted.modelBaseUrl = status.base_url
  persisted.modelName = status.model

  if (Object.prototype.hasOwnProperty.call(input, 'apiKey')) {
    const modelApiKey = input.apiKey?.trim() || ''
    if (modelApiKey) {
      if (encryptionAvailable()) {
        persisted.modelApiKey = encrypt(modelApiKey)
        sessionSecrets.delete('modelApiKey')
      } else {
        delete persisted.modelApiKey
        sessionSecrets.set('modelApiKey', modelApiKey)
      }
    } else {
      delete persisted.modelApiKey
      sessionSecrets.delete('modelApiKey')
    }
  }

  writePersistedSecrets(persisted)
  return getLocalRuntimeSecretStatus()
}

export function createLocalRuntimeBootstrapSecrets(): LocalRuntimeBootstrapSecrets {
  const persistent = encryptionAvailable()
  const persisted = readPersistedSecrets()
  let vaultKey = persistent ? decrypt(persisted.vaultKey) : sessionSecrets.get('vaultKey')

  if (!vaultKey) {
    vaultKey = randomSecret()
    if (persistent) {
      persisted.vaultKey = encrypt(vaultKey)
      writePersistedSecrets(persisted)
    } else {
      sessionSecrets.set('vaultKey', vaultKey)
    }
  }

  const modelApiKey = persistent
    ? decrypt(persisted.modelApiKey)
    : sessionSecrets.get('modelApiKey')

  return {
    session_signing_secret: randomSecret(),
    vault_encryption_secret: vaultKey,
    desktop_bootstrap_token: randomSecret(),
    ...(modelApiKey ? { model_api_key: modelApiKey } : {}),
    ...(persisted.modelBaseUrl ? { model_base_url: persisted.modelBaseUrl } : {}),
    ...(persisted.modelName ? { model_name: persisted.modelName } : {}),
    persistent_secret_storage: persistent,
  }
}

export function registerLocalRuntimeSecretHandlers(options: {
  getModelStatus?: () => Promise<LocalRuntimeModelStatus>
  saveModelConfiguration?: (input: LocalRuntimeModelConfigInput) => Promise<LocalRuntimeModelStatus>
  discoverModels?: (input: LocalRuntimeModelDiscoveryInput) => Promise<LocalRuntimeModelDiscovery>
  applyModelApiKey?: (value: string) => Promise<LocalRuntimeModelStatus>
  deleteModelApiKey?: () => Promise<LocalRuntimeModelStatus>
  renewSession?: () => Promise<void>
  openWebExtension?: () => Promise<void>
} = {}): void {
  if (handlersRegistered) return
  handlersRegistered = true
  ipcMain.handle('local-runtime:get-model-status', async (event) => {
    assertTrustedSecretSender(event)
    return captureIpcResult(async () => {
      if (!options.getModelStatus) throw new Error('managed local runtime is unavailable')
      return options.getModelStatus()
    })
  })
  ipcMain.handle('local-runtime:save-model-configuration', async (event, value: unknown) => {
    assertTrustedSecretSender(event)
    return captureIpcResult(async () => {
      if (!options.saveModelConfiguration) throw new Error('managed local runtime is unavailable')
      const input = validateModelConfigInput(value)
      const status = await options.saveModelConfiguration(input)
      persistLocalRuntimeModelConfiguration(status, input)
      return status
    })
  })
  ipcMain.handle('local-runtime:discover-models', async (event, value: unknown) => {
    assertTrustedSecretSender(event)
    return captureIpcResult(async () => {
      if (!options.discoverModels) throw new Error('managed local runtime is unavailable')
      return options.discoverModels(validateModelDiscoveryInput(value))
    })
  })
  ipcMain.handle('local-runtime:set-model-api-key', async (event, value: string) => {
    assertTrustedSecretSender(event)
    return captureIpcResult(async () => {
      if (!options.applyModelApiKey) throw new Error('managed local runtime is unavailable')
      const status = await options.applyModelApiKey(value.trim())
      setLocalRuntimeModelApiKey(value)
      return status
    })
  })
  ipcMain.handle('local-runtime:delete-model-api-key', async (event) => {
    assertTrustedSecretSender(event)
    return captureIpcResult(async () => {
      if (!options.deleteModelApiKey) throw new Error('managed local runtime is unavailable')
      const status = await options.deleteModelApiKey()
      deleteLocalRuntimeModelApiKey()
      return status
    })
  })
  ipcMain.handle('local-runtime:renew-session', async (event) => {
    assertTrustedSecretSender(event)
    return captureIpcResult(async () => {
      if (!options.renewSession) throw new Error('managed local runtime is unavailable')
      await options.renewSession()
    })
  })
  ipcMain.handle('local-runtime:open-web-extension', async (event) => {
    assertTrustedSecretSender(event)
    return captureIpcResult(async () => {
      if (!options.openWebExtension) throw new Error('managed local runtime is unavailable')
      await options.openWebExtension()
    })
  })
}

export function deleteLocalRuntimeModelApiKey(): void {
  sessionSecrets.delete('modelApiKey')
  const persisted = readPersistedSecrets()
  if (!persisted.modelApiKey) return
  delete persisted.modelApiKey
  writePersistedSecrets(persisted)
}

function assertTrustedSecretSender(event: Electron.IpcMainInvokeEvent): void {
  const senderUrl = event.senderFrame?.url || event.sender.getURL()
  try {
    const url = new URL(senderUrl)
    const isRecovery = url.protocol === 'harness-app:' && url.hostname === 'renderer'
    const isRuntime = trustedRuntimeOrigin !== null && url.origin === trustedRuntimeOrigin
    if (isRecovery || isRuntime) return
  } catch {
    // Fall through to a closed IPC boundary.
  }
  throw new Error('local runtime secret IPC is unavailable for this origin')
}

function secretsFilePath(): string {
  return path.join(app.getPath('userData'), 'secrets.json')
}

function readPersistedSecrets(): PersistedSecrets {
  try {
    const parsed = JSON.parse(fs.readFileSync(secretsFilePath(), 'utf8')) as Partial<PersistedSecrets>
    return {
      schemaVersion: SECRET_SCHEMA_VERSION,
      ...(typeof parsed.vaultKey === 'string' ? { vaultKey: parsed.vaultKey } : {}),
      ...(typeof parsed.modelApiKey === 'string' ? { modelApiKey: parsed.modelApiKey } : {}),
      ...(typeof parsed.modelBaseUrl === 'string' ? { modelBaseUrl: parsed.modelBaseUrl } : {}),
      ...(typeof parsed.modelName === 'string' ? { modelName: parsed.modelName } : {}),
    }
  } catch {
    return { schemaVersion: SECRET_SCHEMA_VERSION }
  }
}

function writePersistedSecrets(secrets: PersistedSecrets): void {
  const target = secretsFilePath()
  fs.mkdirSync(path.dirname(target), { recursive: true })
  const temporary = `${target}.${process.pid}.${Date.now()}.tmp`
  fs.writeFileSync(temporary, JSON.stringify(secrets, null, 2), { mode: 0o600 })
  fs.renameSync(temporary, target)
  try {
    fs.chmodSync(target, 0o600)
  } catch {
    // Windows ACLs are owned by the per-user Electron data directory.
  }
}

function encryptionAvailable(): boolean {
  try {
    return Boolean(safeStorage?.isEncryptionAvailable())
  } catch {
    return false
  }
}

function encrypt(value: string): string {
  return safeStorage.encryptString(value).toString('base64')
}

function decrypt(value: string | undefined): string | undefined {
  if (!value || !encryptionAvailable()) return undefined
  try {
    return safeStorage.decryptString(Buffer.from(value, 'base64'))
  } catch {
    return undefined
  }
}

function randomSecret(): string {
  return randomBytes(48).toString('base64url')
}

function validateModelConfigInput(value: unknown): LocalRuntimeModelConfigInput {
  if (!isRecord(value)
    || typeof value.baseUrl !== 'string'
    || typeof value.model !== 'string'
    || (value.apiKey !== undefined && typeof value.apiKey !== 'string')) {
    throw new Error('model configuration input is invalid')
  }
  return {
    baseUrl: value.baseUrl,
    model: value.model,
    ...(value.apiKey !== undefined ? { apiKey: value.apiKey } : {}),
  }
}

function validateModelDiscoveryInput(value: unknown): LocalRuntimeModelDiscoveryInput {
  if (!isRecord(value)
    || typeof value.baseUrl !== 'string'
    || (value.apiKey !== undefined && typeof value.apiKey !== 'string')) {
    throw new Error('model discovery input is invalid')
  }
  return {
    baseUrl: value.baseUrl,
    ...(value.apiKey !== undefined ? { apiKey: value.apiKey } : {}),
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
