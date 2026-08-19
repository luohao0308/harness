/**
 * SQLiteSyncService - Implementation of SyncService interface
 */

import type {
  SyncService,
  SyncDeltaRequest,
  SyncDeltaResponse,
  SyncOutcome,
  SyncPushConflict,
  SyncPushResult,
} from './sync-service'
import type { OfflineQueue } from '../stores/offline-queue'
import type { TaskStore } from '../stores/task-store'
import type { SyncOperation } from '../stores/types'
import type { SyncMetadata } from './sync-metadata'
import { getDesktopTelemetryPayloadBase } from './desktop-telemetry'
import { apiRequest, getAuthToken } from '../shared/api-client'

type JsonRequester = <T>(endpoint: string, options?: RequestInit) => Promise<T>

export type SQLiteSyncServiceOptions = {
  requestJson?: JsonRequester
}

export const LAST_SYNC_CONFLICTS_METADATA_KEY = 'last_sync_conflicts_json'

export class SQLiteSyncService implements SyncService {
  private requestJson: JsonRequester

  constructor(
    private apiBaseUrl: string,
    private offlineQueue: OfflineQueue,
    private taskStore: TaskStore,
    private syncMetadata: SyncMetadata,
    options: SQLiteSyncServiceOptions = {}
  ) {
    this.requestJson = options.requestJson ?? this.defaultRequestJson
  }

  async fetchDelta(request: SyncDeltaRequest): Promise<SyncDeltaResponse> {
    const params = new URLSearchParams()

    if (request.last_sync_timestamp) {
      params.append('since', request.last_sync_timestamp)
    }

    request.entity_types.forEach(type => {
      params.append('entity_types', type)
    })

    if (request.date_range) {
      params.append('start_date', request.date_range.start)
      params.append('end_date', request.date_range.end)
    }

    const data = await this.requestJson<{ tasks?: unknown[]; server_timestamp: string; has_more?: boolean }>(
      `/api/desktop/sync?${params.toString()}`
    )

    return {
      tasks: data.tasks || [],
      server_timestamp: data.server_timestamp,
      has_more: data.has_more || false,
    } as SyncDeltaResponse
  }

  async pushOperations(operations: SyncOperation[]): Promise<SyncPushResult> {
    if (operations.length === 0) {
      return { applied: 0, conflicts: [] }
    }

    const BATCH_SIZE = 50
    const batches: SyncOperation[][] = []
    const result: SyncPushResult = { applied: 0, conflicts: [] }

    for (let i = 0; i < operations.length; i += BATCH_SIZE) {
      batches.push(operations.slice(i, i + BATCH_SIZE))
    }

    for (const batch of batches) {
      const response = await this.requestJson<SyncPushResult>('/api/desktop/sync/operations', {
        method: 'POST',
        body: JSON.stringify({ operations: batch.map(toServerOperation) }),
      })

      result.applied += response.applied || 0
      result.conflicts.push(...(response.conflicts || []))
    }

    this.recordConflicts(result.conflicts)
    return result
  }

  async sync(): Promise<void> {
    // 1. Fetch delta from server
    const lastSyncTimestamp = await this.getLastSyncTimestamp()
    let outcome: SyncOutcome = 'success'
    try {
      const delta = await this.fetchDelta({
        last_sync_timestamp: lastSyncTimestamp,
        entity_types: ['task'],
      })

      // 2. Update local database with fetched changes
      for (const task of delta.tasks) {
        this.taskStore.upsertFromServer(task, 1)
      }

      // 3. Push local operations to server
      const pendingOps = [
        ...this.offlineQueue.getPending(),
        ...this.offlineQueue.getRetryable(5),
      ]
      if (pendingOps.length > 0) {
        for (const op of pendingOps) {
          if (op.id) {
            this.offlineQueue.markInProgress(op.id)
          }
        }

        try {
          const pushResult = await this.pushOperations(pendingOps)

          // 4. Mark non-conflicting operations as completed
          const conflictIds = new Set(
            pushResult.conflicts.map(conflict => conflict.operation_id).filter(Boolean),
          )
          const conflictEntities = new Set(
            pushResult.conflicts.filter(conflict => !conflict.operation_id).map(conflict => conflict.entity_id),
          )
          for (const op of pendingOps) {
            if (!op.id) continue
            if ((op.operation_id && conflictIds.has(op.operation_id)) || conflictEntities.has(op.entity_id)) {
              this.offlineQueue.markFailed(op.id, 'Server reported a sync conflict')
              if (op.entity_type === 'task') {
                this.taskStore.markConflict(op.entity_id, true)
              }
            } else {
              this.offlineQueue.markCompleted(op.id)
            }
          }
        } catch (error) {
          for (const op of pendingOps) {
            if (op.id) {
              this.offlineQueue.markFailed(op.id, error instanceof Error ? error.message : String(error))
            }
          }
          throw error
        }
      }

      // 5. Update last sync timestamp
      await this.setLastSyncTimestamp(delta.server_timestamp)
    } catch (error) {
      outcome = 'failure'
      throw error
    } finally {
      await this.reportSyncOutcome(outcome)
    }
  }

  private async getLastSyncTimestamp(): Promise<string | null> {
    return this.syncMetadata.getLastSyncTimestamp()
  }

  private async setLastSyncTimestamp(timestamp: string): Promise<void> {
    this.syncMetadata.setLastSyncTimestamp(timestamp)
  }

  private async reportSyncOutcome(outcome: SyncOutcome): Promise<void> {
    try {
      await apiRequest('/api/desktop/metrics', {
        method: 'POST',
        body: JSON.stringify({
          metric_name: outcome === 'success' ? 'sync_success' : 'sync_failure',
          ...getDesktopTelemetryPayloadBase(),
          value: 1,
          metadata: { source: 'sqlite-sync-service' },
        }),
      })
    } catch {
      // Sync success/failure telemetry is best-effort and must not change sync state.
    }
  }

  private recordConflicts(conflicts: SyncPushConflict[]): void {
    if (conflicts.length === 0) {
      this.syncMetadata.deleteMetadata(LAST_SYNC_CONFLICTS_METADATA_KEY)
      return
    }

    this.syncMetadata.setMetadata(LAST_SYNC_CONFLICTS_METADATA_KEY, JSON.stringify(conflicts))
  }

  private defaultRequestJson = async <T>(endpoint: string, options: RequestInit = {}): Promise<T> => {
    if (!this.apiBaseUrl) {
      return apiRequest<T>(endpoint, options)
    }

    const token = getAuthToken()
    const response = await fetch(`${this.apiBaseUrl}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(token && { Authorization: `Bearer ${token}` }),
        ...options.headers,
      },
    })

    if (!response.ok) {
      throw new Error(`Sync request failed: ${response.status} ${response.statusText}`)
    }

    return await response.json() as T
  }
}

function toServerOperation(operation: SyncOperation): {
  type: 'create' | 'update' | 'delete'
  entity_type: 'task' | 'offline_agent_run'
  entity_id: string
  data?: Record<string, unknown> | null
  timestamp: string
  operation_id?: string
} {
  return {
    type: operation.operation_type.toLowerCase() as 'create' | 'update' | 'delete',
    entity_type: operation.entity_type,
    entity_id: operation.entity_id,
    data: operation.payload_json ? JSON.parse(operation.payload_json) as Record<string, unknown> : null,
    timestamp: operation.client_timestamp,
    operation_id: operation.operation_id ?? (operation.id ? String(operation.id) : undefined),
  }
}
