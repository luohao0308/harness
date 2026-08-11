import { app, ipcMain, type BrowserWindow } from 'electron'
import log from 'electron-log'
import { autoUpdater, type UpdateCheckResult } from 'electron-updater'
import type {
  DesktopUpdateChannel,
  DesktopUpdateCheckResponse,
  DesktopUpdateStatus,
} from '../preload-api'
import { apiRequest, buildQueryString } from '../shared/api-client'

type WindowProvider = () => BrowserWindow | null

export interface DesktopUpdateOptions {
  getMainWindow: WindowProvider
}

let getMainWindow: WindowProvider = () => null
let updateHandlersRegistered = false
let updateEventsRegistered = false
let lastStatus: DesktopUpdateStatus = {
  state: 'idle',
  channel: 'stable',
  currentVersion: '0.1.0',
}

export function resolveUpdateChannel(
  version: string = getDesktopAppVersion(),
  env: NodeJS.ProcessEnv = process.env
): DesktopUpdateChannel {
  const configured = (env.HARNESS_DESKTOP_UPDATE_CHANNEL || env.DESKTOP_RELEASE_CHANNEL || '').toLowerCase()
  if (configured === 'beta' || configured === 'stable') return configured
  return version.includes('-beta') ? 'beta' : 'stable'
}

export function configureAutoUpdater(channel: DesktopUpdateChannel = resolveUpdateChannel()): void {
  autoUpdater.logger = log
  // Updates are user-controlled. The renderer owns the explicit download and
  // install actions after the backend policy check has completed.
  autoUpdater.autoDownload = false
  autoUpdater.autoInstallOnAppQuit = false
  autoUpdater.allowPrerelease = channel === 'beta'
  autoUpdater.channel = channel
}

export function registerDesktopUpdateHandlers(options: DesktopUpdateOptions): void {
  getMainWindow = options.getMainWindow

  // Initialize status with actual values now that app is ready
  lastStatus = {
    state: 'idle',
    channel: resolveUpdateChannel(),
    currentVersion: getDesktopAppVersion(),
  }
  configureAutoUpdater()
  registerUpdaterEvents()

  if (updateHandlersRegistered) return
  updateHandlersRegistered = true

  ipcMain.handle('updates:get-status', () => lastStatus)
  ipcMain.handle('updates:check', async () => {
    return checkForDesktopUpdates()
  })
  ipcMain.handle('updates:download', async () => {
    if (lastStatus.state !== 'available') {
      throw new Error('update is not available for download')
    }
    setUpdateStatus({ state: 'downloading' })
    const files = await autoUpdater.downloadUpdate()
    setUpdateStatus({ state: 'downloading', files })
    return lastStatus
  })
  ipcMain.handle('updates:install', () => {
    if (lastStatus.state !== 'downloaded') {
      throw new Error('update is not ready to install')
    }
    autoUpdater.quitAndInstall(false, true)
  })
}

export async function checkForDesktopUpdates(): Promise<DesktopUpdateStatus> {
  const channel = resolveUpdateChannel()
  configureAutoUpdater(channel)
  setUpdateStatus({ state: 'checking', channel, currentVersion: getDesktopAppVersion() })

  if (!app.isPackaged && process.env.HARNESS_DESKTOP_UPDATES_IN_DEV !== '1') {
    setUpdateStatus({
      state: 'not-available',
      channel,
      currentVersion: getDesktopAppVersion(),
      reason: 'updates require a packaged desktop app',
    })
    return lastStatus
  }

  let backendCheck: DesktopUpdateCheckResponse
  try {
    backendCheck = await checkBackendForUpdate(channel)
  } catch (error) {
    setUpdateStatus({
      state: 'error',
      channel,
      currentVersion: getDesktopAppVersion(),
      error: error instanceof Error ? error.message : String(error),
    })
    return lastStatus
  }

  if (!backendCheck.update_available) {
    setUpdateStatus({
      state: 'not-available',
      channel: backendCheck.channel,
      currentVersion: backendCheck.current_version,
      latestVersion: backendCheck.latest_version,
      releaseUrl: backendCheck.release_url,
    })
    return lastStatus
  }

  if (backendCheck.feed_url) {
    const feedValidationError = validateUpdateFeed(backendCheck)
    if (feedValidationError) {
      setUpdateStatus({
        state: 'error',
        channel: backendCheck.channel,
        currentVersion: backendCheck.current_version,
        latestVersion: backendCheck.latest_version,
        releaseUrl: backendCheck.release_url,
        error: feedValidationError,
      })
      return lastStatus
    }
    autoUpdater.setFeedURL({
      provider: 'generic',
      url: backendCheck.feed_url,
      channel: backendCheck.channel,
    })
  }

  let result: UpdateCheckResult | null = null
  try {
    result = await autoUpdater.checkForUpdates()
  } catch (error) {
    setUpdateStatus({
      state: 'error',
      channel: backendCheck.channel,
      currentVersion: backendCheck.current_version,
      latestVersion: backendCheck.latest_version,
      releaseUrl: backendCheck.release_url,
      error: error instanceof Error ? error.message : String(error),
    })
    return lastStatus
  }
  setUpdateStatus({
    state: 'available',
    channel: backendCheck.channel,
    currentVersion: backendCheck.current_version,
    latestVersion: result?.updateInfo.version || backendCheck.latest_version,
    releaseUrl: backendCheck.release_url,
  })
  return lastStatus
}

