import { notifyFeedback } from "../components/ui/feedback-toast";

export type SseConnectionStatus = "connecting" | "open" | "closed" | "retrying" | "failed";

export type SseClientOptions<T> = {
  parse: (data: string) => T;
  onMessage: (event: T, raw: MessageEvent<string>) => void;
  onStatus?: (status: SseConnectionStatus) => void;
  maxRetryDelayMs?: number;
  maxAttemptsBeforeNotice?: number;
};

export type SseClient = {
  close: () => void;
  retryNow: () => void;
};

export function createReconnectingSseClient<T>(
  urlFactory: (lastEventId: string | null) => string,
  options: SseClientOptions<T>,
): SseClient {
  const maxRetryDelayMs = options.maxRetryDelayMs ?? 30_000;
  const maxAttemptsBeforeNotice = options.maxAttemptsBeforeNotice ?? 5;
  let source: EventSource | null = null;
  let closed = false;
  let retryTimer: number | null = null;
  let reconnectAttempts = 0;
  let lastEventId: string | null = null;
  let noticeShown = false;

  const setStatus = (status: SseConnectionStatus) => options.onStatus?.(status);

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
      source?.close();
      if (closed) {
        setStatus("closed");
        return;
      }
      reconnectAttempts += 1;
      const delayMs = Math.min(2 ** Math.max(0, reconnectAttempts - 1) * 1000, maxRetryDelayMs);
      setStatus(reconnectAttempts >= maxAttemptsBeforeNotice ? "failed" : "retrying");
      if (reconnectAttempts >= maxAttemptsBeforeNotice && !noticeShown) {
        noticeShown = true;
        notifyFeedback({
          tone: "warning",
          title: "实时连接断开",
          description: "系统正在自动重连；如果长时间未恢复，请刷新页面。",
        });
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
