import { app, BrowserWindow, powerMonitor } from 'electron'
// Defer Sentry initialization until after app.whenReady()
// import { initializeCrashReporting } from './services/crash-reporting'
import { registerAgentHandlers } from './services/agent-service'
import { recordDesktopStartupReport } from './services/desktop-telemetry'
// Defer desktop-updates import to avoid module-level app.getVersion() call
// import { checkForDesktopUpdates, registerDesktopUpdateHandlers } from './services/desktop-updates'
import { registerFileHandlers } from './services/file-service'
import { registerRendererWorkspaceStorageHandlers } from './services/renderer-workspace-storage'
import { startDesktopOfflineSyncRuntime } from './services/offline-sync-runtime'
import { registerPhase6Handlers } from './services/phase6-service'
import {
  registerRendererProtocol,
  registerRendererSchemePrivileges,
} from './services/renderer-protocol'
import {
  hideMainWindow,
  registerEarlyProtocolHandlers,
  registerSystemIntegration,
  showMainWindow,
  shouldCloseToTray,
} from './services/system-integration'
import { registerTaskHandlers } from './services/task-service'
import {
  createHarnessWindow,
  loadRecoveryRendererInAllWindows,
  loadVerifiedRuntimeInAllWindows,
  registerDesktopWindowHandlers,
} from './services/window-manager'
import { LocalRuntimeManager, shouldStartManagedLocalRuntime } from './services/local-runtime'
import {
  registerLocalRuntimeSecretHandlers,
  setTrustedRuntimeSecretOrigin,
} from './services/local-runtime-secrets'
import { setLocalRuntimeBaseUrl } from './shared/api-client'
import { ensureSingleInstanceLock } from './services/app-instance'
import {
  DesktopStartupTracker,
  formatDesktopStartupBudgetReport,
  isDesktopStartupBudgetMode,
} from './services/startup-performance'
import { installProcessOutputErrorGuards } from './shared/process-output'

installProcessOutputErrorGuards()

let mainWindow: BrowserWindow | null = null
let localRuntimeManager: LocalRuntimeManager | null = null
let runtimeShutdownInProgress = false
let runtimeShutdownComplete = false
let appQuitRequested = false
export const appBootAt = Date.now()
const startupTracker = new DesktopStartupTracker({ startedAtMs: 0 })
const ownsSingleInstance = ensureSingleInstanceLock()

if (!ownsSingleInstance) {
  app.quit()
} else {
  registerRendererSchemePrivileges()
}

// Defer all module-level initialization that depends on Electron app APIs
// registerEarlyProtocolHandlers() - moved to app.whenReady()
// initializeCrashReporting() - moved to app.whenReady()

export async function createMainWindow(options: { deferInitialLoad?: boolean } = {}): Promise<BrowserWindow> {
  mainWindow = await createHarnessWindow({
    kind: 'main',
    route: '/agents/default/workspace',
    deferInitialLoad: options.deferInitialLoad,
  })

  mainWindow.on('close', (event) => {
    if (appQuitRequested) return
    if (!shouldCloseToTray()) return
    event.preventDefault()
    hideMainWindow()
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })

  return mainWindow
}

