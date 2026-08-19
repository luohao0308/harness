import { beforeEach, describe, expect, test, vi } from 'vitest'

const electronState = {
  isPackaged: true,
  version: '0.1.0',
}
const ipcHandlers = new Map<string, (...args: unknown[]) => unknown>()
const updaterEvents = new Map<string, (...args: any[]) => void>()

vi.mock('electron', () => ({
  app: {
    get isPackaged() {
      return electronState.isPackaged
    },
    getVersion: vi.fn(() => electronState.version),
  },
  ipcMain: {
    handle: vi.fn((channel: string, handler: (...args: unknown[]) => unknown) => {
      ipcHandlers.set(channel, handler)
    }),
  },
}))

vi.mock('electron-log', () => ({
  default: {
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}))

const autoUpdater = {
  allowPrerelease: false,
  autoDownload: false,
  autoInstallOnAppQuit: false,
  channel: 'stable',
  logger: null as unknown,
  checkForUpdates: vi.fn(async () => ({ updateInfo: { version: '0.2.0' } })),
  downloadUpdate: vi.fn(async () => ['Forge Harness Desktop-0.2.0.blockmap']),
  on: vi.fn((event: string, callback: (...args: any[]) => void) => {
    updaterEvents.set(event, callback)
  }),
  quitAndInstall: vi.fn(),
  setFeedURL: vi.fn(),
}

vi.mock('electron-updater', () => ({
  autoUpdater,
}))

const apiRequest = vi.fn()

vi.mock('../shared/api-client', () => ({
  apiRequest,
  buildQueryString: (params: Record<string, string | undefined>) => {
    const searchParams = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) searchParams.set(key, value)
    }
    const query = searchParams.toString()
    return query ? `?${query}` : ''
  },
}))

