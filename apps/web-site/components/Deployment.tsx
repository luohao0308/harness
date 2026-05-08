import { MarketingShell } from "./MarketingShell";
import { Server, Activity, Database } from "lucide-react";

export function Deployment({ onNav }: { onNav?: (k: string) => void }) {
  const services: Array<[string, string, string, string]> = [
    ["web-site", "Next.js 官网，承载产品、文档与 OpenAPI 入口", "3000", "active"],
    ["agent-console", "React + Vite 控制台静态资源", "5173", "active"],
    ["api-server", "FastAPI 主服务，承载 OpenAPI 与 SSE", "8000", "active"],
    ["agent-worker", "Dramatiq 任务执行 Worker", "—", "active"],
    ["sandbox-worker", "驱动 Docker Sandbox 生命周期", "—", "active"],
    ["warm-pool", "预热容器池服务", "—", "active"],
    ["postgres", "PostgreSQL 16 持久化存储", "5432", "active"],
    ["redis", "Redis 7 队列与缓存", "6379", "active"],
    ["nginx", "反向代理与 TLS 终结", "8080", "active"],
    ["prometheus", "指标采集", "9090", "active"],
    ["grafana", "运行时仪表盘", "3001", "active"],
    ["loki", "结构化日志聚合", "3100", "active"],
    ["otel-collector", "OpenTelemetry 接收转发", "4317", "active"],
    ["tempo", "真实 Trace 存储与查询", "3200", "active"],
  ];

  return (
    <MarketingShell active="deployment" onNav={onNav}>
      <section className="border-b border-slate-200">
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 py-12">
          <div className="text-[12px] tracking-widest text-slate-500 mb-2">DEPLOYMENT</div>
          <h1 className="text-[32px] sm:text-[40px] tracking-tight text-slate-900 mb-3">
            当前可落地的本地与生产部署
          </h1>
          <p className="text-slate-600 text-[14px] max-w-2xl">
            提供开箱即用的 Docker Compose 拓扑用于本地评估，以及 systemd 托管方向用于生产部署。所有依赖均为开源、可审计、可替换。
          </p>
        </div>
      </section>

      <section className="border-b border-slate-200 bg-slate-50/40">
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 py-12 grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-7 bg-white border border-slate-200 rounded-lg overflow-hidden">
            <div className="px-3 py-2 border-b border-slate-100 flex items-center justify-between">
              <div className="text-[11px] tracking-widest text-slate-500 inline-flex items-center gap-1.5">
                <Server className="w-3 h-3" /> COMPOSE 服务状态
              </div>
              <span className="text-[10px] font-mono text-slate-400">13 services</span>
            </div>
            <table className="w-full text-[12px]">
              <thead className="bg-slate-50/60 text-slate-500">
                <tr className="text-left">
                  <th className="font-normal px-3 py-2">服务</th>
                  <th className="font-normal px-3 py-2">说明</th>
                  <th className="font-normal px-3 py-2">端口</th>
                  <th className="font-normal px-3 py-2">状态</th>
                </tr>
              </thead>
              <tbody>
                {services.map((s) => (
                  <tr key={s[0]} className="border-t border-slate-100">
                    <td className="px-3 py-2 font-mono text-slate-800">{s[0]}</td>
                    <td className="px-3 py-2 text-slate-600">{s[1]}</td>
                    <td className="px-3 py-2 font-mono text-[11px] text-slate-600">{s[2]}</td>
                    <td className="px-3 py-2">
                      <span className="inline-flex items-center gap-1.5 text-emerald-700">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> {s[3]}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="lg:col-span-5 space-y-3">
            <div className="bg-slate-900 text-slate-200 rounded-lg p-4 font-mono text-[12px] leading-relaxed">
              <div className="text-slate-400"># 1. 本地评估（Docker Compose）</div>
              <div>$ docker compose up -d</div>
              <div className="text-slate-500">› starting api-server, agent-worker, postgres...</div>
              <div className="text-emerald-400">› 12 services healthy</div>
              <div className="mt-3 text-slate-400"># 2. 数据库迁移</div>
              <div>$ alembic upgrade head</div>
              <div className="mt-3 text-slate-400"># 3. 健康检查</div>
              <div>$ curl :8080/health</div>
              <div>$ curl :8080/metrics | head</div>
              <div>$ open http://127.0.0.1:3000</div>
              <div>$ open http://127.0.0.1:5173/tasks</div>
              <div className="mt-3 text-slate-400"># 4. 生产托管（systemd）</div>
              <div>$ systemctl status harness-api</div>
              <div>$ systemctl status harness-worker</div>
            </div>

            <div className="bg-white border border-slate-200 rounded-lg p-4">
              <div className="text-[11px] tracking-widest text-slate-500 mb-3 inline-flex items-center gap-1.5">
                <Activity className="w-3 h-3" /> 监控链路
              </div>
              <ul className="text-[12px] text-slate-600 space-y-1.5">
                <li>· Prometheus 抓取 <span className="font-mono">/metrics</span></li>
                <li>· Grafana 加载默认仪表盘</li>
                <li>· Loki 接收 api / worker 日志</li>
                <li>· otel-collector 统一上行链路</li>
                <li>· Tempo 存储真实 Trace span</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      <section className="border-b border-slate-200">
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 py-12 grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="bg-white border border-slate-200 rounded-lg p-5">
            <div className="text-[11px] tracking-widest text-slate-500 mb-2 inline-flex items-center gap-1.5">
              <Database className="w-3 h-3" /> 数据库迁移
            </div>
            <div className="text-[13px] text-slate-900 mb-1">Alembic upgrade head</div>
            <p className="text-[12px] text-slate-600 leading-relaxed">
              所有 schema 变更通过 Alembic 管理，迁移与回滚均有对应脚本和文档。
            </p>
          </div>
          <div className="bg-white border border-slate-200 rounded-lg p-5">
            <div className="text-[11px] tracking-widest text-slate-500 mb-2">健康检查</div>
            <ul className="text-[12px] text-slate-700 space-y-1 font-mono">
              <li>GET /health</li>
              <li>GET /metrics</li>
              <li>控制台 /tasks 页面可达</li>
            </ul>
          </div>
          <div className="bg-white border border-slate-200 rounded-lg p-5">
            <div className="text-[11px] tracking-widest text-slate-500 mb-2">环境变量</div>
            <ul className="text-[12px] text-slate-700 space-y-1 font-mono">
              <li>API_BASE_URL</li>
              <li>CONSOLE_BASE_URL</li>
              <li>DATABASE_URL</li>
              <li>REDIS_URL</li>
              <li>DOCKER_HOST</li>
            </ul>
          </div>
        </div>
      </section>
    </MarketingShell>
  );
}
