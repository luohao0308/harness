/**
 * SyncMetadata tests - RED phase
 * Tests for sync_metadata table operations
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import Database from 'better-sqlite3'
import { SQLiteSyncMetadata } from '../sqlite-sync-metadata'
import type { SyncMetadata } from '../sync-metadata'
import { tmpdir } from 'os'
import { join } from 'path'
import { unlinkSync } from 'fs'

describe('SyncMetadata', () => {
  let db: Database.Database
  let metadata: SyncMetadata
  let dbPath: string

  beforeEach(() => {
    // Create temporary database
    dbPath = join(tmpdir(), `test-sync-metadata-${Date.now()}.db`)
    db = new Database(dbPath)
    metadata = new SQLiteSyncMetadata(db)
    metadata.initialize()
  })

  afterEach(() => {
    metadata.close()
    try {
      unlinkSync(dbPath)
    } catch {
      // Ignore cleanup errors
    }
  })

  describe('initialize', () => {
    it('should create sync_metadata table', () => {
      const tableExists = db
        .prepare(
          "SELECT name FROM sqlite_master WHERE type='table' AND name='sync_metadata'"
        )
        .get()

      expect(tableExists).toBeDefined()
    })

    it('should handle multiple initialize calls without error', () => {
      expect(() => {
        metadata.initialize()
        metadata.initialize()
      }).not.toThrow()
    })
  })

  describe('getLastSyncTimestamp', () => {
    it('should return null when no sync has occurred', () => {
      const timestamp = metadata.getLastSyncTimestamp()

      expect(timestamp).toBeNull()
    })

    it('should return last sync timestamp after sync', () => {
      const testTimestamp = '2026-06-25T12:00:00.000Z'
      metadata.setLastSyncTimestamp(testTimestamp)

      const timestamp = metadata.getLastSyncTimestamp()

      expect(timestamp).toBe(testTimestamp)
    })
  })

  describe('setLastSyncTimestamp', () => {
    it('should store sync timestamp', () => {
      const testTimestamp = '2026-06-25T12:00:00.000Z'

      metadata.setLastSyncTimestamp(testTimestamp)

      const timestamp = metadata.getLastSyncTimestamp()
      expect(timestamp).toBe(testTimestamp)
    })

    it('should update existing timestamp', () => {
      const firstTimestamp = '2026-06-25T12:00:00.000Z'
      const secondTimestamp = '2026-06-25T13:00:00.000Z'

      metadata.setLastSyncTimestamp(firstTimestamp)
      metadata.setLastSyncTimestamp(secondTimestamp)

      const timestamp = metadata.getLastSyncTimestamp()
      expect(timestamp).toBe(secondTimestamp)
    })

    it('should handle ISO 8601 timestamps', () => {
      const testTimestamp = '2026-06-25T12:34:56.789Z'

      metadata.setLastSyncTimestamp(testTimestamp)

      const timestamp = metadata.getLastSyncTimestamp()
      expect(timestamp).toBe(testTimestamp)
    })
  })

  describe('getMetadata', () => {
    it('should return null for non-existent key', () => {
      const value = metadata.getMetadata('non_existent_key')

      expect(value).toBeNull()
    })

    it('should return stored metadata value', () => {
      metadata.setMetadata('test_key', 'test_value')

      const value = metadata.getMetadata('test_key')

      expect(value).toBe('test_value')
    })
  })

  describe('setMetadata', () => {
    it('should store metadata key-value pair', () => {
      metadata.setMetadata('app_version', '1.0.0')

      const value = metadata.getMetadata('app_version')
      expect(value).toBe('1.0.0')
    })

    it('should update existing metadata', () => {
      metadata.setMetadata('app_version', '1.0.0')
      metadata.setMetadata('app_version', '1.0.1')

      const value = metadata.getMetadata('app_version')
      expect(value).toBe('1.0.1')
    })

    it('should handle multiple keys independently', () => {
      metadata.setMetadata('key1', 'value1')
      metadata.setMetadata('key2', 'value2')

      expect(metadata.getMetadata('key1')).toBe('value1')
      expect(metadata.getMetadata('key2')).toBe('value2')
    })
  })

  describe('deleteMetadata', () => {
    it('should delete metadata by key', () => {
      metadata.setMetadata('test_key', 'test_value')
      metadata.deleteMetadata('test_key')

      const value = metadata.getMetadata('test_key')
      expect(value).toBeNull()
    })

    it('should handle deleting non-existent key', () => {
      expect(() => {
        metadata.deleteMetadata('non_existent_key')
      }).not.toThrow()
    })
  })

  describe('integration', () => {
    it('should support sync workflow lifecycle', () => {
      // Initial state - no sync
      expect(metadata.getLastSyncTimestamp()).toBeNull()

      // First sync
      metadata.setLastSyncTimestamp('2026-06-25T12:00:00.000Z')
      expect(metadata.getLastSyncTimestamp()).toBe('2026-06-25T12:00:00.000Z')

      // Store additional metadata
      metadata.setMetadata('last_sync_status', 'success')
      metadata.setMetadata('synced_tasks_count', '42')

      expect(metadata.getMetadata('last_sync_status')).toBe('success')
      expect(metadata.getMetadata('synced_tasks_count')).toBe('42')

      // Second sync
      metadata.setLastSyncTimestamp('2026-06-25T13:00:00.000Z')
      metadata.setMetadata('synced_tasks_count', '55')

      expect(metadata.getLastSyncTimestamp()).toBe('2026-06-25T13:00:00.000Z')
      expect(metadata.getMetadata('synced_tasks_count')).toBe('55')
      expect(metadata.getMetadata('last_sync_status')).toBe('success')
    })
  })
})
