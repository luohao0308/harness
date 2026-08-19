import { beforeEach, describe, expect, test, vi } from 'vitest'
import * as fs from 'node:fs'
import * as os from 'node:os'
import * as path from 'node:path'

describe('packaged renderer protocol', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  test('registers a secure standard scheme and maps renderer files through net.fetch', async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'packaged-renderer-'))
    const rendererRoot = path.join(root, 'renderer')
    fs.mkdirSync(path.join(rendererRoot, 'assets'), { recursive: true })
    fs.writeFileSync(path.join(rendererRoot, 'index.html'), '<!doctype html>')
    fs.writeFileSync(path.join(rendererRoot, 'assets', 'index.js'), 'export {}')
    const originalResourcesPath = process.resourcesPath
    Object.defineProperty(process, 'resourcesPath', { configurable: true, value: root })
    const fetch = vi.fn(() => Promise.resolve(new Response('ok')))
    const handle = vi.fn()
    const registerSchemesAsPrivileged = vi.fn()
    vi.doMock('electron', () => ({
      net: { fetch },
      protocol: { handle, registerSchemesAsPrivileged },
    }))

    try {
      const {
        PACKAGED_RENDERER_URL,
        registerRendererProtocol,
        registerRendererSchemePrivileges,
      } = await import('../services/renderer-protocol')

      registerRendererSchemePrivileges()
      registerRendererProtocol()

      expect(registerSchemesAsPrivileged).toHaveBeenCalledWith([
        expect.objectContaining({
          scheme: 'harness-app',
          privileges: expect.objectContaining({ standard: true, secure: true }),
        }),
      ])
      expect(PACKAGED_RENDERER_URL).toBe('harness-app://renderer/index.html')

      const handler = handle.mock.calls[0]?.[1]
      await handler(new Request('harness-app://renderer/assets/index.js'))
      expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/^file:.*renderer\/assets\/index\.js$/))
    } finally {
      Object.defineProperty(process, 'resourcesPath', { configurable: true, value: originalResourcesPath })
      fs.rmSync(root, { recursive: true, force: true })
    }
  })

  test('rejects requests for untrusted renderer hosts', async () => {
    const fetch = vi.fn()
    const handle = vi.fn()
    vi.doMock('electron', () => ({
      net: { fetch },
      protocol: { handle, registerSchemesAsPrivileged: vi.fn() },
    }))

    const { registerRendererProtocol } = await import('../services/renderer-protocol')
    registerRendererProtocol()

    const handler = handle.mock.calls[0]?.[1]
    const response = await handler(new Request('harness-app://untrusted/index.html'))
    expect(response.status).toBe(404)
    expect(fetch).not.toHaveBeenCalled()
  })

  test('returns an embedded recovery document instead of ERR_FILE_NOT_FOUND', async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'missing-recovery-renderer-'))
    const originalResourcesPath = process.resourcesPath
    const fetch = vi.fn(() => Promise.reject(Object.assign(new Error('ERR_FILE_NOT_FOUND'), { code: 'ERR_FILE_NOT_FOUND' })))
    const handle = vi.fn()
    vi.doMock('electron', () => ({
      net: { fetch },
      protocol: { handle, registerSchemesAsPrivileged: vi.fn() },
    }))

    try {
      const { registerRendererProtocol } = await import('../services/renderer-protocol')
      Object.defineProperty(process, 'resourcesPath', { configurable: true, value: root })
      registerRendererProtocol()

      const handler = handle.mock.calls[0]?.[1]
      const response = await handler(new Request('harness-app://renderer/index.html'))

      expect(response.status).toBe(200)
      expect(response.headers.get('content-security-policy')).toContain("default-src 'none'")
      expect(await response.text()).toContain('Forge Harness Desktop could not load')
    } finally {
      Object.defineProperty(process, 'resourcesPath', { configurable: true, value: originalResourcesPath })
      fs.rmSync(root, { recursive: true, force: true })
    }
  })
})
