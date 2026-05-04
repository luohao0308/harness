import { Box } from "lucide-react";

import { Card, CardHeader } from "../../../components/ui/card";

export function SandboxPanel({ enabled = false }: { enabled?: boolean }) {
  return (
    <Card>
      <CardHeader>
        <div className="inline-flex items-center gap-1.5 text-[11px] tracking-widest text-slate-500">
          <Box className="h-3 w-3" /> 沙箱
        </div>
      </CardHeader>
      <div className="space-y-1 p-3 text-[11px]">
        <div className="flex justify-between">
          <span className="text-slate-500">状态</span>
          <span className={enabled ? "text-emerald-600" : "text-slate-400"}>
            {enabled ? "已请求" : "已关闭"}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-500">镜像</span>
          <span className="font-mono text-slate-800">harness/python:3.11</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-500">网络</span>
          <span className="text-red-600">默认关闭</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-500">WarmPool</span>
          <span className="font-mono text-slate-800">目标 50ms</span>
        </div>
      </div>
    </Card>
  );
}
