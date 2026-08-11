import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'

describe('desktop window manager', () => {
  let userDataRoot: string
  let windowId: number
  let createdWindows: Array<{
    id: number
    options: unknown
    loadURL: ReturnType<typeof vi.fn>
    loadFile: ReturnType<typeof vi.fn>
    on: ReturnType<typeof vi.fn>
    getBounds: ReturnType<typeof vi.fn>
    show: ReturnType<typeof vi.fn>
    focus: ReturnType<typeof vi.fn>
    isDestroyed: ReturnType<typeof vi.fn>
    isFocused: ReturnType<typeof vi.fn>
    isMaximized: ReturnType<typeof vi.fn>
    isMinimized: ReturnType<typeof vi.fn>
    isVisible: ReturnType<typeof vi.fn>
    restore: ReturnType<typeof vi.fn>
    maximize: ReturnType<typeof vi.fn>
    webContents: {
      openDevTools: ReturnType<typeof vi.fn>
      once: ReturnType<typeof vi.fn>
      on: ReturnType<typeof vi.fn>
      send: ReturnType<typeof vi.fn>
      setWindowOpenHandler: ReturnType<typeof vi.fn>
    }
    emitForTest: (event: string) => void
  }>

  beforeEach(() => {
    vi.resetModules()
    userDataRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'desktop-windows-'))
    windowId = 0
    createdWindows = []

    vi.doMock('electron', () => {
      const BrowserWindow = vi.fn((options: unknown) => {
        const events = new Map<string, () => void>()
        const window = {
          id: ++windowId,
          options,
          loadURL: vi.fn(() => Promise.resolve()),
          loadFile: vi.fn(() => Promise.resolve()),
          on: vi.fn((event: string, callback: () => void) => {
            events.set(event, callback)
          }),
          getBounds: vi.fn(() => ({ x: 25, y: 35, width: 1440, height: 900 })),
          show: vi.fn(),
          focus: vi.fn(),
          isDestroyed: vi.fn(() => false),
          isFocused: vi.fn(() => true),
          isMaximized: vi.fn(() => false),
          isMinimized: vi.fn(() => false),
          isVisible: vi.fn(() => true),
          restore: vi.fn(),
          maximize: vi.fn(),
          webContents: {
            openDevTools: vi.fn(),
            once: vi.fn(),
            on: vi.fn(),
            send: vi.fn(),
            setWindowOpenHandler: vi.fn(),
          },
          emitForTest: (event: string) => events.get(event)?.(),
        }
        createdWindows.push(window)
        return window
      })
      return {
        app: {
          getPath: vi.fn(() => userDataRoot),
          isPackaged: false,
        },
        BrowserWindow,
        ipcMain: {
          handle: vi.fn(),
        },
        shell: {
          openExternal: vi.fn(() => Promise.resolve()),
        },
      }
    })

    vi.doMock('../services/crash-reporting', () => ({
      attachWindowCrashReporting: vi.fn(),
    }))
  })

  afterEach(() => {
    vi.restoreAllMocks()
    fs.rmSync(userDataRoot, { recursive: true, force: true })
  })

  test('opens each Agent Run in its own reusable window', async () => {
    const { createHarnessWindow, listDesktopWindows } = await import('../services/window-manager')

    const first = await createHarnessWindow({ kind: 'run', runId: 'run-1' })
    const second = await createHarnessWindow({ kind: 'run', runId: 'run-1' })
    const third = await createHarnessWindow({ kind: 'run', runId: 'run-2' })

    expect(first).toBe(second)
    expect(third).not.toBe(first)
    expect(createdWindows).toHaveLength(2)
    expect(createdWindows[0].loadURL).toHaveBeenCalledWith('http://localhost:5173/runs/run-1')
    expect(createdWindows[1].loadURL).toHaveBeenCalledWith('http://localhost:5173/runs/run-2')
    expect(createdWindows[0].show).toHaveBeenCalled()
    expect(createdWindows[0].focus).toHaveBeenCalled()
    expect(listDesktopWindows().map((item) => item.runId)).toEqual(['run-1', 'run-2'])
  })

  test('defers the initial renderer for a managed-runtime window', async () => {
    const { createHarnessWindow } = await import('../services/window-manager')

    await createHarnessWindow({ kind: 'main', deferInitialLoad: true })

    expect(createdWindows[0].loadURL).not.toHaveBeenCalled()
  })

  test('persists window bounds by profile and window key', async () => {
    const { createHarnessWindow } = await import('../services/window-manager')
    const { readPhase6State } = await import('../services/phase6-store')

    await createHarnessWindow({ kind: 'run', runId: 'run-42' })
    createdWindows[0].emitForTest('resize')

    const state = readPhase6State()
    expect(state.windows['default:run:run-42']).toMatchObject({
      width: 1440,
      height: 900,
      x: 25,
      y: 35,
      maximized: false,
    })
  })

  test('denies renderer-created windows and blocks cross-origin navigation', async () => {
    const { createHarnessWindow } = await import('../services/window-manager')

    await createHarnessWindow({ kind: 'main', route: '/' })

    const window = createdWindows[0]
    expect(window.webContents.setWindowOpenHandler).toHaveBeenCalled()
    const openHandler = window.webContents.setWindowOpenHandler.mock.calls[0]?.[0]
    expect(openHandler({ url: 'https://example.test/docs' })).toEqual({ action: 'deny' })

    const navigationHandler = window.webContents.on.mock.calls.find((call) => call[0] === 'will-navigate')?.[1]
    const preventDefault = vi.fn()
    navigationHandler?.({ preventDefault }, 'https://evil.example.test/')
    expect(preventDefault).toHaveBeenCalled()

    preventDefault.mockClear()
    navigationHandler?.({ preventDefault }, 'http://localhost:5173/runs/run-1')
    expect(preventDefault).not.toHaveBeenCalled()
  })
})
