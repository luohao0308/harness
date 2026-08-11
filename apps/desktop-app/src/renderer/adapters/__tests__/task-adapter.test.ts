import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest'
import { TaskQueue } from '../task-queue'

/**
 * Task Management React Adapter Tests (Phase 1.2 - RED Phase)
 *
 * These tests define the contract for the React adapter layer that bridges
 * agent-console components (HTTP-based) with desktop-app IPC layer.
 *
 * Coverage Requirements:
 * - Task list fetching via IPC
 * - Task status polling and synchronization
 * - Task cancellation operations
 * - Workspace data fetching
 * - Multi-task concurrent execution
 * - Error handling and retry logic
 */

// Mock window.desktopApi (defined in preload.ts)
const mockDesktopApi = {
  task: {
    get: vi.fn(),
    cancel: vi.fn(),
    list: vi.fn(),
  },
  agent: {
    getWorkspace: vi.fn(),
    bindConversation: vi.fn(),
    sendMessage: vi.fn(),
    listConnections: vi.fn(),
  },
  events: {
    onTaskStatusChange: vi.fn(() => vi.fn()), // Return unsubscribe function
    onMessageStream: vi.fn(() => vi.fn()),
    onConnectionStatus: vi.fn(() => vi.fn()),
  },
}

// Expose mock to global
;(global as any).window = {
  desktopApi: mockDesktopApi,
}

// Create a testable TaskQueue with fake timers support
let testQueue: TaskQueue

beforeEach(async () => {
  vi.clearAllMocks()
  vi.useFakeTimers()

  // Replace globalTaskQueue's sleepFn to work with fake timers
  const { globalTaskQueue, TaskQueue } = await import('../task-queue')
  const fakeSleep = (ms: number) => {
    return new Promise<void>(resolve => {
      setTimeout(resolve, ms)
    })
  }
  // @ts-ignore - accessing private field for testing
  globalTaskQueue.sleepFn = fakeSleep
})

afterEach(() => {
  vi.clearAllTimers()
  vi.useRealTimers()
})

describe('Task Adapter - Task List Operations', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
  })

  test('should fetch task list via IPC instead of HTTP', async () => {
    const mockTasks = {
      items: [
        {
          id: 'task-001',
          title: 'Test Task 1',
          goal: 'Test goal 1',
          status: 'RUNNING' as const,
          model_provider: 'anthropic',
          model_name: 'claude-opus-4-6',
          max_runtime_seconds: 3600,
          max_subagents: 5,
          enable_sandbox: true,
          enable_network: true,
          created_at: '2026-06-25T10:00:00Z',
          updated_at: '2026-06-25T10:05:00Z',
          completed_at: null,
        },
        {
          id: 'task-002',
          title: 'Test Task 2',
          goal: 'Test goal 2',
          status: 'COMPLETED' as const,
          model_provider: 'anthropic',
          model_name: 'claude-sonnet-4-6',
          max_runtime_seconds: 1800,
          max_subagents: 3,
          enable_sandbox: false,
          enable_network: true,
          created_at: '2026-06-25T09:00:00Z',
          updated_at: '2026-06-25T09:30:00Z',
          completed_at: '2026-06-25T09:30:00Z',
        },
      ],
    }

    mockDesktopApi.task.list.mockResolvedValue(mockTasks)

    // Import adapter (to be implemented)
    const { listTasks } = await import('../task-adapter')

    const result = await listTasks()

    expect(mockDesktopApi.task.list).toHaveBeenCalledWith(undefined)
    expect(result).toEqual(mockTasks)
  })

  test('should filter task list by status via IPC', async () => {
    const mockTasks = {
      items: [
        {
          id: 'task-001',
          title: 'Running Task',
          goal: 'Test goal',
          status: 'RUNNING' as const,
          model_provider: 'anthropic',
          model_name: 'claude-opus-4-6',
          max_runtime_seconds: 3600,
          max_subagents: 5,
          enable_sandbox: true,
          enable_network: true,
          created_at: '2026-06-25T10:00:00Z',
          updated_at: '2026-06-25T10:05:00Z',
          completed_at: null,
        },
      ],
    }

    mockDesktopApi.task.list.mockResolvedValue(mockTasks)

    const { listTasks } = await import('../task-adapter')

    const result = await listTasks({ status: 'RUNNING' })

    expect(mockDesktopApi.task.list).toHaveBeenCalledWith({ status: 'RUNNING' })
    expect(result).toEqual(mockTasks)
  })

  test('should handle empty task list', async () => {
    mockDesktopApi.task.list.mockResolvedValue({ items: [] })

    const { listTasks } = await import('../task-adapter')

    const result = await listTasks()

    expect(result.items).toHaveLength(0)
  })

  test('should throw error when IPC call fails', async () => {
    vi.useFakeTimers()

    const error = new Error('IPC connection failed')
    mockDesktopApi.task.list.mockRejectedValue(error)

    const { listTasks } = await import('../task-adapter')

    // Queue retries 3 times with exponential backoff (1s, 2s, 4s)
    const promise = listTasks().catch(err => err)

    await vi.advanceTimersByTimeAsync(1000) // First retry
    await vi.advanceTimersByTimeAsync(2000) // Second retry
    await vi.advanceTimersByTimeAsync(4000) // Third retry (max retries exceeded)

    const result = await promise
    expect(result).toBeInstanceOf(Error)
    expect(result.message).toBe('IPC connection failed')

    vi.useRealTimers()
  })
})

