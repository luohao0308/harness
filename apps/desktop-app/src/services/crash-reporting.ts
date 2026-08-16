// Temporarily disable Sentry to avoid module-level app.getAppPath() calls
// import * as Sentry from '@sentry/electron/main'
import { app, type BrowserWindow } from 'electron'
import { recordDesktopCrashEvent } from './desktop-telemetry'
import { redactSensitiveValue, redactSensitiveText } from '../shared/privacy-redaction'

export interface CrashReportingConfig {
  dsn: string
  environment: string
  release: string
}

type SentryMain = {
  captureException: (error: unknown) => void
  captureMessage: (message: string, context?: unknown) => void
  init: (options: unknown) => void
}

let crashReportingInitialized = false
let sentryMainForTests: SentryMain | null = null

export function getCrashReportingConfig(env: NodeJS.ProcessEnv = process.env): CrashReportingConfig | null {
  const dsn = env.HARNESS_DESKTOP_SENTRY_DSN || env.SENTRY_DSN
  if (!dsn) return null

  return {
    dsn,
    environment:
      env.HARNESS_DESKTOP_RELEASE_CHANNEL ||
      env.HARNESS_DESKTOP_UPDATE_CHANNEL ||
      env.SENTRY_ENVIRONMENT ||
      env.NODE_ENV ||
      'production',
    release: env.SENTRY_RELEASE || `harness-desktop@${getDesktopAppVersion()}`,
  }
}

export function initializeCrashReporting(): boolean {
  if (crashReportingInitialized) return true

  const config = getCrashReportingConfig()
  if (!config) return false

  try {
    // Dynamically import Sentry after app is ready to avoid module-level app.getAppPath() calls
    const Sentry = loadSentryMain()

    Sentry.init({
      dsn: config.dsn,
      environment: config.environment,
      release: config.release,
      tracesSampleRate: Number(process.env.SENTRY_TRACES_SAMPLE_RATE || '0.1'),
      enableLogs: true,
      beforeSend: (event: unknown) => redactSensitiveValue(event),
    })

    process.on('uncaughtException', (error) => {
      const message = redactSensitiveText(error.message)
      Sentry.captureException(new Error(message))
      void recordDesktopCrashEvent(message, { scope: 'main-process' })
    })
    process.on('unhandledRejection', (reason) => {
      const message = redactSensitiveText(String(reason))
      Sentry.captureException(new Error(message))
      void recordDesktopCrashEvent(message, { scope: 'main-process' })
    })

    crashReportingInitialized = true
    return true
  } catch (error) {
    console.error('Failed to initialize crash reporting:', error)
    return false
  }
}

export function attachWindowCrashReporting(window: BrowserWindow): void {
  if (!crashReportingInitialized) return

  try {
    const Sentry = loadSentryMain()

    window.webContents.on('render-process-gone', (_event, details) => {
      Sentry.captureMessage('renderer-process-gone', {
        level: 'fatal',
        extra: {
          reason: redactSensitiveText(String(details.reason)),
          exitCode: details.exitCode,
        },
      })
      void recordDesktopCrashEvent('renderer-process-gone', {
        scope: 'renderer',
        reason: redactSensitiveText(String(details.reason)),
        exitCode: details.exitCode,
      })
    })

    window.webContents.on('unresponsive', () => {
      Sentry.captureMessage('renderer-unresponsive', {
        level: 'warning',
      })
      void recordDesktopCrashEvent('renderer-unresponsive', { scope: 'renderer' })
    })
  } catch (error) {
    console.error('Failed to attach window crash reporting:', error)
  }
}

export function resetCrashReportingForTests(): void {
  crashReportingInitialized = false
}

export function setCrashReportingSentryForTests(sentry: SentryMain | null): void {
  sentryMainForTests = sentry
}

function getDesktopAppVersion(): string {
  return typeof app.getVersion === 'function'
    ? app.getVersion()
    : process.env.npm_package_version || '0.1.0'
}

function loadSentryMain(): SentryMain {
  return sentryMainForTests ?? require('@sentry/electron/main')
}
