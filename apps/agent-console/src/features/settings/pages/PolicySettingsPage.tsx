import { useQuery } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, statusTone } from "../../../components/ui/badge";
import { Card, CardHeader } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";
import { useI18n } from "../../../lib/i18n";
import { approvalLabel, booleanLabel, riskLabel, settingsKeyLabel } from "../../../lib/labels";
import { getPolicySettings } from "../../tasks/api";

export function PolicySettingsPage() {
  const { text } = useI18n();
  const settings = useQuery({ queryKey: ["settings", "policies"], queryFn: getPolicySettings });

  return (
    <ConsoleShell title={text("策略设置", "Policy Settings")}>
      <div className="space-y-4 p-4">
        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <ShieldCheck className="h-4 w-4" /> {text("工具策略", "Tool Policies")}
            </div>
            <span className="text-xs text-slate-500">{text("风险、审批、沙箱与审计规则", "Risk, approval, sandbox, and audit rules")}</span>
          </CardHeader>
          <Table>
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <Th>{text("风险等级", "Risk Level")}</Th>
                <Th>{text("沙箱", "Sandbox")}</Th>
                <Th>{text("审批", "Approval")}</Th>
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
          <PolicyCard title={text("审批", "Approval")} data={settings.data?.approvals} />
          <PolicyCard title={text("沙箱", "Sandbox")} data={settings.data?.sandbox} />
          <PolicyCard title={text("审计", "Audit")} data={settings.data?.audit} />
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