describe('Task Adapter - Single Task Operations', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    vi.useRealTimers()
    vi.resetModules()
    const { globalTaskQueue } = await import('../task-queue')
    globalTaskQueue.clear()
  })

  test('should fetch single task by ID via IPC', async () => {
    const mockTask = {
      id: 'task-001',
      title: 'Test Task',
      goal: 'Test goal',
      status: 'RUNNING' as const,
      model_provider: 'anthropic',
      model_name: 'claude-opus-4-6',
      max_runtime_seconds: 3600,
      max_subagents: 5,
      enable_sandbox: true,
      enable_network: true,
      created_at: '2026-06-25T10:00:00Z',
      updated_at: '2026-06-25T10:05:00Z',
      completed_at: null,
    }

    mockDesktopApi.task.get.mockResolvedValue(mockTask)

    const { getTask } = await import('../task-adapter')

    const result = await getTask('task-001')

    expect(mockDesktopApi.task.get).toHaveBeenCalledWith('task-001')
    expect(result).toEqual(mockTask)
  })

  test('should handle task not found error', async () => {
    vi.useFakeTimers()
    const error = new Error('Task not found')
    mockDesktopApi.task.get.mockRejectedValue(error)

    const { getTask } = await import('../task-adapter')

    let caughtError: Error | null = null
    const promise = getTask('nonexistent-task').catch(e => {
      caughtError = e as Error
    })

    // Advance through retry delays: 1s, 2s, 4s = 7s total
    await vi.advanceTimersByTimeAsync(7100)
    await promise

    expect(caughtError).not.toBeNull()
    expect(caughtError?.message).toBe('Task not found')

    vi.useRealTimers()
  })
})

describe('Task Adapter - Task Cancellation', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    vi.useRealTimers()
    vi.resetModules()
    const { globalTaskQueue } = await import('../task-queue')
    globalTaskQueue.clear()
  })

  test('should cancel task via IPC', async () => {
    mockDesktopApi.task.cancel.mockResolvedValue(undefined)

    const { cancelTask } = await import('../task-adapter')

    await cancelTask('task-001')

    expect(mockDesktopApi.task.cancel).toHaveBeenCalledWith('task-001')
  })

  test('should handle cancel error for non-cancellable task', async () => {
    vi.useFakeTimers()
    const error = new Error('Task cannot be cancelled')
    mockDesktopApi.task.cancel.mockRejectedValue(error)

    const { cancelTask } = await import('../task-adapter')

    let caughtError: Error | null = null
    const promise = cancelTask('task-001').catch(e => {
      caughtError = e as Error
    })

    // Advance through retry delays: 1s, 2s, 4s = 7s total
    await vi.advanceTimersByTimeAsync(7100)
    await promise

    expect(caughtError).not.toBeNull()
    expect(caughtError?.message).toBe('Task cannot be cancelled')

    vi.useRealTimers()
  })

  test('should handle cancel error for already completed task', async () => {
    vi.useFakeTimers()
    const error = new Error('Task already completed')
    mockDesktopApi.task.cancel.mockRejectedValue(error)

    const { cancelTask } = await import('../task-adapter')

    let caughtError: Error | null = null
    const promise = cancelTask('task-001').catch(e => {
      caughtError = e as Error
    })

    // Advance through retry delays: 1s, 2s, 4s = 7s total
    await vi.advanceTimersByTimeAsync(7100)
    await promise

    expect(caughtError).not.toBeNull()
    expect(caughtError?.message).toBe('Task already completed')

    vi.useRealTimers()
  })
})

