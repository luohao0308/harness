/**
 * SQLiteOfflineQueue - SQLite implementation of OfflineQueue interface
 */

import Database from 'better-sqlite3'
import type { SyncOperation } from './types'
import type { OfflineQueue } from './offline-queue'

export class SQLiteOfflineQueue implements OfflineQueue {
  private db: Database.Database

  constructor(dbPath: string) {
    this.db = new Database(dbPath)
    this.db.pragma('journal_mode = WAL')
    this.db.pragma('foreign_keys = ON')
  }

  initialize(): void {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS sync_operations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operation_id TEXT,
        operation_type TEXT NOT NULL CHECK(operation_type IN ('CREATE', 'UPDATE', 'DELETE')),
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        client_timestamp TEXT NOT NULL,
        retry_count INTEGER NOT NULL DEFAULT 0,
        last_retry_at TEXT,
        status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'IN_PROGRESS', 'FAILED', 'COMPLETED')),
        error_message TEXT,
        created_at TEXT NOT NULL
      );

      CREATE INDEX IF NOT EXISTS idx_sync_operations_status ON sync_operations(status);
      CREATE INDEX IF NOT EXISTS idx_sync_operations_entity ON sync_operations(entity_type, entity_id);
      CREATE INDEX IF NOT EXISTS idx_sync_operations_created_at ON sync_operations(created_at);
    `)
    const columns = this.db.prepare(`PRAGMA table_info(sync_operations)`).all() as Array<{ name: string }>
    if (!columns.some(column => column.name === 'operation_id')) {
      this.db.exec(`ALTER TABLE sync_operations ADD COLUMN operation_id TEXT`)
    }
    this.db.prepare(`
      UPDATE sync_operations
      SET status = 'PENDING'
      WHERE status = 'IN_PROGRESS'
    `).run()
  }

  enqueue(
    operation: Omit<SyncOperation, 'id' | 'retry_count' | 'last_retry_at' | 'status' | 'error_message'>
  ): SyncOperation {
    const stmt = this.db.prepare(`
      INSERT INTO sync_operations (
        operation_id, operation_type, entity_type, entity_id, payload_json, client_timestamp,
        retry_count, last_retry_at, status, error_message, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, 0, NULL, 'PENDING', NULL, ?)
    `)

    const result = stmt.run(
      operation.operation_id ?? null,
      operation.operation_type,
      operation.entity_type,
      operation.entity_id,
      operation.payload_json,
      operation.client_timestamp,
      operation.client_timestamp
    )

    const created = this.get(result.lastInsertRowid as number)
    if (!created) {
      throw new Error(`Failed to enqueue operation`)
    }

    return created
  }

  getPending(): SyncOperation[] {
    const stmt = this.db.prepare(`
      SELECT * FROM sync_operations
      WHERE status = 'PENDING'
      ORDER BY created_at ASC
    `)

    const rows = stmt.all() as RawSyncOperationRow[]
    return rows.map(row => this.mapRowToOperation(row))
  }

  getRetryable(maxRetries: number): SyncOperation[] {
    const stmt = this.db.prepare(`
      SELECT * FROM sync_operations
      WHERE status = 'FAILED'
        AND retry_count < ?
      ORDER BY last_retry_at ASC
    `)

    const rows = stmt.all(maxRetries) as RawSyncOperationRow[]
    return rows.map(row => this.mapRowToOperation(row))
  }

  markInProgress(id: number): void {
    const stmt = this.db.prepare(`
      UPDATE sync_operations
      SET status = 'IN_PROGRESS'
      WHERE id = ?
    `)

    stmt.run(id)
  }

  markCompleted(id: number): void {
    const stmt = this.db.prepare(`
      UPDATE sync_operations
      SET status = 'COMPLETED'
      WHERE id = ?
    `)

    stmt.run(id)
  }

  markFailed(id: number, errorMessage: string): void {
    const now = new Date().toISOString()

    const stmt = this.db.prepare(`
      UPDATE sync_operations
      SET status = 'FAILED',
          retry_count = retry_count + 1,
          last_retry_at = ?,
          error_message = ?
      WHERE id = ?
    `)

    stmt.run(now, errorMessage, id)
  }

  cleanup(olderThanDays: number): void {
    const threshold = new Date()
    threshold.setDate(threshold.getDate() - olderThanDays)

    const stmt = this.db.prepare(`
      DELETE FROM sync_operations
      WHERE status = 'COMPLETED'
        AND datetime(created_at) < datetime(?)
    `)

    stmt.run(threshold.toISOString())
  }

  get(id: number): SyncOperation | null {
    const stmt = this.db.prepare(`
      SELECT * FROM sync_operations WHERE id = ?
    `)

    const row = stmt.get(id) as RawSyncOperationRow | undefined

    if (!row) {
      return null
    }

    return this.mapRowToOperation(row)
  }

  close(): void {
    this.db.close()
  }

  private mapRowToOperation(row: RawSyncOperationRow): SyncOperation {
    return {
      id: row.id,
      operation_id: row.operation_id ?? undefined,
      operation_type: row.operation_type as 'CREATE' | 'UPDATE' | 'DELETE',
      entity_type: row.entity_type as 'task' | 'offline_agent_run',
      entity_id: row.entity_id,
      payload_json: row.payload_json,
      client_timestamp: row.client_timestamp,
      retry_count: row.retry_count,
      last_retry_at: row.last_retry_at,
      status: row.status as 'PENDING' | 'IN_PROGRESS' | 'FAILED' | 'COMPLETED',
      error_message: row.error_message,
    }
  }
}

interface RawSyncOperationRow {
  id: number
  operation_id: string | null
  operation_type: string
  entity_type: string
  entity_id: string
  payload_json: string
  client_timestamp: string
  retry_count: number
  last_retry_at: string | null
  status: string
  error_message: string | null
}
