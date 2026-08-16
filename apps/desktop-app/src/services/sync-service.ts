/**
 * SyncService - Interface for synchronizing local data with backend
 */

import type { Task } from '../stores/types'

export interface SyncDeltaRequest {
  last_sync_timestamp: string | null
  entity_types: string[]
  date_range?: {
    start: string
    end: string
  }
}

export interface SyncDeltaResponse {
  tasks: Task[]
  server_timestamp: string
  has_more: boolean
}

export interface SyncService {
  /**
   * Fetch incremental changes from server since last sync
   */
  fetchDelta(request: SyncDeltaRequest): Promise<SyncDeltaResponse>

  /**
   * Push local operations to server
   */
  pushOperations(operations: any[]): Promise<SyncPushResult>

  /**
   * Perform full sync cycle: fetch delta, resolve conflicts, push local changes
   */
  sync(): Promise<void>
}

export type SyncOutcome = 'success' | 'failure'

export type SyncPushConflict = {
  entity_id: string
  entity_type: string
  server_version: Record<string, unknown>
  client_version: Record<string, unknown>
}

export type SyncPushResult = {
  applied: number
  conflicts: SyncPushConflict[]
}
