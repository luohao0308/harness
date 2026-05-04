import { MarketingShell } from "./MarketingShell";
import { ArrowRight } from "lucide-react";

function Node({
  title,
  sub,
  tone = "default",
}: {
  title: string;
  sub?: string;
  tone?: "default" | "primary" | "muted" | "accent" | "warn";
}) {
  const tones: Record<string, string> = {
    default: "bg-white border-slate-200 text-slate-800",
    primary: "bg-slate-900 border-slate-900 text-white",
    muted: "bg-slate-50 border-slate-200 text-slate-700",
    accent: "bg-blue-50 border-blue-200 text-blue-900",
    warn: "bg-violet-50 border-violet-200 text-violet-900",
  };
  return (
    <div className={`rounded-md border px-3 py-2 ${tones[tone]}`}>
      <div className="text-[12px] tracking-tight">{title}</div>
      {sub && <div className="text-[10px] opacity-70 mt-0.5 font-mono">{sub}</div>}
    </div>
  );
}

export function MarketingArchitecture({ onNav }: { onNav?: (k: string) => void }) {
  return (
    <MarketingShell active="architecture" onNav={onNav}>
      <section className="border-b border-slate-200">
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 py-12">
          <div className="text-[12px] tracking-widest text-slate-500 mb-2">ARCHITECTURE</div>
          <h1 className="text-[32px] sm:text-[40px] tracking-tight text-slate-900 mb-3">
            当前系统架构
          </h1>
          <p className="text-slate-600 text-[14px] max-w-2xl">
            所有组件均已实装：FastAPI、Dramatiq Worker、PostgreSQL、Redis、Docker Sandbox、WarmPool、Prometheus、Grafana、Loki、Nginx，可通过 systemd 或 Docker Compose 部署。
          </p>
        </div>
      </section>

      <section className="border-b border-slate-200 bg-slate-50/40">
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 py-12 grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Diagram */}
          <div className="lg:col-span-9 bg-white border border-slate-200 rounded-lg p-5 overflow-x-auto">
            <div className="min-w-[820px]">
              <div className="text-[11px] tracking-widest text-slate-500 mb-4">
                USER → CONSOLE → API → RUNTIME
              </div>

              {/* Layer 1 - clients */}
              <div className="grid grid-cols-3 gap-3 mb-3">
                <Node title="User" sub="engineer / admin" tone="primary" />
                <Node title="Next.js 官网" sub="this site" tone="muted" />
                <Node title="React + Vite 控制台" sub="agent-console" tone="accent" />
              </div>
              <div className="flex justify-center text-slate-300 mb-3">
                <ArrowRight className="rotate-90 w-4 h-4" />
              </div>

              {/* Layer 2 - edge */}
              <div className="grid grid-cols-1 gap-3 mb-3">
                <Node title="Nginx" sub="reverse proxy · TLS" tone="muted" />
              </div>
              <div className="flex justify-center text-slate-300 mb-3">
                <ArrowRight className="rotate-90 w-4 h-4" />
              </div>

              {/* Layer 3 - api */}
              <div className="grid grid-cols-1 gap-3 mb-3">
                <Node title="FastAPI API Server" sub="bearer auth · OpenAPI" tone="primary" />
              </div>
              <div className="flex justify-center text-slate-300 mb-3">
                <ArrowRight className="rotate-90 w-4 h-4" />
              </div>

              {/* Layer 4 - services */}
              <div className="grid grid-cols-3 gap-3 mb-3">
                <Node title="Task Service" sub="lifecycle · result" />
                <Node title="Planner" sub="step decomposition" />
                <Node title="Executor / ReAct" sub="tool driver" />
              </div>
              <div className="flex justify-center text-slate-300 mb-3">
                <ArrowRight className="rotate-90 w-4 h-4" />
              </div>

              {/* Layer 5 - tools/runtime */}
              <div className="grid grid-cols-3 gap-3 mb-3">
                <Node title="Tool Registry" sub="risk_level · sandboxed" />
                <Node title="Docker Sandbox" sub="isolated · no-net default" tone="warn" />
                <Node title="WarmPool" sub="< 50ms acquire" tone="accent" />
              </div>
              <div className="flex justify-center text-slate-300 mb-3">
                <ArrowRight className="rotate-90 w-4 h-4" />
              </div>

              {/* Layer 6 - storage / observability */}
              <div className="grid grid-cols-4 gap-3">
                <Node title="Event Store" sub="append-only" tone="primary" />
                <Node title="Result / Replay" sub="state rebuild" />
                <Node title="Audit (Model/Tool/Admin)" sub="auditable trail" />
                <Node title="Dramatiq Worker" sub="agent-worker · sandbox-worker" tone="muted" />
              </div>

              {/* Backing systems */}
              <div className="mt-6 pt-4 border-t border-slate-100">
                <div className="text-[11px] tracking-widest text-slate-500 mb-3">BACKING SYSTEMS</div>
                <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
                  <Node title="PostgreSQL 16" sub="durable state" tone="muted" />
                  <Node title="Redis 7" sub="queue · cache" tone="muted" />
                  <Node title="Prometheus" sub="/metrics" tone="muted" />
                  <Node title="Grafana" sub="dashboards" tone="muted" />
                  <Node title="Loki" sub="logs" tone="muted" />
                  <Node title="systemd / Compose" sub="orchestration" tone="muted" />
                </div>
              </div>
            </div>
          </div>

          {/* Right: invariants */}
          <div className="lg:col-span-3 space-y-3">
            <div className="bg-white border border-slate-200 rounded-lg p-4">
              <div className="text-[11px] tracking-widest text-slate-500 mb-3">RUNTIME 关键指标</div>
              <ul className="text-[12px] space-y-2">
                {[
                  ["Subagent 并发上限", "5"],
                  ["WarmPool 目标延迟", "< 50ms"],
                  ["Event Store", "append-only"],
                  ["Sandbox 默认网络", "禁用"],
                  ["OpenAPI", "JSON / YAML 可导入"],
                  ["Prometheus", "/metrics 已暴露"],
                ].map(([k, v]) => (
                  <li key={k} className="flex justify-between">
                    <span className="text-slate-500">{k}</span>
                    <span className="text-slate-900 font-mono">{v}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="bg-white border border-slate-200 rounded-lg p-4">
              <div className="text-[11px] tracking-widest text-slate-500 mb-3">数据流</div>
              <ol className="text-[12px] text-slate-600 space-y-1 list-decimal pl-4 leading-relaxed">
                <li>用户在控制台或 API 创建任务</li>
                <li>FastAPI 写入 PostgreSQL，并入 Dramatiq 队列</li>
                <li>Worker 触发 Planner，Executor 调度工具</li>
                <li>工具调用进入 Sandbox（WarmPool 命中优先）</li>
                <li>所有事件 append 至 Event Store</li>
                <li>Result / Replay / Audit 三类视图独立查询</li>
              </ol>
            </div>

            <div className="bg-slate-900 text-slate-200 rounded-lg p-4">
              <div className="text-[11px] tracking-widest text-slate-400 mb-2">部署形态</div>
              <div className="font-mono text-[11px] space-y-1">
                <div>· Docker Compose（本地评估）</div>
                <div>· systemd（生产托管）</div>
                <div>· VPC / 物理机 / 混合云</div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </MarketingShell>
  );
}
