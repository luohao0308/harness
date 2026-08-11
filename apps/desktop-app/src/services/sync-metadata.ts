/**
 * SyncMetadata - Interface for managing sync metadata in SQLite
 */

export interface SyncMetadata {
  /**
   * Initialize sync_metadata table
   */
  initialize(): void

  /**
   * Get last sync timestamp
   */
  getLastSyncTimestamp(): string | null

  /**
   * Set last sync timestamp
   */
  setLastSyncTimestamp(timestamp: string): void

  /**
   * Get arbitrary metadata by key
   */
  getMetadata(key: string): string | null

  /**
   * Set arbitrary metadata by key
   */
  setMetadata(key: string, value: string): void

  /**
   * Delete metadata by key
   */
  deleteMetadata(key: string): void

  /**
   * Close database connection
   */
  close(): void
}
