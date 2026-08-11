/**
 * OfflineQueue unit tests - TDD RED phase
 * Tests sync operation queueing and retry logic
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { OfflineQueue } from '../offline-queue'
import { SQLiteOfflineQueue } from '../sqlite-offline-queue'

let queue: OfflineQueue

describe('OfflineQueue', () => {
  beforeEach(() => {
    queue = new SQLiteOfflineQueue(':memory:')
    queue.initialize()
  })

  afterEach(() => {
    queue.close()
  })

  describe('initialize', () => {
    it('should create sync_operations table', () => {
      expect(() => queue.initialize()).not.toThrow()
    })
  })

  describe('enqueue', () => {
    it('should enqueue CREATE operation', () => {
      const operation = queue.enqueue({
        operation_type: 'CREATE',
        entity_type: 'task',
        entity_id: 'task-1',
        payload_json: JSON.stringify({ title: 'New Task' }),
        client_timestamp: new Date().toISOString(),
      })

      expect(operation.id).toBeDefined()
      expect(operation.operation_type).toBe('CREATE')
      expect(operation.status).toBe('PENDING')
      expect(operation.retry_count).toBe(0)
      expect(operation.error_message).toBeNull()
    })

    it('should enqueue UPDATE operation', () => {
      const operation = queue.enqueue({
        operation_type: 'UPDATE',
        entity_type: 'task',
        entity_id: 'task-1',
        payload_json: JSON.stringify({ title: 'Updated Task' }),
        client_timestamp: new Date().toISOString(),
      })

      expect(operation.operation_type).toBe('UPDATE')
      expect(operation.status).toBe('PENDING')
    })

    it('should enqueue DELETE operation', () => {
      const operation = queue.enqueue({
        operation_type: 'DELETE',
        entity_type: 'task',
        entity_id: 'task-1',
        payload_json: JSON.stringify({}),
        client_timestamp: new Date().toISOString(),
      })

      expect(operation.operation_type).toBe('DELETE')
      expect(operation.status).toBe('PENDING')
    })
  })

  describe('getPending', () => {
    it('should return all pending operations', () => {
      queue.enqueue({
        operation_type: 'CREATE',
        entity_type: 'task',
        entity_id: 'task-1',
        payload_json: JSON.stringify({ title: 'Task 1' }),
        client_timestamp: new Date().toISOString(),
      })

      queue.enqueue({
        operation_type: 'UPDATE',
        entity_type: 'task',
        entity_id: 'task-2',
        payload_json: JSON.stringify({ title: 'Task 2' }),
        client_timestamp: new Date().toISOString(),
      })

      const pending = queue.getPending()
      expect(pending.length).toBe(2)
      expect(pending.every(op => op.status === 'PENDING')).toBe(true)
    })

    it('should return empty array when no pending operations', () => {
      const pending = queue.getPending()
      expect(pending).toEqual([])
    })

    it('should not include IN_PROGRESS operations', () => {
      const op = queue.enqueue({
        operation_type: 'CREATE',
        entity_type: 'task',
        entity_id: 'task-1',
        payload_json: JSON.stringify({ title: 'Task 1' }),
        client_timestamp: new Date().toISOString(),
      })

      queue.markInProgress(op.id!)

      const pending = queue.getPending()
      expect(pending.length).toBe(0)
    })
  })

  describe('getRetryable', () => {
    it('should return failed operations below max retries', () => {
      const op = queue.enqueue({
        operation_type: 'CREATE',
        entity_type: 'task',
        entity_id: 'task-1',
        payload_json: JSON.stringify({ title: 'Task 1' }),
        client_timestamp: new Date().toISOString(),
      })

      queue.markFailed(op.id!, 'Network error')

      const retryable = queue.getRetryable(3)
      expect(retryable.length).toBe(1)
      expect(retryable[0].retry_count).toBe(1)
    })

    it('should not return operations at max retries', () => {
      const op = queue.enqueue({
        operation_type: 'CREATE',
        entity_type: 'task',
        entity_id: 'task-1',
        payload_json: JSON.stringify({ title: 'Task 1' }),
        client_timestamp: new Date().toISOString(),
      })

      queue.markFailed(op.id!, 'Error 1')
      queue.markFailed(op.id!, 'Error 2')
      queue.markFailed(op.id!, 'Error 3')

      const retryable = queue.getRetryable(3)
      expect(retryable.length).toBe(0)
    })
  })

  describe('markInProgress', () => {
    it('should update operation status to IN_PROGRESS', () => {
      const op = queue.enqueue({
        operation_type: 'CREATE',
        entity_type: 'task',
        entity_id: 'task-1',
        payload_json: JSON.stringify({ title: 'Task 1' }),
        client_timestamp: new Date().toISOString(),
      })

      queue.markInProgress(op.id!)
      const updated = queue.get(op.id!)

      expect(updated?.status).toBe('IN_PROGRESS')
    })
  })

  describe('markCompleted', () => {
    it('should update operation status to COMPLETED', () => {
      const op = queue.enqueue({
        operation_type: 'CREATE',
        entity_type: 'task',
        entity_id: 'task-1',
        payload_json: JSON.stringify({ title: 'Task 1' }),
        client_timestamp: new Date().toISOString(),
      })

      queue.markCompleted(op.id!)
      const updated = queue.get(op.id!)

      expect(updated?.status).toBe('COMPLETED')
    })
  })

  describe('markFailed', () => {
    it('should increment retry count and set error message', () => {
      const op = queue.enqueue({
        operation_type: 'CREATE',
        entity_type: 'task',
        entity_id: 'task-1',
        payload_json: JSON.stringify({ title: 'Task 1' }),
        client_timestamp: new Date().toISOString(),
      })

      queue.markFailed(op.id!, 'Network timeout')
      const updated = queue.get(op.id!)

      expect(updated?.status).toBe('FAILED')
      expect(updated?.retry_count).toBe(1)
      expect(updated?.error_message).toBe('Network timeout')
      expect(updated?.last_retry_at).not.toBeNull()
    })

    it('should accumulate retry count on multiple failures', () => {
      const op = queue.enqueue({
        operation_type: 'CREATE',
        entity_type: 'task',
        entity_id: 'task-1',
        payload_json: JSON.stringify({ title: 'Task 1' }),
        client_timestamp: new Date().toISOString(),
      })

      queue.markFailed(op.id!, 'Error 1')
      queue.markFailed(op.id!, 'Error 2')
      const updated = queue.get(op.id!)

      expect(updated?.retry_count).toBe(2)
      expect(updated?.error_message).toBe('Error 2')
    })
  })

  describe('cleanup', () => {
    it('should delete completed operations older than threshold', async () => {
      const oldOp = queue.enqueue({
        operation_type: 'CREATE',
        entity_type: 'task',
        entity_id: 'task-1',
        payload_json: JSON.stringify({ title: 'Old Task' }),
        client_timestamp: new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString(),
      })

      const recentOp = queue.enqueue({
        operation_type: 'CREATE',
        entity_type: 'task',
        entity_id: 'task-2',
        payload_json: JSON.stringify({ title: 'Recent Task' }),
        client_timestamp: new Date().toISOString(),
      })

      queue.markCompleted(oldOp.id!)
      queue.markCompleted(recentOp.id!)

      queue.cleanup(7)

      expect(queue.get(oldOp.id!)).toBeNull()
      expect(queue.get(recentOp.id!)).not.toBeNull()
    })

    it('should not delete pending or failed operations', () => {
      const pending = queue.enqueue({
        operation_type: 'CREATE',
        entity_type: 'task',
        entity_id: 'task-1',
        payload_json: JSON.stringify({ title: 'Pending Task' }),
        client_timestamp: new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString(),
      })

      const failed = queue.enqueue({
        operation_type: 'CREATE',
        entity_type: 'task',
        entity_id: 'task-2',
        payload_json: JSON.stringify({ title: 'Failed Task' }),
        client_timestamp: new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString(),
      })

      queue.markFailed(failed.id!, 'Network error')

      queue.cleanup(7)

      expect(queue.get(pending.id!)).not.toBeNull()
      expect(queue.get(failed.id!)).not.toBeNull()
    })
  })

  describe('get', () => {
    it('should return operation by id', () => {
      const op = queue.enqueue({
        operation_type: 'CREATE',
        entity_type: 'task',
        entity_id: 'task-1',
        payload_json: JSON.stringify({ title: 'Task 1' }),
        client_timestamp: new Date().toISOString(),
      })

      const retrieved = queue.get(op.id!)

      expect(retrieved).not.toBeNull()
      expect(retrieved?.id).toBe(op.id)
      expect(retrieved?.entity_id).toBe('task-1')
    })

    it('should return null for non-existent id', () => {
      const retrieved = queue.get(99999)
      expect(retrieved).toBeNull()
    })
  })

  describe('close', () => {
    it('should close database connection', () => {
      expect(() => queue.close()).not.toThrow()
    })
  })
})