async function checkBackendForUpdate(channel: DesktopUpdateChannel): Promise<DesktopUpdateCheckResponse> {
  const suffix = buildQueryString({
    current_version: getDesktopAppVersion(),
    channel,
    platform: process.platform,
    arch: process.arch,
  })

  return apiRequest<DesktopUpdateCheckResponse>(`/api/desktop/updates/check${suffix}`)
}

function registerUpdaterEvents(): void {
  if (updateEventsRegistered) return
  updateEventsRegistered = true

  autoUpdater.on('checking-for-update', () => {
    setUpdateStatus({ state: 'checking' })
  })
  autoUpdater.on('update-available', (info) => {
    setUpdateStatus({
      state: 'available',
      latestVersion: info.version,
      releaseUrl: info.releaseNotes ? String(info.releaseNotes) : lastStatus.releaseUrl,
    })
  })
  autoUpdater.on('update-not-available', (info) => {
    setUpdateStatus({
      state: 'not-available',
      latestVersion: info.version,
    })
  })
  autoUpdater.on('download-progress', (progress) => {
    setUpdateStatus({
      state: 'downloading',
      progress: {
        percent: progress.percent,
        bytesPerSecond: progress.bytesPerSecond,
        transferred: progress.transferred,
        total: progress.total,
      },
    })
  })
  autoUpdater.on('update-downloaded', (info) => {
    setUpdateStatus({
      state: 'downloaded',
      latestVersion: info.version,
    })
  })
  autoUpdater.on('error', (error) => {
    setUpdateStatus({
      state: 'error',
      error: error.message,
    })
  })
}

function setUpdateStatus(next: Partial<DesktopUpdateStatus>): void {
  lastStatus = {
    ...lastStatus,
    ...next,
    checkedAt: new Date().toISOString(),
  }

  const window = getMainWindow()
  if (!window || window.isDestroyed()) return
  window.webContents.send('updates:status', lastStatus)
}

function validateUpdateFeed(response: DesktopUpdateCheckResponse): string | null {
  let feed: URL
  let release: URL
  try {
    feed = new URL(response.feed_url)
    release = new URL(response.release_url)
  } catch {
    return 'update feed must use a trusted HTTPS origin'
  }

  if (feed.protocol !== 'https:' || release.protocol !== 'https:') {
    return 'update feed must use a trusted HTTPS origin'
  }

  const configuredHosts = (process.env.HARNESS_DESKTOP_UPDATE_ALLOWED_HOSTS || '')
    .split(',')
    .map((host) => host.trim().toLowerCase())
    .filter(Boolean)
  const allowedHosts = new Set([release.hostname.toLowerCase(), ...configuredHosts])
  if (feed.hostname.toLowerCase() !== release.hostname.toLowerCase() && !allowedHosts.has(feed.hostname.toLowerCase())) {
    return 'update feed host is not trusted'
  }

  return null
}

export function resetDesktopUpdatesForTests(): void {
  getMainWindow = () => null
  updateHandlersRegistered = false
  updateEventsRegistered = false
  lastStatus = {
    state: 'idle',
    channel: resolveUpdateChannel(),
    currentVersion: getDesktopAppVersion(),
  }
}

function getDesktopAppVersion(): string {
  return typeof app.getVersion === 'function'
    ? app.getVersion()
    : process.env.npm_package_version || '0.1.0'
}
