import type { ObservabilityTraceSpan } from "../../tasks/api";

type Props = {
  spans: ObservabilityTraceSpan[];
  selectedSpanId: string | null;
  onSelect: (span: ObservabilityTraceSpan) => void;
};

const KIND_COLORS: Record<string, string> = {
  server: "bg-cyan-500",
  client: "bg-emerald-500",
  internal: "bg-slate-500",
  producer: "bg-amber-500",
  consumer: "bg-violet-500",
};

export function TraceGantt({ spans, selectedSpanId, onSelect }: Props) {
  const ordered = traceOrder(spans).slice(0, 1000);
  const firstStart = Math.min(
    ...ordered.map((row) => new Date(row.span.start_time).getTime()),
    Date.now(),
  );
  const lastEnd = Math.max(
    ...ordered.map((row) => new Date(row.span.start_time).getTime() + row.span.duration_ms),
    firstStart + 1,
  );
  const total = Math.max(lastEnd - firstStart, 1);

  if (ordered.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-md border border-dashed border-slate-200 bg-slate-50 text-xs text-slate-500">
        暂无 Span
      </div>
    );
  }

  return (
    <div className="max-h-[620px] overflow-auto rounded-md border border-slate-100 bg-white">
      <div className="min-w-[820px] divide-y divide-slate-100">
        {ordered.map(({ span, depth }) => {
          const start = new Date(span.start_time).getTime();
          const left = ((start - firstStart) / total) * 100;
          const width = Math.max(0.8, (Math.max(span.duration_ms, 1) / total) * 100);
          const selected = selectedSpanId === span.span_id;
          return (
            <button
              key={span.span_id}
              type="button"
              onClick={() => onSelect(span)}
              className={`grid w-full grid-cols-[300px_1fr_84px] items-center gap-3 px-3 py-2 text-left text-xs transition ${
                selected ? "bg-cyan-50" : "hover:bg-slate-50"
              }`}
            >
              <div className="min-w-0" style={{ paddingLeft: depth * 14 }}>
                <div className="truncate font-medium text-slate-900">{span.name}</div>
                <div className="mt-0.5 truncate font-mono text-[10px] text-slate-400">
                  {span.service} · {span.span_id}
                </div>
              </div>
              <div className="relative h-5 rounded bg-slate-50">
                <div
                  className={`absolute top-1 h-3 rounded ${KIND_COLORS[span.kind] ?? KIND_COLORS.internal} ${
                    span.status === "ERROR" ? "ring-2 ring-red-300" : ""
                  }`}
                  style={{ left: `${left}%`, width: `${width}%` }}
                />
              </div>
              <div className="font-mono text-[11px] text-slate-500">{span.duration_ms} ms</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function traceOrder(spans: ObservabilityTraceSpan[]) {
  const byParent = new Map<string | null, ObservabilityTraceSpan[]>();
  for (const span of spans) {
    const key = span.parent_span_id ?? null;
    byParent.set(key, [...(byParent.get(key) ?? []), span]);
  }
  for (const rows of byParent.values()) {
    rows.sort((a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime());
  }
  const seen = new Set<string>();
  const rows: Array<{ span: ObservabilityTraceSpan; depth: number }> = [];
  const visit = (span: ObservabilityTraceSpan, depth: number) => {
    if (seen.has(span.span_id)) return;
    seen.add(span.span_id);
    rows.push({ span, depth });
    for (const child of byParent.get(span.span_id) ?? []) {
      visit(child, depth + 1);
    }
  };
  for (const root of byParent.get(null) ?? []) {
    visit(root, 0);
  }
  for (const span of spans) {
    visit(span, 0);
  }
  return rows;
}
