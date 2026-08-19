import { beforeEach, describe, expect, test, vi } from 'vitest'

const handle = vi.fn()
const fromWebContents = vi.fn()
const getWindowWorkspaceState = vi.fn()

vi.mock('electron', () => ({
  BrowserWindow: { fromWebContents },
  ipcMain: { handle },
}))

vi.mock('../services/file-service', () => ({ getWindowWorkspaceState }))

describe('change review IPC', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.clearAllMocks()
  })

  test('registers fixed status, diff, and mutation channels against the current window root', async () => {
    const window = { id: 17 }
    fromWebContents.mockReturnValue(window)
    getWindowWorkspaceState.mockReturnValue({ rootPath: '/workspace', watching: false })
    const service = {
      getStatus: vi.fn(async () => ({ state: 'ready', files: [] })),
      getDiff: vi.fn(async () => ({ path: 'file.txt', sections: [] })),
      mutate: vi.fn(async () => ({ action: 'stage', status: 'completed' })),
    }
    const { registerChangeReviewHandlers } = await import('../services/change-review-service')
    registerChangeReviewHandlers(service as never)

    const handlers = new Map(handle.mock.calls.map(([channel, handler]) => [channel, handler]))
    const event = { sender: { id: 'sender' } }
    await handlers.get('change-review:get-status')?.(event)
    await handlers.get('change-review:get-diff')?.(event, 'file.txt')
    await handlers.get('change-review:mutate')?.(event, {
      action: 'stage',
      previewToken: 'preview',
      hunkIds: ['worktree:0'],
    })

    expect(service.getStatus).toHaveBeenCalledWith('/workspace')
    expect(service.getDiff).toHaveBeenCalledWith('/workspace', 'file.txt', window)
    expect(service.mutate).toHaveBeenCalledWith('/workspace', window, {
      action: 'stage',
      previewToken: 'preview',
      hunkIds: ['worktree:0'],
    })
  })
})
