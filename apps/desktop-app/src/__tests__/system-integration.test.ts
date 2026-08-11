import { beforeEach, describe, expect, test, vi } from 'vitest'
import type { AgentEvent } from '../preload-api'

function installElectronMock() {
  const loginSettings = { openAtLogin: false }
  const appOn = vi.fn()
  const ipcHandle = vi.fn()
  const notificationInstances: Array<{
    options: unknown
    on: ReturnType<typeof vi.fn>
    show: ReturnType<typeof vi.fn>
    click?: () => void
  }> = []

  const app = {
    getLoginItemSettings: vi.fn(() => ({ ...loginSettings })),
    isPackaged: false,
    isReady: vi.fn(() => true),
    on: appOn,
    quit: vi.fn(),
    requestSingleInstanceLock: vi.fn(() => true),
    setAsDefaultProtocolClient: vi.fn(),
    setLoginItemSettings: vi.fn((settings: { openAtLogin?: boolean }) => {
      loginSettings.openAtLogin = Boolean(settings.openAtLogin)
    }),
  }

  const tray = {
    on: vi.fn(),
    setContextMenu: vi.fn(),
    setToolTip: vi.fn(),
  }

  const Notification = Object.assign(vi.fn().mockImplementation((options: unknown) => {
    const instance: {
      options: unknown
      on: ReturnType<typeof vi.fn>
      show: ReturnType<typeof vi.fn>
      click?: () => void
    } = {
      options,
      on: vi.fn((event: string, callback: () => void) => {
        if (event === 'click') instance.click = callback
      }),
      show: vi.fn(),
    }
    notificationInstances.push(instance)
    return instance
  }), {
    isSupported: vi.fn(() => true),
  })

  const electronMock = {
    app,
    BrowserWindow: vi.fn(),
    globalShortcut: {
      register: vi.fn(),
      unregister: vi.fn(),
    },
    ipcMain: {
      handle: ipcHandle,
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
    Notification,
    Tray: vi.fn(() => tray),
  }

  vi.doMock('electron', () => electronMock)
  return { electronMock, notificationInstances, tray }
}

describe('system integration', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.clearAllMocks()
  })

  test('parses agentharness deep links into console routes', async () => {
    installElectronMock()
    const { routeFromDeepLink } = await import('../services/system-integration')

    expect(routeFromDeepLink('agentharness://open?route=/runs/run-1')).toBe('/runs/run-1')
    expect(routeFromDeepLink('agentharness://open?run_id=run-2')).toBe('/runs/run-2')
    expect(routeFromDeepLink('agentharness://open?team_id=team-1')).toBe('/teams/team-1')
    expect(routeFromDeepLink('agentharness://open?agent_id=default')).toBe(
      '/agents/default/workspace?agent_id=default'
    )
    expect(routeFromDeepLink('agentharness://runs/run-3?focus=events')).toBe('/runs/run-3?focus=events')
    expect(routeFromDeepLink('agentharness:///runs/run-4')).toBe('/runs/run-4')
    expect(routeFromDeepLink('https://example.test/runs/run-5')).toBeNull()
  })

  test('registers tray, native menu, login item IPC, global shortcut, and protocol handlers', async () => {
    const { electronMock } = installElectronMock()
    const { registerSystemIntegration } = await import('../services/system-integration')

    registerSystemIntegration({
      getMainWindow: () => null,
      createMainWindow: vi.fn(async () => null as never),
    })

    expect(electronMock.app.setAsDefaultProtocolClient).toHaveBeenCalledWith('agentharness')
    expect(electronMock.app.requestSingleInstanceLock).toHaveBeenCalled()
    expect(electronMock.Tray).toHaveBeenCalled()
    expect(electronMock.Menu.setApplicationMenu).toHaveBeenCalled()
    expect(electronMock.globalShortcut.register).toHaveBeenCalledWith(
      'CommandOrControl+Shift+A',
      expect.any(Function)
    )
    expect(electronMock.ipcMain.handle).toHaveBeenCalledWith(
      'system:set-startup-enabled',
      expect.any(Function)
    )

    const startupHandler = electronMock.ipcMain.handle.mock.calls.find(
      (call) => call[0] === 'system:set-startup-enabled'
    )?.[1]
    expect(startupHandler?.({}, true)).toBe(true)
    expect(electronMock.app.setLoginItemSettings).toHaveBeenCalledWith({
      openAtLogin: true,
      openAsHidden: true,
    })
  })

  test('maps terminal agent events to native notifications', async () => {
    installElectronMock()
    const { notificationFromAgentEvent } = await import('../services/system-integration')

    const baseEvent: AgentEvent = {
      id: 'evt-1',
      agent_run_id: 'run-1',
      event_type: 'TASK_COMPLETED',
      payload_json: { title: '构建桌面端' },
      created_at: '2026-06-26T00:00:00Z',
    }

    expect(notificationFromAgentEvent(baseEvent)).toMatchObject({
      kind: 'completed',
      title: '任务已完成',
      route: '/runs/run-1',
    })
    expect(notificationFromAgentEvent({ ...baseEvent, event_type: 'TASK_FAILED' })).toMatchObject({
      kind: 'error',
      title: '任务出错',
    })
    expect(notificationFromAgentEvent({ ...baseEvent, event_type: 'SYNC_CONFLICT_DETECTED' })).toMatchObject({
      kind: 'conflict',
      title: '检测到同步冲突',
    })
    expect(notificationFromAgentEvent({ ...baseEvent, event_type: 'TOKEN_STREAM' })).toBeNull()
  })

  test('routes to a console path when a notification is clicked', async () => {
    const { notificationInstances } = installElectronMock()
    const send = vi.fn()
    const window = {
      focus: vi.fn(),
      hide: vi.fn(),
      isDestroyed: vi.fn(() => false),
      isMinimized: vi.fn(() => false),
      restore: vi.fn(),
      show: vi.fn(),
      webContents: { send },
    }

    const { showSystemNotification } = await import('../services/system-integration')
    const { registerSystemIntegration } = await import('../services/system-integration')

    registerSystemIntegration({
      getMainWindow: () => window as never,
      createMainWindow: vi.fn(async () => window as never),
    })

    showSystemNotification({
      title: '任务已完成',
      body: '构建桌面端 已完成。',
      route: '/runs/run-1',
    })

    notificationInstances[0].click?.()
    await Promise.resolve()
    await Promise.resolve()

    expect(window.show).toHaveBeenCalled()
    expect(window.focus).toHaveBeenCalled()
    expect(send).toHaveBeenCalledWith('system:open-route', {
      route: '/runs/run-1',
      source: 'notification',
    })
  })
})
