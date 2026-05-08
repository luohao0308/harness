import { MarketingShell } from "./MarketingShell";
import Link from "next/link";
import {
  ListChecks,
  Workflow,
  GitBranch,
  Database,
  Activity,
  Box,
  Zap,
  ShieldCheck,
  FileSearch,
  Settings as SettingsIcon,
  ArrowRight,
} from "lucide-react";
import { siteLinks } from "./site-links";

export function Product({ onNav }: { onNav?: (k: string) => void }) {
  const sections = [
    {
      i: <ListChecks className="w-4 h-4" />,
      t: "任务生命周期",
      s: "完整的 create / list / detail / start / cancel / resume / result 流程，全部通过 FastAPI 暴露并在控制台中可视化。",
      tags: ["POST /api/tasks", "GET /api/tasks", "GET /api/tasks/{id}", "POST /api/tasks/{id}/start", "POST /api/tasks/{id}/cancel", "POST /api/tasks/{id}/resume", "GET /api/tasks/{id}/result"],
    },
    {
      i: <Workflow className="w-4 h-4" />,
      t: "执行架构",
      s: "Planner 负责拆解步骤，Executor 以 ReAct 循环驱动工具调用，Subagent 用于并发子任务。",
      tags: ["Planner", "Executor / ReAct", "Subagent", "max_concurrency=5"],
    },
    {
      i: <Database className="w-4 h-4" />,
      t: "事件与调试",
      s: "所有状态变化以事件形式追加写入 Event Store，控制台可订阅 SSE 实时流，并支持 Replay 重放。",
      tags: ["Event Sourcing", "SSE /api/tasks/{id}/events/stream", "Replay /api/tasks/{id}/replay"],
    },
    {
      i: <Box className="w-4 h-4" />,
      t: "安全运行",
      s: "工具调用全部下放到 Docker Sandbox，WarmPool 预热降低冷启动，策略设置控制网络与工具白名单。",
      tags: ["Docker Sandbox", "WarmPool", "策略设置"],
    },
    {
      i: <FileSearch className="w-4 h-4" />,
      t: "审计",
      s: "Model Call、Tool Call 与 ADMIN_ACTION 三类审计可独立查询，构成完整的合规链路。",
      tags: ["GET /api/tasks/{id}/model-calls", "GET /api/tasks/{id}/tool-calls", "ADMIN_ACTION rows"],
    },
    {
      i: <SettingsIcon className="w-4 h-4" />,
      t: "设置",
      s: "模型设置（默认 provider / 路由）与策略设置（沙箱、网络、工具白名单）可在控制台查询与更新，写入受 admin 限制。",
      tags: ["GET/PUT /api/settings/models", "GET/PUT /api/settings/policies"],
    },
  ];

  const matrix: Array<[string, string, string, string]> = [
    ["任务生命周期", "/api/tasks · /api/tasks/{id}/{start,cancel,resume,result}", "任务列表、任务详情", "标准化任务状态机，避免散落实现"],
    ["Planner", "内部模块（任务启动后触发）", "任务详情 · 执行计划面板", "把自然语言目标拆成可执行步骤"],
    ["Executor / ReAct", "内部模块（事件可见）", "任务详情 · 事件时间线", "可观测的工具调用循环"],
    ["Subagent", "GET /api/subagents · GET /api/subagents/{id} · GET /api/subagents/recovery/summary", "子 Agent 批量运营 · 子 Agent 详情 · 观测页", "并发子任务执行、批量状态筛选、结果产物查看与恢复运营"],
    ["Event Sourcing", "GET /api/tasks/{id}/events", "事件时间线", "全链路可追溯、可审计"],
    ["SSE 实时事件", "GET /api/tasks/{id}/events/stream", "事件时间线（实时）", "无需轮询的实时调试"],
    ["Replay", "POST /api/tasks/{id}/replay", "任务详情 · 重放面板", "故障复盘与状态重建"],
    ["Docker Sandbox", "GET /api/sandboxes · GET /api/sandboxes/{id} · POST /api/sandboxes/{id}/terminate", "Sandboxes 列表", "工具调用的隔离与终止"],
    ["WarmPool", "GET /api/sandboxes/warm-pool", "沙箱 · WarmPool 面板", "降低冷启动尾延迟"],
    ["Model Call 审计", "GET /api/tasks/{id}/model-calls", "任务详情 · 模型工具审计", "模型调用透明化"],
    ["Tool Call 审计", "GET /api/tasks/{id}/tool-calls", "任务详情 · 模型工具审计", "工具行为合规审查"],
    ["ADMIN_ACTION 审计", "Settings PUT 写入后台审计表", "Settings", "高风险变更全程留痕"],
    ["模型设置", "GET/PUT /api/settings/models", "Settings · Models", "统一模型路由配置"],
    ["策略设置", "GET/PUT /api/settings/policies", "Settings · Policies", "沙箱与工具策略集中管理"],
    ["OpenAPI", "GET /openapi.json · 网站 /openapi.yaml", "官网 · 文档", "可直接导入 Swagger / Apifox / Postman"],
    ["Prometheus 指标", "GET /metrics", "Observability", "标准化采集与告警"],
  ];

  return (
    <MarketingShell active="product" onNav={onNav}>
      <section className="border-b border-slate-200">
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 py-12">
          <div className="text-[12px] tracking-widest text-slate-500 mb-2">PRODUCT</div>
          <h1 className="text-[32px] sm:text-[40px] tracking-tight text-slate-900 mb-3">
            当前可用的 Agent Runtime 产品能力
          </h1>
          <p className="text-slate-600 text-[14px] max-w-2xl">
            以下能力均已在当前后端版本中实现并通过 FastAPI 暴露，控制台与 OpenAPI 提供完整入口。本页不展示任何尚未实现的功能。
          </p>
        </div>
      </section>

      <section className="border-b border-slate-200 bg-slate-50/40">
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 py-12">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {sections.map((c) => (
              <div key={c.t} className="bg-white border border-slate-200 rounded-lg p-5">
                <div className="flex items-center gap-2 mb-2 text-slate-700">
                  <span className="w-7 h-7 rounded bg-slate-100 flex items-center justify-center text-slate-600">
                    {c.i}
                  </span>
                  <div className="text-slate-900 text-[14px]">{c.t}</div>
                </div>
                <p className="text-[13px] text-slate-600 leading-relaxed mb-3">{c.s}</p>
                <div className="flex flex-wrap gap-1.5">
                  {c.tags.map((t) => (
                    <span
                      key={t}
                      className="px-1.5 py-0.5 rounded border border-slate-200 bg-slate-50 font-mono text-[11px] text-slate-600"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="border-b border-slate-200">
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 py-12">
          <div className="text-[12px] tracking-widest text-slate-500 mb-2">CAPABILITY MATRIX</div>
          <h2 className="text-slate-900 tracking-tight mb-6">能力 · 接口 · 入口 · 价值</h2>
          <div className="border border-slate-200 rounded-lg bg-white overflow-x-auto">
            <table className="w-full text-[12px] min-w-[760px]">
              <thead className="bg-slate-50 text-slate-500">
                <tr className="text-left">
                  <th className="font-normal px-3 py-2.5">产品能力</th>
                  <th className="font-normal px-3 py-2.5">现有接口</th>
                  <th className="font-normal px-3 py-2.5">控制台入口</th>
                  <th className="font-normal px-3 py-2.5">用户价值</th>
                </tr>
              </thead>
              <tbody>
                {matrix.map((r) => (
                  <tr key={r[0]} className="border-t border-slate-100 hover:bg-slate-50/40">
                    <td className="px-3 py-2.5 text-slate-900">{r[0]}</td>
                    <td className="px-3 py-2.5 font-mono text-[11px] text-slate-600">{r[1]}</td>
                    <td className="px-3 py-2.5 text-slate-600">{r[2]}</td>
                    <td className="px-3 py-2.5 text-slate-600">{r[3]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section>
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 py-12 flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-slate-900 text-[18px] tracking-tight">直接体验当前能力</div>
            <div className="text-[13px] text-slate-500">控制台中所有页面均基于上述接口构建。</div>
          </div>
          <div className="flex items-center gap-2">
            <Link href={siteLinks.console} className="bg-slate-900 text-white text-[13px] px-4 py-2.5 rounded hover:bg-slate-800 inline-flex items-center gap-2">
              进入控制台 <ArrowRight className="w-3.5 h-3.5" />
            </Link>
            <Link href={siteLinks.openapiJson} className="text-[13px] px-4 py-2.5 rounded border border-slate-200 hover:bg-slate-50">
              查看 OpenAPI
            </Link>
          </div>
        </div>
      </section>
    </MarketingShell>
  );
}