if (ownsSingleInstance) app.whenReady().then(async () => {
  startupTracker.mark('app_ready')
  registerRendererProtocol()
  const managedLocalRuntime = shouldStartManagedLocalRuntime()
  let runtimeAttachedToWindow = false
  if (managedLocalRuntime) {
    localRuntimeManager = new LocalRuntimeManager({
      onEndpoint: async (endpoint) => {
        setLocalRuntimeBaseUrl(endpoint.origin)
        setTrustedRuntimeSecretOrigin(endpoint.origin)
        if (!mainWindow || mainWindow.isDestroyed()) return
        await localRuntimeManager?.installDesktopSession(mainWindow.webContents.session)
        await loadVerifiedRuntimeInAllWindows()
        runtimeAttachedToWindow = true
      },
      onUnavailable: (error) => {
        console.error(`Harness local runtime unavailable: ${error.message}`)
        setLocalRuntimeBaseUrl(null)
        setTrustedRuntimeSecretOrigin(null)
        void loadRecoveryRendererInAllWindows()
      },
    })
    powerMonitor.on('resume', () => {
      void localRuntimeManager?.renewDesktopSession().catch((error: unknown) => {
        const message = error instanceof Error ? error.message : String(error)
        console.error(`Harness desktop session resume renewal failed: ${message}`)
      })
    })
  }
  const runtimeStartup = localRuntimeManager
    ? localRuntimeManager.start().then(() => null, (error: unknown) => (
        error instanceof Error ? error : new Error(String(error))
      ))
    : null

  // Initialize crash reporting after app is ready
  const { initializeCrashReporting } = await import('./services/crash-reporting')
  initializeCrashReporting()

  // Register protocol handlers after app is ready
  registerEarlyProtocolHandlers()

  registerAgentHandlers()
  registerFileHandlers()
  registerRendererWorkspaceStorageHandlers()
  registerPhase6Handlers()
  registerTaskHandlers()
  if (!managedLocalRuntime) {
    startDesktopOfflineSyncRuntime()
  }
  registerDesktopWindowHandlers()
  registerSystemIntegration({
    getMainWindow: () => mainWindow,
    createMainWindow,
  })

  // Dynamically import desktop-updates to avoid module-level app.getVersion() call
  const { registerDesktopUpdateHandlers, checkForDesktopUpdates } = await import('./services/desktop-updates')
  registerDesktopUpdateHandlers({
    getMainWindow: () => mainWindow,
  })

  startupTracker.mark('services_ready')
  await createMainWindow({ deferInitialLoad: managedLocalRuntime })
  registerLocalRuntimeSecretHandlers({
    getModelStatus: () => localRuntimeManager
      ? localRuntimeManager.getModelStatus()
      : Promise.reject(new Error('managed local runtime is unavailable')),
    saveModelConfiguration: (input) => localRuntimeManager
      ? localRuntimeManager.saveModelConfiguration(input)
      : Promise.reject(new Error('managed local runtime is unavailable')),
    discoverModels: (input) => localRuntimeManager
      ? localRuntimeManager.discoverModels(input)
      : Promise.reject(new Error('managed local runtime is unavailable')),
    applyModelApiKey: (value) => localRuntimeManager
      ? localRuntimeManager.applyModelApiKey(value)
      : Promise.reject(new Error('managed local runtime is unavailable')),
    deleteModelApiKey: () => localRuntimeManager
      ? localRuntimeManager.deleteModelApiKey()
      : Promise.reject(new Error('managed local runtime is unavailable')),
    renewSession: () => localRuntimeManager
      ? localRuntimeManager.renewDesktopSession()
      : Promise.reject(new Error('managed local runtime is unavailable')),
    openWebExtension: () => localRuntimeManager
      ? localRuntimeManager.openWebExtension()
      : Promise.reject(new Error('managed local runtime is unavailable')),
  })
  if (runtimeStartup) {
    const startupError = await runtimeStartup
    if (startupError) {
      console.error(`Harness local runtime startup failed: ${startupError.message}`)
      await loadRecoveryRendererInAllWindows()
    } else if (!runtimeAttachedToWindow && localRuntimeManager && mainWindow && !mainWindow.isDestroyed()) {
      await localRuntimeManager.installDesktopSession(mainWindow.webContents.session)
      await loadVerifiedRuntimeInAllWindows()
    }
  }
  startupTracker.mark('renderer_loaded')
  const startupReport = startupTracker.report({
    appVersion: typeof app.getVersion === 'function'
      ? app.getVersion()
      : process.env.npm_package_version || '0.1.0',
    packaged: app.isPackaged,
  })
  if (isDesktopStartupBudgetMode()) {
    process.stdout.write(`${formatDesktopStartupBudgetReport(startupReport)}\n`, () => {
      const exitCode = startupReport.passed ? 0 : 1
      const runtime = localRuntimeManager
      localRuntimeManager = null
      if (!runtime) {
        app.exit(exitCode)
        return
      }
      void runtime.stop().catch((error: unknown) => {
        const message = error instanceof Error ? error.message : String(error)
        console.error(`Harness local runtime smoke shutdown failed: ${message}`)
      }).finally(() => app.exit(exitCode))
    })
    return
  }
  void recordDesktopStartupReport(startupReport).catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error)
    console.warn(`Harness Desktop startup telemetry failed: ${message}`)
  })
  if (app.isPackaged) {
    void checkForDesktopUpdates()
  }

  app.on('activate', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      void showMainWindow()
    } else if (BrowserWindow.getAllWindows().length === 0) {
      void createMainWindow()
    }
  })
}).catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error)
  console.error(`Harness Desktop startup failed: ${message}`)
  if (isDesktopStartupBudgetMode()) {
    app.exit(1)
  }
})

app.on('window-all-closed', () => {
  // Harness keeps background sync and local Agent notifications alive through the tray.
})

app.on('before-quit', (event) => {
  appQuitRequested = true
  const runtime = localRuntimeManager
  if (!runtime || runtimeShutdownComplete) return
  event.preventDefault()
  if (runtimeShutdownInProgress) return
  runtimeShutdownInProgress = true
  localRuntimeManager = null
  setLocalRuntimeBaseUrl(null)
  setTrustedRuntimeSecretOrigin(null)
  void runtime.stop().catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error)
    console.error(`Harness local runtime shutdown failed: ${message}`)
  }).finally(() => {
    runtimeShutdownComplete = true
    runtimeShutdownInProgress = false
    app.quit()
  })
})
