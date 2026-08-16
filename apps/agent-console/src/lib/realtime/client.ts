/**
 * Generic real-time client abstraction
 * Extracted from observability/teams polling patterns for reuse
 */

export type RealtimeConnectionStatus = "connecting" | "open" | "closed" | "retrying" | "failed";

export type RealtimeClientOptions<T> = {
  parse: (data: string) => T;
  onMessage: (event: T, raw: MessageEvent<string>) => void;
  onStatus?: (status: RealtimeConnectionStatus) => void;
  maxRetryDelayMs?: number;
  maxAttemptsBeforeNotice?: number;
};

export type RealtimeClient = {
  close: () => void;
  retryNow: () => void;
};

/**
 * Creates a reconnecting SSE client with exponential backoff
 * Re-exported from sse-client.ts for centralized real-time infrastructure
 */
export function createReconnectingRealtimeClient<T>(
  urlFactory: (lastEventId: string | null) => string,
  options: RealtimeClientOptions<T>,
): RealtimeClient {
  const maxRetryDelayMs = options.maxRetryDelayMs ?? 30_000;
  const maxAttemptsBeforeNotice = options.maxAttemptsBeforeNotice ?? 5;
  let source: EventSource | null = null;
  let closed = false;
  let retryTimer: number | null = null;
  let reconnectAttempts = 0;
  let lastEventId: string | null = null;
  let noticeShown = false;

  const setStatus = (status: RealtimeConnectionStatus) => options.onStatus?.(status);

  const clearRetryTimer = () => {
    if (retryTimer !== null) {
      window.clearTimeout(retryTimer);
      retryTimer = null;
    }
  };

  const connect = () => {
    if (closed) return;
    clearRetryTimer();
    source?.close();
    setStatus(reconnectAttempts > 0 ? "retrying" : "connecting");
    source = new EventSource(urlFactory(lastEventId));

    source.onopen = () => {
      reconnectAttempts = 0;
      noticeShown = false;
      setStatus("open");
    };

    source.onmessage = (message) => {
      if (message.lastEventId) {
        lastEventId = message.lastEventId;
      }
      try {
        options.onMessage(options.parse(message.data), message);
      } catch {
        setStatus("failed");
      }
    };

    source.onerror = () => {
      if (closed) {
        source?.close();
        setStatus("closed");
        return;
      }
      source?.close();
      reconnectAttempts += 1;
      const delayMs = Math.min(2 ** Math.max(0, reconnectAttempts - 1) * 1000, maxRetryDelayMs);
      setStatus(reconnectAttempts >= maxAttemptsBeforeNotice ? "failed" : "retrying");

      if (reconnectAttempts >= maxAttemptsBeforeNotice && !noticeShown) {
        noticeShown = true;
        // User feedback handled by consumer via onStatus callback
      }

      retryTimer = window.setTimeout(connect, delayMs);
    };
  };

  connect();

  return {
    close() {
      closed = true;
      clearRetryTimer();
      source?.close();
      setStatus("closed");
    },
    retryNow() {
      reconnectAttempts = 0;
      connect();
    },
  };
}
