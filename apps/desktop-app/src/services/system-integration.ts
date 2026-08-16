import {
  app,
  BrowserWindow,
  globalShortcut,
  ipcMain,
  Menu,
  nativeImage,
  Notification,
  Tray,
  type MenuItemConstructorOptions,
} from 'electron'
import type { AgentEvent, DesktopRoutePayload, SystemNotificationOptions } from '../preload-api'
import { ensureSingleInstanceLock } from './app-instance'

const APP_NAME = 'Harness Desktop'
const DEEP_LINK_PROTOCOL = 'agentharness'
const WAKE_SHORTCUT = 'CommandOrControl+Shift+A'
const TRAY_ICON_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <rect width="16" height="16" rx="4" fill="#0f172a"/>
  <path d="M4 11.5V4.5h2v2.6h4V4.5h2v7h-2V8.9H6v2.6H4Z" fill="#f8fafc"/>
</svg>`

type WindowProvider = () => BrowserWindow | null
type WindowFactory = () => Promise<BrowserWindow>

export interface SystemIntegrationOptions {
  getMainWindow: WindowProvider
  createMainWindow: WindowFactory
}

let getMainWindow: WindowProvider = () => null
let createMainWindow: WindowFactory | null = null
let tray: Tray | null = null
let isQuitting = false
let pendingRoute: DesktopRoutePayload | null = null
let systemHandlersRegistered = false
let protocolHandlersRegistered = false

export function registerSystemIntegration(options: SystemIntegrationOptions): void {
  getMainWindow = options.getMainWindow
  createMainWindow = options.createMainWindow

  registerEarlyProtocolHandlers()
  registerNativeMenu()
  registerTray()
  registerGlobalShortcut()
  registerSystemIpcHandlers()

  app.on('will-quit', () => {
    isQuitting = true
    globalShortcut.unregister(WAKE_SHORTCUT)
  })
}

export function registerEarlyProtocolHandlers(): void {
  if (protocolHandlersRegistered) return
  protocolHandlersRegistered = true

  // Check if app is ready before calling Electron app APIs
  if (!app.isReady()) {
    // Store flag and register handlers after app is ready
    app.whenReady().then(() => {
      doRegisterProtocolHandlers()
    })
    return
  }

  doRegisterProtocolHandlers()
}

function doRegisterProtocolHandlers(): void {
  const singleInstanceApi = app as unknown as {
    setAsDefaultProtocolClient?: (protocol: string) => boolean
  }

  singleInstanceApi.setAsDefaultProtocolClient?.(DEEP_LINK_PROTOCOL)

  if (!ensureSingleInstanceLock()) {
    app.quit()
    return
  }

  app.on('open-url', (event, rawUrl) => {
    event.preventDefault()
    const route = routeFromDeepLink(rawUrl)
    if (route) routeMainWindow(route, 'deep-link')
  })

  app.on('second-instance', (_event, argv) => {
    const route = argv.map(routeFromDeepLink).find((value): value is string => Boolean(value))
    if (route) routeMainWindow(route, 'deep-link')
    else void showMainWindow()
  })
}

export function shouldCloseToTray(): boolean {
  return !isQuitting && tray !== null
}

export function hideMainWindow(): void {
  const window = getMainWindow()
  if (!window || window.isDestroyed()) return
  window.hide()
}

export async function showMainWindow(route?: string): Promise<void> {
  const window = await ensureMainWindow()
  if (!window || window.isDestroyed()) return

  if (typeof window.isMinimized === 'function' && window.isMinimized()) {
    window.restore()
  }
  window.show()
  window.focus()

  if (route) {
    routeMainWindow(route, 'ipc')
  }
}

export function requestQuit(): void {
  isQuitting = true
  app.quit()
}

export function routeFromDeepLink(rawUrl: string): string | null {
  try {
    const url = new URL(rawUrl)
    if (url.protocol !== `${DEEP_LINK_PROTOCOL}:`) return null

    const explicitRoute = url.searchParams.get('route')
    if (explicitRoute) return normalizeConsoleRoute(explicitRoute)

    const runId = url.searchParams.get('run_id') || url.searchParams.get('runId')
    if (runId) return normalizeConsoleRoute(`/runs/${encodeURIComponent(runId)}`)

    const teamId = url.searchParams.get('team_id') || url.searchParams.get('teamId')
    if (teamId) return normalizeConsoleRoute(`/teams/${encodeURIComponent(teamId)}`)

    const agentId = url.searchParams.get('agent_id') || url.searchParams.get('agentId')
    if (agentId) {
      const suffix = url.searchParams.toString()
      const route = `/agents/${encodeURIComponent(agentId)}/workspace${suffix ? `?${suffix}` : ''}`
      return normalizeConsoleRoute(route)
    }

    const hostPath = url.hostname ? `/${url.hostname}${url.pathname}` : url.pathname
    if (hostPath && hostPath !== '/') {
      return normalizeConsoleRoute(`${hostPath}${url.search}${url.hash}`)
    }

    return '/'
  } catch {
    return null
  }
}

export function notificationFromAgentEvent(event: AgentEvent): SystemNotificationOptions | null {
  const eventType = event.event_type.toUpperCase()
  const route = routeForEvent(event)
  const title = titleFromPayload(event) || 'Harness 运行'

  if (eventType.includes('CONFLICT')) {
    return {
      kind: 'conflict',
      title: '检测到同步冲突',
      body: `${title} 需要处理冲突。`,
      route,
    }
  }

  if (eventType.includes('FAILED') || eventType.includes('ERROR')) {
    return {
      kind: 'error',
      title: '任务出错',
      body: `${title} 需要查看错误详情。`,
      route,
    }
  }

  if (eventType.includes('COMPLETED') || eventType.includes('DONE')) {
    return {
      kind: 'completed',
      title: '任务已完成',
      body: `${title} 已完成。点击查看运行详情。`,
      route,
    }
  }

  return null
}

export function showSystemNotification(options: SystemNotificationOptions): void {
  if (typeof Notification.isSupported === 'function' && !Notification.isSupported()) {
    return
  }

  const notification = new Notification({
    title: options.title,
    body: options.body,
    silent: options.silent ?? false,
  })

  if (options.route) {
    notification.on('click', () => {
      routeMainWindow(options.route!, 'notification')
    })
  }

  notification.show()
}

export function notifyForAgentEvent(event: AgentEvent): void {
  const notification = notificationFromAgentEvent(event)
  if (notification) {
    showSystemNotification(notification)
  }
}

export function routeMainWindow(route: string, source: DesktopRoutePayload['source']): void {
  const normalizedRoute = normalizeConsoleRoute(route)
  if (!normalizedRoute) return

  const payload: DesktopRoutePayload = { route: normalizedRoute, source }
  pendingRoute = payload

  void showMainWindow().then(() => {
    const window = getMainWindow()
    if (!window || window.isDestroyed()) return
    window.webContents.send('system:open-route', payload)
  })
}

function registerSystemIpcHandlers(): void {
  if (systemHandlersRegistered) return
  systemHandlersRegistered = true

  ipcMain.handle('system:show-window', async (_event, route?: string) => {
    await showMainWindow(route)
  })
  ipcMain.handle('system:hide-window', () => {
    hideMainWindow()
  })
  ipcMain.handle('system:get-startup-enabled', () => {
    return app.getLoginItemSettings().openAtLogin
  })
  ipcMain.handle('system:set-startup-enabled', (_event, enabled: boolean) => {
    app.setLoginItemSettings({
      openAtLogin: enabled,
      openAsHidden: true,
    })
    registerNativeMenu()
    registerTray()
    return app.getLoginItemSettings().openAtLogin
  })
  ipcMain.handle('system:notify', (_event, options: SystemNotificationOptions) => {
    showSystemNotification(options)
  })
  ipcMain.handle('system:get-pending-route', () => {
    const route = pendingRoute
    pendingRoute = null
    return route
  })
}

async function ensureMainWindow(): Promise<BrowserWindow | null> {
  const existing = getMainWindow()
  if (existing && !existing.isDestroyed()) return existing
  return createMainWindow ? createMainWindow() : null
}

function registerTray(): void {
  if (!Tray) return
  if (!tray) {
    const image = nativeImage.createFromDataURL(
      `data:image/svg+xml;base64,${Buffer.from(TRAY_ICON_SVG).toString('base64')}`
    )
    image.setTemplateImage(true)
    tray = new Tray(image)
    tray.setToolTip(`${APP_NAME} - 后台运行中`)
    tray.on('click', () => {
      void showMainWindow()
    })
  }

  tray.setContextMenu(Menu.buildFromTemplate(buildTrayMenuTemplate()))
}

function registerNativeMenu(): void {
  Menu.setApplicationMenu(Menu.buildFromTemplate(buildApplicationMenuTemplate()))
}

function registerGlobalShortcut(): void {
  globalShortcut.unregister(WAKE_SHORTCUT)
  globalShortcut.register(WAKE_SHORTCUT, () => {
    void showMainWindow()
  })
}

function buildTrayMenuTemplate(): MenuItemConstructorOptions[] {
  return [
    {
      label: '打开 Harness',
      accelerator: WAKE_SHORTCUT,
      click: () => void showMainWindow(),
    },
    {
      label: '新建 Agent 运行',
      click: () => routeMainWindow('/agents/default/workspace', 'menu'),
    },
    {
      label: '运行记录',
      click: () => routeMainWindow('/runs', 'menu'),
    },
    {
      label: 'Agent Studio',
      click: () => routeMainWindow('/agents', 'menu'),
    },
    { type: 'separator' },
    {
      label: '开机自动启动',
      type: 'checkbox',
      checked: app.getLoginItemSettings().openAtLogin,
      click: (item) => {
        app.setLoginItemSettings({
          openAtLogin: item.checked,
          openAsHidden: true,
        })
        registerNativeMenu()
      },
    },
    { type: 'separator' },
    {
      label: '退出 Harness',
      role: 'quit',
      click: requestQuit,
    },
  ]
}

function buildApplicationMenuTemplate(): MenuItemConstructorOptions[] {
  const isMac = process.platform === 'darwin'
  const startupEnabled = app.getLoginItemSettings().openAtLogin

  const appMenu: MenuItemConstructorOptions[] = isMac
    ? [
        {
          label: APP_NAME,
          submenu: [
            { role: 'about' },
            { type: 'separator' },
            {
              label: '开机自动启动',
              type: 'checkbox',
              checked: startupEnabled,
              click: (item) => {
                app.setLoginItemSettings({ openAtLogin: item.checked, openAsHidden: true })
                registerTray()
              },
            },
            { type: 'separator' },
            { role: 'hide' },
            { role: 'hideOthers' },
            { role: 'unhide' },
            { type: 'separator' },
            { label: '退出 Harness', accelerator: 'Command+Q', click: requestQuit },
          ],
        },
      ]
    : []

  return [
    ...appMenu,
    {
      label: '文件',
      submenu: [
        {
          label: '新建 Agent 运行',
          accelerator: 'CommandOrControl+N',
          click: () => routeMainWindow('/agents/default/workspace', 'menu'),
        },
        {
          label: '打开运行记录',
          accelerator: 'CommandOrControl+R',
          click: () => routeMainWindow('/runs', 'menu'),
        },
        { type: 'separator' },
        isMac
          ? { label: '关闭窗口', accelerator: 'Command+W', click: hideMainWindow }
          : { label: '退出 Harness', accelerator: 'Alt+F4', click: requestQuit },
      ],
    },
    {
      label: '编辑',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'selectAll' },
      ],
    },
    {
      label: '视图',
      submenu: [
        {
          label: '唤醒窗口',
          accelerator: WAKE_SHORTCUT,
          click: () => void showMainWindow(),
        },
        { role: 'reload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
      ],
    },
    {
      label: '导航',
      submenu: [
        { label: '看板', accelerator: 'CommandOrControl+1', click: () => routeMainWindow('/', 'menu') },
        { label: 'Agent Studio', accelerator: 'CommandOrControl+2', click: () => routeMainWindow('/agents', 'menu') },
        { label: '运行记录', accelerator: 'CommandOrControl+3', click: () => routeMainWindow('/runs', 'menu') },
        { label: '观测', accelerator: 'CommandOrControl+4', click: () => routeMainWindow('/observability', 'menu') },
        { label: '模型设置', accelerator: 'CommandOrControl+,', click: () => routeMainWindow('/settings/models', 'menu') },
      ],
    },
    {
      label: '窗口',
      submenu: [
        { role: 'minimize' },
        { role: 'zoom' },
        ...(isMac ? ([{ type: 'separator' }, { role: 'front' }] as MenuItemConstructorOptions[]) : []),
      ],
    },
    {
      label: '帮助',
      submenu: [
        { label: '帮助中心', click: () => routeMainWindow('/help', 'menu') },
        { label: '故障排查', click: () => routeMainWindow('/help/troubleshooting', 'menu') },
      ],
    },
  ]
}

function normalizeConsoleRoute(rawRoute: string): string {
  const trimmed = rawRoute.trim()
  if (!trimmed || trimmed.startsWith('//')) return '/'

  const parsed = new URL(trimmed, 'http://agentharness.local')
  return `${parsed.pathname || '/'}${parsed.search}${parsed.hash}`
}

function routeForEvent(event: AgentEvent): string {
  const payload = event.payload_json
  const runId = stringValue(payload.run_id) || stringValue(payload.agent_run_id) || event.agent_run_id
  if (runId) return `/runs/${encodeURIComponent(runId)}`
  const taskId = stringValue(payload.task_id)
  if (taskId) return `/runs/${encodeURIComponent(taskId)}`
  return '/runs'
}

function titleFromPayload(event: AgentEvent): string | null {
  return (
    stringValue(event.payload_json.title) ||
    stringValue(event.payload_json.task_title) ||
    stringValue(event.payload_json.goal) ||
    null
  )
}

function stringValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}
