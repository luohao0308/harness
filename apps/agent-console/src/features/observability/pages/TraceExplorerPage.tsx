import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { GitBranch, RefreshCw, Search } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { formatShortDate } from "../../../lib/utils";
import { TraceGantt } from "../components/TraceGantt";
import { getObservabilityTrace, listObservabilityTraces, type ObservabilityTraceSpan } from "../../tasks/api";

export function TraceExplorerPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTraceId = searchParams.get("trace_id") ?? "";
  const [draftTraceId, setDraftTraceId] = useState(initialTraceId);
  const [traceId, setTraceId] = useState(initialTraceId);
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const traces = useQuery({
    queryKey: ["observability", "traces"],
    queryFn: () => listObservabilityTraces({ limit: 80 }),
    refetchInterval: 20_000,
  });
  const activeTraceId = traceId || traces.data?.items[0]?.trace_id || "";
  const detail = useQuery({
    queryKey: ["observability", "trace-detail", activeTraceId],
    queryFn: () => getObservabilityTrace(activeTraceId),
    enabled: Boolean(activeTraceId),
  });
  const spans = detail.data?.spans ?? [];
  const selectedSpan = useMemo(
    () => spans.find((span) => span.span_id === selectedSpanId) ?? spans[0] ?? null,
    [selectedSpanId, spans],
  );

  const applyTrace = (value = draftTraceId) => {
    const clean = value.trim();
    setTraceId(clean);
    setDraftTraceId(clean);
    const next = new URLSearchParams(searchParams);
    if (clean) next.set("trace_id", clean);
    else next.delete("trace_id");
    setSearchParams(next, { replace: true });
  };

  return (
    <ConsoleShell title="Trace 探索">
      <div className="grid min-h-full grid-cols-12 gap-4 bg-slate-50/70 p-4">
        <aside className="col-span-12 space-y-3 xl:col-span-3">
          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <GitBranch className="h-4 w-4" /> Trace 列表
              </div>
              <Button onClick={() => void traces.refetch()} disabled={traces.isFetching} className="w-8 px-0" aria-label="刷新 Trace">
                <RefreshCw className="h-3.5 w-3.5" />
              </Button>
            </CardHeader>
            <div className="max-h-[720px] overflow-y-auto p-2">
              {(traces.data?.items ?? []).map((trace) => (
                <button
                  key={trace.trace_id}
                  type="button"
                  onClick={() => applyTrace(trace.trace_id)}
                  className={`mb-2 w-full rounded-md border p-2 text-left text-xs transition ${
                    activeTraceId === trace.trace_id ? "border-cyan-300 bg-cyan-50" : "border-slate-100 bg-white hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-medium text-slate-900">{trace.root_name}</span>
                    <Badge tone={statusTone(trace.status)}>{trace.status}</Badge>
                  </div>
                  <div className="mt-1 truncate font-mono text-[10px] text-slate-400">{trace.trace_id}</div>
                  <div className="mt-1 text-[11px] text-slate-500">
                    {trace.span_count} spans · {trace.duration_ms} ms · {formatShortDate(trace.start_time)}
                  </div>
                </button>
              ))}
              {!traces.isLoading && !traces.data?.items.length ? (
                <div className="rounded-md border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-xs text-slate-500">暂无 Trace</div>
              ) : null}
            </div>
          </Card>
        </aside>

        <main className="col-span-12 space-y-3 xl:col-span-6">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <Link to="/observability" className="hover:text-slate-900">观测</Link>
                <span>/</span>
                <span className="font-medium text-slate-900">Trace</span>
              </div>
              <div className="flex items-center gap-2">
                <Input
                  value={draftTraceId}
                  onChange={(event) => setDraftTraceId(event.target.value)}
                  placeholder="trace_id"
                  className="h-8 w-64 font-mono text-xs"
                  aria-label="Trace ID"
                />
                <Button onClick={() => applyTrace()}>
                  <Search className="h-3.5 w-3.5" /> 查询
                </Button>
              </div>
            </CardHeader>
            <div className="p-3">
              <TraceGantt spans={spans} selectedSpanId={selectedSpan?.span_id ?? null} onSelect={(span) => setSelectedSpanId(span.span_id)} />
            </div>
          </Card>
        </main>

        <aside className="col-span-12 xl:col-span-3">
          <Card>
            <CardHeader>
              <div className="text-sm font-semibold text-slate-900">Span 属性</div>
              {detail.data ? <Badge tone="info">{detail.data.source}</Badge> : null}
            </CardHeader>
            <div className="space-y-3 p-3 text-xs">
              {selectedSpan ? <SpanDetail span={selectedSpan} /> : <div className="text-slate-500">选择一个 Span</div>}
            </div>
          </Card>
        </aside>
      </div>
    </ConsoleShell>
  );
}

function SpanDetail({ span }: { span: ObservabilityTraceSpan }) {
  return (
    <>
      <div>
        <div className="text-[11px] text-slate-500">名称</div>
        <div className="mt-1 font-medium text-slate-900">{span.name}</div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Metric label="Kind" value={span.kind} />
        <Metric label="状态" value={span.status} />
        <Metric label="耗时" value={`${span.duration_ms} ms`} />
        <Metric label="服务" value={span.service} />
      </div>
      {span.task_id ? <Link className="text-cyan-700 hover:underline" to={`/runs/${span.task_id}`}>打开运行 {span.task_id.slice(0, 8)}</Link> : null}
      <pre className="max-h-[420px] overflow-auto rounded-md bg-slate-950 p-3 text-[11px] leading-5 text-slate-100">
        {JSON.stringify(span.attributes, null, 2)}
      </pre>
    </>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50 p-2">
      <div className="text-[10px] text-slate-500">{label}</div>
      <div className="mt-1 truncate font-mono text-[11px] text-slate-900">{value}</div>
    </div>
  );
}
