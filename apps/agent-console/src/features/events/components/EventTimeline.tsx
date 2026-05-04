import type { AgentEvent } from "../../tasks/api";
import { Card, CardHeader } from "../../../components/ui/card";
import { Dot, statusTone } from "../../../components/ui/badge";
import { formatShortDate } from "../../../lib/utils";

export function EventTimeline({
  events,
  connected,
}: {
  events: AgentEvent[];
  connected: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="text-[11px] tracking-widest text-slate-500">LIVE EVENT TIMELINE</div>
        <div className="flex items-center gap-2 text-[11px] text-slate-500">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
          {connected ? "streaming" : "snapshot"} · seq {events.at(-1)?.sequence ?? 0}
        </div>
      </CardHeader>
      <div className="font-mono text-[11px]">
        <div className="grid grid-cols-[60px_86px_180px_90px_1fr] border-b border-slate-100 bg-slate-50/40 px-3 py-1.5 text-slate-400">
          <div>seq</div>
          <div>time</div>
          <div>event</div>
          <div>actor</div>
          <div>payload</div>
        </div>
        {events.map((event) => (
          <div
            key={`${event.id}-${event.sequence}`}
            className="grid grid-cols-[60px_86px_180px_90px_1fr] border-b border-slate-50 px-3 py-1.5 hover:bg-slate-50/60"
          >
            <div className="text-slate-400">{event.sequence}</div>
            <div className="text-slate-500">{formatShortDate(event.created_at)}</div>
            <div className="flex items-center gap-1.5">
              <Dot tone={statusTone(event.event_type)} />
              <span className="text-slate-800">{event.event_type}</span>
            </div>
            <div className="text-slate-600">{event.actor_type}</div>
            <div className="truncate text-slate-500">{JSON.stringify(event.payload_json)}</div>
          </div>
        ))}
      </div>
    </Card>
  );
}
