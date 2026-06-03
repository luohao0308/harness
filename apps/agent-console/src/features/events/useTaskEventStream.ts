import { useCallback, useState } from "react";

import type { AgentEvent } from "../tasks/api";
import { taskEventReconnectStreamUrl } from "../tasks/api";
import { useSSE } from "../../hooks/useSSE";

export function useTaskEventStream(taskId: string | undefined) {
  const [events, setEvents] = useState<AgentEvent[]>([]);

  const urlFactory = useCallback(
    (lastEventId: string | null) =>
      taskId ? taskEventReconnectStreamUrl(taskId, lastEventId) : "",
    [taskId],
  );
  const sse = useSSE<AgentEvent>(taskId ? urlFactory : null, {
    parse: (data) => JSON.parse(data) as AgentEvent,
    onMessage: (parsed) => {
        setEvents((current) => {
          if (current.some((event) => event.sequence === parsed.sequence)) {
            return current;
          }
          return [...current, parsed].sort((left, right) => left.sequence - right.sequence);
        });
    },
  });

  return { events, connected: sse.connected, status: sse.status };
}
