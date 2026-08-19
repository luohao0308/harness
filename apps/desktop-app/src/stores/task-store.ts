/**
 * TaskStore - SQLite-backed local task storage with sync metadata
 */

import type {
  Task,
  TaskWithSyncMetadata,
  TaskQueryOptions,
  TransactionCallback,
} from './types'

export interface TaskStore {
  /**
   * Initialize database schema
   */
  initialize(): void

  /**
   * Create a new task
   */
  create(task: Omit<Task, 'id' | 'created_at' | 'updated_at'>): TaskWithSyncMetadata

  /**
   * Get task by ID
   */
  get(id: string): TaskWithSyncMetadata | null

  /**
   * Update task
   */
  update(id: string, updates: Partial<Task>): TaskWithSyncMetadata

  /**
   * Delete task (soft delete - marks for sync)
   */
  delete(id: string): void

  /**
   * Query tasks with filters
   */
  query(options?: TaskQueryOptions): TaskWithSyncMetadata[]

  /**
   * Get all tasks pending sync
   */
  getPendingSync(): TaskWithSyncMetadata[]

  /**
   * Mark task as synced with server
   */
  markSynced(id: string, serverUpdatedAt: string, syncVersion: number): void

  /**
   * Mark task as having local changes
   */
  markLocalChange(id: string): void

  /**
   * Detect conflict for task
   */
  markConflict(id: string, hasConflict: boolean): void

  /**
   * Upsert task from server (during sync)
   */
  upsertFromServer(task: Task, syncVersion: number): TaskWithSyncMetadata

  /**
   * Execute operations in a transaction
   */
  transaction<T>(callback: TransactionCallback<T>): T

  /**
   * Close database connection
   */
  close(): void
}
