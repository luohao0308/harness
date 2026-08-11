import type { ConflictStore, OfflineQueue, SyncMetadataStore, TaskStore } from "./store";
import type {
  DesktopConflictInfo,
  SyncOperation,
  Task,
  TaskQueryOptions,
  TaskWithSyncMetadata,
} from "./types";

function nowIso() {
  return new Date().toISOString();
}

function createTaskId() {
  return `mobile-task-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export class MemoryTaskStore implements TaskStore {
  private tasks = new Map<string, TaskWithSyncMetadata>();

  async initialize() {
    return undefined;
  }

  async create(task: Omit<Task, "id" | "created_at" | "updated_at"> & { id?: string }) {
    const timestamp = nowIso();
    const created: TaskWithSyncMetadata = {
      ...task,
      id: task.id ?? createTaskId(),
      created_at: timestamp,
      updated_at: timestamp,
      sync_version: 0,
      last_synced_at: null,
      server_updated_at: null,
      is_local_only: true,
      has_local_changes: true,
      conflict_detected: false,
    };
    this.tasks.set(created.id, created);
    return created;
  }

  async get(id: string) {
    return this.tasks.get(id) ?? null;
  }

  async update(id: string, updates: Partial<Task>) {
    const existing = this.tasks.get(id);
    if (!existing) throw new Error(`Task ${id} not found`);
    const updated = {
      ...existing,
      ...updates,
      updated_at: nowIso(),
      has_local_changes: true,
    };
    this.tasks.set(id, updated);
    return updated;
  }

  async delete(id: string) {
    this.tasks.delete(id);
  }

  async query(options: TaskQueryOptions = {}) {
    let rows = [...this.tasks.values()];
    if (options.status) rows = rows.filter((task) => task.status === options.status);
    if (options.agent_id) rows = rows.filter((task) => task.agent_id === options.agent_id);
    if (options.since) rows = rows.filter((task) => task.updated_at >= options.since!);
    rows.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    return rows.slice(0, options.limit ?? 100);
  }

  async upsertFromServer(task: Task, syncVersion: number) {
    const existing = this.tasks.get(task.id);
    if (existing?.has_local_changes) {
      const conflicted = { ...existing, conflict_detected: true };
      this.tasks.set(task.id, conflicted);
      return conflicted;
    }

    const now = nowIso();
    const merged: TaskWithSyncMetadata = {
      ...task,
      sync_version: syncVersion,
      last_synced_at: now,
      server_updated_at: task.updated_at,
      is_local_only: false,
      has_local_changes: false,
      conflict_detected: false,
    };
    this.tasks.set(task.id, merged);
    return merged;
  }

  async markSynced(id: string, serverUpdatedAt: string, syncVersion: number) {
    const existing = this.tasks.get(id);
    if (!existing) return;
    this.tasks.set(id, {
      ...existing,
      sync_version: syncVersion,
      last_synced_at: nowIso(),
      server_updated_at: serverUpdatedAt,
      has_local_changes: false,
      is_local_only: false,
    });
  }

  async markConflict(id: string, hasConflict: boolean) {
    const existing = this.tasks.get(id);
    if (!existing) return;
    this.tasks.set(id, { ...existing, conflict_detected: hasConflict });
  }
}

export class MemoryOfflineQueue implements OfflineQueue {
  private operations = new Map<string, SyncOperation>();

  async initialize() {
    return undefined;
  }

  async enqueue(
    operation: Omit<SyncOperation, "id" | "retry_count" | "last_retry_at" | "status" | "error_message" | "created_at">,
  ) {
    const id = `${this.operations.size + 1}`;
    const created: SyncOperation = {
      ...operation,
      id,
      retry_count: 0,
      last_retry_at: null,
      status: "PENDING",
      error_message: null,
      created_at: operation.client_timestamp,
    };
    this.operations.set(id, created);
    return created;
  }

  async getPending() {
    return [...this.operations.values()]
      .filter((operation) => operation.status === "PENDING")
      .sort((a, b) => a.created_at.localeCompare(b.created_at));
  }

  async markCompleted(id: string) {
    const operation = this.operations.get(id);
    if (operation) this.operations.set(id, { ...operation, status: "COMPLETED" });
  }

  async markFailed(id: string, errorMessage: string) {
    const operation = this.operations.get(id);
    if (!operation) return;
    this.operations.set(id, {
      ...operation,
      status: "FAILED",
      retry_count: operation.retry_count + 1,
      last_retry_at: nowIso(),
      error_message: errorMessage,
    });
  }

  async countPending() {
    return (await this.getPending()).length;
  }
}

export class MemorySyncMetadataStore implements SyncMetadataStore {
  private lastSyncTimestamp: string | null = null;

  async initialize() {
    return undefined;
  }

  async getLastSyncTimestamp() {
    return this.lastSyncTimestamp;
  }

  async setLastSyncTimestamp(timestamp: string) {
    this.lastSyncTimestamp = timestamp;
  }
}

export class MemoryConflictStore implements ConflictStore {
  private conflicts: DesktopConflictInfo[] = [];

  async initialize() {
    return undefined;
  }

  async replace(conflicts: DesktopConflictInfo[]) {
    this.conflicts = conflicts;
  }

  async list() {
    return this.conflicts;
  }

  async clear() {
    this.conflicts = [];
  }
}
