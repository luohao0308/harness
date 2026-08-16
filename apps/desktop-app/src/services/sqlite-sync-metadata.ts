/**
 * SQLiteSyncMetadata - SQLite implementation of SyncMetadata interface
 */

import type Database from 'better-sqlite3'
import type { SyncMetadata } from './sync-metadata'

const LAST_SYNC_KEY = 'last_sync_timestamp'

export class SQLiteSyncMetadata implements SyncMetadata {
  constructor(private db: Database.Database) {}

  initialize(): void {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS sync_metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
      )
    `)
  }

  getLastSyncTimestamp(): string | null {
    return this.getMetadata(LAST_SYNC_KEY)
  }

  setLastSyncTimestamp(timestamp: string): void {
    this.setMetadata(LAST_SYNC_KEY, timestamp)
  }

  getMetadata(key: string): string | null {
    const stmt = this.db.prepare('SELECT value FROM sync_metadata WHERE key = ?')
    const row = stmt.get(key) as { value: string } | undefined

    return row ? row.value : null
  }

  setMetadata(key: string, value: string): void {
    const stmt = this.db.prepare(`
      INSERT INTO sync_metadata (key, value, updated_at)
      VALUES (?, ?, datetime('now'))
      ON CONFLICT(key) DO UPDATE SET
        value = excluded.value,
        updated_at = datetime('now')
    `)

    stmt.run(key, value)
  }

  deleteMetadata(key: string): void {
    const stmt = this.db.prepare('DELETE FROM sync_metadata WHERE key = ?')
    stmt.run(key)
  }

  close(): void {
    this.db.close()
  }
}
