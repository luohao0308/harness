import { beforeEach, describe, expect, test, vi } from 'vitest'

vi.mock('electron', () => ({
  app: {
    getVersion: vi.fn(() => '0.1.0'),
  },
}))

vi.mock('../services/desktop-telemetry', () => ({
  recordDesktopCrashEvent: vi.fn(),
}))

const sentry = {
  captureException: vi.fn(),
  captureMessage: vi.fn(),
  init: vi.fn(),
}

vi.mock('@sentry/electron/main', () => sentry)

describe('crash reporting', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    delete process.env.HARNESS_DESKTOP_SENTRY_DSN
    delete process.env.HARNESS_DESKTOP_UPDATE_CHANNEL
    delete process.env.SENTRY_DSN
    delete process.env.SENTRY_RELEASE
    const { resetCrashReportingForTests, setCrashReportingSentryForTests } = await import(
      '../services/crash-reporting'
    )
    resetCrashReportingForTests()
    setCrashReportingSentryForTests(sentry)
  })

  test('does not initialize Sentry without a DSN', async () => {
    const { initializeCrashReporting } = await import('../services/crash-reporting')

    expect(initializeCrashReporting()).toBe(false)
    expect(sentry.init).not.toHaveBeenCalled()
  })

  test('initializes Sentry with release and environment metadata', async () => {
    process.env.HARNESS_DESKTOP_SENTRY_DSN = 'https://public@example.com/1'
    process.env.HARNESS_DESKTOP_UPDATE_CHANNEL = 'beta'
    process.env.SENTRY_RELEASE = 'harness-desktop@0.2.0'
    const { initializeCrashReporting } = await import('../services/crash-reporting')

    expect(initializeCrashReporting()).toBe(true)
    expect(sentry.init).toHaveBeenCalledWith(
      expect.objectContaining({
        dsn: 'https://public@example.com/1',
        environment: 'beta',
        release: 'harness-desktop@0.2.0',
      })
    )
    const options = sentry.init.mock.calls[0]?.[0] as { beforeSend?: (event: unknown) => unknown }
    expect(options.beforeSend?.({ request: { headers: { authorization: 'Bearer secret-token' } } })).toEqual({
      request: { headers: { authorization: '[REDACTED]' } },
    })
  })

  test('captures renderer process crashes from BrowserWindow webContents', async () => {
    process.env.HARNESS_DESKTOP_SENTRY_DSN = 'https://public@example.com/1'
    const listeners = new Map<string, (...args: any[]) => void>()
    const window = {
      webContents: {
        on: vi.fn((event: string, callback: (...args: any[]) => void) => {
          listeners.set(event, callback)
        }),
      },
    }
    const { attachWindowCrashReporting, initializeCrashReporting } = await import('../services/crash-reporting')

    initializeCrashReporting()
    attachWindowCrashReporting(window as never)
    listeners.get('render-process-gone')?.({}, { reason: 'crashed', exitCode: 9 })

    expect(sentry.captureMessage).toHaveBeenCalledWith(
      'renderer-process-gone',
      expect.objectContaining({
        level: 'fatal',
        extra: expect.objectContaining({ reason: 'crashed', exitCode: 9 }),
      })
    )
  })
})
