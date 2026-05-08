import {
  ArrowRight,
  FileJson,
  Workflow,
  Play,
  Database,
  Activity,
  GitBranch,
  Box,
  Zap,
  FileSearch,
  Settings as SettingsIcon,
  ListChecks,
  Brain,
  Wrench,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { MarketingShell } from "./MarketingShell";
import { ConsolePreview } from "./ConsolePreview";
import { consolePath, siteLinks } from "./site-links";

export function Homepage({ onNav }: { onNav?: (k: string) => void }) {
  return (
    <MarketingShell active="home" onNav={onNav}>
      {/* Hero */}
      <section className="border-b border-slate-200">
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 pt-12 sm:pt-16 pb-12">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
            <div className="lg:col-span-6">
              <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full border border-slate-200 bg-white text-[12px] text-slate-600 mb-5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                v1.4 · 当前已实现的能力均可运行、可验证、可部署
              </div>
              <h1 className="text-[36px] sm:text-[44px] leading-[1.1] tracking-tight text-slate-900 mb-4">
                生产级企业 AI Agent
                <br />
                Harness 平台
              </h1>
              <p className="text-slate-600 text-[15px] leading-[1.6] max-w-xl mb-7">
                将大模型能力工程化为具备 任务生命周期、事件溯源、Replay、Subagent 编排、Docker
                Sandbox 与审计的执行系统。Model 提供推理，Harness 提供可靠性。
              </p>
              <div className="flex flex-wrap items-center gap-3">
                <Link href={siteLinks.console} className="bg-slate-900 text-white text-[13px] px-4 py-2.5 rounded hover:bg-slate-800 inline-flex items-center gap-2">
                  进入控制台 <ArrowRight className="w-3.5 h-3.5" />
                </Link>
                <Link href={siteLinks.openapiJson} className="text-[13px] px-4 py-2.5 rounded border border-slate-200 hover:bg-slate-50 text-slate-700 inline-flex items-center gap-2">
                  <FileJson className="w-3.5 h-3.5" /> 查看 OpenAPI
                </Link>
              </div>
              <div className="grid grid-cols-3 gap-6 mt-10 pt-6 border-t border-slate-100 max-w-lg">
                <div>
                  <div className="text-slate-900 tracking-tight">{"<50ms"}</div>
                  <div className="text-[12px] text-slate-500 mt-0.5">WarmPool 目标延迟</div>
                </div>
                <div>
                  <div className="text-slate-900 tracking-tight">5</div>
                  <div className="text-[12px] text-slate-500 mt-0.5">Subagent 并发上限</div>
                </div>
                <div>
                  <div className="text-slate-900 tracking-tight">append-only</div>
                  <div className="text-[12px] text-slate-500 mt-0.5">Event Store 模型</div>
                </div>
              </div>
            </div>
            <div className="lg:col-span-6">
              <ConsolePreview />
            </div>
          </div>
        </div>
      </section>

      {/* Formula */}
      <section className="border-b border-slate-200">
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 py-14">
          <div className="text-[12px] tracking-widest text-slate-500 mb-2">CORE PRINCIPLE</div>
          <div className="text-[26px] sm:text-[28px] tracking-tight text-slate-900 mb-8">
            Model <span className="text-slate-400">+</span> Harness{" "}
            <span className="text-slate-400">=</span> Agent
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-px bg-slate-200 border border-slate-200 rounded-lg overflow-hidden">
            {[
              {
                t: "Model",
                d: "理解 · 推理 · 生成",
                s: "LLM 提供语言与推理能力，但不保证可靠性、隔离性和可恢复性。",
              },
              {
                t: "Harness",
                d: "Planner · Executor · Subagent · Event Store · Sandbox · WarmPool",
                s: "工程化 runtime：所有事件可审计、可重放，所有工具调用可隔离、可取消。",
              },
              {
                t: "Agent",
                d: "可运行 · 可观测 · 可交付",
                s: "通过控制台与 OpenAPI 暴露完整任务生命周期，支持私有化部署。",
              },
            ].map((c) => (
              <div key={c.t} className="bg-white p-6">
                <div className="text-slate-900 tracking-tight mb-1">{c.t}</div>
                <div className="text-[12px] text-slate-500 mb-3">{c.d}</div>
                <div className="text-[13px] text-slate-600 leading-relaxed">{c.s}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Lifecycle */}
      <section className="border-b border-slate-200 bg-slate-50/50">
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 py-14">
          <div className="text-[12px] tracking-widest text-slate-500 mb-2">LIFECYCLE</div>
          <h2 className="text-slate-900 tracking-tight mb-2">当前已实现的任务执行闭环</h2>
          <p className="text-[13px] text-slate-600 mb-8 max-w-2xl">
            从创建到调试，全部基于 FastAPI 后端、Event Sourcing 与 Replay 实现。每一步都有对应接口与控制台入口。
          </p>
          <div className="overflow-x-auto">
            <div className="flex items-stretch gap-2 min-w-[900px]">
              {[
                ["创建任务", "POST /api/tasks", "工程师在控制台或 API 创建"],
                ["启动任务", "POST /api/tasks/{id}/start", "进入 Planner 阶段"],
                ["Planner 生成计划", "planner", "拆解为带依赖的步骤"],
                ["Executor 执行", "executor / ReAct", "驱动工具与 Subagent"],
                ["Event Store 写入", "append-only", "全部事件入库"],
                ["Result 输出", "GET /api/tasks/{id}/result", "结构化结果与产物"],
                ["Replay 调试", "POST /api/tasks/{id}/replay", "任意时刻重建状态"],
              ].map((s, i, arr) => (
                <div key={i} className="flex items-stretch gap-2">
                  <div className="bg-white border border-slate-200 rounded-lg p-3 w-[140px]">
                    <div className="text-[11px] tracking-widest text-slate-400 mb-1">
                      0{i + 1}
                    </div>
                    <div className="text-[13px] text-slate-900 mb-1">{s[0]}</div>
                    <div className="text-[10px] font-mono text-slate-500 mb-1">{s[1]}</div>
                    <div className="text-[11px] text-slate-500 leading-snug">{s[2]}</div>
                  </div>
                  {i < arr.length - 1 && (
                    <div className="flex items-center text-slate-300">
                      <ArrowRight className="w-4 h-4" />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Capability cards */}
      <section className="border-b border-slate-200">
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 py-14">
          <div className="text-[12px] tracking-widest text-slate-500 mb-2">CAPABILITIES</div>
          <h2 className="text-slate-900 tracking-tight mb-8">十大已实现核心能力</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-px bg-slate-200 border border-slate-200 rounded-lg overflow-hidden">
            {[
              { i: <ListChecks className="w-4 h-4" />, t: "任务生命周期", s: "创建 / 启动 / 取消 / 恢复 / 详情 / 列表" },
              { i: <Database className="w-4 h-4" />, t: "事件溯源", s: "append-only 事件存储，可审计可重建" },
              { i: <Play className="w-4 h-4" />, t: "Replay 调试", s: "任意时刻重放任务状态，便于调试" },
              { i: <GitBranch className="w-4 h-4" />, t: "Subagent 编排", s: "并发上限 5，可查询、可取消、可看结果产物" },
              { i: <Box className="w-4 h-4" />, t: "Docker 沙箱", s: "查询、详情、终止，默认禁网" },
              { i: <Zap className="w-4 h-4" />, t: "WarmPool 预热池", s: "状态查询，目标 < 50ms 启动" },
              { i: <FileSearch className="w-4 h-4" />, t: "模型与工具审计", s: "Model Call、Tool Call 审计查询" },
              { i: <SettingsIcon className="w-4 h-4" />, t: "运行设置", s: "模型设置、策略设置查询/更新" },
              { i: <Activity className="w-4 h-4" />, t: "观测与运营", s: "Prometheus /metrics、SSE 实时事件" },
              { i: <FileJson className="w-4 h-4" />, t: "OpenAPI", s: "JSON / YAML 可导入 Swagger / Apifox" },
            ].map((c) => (
              <div key={c.t} className="bg-white p-5">
                <div className="flex items-center gap-2 mb-2 text-slate-700">
                  <span className="w-7 h-7 rounded bg-slate-100 flex items-center justify-center text-slate-600">
                    {c.i}
                  </span>
                  <div className="text-slate-900 text-[13px]">{c.t}</div>
                </div>
                <p className="text-[12px] text-slate-600 leading-relaxed">{c.s}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Console preview surface */}
      <section className="border-b border-slate-200 bg-slate-50/50">
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 py-14">
          <div className="text-[12px] tracking-widest text-slate-500 mb-2">CONSOLE</div>
          <h2 className="text-slate-900 tracking-tight mb-2">控制台已上线的页面</h2>
          <p className="text-[13px] text-slate-600 mb-8 max-w-2xl">
            官网仅介绍能力，所有任务执行均在控制台中完成。下列为当前已实现的控制台页面入口。
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2">
            {[
              ["任务列表", <ListChecks className="w-4 h-4" />, consolePath("/tasks")],
              ["创建任务", <Workflow className="w-4 h-4" />, consolePath("/tasks/new")],
              ["子 Agent", <GitBranch className="w-4 h-4" />, consolePath("/subagents")],
              ["沙箱治理", <Box className="w-4 h-4" />, consolePath("/sandboxes")],
              ["观测运营", <Activity className="w-4 h-4" />, consolePath("/observability")],
              ["策略设置", <ShieldCheck className="w-4 h-4" />, consolePath("/settings/policies")],
              ["模型设置", <Brain className="w-4 h-4" />, consolePath("/settings/models")],
            ].map(([t, ic, href]) => (
              <Link
                key={t as string}
                href={href as string}
                className="bg-white border border-slate-200 rounded-lg p-3 hover:border-slate-300 transition-colors"
              >
                <div className="w-7 h-7 rounded bg-slate-100 flex items-center justify-center text-slate-600 mb-2">
                  {ic as any}
                </div>
                <div className="text-[12px] text-slate-900">{t as string}</div>
                <div className="text-[10px] text-slate-500 mt-0.5">已上线</div>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section>
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 py-14 text-center">
          <h2 className="text-[24px] sm:text-[28px] tracking-tight text-slate-900 mb-3">
            构建可审计、可恢复、可隔离的企业 Agent 系统
          </h2>
          <p className="text-[14px] text-slate-600 mb-6 max-w-xl mx-auto">
            当前版本所有功能均已实现并可在私有化环境中运行。直接进入控制台，或通过 OpenAPI 集成。
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <Link href={siteLinks.console} className="bg-slate-900 text-white text-[13px] px-4 py-2.5 rounded hover:bg-slate-800 inline-flex items-center gap-2">
              进入控制台 <ArrowRight className="w-3.5 h-3.5" />
            </Link>
            <Link href={siteLinks.openapiJson} className="text-[13px] px-4 py-2.5 rounded border border-slate-200 hover:bg-slate-50 inline-flex items-center gap-2">
              <FileJson className="w-3.5 h-3.5" /> 查看 OpenAPI
            </Link>
            <Link
              href="/contact"
              className="text-[13px] px-4 py-2.5 rounded border border-slate-200 hover:bg-slate-50 inline-flex items-center gap-2"
            >
              <ShieldCheck className="w-3.5 h-3.5" /> 申请企业接入
            </Link>
          </div>
        </div>
      </section>
    </MarketingShell>
  );
}