describe('Task Adapter - Workspace Data Fetching', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    vi.useRealTimers()
    vi.resetModules()
    const { globalTaskQueue } = await import('../task-queue')
    globalTaskQueue.clear()
  })

  test('should fetch workspace data for a task via IPC', async () => {
    const mockWorkspace = {
      run: {
        id: 'task-001',
        title: 'Test Task',
        goal: 'Test goal',
        status: 'RUNNING' as const,
        model_provider: 'anthropic',
        model_name: 'claude-opus-4-6',
        max_runtime_seconds: 3600,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: true,
        created_at: '2026-06-25T10:00:00Z',
        updated_at: '2026-06-25T10:05:00Z',
        completed_at: null,
      },
      plan: null,
      events: [],
      knowledge_grounding: null,
      context_assembly: null,
      token_optimization: {},
      subagents: [],
      tool_calls: [],
      model_calls: [],
      approvals: [],
      assignments: [],
      handoffs: [],
    }

    mockDesktopApi.agent.getWorkspace.mockResolvedValue(mockWorkspace)

    const { getAgentRunWorkspace } = await import('../task-adapter')

    const result = await getAgentRunWorkspace('task-001')

    expect(mockDesktopApi.agent.getWorkspace).toHaveBeenCalledWith('task-001', undefined)
    expect(result).toEqual(mockWorkspace)
  })

  test('should fetch workspace data with selectors via IPC', async () => {
    const mockWorkspace = {
      run: {
        id: 'task-001',
        title: 'Test Task',
        goal: 'Test goal',
        status: 'RUNNING' as const,
        model_provider: 'anthropic',
        model_name: 'claude-opus-4-6',
        max_runtime_seconds: 3600,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: true,
        created_at: '2026-06-25T10:00:00Z',
        updated_at: '2026-06-25T10:05:00Z',
        completed_at: null,
      },
      plan: null,
      events: [
        {
          id: 'event-001',
          type: 'message',
          data: { content: 'Test message' },
        },
      ],
      knowledge_grounding: null,
      context_assembly: null,
      token_optimization: {},
      subagents: [],
      tool_calls: [],
      model_calls: [],
      approvals: [],
      assignments: [],
      handoffs: [],
    }

    const selectors = { include_events: true }
    mockDesktopApi.agent.getWorkspace.mockResolvedValue(mockWorkspace)

    const { getAgentRunWorkspace } = await import('../task-adapter')

    const result = await getAgentRunWorkspace('task-001', selectors)

    expect(mockDesktopApi.agent.getWorkspace).toHaveBeenCalledWith('task-001', selectors)
    expect(result.events).toHaveLength(1)
  })

  test('should handle workspace fetch error', async () => {
    vi.useFakeTimers()
    const error = new Error('Workspace not found')
    mockDesktopApi.agent.getWorkspace.mockRejectedValue(error)

    const { getAgentRunWorkspace } = await import('../task-adapter')

    let caughtError: Error | null = null
    const promise = getAgentRunWorkspace('task-001').catch(e => {
      caughtError = e as Error
    })

    // Advance through retry delays: 1s, 2s, 4s = 7s total
    await vi.advanceTimersByTimeAsync(7100)
    await promise

    expect(caughtError).not.toBeNull()
    expect(caughtError?.message).toBe('Workspace not found')

    vi.useRealTimers()
  })
})

