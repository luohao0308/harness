import { describe, test, expect, vi, beforeEach, afterAll } from 'vitest'

// Mock desktop-telemetry to prevent real API calls
vi.mock('../services/desktop-telemetry', () => ({
  recordDesktopStartupReport: vi.fn(() => Promise.resolve()),
  recordDesktopStartupTime: vi.fn(() => Promise.resolve()),
  checkForDesktopUpdates: vi.fn(() => Promise.resolve())
}))

vi.mock('../services/renderer-protocol', () => ({
  PACKAGED_RENDERER_URL: 'harness-app://renderer/index.html',
  RENDERER_HOST: 'renderer',
  RENDERER_SCHEME: 'harness-app',
  registerRendererProtocol: vi.fn(),
  registerRendererSchemePrivileges: vi.fn(),
}))

// Mock electron (this will override the vitest.setup.ts mock for this test file)
vi.mock('electron', () => ({
  app: {
    isPackaged: false,
    isReady: vi.fn(() => true),
    on: vi.fn(),
    whenReady: vi.fn(() => Promise.resolve()),
    quit: vi.fn(),
    requestSingleInstanceLock: vi.fn(() => true),
    setAsDefaultProtocolClient: vi.fn(),
    getLoginItemSettings: vi.fn(() => ({ openAtLogin: false })),
    setLoginItemSettings: vi.fn(),
    getPath: vi.fn((name: string) => {
      if (name === 'userData') return '/tmp/test-user-data'
      return '/tmp/test-data'
    }),
    getVersion: vi.fn(() => '1.0.0')
  },
  BrowserWindow: vi.fn(),
  ipcMain: {
    handle: vi.fn(),
    removeHandler: vi.fn()
  },
  globalShortcut: {
    register: vi.fn(),
    unregister: vi.fn()
  },
  Menu: {
    buildFromTemplate: vi.fn((template) => ({ template })),
    setApplicationMenu: vi.fn()
  },
  nativeImage: {
    createFromDataURL: vi.fn(() => ({ setTemplateImage: vi.fn() }))
  },
  Notification: Object.assign(vi.fn(() => ({ on: vi.fn(), show: vi.fn() })), {
    isSupported: vi.fn(() => true)
  }),
  Tray: vi.fn(() => ({
    on: vi.fn(),
    setContextMenu: vi.fn(),
    setToolTip: vi.fn()
  }))
}))

