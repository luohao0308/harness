import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest'
import type { AgentEvent, SseConnectionStatus } from '../preload-api'

describe('SSE Bridge', () => {
  let mockWebContents: {
    send: ReturnType<typeof vi.fn>
  }
  let mockNotifyForAgentEvent: ReturnType<typeof vi.fn>
  let mockEventSource: {
    addEventListener: ReturnType<typeof vi.fn>
    close: ReturnType<typeof vi.fn>
    readyState: number
  }

  beforeEach(() => {
    vi.resetModules()
    mockWebContents = {
      send: vi.fn(),
    }

    mockEventSource = {
      addEventListener: vi.fn(),
      close: vi.fn(),
      readyState: 1, // OPEN
    }

    vi.doMock('electron', () => ({
      BrowserWindow: {
        getAllWindows: () => [{ webContents: mockWebContents }],
      },
    }))
    mockNotifyForAgentEvent = vi.fn()
    vi.doMock('../services/system-integration', () => ({
      notifyForAgentEvent: mockNotifyForAgentEvent,
    }))

    global.EventSource = vi.fn(() => mockEventSource) as any
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('createSseBridge', () => {
    test('should establish SSE connection', async () => {
      const { createSseBridge } = await import('../services/sse-bridge')

      createSseBridge('task-123', null)

      expect(global.EventSource).toHaveBeenCalledWith(
        expect.stringContaining('/api/tasks/task-123/events/stream')
      )
    })

    test('should include lastEventId in URL when provided', async () => {
      const { createSseBridge } = await import('../services/sse-bridge')

      createSseBridge('task-123', 'event-456')

      expect(global.EventSource).toHaveBeenCalledWith(
        expect.stringMatching(/after_sequence=event-456/)
      )
    })

    test('should forward SSE events to renderer via IPC', async () => {
      const { createSseBridge } = await import('../services/sse-bridge')

      createSseBridge('task-123', null)

      const messageHandler = mockEventSource.addEventListener.mock.calls.find(
        (call) => call[0] === 'message'
      )?.[1]

      expect(messageHandler).toBeDefined()

      const mockEvent: AgentEvent = {
        id: 'event-789',
        agent_run_id: 'run-abc',
        event_type: 'TOOL_APPROVAL_REQUESTED',
        payload_json: { tool: 'bash', command: 'ls' },
        created_at: '2026-06-25T00:00:00Z',
      }

      messageHandler({ data: JSON.stringify(mockEvent) })

      expect(mockWebContents.send).toHaveBeenCalledWith('agent:message-stream', mockEvent)
      expect(mockNotifyForAgentEvent).toHaveBeenCalledWith(mockEvent)
    })

    test('should send connection status updates', async () => {
      const { createSseBridge } = await import('../services/sse-bridge')

      createSseBridge('task-123', null)

      const openHandler = mockEventSource.addEventListener.mock.calls.find(
        (call) => call[0] === 'open'
      )?.[1]

      openHandler({ type: 'open' })

      expect(mockWebContents.send).toHaveBeenCalledWith('agent:connection-status', 'open')
    })

    test('should handle SSE errors', async () => {
      const { createSseBridge } = await import('../services/sse-bridge')

      createSseBridge('task-123', null)

      const errorHandler = mockEventSource.addEventListener.mock.calls.find(
        (call) => call[0] === 'error'
      )?.[1]

      errorHandler({ type: 'error' })

      expect(mockWebContents.send).toHaveBeenCalledWith('agent:connection-status', 'retrying')
    })

    test('should retry connection with exponential backoff', async () => {
      vi.useFakeTimers()

      const { createSseBridge } = await import('../services/sse-bridge')

      const bridge = createSseBridge('task-123', null)

      const errorHandler = mockEventSource.addEventListener.mock.calls.find(
        (call) => call[0] === 'error'
      )?.[1]

      // First error
      errorHandler({ type: 'error' })
      expect(mockWebContents.send).toHaveBeenCalledWith('agent:connection-status', 'retrying')

      // Should retry after 1s (2^0 * 1000ms)
      vi.advanceTimersByTime(1000)
      expect(global.EventSource).toHaveBeenCalledTimes(2)

      // Second error
      const newEventSource = vi.mocked(global.EventSource).mock.results[1].value
      const errorHandler2 = newEventSource.addEventListener.mock.calls.find(
        (call: any) => call[0] === 'error'
      )?.[1]
      errorHandler2({ type: 'error' })

      // Should retry after 2s (2^1 * 1000ms)
      vi.advanceTimersByTime(2000)
      expect(global.EventSource).toHaveBeenCalledTimes(3)

      vi.useRealTimers()
    })

    test('should close connection', async () => {
      const { createSseBridge } = await import('../services/sse-bridge')

      const bridge = createSseBridge('task-123', null)

      bridge.close()

      expect(mockEventSource.close).toHaveBeenCalled()
      expect(mockWebContents.send).toHaveBeenCalledWith('agent:connection-status', 'closed')
    })

    test('should handle multiple simultaneous streams', async () => {
      const { createSseBridge } = await import('../services/sse-bridge')

      const bridge1 = createSseBridge('task-123', null)
      const bridge2 = createSseBridge('task-456', null)

      expect(global.EventSource).toHaveBeenCalledTimes(2)
      expect(global.EventSource).toHaveBeenCalledWith(
        expect.stringContaining('/api/tasks/task-123/events/stream')
      )
      expect(global.EventSource).toHaveBeenCalledWith(
        expect.stringContaining('/api/tasks/task-456/events/stream')
      )
    })

    test('should parse event data correctly', async () => {
      const { createSseBridge } = await import('../services/sse-bridge')

      createSseBridge('task-123', null)

      const messageHandler = mockEventSource.addEventListener.mock.calls.find(
        (call) => call[0] === 'message'
      )?.[1]

      const mockEvent = {
        id: 'event-789',
        agent_run_id: 'run-abc',
        event_type: 'LOCAL_AGENT_TOOL_REQUESTED',
        payload_json: {
          tool: 'read',
          args: { file_path: '/test/file.ts' },
        },
        created_at: '2026-06-25T00:00:00Z',
      }

      messageHandler({ data: JSON.stringify(mockEvent) })

      expect(mockWebContents.send).toHaveBeenCalledWith('agent:message-stream', mockEvent)
    })

    test('should handle malformed event data', async () => {
      const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

      const { createSseBridge } = await import('../services/sse-bridge')

      createSseBridge('task-123', null)

      const messageHandler = mockEventSource.addEventListener.mock.calls.find(
        (call) => call[0] === 'message'
      )?.[1]

      messageHandler({ data: 'invalid json' })

      expect(consoleErrorSpy).toHaveBeenCalled()
      expect(mockWebContents.send).not.toHaveBeenCalledWith('agent:message-stream', expect.anything())

      consoleErrorSpy.mockRestore()
    })

    test('should stop retrying after max attempts', async () => {
      vi.useFakeTimers()

      const { createSseBridge } = await import('../services/sse-bridge')

      createSseBridge('task-123', null, { maxRetryAttempts: 3 })

      const errorHandler = mockEventSource.addEventListener.mock.calls.find(
        (call) => call[0] === 'error'
      )?.[1]

      // Fail 3 times
      for (let i = 0; i < 3; i++) {
        errorHandler({ type: 'error' })
        vi.advanceTimersByTime(Math.pow(2, i) * 1000)
      }

      expect(global.EventSource).toHaveBeenCalledTimes(4) // Initial + 3 retries

      // Fourth error should not retry
      const lastEventSource = vi.mocked(global.EventSource).mock.results[3].value
      const errorHandler4 = lastEventSource.addEventListener.mock.calls.find(
        (call: any) => call[0] === 'error'
      )?.[1]
      errorHandler4({ type: 'error' })

      vi.advanceTimersByTime(10000)
      expect(global.EventSource).toHaveBeenCalledTimes(4) // No new connection

      expect(mockWebContents.send).toHaveBeenCalledWith('agent:connection-status', 'failed')

      vi.useRealTimers()
    })
  })

  describe('retryNow', () => {
    test('should immediately retry connection', async () => {
      vi.useFakeTimers()

      const { createSseBridge } = await import('../services/sse-bridge')

      const bridge = createSseBridge('task-123', null)

      const errorHandler = mockEventSource.addEventListener.mock.calls.find(
        (call) => call[0] === 'error'
      )?.[1]

      errorHandler({ type: 'error' })

      // Before scheduled retry time
      vi.advanceTimersByTime(500)
      expect(global.EventSource).toHaveBeenCalledTimes(1)

      // Call retryNow
      bridge.retryNow()

      // Should retry immediately
      expect(global.EventSource).toHaveBeenCalledTimes(2)

      vi.useRealTimers()
    })
  })
})