describe('Task Adapter - Task Status Polling', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    vi.resetModules()
    const { globalTaskQueue } = await import('../task-queue')
    globalTaskQueue.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  test('should poll task status at regular intervals', async () => {
    const mockTask = {
      id: 'task-001',
      title: 'Test Task',
      goal: 'Test goal',
      status: 'RUNNING' as const,
      model_provider: 'anthropic',
      model_name: 'claude-opus-4-6',
      max_runtime_seconds: 3600,
      max_subagents: 5,
      enable_sandbox: true,
      enable_network: true,
      created_at: '2026-06-25T10:00:00Z',
      updated_at: '2026-06-25T10:05:00Z',
      completed_at: null,
    }

    mockDesktopApi.task.get.mockResolvedValue(mockTask)

    const { startTaskPolling } = await import('../task-adapter')
    const onUpdate = vi.fn()

    const stopPolling = startTaskPolling('task-001', onUpdate, { intervalMs: 1000 })

    // Immediate poll
    await vi.waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(1))
    expect(onUpdate).toHaveBeenCalledWith(mockTask)

    // First interval poll at 1000ms
    await vi.advanceTimersByTimeAsync(1000)
    await vi.runOnlyPendingTimersAsync()
    await vi.waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(2))

    // Second interval poll at 2000ms
    await vi.advanceTimersByTimeAsync(1000)
    await vi.runOnlyPendingTimersAsync()
    await vi.waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(3))

    stopPolling()
    vi.clearAllTimers()
  })

  test('should stop polling when task reaches terminal status', async () => {
    let callCount = 0
    mockDesktopApi.task.get.mockImplementation(async () => {
      callCount++
      return {
        id: 'task-001',
        title: 'Test Task',
        goal: 'Test goal',
        status: callCount < 3 ? ('RUNNING' as const) : ('COMPLETED' as const),
        model_provider: 'anthropic',
        model_name: 'claude-opus-4-6',
        max_runtime_seconds: 3600,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: true,
        created_at: '2026-06-25T10:00:00Z',
        updated_at: '2026-06-25T10:05:00Z',
        completed_at: callCount < 3 ? null : '2026-06-25T10:10:00Z',
      }
    })

    const { startTaskPolling } = await import('../task-adapter')
    const onUpdate = vi.fn()
    const onComplete = vi.fn()

    startTaskPolling('task-001', onUpdate, {
      intervalMs: 1000,
      stopOnComplete: true,
      onComplete,
    })

    // Immediate poll: RUNNING
    await vi.waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(1))
    expect(onComplete).not.toHaveBeenCalled()

    // First interval: RUNNING
    await vi.advanceTimersByTimeAsync(1000)
    await vi.runOnlyPendingTimersAsync()
    await vi.waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(2))
    expect(onComplete).not.toHaveBeenCalled()

    // Second interval: COMPLETED - should stop
    await vi.advanceTimersByTimeAsync(1000)
    await vi.runOnlyPendingTimersAsync()
    await vi.waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(3))
    await vi.waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1))

    // Third interval should NOT happen (polling stopped)
    await vi.advanceTimersByTimeAsync(1000)
    await vi.runOnlyPendingTimersAsync()
    expect(onUpdate).toHaveBeenCalledTimes(3) // Still 3
  })

  test('should handle polling errors gracefully', async () => {
    // Mock the queue's enqueue to bypass retry logic and fail immediately
    const { globalTaskQueue } = await import('../task-queue')
    const enqueueSpy = vi.spyOn(globalTaskQueue, 'enqueue')
    enqueueSpy.mockRejectedValue(new Error('Network error'))

    const taskAdapter = await import('../task-adapter')

    const onUpdate = vi.fn()
    const onError = vi.fn()

    const stopPolling = taskAdapter.startTaskPolling('task-001', onUpdate, {
      intervalMs: 100,
      onError,
    })

    // Wait for the async error to propagate
    await vi.waitFor(() => {
      expect(onError).toHaveBeenCalledWith(expect.any(Error))
    })

    expect((onError.mock.calls[0][0] as Error).message).toBe('Network error')
    expect(onUpdate).not.toHaveBeenCalled()

    stopPolling()
    enqueueSpy.mockRestore()
  })
})

