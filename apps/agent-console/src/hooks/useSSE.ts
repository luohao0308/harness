import { useEffect, useRef, useState } from "react";

import {
  createReconnectingSseClient,
  type SseConnectionStatus,
  type SseClientOptions,
} from "../lib/sse-client";

export function useSSE<T>(
  urlFactory: ((lastEventId: string | null) => string) | null,
  options: Omit<SseClientOptions<T>, "onStatus"> & {
    onStatus?: (status: SseConnectionStatus) => void;
  },
) {
  const [status, setStatus] = useState<SseConnectionStatus>("closed");
  const optionsRef = useRef(options);

  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  useEffect(() => {
    if (!urlFactory) {
      setStatus("closed");
      return undefined;
    }
    const client = createReconnectingSseClient(urlFactory, {
      parse: (data) => optionsRef.current.parse(data),
      onMessage: (event, raw) => optionsRef.current.onMessage(event, raw),
      maxRetryDelayMs: options.maxRetryDelayMs,
      maxAttemptsBeforeNotice: options.maxAttemptsBeforeNotice,
      onStatus(nextStatus) {
        setStatus(nextStatus);
        optionsRef.current.onStatus?.(nextStatus);
      },
    });
    return () => client.close();
  }, [options.maxAttemptsBeforeNotice, options.maxRetryDelayMs, urlFactory]);

  return { status, connected: status === "open" };
}
