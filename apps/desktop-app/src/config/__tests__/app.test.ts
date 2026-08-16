import { describe, test, expect, vi, beforeEach } from 'vitest'

// Mock electron before importing config
vi.mock('electron', () => ({
  app: {
    isPackaged: false,
    getPath: vi.fn((name: string) => `/mock/path/${name}`)
  }
}))

describe('App Config', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    delete process.env.HARNESS_DESKTOP_USE_PACKAGED_RENDERER
  })

  test('should return valid app configuration', async () => {
    const { getAppConfig } = await import('../app')
    const config = getAppConfig()

    expect(config).toMatchObject({
      devServerUrl: expect.stringContaining('http://localhost'),
      isDev: expect.any(Boolean),
      openDevTools: false,
      window: {
        width: expect.any(Number),
        height: expect.any(Number),
        minWidth: expect.any(Number),
        minHeight: expect.any(Number)
      }
    })
  })

  test('should have reasonable window dimensions', async () => {
    const { getAppConfig } = await import('../app')
    const config = getAppConfig()

    expect(config.window.width).toBeGreaterThanOrEqual(800)
    expect(config.window.height).toBeGreaterThanOrEqual(600)
    expect(config.window.minWidth).toBeLessThanOrEqual(config.window.width)
    expect(config.window.minHeight).toBeLessThanOrEqual(config.window.height)
  })

  test('should respect VITE_DEV_SERVER_URL environment variable', async () => {
    const originalEnv = process.env.VITE_DEV_SERVER_URL
    process.env.VITE_DEV_SERVER_URL = 'http://localhost:3000'

    const { getAppConfig } = await import('../app')
    const config = getAppConfig()
    expect(config.devServerUrl).toBe('http://localhost:3000')

    // Restore
    if (originalEnv) {
      process.env.VITE_DEV_SERVER_URL = originalEnv
    } else {
      delete process.env.VITE_DEV_SERVER_URL
    }
  })

  test('should only enable DevTools when explicitly requested', async () => {
    const originalEnv = process.env.HARNESS_DESKTOP_OPEN_DEVTOOLS
    delete process.env.HARNESS_DESKTOP_OPEN_DEVTOOLS
    vi.resetModules()

    let module = await import('../app')
    expect(module.getAppConfig().openDevTools).toBe(false)

    process.env.HARNESS_DESKTOP_OPEN_DEVTOOLS = '1'
    vi.resetModules()
    module = await import('../app')
    expect(module.getAppConfig().openDevTools).toBe(true)

    if (originalEnv) {
      process.env.HARNESS_DESKTOP_OPEN_DEVTOOLS = originalEnv
    } else {
      delete process.env.HARNESS_DESKTOP_OPEN_DEVTOOLS
    }
  })

  test('should use the packaged renderer for the startup budget harness', async () => {
    process.env.HARNESS_DESKTOP_USE_PACKAGED_RENDERER = '1'

    const { getAppConfig } = await import('../app')

    expect(getAppConfig().isDev).toBe(false)
    delete process.env.HARNESS_DESKTOP_USE_PACKAGED_RENDERER
  })
})
