import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest'

// Fresh mock for isolated test
const mockApi = {
  task: {
    get: vi.fn().mockResolvedValue({
      id: 'task-001',
      title: 'Test',
      status: 'RUNNING',
      model_provider: 'anthropic',
      model_name: 'claude-opus-4-6',
      max_runtime_seconds: 3600,
      max_subagents: 5,
      enable_sandbox: true,
      enable_network: true,
      created_at: '2026-06-25T10:00:00Z',
      updated_at: '2026-06-25T10:05:00Z',
      completed_at: null,
    })
  }
}

global.window = { desktopApi: mockApi } as any

describe('Isolated Polling', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  test('fresh import with waitFor', async () => {
    // Force fresh module import
    vi.resetModules()
    const { startTaskPolling } = await import('../task-adapter')
    const onUpdate = vi.fn()

    startTaskPolling('task-001', onUpdate, { intervalMs: 1000 })

    await vi.waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(1), { timeout: 5000 })
    expect(onUpdate).toHaveBeenCalledWith(expect.objectContaining({ id: 'task-001' }))
  })
})
