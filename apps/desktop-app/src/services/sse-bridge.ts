import { BrowserWindow } from 'electron'
import type { AgentEvent, SseConnectionStatus } from '../preload-api'
import { getApiBaseUrl, getAuthToken } from '../shared/api-client'
import { notifyForAgentEvent } from './system-integration'

const DEFAULT_MAX_RETRY_ATTEMPTS = Infinity
const DEFAULT_MAX_RETRY_DELAY_MS = 30000
const INITIAL_RETRY_DELAY_MS = 1000
const RETRY_BACKOFF_BASE = 2

function buildStreamUrl(taskId: string, lastEventId: string | null): string {
  const params = new URLSearchParams()
  const token = getAuthToken()
  if (token) {
    params.set('access_token', token)
  }
  if (lastEventId) {
    params.set('after_sequence', lastEventId)
  }
  const baseUrl = getApiBaseUrl()
  return `${baseUrl}/api/tasks/${taskId}/events/stream?${params.toString()}`
}

function sendToRenderer(channel: string, data: unknown): void {
  const windows = BrowserWindow.getAllWindows()
  for (const window of windows) {
    window.webContents.send(channel, data)
  }
}

function calculateRetryDelay(attemptNumber: number, maxDelayMs: number): number {
  const exponentialDelay = Math.pow(RETRY_BACKOFF_BASE, attemptNumber - 1) * INITIAL_RETRY_DELAY_MS
  return Math.min(exponentialDelay, maxDelayMs)
}

export interface SseBridge {
  close: () => void
  retryNow: () => void
}

export interface SseBridgeOptions {
  maxRetryAttempts?: number
  maxRetryDelayMs?: number
}

export function createSseBridge(
  taskId: string,
  lastEventId: string | null,
  options: SseBridgeOptions = {}
): SseBridge {
  const {
    maxRetryAttempts = DEFAULT_MAX_RETRY_ATTEMPTS,
    maxRetryDelayMs = DEFAULT_MAX_RETRY_DELAY_MS
  } = options

  let eventSource: EventSource | null = null
  let retryAttempts = 0
  let retryTimeout: NodeJS.Timeout | null = null
  let isClosed = false
  let currentLastEventId = lastEventId

  function cleanupRetryTimeout(): void {
    if (retryTimeout) {
      clearTimeout(retryTimeout)
      retryTimeout = null
    }
  }

  function closeEventSource(): void {
    eventSource?.close()
    eventSource = null
  }

  function scheduleRetry(): void {
    const delay = calculateRetryDelay(retryAttempts, maxRetryDelayMs)
    retryTimeout = setTimeout(() => {
      connect()
    }, delay)
  }

  function handleConnectionOpen(): void {
    retryAttempts = 0
    sendToRenderer('agent:connection-status', 'open' as SseConnectionStatus)
  }

  function handleMessage(event: MessageEvent): void {
    try {
      const data = JSON.parse(event.data) as AgentEvent
      currentLastEventId = data.id
      sendToRenderer('agent:message-stream', data)
      notifyForAgentEvent(data)
    } catch (error) {
      console.error('Failed to parse SSE event:', error)
    }
  }

  function handleConnectionError(): void {
    closeEventSource()

    if (isClosed) return

    retryAttempts++

    if (retryAttempts > maxRetryAttempts) {
      sendToRenderer('agent:connection-status', 'failed' as SseConnectionStatus)
      return
    }

    sendToRenderer('agent:connection-status', 'retrying' as SseConnectionStatus)
    scheduleRetry()
  }

  function connect(): void {
    if (isClosed) return

    const url = buildStreamUrl(taskId, currentLastEventId)
    eventSource = new EventSource(url)

    eventSource.addEventListener('open', handleConnectionOpen)
    eventSource.addEventListener('message', handleMessage)
    eventSource.addEventListener('error', handleConnectionError)
  }

  connect()

  return {
    close: () => {
      isClosed = true
      cleanupRetryTimeout()
      closeEventSource()
      sendToRenderer('agent:connection-status', 'closed' as SseConnectionStatus)
    },
    retryNow: () => {
      cleanupRetryTimeout()
      closeEventSource()
      connect()
    },
  }
}
