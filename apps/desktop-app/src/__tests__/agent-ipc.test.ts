import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest'
import type {
  LocalAgentConversationBinding,
  LocalAgentSendMessagePayload,
  LocalAgentSendMessageResponse,
  AgentRunWorkspace,
  Task,
  LocalAgentConnection,
} from '../preload-api'

describe('Agent IPC', () => {
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

  describe('bindConversation', () => {
    test('should register IPC handler for agent:bind-conversation', async () => {
      const { registerAgentHandlers } = await import('../services/agent-service')
      registerAgentHandlers()

      expect(mockIpcMain.handle).toHaveBeenCalledWith(
        'agent:bind-conversation',
        expect.any(Function)
      )
    })

    test('should call API and return binding', async () => {
      const mockBinding: LocalAgentConversationBinding = {
        id: 'binding-123',
        connection_id: 'conn-456',
        agent_id: 'agent-789',
        agent_session_id: 'session-abc',
        adapter_session_id: null,
        resume_mode: 'native_resume',
        status: 'active',
        created_at: '2026-06-25T00:00:00Z',
        updated_at: '2026-06-25T00:00:00Z',
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockBinding,
      })

      const { registerAgentHandlers } = await import('../services/agent-service')
      registerAgentHandlers()

      const handler = mockIpcMain.handle.mock.calls.find(
        (call) => call[0] === 'agent:bind-conversation'
      )?.[1]

      expect(handler).toBeDefined()

      const result = await handler(null, 'conn-456', {
        agent_session_id: 'session-abc',
        resume_mode: 'native_resume',
      })

      expect(result).toEqual(mockBinding)
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/agents/local-agent/connections/conn-456/bindings'),
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('session-abc'),
        })
      )
    })

    test('should throw error when API call fails', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
      })

      const { registerAgentHandlers } = await import('../services/agent-service')
      registerAgentHandlers()

      const handler = mockIpcMain.handle.mock.calls.find(
        (call) => call[0] === 'agent:bind-conversation'
      )?.[1]

      await expect(handler(null, 'conn-456', {})).rejects.toThrow('API request failed')
    })

    test('should handle network errors', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'))

      const { registerAgentHandlers } = await import('../services/agent-service')
      registerAgentHandlers()

      const handler = mockIpcMain.handle.mock.calls.find(
        (call) => call[0] === 'agent:bind-conversation'
      )?.[1]

      await expect(handler(null, 'conn-456', {})).rejects.toThrow('Network error')
    })
  })

  describe('sendMessage', () => {
    test('should register IPC handler for agent:send-message', async () => {
      const { registerAgentHandlers } = await import('../services/agent-service')
      registerAgentHandlers()

      expect(mockIpcMain.handle).toHaveBeenCalledWith('agent:send-message', expect.any(Function))
    })

    test('should call API and return response', async () => {
      const mockPayload: LocalAgentSendMessagePayload = {
        content: 'Hello agent',
        client_message_id: 'msg-123',
        workspace_mode: 'chat',
      }

      const mockResponse: LocalAgentSendMessageResponse = {
        bridge_task_id: 'task-456',
        run_id: 'run-789',
        agent_session_id: 'session-abc',
        user_message_id: 'user-msg-def',
        status: 'created',
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      })

      const { registerAgentHandlers } = await import('../services/agent-service')
      registerAgentHandlers()

      const handler = mockIpcMain.handle.mock.calls.find(
        (call) => call[0] === 'agent:send-message'
      )?.[1]

      const result = await handler(null, 'binding-123', mockPayload)

      expect(result).toEqual(mockResponse)
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/agents/local-agent/bindings/binding-123/messages'),
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('Hello agent'),
        })
      )
    })

    test('should handle empty message content', async () => {
      const mockPayload: LocalAgentSendMessagePayload = {
        content: '',
        client_message_id: 'msg-123',
      }

      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
      })

      const { registerAgentHandlers } = await import('../services/agent-service')
      registerAgentHandlers()

      const handler = mockIpcMain.handle.mock.calls.find(
        (call) => call[0] === 'agent:send-message'
      )?.[1]

      await expect(handler(null, 'binding-123', mockPayload)).rejects.toThrow()
    })
  })

  describe('getWorkspace', () => {
    test('should register IPC handler for agent:get-workspace', async () => {
      const { registerAgentHandlers } = await import('../services/agent-service')
      registerAgentHandlers()

      expect(mockIpcMain.handle).toHaveBeenCalledWith('agent:get-workspace', expect.any(Function))
    })

    test('should call API and return workspace data', async () => {
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

      const mockWorkspace: AgentRunWorkspace = {
        run: mockTask,
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

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockWorkspace,
      })

      const { registerAgentHandlers } = await import('../services/agent-service')
      registerAgentHandlers()

      const handler = mockIpcMain.handle.mock.calls.find(
        (call) => call[0] === 'agent:get-workspace'
      )?.[1]

      const result = await handler(null, 'run-123', {})

      expect(result).toEqual(mockWorkspace)
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/agents/runs/run-123/workspace'),
        expect.any(Object)
      )
    })

    test('should include query parameters when selectors provided', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          run: {},
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
        }),
      })

      const { registerAgentHandlers } = await import('../services/agent-service')
      registerAgentHandlers()

      const handler = mockIpcMain.handle.mock.calls.find(
        (call) => call[0] === 'agent:get-workspace'
      )?.[1]

      await handler(null, 'run-123', {
        retrieval_session_id: 'session-456',
        prompt_manifest_id: 'manifest-789',
      })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringMatching(/retrieval_session_id=session-456/),
        expect.any(Object)
      )
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringMatching(/prompt_manifest_id=manifest-789/),
        expect.any(Object)
      )
    })
  })

  describe('listConnections', () => {
    test('should register IPC handler for agent:list-connections', async () => {
      const { registerAgentHandlers } = await import('../services/agent-service')
      registerAgentHandlers()

      expect(mockIpcMain.handle).toHaveBeenCalledWith(
        'agent:list-connections',
        expect.any(Function)
      )
    })

    test('should call API and return connections list', async () => {
      const mockConnections: LocalAgentConnection[] = [
        {
          id: 'conn-1',
          agent_id: 'agent-123',
          display_name: 'Local Agent 1',
          adapter_kind: 'local',
          status: 'connected',
        },
        {
          id: 'conn-2',
          agent_id: 'agent-123',
          display_name: 'Local Agent 2',
          adapter_kind: 'local',
          status: 'connected',
        },
      ]

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ items: mockConnections }),
      })

      const { registerAgentHandlers } = await import('../services/agent-service')
      registerAgentHandlers()

      const handler = mockIpcMain.handle.mock.calls.find(
        (call) => call[0] === 'agent:list-connections'
      )?.[1]

      const result = await handler(null)

      expect(result).toEqual({ items: mockConnections })
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/agents/local-agent/connections'),
        expect.any(Object)
      )
    })

    test('should return empty list when no connections', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ items: [] }),
      })

      const { registerAgentHandlers } = await import('../services/agent-service')
      registerAgentHandlers()

      const handler = mockIpcMain.handle.mock.calls.find(
        (call) => call[0] === 'agent:list-connections'
      )?.[1]

      const result = await handler(null)

      expect(result).toEqual({ items: [] })
    })
  })
})
