import { vi } from 'vitest'

// Mock @sentry/electron to avoid module resolution issues in tests
vi.mock('@sentry/electron/main', () => ({
  init: vi.fn(),
  captureException: vi.fn(),
  captureMessage: vi.fn(),
  setContext: vi.fn(),
  setUser: vi.fn(),
  addBreadcrumb: vi.fn(),
}))

vi.mock('@sentry/electron/renderer', () => ({
  init: vi.fn(),
  captureException: vi.fn(),
  captureMessage: vi.fn(),
  setContext: vi.fn(),
  setUser: vi.fn(),
  addBreadcrumb: vi.fn(),
}))

// Mock electron app.getPath for phase6-store
vi.mock('electron', async () => {
  const actual = await vi.importActual<typeof import('electron')>('electron')
  return {
    ...actual,
    app: {
      ...actual.app,
      getPath: vi.fn((name: string) => {
        if (name === 'userData') return '/tmp/test-user-data'
        return '/tmp/test-data'
      }),
      getVersion: vi.fn(() => '1.0.0'),
    },
  }
})

// Mock electron-updater to avoid initialization issues
vi.mock('electron-updater', () => ({
  autoUpdater: {
    logger: null,
    autoDownload: false,
    autoInstallOnAppQuit: false,
    allowDowngrade: false,
    allowPrerelease: false,
    checkForUpdates: vi.fn(),
    downloadUpdate: vi.fn(),
    quitAndInstall: vi.fn(),
    on: vi.fn(),
    once: vi.fn(),
    removeListener: vi.fn(),
  },
}))
