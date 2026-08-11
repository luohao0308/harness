/**
 * ConflictResolver - Interface for field-level conflict resolution
 */

import type { Task } from '../stores/types'

export interface FieldConflict {
  field: string
  localValue: any
  serverValue: any
  canAutoMerge: boolean
}

export interface ConflictResolution {
  merged: Partial<Task>
  requiresUserDecision: boolean
  unresolvedConflicts: FieldConflict[]
}

export interface ConflictResolver {
  /**
   * Detect conflicts between local and server versions
   */
  detectConflicts(local: Partial<Task>, server: Partial<Task>): FieldConflict[]

  /**
   * Automatically merge non-conflicting fields
   */
  autoMerge(
    local: Partial<Task>,
    server: Partial<Task>,
    conflicts: FieldConflict[]
  ): ConflictResolution

  /**
   * Apply user choices to resolve conflicts
   */
  applyUserResolution(
    merged: Partial<Task>,
    conflicts: FieldConflict[],
    userChoices: Record<string, 'local' | 'server'>
  ): Partial<Task>

  /**
   * Resolve conflicts (detect, auto-merge, return resolution)
   */
  resolve(local: Partial<Task>, server: Partial<Task>): ConflictResolution
}
