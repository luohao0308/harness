import * as SQLite from "expo-sqlite";

import type { ConflictStore, OfflineQueue, SyncMetadataStore, TaskStore } from "./store";
import type {
  DesktopConflictInfo,
  SyncOperation,
  Task,
  TaskQueryOptions,
  TaskWithSyncMetadata,
} from "./types";

type Database = SQLite.SQLiteDatabase;

function boolToInt(value: boolean) {
  return value ? 1 : 0;
}

function intToBool(value: number) {
  return value === 1;
}

function nowIso() {
  return new Date().toISOString();
}

function createTaskId() {
  return `mobile-task-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export async function openHarnessMobileDatabase() {
  return SQLite.openDatabaseAsync("harness-mobile.db");
}

export class SQLiteTaskStore implements TaskStore {
  constructor(private readonly db: Database) {}

  async initialize() {
    await this.db.execAsync(`
      PRAGMA journal_mode = WAL;
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
      CREATE INDEX IF NOT EXISTS idx_mobile_tasks_updated_at ON tasks(updated_at);
      CREATE INDEX IF NOT EXISTS idx_mobile_tasks_status ON tasks(status);
      CREATE INDEX IF NOT EXISTS idx_mobile_tasks_agent_id ON tasks(agent_id);
    `);
  }

  async create(task: Omit<Task, "id" | "created_at" | "updated_at"> & { id?: string }) {
    const id = task.id ?? createTaskId();
    const timestamp = nowIso();
    await this.db.runAsync(
      `INSERT INTO tasks (
        id, organization_id, agent_id, created_by, title, goal, status,
        model_provider, model_name, max_runtime_seconds, max_subagents,
        enable_sandbox, enable_network, capability_snapshot_json,
        created_at, updated_at, completed_at, sync_version, last_synced_at,
        server_updated_at, is_local_only, has_local_changes, conflict_detected
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL, 1, 1, 0)`,
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
      boolToInt(task.enable_sandbox),
      boolToInt(task.enable_network),
      JSON.stringify(task.capability_snapshot_json),
      timestamp,
      timestamp,
      task.completed_at,
    );
    const created = await this.get(id);
    if (!created) throw new Error(`Failed to create task ${id}`);
    return created;
  }

  async get(id: string) {
    const row = await this.db.getFirstAsync<RawTaskRow>("SELECT * FROM tasks WHERE id = ?", id);
    return row ? mapTaskRow(row) : null;
  }

  async update(id: string, updates: Partial<Task>) {
    const existing = await this.get(id);
    if (!existing) throw new Error(`Task ${id} not found`);
    const next = { ...existing, ...updates, updated_at: nowIso(), has_local_changes: true };
    await this.db.runAsync(
      `UPDATE tasks SET
        organization_id = ?, agent_id = ?, created_by = ?, title = ?, goal = ?,
        status = ?, model_provider = ?, model_name = ?, max_runtime_seconds = ?,
        max_subagents = ?, enable_sandbox = ?, enable_network = ?,
        capability_snapshot_json = ?, updated_at = ?, completed_at = ?,
        has_local_changes = 1
      WHERE id = ?`,
      next.organization_id,
      next.agent_id,
      next.created_by,
      next.title,
      next.goal,
      next.status,
      next.model_provider,
      next.model_name,
      next.max_runtime_seconds,
      next.max_subagents,
      boolToInt(next.enable_sandbox),
      boolToInt(next.enable_network),
      JSON.stringify(next.capability_snapshot_json),
      next.updated_at,
      next.completed_at,
      id,
    );
    const updated = await this.get(id);
    if (!updated) throw new Error(`Failed to update task ${id}`);
    return updated;
  }

  async delete(id: string) {
    await this.db.runAsync("DELETE FROM tasks WHERE id = ?", id);
  }

  async query(options: TaskQueryOptions = {}) {
    const conditions: string[] = [];
    const values: SQLite.SQLiteBindValue[] = [];
    if (options.status) {
      conditions.push("status = ?");
      values.push(options.status);
    }
    if (options.agent_id) {
      conditions.push("agent_id = ?");
      values.push(options.agent_id);
    }
    if (options.since) {
      conditions.push("updated_at >= ?");
      values.push(options.since);
    }
    values.push(options.limit ?? 100);
    const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";
    const rows = await this.db.getAllAsync<RawTaskRow>(
      `SELECT * FROM tasks ${whereClause} ORDER BY updated_at DESC LIMIT ?`,
      ...values,
    );
    return rows.map(mapTaskRow);
  }

  async upsertFromServer(task: Task, syncVersion: number) {
    const existing = await this.get(task.id);
    if (existing?.has_local_changes) {
      await this.markConflict(task.id, true);
      const conflicted = await this.get(task.id);
      if (!conflicted) throw new Error(`Failed to mark conflict for ${task.id}`);
      return conflicted;
    }
    const timestamp = nowIso();
    await this.db.runAsync(
      `INSERT INTO tasks (
        id, organization_id, agent_id, created_by, title, goal, status,
        model_provider, model_name, max_runtime_seconds, max_subagents,
        enable_sandbox, enable_network, capability_snapshot_json,
        created_at, updated_at, completed_at, sync_version, last_synced_at,
        server_updated_at, is_local_only, has_local_changes, conflict_detected
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0)
      ON CONFLICT(id) DO UPDATE SET
        organization_id = excluded.organization_id,
        agent_id = excluded.agent_id,
        created_by = excluded.created_by,
        title = excluded.title,
        goal = excluded.goal,
        status = excluded.status,
        model_provider = excluded.model_provider,
        model_name = excluded.model_name,
        max_runtime_seconds = excluded.max_runtime_seconds,
        max_subagents = excluded.max_subagents,
        enable_sandbox = excluded.enable_sandbox,
        enable_network = excluded.enable_network,
        capability_snapshot_json = excluded.capability_snapshot_json,
        updated_at = excluded.updated_at,
        completed_at = excluded.completed_at,
        sync_version = excluded.sync_version,
        last_synced_at = excluded.last_synced_at,
        server_updated_at = excluded.server_updated_at,
        is_local_only = 0,
        has_local_changes = 0,
        conflict_detected = 0`,
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
      boolToInt(task.enable_sandbox),
      boolToInt(task.enable_network),
      JSON.stringify(task.capability_snapshot_json),
      task.created_at,
      task.updated_at,
      task.completed_at,
      syncVersion,
      timestamp,
      task.updated_at,
    );
    const updated = await this.get(task.id);
    if (!updated) throw new Error(`Failed to upsert task ${task.id}`);
    return updated;
  }

  async markSynced(id: string, serverUpdatedAt: string, syncVersion: number) {
    await this.db.runAsync(
      `UPDATE tasks
       SET sync_version = ?, last_synced_at = ?, server_updated_at = ?,
           has_local_changes = 0, is_local_only = 0
       WHERE id = ?`,
      syncVersion,
      nowIso(),
      serverUpdatedAt,
      id,
    );
  }

  async markConflict(id: string, hasConflict: boolean) {
    await this.db.runAsync(
      "UPDATE tasks SET conflict_detected = ? WHERE id = ?",
      boolToInt(hasConflict),
      id,
    );
  }
}

export class SQLiteOfflineQueue implements OfflineQueue {
  constructor(private readonly db: Database) {}

  async initialize() {
    await this.db.execAsync(`
      CREATE TABLE IF NOT EXISTS sync_operations (
        id TEXT PRIMARY KEY,
        operation_type TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        client_timestamp TEXT NOT NULL,
        retry_count INTEGER NOT NULL DEFAULT 0,
        last_retry_at TEXT,
        status TEXT NOT NULL DEFAULT 'PENDING',
        error_message TEXT,
        created_at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_mobile_sync_operations_status ON sync_operations(status);
      CREATE INDEX IF NOT EXISTS idx_mobile_sync_operations_created ON sync_operations(created_at);
    `);
  }

  async enqueue(
    operation: Omit<SyncOperation, "id" | "retry_count" | "last_retry_at" | "status" | "error_message" | "created_at">,
  ) {
    const id = `sync-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    await this.db.runAsync(
      `INSERT INTO sync_operations (
        id, operation_type, entity_type, entity_id, payload_json, client_timestamp,
        retry_count, last_retry_at, status, error_message, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, 0, NULL, 'PENDING', NULL, ?)`,
      id,
      operation.operation_type,
      operation.entity_type,
      operation.entity_id,
      operation.payload_json,
      operation.client_timestamp,
      operation.client_timestamp,
    );
    return {
      ...operation,
      id,
      retry_count: 0,
      last_retry_at: null,
      status: "PENDING" as const,
      error_message: null,
      created_at: operation.client_timestamp,
    };
  }

  async getPending() {
    const rows = await this.db.getAllAsync<RawSyncOperationRow>(
      "SELECT * FROM sync_operations WHERE status = 'PENDING' ORDER BY created_at ASC",
    );
    return rows.map(mapSyncOperationRow);
  }

  async markCompleted(id: string) {
    await this.db.runAsync("UPDATE sync_operations SET status = 'COMPLETED' WHERE id = ?", id);
  }

  async markFailed(id: string, errorMessage: string) {
    await this.db.runAsync(
      `UPDATE sync_operations
       SET status = 'FAILED', retry_count = retry_count + 1,
           last_retry_at = ?, error_message = ?
       WHERE id = ?`,
      nowIso(),
      errorMessage,
      id,
    );
  }

  async countPending() {
    const row = await this.db.getFirstAsync<{ total: number }>(
      "SELECT COUNT(*) AS total FROM sync_operations WHERE status = 'PENDING'",
    );
    return row?.total ?? 0;
  }
}

