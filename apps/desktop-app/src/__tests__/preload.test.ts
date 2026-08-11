import { describe, test, expect, vi, beforeEach } from 'vitest'

// Mock electron modules
const mockIpcRenderer = {
  invoke: vi.fn(),
  sendSync: vi.fn(),
  on: vi.fn(),
  removeListener: vi.fn(),
}

const mockContextBridge = {
  exposeInMainWorld: vi.fn(),
}

vi.mock('electron', () => ({
  ipcRenderer: mockIpcRenderer,
  contextBridge: mockContextBridge,
}))

describe('Preload Script', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  test('should expose desktopApi to main world via contextBridge', async () => {
    // Import will trigger contextBridge.exposeInMainWorld at module load
    await import('../preload')

    expect(mockContextBridge.exposeInMainWorld).toHaveBeenCalledWith(
      'desktopApi',
      expect.objectContaining({
        agent: expect.any(Object),
        storage: expect.any(Object),
        task: expect.any(Object),
        system: expect.any(Object),
        feedback: expect.any(Object),
        events: expect.any(Object),
      })
    )
  })

  test('limits the recovery renderer to write-only local runtime setup IPC', async () => {
    const { selectDesktopApiForUrl } = await import('../preload')

    const recoveryApi = selectDesktopApiForUrl('harness-app://renderer/index.html')

    expect(recoveryApi).toEqual({ localRuntime: expect.any(Object) })
    expect(recoveryApi).not.toHaveProperty('agent')
  })

  test('should expose agent.bindConversation that invokes IPC handler', async () => {
    vi.resetModules()
    await import('../preload')

    const exposedApi = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    expect(exposedApi).toBeDefined()
    const api = exposedApi!
    const connectionId = 'conn-123'
    const payload = { agent_session_id: 'sess-456' }

    mockIpcRenderer.invoke.mockResolvedValue({ binding_id: 'binding-789' })

    await api.agent.bindConversation(connectionId, payload)

    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith(
      'agent:bind-conversation',
      connectionId,
      payload
    )
  })

  test('should expose agent.sendMessage that invokes IPC handler', async () => {
    vi.resetModules()
    await import('../preload')

    const exposedApi = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    expect(exposedApi).toBeDefined()
    const api = exposedApi!
    const bindingId = 'binding-789'
    const payload = { content: 'Hello', role: 'user' as const }

    mockIpcRenderer.invoke.mockResolvedValue({ message_id: 'msg-001' })

    await api.agent.sendMessage(bindingId, payload)

    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith(
      'agent:send-message',
      bindingId,
      payload
    )
  })

  test('should expose agent.getWorkspace that invokes IPC handler', async () => {
    vi.resetModules()
    await import('../preload')

    const exposedApi = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    expect(exposedApi).toBeDefined()
    const api = exposedApi!
    const runId = 'run-123'
    const selectors = { retrieval_session_id: 'retr-456' }

    mockIpcRenderer.invoke.mockResolvedValue({ workspace_id: 'ws-789' })

    await api.agent.getWorkspace(runId, selectors)

    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith(
      'agent:get-workspace',
      runId,
      selectors
    )
  })

  test('should expose agent.listConnections that invokes IPC handler', async () => {
    vi.resetModules()
    await import('../preload')

    const exposedApi = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    expect(exposedApi).toBeDefined()
    const api = exposedApi!

    mockIpcRenderer.invoke.mockResolvedValue({ items: [] })

    await api.agent.listConnections()

    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('agent:list-connections')
  })

  test('should expose task.get that invokes IPC handler', async () => {
    vi.resetModules()
    await import('../preload')

    const exposedApi = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    expect(exposedApi).toBeDefined()
    const api = exposedApi!
    const taskId = 'task-123'

    mockIpcRenderer.invoke.mockResolvedValue({ task_id: taskId, status: 'running' })

    await api.task.get(taskId)

    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('task:get', taskId)
  })

  test('should expose task.cancel that invokes IPC handler', async () => {
    vi.resetModules()
    await import('../preload')

    const exposedApi = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    expect(exposedApi).toBeDefined()
    const api = exposedApi!
    const taskId = 'task-123'

    mockIpcRenderer.invoke.mockResolvedValue(undefined)

    await api.task.cancel(taskId)

    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('task:cancel', taskId)
  })

  test('should expose task.list that invokes IPC handler', async () => {
    vi.resetModules()
    await import('../preload')

    const exposedApi = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    expect(exposedApi).toBeDefined()
    const api = exposedApi!
    const filters = { status: 'running' as const }

    mockIpcRenderer.invoke.mockResolvedValue({ items: [] })

    await api.task.list(filters)

    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('task:list', filters)
  })

  test('should expose events.onMessageStream that registers IPC listener', async () => {
    vi.resetModules()
    await import('../preload')

    const exposedApi = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    expect(exposedApi).toBeDefined()
    const api = exposedApi!
    const callback = vi.fn()

    const unsubscribe = api.events.onMessageStream(callback)

    expect(mockIpcRenderer.on).toHaveBeenCalledWith(
      'agent:message-stream',
      expect.any(Function)
    )

    // Simulate event
    const listener = mockIpcRenderer.on.mock.calls[0][1]
    const mockEvent = {} as any
    const agentEvent = { type: 'message', data: 'test' }
    listener(mockEvent, agentEvent)

    expect(callback).toHaveBeenCalledWith(agentEvent)

    // Test unsubscribe
    unsubscribe()
    expect(mockIpcRenderer.removeListener).toHaveBeenCalledWith(
      'agent:message-stream',
      listener
    )
  })

  test('should expose system methods that invoke IPC handlers', async () => {
    vi.resetModules()
    await import('../preload')

    const exposedApi = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    expect(exposedApi).toBeDefined()
    const api = exposedApi!

    await api.system.showWindow('/runs/run-1')
    await api.system.hideWindow()
    await api.system.getStartupEnabled()
    await api.system.setStartupEnabled(true)
    await api.system.notify({
      title: '任务已完成',
      body: '运行已完成。',
      route: '/runs/run-1',
    })
    await api.system.getPendingRoute()

    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('system:show-window', '/runs/run-1')
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('system:hide-window')
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('system:get-startup-enabled')
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('system:set-startup-enabled', true)
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('system:notify', {
      title: '任务已完成',
      body: '运行已完成。',
      route: '/runs/run-1',
    })
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('system:get-pending-route')
  })

  test('should expose feedback methods that invoke IPC handlers', async () => {
    vi.resetModules()
    await import('../preload')

    const exposedApi = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    expect(exposedApi).toBeDefined()
    const api = exposedApi!
    const payload = {
      title: 'Startup too slow',
      description: 'The app took too long to open.',
      app_version: '0.1.0',
      platform: 'darwin',
    }

    mockIpcRenderer.invoke.mockResolvedValue({ received: true })

    await api.feedback.submit(payload)
    await api.feedback.recordMetric({
      metric_name: 'startup_time_ms',
      app_version: '0.1.0',
      platform: 'darwin',
      value: 2500,
    })
    await api.feedback.getMetricsSummary()

    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('feedback:submit', payload)
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith(
      'feedback:record-metric',
      expect.objectContaining({ metric_name: 'startup_time_ms' })
    )
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith('feedback:get-metrics-summary')
  })

  test('should expose events.onConnectionStatus that registers IPC listener', async () => {
    vi.resetModules()
    await import('../preload')

    const exposedApi = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    expect(exposedApi).toBeDefined()
    const api = exposedApi!
    const callback = vi.fn()

    const unsubscribe = api.events.onConnectionStatus(callback)

    expect(mockIpcRenderer.on).toHaveBeenCalledWith(
      'agent:connection-status',
      expect.any(Function)
    )

    // Simulate event
    const listener = mockIpcRenderer.on.mock.calls[0][1]
    const mockEvent = {} as any
    const status = { connected: true, url: 'http://localhost:8000/sse' }
    listener(mockEvent, status)

    expect(callback).toHaveBeenCalledWith(status)

    // Test unsubscribe
    unsubscribe()
    expect(mockIpcRenderer.removeListener).toHaveBeenCalledWith(
      'agent:connection-status',
      listener
    )
  })

  test('should expose events.onTaskStatusChange that registers IPC listener', async () => {
    vi.resetModules()
    await import('../preload')

    const exposedApi = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    expect(exposedApi).toBeDefined()
    const api = exposedApi!
    const callback = vi.fn()

    const unsubscribe = api.events.onTaskStatusChange(callback)

    expect(mockIpcRenderer.on).toHaveBeenCalledWith(
      'task:status-change',
      expect.any(Function)
    )

    // Simulate event
    const listener = mockIpcRenderer.on.mock.calls[0][1]
    const mockEvent = {} as any
    const task = { task_id: 'task-123', status: 'completed' as const }
    listener(mockEvent, task)

    expect(callback).toHaveBeenCalledWith(task)

    // Test unsubscribe
    unsubscribe()
    expect(mockIpcRenderer.removeListener).toHaveBeenCalledWith(
      'task:status-change',
      listener
    )
  })

  test('should expose events.onOpenRoute that registers IPC listener', async () => {
    vi.resetModules()
    await import('../preload')

    const exposedApi = mockContextBridge.exposeInMainWorld.mock.calls[0]?.[1]
    expect(exposedApi).toBeDefined()
    const api = exposedApi!
    const callback = vi.fn()

    const unsubscribe = api.events.onOpenRoute(callback)

    expect(mockIpcRenderer.on).toHaveBeenCalledWith(
      'system:open-route',
      expect.any(Function)
    )

    const listener = mockIpcRenderer.on.mock.calls.find(
      (call) => call[0] === 'system:open-route'
    )?.[1]
    const payload = { route: '/runs/run-1', source: 'notification' as const }
    listener({} as any, payload)

    expect(callback).toHaveBeenCalledWith(payload)

    unsubscribe()
    expect(mockIpcRenderer.removeListener).toHaveBeenCalledWith(
      'system:open-route',
      listener
    )
  })
})