describe('desktop updates', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    ipcHandlers.clear()
    updaterEvents.clear()
    electronState.isPackaged = true
    electronState.version = '0.1.0'
    delete process.env.HARNESS_DESKTOP_UPDATE_CHANNEL
    delete process.env.DESKTOP_RELEASE_CHANNEL
    delete process.env.HARNESS_DESKTOP_UPDATES_IN_DEV
    const { resetDesktopUpdatesForTests } = await import('../services/desktop-updates')
    resetDesktopUpdatesForTests()
  })

  test('resolves stable and beta update channels', async () => {
    const { resolveUpdateChannel } = await import('../services/desktop-updates')

    expect(resolveUpdateChannel('0.2.0')).toBe('stable')
    expect(resolveUpdateChannel('0.2.0-beta.1')).toBe('beta')
    expect(resolveUpdateChannel('0.2.0', { HARNESS_DESKTOP_UPDATE_CHANNEL: 'beta' } as NodeJS.ProcessEnv)).toBe(
      'beta'
    )
  })

  test('checks backend policy before electron-updater and uses returned feed url', async () => {
    apiRequest.mockResolvedValue({
      update_available: true,
      channel: 'stable',
      current_version: '0.1.0',
      latest_version: '0.2.0',
      platform: 'darwin',
      arch: 'arm64',
      release_url: 'https://github.com/luohao0308/forge-harness/releases/tag/v0.2.0',
      feed_url: 'https://github.com/luohao0308/forge-harness/releases/download/v0.2.0',
      metadata_url: 'https://github.com/luohao0308/forge-harness/releases/download/v0.2.0/latest-mac.yml',
      checked_at: '2026-06-26T00:00:00Z',
    })
    const { checkForDesktopUpdates } = await import('../services/desktop-updates')

    const status = await checkForDesktopUpdates()

    expect(apiRequest).toHaveBeenCalledWith(expect.stringContaining('/api/desktop/updates/check?'))
    expect(autoUpdater.setFeedURL).toHaveBeenCalledWith({
      provider: 'generic',
      url: 'https://github.com/luohao0308/forge-harness/releases/download/v0.2.0',
      channel: 'stable',
    })
    expect(autoUpdater.checkForUpdates).toHaveBeenCalled()
    expect(autoUpdater.autoDownload).toBe(false)
    expect(autoUpdater.autoInstallOnAppQuit).toBe(false)
    expect(status).toMatchObject({
      state: 'available',
      channel: 'stable',
      currentVersion: '0.1.0',
      latestVersion: '0.2.0',
    })
  })

  test('rejects update feeds that are not HTTPS or do not match the release host', async () => {
    apiRequest.mockResolvedValue({
      update_available: true,
      channel: 'stable',
      current_version: '0.1.0',
      latest_version: '0.2.0',
      platform: 'darwin',
      arch: 'arm64',
      release_url: 'https://github.com/luohao0308/forge-harness/releases/tag/v0.2.0',
      feed_url: 'http://updates.example.test/v0.2.0',
      metadata_url: 'http://updates.example.test/v0.2.0/latest-mac.yml',
      checked_at: '2026-06-26T00:00:00Z',
    })
    const { checkForDesktopUpdates } = await import('../services/desktop-updates')

    const status = await checkForDesktopUpdates()

    expect(status).toMatchObject({
      state: 'error',
      error: expect.stringContaining('trusted HTTPS origin'),
    })
    expect(autoUpdater.setFeedURL).not.toHaveBeenCalled()
    expect(autoUpdater.checkForUpdates).not.toHaveBeenCalled()
  })

  test('skips electron-updater when backend reports no update', async () => {
    apiRequest.mockResolvedValue({
      update_available: false,
      channel: 'stable',
      current_version: '0.2.0',
      latest_version: '0.2.0',
      platform: 'linux',
      arch: 'x64',
      release_url: 'https://github.com/luohao0308/forge-harness/releases/tag/v0.2.0',
      feed_url: 'https://github.com/luohao0308/forge-harness/releases/download/v0.2.0',
      metadata_url: 'https://github.com/luohao0308/forge-harness/releases/download/v0.2.0/latest-linux.yml',
      checked_at: '2026-06-26T00:00:00Z',
    })
    electronState.version = '0.2.0'
    const { checkForDesktopUpdates } = await import('../services/desktop-updates')

    const status = await checkForDesktopUpdates()

    expect(autoUpdater.checkForUpdates).not.toHaveBeenCalled()
    expect(status.state).toBe('not-available')
  })

  test('registers update IPC and publishes progress events to renderer', async () => {
    const send = vi.fn()
    const window = {
      isDestroyed: vi.fn(() => false),
      webContents: { send },
    }
    const { registerDesktopUpdateHandlers } = await import('../services/desktop-updates')

    registerDesktopUpdateHandlers({
      getMainWindow: () => window as never,
    })
    updaterEvents.get('download-progress')?.({
      percent: 42,
      bytesPerSecond: 1024,
      transferred: 42,
      total: 100,
    })

    expect(ipcHandlers.has('updates:check')).toBe(true)
    expect(ipcHandlers.has('updates:install')).toBe(true)
    expect(send).toHaveBeenCalledWith(
      'updates:status',
      expect.objectContaining({
        state: 'downloading',
        progress: expect.objectContaining({ percent: 42 }),
      })
    )
  })

  test('gates download and install IPC by update state', async () => {
    const { registerDesktopUpdateHandlers } = await import('../services/desktop-updates')
    registerDesktopUpdateHandlers({ getMainWindow: () => null })

    const download = ipcHandlers.get('updates:download')
    const install = ipcHandlers.get('updates:install')

    await expect(download?.({})).rejects.toThrow('not available for download')
    expect(() => install?.({})).toThrow('not ready to install')

    apiRequest.mockResolvedValue({
      update_available: true,
      channel: 'stable',
      current_version: '0.1.0',
      latest_version: '0.2.0',
      platform: 'darwin',
      arch: 'arm64',
      release_url: 'https://github.com/luohao0308/forge-harness/releases/tag/v0.2.0',
      feed_url: 'https://github.com/luohao0308/forge-harness/releases/download/v0.2.0',
      metadata_url: 'https://github.com/luohao0308/forge-harness/releases/download/v0.2.0/latest-mac.yml',
      checked_at: '2026-06-26T00:00:00Z',
    })
    const { checkForDesktopUpdates } = await import('../services/desktop-updates')
    await checkForDesktopUpdates()
    await expect(download?.({})).resolves.toMatchObject({ state: 'downloading' })

    expect(() => install?.({})).toThrow('not ready to install')
    updaterEvents.get('update-downloaded')?.({ version: '0.2.0' })
    expect(() => install?.({})).not.toThrow()
    expect(autoUpdater.quitAndInstall).toHaveBeenCalledWith(false, true)
  })
})
