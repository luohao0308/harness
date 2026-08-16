import { MobileApiClient } from "./api-client";
import type { ConflictStore, OfflineQueue, SyncMetadataStore, TaskStore } from "./store";
import type {
  DesktopSyncOperation,
  SyncOperation,
  SyncSnapshot,
  Task,
} from "./types";
import { normalizeDesktopTask } from "./types";

export class MobileSyncService {
  constructor(
    private readonly api: MobileApiClient,
    private readonly taskStore: TaskStore,
    private readonly offlineQueue: OfflineQueue,
    private readonly metadataStore: SyncMetadataStore,
    private readonly conflictStore: ConflictStore,
  ) {}

  async initialize() {
    await Promise.all([
      this.taskStore.initialize(),
      this.offlineQueue.initialize(),
      this.metadataStore.initialize(),
      this.conflictStore.initialize(),
    ]);
  }

  async snapshot(offline = false): Promise<SyncSnapshot> {
    const [tasks, pendingOperations, conflicts, lastSyncAt] = await Promise.all([
      this.taskStore.query({ limit: 100 }),
      this.offlineQueue.countPending(),
      this.conflictStore.list(),
      this.metadataStore.getLastSyncTimestamp(),
    ]);
    return { tasks, pendingOperations, conflicts, lastSyncAt, offline };
  }

  async createLocalTask(
    input: Pick<Task, "title" | "goal"> &
      Partial<Pick<Task, "agent_id" | "model_provider" | "model_name" | "enable_network" | "enable_sandbox">>,
  ) {
    const task = await this.taskStore.create({
      organization_id: null,
      agent_id: input.agent_id ?? null,
      created_by: null,
      title: input.title,
      goal: input.goal,
      status: "pending",
      model_provider: input.model_provider ?? "anthropic",
      model_name: input.model_name ?? "claude-opus-4",
      max_runtime_seconds: 3600,
      max_subagents: 2,
      enable_sandbox: input.enable_sandbox ?? true,
      enable_network: input.enable_network ?? false,
      capability_snapshot_json: {},
      completed_at: null,
    });
    await this.enqueueTaskOperation("CREATE", task.id, task);
    return task;
  }

  async updateLocalTask(id: string, updates: Partial<Task>) {
    const task = await this.taskStore.update(id, updates);
    await this.enqueueTaskOperation("UPDATE", id, updates);
    return task;
  }

  async deleteLocalTask(id: string) {
    await this.taskStore.delete(id);
    await this.enqueueTaskOperation("DELETE", id, null);
  }

  async sync(): Promise<SyncSnapshot> {
    let offline = false;
    try {
      const lastSyncTimestamp = await this.metadataStore.getLastSyncTimestamp();
      const delta = await this.api.fetchDesktopSync(lastSyncTimestamp);
      for (const task of delta.tasks) {
        await this.taskStore.upsertFromServer(normalizeDesktopTask(task), 1);
      }

      const pending = await this.offlineQueue.getPending();
      if (pending.length > 0) {
        const response = await this.api.pushDesktopOperations(pending.map(toDesktopOperation));
        await this.conflictStore.replace(response.conflicts);
        const conflictIds = new Set(response.conflicts.map((conflict) => conflict.entity_id));
        for (const operation of pending) {
          if (conflictIds.has(operation.entity_id)) {
            await this.offlineQueue.markFailed(operation.id, "Sync conflict");
            await this.taskStore.markConflict(operation.entity_id, true);
          } else {
            await this.offlineQueue.markCompleted(operation.id);
          }
        }
      } else {
        await this.conflictStore.clear();
      }

      await this.metadataStore.setLastSyncTimestamp(delta.server_timestamp);
    } catch (error) {
      offline = true;
      const message = error instanceof Error ? error.message : String(error);
      for (const operation of await this.offlineQueue.getPending()) {
        await this.offlineQueue.markFailed(operation.id, message);
      }
    }
    return this.snapshot(offline);
  }

  private async enqueueTaskOperation(
    type: SyncOperation["operation_type"],
    entityId: string,
    payload: Partial<Task> | null,
  ) {
    const timestamp = new Date().toISOString();
    await this.offlineQueue.enqueue({
      operation_type: type,
      entity_type: "task",
      entity_id: entityId,
      payload_json: JSON.stringify(payload),
      client_timestamp: timestamp,
    });
  }
}

export function toDesktopOperation(operation: SyncOperation): DesktopSyncOperation {
  const typeMap = {
    CREATE: "create",
    UPDATE: "update",
    DELETE: "delete",
  } as const;

  return {
    type: typeMap[operation.operation_type],
    entity_type: "task",
    entity_id: operation.entity_id,
    data: operation.payload_json ? (JSON.parse(operation.payload_json) as Record<string, unknown>) : null,
    timestamp: operation.client_timestamp,
  };
}
