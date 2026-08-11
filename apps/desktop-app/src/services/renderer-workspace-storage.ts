import { app, ipcMain } from 'electron'
import { createHash } from 'node:crypto'
import * as fs from 'node:fs'
import * as path from 'node:path'
import { getActiveProfile } from './phase6-store'

const STORAGE_KEY_PREFIX = 'harness.workspace.'
const MAX_KEY_LENGTH = 512
const MAX_VALUE_BYTES = 8 * 1024 * 1024
const MAX_ENTRY_COUNT = 256

type WorkspaceState = Record<string, string>
let handlersRegistered = false

export function registerRendererWorkspaceStorageHandlers(): void {
  if (handlersRegistered) return
  handlersRegistered = true

  ipcMain.on('renderer-workspace-storage:get', (event, key: unknown) => {
    event.returnValue = readWorkspaceValue(key)
  })
  ipcMain.on('renderer-workspace-storage:set', (event, key: unknown, value: unknown) => {
    event.returnValue = writeWorkspaceValue(key, value)
  })
  ipcMain.on('renderer-workspace-storage:remove', (event, key: unknown) => {
    event.returnValue = removeWorkspaceValue(key)
  })
}

export function readWorkspaceValue(key: unknown): string | null {
  if (!isAllowedKey(key)) return null
  return readState()[key] ?? null
}

export function writeWorkspaceValue(key: unknown, value: unknown): boolean {
  if (!isAllowedKey(key) || typeof value !== 'string' || Buffer.byteLength(value, 'utf8') > MAX_VALUE_BYTES) {
    return false
  }
  const state = readState()
  if (!(key in state) && Object.keys(state).length >= MAX_ENTRY_COUNT) return false
  state[key] = value
  return writeState(state)
}

export function removeWorkspaceValue(key: unknown): boolean {
  if (!isAllowedKey(key)) return false
  const state = readState()
  if (!(key in state)) return true
  delete state[key]
  return writeState(state)
}

function isAllowedKey(key: unknown): key is string {
  return typeof key === 'string' && key.startsWith(STORAGE_KEY_PREFIX) && key.length <= MAX_KEY_LENGTH
}

function readState(): WorkspaceState {
  try {
    const parsed = JSON.parse(fs.readFileSync(stateFilePath(), 'utf8')) as unknown
    if (!isRecord(parsed)) return {}
    const state: WorkspaceState = {}
    for (const [key, value] of Object.entries(parsed)) {
      if (isAllowedKey(key) && typeof value === 'string') state[key] = value
    }
    return state
  } catch {
    return {}
  }
}

function writeState(state: WorkspaceState): boolean {
  const target = stateFilePath()
  const temporary = `${target}.${process.pid}.tmp`
  try {
    fs.mkdirSync(path.dirname(target), { recursive: true })
    fs.writeFileSync(temporary, JSON.stringify(state), { encoding: 'utf8', mode: 0o600 })
    fs.renameSync(temporary, target)
    return true
  } catch {
    try {
      fs.unlinkSync(temporary)
    } catch {
      // Ignore cleanup errors after a failed atomic write.
    }
    return false
  }
}

function stateFilePath(): string {
  const profileHash = createHash('sha256').update(getActiveProfile().id).digest('hex').slice(0, 16)
  return path.join(app.getPath('userData'), 'renderer-workspace-state', `${profileHash}.json`)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
