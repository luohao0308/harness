import { useQuery } from "@tanstack/react-query";
import { Box } from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Card, CardHeader } from "../../../components/ui/card";
import { useI18n } from "../../../lib/i18n";
import { getWarmPool } from "../../tasks/api";

export function SandboxesPage() {
  const { text } = useI18n();
  const warmPool = useQuery({ queryKey: ["warm-pool"], queryFn: getWarmPool });

  return (
    <ConsoleShell title={text("沙箱", "Sandboxes")}>
      <div className="space-y-4 p-4">
        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Box className="h-4 w-4" /> WarmPool
            </div>
            <span className="text-xs text-slate-500">{text("Docker 容器沙箱预热池", "Docker container sandbox warm pool")}</span>
          </CardHeader>
          <div className="grid grid-cols-4 gap-3 p-3 text-xs">
            <Metric label={text("空闲", "Idle")} value={String(warmPool.data?.idle ?? "...")} />
            <Metric label={text("忙碌", "Busy")} value={String(warmPool.data?.busy ?? "...")} />
            <Metric label={text("失败", "Failed")} value={String(warmPool.data?.failed ?? "...")} />
            <Metric label={text("容量", "Capacity")} value={`${warmPool.data?.min_size ?? "..."} / ${warmPool.data?.max_size ?? "..."}`} />
          </div>
        </Card>
      </div>
    </ConsoleShell>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50 p-3">
      <div className="text-slate-500">{label}</div>
      <div className="mt-1 font-mono text-slate-900">{value}</div>
    </div>
  );
}