export class SQLiteSyncMetadataStore implements SyncMetadataStore {
  constructor(private readonly db: Database) {}

  async initialize() {
    await this.db.execAsync(`
      CREATE TABLE IF NOT EXISTS sync_metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
    `);
  }

  async getLastSyncTimestamp() {
    const row = await this.db.getFirstAsync<{ value: string }>(
      "SELECT value FROM sync_metadata WHERE key = 'last_sync_timestamp'",
    );
    return row?.value ?? null;
  }

  async setLastSyncTimestamp(timestamp: string) {
    await this.db.runAsync(
      `INSERT INTO sync_metadata (key, value, updated_at)
       VALUES ('last_sync_timestamp', ?, ?)
       ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at`,
      timestamp,
      nowIso(),
    );
  }
}

export class SQLiteConflictStore implements ConflictStore {
  constructor(private readonly db: Database) {}

  async initialize() {
    await this.db.execAsync(`
      CREATE TABLE IF NOT EXISTS sync_conflicts (
        entity_id TEXT PRIMARY KEY,
        entity_type TEXT NOT NULL,
        server_version_json TEXT NOT NULL,
        client_version_json TEXT NOT NULL,
        created_at TEXT NOT NULL
      );
    `);
  }

  async replace(conflicts: DesktopConflictInfo[]) {
    await this.db.execAsync("DELETE FROM sync_conflicts");
    for (const conflict of conflicts) {
      await this.db.runAsync(
        `INSERT INTO sync_conflicts (
          entity_id, entity_type, server_version_json, client_version_json, created_at
        ) VALUES (?, ?, ?, ?, ?)`,
        conflict.entity_id,
        conflict.entity_type,
        JSON.stringify(conflict.server_version),
        JSON.stringify(conflict.client_version),
        nowIso(),
      );
    }
  }

