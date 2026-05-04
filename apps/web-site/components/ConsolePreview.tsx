import { Badge, Dot } from "./shared";
import { Activity, Box, GitBranch, Cpu } from "lucide-react";

export function ConsolePreview() {
  return (
    <div className="rounded-lg border border-slate-200 bg-white shadow-2xl shadow-slate-900/10 overflow-hidden font-mono text-[12px]">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-200 bg-slate-50">
        <div className="flex gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-red-400" />
          <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
        </div>
        <div className="ml-3 px-2 py-0.5 rounded bg-white border border-slate-200 text-slate-500 text-[11px]">
          console.harness.enterprise / tasks / task_8f21
        </div>
        <div className="ml-auto flex items-center gap-2 text-[11px] text-slate-500">
          <Dot tone="success" /> api healthy
        </div>
      </div>

      <div className="grid grid-cols-12 gap-0">
        <div className="col-span-5 border-r border-slate-100 p-3">
          <div className="flex items-center justify-between mb-2">
            <div className="text-slate-500 text-[11px] tracking-wide">EXECUTION PLAN</div>
            <Badge tone="running">RUNNING</Badge>
          </div>
          <div className="space-y-1.5">
            {[
              ["1", "inspect_project", "COMPLETED", "success"],
              ["2", "read_test_config", "COMPLETED", "success"],
              ["3", "run_tests", "RUNNING", "running"],
              ["4", "dependency_review", "WAITING", "warning"],
              ["5", "produce_report", "PENDING", "pending"],
            ].map(([n, name, st, tone]) => (
              <div
                key={n}
                className="flex items-center gap-2 px-2 py-1.5 rounded bg-slate-50/60 border border-slate-100"
              >
                <span className="text-slate-400 w-4">{n}</span>
                <span className="text-slate-700 flex-1 truncate">{name}</span>
                <Dot tone={tone as string} />
                <span className="text-slate-500 text-[10px]">{st}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="col-span-4 border-r border-slate-100 p-3">
          <div className="flex items-center justify-between mb-2">
            <div className="text-slate-500 text-[11px] tracking-wide flex items-center gap-1.5">
              <Activity className="w-3 h-3" /> EVENT STREAM
            </div>
            <span className="text-[10px] text-slate-400">seq 0142</span>
          </div>
          <div className="space-y-1 text-[11px]">
            {[
              ["0138", "TASK_STARTED", "info"],
              ["0139", "PLAN_GENERATED", "info"],
              ["0140", "STEP_STARTED", "running"],
              ["0141", "SANDBOX_ALLOCATED", "purple"],
              ["0142", "TOOL_CALLED", "running"],
            ].map(([seq, ev, tone]) => (
              <div key={seq} className="flex items-center gap-2 py-0.5">
                <span className="text-slate-300 w-9">{seq}</span>
                <Dot tone={tone as string} />
                <span className="text-slate-700">{ev}</span>
              </div>
            ))}
          </div>

          <div className="mt-3 pt-3 border-t border-slate-100">
            <div className="text-slate-500 text-[11px] tracking-wide mb-1.5 flex items-center gap-1.5">
              <GitBranch className="w-3 h-3" /> SUBAGENTS
            </div>
            <div className="space-y-1">
              <div className="flex justify-between text-[11px]">
                <span className="text-slate-700">subagent-1</span>
                <Badge tone="running">RUN</Badge>
              </div>
              <div className="flex justify-between text-[11px]">
                <span className="text-slate-700">subagent-2</span>
                <Badge tone="success">OK</Badge>
              </div>
              <div className="flex justify-between text-[11px]">
                <span className="text-slate-700">subagent-3</span>
                <Badge tone="pending">PEND</Badge>
              </div>
            </div>
          </div>
        </div>

        <div className="col-span-3 p-3">
          <div className="text-slate-500 text-[11px] tracking-wide mb-2 flex items-center gap-1.5">
            <Box className="w-3 h-3" /> SANDBOX
          </div>
          <div className="rounded border border-slate-200 p-2 mb-2">
            <div className="text-slate-700 text-[11px]">sbx_a91f</div>
            <div className="text-slate-400 text-[10px]">harness/python:3.11</div>
            <div className="flex justify-between mt-1.5 text-[10px]">
              <span className="text-slate-500">cpu</span>
              <span className="text-slate-700">42%</span>
            </div>
            <div className="flex justify-between text-[10px]">
              <span className="text-slate-500">mem</span>
              <span className="text-slate-700">312 MB</span>
            </div>
            <div className="flex justify-between text-[10px]">
              <span className="text-slate-500">net</span>
              <span className="text-red-500">disabled</span>
            </div>
          </div>
          <div className="text-slate-500 text-[11px] tracking-wide mb-1 flex items-center gap-1.5">
            <Cpu className="w-3 h-3" /> WARMPOOL
          </div>
          <div className="text-[11px] text-slate-700">acquire 38ms</div>
          <div className="text-[10px] text-emerald-600">hit rate 94.2%</div>
        </div>
      </div>
    </div>
  );
}
