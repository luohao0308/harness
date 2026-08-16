import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import type { BrowserWindow } from 'electron'

// Mock Electron modules
vi.mock('electron', () => ({
  app: {
    whenReady: vi.fn(() => Promise.resolve()),
    exit: vi.fn(),
    quit: vi.fn(),
    on: vi.fn(),
    isPackaged: false,
    getPath: vi.fn((name: string) => `/mock/path/${name}`),
    getLoginItemSettings: vi.fn(() => ({ openAtLogin: false })),
    requestSingleInstanceLock: vi.fn(() => true),
    setAsDefaultProtocolClient: vi.fn(),
    setLoginItemSettings: vi.fn()
  },
  BrowserWindow: Object.assign(vi.fn().mockImplementation(() => ({
    id: Math.floor(Math.random() * 10000),
    loadURL: vi.fn(() => Promise.resolve()),
    loadFile: vi.fn(() => Promise.resolve()),
    on: vi.fn(),
    getBounds: vi.fn(() => ({ x: 10, y: 20, width: 1280, height: 800 })),
    hide: vi.fn(),
    show: vi.fn(),
    focus: vi.fn(),
    restore: vi.fn(),
    maximize: vi.fn(),
    webContents: {
      openDevTools: vi.fn(),
      once: vi.fn(),
      send: vi.fn()
    },
    isFocused: vi.fn(() => true),
    isMaximized: vi.fn(() => false),
    isMinimized: vi.fn(() => false),
    isDestroyed: vi.fn(() => false),
    isVisible: vi.fn(() => true),
    destroy: vi.fn()
  })), {
    getAllWindows: vi.fn(() => [])
  }),
  globalShortcut: {
    register: vi.fn(),
    unregister: vi.fn()
  },
  ipcMain: {
    handle: vi.fn(),
    removeHandler: vi.fn()
  },
  Menu: {
    buildFromTemplate: vi.fn((template) => ({ template })),
    setApplicationMenu: vi.fn()
  },
  nativeImage: {
    createFromDataURL: vi.fn(() => ({
      setTemplateImage: vi.fn()
    }))
  },
  powerMonitor: {
    on: vi.fn(),
  },
  Notification: Object.assign(vi.fn(() => ({
    on: vi.fn(),
    show: vi.fn()
  })), {
    isSupported: vi.fn(() => true)
  }),
  Tray: vi.fn(() => ({
    on: vi.fn(),
    setContextMenu: vi.fn(),
    setToolTip: vi.fn()
  }))
}))

vi.mock('../services/desktop-telemetry', () => ({
  recordDesktopStartupReport: vi.fn(() => Promise.resolve()),
  recordDesktopStartupTime: vi.fn(),
}))

vi.mock('../services/renderer-protocol', () => ({
  PACKAGED_RENDERER_URL: 'harness-app://renderer/index.html',
  RENDERER_HOST: 'renderer',
  RENDERER_SCHEME: 'harness-app',
  registerRendererProtocol: vi.fn(),
  registerRendererSchemePrivileges: vi.fn(),
}))

vi.mock('../services/crash-reporting', () => ({
  attachWindowCrashReporting: vi.fn(),
  initializeCrashReporting: vi.fn(),
}))

vi.mock('../services/agent-service', () => ({
  registerAgentHandlers: vi.fn(),
}))

vi.mock('../services/file-service', () => ({
  registerFileHandlers: vi.fn(),
}))

vi.mock('../services/renderer-workspace-storage', () => ({
  registerRendererWorkspaceStorageHandlers: vi.fn(),
}))

vi.mock('../services/offline-sync-runtime', () => ({
  startDesktopOfflineSyncRuntime: vi.fn(),
}))

vi.mock('../services/desktop-updates', () => ({
  checkForDesktopUpdates: vi.fn(),
  registerDesktopUpdateHandlers: vi.fn(),
}))

vi.mock('../services/phase6-service', () => ({
  registerPhase6Handlers: vi.fn(),
}))

vi.mock('../services/system-integration', () => ({
  hideMainWindow: vi.fn(),
  registerEarlyProtocolHandlers: vi.fn(),
  registerSystemIntegration: vi.fn(),
  showMainWindow: vi.fn(),
  shouldCloseToTray: vi.fn(() => false),
}))

vi.mock('../services/task-service', () => ({
  registerTaskHandlers: vi.fn(),
}))

