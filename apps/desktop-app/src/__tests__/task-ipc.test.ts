import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest'
import type { Task, TaskStatus } from '../preload-api'

describe('Task IPC', () => {
  let mockIpcMain: {
    handle: ReturnType<typeof vi.fn>
    removeHandler: ReturnType<typeof vi.fn>
  }
  let mockFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.resetModules()
    mockIpcMain = {
      handle: vi.fn(),
      removeHandler: vi.fn(),
    }
    mockFetch = vi.fn()

    vi.doMock('electron', () => ({
      ipcMain: mockIpcMain,
    }))

    global.fetch = mockFetch
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('getTask', () => {
    test('should register IPC handler for task:get', async () => {
      const { registerTaskHandlers } = await import('../services/task-service')
      registerTaskHandlers()

      expect(mockIpcMain.handle).toHaveBeenCalledWith('task:get', expect.any(Function))
    })

    test('should call API and return task', async () => {
      const mockTask: Task = {
        id: 'task-123',
        agent_id: 'agent-456',
        title: 'Test Task',
        goal: 'Complete test',
        status: 'RUNNING',
        model_provider: 'anthropic',
        model_name: 'claude-opus-4-6',
        max_runtime_seconds: 3600,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: true,
        created_at: '2026-06-25T00:00:00Z',
        updated_at: '2026-06-25T00:00:00Z',
        completed_at: null,
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockTask,
      })

      const { registerTaskHandlers } = await import('../services/task-service')
      registerTaskHandlers()

      const handler = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'task:get')?.[1]

      const result = await handler(null, 'task-123')

      expect(result).toEqual(mockTask)
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tasks/task-123'),
        expect.any(Object)
      )
    })

    test('should handle task not found', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
      })

      const { registerTaskHandlers } = await import('../services/task-service')
      registerTaskHandlers()

      const handler = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'task:get')?.[1]

      await expect(handler(null, 'task-123')).rejects.toThrow('API request failed')
    })
  })

  describe('cancelTask', () => {
    test('should register IPC handler for task:cancel', async () => {
      const { registerTaskHandlers } = await import('../services/task-service')
      registerTaskHandlers()

      expect(mockIpcMain.handle).toHaveBeenCalledWith('task:cancel', expect.any(Function))
    })

    test('should call API to cancel task', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({}),
      })

      const { registerTaskHandlers } = await import('../services/task-service')
      registerTaskHandlers()

      const handler = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'task:cancel')?.[1]

      await handler(null, 'task-123')

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tasks/task-123/cancel'),
        expect.objectContaining({
          method: 'POST',
        })
      )
    })

    test('should handle cancellation errors', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
      })

      const { registerTaskHandlers } = await import('../services/task-service')
      registerTaskHandlers()

      const handler = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'task:cancel')?.[1]

      await expect(handler(null, 'task-123')).rejects.toThrow()
    })
  })

  describe('listTasks', () => {
    test('should register IPC handler for task:list', async () => {
      const { registerTaskHandlers } = await import('../services/task-service')
      registerTaskHandlers()

      expect(mockIpcMain.handle).toHaveBeenCalledWith('task:list', expect.any(Function))
    })

    test('should call API and return tasks list', async () => {
      const mockTasks: Task[] = [
        {
          id: 'task-1',
          agent_id: 'agent-123',
          title: 'Task 1',
          goal: 'Goal 1',
          status: 'RUNNING',
          model_provider: 'anthropic',
          model_name: 'claude-opus-4-6',
          max_runtime_seconds: 3600,
          max_subagents: 5,
          enable_sandbox: true,
          enable_network: true,
          created_at: '2026-06-25T00:00:00Z',
          updated_at: '2026-06-25T00:00:00Z',
          completed_at: null,
        },
        {
          id: 'task-2',
          agent_id: 'agent-123',
          title: 'Task 2',
          goal: 'Goal 2',
          status: 'COMPLETED',
          model_provider: 'anthropic',
          model_name: 'claude-opus-4-6',
          max_runtime_seconds: 3600,
          max_subagents: 5,
          enable_sandbox: true,
          enable_network: true,
          created_at: '2026-06-25T00:00:00Z',
          updated_at: '2026-06-25T00:00:00Z',
          completed_at: '2026-06-25T01:00:00Z',
        },
      ]

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ items: mockTasks }),
      })

      const { registerTaskHandlers } = await import('../services/task-service')
      registerTaskHandlers()

      const handler = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'task:list')?.[1]

      const result = await handler(null, {})

      expect(result).toEqual({ items: mockTasks })
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tasks'),
        expect.any(Object)
      )
    })

    test('should filter tasks by status', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ items: [] }),
      })

      const { registerTaskHandlers } = await import('../services/task-service')
      registerTaskHandlers()

      const handler = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'task:list')?.[1]

      await handler(null, { status: 'RUNNING' })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringMatching(/status=RUNNING/),
        expect.any(Object)
      )
    })

    test('should return empty list when no tasks', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ items: [] }),
      })

      const { registerTaskHandlers } = await import('../services/task-service')
      registerTaskHandlers()

      const handler = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'task:list')?.[1]

      const result = await handler(null, {})

      expect(result).toEqual({ items: [] })
    })
  })

  describe('Task lifecycle', () => {
    test('should track task status changes', async () => {
      const mockTask: Task = {
        id: 'task-123',
        agent_id: 'agent-456',
        title: 'Test Task',
        goal: 'Complete test',
        status: 'CREATED',
        model_provider: 'anthropic',
        model_name: 'claude-opus-4-6',
        max_runtime_seconds: 3600,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: true,
        created_at: '2026-06-25T00:00:00Z',
        updated_at: '2026-06-25T00:00:00Z',
        completed_at: null,
      }

      const statuses: TaskStatus[] = [
        'CREATED',
        'PLANNING',
        'PLANNED',
        'RUNNING',
        'WAITING_APPROVAL',
        'RUNNING',
        'COMPLETED',
      ]

      for (const status of statuses) {
        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: async () => ({ ...mockTask, status }),
        })
      }

      const { registerTaskHandlers } = await import('../services/task-service')
      registerTaskHandlers()

      const handler = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'task:get')?.[1]

      for (const status of statuses) {
        const result = await handler(null, 'task-123')
        expect(result.status).toBe(status)
      }
    })

    test('should handle failed tasks', async () => {
      const mockTask: Task = {
        id: 'task-123',
        agent_id: 'agent-456',
        title: 'Test Task',
        goal: 'Complete test',
        status: 'FAILED',
        model_provider: 'anthropic',
        model_name: 'claude-opus-4-6',
        max_runtime_seconds: 3600,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: true,
        created_at: '2026-06-25T00:00:00Z',
        updated_at: '2026-06-25T00:00:00Z',
        completed_at: '2026-06-25T00:30:00Z',
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockTask,
      })

      const { registerTaskHandlers } = await import('../services/task-service')
      registerTaskHandlers()

      const handler = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'task:get')?.[1]

      const result = await handler(null, 'task-123')

      expect(result.status).toBe('FAILED')
      expect(result.completed_at).toBe('2026-06-25T00:30:00Z')
    })

    test('should handle cancelled tasks', async () => {
      const mockTask: Task = {
        id: 'task-123',
        agent_id: 'agent-456',
        title: 'Test Task',
        goal: 'Complete test',
        status: 'CANCELLED',
        model_provider: 'anthropic',
        model_name: 'claude-opus-4-6',
        max_runtime_seconds: 3600,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: true,
        created_at: '2026-06-25T00:00:00Z',
        updated_at: '2026-06-25T00:00:00Z',
        completed_at: '2026-06-25T00:15:00Z',
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockTask,
      })

      const { registerTaskHandlers } = await import('../services/task-service')
      registerTaskHandlers()

      const handler = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'task:get')?.[1]

      const result = await handler(null, 'task-123')

      expect(result.status).toBe('CANCELLED')
      expect(result.completed_at).toBe('2026-06-25T00:15:00Z')
    })
  })

  describe('Error handling', () => {
    test('should handle network timeouts', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network timeout'))

      const { registerTaskHandlers } = await import('../services/task-service')
      registerTaskHandlers()

      const handler = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'task:get')?.[1]

      await expect(handler(null, 'task-123')).rejects.toThrow('Network timeout')
    })

    test('should handle auth errors', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
      })

      const { registerTaskHandlers } = await import('../services/task-service')
      registerTaskHandlers()

      const handler = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'task:get')?.[1]

      await expect(handler(null, 'task-123')).rejects.toThrow('API request failed')
    })

    test('should handle server errors', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
      })

      const { registerTaskHandlers } = await import('../services/task-service')
      registerTaskHandlers()

      const handler = mockIpcMain.handle.mock.calls.find((call) => call[0] === 'task:get')?.[1]

      await expect(handler(null, 'task-123')).rejects.toThrow('API request failed')
    })
  })
})
