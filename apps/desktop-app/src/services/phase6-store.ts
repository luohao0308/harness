import { app, safeStorage } from 'electron'
import * as fs from 'fs'
import * as path from 'path'

export type DesktopProfileMetadata = {
  id: string
  label: string
  apiBaseUrl: string
  dataPath: string
  createdAt: string
  updatedAt: string
  hasCredential: boolean
  credentialStorage: 'persistent' | 'session' | 'none'
}

export type DesktopProfile = DesktopProfileMetadata

type StoredCredential =
  | { kind: 'safeStorage'; encryptedValue: string }
  | { kind: 'reference'; reference: string }

type StoredDesktopProfile = Omit<DesktopProfileMetadata, 'hasCredential' | 'credentialStorage'> & {
  credential?: StoredCredential
  workspaceRoot?: string
}

export type WindowState = {
  width: number
  height: number
  x?: number
  y?: number
  maximized?: boolean
  updatedAt: string
}

export type LocalModelSettings = {
  enabled: boolean
  provider: 'ollama' | 'openai-compatible'
  baseUrl: string
  model: string
  updatedAt: string
}

export type OfflineTask = {
  id: string
  prompt: string
  result: string
  modelSource: 'deterministic-local' | 'local-model'
  status: 'completed' | 'failed'
  createdAt: string
  modelRequested?: boolean
  fallbackReason?: string | null
  durationMs?: number
}

export type Phase6State = {
  schemaVersion: 2
  activeProfileId: string
  profiles: StoredDesktopProfile[]
  windows: Record<string, WindowState>
  localModel: LocalModelSettings
  offlineTasks: OfflineTask[]
  projectKnowledgeGenerations: Record<string, number>
}

const DEFAULT_PROFILE_ID = 'default'
const PHASE6_STATE_SCHEMA_VERSION = 2
const memoryCredentialStore = new Map<string, string>()

const DEFAULT_LOCAL_MODEL: LocalModelSettings = {
  enabled: false,
  provider: 'ollama',
  baseUrl: 'http://127.0.0.1:11434',
  model: 'llama3.1',
  updatedAt: new Date(0).toISOString(),
}

function defaultProfile(now: string): StoredDesktopProfile {
  const profile: StoredDesktopProfile = {
    id: DEFAULT_PROFILE_ID,
    label: '默认工作区',
    apiBaseUrl: process.env.API_BASE_URL || 'http://localhost:8000',
    dataPath: path.join(app.getPath('userData'), 'profiles', DEFAULT_PROFILE_ID),
    createdAt: now,
    updatedAt: now,
  }
  if (process.env.AUTH_TOKEN) {
    profile.credential = credentialForToken(DEFAULT_PROFILE_ID, process.env.AUTH_TOKEN)
  }
  return profile
}

function defaultState(): Phase6State {
  const now = new Date().toISOString()
  return {
    schemaVersion: PHASE6_STATE_SCHEMA_VERSION,
    activeProfileId: DEFAULT_PROFILE_ID,
    profiles: [defaultProfile(now)],
    windows: {},
    localModel: { ...DEFAULT_LOCAL_MODEL, updatedAt: now },
    offlineTasks: [],
    projectKnowledgeGenerations: {},
  }
}

export function readPhase6State(): Phase6State {
  const filePath = stateFilePath()
  if (!fs.existsSync(filePath)) return defaultState()
  try {
    const parsed = JSON.parse(fs.readFileSync(filePath, 'utf-8')) as Record<string, unknown>
    const fallback = defaultState()
    const normalized: Phase6State = {
      schemaVersion: PHASE6_STATE_SCHEMA_VERSION,
      activeProfileId: typeof parsed.activeProfileId === 'string' ? parsed.activeProfileId : fallback.activeProfileId,
      profiles: normalizeProfiles(parsed.profiles, fallback.profiles),
      windows: isRecord(parsed.windows) ? parsed.windows as Record<string, WindowState> : {},
      localModel: isRecord(parsed.localModel)
        ? { ...fallback.localModel, ...parsed.localModel }
        : fallback.localModel,
      offlineTasks: Array.isArray(parsed.offlineTasks) ? parsed.offlineTasks.slice(0, 100) : [],
      projectKnowledgeGenerations: isRecord(parsed.projectKnowledgeGenerations)
        ? Object.fromEntries(Object.entries(parsed.projectKnowledgeGenerations).filter(([, value]) => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0)) as Record<string, number>
        : {},
    }
    if (parsed.schemaVersion !== PHASE6_STATE_SCHEMA_VERSION || hasLegacyProfileToken(parsed.profiles)) {
      writePhase6State(normalized)
    }
    return normalized
  } catch {
    return defaultState()
  }
}

