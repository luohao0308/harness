/**
 * Task Management React Adapter (Phase 1.2 - REFACTOR Phase)
 *
 * This adapter bridges agent-console components (HTTP-based) with desktop-app IPC layer.
 * It replaces HTTP calls with window.desktopApi.* IPC calls while maintaining the same
 * interface as the web version.
 *
 * Key features:
 * - Task list fetching via IPC
 * - Task status polling with exponential backoff
 * - Task result caching to reduce IPC overhead
 * - Task cancellation operations
 * - Workspace data fetching
 * - Event-based status updates
 *
 * Refactoring improvements:
 * - Exponential backoff for polling (reduces load on long-running tasks)
 * - Task result caching (avoids redundant IPC calls)
 * - Shared polling logic extraction
 */

import type {
  Task,
  TaskStatus,
  AgentRunWorkspace,
  DesktopApi,
} from '../../preload-api'
import { globalTaskQueue } from './task-queue'

// Access window.desktopApi (exposed by preload.ts via contextBridge)
const api: DesktopApi = (window as any).desktopApi

/**
 * Simple in-memory cache for task results
 * Reduces redundant IPC calls for frequently accessed tasks
 */
class TaskCache {
  private cache = new Map<string, { task: Task; timestamp: number }>()
  private readonly ttlMs: number

  constructor(ttlMs: number = 5000) {
    this.ttlMs = ttlMs
  }

  get(taskId: string): Task | null {
    const entry = this.cache.get(taskId)
    if (!entry) return null

    const isExpired = Date.now() - entry.timestamp > this.ttlMs
    if (isExpired) {
      this.cache.delete(taskId)
      return null
    }

    return entry.task
  }

  set(taskId: string, task: Task): void {
    this.cache.set(taskId, { task, timestamp: Date.now() })
  }

  invalidate(taskId: string): void {
    this.cache.delete(taskId)
  }

  clear(): void {
    this.cache.clear()
  }
}

const taskCache = new TaskCache()

/**
 * Fetch all tasks or filter by status
 * Uses task queue to prevent overwhelming the main process
 */
export async function listTasks(filters?: {
  status?: TaskStatus
}): Promise<{ items: Task[] }> {
  return globalTaskQueue.enqueue(() => api.task.list(filters), { priority: 'NORMAL' })
}

/**
 * Fetch a single task by ID with caching
 * Uses task queue for high-priority operations (user-initiated)
 */
export async function getTask(
  taskId: string,
  options: { useCache?: boolean; priority?: 'HIGH' | 'NORMAL' | 'LOW' } = {}
): Promise<Task> {
  const { useCache = true, priority = 'NORMAL' } = options

  // Check cache first
  if (useCache) {
    const cached = taskCache.get(taskId)
    if (cached) {
      return cached
    }
  }

  // Fetch from IPC via queue and cache result
  const task = await globalTaskQueue.enqueue(() => api.task.get(taskId), { priority })
  taskCache.set(taskId, task)
  return task
}

/**
 * Cancel a running task and invalidate cache
 * High priority operation (user-initiated cancellation)
 */
export async function cancelTask(taskId: string): Promise<void> {
  await globalTaskQueue.enqueue(() => api.task.cancel(taskId), { priority: 'HIGH' })
  // Invalidate cache since task status changed
  taskCache.invalidate(taskId)
}

/**
 * Fetch workspace data for an agent run
 * Uses task queue for workspace data operations
 */
export async function getAgentRunWorkspace(
  runId: string,
  selectors?: { retrieval_session_id?: string; prompt_manifest_id?: string }
): Promise<AgentRunWorkspace> {
  return globalTaskQueue.enqueue(
    () => api.agent.getWorkspace(runId, selectors),
    { priority: 'NORMAL' }
  )
}

/**
 * Terminal task statuses that indicate a task has finished
 */
const TERMINAL_STATUSES: readonly TaskStatus[] = ['COMPLETED', 'FAILED', 'CANCELLED'] as const

/**
 * Check if a task has reached a terminal status
 */
function isTerminalStatus(status: TaskStatus): boolean {
  return TERMINAL_STATUSES.includes(status)
}

/**
 * Poll task status at regular intervals with exponential backoff
 *
 * Exponential backoff reduces polling frequency for long-running tasks:
 * - Starts at intervalMs (default 2000ms)
 * - Multiplies by backoffMultiplier (default 1.5) after each poll
 * - Caps at maxIntervalMs (default 10000ms)
 * - Example: 2s → 3s → 4.5s → 6.75s → 10s (capped)
 *
 * @param taskId - Task ID to poll
 * @param onUpdate - Callback invoked when task status changes
 * @param options - Polling configuration
 * @returns Function to stop polling
 */
export function startTaskPolling(
  taskId: string,
  onUpdate: (task: Task) => void,
  options: {
    intervalMs?: number
    maxIntervalMs?: number
    backoffMultiplier?: number
    stopOnComplete?: boolean
    onComplete?: (task: Task) => void
    onError?: (error: Error) => void
  } = {}
): () => void {
  const {
    intervalMs = 2000,
    maxIntervalMs = 10000,
    backoffMultiplier = 1.5,
    stopOnComplete = false,
    onComplete,
    onError,
  } = options

  let currentInterval = intervalMs
  let intervalId: ReturnType<typeof setInterval> | null = null
  let stopped = false

  const poll = async () => {
    if (stopped) return

    try {
      // Skip cache to get fresh status during polling
      const task = await getTask(taskId, { useCache: false })
      onUpdate(task)

      // Check if task reached terminal status
      if (stopOnComplete && isTerminalStatus(task.status)) {
        if (onComplete) {
          onComplete(task)
        }
        stop()
        return
      }

      // Apply exponential backoff for long-running tasks
      if (currentInterval < maxIntervalMs) {
        const nextInterval = Math.min(currentInterval * backoffMultiplier, maxIntervalMs)
        if (nextInterval !== currentInterval) {
          currentInterval = nextInterval
          if (intervalId) {
            clearInterval(intervalId)
            intervalId = setInterval(() => {
              void poll()
            }, currentInterval)
          }
        }
      }
    } catch (error) {
      stop()
      if (onError) {
        // Call onError synchronously to ensure it fires in tests
        onError(error as Error)
      }
    }
  }

  const stop = () => {
    stopped = true
    if (intervalId) {
      clearInterval(intervalId)
      intervalId = null
    }
  }

  // Poll immediately once, then at intervals
  void poll()
  intervalId = setInterval(() => {
    void poll()
  }, currentInterval)

  return stop
}

/**
 * Subscribe to task status change events via IPC
 * Invalidates cache when task status changes
 *
 * @param onStatusChange - Callback invoked when any task status changes
 * @param options - Filter options
 * @returns Function to unsubscribe
 */
export function subscribeToTaskStatusChanges(
  onStatusChange: (task: Task) => void,
  options: { taskId?: string } = {}
): () => void {
  const { taskId } = options

  const handler = (task: Task) => {
    // Invalidate cache for updated task
    taskCache.invalidate(task.id)

    // Filter by task ID if specified
    if (taskId && task.id !== taskId) {
      return
    }
    onStatusChange(task)
  }

  // Register listener and return unsubscribe function
  const unsubscribe = api.events.onTaskStatusChange(handler)
  return unsubscribe
}

/**
 * Clear all cached task data
 * Useful when switching contexts or logging out
 */
export function clearTaskCache(): void {
  taskCache.clear()
}
