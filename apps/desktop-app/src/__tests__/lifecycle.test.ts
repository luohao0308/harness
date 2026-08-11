import { beforeEach, describe, expect, test, vi } from 'vitest'

vi.mock('../services/renderer-protocol', () => ({
  PACKAGED_RENDERER_URL: 'harness-app://renderer/index.html',
  RENDERER_HOST: 'renderer',
  RENDERER_SCHEME: 'harness-app',
  registerRendererProtocol: vi.fn(),
  registerRendererSchemePrivileges: vi.fn(),
}))

function createElectronMock(windowOverrides: Record<string, unknown> = {}) {
  const mockWindow = {
    id: Math.floor(Math.random() * 10000),
    focus: vi.fn(),
    getBounds: vi.fn(() => ({ x: 10, y: 20, width: 1280, height: 800 })),
    hide: vi.fn(),
    isFocused: vi.fn(() => true),
    isDestroyed: vi.fn(() => false),
    isMaximized: vi.fn(() => false),
    isMinimized: vi.fn(() => false),
    isVisible: vi.fn(() => true),
    loadFile: vi.fn(() => Promise.resolve()),
    loadURL: vi.fn(() => Promise.resolve()),
    maximize: vi.fn(),
    on: vi.fn(),
    restore: vi.fn(),
    show: vi.fn(),
    webContents: {
      on: vi.fn(),
      openDevTools: vi.fn(),
      once: vi.fn(),
      setWindowOpenHandler: vi.fn(),
      send: vi.fn(),
    },
    ...windowOverrides,
  }

  const BrowserWindow = Object.assign(vi.fn(() => mockWindow), {
    getAllWindows: vi.fn(() => []),
  })

  const electronMock = {
    app: {
      getLoginItemSettings: vi.fn(() => ({ openAtLogin: false })),
      getPath: vi.fn((name: string) => `/mock/path/${name}`),
      isReady: vi.fn(() => true),
      isPackaged: false,
      on: vi.fn(),
      exit: vi.fn(),
      quit: vi.fn(),
      requestSingleInstanceLock: vi.fn(() => true),
      setAsDefaultProtocolClient: vi.fn(),
      setLoginItemSettings: vi.fn(),
      whenReady: vi.fn(() => Promise.resolve()),
    },
    BrowserWindow,
    globalShortcut: {
      register: vi.fn(),
      unregister: vi.fn(),
    },
    ipcMain: {
      handle: vi.fn(),
      on: vi.fn(),
      removeHandler: vi.fn(),
    },
    Menu: {
      buildFromTemplate: vi.fn((template) => ({ template })),
      setApplicationMenu: vi.fn(),
    },
    nativeImage: {
      createFromDataURL: vi.fn(() => ({
        setTemplateImage: vi.fn(),
      })),
    },
    Notification: Object.assign(vi.fn(() => ({ on: vi.fn(), show: vi.fn() })), {
      isSupported: vi.fn(() => true),
    }),
    Tray: vi.fn(() => ({
      on: vi.fn(),
      setContextMenu: vi.fn(),
      setToolTip: vi.fn(),
    })),
  }

  vi.doMock('electron', () => electronMock)
  vi.doMock('../services/desktop-telemetry', () => ({
    recordDesktopStartupReport: vi.fn(() => Promise.resolve()),
    recordDesktopStartupTime: vi.fn(),
  }))
  vi.doMock('../services/crash-reporting', () => ({
    attachWindowCrashReporting: vi.fn(),
    initializeCrashReporting: vi.fn(),
  }))
  vi.doMock('../services/agent-service', () => ({
    registerAgentHandlers: vi.fn(),
  }))
  vi.doMock('../services/file-service', () => ({
    registerFileHandlers: vi.fn(),
  }))
  vi.doMock('../services/offline-sync-runtime', () => ({
    startDesktopOfflineSyncRuntime: vi.fn(),
  }))
  vi.doMock('../services/desktop-updates', () => ({
    checkForDesktopUpdates: vi.fn(),
    registerDesktopUpdateHandlers: vi.fn(),
  }))
  vi.doMock('../services/phase6-service', () => ({
    registerPhase6Handlers: vi.fn(),
  }))
  vi.doMock('../services/task-service', () => ({
    registerTaskHandlers: vi.fn(),
  }))
  return { electronMock, mockWindow }
}

async function waitForAppHandler(appOn: unknown, eventName: string) {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const handler = (appOn as any).mock.calls.find(
      (call: any[]) => call[0] === eventName
    )?.[1]
    if (handler) return handler as () => Promise<void> | void
    await new Promise((resolve) => setTimeout(resolve, 0))
  }
  return undefined
}

describe('Main Process Lifecycle', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.clearAllMocks()
  })

  test('should handle activate event on macOS', async () => {
    const { electronMock } = createElectronMock()
    const { app, BrowserWindow } = await import('electron')

    await import('../main')

    const activateHandler = await waitForAppHandler(app.on, 'activate')

    expect(activateHandler).toBeDefined()
    await activateHandler?.()

    expect(BrowserWindow).toHaveBeenCalled()
    expect(electronMock.app.quit).not.toHaveBeenCalled()
  })

  test('should keep background services alive on window-all-closed', async () => {
    createElectronMock()
    const { app } = await import('electron')

    await import('../main')

    const closedHandler = (app.on as any).mock.calls.find(
      (call: any[]) => call[0] === 'window-all-closed'
    )?.[1]

    expect(closedHandler).toBeDefined()
    closedHandler?.()

    expect(app.quit).not.toHaveBeenCalled()
  })

  test('should handle window closed event', async () => {
    const { mockWindow } = createElectronMock()
    const { createMainWindow } = await import('../main')

    await createMainWindow()

    const closedHandler = mockWindow.on.mock.calls.find(
      (call: any[]) => call[0] === 'closed'
    )?.[1]

    expect(closedHandler).toBeDefined()
    expect(() => closedHandler?.()).not.toThrow()
  })
})
