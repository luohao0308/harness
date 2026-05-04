import Link from "next/link";
import {
  Activity,
  ArrowRight,
  Box,
  Code2,
  Database,
  FileSearch,
  GitBranch,
  ShieldCheck,
  Terminal,
} from "lucide-react";

import { MarketingShell } from "./MarketingShell";
import { siteLinks } from "./site-links";

const scenarios = [
  {
    icon: <Code2 className="h-4 w-4" />,
    title: "代码工程自动化",
    problem: "代码审查、迁移、批量修复和 CI 失败分析需要可追踪的执行链路。",
    flow: "创建任务 -> Planner 拆解 -> Executor 调用工具 -> Result 输出报告。",
    components: ["Task Lifecycle", "Planner", "Executor", "Tool Call Audit"],
    output: "审查报告、修复步骤、事件流和工具调用记录。",
  },
  {
    icon: <Activity className="h-4 w-4" />,
    title: "DevOps 故障诊断",
    problem: "日志、指标和事件分散，定位过程缺少可复盘记录。",
    flow: "任务启动 -> 事件流订阅 -> Sandbox 工具执行 -> Replay 复盘。",
    components: ["Event Sourcing", "Replay", "Observability", "Docker Sandbox"],
    output: "故障点、诊断摘要、事件序号和任务结果。",
  },
  {
    icon: <Terminal className="h-4 w-4" />,
    title: "SRE 运维助手",
    problem: "Runbook 操作需要隔离执行、超时保护和明确审计。",
    flow: "策略检查 -> 工具调用 -> 沙箱执行 -> 审计记录。",
    components: ["Policy", "Tool Registry", "Sandbox", "Tool Call Audit"],
    output: "执行摘要、沙箱记录、工具输入输出和事件链。",
  },
  {
    icon: <ShieldCheck className="h-4 w-4" />,
    title: "安全审计与合规证据",
    problem: "模型调用、工具调用和管理动作需要独立留痕。",
    flow: "Settings 管理 -> ADMIN_ACTION -> Model/Tool Audit -> 导出证据。",
    components: ["ADMIN_ACTION", "Model Call Audit", "Tool Call Audit", "Event Store"],
    output: "审计清单、策略记录、模型工具调用详情。",
  },
  {
    icon: <Database className="h-4 w-4" />,
    title: "数据处理 Agent",
    problem: "数据质量检查和报表生成需要长流程任务状态可见。",
    flow: "任务创建 -> Subagent 并发 -> Result 汇总 -> Observability 查看。",
    components: ["Subagent", "Task Result", "Event Sourcing", "Observability"],
    output: "处理摘要、子任务状态、产物和运行指标。",
  },
  {
    icon: <FileSearch className="h-4 w-4" />,
    title: "内部知识任务流",
    problem: "文档分析、跨系统检索和报告生成需要受控工具执行。",
    flow: "Planner 拆解 -> read/list 工具 -> 事件记录 -> 结果产物。",
    components: ["Planner", "Tool Registry", "Event Store", "Task Result"],
    output: "知识摘要、引用记录、任务事件和最终报告。",
  },
];

const matrix = [
  ["代码工程自动化", "✓", "—", "✓", "✓", "模型/工具审计"],
  ["DevOps 故障诊断", "✓", "—", "✓", "✓", "Prometheus / Replay"],
  ["SRE 运维助手", "✓", "—", "✓", "✓", "工具审计"],
  ["安全审计与合规证据", "—", "—", "✓", "✓", "ADMIN_ACTION"],
  ["数据处理 Agent", "✓", "✓", "按任务策略", "✓", "任务结果"],
  ["内部知识任务流", "✓", "—", "按工具策略", "✓", "事件流"],
];

export function Solutions({ onNav }: { onNav?: (k: string) => void }) {
  return (
    <MarketingShell active="solutions" onNav={onNav}>
      <section className="border-b border-slate-200">
        <div className="mx-auto max-w-[1320px] px-4 py-12 sm:px-8">
          <div className="mb-2 text-[12px] tracking-widest text-slate-500">SOLUTIONS</div>
          <h1 className="mb-3 text-[32px] tracking-tight text-slate-900 sm:text-[40px]">
            基于当前运行时能力的企业场景
          </h1>
          <p className="max-w-2xl text-[14px] leading-relaxed text-slate-600">
            这些方案全部建立在已实现的任务、事件、Replay、Subagent、Sandbox、审计和观测能力上，不展示未落地的插件市场、计费或团队管理功能。
          </p>
        </div>
      </section>

      <section className="border-b border-slate-200 bg-slate-50/40">
        <div className="mx-auto grid max-w-[1320px] grid-cols-1 gap-3 px-4 py-12 sm:px-8 lg:grid-cols-3">
          {scenarios.map((item) => (
            <article key={item.title} className="rounded-lg border border-slate-200 bg-white p-5">
              <div className="mb-3 flex items-center gap-2 text-slate-700">
                <span className="flex h-8 w-8 items-center justify-center rounded bg-slate-100 text-slate-600">
                  {item.icon}
                </span>
                <h2 className="text-[15px] tracking-tight text-slate-900">{item.title}</h2>
              </div>
              <div className="space-y-3 text-[12px] leading-relaxed">
                <Block label="业务问题" text={item.problem} />
                <Block label="Agent 执行流程" text={item.flow} />
                <div>
                  <div className="mb-1 text-slate-500">涉及组件</div>
                  <div className="flex flex-wrap gap-1.5">
                    {item.components.map((component) => (
                      <span
                        key={component}
                        className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-[10px] text-slate-600"
                      >
                        {component}
                      </span>
                    ))}
                  </div>
                </div>
                <Block label="产物输出" text={item.output} />
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="border-b border-slate-200">
        <div className="mx-auto max-w-[1320px] px-4 py-12 sm:px-8">
          <div className="mb-2 text-[12px] tracking-widest text-slate-500">MAPPING</div>
          <h2 className="mb-6 tracking-tight text-slate-900">场景到 Harness 能力映射</h2>
          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="w-full min-w-[760px] text-[12px]">
              <thead className="bg-slate-50 text-left text-slate-500">
                <tr>
                  {["场景", "Planner", "Subagent", "Sandbox", "Event Store", "Observability"].map((header) => (
                    <th key={header} className="px-3 py-2.5 font-normal">{header}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {matrix.map((row) => (
                  <tr key={row[0]} className="border-t border-slate-100">
                    <td className="px-3 py-2.5 text-slate-900">{row[0]}</td>
                    {row.slice(1).map((cell, index) => (
                      <td key={`${row[0]}-${index}`} className="px-3 py-2.5 text-slate-600">
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section>
        <div className="mx-auto flex max-w-[1320px] flex-wrap items-center justify-between gap-4 px-4 py-12 sm:px-8">
          <div>
            <div className="text-[18px] tracking-tight text-slate-900">从一个可验证场景开始</div>
            <p className="mt-1 text-[13px] text-slate-500">创建任务后即可看到计划、事件、结果、审计与 Replay。</p>
          </div>
          <Link
            href={siteLinks.console}
            className="inline-flex items-center gap-2 rounded bg-slate-900 px-4 py-2.5 text-[13px] text-white hover:bg-slate-800"
          >
            进入控制台 <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </section>
    </MarketingShell>
  );
}

function Block({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <div className="mb-1 text-slate-500">{label}</div>
      <p className="text-slate-700">{text}</p>
    </div>
  );
}
