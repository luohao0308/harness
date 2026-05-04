import Link from "next/link";
import { type ReactNode } from "react";
import { ArrowRight, FileJson } from "lucide-react";

import { siteLinks } from "./site-links";

export function Logo() {
  return (
    <div className="flex items-center gap-2">
      <div className="w-6 h-6 rounded bg-slate-900 flex items-center justify-center">
        <div className="w-2.5 h-2.5 border border-white border-r-0 border-b-0" />
      </div>
      <span className="text-slate-900 tracking-tight">Harness</span>
      <span className="text-slate-400 text-[12px] border-l border-slate-200 pl-2 hidden sm:inline">
        Enterprise
      </span>
    </div>
  );
}

const navItems = [
  { k: "home", label: "首页" },
  { k: "product", label: "产品" },
  { k: "architecture", label: "架构" },
  { k: "solutions", label: "方案" },
  { k: "security", label: "安全" },
  { k: "deployment", label: "部署" },
  { k: "docs", label: "文档" },
  { k: "contact", label: "联系" },
];

export function MarketingShell({
  active,
  children,
  onNav,
}: {
  active: string;
  children: ReactNode;
  onNav?: (k: string) => void;
}) {
  return (
    <div className="bg-white text-slate-900 min-h-full">
      <header className="border-b border-slate-200 bg-white sticky top-0 z-10">
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 h-14 flex items-center">
          <Link href="/" className="shrink-0">
            <Logo />
          </Link>
          <nav className="ml-6 sm:ml-10 hidden md:flex items-center gap-5 text-[13px] text-slate-600">
            {navItems.map((it) => (
              <Link
                href={it.k === "home" ? "/" : `/${it.k}`}
                key={it.k}
                className={`hover:text-slate-900 ${active === it.k ? "text-slate-900" : ""}`}
              >
                {it.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <Link
              href={siteLinks.openapiJson}
              className="hidden sm:inline-flex text-[13px] text-slate-600 px-3 py-1.5 hover:text-slate-900 items-center gap-1.5 border border-slate-200 rounded"
            >
              <FileJson className="w-3.5 h-3.5" /> OpenAPI
            </Link>
            <Link
              href={siteLinks.console}
              className="text-[13px] bg-slate-900 text-white px-3.5 py-1.5 rounded hover:bg-slate-800 inline-flex items-center gap-1.5"
            >
              进入控制台 <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>
        <div className="md:hidden border-t border-slate-100 overflow-x-auto">
          <div className="px-4 py-2 flex items-center gap-4 text-[12px] text-slate-600 whitespace-nowrap">
            {navItems.map((it) => (
              <Link key={it.k} href={it.k === "home" ? "/" : `/${it.k}`} className={active === it.k ? "text-slate-900" : ""}>
                {it.label}
              </Link>
            ))}
          </div>
        </div>
      </header>

      {children}

      <footer className="border-t border-slate-200 bg-white">
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 py-10 grid grid-cols-2 md:grid-cols-5 gap-6 text-[12px]">
          <div className="col-span-2">
            <Logo />
            <p className="mt-3 text-slate-500 leading-relaxed max-w-sm">
              生产级企业 AI Agent Harness 平台。Model 提供推理，Harness 提供可靠性。
            </p>
          </div>
          <div>
            <div className="text-slate-900 mb-2">产品入口</div>
            <ul className="space-y-1.5 text-slate-500">
              <li><Link href={siteLinks.console} className="hover:text-slate-900">控制台</Link></li>
              <li><Link href={siteLinks.openapiJson} className="hover:text-slate-900">OpenAPI JSON</Link></li>
              <li><Link href={siteLinks.openapiYaml} className="hover:text-slate-900">OpenAPI YAML</Link></li>
            </ul>
          </div>
          <div>
            <div className="text-slate-900 mb-2">文档</div>
            <ul className="space-y-1.5 text-slate-500">
              <li><Link href={siteLinks.usageFlow} className="hover:text-slate-900">使用流程</Link></li>
              <li><Link href={siteLinks.deployment} className="hover:text-slate-900">部署文档</Link></li>
              <li><Link href={siteLinks.localDevelopment} className="hover:text-slate-900">本地开发</Link></li>
              <li><Link href={siteLinks.troubleshooting} className="hover:text-slate-900">故障排查</Link></li>
            </ul>
          </div>
          <div>
            <div className="text-slate-900 mb-2">联系</div>
            <ul className="space-y-1.5 text-slate-500">
              <li><Link href="/contact" className="hover:text-slate-900">申请演示</Link></li>
              <li><Link href={siteLinks.console} className="hover:text-slate-900">企业接入</Link></li>
              <li className="font-mono">v1.4 · 2026</li>
            </ul>
          </div>
        </div>
        <div className="border-t border-slate-100 py-4 text-center text-[11px] text-slate-400">
          © 2026 Harness Systems · Production-grade harness layer for enterprise AI agents
        </div>
      </footer>
    </div>
  );
}
