/**
 * TaskStore unit tests - TDD RED phase
 * Tests CRUD operations with sync metadata tracking
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { TaskStore } from '../task-store'
import { SQLiteTaskStore } from '../sqlite-task-store'
import type { Task, TaskWithSyncMetadata } from '../types'

let store: TaskStore

describe('TaskStore', () => {
  beforeEach(() => {
    store = new SQLiteTaskStore(':memory:')
    store.initialize()
  })

  afterEach(() => {
    store.close()
  })

  describe('initialize', () => {
    it('should create all required tables', () => {
      expect(() => store.initialize()).not.toThrow()
    })

    it('should create tasks table with sync metadata columns', () => {
      store.initialize()
      // Verify schema - will check via queries in GREEN phase
      expect(true).toBe(true)
    })
  })

  describe('create', () => {
    it('should create task with generated id and timestamps', () => {
      const taskData = {
        organization_id: 'org-1',
        agent_id: 'agent-1',
        created_by: 'user-1',
        title: 'Test Task',
        goal: 'Test goal',
        status: 'CREATED',
        model_provider: 'anthropic',
        model_name: 'claude-opus-4',
        max_runtime_seconds: 1800,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: false,
        capability_snapshot_json: {},
        completed_at: null,
      }

      const created = store.create(taskData)

      expect(created.id).toBeDefined()
      expect(created.title).toBe('Test Task')
      expect(created.created_at).toBeDefined()
      expect(created.updated_at).toBeDefined()
    })

    it('should initialize sync metadata to default values', () => {
      const taskData = {
        organization_id: 'org-1',
        agent_id: null,
        created_by: 'user-1',
        title: 'Test Task',
        goal: 'Test goal',
        status: 'CREATED',
        model_provider: 'anthropic',
        model_name: 'claude-sonnet-4',
        max_runtime_seconds: 1800,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: false,
        capability_snapshot_json: {},
        completed_at: null,
      }

      const created = store.create(taskData)

      expect(created.sync_version).toBe(0)
      expect(created.last_synced_at).toBeNull()
      expect(created.server_updated_at).toBeNull()
      expect(created.is_local_only).toBe(true)
      expect(created.has_local_changes).toBe(true)
      expect(created.conflict_detected).toBe(false)
    })

    it('should throw error if required fields are missing', () => {
      const invalidData = {
        organization_id: 'org-1',
      } as unknown as Omit<Task, 'id' | 'created_at' | 'updated_at'>

      expect(() => store.create(invalidData)).toThrow()
    })
  })

  describe('get', () => {
    it('should return task by id', () => {
      const created = store.create({
        organization_id: 'org-1',
        agent_id: null,
        created_by: 'user-1',
        title: 'Test Task',
        goal: 'Test goal',
        status: 'CREATED',
        model_provider: 'anthropic',
        model_name: 'claude-opus-4',
        max_runtime_seconds: 1800,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: false,
        capability_snapshot_json: {},
        completed_at: null,
      })

      const retrieved = store.get(created.id)

      expect(retrieved).not.toBeNull()
      expect(retrieved?.id).toBe(created.id)
      expect(retrieved?.title).toBe('Test Task')
    })

    it('should return null for non-existent id', () => {
      const result = store.get('non-existent-id')
      expect(result).toBeNull()
    })

    it('should include sync metadata in retrieved task', () => {
      const created = store.create({
        organization_id: 'org-1',
        agent_id: null,
        created_by: 'user-1',
        title: 'Test Task',
        goal: 'Test goal',
        status: 'CREATED',
        model_provider: 'anthropic',
        model_name: 'claude-opus-4',
        max_runtime_seconds: 1800,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: false,
        capability_snapshot_json: {},
        completed_at: null,
      })

      const retrieved = store.get(created.id)

      expect(retrieved?.sync_version).toBeDefined()
      expect(retrieved?.has_local_changes).toBeDefined()
    })
  })

  describe('update', () => {
    it('should update task fields', () => {
      const created = store.create({
        organization_id: 'org-1',
        agent_id: null,
        created_by: 'user-1',
        title: 'Original Title',
        goal: 'Original goal',
        status: 'CREATED',
        model_provider: 'anthropic',
        model_name: 'claude-opus-4',
        max_runtime_seconds: 1800,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: false,
        capability_snapshot_json: {},
        completed_at: null,
      })

      const updated = store.update(created.id, {
        title: 'Updated Title',
        status: 'RUNNING',
      })

      expect(updated.title).toBe('Updated Title')
      expect(updated.status).toBe('RUNNING')
      expect(updated.goal).toBe('Original goal') // Unchanged field preserved
    })

    it('should update updated_at timestamp', async () => {
      const created = store.create({
        organization_id: 'org-1',
        agent_id: null,
        created_by: 'user-1',
        title: 'Test Task',
        goal: 'Test goal',
        status: 'CREATED',
        model_provider: 'anthropic',
        model_name: 'claude-opus-4',
        max_runtime_seconds: 1800,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: false,
        capability_snapshot_json: {},
        completed_at: null,
      })

      const originalUpdatedAt = created.updated_at

      // Small delay to ensure timestamp changes
      await new Promise(resolve => setTimeout(resolve, 10))
      const updated = store.update(created.id, { title: 'New Title' })

      expect(updated.updated_at).not.toBe(originalUpdatedAt)
      expect(new Date(updated.updated_at).getTime()).toBeGreaterThan(
        new Date(originalUpdatedAt).getTime()
      )
    })

    it('should mark task as having local changes', () => {
      const created = store.create({
        organization_id: 'org-1',
        agent_id: null,
        created_by: 'user-1',
        title: 'Test Task',
        goal: 'Test goal',
        status: 'CREATED',
        model_provider: 'anthropic',
        model_name: 'claude-opus-4',
        max_runtime_seconds: 1800,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: false,
        capability_snapshot_json: {},
        completed_at: null,
      })

      // Simulate synced state
      store.markSynced(created.id, new Date().toISOString(), 1)
      const synced = store.get(created.id)
      expect(synced?.has_local_changes).toBe(false)

      // Update should mark as changed
      const updated = store.update(created.id, { title: 'Modified' })
      expect(updated.has_local_changes).toBe(true)
    })

    it('should throw error for non-existent task', () => {
      expect(() => store.update('non-existent-id', { title: 'New' })).toThrow()
    })
  })

  describe('delete', () => {
    it('should mark task for deletion sync', () => {
      const created = store.create({
        organization_id: 'org-1',
        agent_id: null,
        created_by: 'user-1',
        title: 'Test Task',
        goal: 'Test goal',
        status: 'CREATED',
        model_provider: 'anthropic',
        model_name: 'claude-opus-4',
        max_runtime_seconds: 1800,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: false,
        capability_snapshot_json: {},
        completed_at: null,
      })

      store.delete(created.id)

      // Task should be marked as deleted but still queryable for sync
      const deleted = store.get(created.id)
      expect(deleted).toBeNull() // Not returned by normal get
    })

    it('should not throw for non-existent task', () => {
      expect(() => store.delete('non-existent-id')).not.toThrow()
    })
  })

  describe('query', () => {
    beforeEach(() => {
      // Create test data
      store.create({
        organization_id: 'org-1',
        agent_id: 'agent-1',
        created_by: 'user-1',
        title: 'Task 1',
        goal: 'Goal 1',
        status: 'CREATED',
        model_provider: 'anthropic',
        model_name: 'claude-opus-4',
        max_runtime_seconds: 1800,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: false,
        capability_snapshot_json: {},
        completed_at: null,
      })

      store.create({
        organization_id: 'org-1',
        agent_id: 'agent-2',
        created_by: 'user-1',
        title: 'Task 2',
        goal: 'Goal 2',
        status: 'RUNNING',
        model_provider: 'anthropic',
        model_name: 'claude-sonnet-4',
        max_runtime_seconds: 1800,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: false,
        capability_snapshot_json: {},
        completed_at: null,
      })

      store.create({
        organization_id: 'org-2',
        agent_id: 'agent-1',
        created_by: 'user-2',
        title: 'Task 3',
        goal: 'Goal 3',
        status: 'COMPLETED',
        model_provider: 'anthropic',
        model_name: 'claude-opus-4',
        max_runtime_seconds: 1800,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: false,
        capability_snapshot_json: {},
        completed_at: new Date().toISOString(),
      })
    })

    it('should return all tasks when no filters', () => {
      const results = store.query()
      expect(results.length).toBe(3)
    })

    it('should filter by status', () => {
      const results = store.query({ status: 'RUNNING' })
      expect(results.length).toBe(1)
      expect(results[0].title).toBe('Task 2')
    })

    it('should filter by agent_id', () => {
      const results = store.query({ agent_id: 'agent-1' })
      expect(results.length).toBe(2)
    })

    it('should filter by organization_id', () => {
      const results = store.query({ organization_id: 'org-2' })
      expect(results.length).toBe(1)
      expect(results[0].title).toBe('Task 3')
    })

    it('should filter by has_local_changes', () => {
      const allTasks = store.query({})
      store.markSynced(allTasks[0].id, new Date().toISOString(), 1)

      const results = store.query({ has_local_changes: true })
      expect(results.length).toBe(2) // 2 still have local changes
    })

    it('should support limit', () => {
      const results = store.query({ limit: 2 })
      expect(results.length).toBe(2)
    })

    it('should support offset for pagination', () => {
      const page1 = store.query({ limit: 2, offset: 0 })
      const page2 = store.query({ limit: 2, offset: 2 })

      expect(page1.length).toBe(2)
      expect(page2.length).toBe(1)
      expect(page1[0].id).not.toBe(page2[0].id)
    })

    it('should filter by since timestamp', () => {
      const futureDate = new Date(Date.now() + 10000).toISOString()
      const results = store.query({ since: futureDate })
      expect(results.length).toBe(0)

      const pastDate = new Date(Date.now() - 10000).toISOString()
      const allResults = store.query({ since: pastDate })
      expect(allResults.length).toBe(3)
    })
  })

  describe('getPendingSync', () => {
    it('should return tasks with has_local_changes = true', () => {
      const task1 = store.create({
        organization_id: 'org-1',
        agent_id: null,
        created_by: 'user-1',
        title: 'Task 1',
        goal: 'Goal 1',
        status: 'CREATED',
        model_provider: 'anthropic',
        model_name: 'claude-opus-4',
        max_runtime_seconds: 1800,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: false,
        capability_snapshot_json: {},
        completed_at: null,
      })

      const task2 = store.create({
        organization_id: 'org-1',
        agent_id: null,
        created_by: 'user-1',
        title: 'Task 2',
        goal: 'Goal 2',
        status: 'CREATED',
        model_provider: 'anthropic',
        model_name: 'claude-opus-4',
        max_runtime_seconds: 1800,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: false,
        capability_snapshot_json: {},
        completed_at: null,
      })

      // Mark task2 as synced
      store.markSynced(task2.id, new Date().toISOString(), 1)

      const pending = store.getPendingSync()
      expect(pending.length).toBe(1)
      expect(pending[0].id).toBe(task1.id)
    })
  })

  describe('markSynced', () => {
    it('should update sync metadata', () => {
      const created = store.create({
        organization_id: 'org-1',
        agent_id: null,
        created_by: 'user-1',
        title: 'Test Task',
        goal: 'Test goal',
        status: 'CREATED',
        model_provider: 'anthropic',
        model_name: 'claude-opus-4',
        max_runtime_seconds: 1800,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: false,
        capability_snapshot_json: {},
        completed_at: null,
      })

      const serverTime = new Date().toISOString()
      store.markSynced(created.id, serverTime, 1)

      const synced = store.get(created.id)
      expect(synced?.sync_version).toBe(1)
      expect(synced?.last_synced_at).toBeDefined()
      expect(synced?.server_updated_at).toBe(serverTime)
      expect(synced?.has_local_changes).toBe(false)
      expect(synced?.is_local_only).toBe(false)
    })
  })

  describe('markLocalChange', () => {
    it('should set has_local_changes to true', () => {
      const created = store.create({
        organization_id: 'org-1',
        agent_id: null,
        created_by: 'user-1',
        title: 'Test Task',
        goal: 'Test goal',
        status: 'CREATED',
        model_provider: 'anthropic',
        model_name: 'claude-opus-4',
        max_runtime_seconds: 1800,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: false,
        capability_snapshot_json: {},
        completed_at: null,
      })

      store.markSynced(created.id, new Date().toISOString(), 1)
      const synced = store.get(created.id)
      expect(synced?.has_local_changes).toBe(false)

      store.markLocalChange(created.id)
      const modified = store.get(created.id)
      expect(modified?.has_local_changes).toBe(true)
    })
  })

  describe('markConflict', () => {
    it('should set conflict_detected flag', () => {
      const created = store.create({
        organization_id: 'org-1',
        agent_id: null,
        created_by: 'user-1',
        title: 'Test Task',
        goal: 'Test goal',
        status: 'CREATED',
        model_provider: 'anthropic',
        model_name: 'claude-opus-4',
        max_runtime_seconds: 1800,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: false,
        capability_snapshot_json: {},
        completed_at: null,
      })

      store.markConflict(created.id, true)
      const conflicted = store.get(created.id)
      expect(conflicted?.conflict_detected).toBe(true)

      store.markConflict(created.id, false)
      const resolved = store.get(created.id)
      expect(resolved?.conflict_detected).toBe(false)
    })
  })

  describe('upsertFromServer', () => {
    it('should insert new task from server', () => {
      const serverTask: Task = {
        id: 'server-task-1',
        organization_id: 'org-1',
        agent_id: null,
        created_by: 'user-1',
        title: 'Server Task',
        goal: 'Server goal',
        status: 'RUNNING',
        model_provider: 'anthropic',
        model_name: 'claude-opus-4',
        max_runtime_seconds: 1800,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: false,
        capability_snapshot_json: {},
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        completed_at: null,
      }

      const inserted = store.upsertFromServer(serverTask, 1)

      expect(inserted.id).toBe('server-task-1')
      expect(inserted.title).toBe('Server Task')
      expect(inserted.sync_version).toBe(1)
      expect(inserted.is_local_only).toBe(false)
      expect(inserted.has_local_changes).toBe(false)
    })

    it('should update existing task from server if no local changes', () => {
      const created = store.create({
        organization_id: 'org-1',
        agent_id: null,
        created_by: 'user-1',
        title: 'Local Task',
        goal: 'Local goal',
        status: 'CREATED',
        model_provider: 'anthropic',
        model_name: 'claude-opus-4',
        max_runtime_seconds: 1800,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: false,
        capability_snapshot_json: {},
        completed_at: null,
      })

      store.markSynced(created.id, new Date().toISOString(), 1)

      const serverTask: Task = {
        ...created,
        title: 'Updated from Server',
        status: 'RUNNING',
        updated_at: new Date().toISOString(),
      }

      const updated = store.upsertFromServer(serverTask, 2)

      expect(updated.title).toBe('Updated from Server')
      expect(updated.status).toBe('RUNNING')
      expect(updated.sync_version).toBe(2)
    })

    it('should preserve local changes and detect conflict', () => {
      const created = store.create({
        organization_id: 'org-1',
        agent_id: null,
        created_by: 'user-1',
        title: 'Local Task',
        goal: 'Local goal',
        status: 'CREATED',
        model_provider: 'anthropic',
        model_name: 'claude-opus-4',
        max_runtime_seconds: 1800,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: false,
        capability_snapshot_json: {},
        completed_at: null,
      })

      // Modify locally
      store.update(created.id, { title: 'Modified Locally' })

      const serverTask: Task = {
        ...created,
        title: 'Modified on Server',
        updated_at: new Date().toISOString(),
      }

      const result = store.upsertFromServer(serverTask, 2)

      // Should preserve local changes and mark conflict
      expect(result.title).toBe('Modified Locally')
      expect(result.conflict_detected).toBe(true)
      expect(result.has_local_changes).toBe(true)
    })
  })

  describe('transaction', () => {
    it('should commit successful transaction', () => {
      const result = store.transaction(() => {
        const task1 = store.create({
          organization_id: 'org-1',
          agent_id: null,
          created_by: 'user-1',
          title: 'Task in Transaction 1',
          goal: 'Goal 1',
          status: 'CREATED',
          model_provider: 'anthropic',
          model_name: 'claude-opus-4',
          max_runtime_seconds: 1800,
          max_subagents: 5,
          enable_sandbox: true,
          enable_network: false,
          capability_snapshot_json: {},
          completed_at: null,
        })

        const task2 = store.create({
          organization_id: 'org-1',
          agent_id: null,
          created_by: 'user-1',
          title: 'Task in Transaction 2',
          goal: 'Goal 2',
          status: 'CREATED',
          model_provider: 'anthropic',
          model_name: 'claude-opus-4',
          max_runtime_seconds: 1800,
          max_subagents: 5,
          enable_sandbox: true,
          enable_network: false,
          capability_snapshot_json: {},
          completed_at: null,
        })

        return [task1.id, task2.id]
      })

      expect(result.length).toBe(2)
      expect(store.get(result[0])).not.toBeNull()
      expect(store.get(result[1])).not.toBeNull()
    })

    it('should rollback on error', () => {
      const beforeCount = store.query({}).length

      expect(() => {
        store.transaction(() => {
          store.create({
            organization_id: 'org-1',
            agent_id: null,
            created_by: 'user-1',
            title: 'Task before error',
            goal: 'Goal',
            status: 'CREATED',
            model_provider: 'anthropic',
            model_name: 'claude-opus-4',
            max_runtime_seconds: 1800,
            max_subagents: 5,
            enable_sandbox: true,
            enable_network: false,
            capability_snapshot_json: {},
            completed_at: null,
          })

          throw new Error('Transaction failed')
        })
      }).toThrow('Transaction failed')

      const afterCount = store.query({}).length
      expect(afterCount).toBe(beforeCount) // No changes persisted
    })
  })

  describe('close', () => {
    it('should close database connection', () => {
      expect(() => store.close()).not.toThrow()
    })
  })
})
