import type { AgentEvent } from "../../tasks/api";
import type { Subagent } from "../../tasks/api";
import { Card, CardHeader } from "../../../components/ui/card";
import { Badge, Dot, statusTone } from "../../../components/ui/badge";
import { useI18n } from "../../../lib/i18n";
import { actorLabel, eventLabel } from "../../../lib/labels";
import { statusLabel } from "../../../lib/labels";
import { formatShortDate } from "../../../lib/utils";

export function EventTimeline({
  events,
  connected,
  subagents = [],
}: {
  events: AgentEvent[];
  connected: boolean;
  subagents?: Subagent[];
}) {
  const { text } = useI18n();
  const subagentsById = new Map(subagents.map((subagent) => [subagent.id, subagent]));
  const topology = events
    .filter((event) => event.event_type === "SUBAGENT_SPAWNED")
    .map((event) => {
      const agentRunId =
        typeof event.payload_json.agent_run_id === "string"
          ? event.payload_json.agent_run_id
          : event.agent_run_id;
      const assignment = event.payload_json.assignment;
      const stepKey =
        assignment && typeof assignment === "object" && !Array.isArray(assignment)
          ? (assignment as Record<string, unknown>).step_key
          : undefined;
      return {
        sequence: event.sequence,
        stepKey: typeof stepKey === "string" && stepKey.length > 0 ? stepKey : "未绑定步骤",
        agentRunId,
        subagent: agentRunId ? subagentsById.get(agentRunId) : undefined,
      };
    });
  return (
    <Card>
      <CardHeader>
        <div className="text-[11px] tracking-widest text-slate-500">{text("实时事件时间线", "Live Event Timeline")}</div>
        <div className="flex items-center gap-2 text-[11px] text-slate-500">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
          {connected ? text("实时连接", "Live connection") : text("快照", "Snapshot")} ·{" "}
          {text(`序号 ${events.at(-1)?.sequence ?? 0}`, `Seq ${events.at(-1)?.sequence ?? 0}`)}
        </div>
      </CardHeader>
      {topology.length > 0 && (
        <div className="border-b border-slate-100 px-3 py-2 text-[10px] text-slate-500">
          <div className="mb-1 font-semibold text-slate-700">{text("并行执行拓扑", "Parallel Execution Topology")}</div>
          <div className="space-y-1">
            {topology.slice(0, 5).map((item) => (
              <div
                key={`${item.sequence}-${item.agentRunId ?? item.stepKey}`}
                className="flex items-center gap-1.5 truncate"
              >
                <span className="font-mono text-slate-700">{item.stepKey}</span>
                <span className="text-slate-300">→</span>
                <GitBranchLabel agentRunId={item.agentRunId} />
                <Badge tone={statusTone(item.subagent?.status ?? "PENDING")} className="px-1 py-0 text-[10px]">
                  {statusLabel(item.subagent?.status ?? "PENDING")}
                </Badge>
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="font-mono text-[11px]">
        <div className="grid grid-cols-[60px_86px_180px_90px_1fr] border-b border-slate-100 bg-slate-50/40 px-3 py-1.5 text-slate-400">
          <div>{text("序号", "Seq")}</div>
          <div>{text("时间", "Time")}</div>
          <div>{text("事件", "Event")}</div>
          <div>{text("来源", "Source")}</div>
          <div>{text("载荷", "Payload")}</div>
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
              <span className="text-slate-800">{eventLabel(event.event_type)}</span>
            </div>
            <div className="text-slate-600">{actorLabel(event.actor_type)}</div>
            <div className="truncate text-slate-500">{JSON.stringify(event.payload_json)}</div>
          </div>
        ))}
      </div>
    </Card>
  );
}

function GitBranchLabel({ agentRunId }: { agentRunId: string | null }) {
  const { text } = useI18n();
  return (
    <span className="font-mono text-slate-600">
      {agentRunId ? agentRunId.slice(0, 8) : text("等待子代理", "Waiting for subagent")}
    </span>
  );
}
