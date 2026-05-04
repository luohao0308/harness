"use client";

import Link from "next/link";
import { useState } from "react";
import { MarketingShell } from "./MarketingShell";
import { FileText, FileJson, Wrench, ShieldCheck, Activity, BookOpen } from "lucide-react";
import { siteLinks } from "./site-links";

type Doc = {
  k: string;
  cat: string;
  t: string;
  s: string;
  meta: string;
  href: string;
  highlight?: boolean;
};

const docs: Doc[] = [
  { k: "flow", cat: "入门", t: "网站使用流程", s: "首次访问到任务执行的完整路径，含控制台与 API 两条入口。", meta: "markdown · 6 min", href: siteLinks.usageFlow },
  { k: "local", cat: "入门", t: "本地开发", s: "克隆仓库 → 启动 Compose → 数据库迁移 → 控制台联调。", meta: "markdown · 8 min", href: siteLinks.localDevelopment },
  { k: "openapi-json", cat: "API", t: "OpenAPI JSON", s: "完整接口定义。可直接导入 Swagger UI / Apifox / Postman。", meta: "openapi.json", href: siteLinks.openapiJson, highlight: true },
  { k: "openapi-yaml", cat: "API", t: "OpenAPI YAML", s: "与 JSON 等价的 YAML 版本，便于 Git 审查与 diff。", meta: "openapi.yaml", href: siteLinks.openapiYaml, highlight: true },
  { k: "deploy", cat: "运维", t: "部署 Runbook", s: "Docker Compose 拓扑、systemd 单元、Nginx 配置与回归步骤。", meta: "markdown · 14 min", href: siteLinks.deployment },
  { k: "migrate", cat: "运维", t: "数据库迁移", s: "Alembic 命令、生成迁移脚本与版本约定。", meta: "markdown · 4 min", href: "https://github.com/luohao0308/harness/blob/develop/docs/runbooks/migrations.md" },
  { k: "rollback", cat: "运维", t: "回滚", s: "API、Worker、Schema 三层回滚策略与验证清单。", meta: "markdown · 5 min", href: "https://github.com/luohao0308/harness/blob/develop/docs/runbooks/rollback.md" },
  { k: "trouble", cat: "运维", t: "故障排查", s: "常见错误码、Sandbox 资源耗尽、Event 写入异常的定位方式。", meta: "markdown · 12 min", href: siteLinks.troubleshooting },
  { k: "threat", cat: "安全", t: "安全威胁模型", s: "Bearer 鉴权、Sandbox 隔离与审计的设计取舍。", meta: "markdown · 10 min", href: "https://github.com/luohao0308/harness/blob/develop/docs/security/threat-model.md" },
  { k: "test", cat: "工程", t: "测试策略", s: "单测、集成、Replay 回放测试的分层与覆盖目标。", meta: "markdown · 6 min", href: "https://github.com/luohao0308/harness/blob/develop/docs/qa/test-strategy.md" },
  { k: "feat", cat: "工程", t: "功能说明文档", s: "已实现能力一览，与 OpenAPI、控制台页面的对应关系。", meta: "markdown · 9 min", href: "https://github.com/luohao0308/harness/blob/develop/docs/human/features/README.md" },
];

const cats = ["全部", "入门", "API", "运维", "安全", "工程"];

const catIcon: Record<string, any> = {
  入门: <BookOpen className="w-3.5 h-3.5" />,
  API: <FileJson className="w-3.5 h-3.5" />,
  运维: <Wrench className="w-3.5 h-3.5" />,
  安全: <ShieldCheck className="w-3.5 h-3.5" />,
  工程: <Activity className="w-3.5 h-3.5" />,
};

export function Docs({ onNav }: { onNav?: (k: string) => void }) {
  const [cat, setCat] = useState("全部");
  const list = cat === "全部" ? docs : docs.filter((d) => d.cat === cat);

  return (
    <MarketingShell active="docs" onNav={onNav}>
      <section className="border-b border-slate-200">
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 py-12">
          <div className="text-[12px] tracking-widest text-slate-500 mb-2">DOCS</div>
          <h1 className="text-[32px] sm:text-[40px] tracking-tight text-slate-900 mb-3">
            开发者与运维文档中心
          </h1>
          <p className="text-slate-600 text-[14px] max-w-2xl">
            所有文档均基于当前仓库已有内容。OpenAPI JSON / YAML 可直接导入 Swagger、Apifox、Postman 中使用。
          </p>
        </div>
      </section>

      <section className="bg-slate-50/40">
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 py-10 grid grid-cols-1 lg:grid-cols-12 gap-6">
          <aside className="lg:col-span-3">
            <div className="bg-white border border-slate-200 rounded-lg p-2 sticky top-20">
              <div className="px-2 py-2 text-[11px] tracking-widest text-slate-500">分类</div>
              {cats.map((c) => (
                <button
                  key={c}
                  onClick={() => setCat(c)}
                  className={`w-full text-left px-2.5 py-1.5 rounded text-[13px] mb-0.5 inline-flex items-center gap-2 ${
                    cat === c
                      ? "bg-slate-100 text-slate-900"
                      : "text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  <span className="text-slate-500">{catIcon[c] || <FileText className="w-3.5 h-3.5" />}</span>
                  <span className="flex-1">{c}</span>
                  <span className="text-[10px] font-mono text-slate-400">
                    {c === "全部" ? docs.length : docs.filter((d) => d.cat === c).length}
                  </span>
                </button>
              ))}
              <div className="border-t border-slate-100 mt-2 pt-2 px-2 text-[11px] text-slate-500 leading-relaxed">
                提示：OpenAPI 直接复制 URL 导入到 Swagger UI 或 Apifox 即可获得可调试接口。
              </div>
            </div>
          </aside>

          <div className="lg:col-span-9 grid grid-cols-1 md:grid-cols-2 gap-3">
            {list.map((d) => (
              <div
                key={d.k}
                className={`bg-white border rounded-lg p-5 hover:border-slate-300 transition-colors ${
                  d.highlight ? "border-slate-300" : "border-slate-200"
                }`}
              >
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[11px] tracking-widest text-slate-500">{d.cat}</span>
                  {d.highlight && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded border border-emerald-200 bg-emerald-50 text-emerald-700">
                      可直接导入
                    </span>
                  )}
                </div>
                <div className="text-slate-900 text-[15px] tracking-tight mb-1">{d.t}</div>
                <p className="text-[12px] text-slate-600 leading-relaxed mb-3">{d.s}</p>
                <div className="flex items-center justify-between text-[11px] text-slate-500">
                  <span className="font-mono">{d.meta}</span>
                  <Link href={d.href} className="text-slate-700 hover:text-slate-900">打开 →</Link>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </MarketingShell>
  );
}