export function writePhase6State(state: Phase6State): Phase6State {
  const filePath = stateFilePath()
  fs.mkdirSync(path.dirname(filePath), { recursive: true })
  const next: Phase6State = { ...state, schemaVersion: PHASE6_STATE_SCHEMA_VERSION }
  const temporaryPath = `${filePath}.${process.pid}.${Date.now()}.tmp`
  fs.writeFileSync(temporaryPath, JSON.stringify(next, null, 2))
  fs.renameSync(temporaryPath, filePath)
  return next
}

export function listProfiles(): { activeProfileId: string; profiles: DesktopProfileMetadata[] } {
  const state = readPhase6State()
  return { activeProfileId: state.activeProfileId, profiles: state.profiles.map(sanitizeProfile) }
}

export function upsertProfile(input: {
  id?: string
  label: string
  apiBaseUrl?: string
  authToken?: string
  dataPath?: string
}): DesktopProfileMetadata {
  const state = readPhase6State()
  const now = new Date().toISOString()
  const id = normalizeId(input.id || input.label)
  const existing = state.profiles.find((profile) => profile.id === id)
  const profile: StoredDesktopProfile = {
    id,
    label: input.label.trim() || id,
    apiBaseUrl: input.apiBaseUrl?.trim() || existing?.apiBaseUrl || 'http://localhost:8000',
    credential: input.authToken !== undefined ? credentialForToken(id, input.authToken) : existing?.credential,
    dataPath: input.dataPath?.trim() || existing?.dataPath || path.join(app.getPath('userData'), 'profiles', id),
    workspaceRoot: existing?.workspaceRoot,
    createdAt: existing?.createdAt || now,
    updatedAt: now,
  }
  state.profiles = existing
    ? state.profiles.map((item) => item.id === id ? profile : item)
    : [...state.profiles, profile]
  if (!state.activeProfileId) state.activeProfileId = id
  writePhase6State(state)
  return sanitizeProfile(profile)
}

export function setActiveProfile(profileId: string): DesktopProfileMetadata {
  const state = readPhase6State()
  const profile = state.profiles.find((item) => item.id === profileId)
  if (!profile) throw new Error('desktop profile not found')
  state.activeProfileId = profile.id
  writePhase6State(state)
  return sanitizeProfile(profile)
}

export function getActiveProfile(): DesktopProfileMetadata {
  return sanitizeProfile(getActiveStoredProfile())
}

function getActiveStoredProfile(): StoredDesktopProfile {
  const state = readPhase6State()
  return state.profiles.find((profile) => profile.id === state.activeProfileId) || state.profiles[0] || defaultProfile(new Date().toISOString())
}

export function getActiveProfileCredential(): string {
  return resolveCredential(getActiveStoredProfile())
}

export function getActiveProfileWorkspaceRoot(): string | null {
  return getActiveStoredProfile().workspaceRoot?.trim() || null
}

export function setActiveProfileWorkspaceRoot(rootPath: string | null): void {
  const state = readPhase6State()
  const profile = state.profiles.find((item) => item.id === state.activeProfileId)
  if (!profile) throw new Error('desktop profile not found')
  const normalized = rootPath?.trim() || null
  if (normalized === null) {
    delete profile.workspaceRoot
  } else {
    profile.workspaceRoot = normalized
  }
  profile.updatedAt = new Date().toISOString()
  writePhase6State(state)
}

export function readWindowState(key: string): WindowState | null {
  return readPhase6State().windows[key] ?? null
}

export function writeWindowState(key: string, bounds: Omit<WindowState, 'updatedAt'>): WindowState {
  const state = readPhase6State()
  const next: WindowState = {
    ...bounds,
    updatedAt: new Date().toISOString(),
  }
  state.windows[key] = next
  writePhase6State(state)
  return next
}

export function getLocalModelSettings(): LocalModelSettings {
  return readPhase6State().localModel
}

export function setLocalModelSettings(input: Partial<LocalModelSettings>): LocalModelSettings {
  const state = readPhase6State()
  const next: LocalModelSettings = {
    ...state.localModel,
    ...input,
    provider: input.provider || state.localModel.provider,
    updatedAt: new Date().toISOString(),
  }
  state.localModel = next
  writePhase6State(state)
  return next
}

