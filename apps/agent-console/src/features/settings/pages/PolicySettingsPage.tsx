import { useQuery } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, statusTone } from "../../../components/ui/badge";
import { Card, CardHeader } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { approvalLabel, booleanLabel, riskLabel, settingsKeyLabel } from "../../../lib/labels";
import { getPolicySettings } from "../../tasks/api";

export function PolicySettingsPage() {
  const settings = useQuery({ queryKey: ["settings", "policies"], queryFn: getPolicySettings });

  return (
    <ConsoleShell title="策略设置">
      <div className="space-y-4 p-4">
        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <ShieldCheck className="h-4 w-4" /> 工具策略
            </div>
            <span className="text-xs text-slate-500">风险、审批、沙箱与审计规则</span>
          </CardHeader>
          <Table>
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <Th>风险等级</Th>
                <Th>沙箱</Th>
                <Th>审批</Th>
              </tr>
            </thead>
            <tbody>
              {(settings.data?.risk_levels ?? []).map((risk) => (
                <tr key={String(risk.name)} className="border-t border-slate-100">
                  <Td>
                    <Badge tone={statusTone(String(risk.name))}>{riskLabel(String(risk.name))}</Badge>
                  </Td>
                  <Td>{booleanLabel(risk.requires_sandbox)}</Td>
                  <Td>{approvalLabel(String(risk.approval))}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>
        <div className="grid grid-cols-3 gap-3">
          <PolicyCard title="审批" data={settings.data?.approvals} />
          <PolicyCard title="沙箱" data={settings.data?.sandbox} />
          <PolicyCard title="审计" data={settings.data?.audit} />
        </div>
      </div>
    </ConsoleShell>
  );
}

function PolicyCard({ title, data }: { title: string; data?: Record<string, unknown> }) {
  return (
    <Card>
      <CardHeader>
        <div className="text-[11px] tracking-widest text-slate-500">{title}</div>
      </CardHeader>
      <div className="space-y-1 p-3 text-xs">
        {Object.entries(data ?? {}).map(([key, value]) => (
          <div key={key} className="flex justify-between gap-3">
            <span className="text-slate-500">{settingsKeyLabel(key)}</span>
            <span className="font-mono text-slate-900">{booleanLabel(value)}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}
