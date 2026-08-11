/**
 * Task Queue Manager for Desktop App (Phase 1.2 - REFACTOR)
 *
 * Manages concurrent task operations with priority queuing:
 * - Limits concurrent IPC calls to prevent overwhelming the main process
 * - Priority-based task execution (HIGH > NORMAL > LOW)
 * - Automatic retries with exponential backoff for failed operations
 * - Queue metrics for monitoring and debugging
 */

export type TaskPriority = 'HIGH' | 'NORMAL' | 'LOW'

interface QueuedTask<T> {
  id: string
  priority: TaskPriority
  operation: () => Promise<T>
  resolve: (value: T) => void
  reject: (error: Error) => void
  retries: number
  maxRetries: number
}

interface QueueMetrics {
  pending: number
  running: number
  completed: number
  failed: number
  totalWaitTimeMs: number
  averageWaitTimeMs: number
}

export class TaskQueue {
  private queue: QueuedTask<any>[] = []
  private running = 0
  private readonly maxConcurrent: number
  private metrics = {
    completed: 0,
    failed: 0,
    totalWaitTimeMs: 0,
  }
  private taskStartTimes = new Map<string, number>()
  private sleepFn: (ms: number) => Promise<void>

  constructor(
    maxConcurrent: number = 5,
    sleepFn: (ms: number) => Promise<void> = (ms) => new Promise(resolve => setTimeout(resolve, ms))
  ) {
    this.maxConcurrent = maxConcurrent
    this.sleepFn = sleepFn
  }

  /**
   * Enqueue a task operation with priority
   */
  async enqueue<T>(
    operation: () => Promise<T>,
    options: {
      priority?: TaskPriority
      maxRetries?: number
    } = {}
  ): Promise<T> {
    const { priority = 'NORMAL', maxRetries = 3 } = options

    return new Promise<T>((resolve, reject) => {
      const task: QueuedTask<T> = {
        id: `task-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        priority,
        operation,
        resolve,
        reject,
        retries: 0,
        maxRetries,
      }

      // Insert task based on priority
      this.insertByPriority(task)
      this.taskStartTimes.set(task.id, Date.now())

      // Try to process queue
      this.processQueue()
    })
  }

  /**
   * Insert task into queue based on priority
   */
  private insertByPriority<T>(task: QueuedTask<T>): void {
    const priorityOrder = { HIGH: 0, NORMAL: 1, LOW: 2 }
    const taskPriorityValue = priorityOrder[task.priority]

    let insertIndex = this.queue.length
    for (let i = 0; i < this.queue.length; i++) {
      if (priorityOrder[this.queue[i].priority] > taskPriorityValue) {
        insertIndex = i
        break
      }
    }

    this.queue.splice(insertIndex, 0, task)
  }

  /**
   * Process queued tasks up to maxConcurrent limit
   */
  private async processQueue(): Promise<void> {
    while (this.running < this.maxConcurrent && this.queue.length > 0) {
      const task = this.queue.shift()
      if (!task) break

      this.running++
      this.executeTask(task)
    }
  }

  /**
   * Execute a single task with retry logic
   */
  private async executeTask<T>(task: QueuedTask<T>): Promise<void> {
    try {
      const result = await task.operation()

      // Record metrics
      const startTime = this.taskStartTimes.get(task.id)
      if (startTime) {
        const waitTime = Date.now() - startTime
        this.metrics.totalWaitTimeMs += waitTime
        this.taskStartTimes.delete(task.id)
      }
      this.metrics.completed++

      task.resolve(result)
      this.running--
      this.processQueue()
    } catch (error) {
      // Retry logic with exponential backoff
      if (task.retries < task.maxRetries) {
        task.retries++
        const backoffMs = Math.pow(2, task.retries - 1) * 1000

        await this.sleepFn(backoffMs)

        // Re-enqueue with same priority (keep running count as-is)
        this.insertByPriority(task)
        this.processQueue()
      } else {
        // Max retries exceeded - reject immediately
        this.running--
        this.metrics.failed++

        // Reject synchronously to ensure error propagates immediately
        task.reject(error as Error)
        this.processQueue()
      }
    }
  }

  /**
   * Get current queue metrics
   */
  getMetrics(): QueueMetrics {
    return {
      pending: this.queue.length,
      running: this.running,
      completed: this.metrics.completed,
      failed: this.metrics.failed,
      totalWaitTimeMs: this.metrics.totalWaitTimeMs,
      averageWaitTimeMs:
        this.metrics.completed > 0
          ? this.metrics.totalWaitTimeMs / this.metrics.completed
          : 0,
    }
  }

  /**
   * Clear all pending tasks
   */
  clear(): void {
    this.queue.forEach(task => {
      task.reject(new Error('Queue cleared'))
    })
    this.queue = []
    this.taskStartTimes.clear()
  }

  /**
   * Wait for all running tasks to complete
   */
  async drain(): Promise<void> {
    while (this.running > 0 || this.queue.length > 0) {
      await new Promise(resolve => setTimeout(resolve, 100))
    }
  }
}

// Global task queue instance with max 5 concurrent operations
export const globalTaskQueue = new TaskQueue(5)