  async list() {
    const rows = await this.db.getAllAsync<RawConflictRow>("SELECT * FROM sync_conflicts");
    return rows.map((row) => ({
      entity_id: row.entity_id,
      entity_type: row.entity_type,
      server_version: JSON.parse(row.server_version_json) as Record<string, unknown>,
      client_version: JSON.parse(row.client_version_json) as Record<string, unknown>,
    }));
  }

  async clear() {
    await this.db.execAsync("DELETE FROM sync_conflicts");
  }
}

function mapTaskRow(row: RawTaskRow): TaskWithSyncMetadata {
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
    enable_sandbox: intToBool(row.enable_sandbox),
    enable_network: intToBool(row.enable_network),
    capability_snapshot_json: JSON.parse(row.capability_snapshot_json) as Record<string, unknown>,
    created_at: row.created_at,
    updated_at: row.updated_at,
    completed_at: row.completed_at,
    sync_version: row.sync_version,
    last_synced_at: row.last_synced_at,
    server_updated_at: row.server_updated_at,
    is_local_only: intToBool(row.is_local_only),
    has_local_changes: intToBool(row.has_local_changes),
    conflict_detected: intToBool(row.conflict_detected),
  };
}

function mapSyncOperationRow(row: RawSyncOperationRow): SyncOperation {
  return {
    id: row.id,
    operation_type: row.operation_type as SyncOperation["operation_type"],
    entity_type: "task",
    entity_id: row.entity_id,
    payload_json: row.payload_json,
    client_timestamp: row.client_timestamp,
    retry_count: row.retry_count,
    last_retry_at: row.last_retry_at,
    status: row.status as SyncOperation["status"],
    error_message: row.error_message,
    created_at: row.created_at,
  };
}

interface RawTaskRow {
  id: string;
  organization_id: string | null;
  agent_id: string | null;
  created_by: string | null;
  title: string;
  goal: string;
  status: string;
  model_provider: string;
  model_name: string;
  max_runtime_seconds: number;
  max_subagents: number;
  enable_sandbox: number;
  enable_network: number;
  capability_snapshot_json: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  sync_version: number;
  last_synced_at: string | null;
  server_updated_at: string | null;
  is_local_only: number;
  has_local_changes: number;
  conflict_detected: number;
}

interface RawSyncOperationRow {
  id: string;
  operation_type: string;
  entity_type: string;
  entity_id: string;
  payload_json: string;
  client_timestamp: string;
  retry_count: number;
  last_retry_at: string | null;
  status: string;
  error_message: string | null;
  created_at: string;
}

interface RawConflictRow {
  entity_id: string;
  entity_type: string;
  server_version_json: string;
  client_version_json: string;
}
