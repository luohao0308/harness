/**
 * Type definitions for TaskStore and sync-related types
 */

export interface Task {
  id: string
  organization_id: string | null
  agent_id: string | null
  created_by: string | null
  title: string
  goal: string
  status: string
  model_provider: string
  model_name: string
  max_runtime_seconds: number
  max_subagents: number
  enable_sandbox: boolean
  enable_network: boolean
  capability_snapshot_json: Record<string, unknown>
  created_at: string
  updated_at: string
  completed_at: string | null
}

export interface TaskWithSyncMetadata extends Task {
  sync_version: number
  last_synced_at: string | null
  server_updated_at: string | null
  is_local_only: boolean
  has_local_changes: boolean
  conflict_detected: boolean
}

export interface SyncOperation {
  id?: number
  operation_type: 'CREATE' | 'UPDATE' | 'DELETE'
  entity_type: 'task'
  entity_id: string
  payload_json: string
  client_timestamp: string
  retry_count: number
  last_retry_at: string | null
  status: 'PENDING' | 'IN_PROGRESS' | 'FAILED' | 'COMPLETED'
  error_message: string | null
}

export interface SyncConflict {
  id?: number
  entity_type: 'task'
  entity_id: string
  field_name: string
  local_value: string
  server_value: string
  local_updated_at: string
  server_updated_at: string
  resolved: boolean
  resolution_choice: 'local' | 'server' | 'merged' | null
  created_at: string
}

export interface SyncMetadata {
  key: string
  value: string
  updated_at: string
}

export interface TaskQueryOptions {
  status?: string
  agent_id?: string
  organization_id?: string
  since?: string
  limit?: number
  offset?: number
  has_local_changes?: boolean
}

export interface TransactionCallback<T> {
  (db: unknown): T
}
