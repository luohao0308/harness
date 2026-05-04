"use client";

import Link from "next/link";
import { type ReactNode, useState } from "react";
import { MarketingShell } from "./MarketingShell";
import { ArrowRight } from "lucide-react";
import { siteLinks } from "./site-links";

const deployOpts = [
  "Docker Compose 本地评估",
  "VPC",
  "物理机房",
  "混合云",
];

const capOpts = [
  "任务执行",
  "事件溯源",
  "Replay 调试",
  "Subagent",
  "Docker Sandbox",
  "WarmPool",
  "模型/工具审计",
  "OpenAPI 集成",
  "监控观测",
];

const flow: Array<[string, string]> = [
  ["01", "需求确认"],
  ["02", "本地评估"],
  ["03", "架构接入"],
  ["04", "部署验证"],
  ["05", "控制台联调"],
];

export function Contact({ onNav }: { onNav?: (k: string) => void }) {
  const [deploy, setDeploy] = useState<string>(deployOpts[0]);
  const [caps, setCaps] = useState<string[]>([]);

  function toggleCap(c: string) {
    setCaps((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]));
  }

  return (
    <MarketingShell active="contact" onNav={onNav}>
      <section className="border-b border-slate-200">
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 py-12">
          <div className="text-[12px] tracking-widest text-slate-500 mb-2">CONTACT</div>
          <h1 className="text-[32px] sm:text-[40px] tracking-tight text-slate-900 mb-3">
            申请演示与企业接入咨询
          </h1>
          <p className="text-slate-600 text-[14px] max-w-2xl">
            请填写以下信息，我们将在 1 个工作日内联系。咨询范围仅限当前已实现的能力。
          </p>
        </div>
      </section>

      <section className="bg-slate-50/40">
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 py-12 grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Form */}
          <form
            onSubmit={(e) => e.preventDefault()}
            className="lg:col-span-8 bg-white border border-slate-200 rounded-lg p-6 space-y-5"
          >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Field label="姓名" placeholder="张三" />
              <Field label="公司" placeholder="Example Co." />
              <Field label="邮箱" placeholder="you@example.com" type="email" />
              <Field label="角色" placeholder="平台工程 / SRE / 安全 / 架构师" />
            </div>

            <div>
              <Label>部署方式</Label>
              <div className="flex flex-wrap gap-2">
                {deployOpts.map((o) => (
                  <button
                    key={o}
                    type="button"
                    onClick={() => setDeploy(o)}
                    className={`px-3 h-8 rounded border text-[12px] ${
                      deploy === o
                        ? "bg-slate-900 text-white border-slate-900"
                        : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50"
                    }`}
                  >
                    {o}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <Label>关注能力（多选，仅当前已实现）</Label>
              <div className="flex flex-wrap gap-2">
                {capOpts.map((c) => {
                  const on = caps.includes(c);
                  return (
                    <button
                      key={c}
                      type="button"
                      onClick={() => toggleCap(c)}
                      className={`px-3 h-8 rounded border text-[12px] ${
                        on
                          ? "bg-slate-100 text-slate-900 border-slate-300"
                          : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50"
                      }`}
                    >
                      {on ? "✓ " : ""}
                      {c}
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <Label>备注</Label>
              <textarea
                rows={4}
                placeholder="任务规模、合规要求、目标接入时间等"
                className="w-full px-3 py-2 rounded border border-slate-200 bg-white text-[13px] outline-none focus:border-slate-400 placeholder:text-slate-400 resize-none"
              />
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-100">
              <div className="text-[11px] text-slate-500">
                提交即同意我方仅用于本次咨询联系。
              </div>
              <button
                type="submit"
                className="bg-slate-900 text-white text-[13px] px-4 py-2.5 rounded hover:bg-slate-800 inline-flex items-center gap-2"
              >
                提交申请 <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </form>

          {/* Side */}
          <aside className="lg:col-span-4 space-y-3">
            <div className="bg-white border border-slate-200 rounded-lg p-5">
              <div className="text-[11px] tracking-widest text-slate-500 mb-3">联系后流程</div>
              <ol className="space-y-2">
                {flow.map(([n, t], i) => (
                  <li key={n} className="flex items-center gap-3">
                    <span className="w-6 h-6 rounded bg-slate-100 text-slate-700 font-mono text-[11px] flex items-center justify-center">
                      {n}
                    </span>
                    <span className="text-[13px] text-slate-800">{t}</span>
                    {i < flow.length - 1 && (
                      <span className="ml-auto text-slate-300 text-[11px]">↓</span>
                    )}
                  </li>
                ))}
              </ol>
            </div>

            <div className="bg-white border border-slate-200 rounded-lg p-5">
              <div className="text-[11px] tracking-widest text-slate-500 mb-2">直接入口</div>
              <ul className="text-[13px] space-y-2">
                <li>
                  <Link href={siteLinks.console} className="text-slate-800 hover:text-slate-900 inline-flex items-center gap-1">
                    进入控制台 <ArrowRight className="w-3 h-3" />
                  </Link>
                </li>
                <li>
                  <Link href={siteLinks.openapiJson} className="text-slate-800 hover:text-slate-900 inline-flex items-center gap-1">
                    查看 OpenAPI <ArrowRight className="w-3 h-3" />
                  </Link>
                </li>
                <li>
                  <Link
                    href="/docs"
                    className="text-slate-800 hover:text-slate-900 inline-flex items-center gap-1"
                  >
                    阅读文档 <ArrowRight className="w-3 h-3" />
                  </Link>
                </li>
              </ul>
            </div>

            <div className="bg-slate-900 text-slate-200 rounded-lg p-5 text-[12px] leading-relaxed">
              企业接入仅限当前已实现的能力组合。如需 SSO / LDAP / 多租户等尚未发布的特性，可在备注中注明，我们会评估路线图。
            </div>
          </aside>
        </div>
      </section>
    </MarketingShell>
  );
}

function Label({ children }: { children: ReactNode }) {
  return <div className="text-[12px] text-slate-700 mb-2">{children}</div>;
}

function Field({
  label,
  placeholder,
  type = "text",
}: {
  label: string;
  placeholder: string;
  type?: string;
}) {
  return (
    <div>
      <Label>{label}</Label>
      <input
        type={type}
        placeholder={placeholder}
        className="w-full h-9 px-3 rounded border border-slate-200 bg-white text-[13px] outline-none focus:border-slate-400 placeholder:text-slate-400"
      />
    </div>
  );
}