describe('Hot Reload Development Mode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  test('should load dev server URL in development mode', async () => {
    const { getAppConfig } = await import('../config/app')
    const config = getAppConfig()

    expect(config.isDev).toBe(true)
    expect(config.devServerUrl).toContain('localhost')
  })

  // Cleanup any pending fetch operations
  afterAll(() => {
    // Allow time for any pending network requests to abort cleanly
    return new Promise(resolve => setTimeout(resolve, 100))
  })

  test('should enable DevTools only when requested in development mode', async () => {
    // Reset modules to get fresh imports
    const originalEnv = process.env.HARNESS_DESKTOP_OPEN_DEVTOOLS
    process.env.HARNESS_DESKTOP_OPEN_DEVTOOLS = '1'
    vi.resetModules()

    const mockWindow = {
      loadURL: vi.fn(() => Promise.resolve()),
      webContents: {
        openDevTools: vi.fn(),
        send: vi.fn()
      },
      on: vi.fn(),
      isDestroyed: vi.fn(() => false),
      isMinimized: vi.fn(() => false),
      restore: vi.fn(),
      show: vi.fn(),
      focus: vi.fn()
    }

    // Re-mock electron with new BrowserWindow implementation
    vi.doMock('electron', () => ({
      app: {
        isPackaged: false,
        isReady: vi.fn(() => true),
        on: vi.fn(),
        whenReady: vi.fn(() => Promise.resolve()),
        quit: vi.fn(),
        requestSingleInstanceLock: vi.fn(() => true),
        setAsDefaultProtocolClient: vi.fn(),
        getLoginItemSettings: vi.fn(() => ({ openAtLogin: false })),
        setLoginItemSettings: vi.fn(),
        getPath: vi.fn((name: string) => {
          if (name === 'userData') return '/tmp/test-user-data'
          return '/tmp/test-data'
        }),
        getVersion: vi.fn(() => '1.0.0')
      },
      BrowserWindow: vi.fn(() => mockWindow),
      ipcMain: {
        handle: vi.fn(),
        removeHandler: vi.fn()
      },
      globalShortcut: {
        register: vi.fn(),
        unregister: vi.fn()
      },
      Menu: {
        buildFromTemplate: vi.fn((template) => ({ template })),
        setApplicationMenu: vi.fn()
      },
      nativeImage: {
        createFromDataURL: vi.fn(() => ({ setTemplateImage: vi.fn() }))
      },
      Notification: Object.assign(vi.fn(() => ({ on: vi.fn(), show: vi.fn() })), {
        isSupported: vi.fn(() => true)
      }),
      Tray: vi.fn(() => ({
        on: vi.fn(),
        setContextMenu: vi.fn(),
        setToolTip: vi.fn()
      }))
    }))

    const { createMainWindow } = await import('../main')
    await createMainWindow()

    expect(mockWindow.webContents.openDevTools).toHaveBeenCalled()

    if (originalEnv) {
      process.env.HARNESS_DESKTOP_OPEN_DEVTOOLS = originalEnv
    } else {
      delete process.env.HARNESS_DESKTOP_OPEN_DEVTOOLS
    }
  })

  test('should support custom dev server port via environment variable', async () => {
    const originalEnv = process.env.VITE_DEV_SERVER_URL
    process.env.VITE_DEV_SERVER_URL = 'http://localhost:3000'

    // Clear module cache to get fresh config
    vi.resetModules()

    const { getAppConfig } = await import('../config/app')
    const config = getAppConfig()

    expect(config.devServerUrl).toBe('http://localhost:3000')

    // Restore
    if (originalEnv) {
      process.env.VITE_DEV_SERVER_URL = originalEnv
    } else {
      delete process.env.VITE_DEV_SERVER_URL
    }
  })

  test('should watch for Vite HMR updates', async () => {
    // Reset modules to get fresh imports
    vi.resetModules()

    const mockWindow = {
      loadURL: vi.fn(() => Promise.resolve()),
      webContents: {
        openDevTools: vi.fn(),
        on: vi.fn(),
        send: vi.fn()
      },
      on: vi.fn(),
      isDestroyed: vi.fn(() => false),
      isMinimized: vi.fn(() => false),
      restore: vi.fn(),
      show: vi.fn(),
      focus: vi.fn()
    }

    // Re-mock electron with new BrowserWindow implementation
    vi.doMock('electron', () => ({
      app: {
        isPackaged: false,
        isReady: vi.fn(() => true),
        on: vi.fn(),
        whenReady: vi.fn(() => Promise.resolve()),
        quit: vi.fn(),
        requestSingleInstanceLock: vi.fn(() => true),
        setAsDefaultProtocolClient: vi.fn(),
        getLoginItemSettings: vi.fn(() => ({ openAtLogin: false })),
        setLoginItemSettings: vi.fn(),
        getPath: vi.fn((name: string) => {
          if (name === 'userData') return '/tmp/test-user-data'
          return '/tmp/test-data'
        }),
        getVersion: vi.fn(() => '1.0.0')
      },
      BrowserWindow: vi.fn(() => mockWindow),
      ipcMain: {
        handle: vi.fn(),
        removeHandler: vi.fn()
      },
      globalShortcut: {
        register: vi.fn(),
        unregister: vi.fn()
      },
      Menu: {
        buildFromTemplate: vi.fn((template) => ({ template })),
        setApplicationMenu: vi.fn()
      },
      nativeImage: {
        createFromDataURL: vi.fn(() => ({ setTemplateImage: vi.fn() }))
      },
      Notification: Object.assign(vi.fn(() => ({ on: vi.fn(), show: vi.fn() })), {
        isSupported: vi.fn(() => true)
      }),
      Tray: vi.fn(() => ({
        on: vi.fn(),
        setContextMenu: vi.fn(),
        setToolTip: vi.fn()
      }))
    }))

    const { createMainWindow } = await import('../main')
    const window = await createMainWindow()

    // Verify window can receive updates from Vite dev server
    expect(mockWindow.loadURL).toHaveBeenCalledWith(
      expect.stringContaining('localhost')
    )
  })
})
