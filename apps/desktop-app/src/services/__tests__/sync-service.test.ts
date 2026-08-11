/**
 * SyncService tests - RED phase
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { SQLiteSyncService } from '../sqlite-sync-service'
import { SQLiteOfflineQueue } from '../../stores/sqlite-offline-queue'
import { SQLiteTaskStore } from '../../stores/sqlite-task-store'
import type { SyncService, SyncDeltaRequest, SyncDeltaResponse } from '../sync-service'
import type { SyncMetadata } from '../sync-metadata'
import { setDesktopProfileResolver } from '../../shared/api-client'

describe('SyncService', () => {
  let syncService: SyncService
  let offlineQueue: SQLiteOfflineQueue
  let taskStore: SQLiteTaskStore
  let syncMetadata: SyncMetadata

  beforeEach(() => {
    offlineQueue = new SQLiteOfflineQueue(':memory:')
    offlineQueue.initialize()

    taskStore = new SQLiteTaskStore(':memory:')
    taskStore.initialize()

    const metadata = new Map<string, string>()
    syncMetadata = {
      initialize: vi.fn(),
      getLastSyncTimestamp: vi.fn(() => metadata.get('last_sync_timestamp') ?? null),
      setLastSyncTimestamp: vi.fn((timestamp: string) => {
        metadata.set('last_sync_timestamp', timestamp)
      }),
      getMetadata: vi.fn((key: string) => metadata.get(key) ?? null),
      setMetadata: vi.fn((key: string, value: string) => {
        metadata.set(key, value)
      }),
      deleteMetadata: vi.fn((key: string) => {
        metadata.delete(key)
      }),
      close: vi.fn(),
    }

    syncService = new SQLiteSyncService('http://localhost:3000', offlineQueue, taskStore, syncMetadata)

    // Mock fetch globally
    global.fetch = vi.fn()
  })

  afterEach(() => {
    setDesktopProfileResolver(null)
    vi.restoreAllMocks()
    if (offlineQueue) {
      offlineQueue.close()
    }
    if (taskStore) {
      taskStore.close()
    }
    if (syncMetadata && typeof syncMetadata.close === 'function') {
      syncMetadata.close()
    }
  })

  describe('fetchDelta', () => {
    it('should fetch tasks since last sync timestamp', async () => {
      const mockResponse = {
        tasks: [
          {
            id: 'task-1',
            title: 'Test Task',
            created_at: '2026-06-24T00:00:00.000Z',
            updated_at: '2026-06-24T00:00:00.000Z',
          },
        ],
        server_timestamp: '2026-06-25T00:00:00.000Z',
        has_more: false,
      }

      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      } as Response)

      const request: SyncDeltaRequest = {
        last_sync_timestamp: '2026-06-20T00:00:00.000Z',
        entity_types: ['task'],
      }

      const response = await syncService.fetchDelta(request)

      expect(response).toHaveProperty('tasks')
      expect(response).toHaveProperty('server_timestamp')
      expect(response).toHaveProperty('has_more')
      expect(Array.isArray(response.tasks)).toBe(true)
      expect(vi.mocked(fetch).mock.calls[0][0]).toEqual(
        expect.stringContaining('since=2026-06-20T00%3A00%3A00.000Z')
      )
    })

    it('should fetch all tasks when last_sync_timestamp is null', async () => {
      const mockResponse = {
        tasks: [
          {
            id: 'task-1',
            title: 'Test Task',
            created_at: '2026-06-24T00:00:00.000Z',
            updated_at: '2026-06-24T00:00:00.000Z',
          },
        ],
        server_timestamp: '2026-06-25T00:00:00.000Z',
        has_more: false,
      }

      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      } as Response)

      const request: SyncDeltaRequest = {
        last_sync_timestamp: null,
        entity_types: ['task'],
      }

      const response = await syncService.fetchDelta(request)

      expect(response.tasks).toBeDefined()
      expect(response.server_timestamp).toBeDefined()
      expect(vi.mocked(fetch).mock.calls[0][0]).toEqual(expect.not.stringContaining('since='))
    })

    it('should respect date range filter', async () => {
      const mockResponse = {
        tasks: [
          {
            id: 'task-1',
            title: 'Test Task',
            created_at: '2026-06-15T00:00:00.000Z',
            updated_at: '2026-06-15T00:00:00.000Z',
          },
        ],
        server_timestamp: '2026-06-25T00:00:00.000Z',
        has_more: false,
      }

      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      } as Response)

      const request: SyncDeltaRequest = {
        last_sync_timestamp: null,
        entity_types: ['task'],
        date_range: {
          start: '2026-06-01T00:00:00.000Z',
          end: '2026-06-30T23:59:59.999Z',
        },
      }

      const response = await syncService.fetchDelta(request)

      expect(response.tasks).toBeDefined()
      expect(vi.mocked(fetch).mock.calls[0][0]).toEqual(
        expect.stringContaining('start_date=2026-06-01T00%3A00%3A00.000Z')
      )
      expect(vi.mocked(fetch).mock.calls[0][0]).toEqual(
        expect.stringContaining('end_date=2026-06-30T23%3A59%3A59.999Z')
      )
      // Verify all tasks are within date range
      response.tasks.forEach(task => {
        const createdAt = new Date(task.created_at)
        expect(createdAt.getTime()).toBeGreaterThanOrEqual(new Date(request.date_range!.start).getTime())
        expect(createdAt.getTime()).toBeLessThanOrEqual(new Date(request.date_range!.end).getTime())
      })
    })

    it('should handle empty response when no changes', async () => {
      const mockResponse = {
        tasks: [],
        server_timestamp: '2026-06-25T00:00:00.000Z',
        has_more: false,
      }

      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      } as Response)

      const request: SyncDeltaRequest = {
        last_sync_timestamp: new Date().toISOString(),
        entity_types: ['task'],
      }

      const response = await syncService.fetchDelta(request)

      expect(response.tasks).toEqual([])
      expect(response.has_more).toBe(false)
    })

    it('should include active profile auth token in sync requests', async () => {
      setDesktopProfileResolver(() => ({ authToken: 'profile-token' }))
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          tasks: [],
          server_timestamp: '2026-06-25T00:00:00.000Z',
          has_more: false,
        }),
      } as Response)

      await syncService.fetchDelta({
        last_sync_timestamp: null,
        entity_types: ['task'],
      })

      expect(vi.mocked(fetch).mock.calls[0][1]).toMatchObject({
        headers: expect.objectContaining({
          Authorization: 'Bearer profile-token',
        }),
      })
    })

    it('should throw error on network failure', async () => {
      const request: SyncDeltaRequest = {
        last_sync_timestamp: null,
        entity_types: ['task'],
      }

      vi.mocked(fetch).mockRejectedValueOnce(new Error('Network error'))

      await expect(syncService.fetchDelta(request)).rejects.toThrow('Network error')
    })

    it('should handle paginated responses', async () => {
      const mockResponse = {
        tasks: [
          {
            id: 'task-1',
            title: 'Test Task',
            created_at: '2026-06-24T00:00:00.000Z',
            updated_at: '2026-06-24T00:00:00.000Z',
          },
        ],
        server_timestamp: '2026-06-25T00:00:00.000Z',
        has_more: true,
      }

      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      } as Response)

      const request: SyncDeltaRequest = {
        last_sync_timestamp: null,
        entity_types: ['task'],
      }

      const response = await syncService.fetchDelta(request)

      if (response.has_more) {
        expect(response.tasks.length).toBeGreaterThan(0)
        expect(response.server_timestamp).toBeDefined()
      }
    })
  })

  describe('pushOperations', () => {
    it('should push local operations to server', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      } as Response)

      const operations = [
        {
          operation_type: 'CREATE',
          entity_type: 'task',
          entity_id: 'task-1',
          payload_json: JSON.stringify({ title: 'New Task' }),
          client_timestamp: new Date().toISOString(),
        },
      ]

      await expect(syncService.pushOperations(operations)).resolves.not.toThrow()
      expect(fetch).toHaveBeenCalledWith(
        'http://localhost:3000/api/desktop/sync/operations',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        })
      )
    })

    it('should handle empty operations array', async () => {
      await expect(syncService.pushOperations([])).resolves.not.toThrow()
      expect(fetch).not.toHaveBeenCalled()
    })

    it('should throw error on server rejection', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
      } as Response)

      const operations = [
        {
          operation_type: 'UPDATE',
          entity_type: 'task',
          entity_id: 'task-1',
          payload_json: JSON.stringify({ title: 'Updated Task' }),
          client_timestamp: new Date().toISOString(),
        },
      ]

      await expect(syncService.pushOperations(operations)).rejects.toThrow()
    })

    it('should batch large operation sets', async () => {
      vi.mocked(fetch).mockResolvedValue({
        ok: true,
        json: async () => ({ success: true }),
      } as Response)

      const operations = Array.from({ length: 100 }, (_, i) => ({
        operation_type: 'CREATE',
        entity_type: 'task',
        entity_id: `task-${i}`,
        payload_json: JSON.stringify({ title: `Task ${i}` }),
        client_timestamp: new Date().toISOString(),
      }))

      await expect(syncService.pushOperations(operations)).resolves.not.toThrow()
      // Should make 2 batches (50 + 50)
      expect(fetch).toHaveBeenCalledTimes(2)
    })
  })

  describe('sync', () => {
    it('should perform full sync cycle', async () => {
      vi.mocked(fetch).mockResolvedValue({
        ok: true,
        json: async () => ({
          tasks: [],
          server_timestamp: '2026-06-25T00:00:00.000Z',
          has_more: false,
        }),
      } as Response)

      await expect(syncService.sync()).resolves.not.toThrow()
    })

    it('should fetch delta before pushing operations', async () => {
      // Enqueue an operation so pushOperations gets called
      offlineQueue.enqueue({
        operation_type: 'CREATE',
        entity_type: 'task',
        entity_id: 'task-1',
        payload_json: JSON.stringify({ title: 'New Task' }),
        client_timestamp: new Date().toISOString(),
      })

      vi.mocked(fetch).mockResolvedValue({
        ok: true,
        json: async () => ({
          tasks: [],
          server_timestamp: '2026-06-25T00:00:00.000Z',
          has_more: false,
        }),
      } as Response)

      const fetchDeltaSpy = vi.spyOn(syncService, 'fetchDelta')
      const pushOperationsSpy = vi.spyOn(syncService, 'pushOperations')

      await syncService.sync()

      expect(fetchDeltaSpy).toHaveBeenCalled()
      expect(pushOperationsSpy).toHaveBeenCalled()
      expect(fetchDeltaSpy.mock.invocationCallOrder[0]).toBeLessThan(
        pushOperationsSpy.mock.invocationCallOrder[0]
      )
    })

    it('should update local database with fetched changes', async () => {
      const mockTask = {
        id: 'task-1',
        organization_id: 'org-1',
        agent_id: null,
        created_by: 'user-1',
        title: 'Fetched Task',
        goal: 'Test goal',
        status: 'pending',
        model_provider: 'anthropic',
        model_name: 'claude-opus-4',
        max_runtime_seconds: 3600,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: false,
        capability_snapshot_json: {},
        created_at: '2026-06-24T00:00:00.000Z',
        updated_at: '2026-06-24T00:00:00.000Z',
        completed_at: null,
      }

      vi.mocked(fetch).mockResolvedValue({
        ok: true,
        json: async () => ({
          tasks: [mockTask],
          server_timestamp: '2026-06-25T00:00:00.000Z',
          has_more: false,
        }),
      } as Response)

      await syncService.sync()

      const savedTask = taskStore.get('task-1')
      expect(savedTask).not.toBeNull()
      expect(savedTask?.title).toBe('Fetched Task')
    })

    it('should mark operations as completed after successful push', async () => {
      // Enqueue a pending operation
      const op = offlineQueue.enqueue({
        operation_type: 'CREATE',
        entity_type: 'task',
        entity_id: 'task-1',
        payload_json: JSON.stringify({ title: 'New Task' }),
        client_timestamp: new Date().toISOString(),
      })

      vi.mocked(fetch).mockResolvedValue({
        ok: true,
        json: async () => ({
          tasks: [],
          server_timestamp: '2026-06-25T00:00:00.000Z',
          has_more: false,
        }),
      } as Response)

      await syncService.sync()

      const updatedOp = offlineQueue.get(op.id!)
      expect(updatedOp?.status).toBe('COMPLETED')
    })

    it('should handle conflicts during sync', async () => {
      vi.mocked(fetch).mockResolvedValue({
        ok: true,
        json: async () => ({
          tasks: [],
          server_timestamp: '2026-06-25T00:00:00.000Z',
          has_more: false,
        }),
      } as Response)

      await syncService.sync()

      // TODO: Verify conflicts are detected and resolved
    })

    it('should rollback on sync failure', async () => {
      vi.mocked(fetch)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            tasks: [],
            server_timestamp: '2026-06-25T00:00:00.000Z',
            has_more: false,
          }),
        } as Response)
        .mockResolvedValueOnce({
          ok: false,
          status: 500,
          statusText: 'Internal Server Error',
        } as Response)

      // Enqueue an operation
      offlineQueue.enqueue({
        operation_type: 'CREATE',
        entity_type: 'task',
        entity_id: 'task-1',
        payload_json: JSON.stringify({ title: 'New Task' }),
        client_timestamp: new Date().toISOString(),
      })

      await expect(syncService.sync()).rejects.toThrow()

      // TODO: Verify local state is rolled back
    })
  })
})
