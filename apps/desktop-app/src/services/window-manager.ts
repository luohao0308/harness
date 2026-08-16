import { BrowserWindow, ipcMain, shell } from 'electron'
import * as path from 'path'
import { getAppConfig } from '../config/app'
import type { DesktopRoutePayload } from '../preload-api'
import { attachWindowCrashReporting } from './crash-reporting'
import { getActiveProfile, readWindowState, writeWindowState } from './phase6-store'
import { PACKAGED_RENDERER_URL, RENDERER_HOST, RENDERER_SCHEME } from './renderer-protocol'
import { getVerifiedRuntimeEndpoint } from './local-runtime'

type WindowKind = 'main' | 'run'

type CreateHarnessWindowOptions = {
  kind: WindowKind
  runId?: string | null
  route?: string | null
  deferInitialLoad?: boolean
}

export type DesktopWindowSummary = {
  id: number
  key: string
  kind: WindowKind
  runId: string | null
  route: string
  profileId: string
  focused: boolean
  visible: boolean
}

const windowsByKey = new Map<string, BrowserWindow>()
const metadataById = new Map<number, Omit<DesktopWindowSummary, 'focused' | 'visible'>>()
let windowHandlersRegistered = false

export async function createHarnessWindow(
  options: CreateHarnessWindowOptions,
): Promise<BrowserWindow> {
  const config = getAppConfig()
  const profile = getActiveProfile()
  const route = normalizeRoute(options.route || routeForWindow(options))
  const key = windowKey(profile.id, options.kind, options.runId)
  const existing = windowsByKey.get(key)
  if (existing && !existing.isDestroyed()) {
    focusWindow(existing)
    sendRoute(existing, route, 'ipc')
    return existing
  }

  const state = readWindowState(key)
  const window = new BrowserWindow({
    width: state?.width ?? config.window.width,
    height: state?.height ?? config.window.height,
    x: state?.x,
    y: state?.y,
    minWidth: config.window.minWidth,
    minHeight: config.window.minHeight,
    title: options.kind === 'run' && options.runId ? `Harness Run ${options.runId}` : 'Harness Desktop',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      preload: path.join(__dirname, '../preload.js'),
    },
  })

  windowsByKey.set(key, window)
  metadataById.set(window.id, {
    id: window.id,
    key,
    kind: options.kind,
    runId: options.runId || null,
    route,
    profileId: profile.id,
  })

  bindWindowPersistence(window, key)
  bindWindowSecurity(window, config)
  attachWindowCrashReporting(window)

  if (state?.maximized) {
    window.maximize()
  }

  if (options.deferInitialLoad) {
    // The managed runtime loads the authenticated renderer once its sidecar is ready.
  } else if (config.isDev) {
    await window.loadURL(`${config.devServerUrl}${route}`)
    if (config.openDevTools) {
      window.webContents.openDevTools()
    }
  } else {
    window.webContents.once('did-finish-load', () => {
      sendRoute(window, route, 'ipc')
    })
    const runtimeEndpoint = getVerifiedRuntimeEndpoint()
    await window.loadURL(runtimeEndpoint ? routeAtRuntime(runtimeEndpoint.origin, route) : PACKAGED_RENDERER_URL)
  }

  return window
}

function bindWindowSecurity(window: BrowserWindow, config: ReturnType<typeof getAppConfig>): void {
  if (typeof window.webContents.setWindowOpenHandler === 'function') {
    window.webContents.setWindowOpenHandler(({ url }) => {
      if (isExternalHttpUrl(url) && !isLoopbackHttpUrl(url)) {
        void shell.openExternal(url)
      }
      return { action: 'deny' }
    })
  }

  if (typeof window.webContents.on === 'function') {
    window.webContents.on('will-navigate', (event, url) => {
      if (!isAllowedNavigation(url, config)) {
        event.preventDefault()
      }
    })
  }
}

function isAllowedNavigation(rawUrl: string, config: ReturnType<typeof getAppConfig>): boolean {
  try {
    const url = new URL(rawUrl)
    if (!config.isDev) {
      const isRecovery = url.protocol === `${RENDERER_SCHEME}:` && url.hostname === RENDERER_HOST
      const runtimeEndpoint = getVerifiedRuntimeEndpoint()
      return isRecovery || Boolean(runtimeEndpoint && url.origin === runtimeEndpoint.origin)
    }
    return url.origin === new URL(config.devServerUrl).origin
  } catch {
    return false
  }
}

