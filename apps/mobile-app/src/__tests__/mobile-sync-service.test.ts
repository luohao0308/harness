import { describe, expect, it, vi } from "vitest";

import { MobileSyncService, toDesktopOperation } from "../sync/mobile-sync-service";
import {
  MemoryConflictStore,
  MemoryOfflineQueue,
  MemorySyncMetadataStore,
  MemoryTaskStore,
} from "../sync/memory-store";
import type {
  DesktopSyncOperation,
  DesktopSyncOperationsResponse,
  DesktopSyncResponse,
  SyncOperation,
} from "../sync/types";

class FakeApi {
  syncResponse: DesktopSyncResponse = {
    tasks: [],
    server_timestamp: "2026-06-27T00:00:00Z",
  };
  operationsResponse: DesktopSyncOperationsResponse = {
    applied: 0,
    conflicts: [],
  };
  pushedOperations: DesktopSyncOperation[][] = [];
  fetchDesktopSync = vi.fn(async () => this.syncResponse);
  pushDesktopOperations = vi.fn(async (operations: DesktopSyncOperation[]) => {
    this.pushedOperations.push(operations);
    return this.operationsResponse;
  });
}

function createHarness() {
  const api = new FakeApi();
  const taskStore = new MemoryTaskStore();
  const queue = new MemoryOfflineQueue();
  const metadata = new MemorySyncMetadataStore();
  const conflicts = new MemoryConflictStore();
  const service = new MobileSyncService(api as never, taskStore, queue, metadata, conflicts);
  return { api, taskStore, queue, metadata, conflicts, service };
}

describe("MobileSyncService", () => {
  it("fetches server tasks through the desktop sync endpoint shape", async () => {
    const { api, service } = createHarness();
    await service.initialize();
    api.syncResponse = {
      server_timestamp: "2026-06-27T01:00:00Z",
      tasks: [
        {
          id: "task-1",
          title: "Review run",
          goal: "Check failure",
          status: "RUNNING",
          created_at: "2026-06-27T00:00:00Z",
          updated_at: "2026-06-27T00:30:00Z",
          completed_at: null,
          model_provider: "deepseek",
          model_name: "deepseek-chat",
        },
      ],
    };

    const snapshot = await service.sync();

    expect(api.fetchDesktopSync).toHaveBeenCalledWith(null);
    expect(snapshot.tasks).toHaveLength(1);
    expect(snapshot.tasks[0]?.title).toBe("Review run");
    expect(snapshot.lastSyncAt).toBe("2026-06-27T01:00:00Z");
    expect(snapshot.offline).toBe(false);
  });

  it("queues local task creation and pushes it as desktop sync operation", async () => {
    const { api, service } = createHarness();
    await service.initialize();
    await service.createLocalTask({ title: "Offline task", goal: "Keep working" });
    api.operationsResponse = { applied: 1, conflicts: [] };

    const snapshot = await service.sync();

    expect(api.pushDesktopOperations).toHaveBeenCalledTimes(1);
    const pushed = api.pushedOperations[0];
    expect(pushed?.[0]?.type).toBe("create");
    expect(pushed?.[0]?.data?.title).toBe("Offline task");
    expect(snapshot.pendingOperations).toBe(0);
  });

  it("keeps conflict evidence when backend rejects an operation", async () => {
    const { api, service } = createHarness();
    await service.initialize();
    const task = await service.createLocalTask({ title: "Conflicting task", goal: "Edit while remote changed" });
    api.operationsResponse = {
      applied: 0,
      conflicts: [
        {
          entity_id: task.id,
          entity_type: "task",
          server_version: { title: "Remote" },
          client_version: { title: "Local" },
        },
      ],
    };

    const snapshot = await service.sync();

    expect(snapshot.conflicts).toHaveLength(1);
    expect(snapshot.tasks[0]?.conflict_detected).toBe(true);
  });

  it("marks snapshot offline when sync request fails", async () => {
    const { api, service } = createHarness();
    await service.initialize();
    api.fetchDesktopSync.mockRejectedValueOnce(new Error("network down"));

    const snapshot = await service.sync();

    expect(snapshot.offline).toBe(true);
    expect(snapshot.tasks).toEqual([]);
  });
});

describe("toDesktopOperation", () => {
  it("maps uppercase desktop queue operations to backend payloads", () => {
    const operation: SyncOperation = {
      id: "1",
      operation_type: "UPDATE",
      entity_type: "task",
      entity_id: "task-1",
      payload_json: JSON.stringify({ title: "Updated" }),
      client_timestamp: "2026-06-27T00:00:00Z",
      retry_count: 0,
      last_retry_at: null,
      status: "PENDING",
      error_message: null,
      created_at: "2026-06-27T00:00:00Z",
    };

    expect(toDesktopOperation(operation)).toEqual({
      type: "update",
      entity_type: "task",
      entity_id: "task-1",
      data: { title: "Updated" },
      timestamp: "2026-06-27T00:00:00Z",
    });
  });
});
