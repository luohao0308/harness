/**
 * OfflineQueue - Queue for offline operations to sync when reconnected
 */

import type { SyncOperation } from './types'

export interface OfflineQueue {
  /**
   * Initialize sync_operations table
   */
  initialize(): void

  /**
   * Enqueue an operation for sync
   */
  enqueue(operation: Omit<SyncOperation, 'id' | 'retry_count' | 'last_retry_at' | 'status' | 'error_message'>): SyncOperation

  /**
   * Get all pending operations
   */
  getPending(): SyncOperation[]

  /**
   * Get failed operations that can be retried
   */
  getRetryable(maxRetries: number): SyncOperation[]

  /**
   * Mark operation as in progress
   */
  markInProgress(id: number): void

  /**
   * Mark operation as completed
   */
  markCompleted(id: number): void

  /**
   * Mark operation as failed and increment retry count
   */
  markFailed(id: number, errorMessage: string): void

  /**
   * Delete completed operations older than a threshold
   */
  cleanup(olderThanDays: number): void

  /**
   * Get operation by ID
   */
  get(id: number): SyncOperation | null

  /**
   * Close database connection
   */
  close(): void
}
