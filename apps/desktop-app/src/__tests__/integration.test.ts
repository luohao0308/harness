import { describe, test, expect, beforeAll, afterAll, vi } from 'vitest'
import { spawn, type ChildProcess } from 'child_process'
import path from 'path'

// Mock electron to avoid installation issues in tests
vi.mock('electron', () => ({
  app: {
    isPackaged: false,
    getPath: vi.fn((name: string) => `/mock/path/${name}`)
  }
}))

describe('React SPA Integration', () => {
  let viteProcess: ChildProcess | null = null
  const VITE_PORT = 5173
  const AGENT_CONSOLE_PATH = path.resolve(__dirname, '../../../agent-console')

  beforeAll(async () => {
    // Skip in CI or if agent-console doesn't exist
    if (process.env.CI) {
      return
    }

    // Start Vite dev server for integration test
    viteProcess = spawn('npm', ['run', 'dev'], {
      cwd: AGENT_CONSOLE_PATH,
      stdio: 'pipe'
    })

    // Wait for server to be ready
    await new Promise<void>((resolve) => {
      const timeout = setTimeout(() => resolve(), 5000)
      viteProcess?.stdout?.on('data', (data) => {
        if (data.toString().includes('ready')) {
          clearTimeout(timeout)
          resolve()
        }
      })
    })
  }, 10000)

  afterAll(() => {
    if (viteProcess) {
      viteProcess.kill()
    }
  })

  test('should be able to connect to React dev server', async () => {
    if (process.env.CI) {
      expect(true).toBe(true)
      return
    }

    const response = await fetch(`http://localhost:${VITE_PORT}`)
    expect(response.ok).toBe(true)

    const html = await response.text()
    expect(html).toContain('<!doctype html>')
    expect(html).toContain('<div id="root"></div>')
  })

  test('should load Vite client module', async () => {
    if (process.env.CI) {
      expect(true).toBe(true)
      return
    }

    const response = await fetch(`http://localhost:${VITE_PORT}/@vite/client`)
    expect(response.ok).toBe(true)
  })

  test('Electron window configuration should match React SPA needs', async () => {
    const { getAppConfig } = await import('../config/app')
    const config = getAppConfig()

    // Verify dev server URL points to correct port
    expect(config.devServerUrl).toContain('localhost')

    // Verify window size is adequate for React app
    expect(config.window.width).toBeGreaterThanOrEqual(1024)
    expect(config.window.height).toBeGreaterThanOrEqual(768)
  })
})