export function appendOfflineTask(task: OfflineTask): OfflineTask {
  const state = readPhase6State()
  state.offlineTasks = [task, ...state.offlineTasks].slice(0, 100)
  writePhase6State(state)
  return task
}

export function listOfflineTasks(): OfflineTask[] {
  return readPhase6State().offlineTasks
}

export function nextProjectKnowledgeSnapshotGeneration(rootIdentity: string): number {
  const state = readPhase6State()
  const next = (state.projectKnowledgeGenerations[rootIdentity] ?? 0) + 1
  state.projectKnowledgeGenerations[rootIdentity] = next
  writePhase6State(state)
  return next
}

function stateFilePath(): string {
  return path.join(app.getPath('userData'), 'phase6-state.json')
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function normalizeProfiles(value: unknown, fallback: StoredDesktopProfile[]): StoredDesktopProfile[] {
  if (!Array.isArray(value) || value.length === 0) return fallback
  return value
    .filter(isRecord)
    .map((profile) => {
      const id = normalizeId(String(profile.id || profile.label || DEFAULT_PROFILE_ID))
      const authToken = typeof profile.authToken === 'string' ? profile.authToken : undefined
      return {
        id,
        label: String(profile.label || id),
        apiBaseUrl: String(profile.apiBaseUrl || 'http://localhost:8000'),
        dataPath: String(profile.dataPath || path.join(app.getPath('userData'), 'profiles', id)),
        credential: normalizeCredential(id, profile.credential, authToken),
        workspaceRoot: typeof profile.workspaceRoot === 'string' ? profile.workspaceRoot : undefined,
        createdAt: String(profile.createdAt || new Date().toISOString()),
        updatedAt: String(profile.updatedAt || new Date().toISOString()),
      }
    })
}

function normalizeCredential(
  profileId: string,
  value: unknown,
  legacyAuthToken?: string
): StoredCredential | undefined {
  if (isRecord(value) && value.kind === 'safeStorage' && typeof value.encryptedValue === 'string') {
    return { kind: 'safeStorage', encryptedValue: value.encryptedValue }
  }
  if (isRecord(value) && value.kind === 'reference' && typeof value.reference === 'string') {
    return { kind: 'reference', reference: value.reference }
  }
  if (legacyAuthToken) return credentialForToken(profileId, legacyAuthToken)
  return undefined
}

function credentialForToken(profileId: string, token: string): StoredCredential | undefined {
  if (!token) return undefined
  if (isSafeStorageEncryptionAvailable()) {
    return {
      kind: 'safeStorage',
      encryptedValue: safeStorage.encryptString(token).toString('base64'),
    }
  }
  const reference = `memory:${profileId}`
  memoryCredentialStore.set(reference, token)
  return { kind: 'reference', reference }
}

function resolveCredential(profile: StoredDesktopProfile): string {
  if (!profile.credential) return ''
  if (profile.credential.kind === 'safeStorage') {
    try {
      return safeStorage.decryptString(Buffer.from(profile.credential.encryptedValue, 'base64'))
    } catch {
      return ''
    }
  }
  return memoryCredentialStore.get(profile.credential.reference) || ''
}

function isSafeStorageEncryptionAvailable(): boolean {
  try {
    return Boolean(safeStorage?.isEncryptionAvailable())
  } catch {
    return false
  }
}

function sanitizeProfile(profile: StoredDesktopProfile): DesktopProfileMetadata {
  const credentialStorage = !profile.credential
    ? 'none'
    : profile.credential.kind === 'safeStorage'
      ? 'persistent'
      : memoryCredentialStore.has(profile.credential.reference)
        ? 'session'
        : 'none'
  return {
    id: profile.id,
    label: profile.label,
    apiBaseUrl: profile.apiBaseUrl,
    dataPath: profile.dataPath,
    createdAt: profile.createdAt,
    updatedAt: profile.updatedAt,
    hasCredential: credentialStorage !== 'none',
    credentialStorage,
  }
}

function hasLegacyProfileToken(value: unknown): boolean {
  return Array.isArray(value)
    && value.some((profile) => isRecord(profile) && typeof profile.authToken === 'string')
}

function normalizeId(value: string): string {
  const normalized = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return normalized || DEFAULT_PROFILE_ID
}
