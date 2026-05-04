import { useQuery } from "@tanstack/react-query";
import { Box } from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Card, CardHeader } from "../../../components/ui/card";
import { getWarmPool } from "../../tasks/api";

export function SandboxesPage() {
  const warmPool = useQuery({ queryKey: ["warm-pool"], queryFn: getWarmPool });

  return (
    <ConsoleShell title="沙箱">
      <div className="space-y-4 p-4">
        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Box className="h-4 w-4" /> WarmPool
            </div>
            <span className="text-xs text-slate-500">Docker 容器沙箱预热池</span>
          </CardHeader>
          <div className="grid grid-cols-4 gap-3 p-3 text-xs">
            <Metric label="空闲" value={String(warmPool.data?.idle ?? "...")} />
            <Metric label="忙碌" value={String(warmPool.data?.busy ?? "...")} />
            <Metric label="失败" value={String(warmPool.data?.failed ?? "...")} />
            <Metric label="容量" value={`${warmPool.data?.min_size ?? "..."} / ${warmPool.data?.max_size ?? "..."}`} />
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
