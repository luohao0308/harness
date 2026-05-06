import { useEffect, useRef } from "react";
import * as echarts from "echarts";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Card, CardHeader } from "../../../components/ui/card";
import { useI18n } from "../../../lib/i18n";

export function PlaceholderPage({ title, chart = false }: { title: string; chart?: boolean }) {
  const { text } = useI18n();
  const chartRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!chart || !chartRef.current) {
      return undefined;
    }
    const instance = echarts.init(chartRef.current);
    instance.setOption({
      grid: { left: 28, right: 12, top: 16, bottom: 24 },
      xAxis: { type: "category", data: ["10:00", "10:10", "10:20", "10:30", "10:40"] },
      yAxis: { type: "value" },
      series: [{ type: "line", smooth: true, data: [12, 18, 16, 24, 21] }],
    });
    return () => instance.dispose();
  }, [chart]);

  return (
    <ConsoleShell title={title}>
      <div className="mx-auto max-w-[1440px] p-6">
        <Card>
          <CardHeader>
            <div className="text-[11px] tracking-widest text-slate-500">
              {title.toUpperCase()}
            </div>
          </CardHeader>
          <div className="p-5 text-sm text-slate-600">
            {chart ? (
              <div ref={chartRef} className="h-72 w-full" />
            ) : (
              <div className="rounded-md border border-dashed border-slate-200 p-8">
                {text(
                  "该运营视图已预留给后续运行时阶段。",
                  "This operational view is reserved for the next runtime stages.",
                )}
              </div>
            )}
          </div>
        </Card>
      </div>
    </ConsoleShell>
  );
}
