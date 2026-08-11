import NetInfo from "@react-native-community/netinfo";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { createMobileSyncService } from "../sync/create-mobile-sync";
import type { MobileSyncService } from "../sync/mobile-sync-service";
import type { SyncSnapshot, TaskWithSyncMetadata } from "../sync/types";

type TaskForm = {
  title: string;
  goal: string;
};

const EMPTY_SNAPSHOT: SyncSnapshot = {
  tasks: [],
  pendingOperations: 0,
  conflicts: [],
  lastSyncAt: null,
  offline: false,
};

export function useMobileTasks() {
  const serviceRef = useRef<MobileSyncService | null>(null);
  const [snapshot, setSnapshot] = useState<SyncSnapshot>(EMPTY_SNAPSHOT);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(true);

  useEffect(() => {
    const unsubscribe = NetInfo.addEventListener((state) => {
      setIsConnected(state.isConnected !== false && state.isInternetReachable !== false);
    });
    return unsubscribe;
  }, []);

  useEffect(() => {
    let mounted = true;
    createMobileSyncService()
      .then(async (service) => {
        serviceRef.current = service;
        const next = await service.sync();
        if (mounted) setSnapshot(next);
      })
      .catch((initializationError: unknown) => {
        if (mounted) {
          setError(errorMessage(initializationError));
        }
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    const service = serviceRef.current;
    if (!service) return;
    setRefreshing(true);
    setError(null);
    try {
      const next = await service.sync();
      setSnapshot({ ...next, offline: next.offline || !isConnected });
    } catch (refreshError: unknown) {
      setError(errorMessage(refreshError));
      setSnapshot(await service.snapshot(true));
    } finally {
      setRefreshing(false);
    }
  }, [isConnected]);

  const createTask = useCallback(async (form: TaskForm) => {
    const service = serviceRef.current;
    if (!service) return;
    setError(null);
    try {
      await service.createLocalTask({
        title: form.title.trim(),
        goal: form.goal.trim(),
      });
      setSnapshot(await service.snapshot(!isConnected));
    } catch (createError: unknown) {
      setError(errorMessage(createError));
    }
  }, [isConnected]);

  const markCompleted = useCallback(async (task: TaskWithSyncMetadata) => {
    const service = serviceRef.current;
    if (!service) return;
    setError(null);
    try {
      await service.updateLocalTask(task.id, {
        status: "completed",
        completed_at: new Date().toISOString(),
      });
      setSnapshot(await service.snapshot(!isConnected));
    } catch (updateError: unknown) {
      setError(errorMessage(updateError));
    }
  }, [isConnected]);

  const sortedTasks = useMemo(() => {
    return [...snapshot.tasks].sort((a, b) => {
      if (a.conflict_detected !== b.conflict_detected) {
        return a.conflict_detected ? -1 : 1;
      }
      if (a.has_local_changes !== b.has_local_changes) {
        return a.has_local_changes ? -1 : 1;
      }
      return b.updated_at.localeCompare(a.updated_at);
    });
  }, [snapshot.tasks]);

  return {
    tasks: sortedTasks,
    loading,
    refreshing,
    refresh,
    createTask,
    markCompleted,
    error,
    syncState: {
      offline: snapshot.offline || !isConnected,
      pendingOperations: snapshot.pendingOperations,
      conflicts: snapshot.conflicts.length,
      lastSyncAt: snapshot.lastSyncAt,
    },
  };
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}
