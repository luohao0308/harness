import type {
  DesktopConflictInfo,
  SyncOperation,
  Task,
  TaskQueryOptions,
  TaskWithSyncMetadata,
} from "./types";

export interface TaskStore {
  initialize(): Promise<void>;
  create(task: Omit<Task, "id" | "created_at" | "updated_at"> & { id?: string }): Promise<TaskWithSyncMetadata>;
  get(id: string): Promise<TaskWithSyncMetadata | null>;
  update(id: string, updates: Partial<Task>): Promise<TaskWithSyncMetadata>;
  delete(id: string): Promise<void>;
  query(options?: TaskQueryOptions): Promise<TaskWithSyncMetadata[]>;
  upsertFromServer(task: Task, syncVersion: number): Promise<TaskWithSyncMetadata>;
  markSynced(id: string, serverUpdatedAt: string, syncVersion: number): Promise<void>;
  markConflict(id: string, hasConflict: boolean): Promise<void>;
}

export interface OfflineQueue {
  initialize(): Promise<void>;
  enqueue(operation: Omit<SyncOperation, "id" | "retry_count" | "last_retry_at" | "status" | "error_message" | "created_at">): Promise<SyncOperation>;
  getPending(): Promise<SyncOperation[]>;
  markCompleted(id: string): Promise<void>;
  markFailed(id: string, errorMessage: string): Promise<void>;
  countPending(): Promise<number>;
}

export interface SyncMetadataStore {
  initialize(): Promise<void>;
  getLastSyncTimestamp(): Promise<string | null>;
  setLastSyncTimestamp(timestamp: string): Promise<void>;
}

export interface ConflictStore {
  initialize(): Promise<void>;
  replace(conflicts: DesktopConflictInfo[]): Promise<void>;
  list(): Promise<DesktopConflictInfo[]>;
  clear(): Promise<void>;
}
