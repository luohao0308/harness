import { describe, test, expect, vi, beforeEach } from 'vitest'

// Mock desktop-telemetry to prevent real API calls
vi.mock('../services/desktop-telemetry', () => ({
  recordDesktopStartupReport: vi.fn(() => Promise.resolve()),
  recordDesktopStartupTime: vi.fn(() => Promise.resolve()),
  checkForDesktopUpdates: vi.fn(() => Promise.resolve())
}))

// Mock electron
vi.mock('electron', () => ({
  app: {
    isPackaged: true, // Production mode
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
      BrowserWindow: vi.fn(() => ({
    loadURL: vi.fn(() => Promise.resolve()),
    loadFile: vi.fn(() => Promise.resolve()),
    webContents: {
      openDevTools: vi.fn()
    },
        on: vi.fn()
      })),
      protocol: {
        registerSchemesAsPrivileged: vi.fn(),
        handle: vi.fn(),
      },
      net: {
        fetch: vi.fn(),
      },
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
  powerMonitor: {
    on: vi.fn(),
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

describe('Production Mode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  test('should load static files in production mode', async () => {
    vi.resetModules()

    const mockWindow = {
      loadURL: vi.fn(() => Promise.resolve()),
      loadFile: vi.fn(() => Promise.resolve()),
      webContents: {
        openDevTools: vi.fn(),
        send: vi.fn(),
        on: vi.fn(),
        once: vi.fn()
      },
      on: vi.fn(),
      isDestroyed: vi.fn(() => false),
      isMinimized: vi.fn(() => false),
      restore: vi.fn(),
      show: vi.fn(),
      focus: vi.fn()
    }

    vi.doMock('electron', () => ({
      app: {
        isPackaged: true, // Production mode
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
      protocol: {
        registerSchemesAsPrivileged: vi.fn(),
        handle: vi.fn(),
      },
      net: {
        fetch: vi.fn(),
      },
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
      powerMonitor: {
        on: vi.fn(),
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

    expect(mockWindow.loadURL).toHaveBeenCalledWith('harness-app://renderer/index.html')
    expect(mockWindow.loadFile).not.toHaveBeenCalled()

    // Verify DevTools not opened in production
    expect(mockWindow.webContents.openDevTools).not.toHaveBeenCalled()
  })

  test('should use the trusted renderer protocol in production', async () => {
    vi.resetModules()

    const mockWindow = {
      loadURL: vi.fn(() => Promise.resolve()),
      loadFile: vi.fn(() => Promise.resolve()),
      webContents: {
        openDevTools: vi.fn(),
        send: vi.fn(),
        on: vi.fn(),
        once: vi.fn()
      },
      on: vi.fn(),
      isDestroyed: vi.fn(() => false),
      isMinimized: vi.fn(() => false),
      restore: vi.fn(),
      show: vi.fn(),
      focus: vi.fn()
    }

    vi.doMock('electron', () => ({
      app: {
        isPackaged: true,
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
      protocol: {
        registerSchemesAsPrivileged: vi.fn(),
        handle: vi.fn(),
      },
      net: {
        fetch: vi.fn(),
      },
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
      powerMonitor: {
        on: vi.fn(),
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

    expect(mockWindow.loadURL).toHaveBeenCalledWith('harness-app://renderer/index.html')
    expect(mockWindow.loadFile).not.toHaveBeenCalled()
  })

  test('should report isDev=false in production config', async () => {
    // This test only checks config, doesn't need to import main.ts
    // which would trigger IPC handler registration
    const { getAppConfig } = await import('../config/app')

    // Temporarily override app.isPackaged
    const { app } = await import('electron')
    const originalIsPackaged = app.isPackaged
    Object.defineProperty(app, 'isPackaged', { value: true, writable: true })

    const config = getAppConfig()

    expect(config.isDev).toBe(false)

    // Restore
    Object.defineProperty(app, 'isPackaged', { value: originalIsPackaged, writable: true })
  })
})
