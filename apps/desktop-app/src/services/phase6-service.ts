import { BrowserWindow, ipcMain } from 'electron'
import type {
  DesktopLocalModelSettings,
  DesktopLocalModelHealth,
  DesktopOfflineTask,
  DesktopProfile,
  DesktopProfileSaveInput,
} from '../preload-api'
import { setDesktopProfileResolver } from '../shared/api-client'
import {
  appendOfflineTask,
  getActiveProfile,
  getActiveProfileCredential,
  getLocalModelSettings,
  listOfflineTasks,
  listProfiles,
  setActiveProfile,
  setLocalModelSettings,
  upsertProfile,
} from './phase6-store'

let phase6HandlersRegistered = false
const LOCAL_MODEL_TIMEOUT_MS = 10_000

export function registerPhase6Handlers(): void {
  setDesktopProfileResolver(() => {
    const profile = getActiveProfile()
    return { apiBaseUrl: profile.apiBaseUrl, authToken: getActiveProfileCredential() }
  })

  if (phase6HandlersRegistered) return
  phase6HandlersRegistered = true

  ipcMain.handle('profile:list', () => listProfiles())

  ipcMain.handle(
    'profile:save',
    (_event, payload: DesktopProfileSaveInput): DesktopProfile => {
      return upsertProfile(payload)
    }
  )

  ipcMain.handle('profile:switch', (event, profileId: string): DesktopProfile => {
    const profile = setActiveProfile(profileId)
    BrowserWindow.getAllWindows().forEach((window) => {
      window.webContents.send('profile:changed', profile)
    })
    event.sender.send('profile:changed', profile)
    return profile
  })

  ipcMain.handle('local-model:get-settings', (): DesktopLocalModelSettings => {
    return getLocalModelSettings()
  })

  ipcMain.handle(
    'local-model:set-settings',
    (_event, payload: Partial<DesktopLocalModelSettings>): DesktopLocalModelSettings => {
      const current = getLocalModelSettings()
      const next = { ...current, ...payload }
      validateLocalModelSettings(next)
      return setLocalModelSettings(payload)
    }
  )

  ipcMain.handle('local-model:test-connection', async (): Promise<DesktopLocalModelHealth> => {
    return testLocalModelConnection(getLocalModelSettings())
  })

  ipcMain.handle(
    'offline:run-simple-task',
    async (_event, payload: { prompt: string; useLocalModel?: boolean }): Promise<DesktopOfflineTask> => {
      return runOfflineSimpleTask(payload.prompt, { useLocalModel: Boolean(payload.useLocalModel) })
    }
  )

  ipcMain.handle('offline:list-tasks', (): { items: DesktopOfflineTask[] } => {
    return { items: listOfflineTasks() }
  })
}

export async function runOfflineSimpleTask(
  prompt: string,
  options: { useLocalModel?: boolean } = {}
): Promise<DesktopOfflineTask> {
  const normalizedPrompt = prompt.trim()
  if (!normalizedPrompt) {
    throw new Error('offline prompt is required')
  }

  const localModel = getLocalModelSettings()
  const createdAt = new Date().toISOString()
  const startedAt = Date.now()
  let fallbackReason: string | null = null
  if (options.useLocalModel && localModel.enabled) {
    try {
      const result = await invokeLocalModel(normalizedPrompt, localModel)
      return appendOfflineTask({
        id: offlineTaskId(),
        prompt: normalizedPrompt,
        result,
        modelSource: 'local-model',
        status: 'completed',
        createdAt,
        modelRequested: true,
        fallbackReason: null,
        durationMs: Date.now() - startedAt,
      })
    } catch (error) {
      fallbackReason = errorMessage(error)
    }
  }

  return appendOfflineTask({
    id: offlineTaskId(),
    prompt: normalizedPrompt,
    result: deterministicOfflineResult(normalizedPrompt),
    modelSource: 'deterministic-local',
    status: 'completed',
    createdAt,
    modelRequested: Boolean(options.useLocalModel && localModel.enabled),
    fallbackReason,
    durationMs: Date.now() - startedAt,
  })
}

async function invokeLocalModel(
  prompt: string,
  settings: DesktopLocalModelSettings
): Promise<string> {
  validateLocalModelSettings(settings)
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), LOCAL_MODEL_TIMEOUT_MS)
  try {
    if (settings.provider === 'ollama') {
      const response = await fetch(`${settings.baseUrl.replace(/\/$/, '')}/api/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: settings.model,
          prompt,
          stream: false,
        }),
        signal: controller.signal,
      })
      if (!response.ok) throw new Error(`local model failed: ${response.status}`)
      const payload = await response.json() as { response?: string }
      return String(payload.response || '').trim() || deterministicOfflineResult(prompt)
    }

    const response = await fetch(`${settings.baseUrl.replace(/\/$/, '')}/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: settings.model,
        messages: [{ role: 'user', content: prompt }],
      }),
      signal: controller.signal,
    })
    if (!response.ok) throw new Error(`local model failed: ${response.status}`)
    const payload = await response.json() as {
      choices?: Array<{ message?: { content?: string } }>
    }
    return String(payload.choices?.[0]?.message?.content || '').trim() || deterministicOfflineResult(prompt)
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error('local model request timed out')
    }
    throw error
  } finally {
    clearTimeout(timeout)
  }
}

async function testLocalModelConnection(settings: DesktopLocalModelSettings): Promise<DesktopLocalModelHealth> {
  const checkedAt = new Date().toISOString()
  const startedAt = Date.now()
  try {
    validateLocalModelSettings(settings)
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), LOCAL_MODEL_TIMEOUT_MS)
    try {
      const baseUrl = settings.baseUrl.replace(/\/$/, '')
      const path = settings.provider === 'ollama' ? '/api/tags' : '/models'
      const response = await fetch(`${baseUrl}${path}`, { signal: controller.signal })
      if (!response.ok) throw new Error(`local model health check failed: ${response.status}`)
    } finally {
      clearTimeout(timeout)
    }
    return { available: true, checkedAt, durationMs: Date.now() - startedAt, error: null }
  } catch (error) {
    return {
      available: false,
      checkedAt,
      durationMs: Date.now() - startedAt,
      error: errorMessage(error),
    }
  }
}

function validateLocalModelSettings(settings: DesktopLocalModelSettings): void {
  if (!settings.model.trim()) throw new Error('local model name is required')
  let endpoint: URL
  try {
    endpoint = new URL(settings.baseUrl)
  } catch {
    throw new Error('local model endpoint is invalid')
  }
  if (endpoint.protocol !== 'http:' && endpoint.protocol !== 'https:') {
    throw new Error('local model endpoint must use HTTP or HTTPS')
  }
  const hostname = endpoint.hostname.toLowerCase()
  const isLoopback = hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1' || hostname === '[::1]'
  if (!isLoopback && process.env.HARNESS_DESKTOP_ALLOW_REMOTE_LOCAL_MODEL !== '1') {
    throw new Error('local model endpoint must be on this device')
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function deterministicOfflineResult(prompt: string): string {
  const lines = prompt
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean)
  const title = lines[0] || prompt
  return [
    `离线任务已完成：${title.slice(0, 80)}`,
    '',
    '本地摘要：',
    ...lines.slice(0, 5).map((line, index) => `${index + 1}. ${line}`),
    '',
    '联网恢复后，可把此结果发送到 Agent Run 继续执行和审计。',
  ].join('\n')
}

function offlineTaskId(): string {
  return `offline-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}