describe('Task Adapter - Multi-Task Concurrent Execution', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    vi.resetModules()
    const { globalTaskQueue } = await import('../task-queue')
    globalTaskQueue.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  test('should poll multiple tasks concurrently', async () => {
    const mockTask1 = {
      id: 'task-001',
      title: 'Task 1',
      goal: 'Goal 1',
      status: 'RUNNING' as const,
      model_provider: 'anthropic',
      model_name: 'claude-opus-4-6',
      max_runtime_seconds: 3600,
      max_subagents: 5,
      enable_sandbox: true,
      enable_network: true,
      created_at: '2026-06-25T10:00:00Z',
      updated_at: '2026-06-25T10:05:00Z',
      completed_at: null,
    }

    const mockTask2 = {
      id: 'task-002',
      title: 'Task 2',
      goal: 'Goal 2',
      status: 'RUNNING' as const,
      model_provider: 'anthropic',
      model_name: 'claude-sonnet-4-6',
      max_runtime_seconds: 1800,
      max_subagents: 3,
      enable_sandbox: false,
      enable_network: true,
      created_at: '2026-06-25T10:00:00Z',
      updated_at: '2026-06-25T10:05:00Z',
      completed_at: null,
    }

    mockDesktopApi.task.get.mockImplementation(async (taskId: string) => {
      return taskId === 'task-001' ? mockTask1 : mockTask2
    })

    const { startTaskPolling } = await import('../task-adapter')
    const onUpdate1 = vi.fn()
    const onUpdate2 = vi.fn()

    const stop1 = startTaskPolling('task-001', onUpdate1, { intervalMs: 1000 })
    const stop2 = startTaskPolling('task-002', onUpdate2, { intervalMs: 1000 })

    // Both should poll simultaneously
    await vi.runOnlyPendingTimersAsync()
    expect(mockDesktopApi.task.get).toHaveBeenCalledWith('task-001')
    expect(mockDesktopApi.task.get).toHaveBeenCalledWith('task-002')
    expect(onUpdate1).toHaveBeenCalledWith(mockTask1)
    expect(onUpdate2).toHaveBeenCalledWith(mockTask2)

    stop1()
    stop2()
  })

  test('should handle stopping one poll without affecting others', async () => {
    const mockTask = {
      id: 'task-001',
      title: 'Task',
      goal: 'Goal',
      status: 'RUNNING' as const,
      model_provider: 'anthropic',
      model_name: 'claude-opus-4-6',
      max_runtime_seconds: 3600,
      max_subagents: 5,
      enable_sandbox: true,
      enable_network: true,
      created_at: '2026-06-25T10:00:00Z',
      updated_at: '2026-06-25T10:05:00Z',
      completed_at: null,
    }

    mockDesktopApi.task.get.mockResolvedValue(mockTask)

    const { startTaskPolling } = await import('../task-adapter')
    const onUpdate1 = vi.fn()
    const onUpdate2 = vi.fn()

    const stop1 = startTaskPolling('task-001', onUpdate1, { intervalMs: 1000 })
    const stop2 = startTaskPolling('task-002', onUpdate2, { intervalMs: 1000 })

    // Immediate poll for both
    await vi.waitFor(() => expect(onUpdate1).toHaveBeenCalledTimes(1))
    await vi.waitFor(() => expect(onUpdate2).toHaveBeenCalledTimes(1))

    // First interval tick for both
    await vi.advanceTimersByTimeAsync(1000)
    await vi.runOnlyPendingTimersAsync()
    await vi.waitFor(() => expect(onUpdate1).toHaveBeenCalledTimes(2))
    await vi.waitFor(() => expect(onUpdate2).toHaveBeenCalledTimes(2))

    // Stop first polling
    stop1()

    // Second interval - only task-002 should continue
    await vi.advanceTimersByTimeAsync(1000)
    await vi.runOnlyPendingTimersAsync()
    expect(onUpdate1).toHaveBeenCalledTimes(2) // Still 2
    await vi.waitFor(() => expect(onUpdate2).toHaveBeenCalledTimes(3))

    stop2()
  })
})

describe('Task Adapter - Event-Based Status Updates', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    vi.resetModules()
    const { globalTaskQueue } = await import('../task-queue')
    globalTaskQueue.clear()
  })

  test('should register IPC event listener for task status changes', async () => {
    const { subscribeToTaskStatusChanges } = await import('../task-adapter')
    const onStatusChange = vi.fn()

    const unsubscribe = subscribeToTaskStatusChanges(onStatusChange)

    expect(mockDesktopApi.events.onTaskStatusChange).toHaveBeenCalledWith(
      expect.any(Function)
    )

    // Simulate IPC event
    const listener = mockDesktopApi.events.onTaskStatusChange.mock.calls[0][0]
    const mockTask = {
      id: 'task-001',
      title: 'Test Task',
      goal: 'Test goal',
      status: 'COMPLETED' as const,
      model_provider: 'anthropic',
      model_name: 'claude-opus-4-6',
      max_runtime_seconds: 3600,
      max_subagents: 5,
      enable_sandbox: true,
      enable_network: true,
      created_at: '2026-06-25T10:00:00Z',
      updated_at: '2026-06-25T10:10:00Z',
      completed_at: '2026-06-25T10:10:00Z',
    }
    listener(mockTask)

    expect(onStatusChange).toHaveBeenCalledWith(mockTask)

    unsubscribe()
  })

  test('should filter task status events by task ID', async () => {
    const { subscribeToTaskStatusChanges } = await import('../task-adapter')
    const onStatusChange = vi.fn()

    const unsubscribe = subscribeToTaskStatusChanges(onStatusChange, { taskId: 'task-001' })

    const listener = mockDesktopApi.events.onTaskStatusChange.mock.calls[0][0]

    // Event for matching task
    listener({ id: 'task-001', status: 'COMPLETED' })
    expect(onStatusChange).toHaveBeenCalledTimes(1)

    // Event for different task - should be filtered
    listener({ id: 'task-002', status: 'COMPLETED' })
    expect(onStatusChange).toHaveBeenCalledTimes(1) // Still 1

    unsubscribe()
  })
})
