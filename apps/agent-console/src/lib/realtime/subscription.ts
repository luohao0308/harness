import { useEffect, useMemo, useRef, useState } from "react";
import {
  createReconnectingRealtimeClient,
  type RealtimeConnectionStatus,
  type RealtimeClientOptions,
} from "./client";

/**
 * React hook for managing real-time subscriptions
 * Wraps the low-level client with React lifecycle management
 */
export function useRealtimeSubscription<T>(
  urlFactory: ((lastEventId: string | null) => string) | null,
  options: Omit<RealtimeClientOptions<T>, "onStatus"> & {
    onStatus?: (status: RealtimeConnectionStatus) => void;
  },
) {
  const [status, setStatus] = useState<RealtimeConnectionStatus>("closed");
  const optionsRef = useRef(options);
  const parseRef = useRef(options.parse);
  const onMessageRef = useRef(options.onMessage);

  // Extract config values before useMemo so React compares primitive values
  const maxRetryDelayMs = options.maxRetryDelayMs;
  const maxAttemptsBeforeNotice = options.maxAttemptsBeforeNotice;

  // Memoize config values to prevent unnecessary reconnections
  const config = useMemo(
    () => ({
      maxRetryDelayMs,
      maxAttemptsBeforeNotice,
    }),
    [maxRetryDelayMs, maxAttemptsBeforeNotice]
  );

  useEffect(() => {
    optionsRef.current = options;
    parseRef.current = options.parse;
    onMessageRef.current = options.onMessage;
  });

  useEffect(() => {
    if (!urlFactory) {
      setStatus("closed");
      return undefined;
    }

    const client = createReconnectingRealtimeClient(urlFactory, {
      parse: (data) => parseRef.current(data),
      onMessage: (event, raw) => onMessageRef.current(event, raw),
      maxRetryDelayMs: config.maxRetryDelayMs,
      maxAttemptsBeforeNotice: config.maxAttemptsBeforeNotice,
      onStatus(nextStatus) {
        setStatus(nextStatus);
        optionsRef.current.onStatus?.(nextStatus);
      },
    });

    return () => client.close();
  }, [config, urlFactory]);

  return { status, connected: status === "open" };
}

export type SubscriptionHandle = ReturnType<typeof useRealtimeSubscription>;
