/**
 * SQLiteTaskStore - SQLite implementation of TaskStore interface
 */

import Database from 'better-sqlite3'
import type {
  Task,
  TaskWithSyncMetadata,
  TaskQueryOptions,
  TransactionCallback,
} from './types'
import type { TaskStore } from './task-store'

export class SQLiteTaskStore implements TaskStore {
  private db: Database.Database

  constructor(dbPath: string) {
    this.db = new Database(dbPath)
    this.db.pragma('journal_mode = WAL')
    this.db.pragma('foreign_keys = ON')
  }

  initialize(): void {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        organization_id TEXT,
        agent_id TEXT,
        created_by TEXT,
        title TEXT NOT NULL,
        goal TEXT NOT NULL,
        status TEXT NOT NULL,
        model_provider TEXT NOT NULL,
        model_name TEXT NOT NULL,
        max_runtime_seconds INTEGER NOT NULL,
        max_subagents INTEGER NOT NULL,
        enable_sandbox INTEGER NOT NULL,
        enable_network INTEGER NOT NULL,
        capability_snapshot_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        completed_at TEXT,
        sync_version INTEGER NOT NULL DEFAULT 0,
        last_synced_at TEXT,
        server_updated_at TEXT,
        is_local_only INTEGER NOT NULL DEFAULT 1,
        has_local_changes INTEGER NOT NULL DEFAULT 0,
        conflict_detected INTEGER NOT NULL DEFAULT 0
      );

      CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
      CREATE INDEX IF NOT EXISTS idx_tasks_agent_id ON tasks(agent_id);
      CREATE INDEX IF NOT EXISTS idx_tasks_organization_id ON tasks(organization_id);
      CREATE INDEX IF NOT EXISTS idx_tasks_updated_at ON tasks(updated_at);
      CREATE INDEX IF NOT EXISTS idx_tasks_has_local_changes ON tasks(has_local_changes);
    `)
  }

  create(task: Omit<Task, 'id' | 'created_at' | 'updated_at'>): TaskWithSyncMetadata {
    const id = `task_${Date.now()}_${Math.random().toString(36).substring(2, 15)}`
    const now = new Date().toISOString()

    const stmt = this.db.prepare(`
      INSERT INTO tasks (
        id, organization_id, agent_id, created_by, title, goal, status,
        model_provider, model_name, max_runtime_seconds, max_subagents,
        enable_sandbox, enable_network, capability_snapshot_json,
        created_at, updated_at, completed_at,
        sync_version, last_synced_at, server_updated_at,
        is_local_only, has_local_changes, conflict_detected
      ) VALUES (
        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
      )
    `)

    stmt.run(
      id,
      task.organization_id,
      task.agent_id,
      task.created_by,
      task.title,
      task.goal,
      task.status,
      task.model_provider,
      task.model_name,
      task.max_runtime_seconds,
      task.max_subagents,
      task.enable_sandbox ? 1 : 0,
      task.enable_network ? 1 : 0,
      JSON.stringify(task.capability_snapshot_json),
      now,
      now,
      task.completed_at,
      0,
      null,
      null,
      1,
      1,
      0
    )

    const created = this.get(id)
    if (!created) {
      throw new Error(`Failed to create task ${id}`)
    }

    return created
  }

  get(id: string): TaskWithSyncMetadata | null {
    const stmt = this.db.prepare(`
      SELECT * FROM tasks WHERE id = ?
    `)

    const row = stmt.get(id) as RawTaskRow | undefined

    if (!row) {
      return null
    }

    return this.mapRowToTask(row)
  }

  update(id: string, updates: Partial<Task>): TaskWithSyncMetadata {
    const existing = this.get(id)
    if (!existing) {
      throw new Error(`Task ${id} not found`)
    }

    const now = new Date().toISOString()

    const fields: string[] = []
    const values: unknown[] = []

    if (updates.organization_id !== undefined) {
      fields.push('organization_id = ?')
      values.push(updates.organization_id)
    }
    if (updates.agent_id !== undefined) {
      fields.push('agent_id = ?')
      values.push(updates.agent_id)
    }
    if (updates.created_by !== undefined) {
      fields.push('created_by = ?')
      values.push(updates.created_by)
    }
    if (updates.title !== undefined) {
      fields.push('title = ?')
      values.push(updates.title)
    }
    if (updates.goal !== undefined) {
      fields.push('goal = ?')
      values.push(updates.goal)
    }
    if (updates.status !== undefined) {
      fields.push('status = ?')
      values.push(updates.status)
    }
    if (updates.model_provider !== undefined) {
      fields.push('model_provider = ?')
      values.push(updates.model_provider)
    }
    if (updates.model_name !== undefined) {
      fields.push('model_name = ?')
      values.push(updates.model_name)
    }
    if (updates.max_runtime_seconds !== undefined) {
      fields.push('max_runtime_seconds = ?')
      values.push(updates.max_runtime_seconds)
    }
    if (updates.max_subagents !== undefined) {
      fields.push('max_subagents = ?')
      values.push(updates.max_subagents)
    }
    if (updates.enable_sandbox !== undefined) {
      fields.push('enable_sandbox = ?')
      values.push(updates.enable_sandbox ? 1 : 0)
    }
    if (updates.enable_network !== undefined) {
      fields.push('enable_network = ?')
      values.push(updates.enable_network ? 1 : 0)
    }
    if (updates.capability_snapshot_json !== undefined) {
      fields.push('capability_snapshot_json = ?')
      values.push(JSON.stringify(updates.capability_snapshot_json))
    }
    if (updates.completed_at !== undefined) {
      fields.push('completed_at = ?')
      values.push(updates.completed_at)
    }

    fields.push('updated_at = ?')
    values.push(now)
    fields.push('has_local_changes = ?')
    values.push(1)

    values.push(id)

    const stmt = this.db.prepare(`
      UPDATE tasks SET ${fields.join(', ')} WHERE id = ?
    `)

    stmt.run(...values)

    const updated = this.get(id)
    if (!updated) {
      throw new Error(`Failed to update task ${id}`)
    }

    return updated
  }

  delete(id: string): void {
    const stmt = this.db.prepare(`
      DELETE FROM tasks WHERE id = ?
    `)

    stmt.run(id)
  }

  query(options: TaskQueryOptions = {}): TaskWithSyncMetadata[] {
    const conditions: string[] = []
    const values: unknown[] = []

    if (options.status !== undefined) {
      conditions.push('status = ?')
      values.push(options.status)
    }

    if (options.agent_id !== undefined) {
      conditions.push('agent_id = ?')
      values.push(options.agent_id)
    }

    if (options.organization_id !== undefined) {
      conditions.push('organization_id = ?')
      values.push(options.organization_id)
    }

    if (options.since !== undefined) {
      conditions.push('updated_at >= ?')
      values.push(options.since)
    }

    if (options.has_local_changes !== undefined) {
      conditions.push('has_local_changes = ?')
      values.push(options.has_local_changes ? 1 : 0)
    }

    const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : ''

    const limit = options.limit ?? 100
    const offset = options.offset ?? 0

    const sql = `
      SELECT * FROM tasks
      ${whereClause}
      ORDER BY updated_at DESC
      LIMIT ? OFFSET ?
    `

    values.push(limit, offset)

    const stmt = this.db.prepare(sql)
    const rows = stmt.all(...values) as RawTaskRow[]

    return rows.map(row => this.mapRowToTask(row))
  }

  getPendingSync(): TaskWithSyncMetadata[] {
    const stmt = this.db.prepare(`
      SELECT * FROM tasks WHERE has_local_changes = 1
      ORDER BY updated_at ASC
    `)

    const rows = stmt.all() as RawTaskRow[]
    return rows.map(row => this.mapRowToTask(row))
  }

  markSynced(id: string, serverUpdatedAt: string, syncVersion: number): void {
    const stmt = this.db.prepare(`
      UPDATE tasks
      SET sync_version = ?,
          last_synced_at = ?,
          server_updated_at = ?,
          has_local_changes = 0,
          is_local_only = 0
      WHERE id = ?
    `)

    const now = new Date().toISOString()
    stmt.run(syncVersion, now, serverUpdatedAt, id)
  }

  markLocalChange(id: string): void {
    const stmt = this.db.prepare(`
      UPDATE tasks SET has_local_changes = 1 WHERE id = ?
    `)

    stmt.run(id)
  }

  markConflict(id: string, hasConflict: boolean): void {
    const stmt = this.db.prepare(`
      UPDATE tasks SET conflict_detected = ? WHERE id = ?
    `)

    stmt.run(hasConflict ? 1 : 0, id)
  }

  upsertFromServer(task: Task, syncVersion: number): TaskWithSyncMetadata {
    const existing = this.get(task.id)

    if (!existing) {
      const stmt = this.db.prepare(`
        INSERT INTO tasks (
          id, organization_id, agent_id, created_by, title, goal, status,
          model_provider, model_name, max_runtime_seconds, max_subagents,
          enable_sandbox, enable_network, capability_snapshot_json,
          created_at, updated_at, completed_at,
          sync_version, last_synced_at, server_updated_at,
          is_local_only, has_local_changes, conflict_detected
        ) VALUES (
          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
      `)

      const now = new Date().toISOString()

      stmt.run(
        task.id,
        task.organization_id,
        task.agent_id,
        task.created_by,
        task.title,
        task.goal,
        task.status,
        task.model_provider,
        task.model_name,
        task.max_runtime_seconds,
        task.max_subagents,
        task.enable_sandbox ? 1 : 0,
        task.enable_network ? 1 : 0,
        JSON.stringify(task.capability_snapshot_json),
        task.created_at,
        task.updated_at,
        task.completed_at,
        syncVersion,
        now,
        task.updated_at,
        0,
        0,
        0
      )

      const created = this.get(task.id)
      if (!created) {
        throw new Error(`Failed to upsert task ${task.id}`)
      }

      return created
    }

    if (existing.has_local_changes) {
      this.markConflict(task.id, true)

      const conflicted = this.get(task.id)
      if (!conflicted) {
        throw new Error(`Failed to mark conflict for task ${task.id}`)
      }

      return conflicted
    }

    const stmt = this.db.prepare(`
      UPDATE tasks
      SET organization_id = ?,
          agent_id = ?,
          created_by = ?,
          title = ?,
          goal = ?,
          status = ?,
          model_provider = ?,
          model_name = ?,
          max_runtime_seconds = ?,
          max_subagents = ?,
          enable_sandbox = ?,
          enable_network = ?,
          capability_snapshot_json = ?,
          updated_at = ?,
          completed_at = ?,
          sync_version = ?,
          last_synced_at = ?,
          server_updated_at = ?,
          is_local_only = 0,
          has_local_changes = 0,
          conflict_detected = 0
      WHERE id = ?
    `)

    const now = new Date().toISOString()

    stmt.run(
      task.organization_id,
      task.agent_id,
      task.created_by,
      task.title,
      task.goal,
      task.status,
      task.model_provider,
      task.model_name,
      task.max_runtime_seconds,
      task.max_subagents,
      task.enable_sandbox ? 1 : 0,
      task.enable_network ? 1 : 0,
      JSON.stringify(task.capability_snapshot_json),
      task.updated_at,
      task.completed_at,
      syncVersion,
      now,
      task.updated_at,
      task.id
    )

    const updated = this.get(task.id)
    if (!updated) {
      throw new Error(`Failed to upsert task ${task.id}`)
    }

    return updated
  }

  transaction<T>(callback: TransactionCallback<T>): T {
    const txn = this.db.transaction(() => {
      return callback(this.db)
    })

    return txn()
  }

  close(): void {
    this.db.close()
  }

  private mapRowToTask(row: RawTaskRow): TaskWithSyncMetadata {
    return {
      id: row.id,
      organization_id: row.organization_id,
      agent_id: row.agent_id,
      created_by: row.created_by,
      title: row.title,
      goal: row.goal,
      status: row.status,
      model_provider: row.model_provider,
      model_name: row.model_name,
      max_runtime_seconds: row.max_runtime_seconds,
      max_subagents: row.max_subagents,
      enable_sandbox: row.enable_sandbox === 1,
      enable_network: row.enable_network === 1,
      capability_snapshot_json: JSON.parse(row.capability_snapshot_json),
      created_at: row.created_at,
      updated_at: row.updated_at,
      completed_at: row.completed_at,
      sync_version: row.sync_version,
      last_synced_at: row.last_synced_at,
      server_updated_at: row.server_updated_at,
      is_local_only: row.is_local_only === 1,
      has_local_changes: row.has_local_changes === 1,
      conflict_detected: row.conflict_detected === 1,
    }
  }
}

interface RawTaskRow {
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
  enable_sandbox: number
  enable_network: number
  capability_snapshot_json: string
  created_at: string
  updated_at: string
  completed_at: string | null
  sync_version: number
  last_synced_at: string | null
  server_updated_at: string | null
  is_local_only: number
  has_local_changes: number
  conflict_detected: number
}