vi.mock('../services/local-runtime', () => ({
  LocalRuntimeManager: vi.fn(() => ({
    start: vi.fn(() => Promise.reject(new Error('test runtime unavailable'))),
    stop: vi.fn(() => Promise.resolve()),
    getModelStatus: vi.fn(() => Promise.resolve()),
    saveModelConfiguration: vi.fn(() => Promise.resolve()),
    discoverModels: vi.fn(() => Promise.resolve()),
    applyModelApiKey: vi.fn(() => Promise.resolve()),
    deleteModelApiKey: vi.fn(() => Promise.resolve()),
    renewDesktopSession: vi.fn(() => Promise.resolve()),
    openWebExtension: vi.fn(() => Promise.resolve()),
  })),
  shouldStartManagedLocalRuntime: vi.fn(() => process.env.HARNESS_TEST_MANAGED_RUNTIME === '1'),
  getVerifiedRuntimeEndpoint: vi.fn(() => null),
}))

describe('Electron App Startup', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.clearAllMocks()
    delete process.env.HARNESS_DESKTOP_STARTUP_BUDGET_MODE
    delete process.env.HARNESS_TEST_MANAGED_RUNTIME
  })

  afterEach(() => {
    delete process.env.HARNESS_DESKTOP_STARTUP_BUDGET_MODE
    delete process.env.HARNESS_TEST_MANAGED_RUNTIME
    vi.clearAllMocks()
  })

  test('should create main window on app ready', async () => {
    const { BrowserWindow } = await import('electron')
    const { createMainWindow } = await import('../main')

    const window = await createMainWindow()

    expect(BrowserWindow).toHaveBeenCalled()
    expect(window).toBeDefined()
  })

  test('should load development server URL in dev mode', async () => {
    const { BrowserWindow } = await import('electron')
    const { createMainWindow } = await import('../main')

    const window = await createMainWindow()

    expect(window.loadURL).toHaveBeenCalledWith(
      'http://localhost:5173/agents/default/workspace'
    )
  })

  test('should configure window with correct dimensions', async () => {
    const { BrowserWindow } = await import('electron')
    const { createMainWindow } = await import('../main')

    await createMainWindow()

    const mockConstructor = BrowserWindow as unknown as ReturnType<typeof vi.fn>
    const callArgs = mockConstructor.mock.calls[mockConstructor.mock.calls.length - 1]?.[0]

    expect(callArgs).toMatchObject({
      width: expect.any(Number),
      height: expect.any(Number),
      webPreferences: {
        nodeIntegration: false,
        contextIsolation: true
      }
    })
  })

  test('should not open DevTools by default in development mode', async () => {
    const { createMainWindow } = await import('../main')

    const window = await createMainWindow()

    expect(window.webContents.openDevTools).not.toHaveBeenCalled()
  })

  test('should keep running in tray when all windows are closed', async () => {
    const { app } = await import('electron')

    // Simulate window-all-closed event
    const mockOn = app.on as ReturnType<typeof vi.fn>
    const windowClosedCallback = mockOn.mock.calls.find(
      call => call[0] === 'window-all-closed'
    )?.[1]

    if (windowClosedCallback) {
      windowClosedCallback()
      expect(app.quit).not.toHaveBeenCalled()
    }
  })

  test('does not open the legacy offline SQLite runtime in managed local mode', async () => {
    process.env.HARNESS_TEST_MANAGED_RUNTIME = '1'
    const offlineRuntime = await import('../services/offline-sync-runtime')

    await import('../main')

    await vi.waitFor(() => expect(offlineRuntime.startDesktopOfflineSyncRuntime).not.toHaveBeenCalled())
  })

  test('renews the managed local session after system resume', async () => {
    process.env.HARNESS_TEST_MANAGED_RUNTIME = '1'
    const { powerMonitor } = await import('electron')
    const runtimeModule = await import('../services/local-runtime')

    await import('../main')
    await vi.waitFor(() => expect(runtimeModule.LocalRuntimeManager).toHaveBeenCalled())
    const powerMonitorCalls = vi.mocked(powerMonitor.on).mock.calls as unknown as Array<[
      string,
      () => void,
    ]>
    const resume = powerMonitorCalls.find((call) => call[0] === 'resume')?.[1]
    const runtime = vi.mocked(runtimeModule.LocalRuntimeManager).mock.results[0]?.value

    resume?.()

    expect(runtime.renewDesktopSession).toHaveBeenCalledOnce()
  })

  test('waits for managed harnessd shutdown before allowing Electron to quit', async () => {
    process.env.HARNESS_TEST_MANAGED_RUNTIME = '1'
    const { app, BrowserWindow } = await import('electron')
    const runtimeModule = await import('../services/local-runtime')
    const systemIntegration = await import('../services/system-integration')

    await import('../main')
    await vi.waitFor(() => expect(runtimeModule.LocalRuntimeManager).toHaveBeenCalled())
    await vi.waitFor(() => expect(BrowserWindow).toHaveBeenCalled())
    const appOnCalls = vi.mocked(app.on).mock.calls as unknown as Array<[
      string,
      (event: { preventDefault: () => void }) => void,
    ]>
    const beforeQuit = appOnCalls.find((call) => call[0] === 'before-quit')?.[1]
    const runtime = vi.mocked(runtimeModule.LocalRuntimeManager).mock.results[0]?.value
    const preventDefault = vi.fn()

    beforeQuit?.({ preventDefault })

    expect(preventDefault).toHaveBeenCalledOnce()
    expect(runtime.stop).toHaveBeenCalledOnce()
    await vi.waitFor(() => expect(app.quit).toHaveBeenCalled())

    vi.mocked(systemIntegration.shouldCloseToTray).mockReturnValue(true)
    const mockWindow = vi.mocked(BrowserWindow).mock.results.at(-1)?.value
    const close = mockWindow.on.mock.calls.filter((call: unknown[]) => call[0] === 'close').at(-1)?.[1]
    const preventWindowClose = vi.fn()
    close?.({ preventDefault: preventWindowClose })

    expect(preventWindowClose).not.toHaveBeenCalled()
  })

  test('should expose boot timestamp for startup telemetry', async () => {
    const { appBootAt } = await import('../main')
    expect(typeof appBootAt).toBe('number')
  })

  test('should report startup only after the main renderer has loaded', async () => {
    let resolveLoad: (() => void) | undefined
    const { BrowserWindow } = await import('electron')
    const BrowserWindowMock = BrowserWindow as unknown as ReturnType<typeof vi.fn>
    const mockWindow = BrowserWindowMock()
    mockWindow.loadURL.mockImplementationOnce(
      () => new Promise<void>((resolve) => {
        resolveLoad = resolve
      }),
    )
    BrowserWindowMock.mockImplementationOnce(() => mockWindow)
    BrowserWindowMock.mockClear()

    const telemetry = await import('../services/desktop-telemetry')
    await import('../main')

    await vi.waitFor(() => expect(mockWindow.loadURL).toHaveBeenCalled())
    expect(telemetry.recordDesktopStartupReport).not.toHaveBeenCalled()

    resolveLoad?.()

    await vi.waitFor(() => expect(telemetry.recordDesktopStartupReport).toHaveBeenCalledOnce())
    expect(telemetry.recordDesktopStartupReport).toHaveBeenCalledWith(
      expect.objectContaining({
        timings_ms: expect.objectContaining({ total_ms: expect.any(Number) }),
      }),
    )
  })

  test('should flush the startup report before exiting budget mode', async () => {
    process.env.HARNESS_DESKTOP_STARTUP_BUDGET_MODE = '1'
    process.env.HARNESS_TEST_MANAGED_RUNTIME = '1'
    const { app } = await import('electron')
    let flushReport: (() => void) | undefined
    const writeSpy = vi.spyOn(process.stdout, 'write').mockImplementation(((...args: unknown[]) => {
      flushReport = args.find((argument) => typeof argument === 'function') as (() => void) | undefined
      return true
    }) as typeof process.stdout.write)

    try {
      await import('../main')

      await vi.waitFor(() => expect(writeSpy).toHaveBeenCalledOnce())
      expect(app.exit).not.toHaveBeenCalled()
      const output = String(writeSpy.mock.calls[0][0])
      const report = JSON.parse(output.slice(output.indexOf('{')))
      expect(output).toContain('HARNESS_DESKTOP_STARTUP_REPORT ')

      flushReport?.()

      const runtimeModule = await import('../services/local-runtime')
      const runtime = vi.mocked(runtimeModule.LocalRuntimeManager).mock.results[0]?.value
      expect(runtime.stop).toHaveBeenCalledOnce()
      await vi.waitFor(() => expect(app.exit).toHaveBeenCalledWith(report.passed ? 0 : 1))
    } finally {
      writeSpy.mockRestore()
    }
  })

})
