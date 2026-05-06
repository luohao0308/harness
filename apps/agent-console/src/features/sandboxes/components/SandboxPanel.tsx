import { Box } from "lucide-react";

import { Card, CardHeader } from "../../../components/ui/card";
import { useI18n } from "../../../lib/i18n";

export function SandboxPanel({ enabled = false }: { enabled?: boolean }) {
  const { text } = useI18n();
  return (
    <Card>
      <CardHeader>
        <div className="inline-flex items-center gap-1.5 text-[11px] tracking-widest text-slate-500">
          <Box className="h-3 w-3" /> {text("沙箱", "Sandbox")}
        </div>
      </CardHeader>
      <div className="space-y-1 p-3 text-[11px]">
        <div className="flex justify-between">
          <span className="text-slate-500">{text("状态", "Status")}</span>
          <span className={enabled ? "text-emerald-600" : "text-slate-400"}>
            {enabled ? text("已请求", "Requested") : text("已关闭", "Disabled")}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-500">{text("镜像", "Image")}</span>
          <span className="font-mono text-slate-800">harness/python:3.11</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-500">{text("网络", "Network")}</span>
          <span className="text-red-600">{text("默认关闭", "Off by default")}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-500">WarmPool</span>
          <span className="font-mono text-slate-800">{text("目标 50ms", "target 50ms")}</span>
        </div>
      </div>
    </Card>
  );
}
