/**
 * SQLiteConflictResolver - Implementation of ConflictResolver interface
 */

import type { Task } from '../stores/types'
import type { ConflictResolver, FieldConflict, ConflictResolution } from './conflict-resolver'

const METADATA_FIELDS = new Set(['id', 'created_at', 'updated_at'])
const STATUS_PRIORITY: Record<string, number> = {
  completed: 3,
  in_progress: 2,
  pending: 1,
}

export class SQLiteConflictResolver implements ConflictResolver {
  detectConflicts(local: Partial<Task>, server: Partial<Task>): FieldConflict[] {
    const conflicts: FieldConflict[] = []
    const allFields = new Set([...Object.keys(local), ...Object.keys(server)])

    for (const field of allFields) {
      // Skip metadata fields
      if (METADATA_FIELDS.has(field)) {
        continue
      }

      const localValue = local[field as keyof Task]
      const serverValue = server[field as keyof Task]

      // No conflict if values are identical
      if (localValue === serverValue) {
        continue
      }

      // Only include if field exists in both and values differ
      if (localValue !== undefined && serverValue !== undefined) {
        conflicts.push({
          field,
          localValue,
          serverValue,
          canAutoMerge: this.canAutoMerge(field, localValue, serverValue, local, server),
        })
      }
    }

    return conflicts
  }

  autoMerge(
    local: Partial<Task>,
    server: Partial<Task>,
    conflicts: FieldConflict[]
  ): ConflictResolution {
    const merged: Partial<Task> = { ...local }
    const unresolvedConflicts: FieldConflict[] = []

    // Merge non-conflicting fields from server
    for (const key of Object.keys(server)) {
      const field = key as keyof Task
      if (!conflicts.some(c => c.field === field) && !METADATA_FIELDS.has(field)) {
        merged[field] = server[field]
      }
    }

    // Process conflicts
    for (const conflict of conflicts) {
      if (conflict.canAutoMerge) {
        // Auto-merge based on field type
        if (conflict.field === 'status') {
          // Status priority: in_progress > pending > completed
          const localPriority = STATUS_PRIORITY[conflict.localValue] || 0
          const serverPriority = STATUS_PRIORITY[conflict.serverValue] || 0
          merged[conflict.field as keyof Task] = localPriority >= serverPriority
            ? conflict.localValue
            : conflict.serverValue
        } else {
          // Last-write-wins for timestamp-based conflicts
          const localTimestamp = local.updated_at ? new Date(local.updated_at).getTime() : 0
          const serverTimestamp = server.updated_at ? new Date(server.updated_at).getTime() : 0
          merged[conflict.field as keyof Task] = localTimestamp >= serverTimestamp
            ? conflict.localValue
            : conflict.serverValue
        }
      } else {
        // Cannot auto-merge, require user decision
        unresolvedConflicts.push(conflict)
      }
    }

    return {
      merged,
      requiresUserDecision: unresolvedConflicts.length > 0,
      unresolvedConflicts,
    }
  }

  applyUserResolution(
    merged: Partial<Task>,
    conflicts: FieldConflict[],
    userChoices: Record<string, 'local' | 'server'>
  ): Partial<Task> {
    // Validate user choices are complete
    for (const conflict of conflicts) {
      if (!userChoices[conflict.field]) {
        throw new Error(`Missing user choice for field: ${conflict.field}`)
      }
    }

    // Apply user choices
    const result = { ...merged }
    for (const conflict of conflicts) {
      const choice = userChoices[conflict.field]
      result[conflict.field as keyof Task] = choice === 'local'
        ? conflict.localValue
        : conflict.serverValue
    }

    return result
  }

  resolve(local: Partial<Task>, server: Partial<Task>): ConflictResolution {
    const conflicts = this.detectConflicts(local, server)
    return this.autoMerge(local, server, conflicts)
  }

  private canAutoMerge(
    field: string,
    localValue: any,
    serverValue: any,
    local: Partial<Task>,
    server: Partial<Task>
  ): boolean {
    // Status conflicts can be auto-merged based on priority
    if (field === 'status') {
      return true
    }

    // If we have timestamps, we can use last-write-wins
    if (local.updated_at && server.updated_at) {
      return true
    }

    // Text fields with different values require user decision
    return false
  }
}