function isLoopbackHttpUrl(rawUrl: string): boolean {
  try {
    const url = new URL(rawUrl)
    return url.protocol === 'http:' && (url.hostname === '127.0.0.1' || url.hostname === 'localhost')
  } catch {
    return false
  }
}

function routeAtRuntime(origin: string, route: string): string {
  const url = new URL('/desktop/', origin)
  url.hash = route
  return url.toString()
}

export async function loadVerifiedRuntimeInAllWindows(): Promise<void> {
  const endpoint = getVerifiedRuntimeEndpoint()
  if (!endpoint) throw new Error('verified local runtime endpoint is unavailable')
  await Promise.all(Array.from(metadataById.values()).map(async (metadata) => {
    const window = windowsByKey.get(metadata.key)
    if (!window || window.isDestroyed()) return
    await window.loadURL(routeAtRuntime(endpoint.origin, metadata.route))
    showWindowIfHidden(window)
  }))
}

export async function loadRecoveryRendererInAllWindows(): Promise<void> {
  await Promise.all(Array.from(windowsByKey.values()).map(async (window) => {
    if (!window.isDestroyed()) {
      await window.loadURL(PACKAGED_RENDERER_URL)
      showWindowIfHidden(window)
    }
  }))
}

function showWindowIfHidden(window: BrowserWindow): void {
  if (typeof window.isVisible !== 'function' || !window.isVisible()) window.show()
}

function isExternalHttpUrl(rawUrl: string): boolean {
  try {
    const url = new URL(rawUrl)
    return url.protocol === 'https:' || url.protocol === 'http:'
  } catch {
    return false
  }
}

export function registerDesktopWindowHandlers(): void {
  if (windowHandlersRegistered) return
  windowHandlersRegistered = true

  ipcMain.handle('window:open-run', async (_event, runId: string) => {
    const window = await createHarnessWindow({ kind: 'run', runId })
    return summarizeWindow(window)
  })

  ipcMain.handle('window:list', () => {
    return { items: listDesktopWindows() }
  })

  ipcMain.handle('window:get-state', () => {
    const profile = getActiveProfile()
    return {
      profileId: profile.id,
      items: listDesktopWindows(),
    }
  })
}

export function listDesktopWindows(): DesktopWindowSummary[] {
  return Array.from(metadataById.values())
    .map((metadata) => {
      const window = windowsByKey.get(metadata.key)
      if (!window || window.isDestroyed()) return null
      return {
        ...metadata,
        focused: window.isFocused(),
        visible: window.isVisible(),
      }
    })
    .filter((item): item is DesktopWindowSummary => item !== null)
}

function summarizeWindow(window: BrowserWindow): DesktopWindowSummary {
  const metadata = metadataById.get(window.id)
  if (!metadata) {
    throw new Error('desktop window metadata missing')
  }
  return {
    ...metadata,
    focused: window.isFocused(),
    visible: window.isVisible(),
  }
}

function bindWindowPersistence(window: BrowserWindow, key: string): void {
  const persist = () => {
    if (window.isDestroyed()) return
    const bounds = window.getBounds()
    writeWindowState(key, {
      width: bounds.width,
      height: bounds.height,
      x: bounds.x,
      y: bounds.y,
      maximized: window.isMaximized(),
    })
  }
  window.on('resize', persist)
  window.on('move', persist)
  window.on('maximize', persist)
  window.on('unmaximize', persist)
  window.on('close', persist)
  window.on('closed', () => {
    windowsByKey.delete(key)
    metadataById.delete(window.id)
  })
}

function focusWindow(window: BrowserWindow): void {
  if (window.isMinimized()) {
    window.restore()
  }
  window.show()
  window.focus()
}

function sendRoute(
  window: BrowserWindow,
  route: string,
  source: DesktopRoutePayload['source'],
): void {
  window.webContents.send('system:open-route', { route, source })
}

function routeForWindow(options: CreateHarnessWindowOptions): string {
  if (options.kind === 'run' && options.runId) {
    return `/runs/${encodeURIComponent(options.runId)}`
  }
  return '/'
}

function windowKey(profileId: string, kind: WindowKind, runId?: string | null): string {
  return `${profileId}:${kind}:${runId || 'main'}`
}

function normalizeRoute(route: string): string {
  const trimmed = route.trim()
  if (!trimmed || trimmed.startsWith('//')) return '/'
  try {
    const url = new URL(trimmed, 'http://desktop.local')
    return `${url.pathname || '/'}${url.search}${url.hash}`
  } catch {
    return '/'
  }
}
