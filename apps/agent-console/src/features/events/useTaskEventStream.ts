import { useEffect, useState } from "react";

import type { AgentEvent } from "../tasks/api";
import { taskEventStreamUrl } from "../tasks/api";

export function useTaskEventStream(taskId: string | undefined) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!taskId) {
      return undefined;
    }

    const eventSource = new EventSource(taskEventStreamUrl(taskId));
    eventSource.onopen = () => setConnected(true);
    eventSource.onerror = () => setConnected(false);
    eventSource.onmessage = (message) => {
      try {
        const parsed = JSON.parse(message.data) as AgentEvent;
        setEvents((current) => {
          if (current.some((event) => event.sequence === parsed.sequence)) {
            return current;
          }
          return [...current, parsed].sort((left, right) => left.sequence - right.sequence);
        });
      } catch {
        setConnected(false);
      }
    };

    return () => {
      eventSource.close();
      setConnected(false);
    };
  }, [taskId]);

  return { events, connected };
}
