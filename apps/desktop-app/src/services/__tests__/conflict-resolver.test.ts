/**
 * ConflictResolver tests - RED phase
 */

import { describe, it, expect } from 'vitest'
import { SQLiteConflictResolver } from '../sqlite-conflict-resolver'
import type { ConflictResolver, ConflictResolution, FieldConflict } from '../conflict-resolver'
import type { Task } from '../../stores/types'

describe('ConflictResolver', () => {
  describe('detectConflicts', () => {
    it('should detect no conflicts when fields are identical', () => {
      const resolver: ConflictResolver = new SQLiteConflictResolver()

      const localTask: Partial<Task> = {
        id: 'task-1',
        title: 'Task Title',
        status: 'pending',
      }

      const serverTask: Partial<Task> = {
        id: 'task-1',
        title: 'Task Title',
        status: 'pending',
      }

      const conflicts = resolver.detectConflicts(localTask, serverTask)

      expect(conflicts).toEqual([])
    })

    it('should detect conflicts when non-conflicting fields differ', () => {
      const resolver: ConflictResolver = new SQLiteConflictResolver()

      const localTask: Partial<Task> = {
        id: 'task-1',
        title: 'Local Title',
        status: 'pending',
      }

      const serverTask: Partial<Task> = {
        id: 'task-1',
        title: 'Server Title',
        status: 'pending',
      }

      const conflicts = resolver.detectConflicts(localTask, serverTask)

      expect(conflicts.length).toBeGreaterThan(0)
      expect(conflicts[0].field).toBe('title')
      expect(conflicts[0].localValue).toBe('Local Title')
      expect(conflicts[0].serverValue).toBe('Server Title')
    })

    it('should handle multiple conflicting fields', () => {
      const resolver: ConflictResolver = new SQLiteConflictResolver()

      const localTask: Partial<Task> = {
        id: 'task-1',
        title: 'Local Title',
        status: 'in_progress',
        goal: 'Local goal',
      }

      const serverTask: Partial<Task> = {
        id: 'task-1',
        title: 'Server Title',
        status: 'completed',
        goal: 'Server goal',
      }

      const conflicts = resolver.detectConflicts(localTask, serverTask)

      expect(conflicts.length).toBe(3)
      expect(conflicts.map(c => c.field).sort()).toEqual(['goal', 'status', 'title'])
    })

    it('should ignore metadata fields (created_at, updated_at)', () => {
      const resolver: ConflictResolver = new SQLiteConflictResolver()

      const localTask: Partial<Task> = {
        id: 'task-1',
        title: 'Task Title',
        created_at: '2026-06-24T00:00:00.000Z',
        updated_at: '2026-06-24T12:00:00.000Z',
      }

      const serverTask: Partial<Task> = {
        id: 'task-1',
        title: 'Task Title',
        created_at: '2026-06-24T00:00:00.000Z',
        updated_at: '2026-06-25T00:00:00.000Z',
      }

      const conflicts = resolver.detectConflicts(localTask, serverTask)

      expect(conflicts).toEqual([])
    })
  })

  describe('autoMerge', () => {
    it('should automatically merge non-conflicting fields', () => {
      const resolver: ConflictResolver = new SQLiteConflictResolver()

      const localTask: Partial<Task> = {
        id: 'task-1',
        title: 'Local Title',
        status: 'pending',
        goal: 'Shared goal',
      }

      const serverTask: Partial<Task> = {
        id: 'task-1',
        title: 'Server Title',
        status: 'pending',
        goal: 'Shared goal',
      }

      const conflicts: FieldConflict[] = [
        {
          field: 'title',
          localValue: 'Local Title',
          serverValue: 'Server Title',
          canAutoMerge: false,
        },
      ]

      const resolution = resolver.autoMerge(localTask, serverTask, conflicts)

      expect(resolution.merged.goal).toBe('Shared goal')
      expect(resolution.merged.status).toBe('pending')
      expect(resolution.requiresUserDecision).toBe(true)
      expect(resolution.unresolvedConflicts.length).toBe(1)
      expect(resolution.unresolvedConflicts[0].field).toBe('title')
    })

    it('should use last-write-wins for timestamp-based conflicts', () => {
      const resolver: ConflictResolver = new SQLiteConflictResolver()

      const localTask: Partial<Task> = {
        id: 'task-1',
        title: 'Local Title',
        updated_at: '2026-06-25T12:00:00.000Z',
      }

      const serverTask: Partial<Task> = {
        id: 'task-1',
        title: 'Server Title',
        updated_at: '2026-06-25T11:00:00.000Z',
      }

      const conflicts: FieldConflict[] = [
        {
          field: 'title',
          localValue: 'Local Title',
          serverValue: 'Server Title',
          canAutoMerge: true,
        },
      ]

      const resolution = resolver.autoMerge(localTask, serverTask, conflicts)

      expect(resolution.merged.title).toBe('Local Title')
      expect(resolution.requiresUserDecision).toBe(false)
      expect(resolution.unresolvedConflicts).toEqual([])
    })

    it('should merge status transitions intelligently', () => {
      const resolver: ConflictResolver = new SQLiteConflictResolver()

      const localTask: Partial<Task> = {
        id: 'task-1',
        status: 'in_progress',
      }

      const serverTask: Partial<Task> = {
        id: 'task-1',
        status: 'pending',
      }

      const conflicts: FieldConflict[] = [
        {
          field: 'status',
          localValue: 'in_progress',
          serverValue: 'pending',
          canAutoMerge: true,
        },
      ]

      const resolution = resolver.autoMerge(localTask, serverTask, conflicts)

      // in_progress > pending, so prefer local
      expect(resolution.merged.status).toBe('in_progress')
      expect(resolution.requiresUserDecision).toBe(false)
    })

    it('should require user decision for conflicting text fields', () => {
      const resolver: ConflictResolver = new SQLiteConflictResolver()

      const localTask: Partial<Task> = {
        id: 'task-1',
        title: 'Local Title',
        goal: 'Local goal',
      }

      const serverTask: Partial<Task> = {
        id: 'task-1',
        title: 'Server Title',
        goal: 'Server goal',
      }

      const conflicts: FieldConflict[] = [
        {
          field: 'title',
          localValue: 'Local Title',
          serverValue: 'Server Title',
          canAutoMerge: false,
        },
        {
          field: 'goal',
          localValue: 'Local goal',
          serverValue: 'Server goal',
          canAutoMerge: false,
        },
      ]

      const resolution = resolver.autoMerge(localTask, serverTask, conflicts)

      expect(resolution.requiresUserDecision).toBe(true)
      expect(resolution.unresolvedConflicts.length).toBe(2)
      expect(resolution.unresolvedConflicts.map(c => c.field).sort()).toEqual(['goal', 'title'])
    })
  })

  describe('applyUserResolution', () => {
    it('should apply user choices to merged result', () => {
      const resolver: ConflictResolver = new SQLiteConflictResolver()

      const merged: Partial<Task> = {
        id: 'task-1',
        status: 'pending',
      }

      const userChoices: Record<string, 'local' | 'server'> = {
        title: 'local',
        goal: 'server',
      }

      const conflicts: FieldConflict[] = [
        {
          field: 'title',
          localValue: 'Local Title',
          serverValue: 'Server Title',
          canAutoMerge: false,
        },
        {
          field: 'goal',
          localValue: 'Local goal',
          serverValue: 'Server goal',
          canAutoMerge: false,
        },
      ]

      const result = resolver.applyUserResolution(merged, conflicts, userChoices)

      expect(result.title).toBe('Local Title')
      expect(result.goal).toBe('Server goal')
      expect(result.status).toBe('pending')
    })

    it('should throw error if user choices are incomplete', () => {
      const resolver: ConflictResolver = new SQLiteConflictResolver()

      const merged: Partial<Task> = {
        id: 'task-1',
      }

      const userChoices: Record<string, 'local' | 'server'> = {
        title: 'local',
      }

      const conflicts: FieldConflict[] = [
        {
          field: 'title',
          localValue: 'Local Title',
          serverValue: 'Server Title',
          canAutoMerge: false,
        },
        {
          field: 'goal',
          localValue: 'Local goal',
          serverValue: 'Server goal',
          canAutoMerge: false,
        },
      ]

      expect(() => {
        resolver.applyUserResolution(merged, conflicts, userChoices)
      }).toThrow()
    })
  })

  describe('resolve', () => {
    it('should resolve conflicts without user input when auto-merge succeeds', () => {
      const resolver: ConflictResolver = new SQLiteConflictResolver()

      const localTask: Partial<Task> = {
        id: 'task-1',
        title: 'Shared Title',
        status: 'in_progress',
      }

      const serverTask: Partial<Task> = {
        id: 'task-1',
        title: 'Shared Title',
        status: 'pending',
      }

      const resolution = resolver.resolve(localTask, serverTask)

      expect(resolution.requiresUserDecision).toBe(false)
      expect(resolution.merged.status).toBe('in_progress')
    })

    it('should flag conflicts that require user decision', () => {
      const resolver: ConflictResolver = new SQLiteConflictResolver()

      const localTask: Partial<Task> = {
        id: 'task-1',
        title: 'Local Title',
        goal: 'Local goal',
      }

      const serverTask: Partial<Task> = {
        id: 'task-1',
        title: 'Server Title',
        goal: 'Server goal',
      }

      const resolution = resolver.resolve(localTask, serverTask)

      expect(resolution.requiresUserDecision).toBe(true)
      expect(resolution.unresolvedConflicts.length).toBeGreaterThan(0)
    })
  })
})
