import { useQuery } from "@tanstack/react-query";
import { Brain } from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Card, CardHeader } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { statusLabel } from "../../../lib/labels";
import { getModelSettings } from "../../tasks/api";

export function ModelSettingsPage() {
  const settings = useQuery({ queryKey: ["settings", "models"], queryFn: getModelSettings });

  return (
    <ConsoleShell title="模型设置">
      <div className="space-y-4 p-4">
        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Brain className="h-4 w-4" /> 模型网关
            </div>
            <span className="text-xs text-slate-500">模型网关、供应商与限流状态</span>
          </CardHeader>
          <div className="grid grid-cols-3 gap-3 p-3 text-xs">
            <Metric label="默认供应商" value={settings.data?.default_provider ?? "..."} />
            <Metric label="默认模型" value={settings.data?.default_model ?? "..."} />
            <Metric label="健康状态" value={statusLabel(String(settings.data?.health.status ?? "..."))} />
          </div>
        </Card>
        <Card>
          <CardHeader>
            <div className="text-[11px] tracking-widest text-slate-500">供应商</div>
          </CardHeader>
          <Table>
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <Th>名称</Th>
                <Th>状态</Th>
                <Th>限流</Th>
              </tr>
            </thead>
            <tbody>
              {(settings.data?.providers ?? []).map((provider) => (
                <tr key={String(provider.name)} className="border-t border-slate-100">
                  <Td className="font-mono">{String(provider.name)}</Td>
                  <Td>{statusLabel(String(provider.status))}</Td>
                  <Td>{String(provider.rate_limit_rpm)} rpm</Td>
                </tr>
              ))}
            </tbody>
          </Table>
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
