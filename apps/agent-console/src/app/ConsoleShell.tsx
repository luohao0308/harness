import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  Activity,
  Bell,
  Bot,
  Box,
  Brain,
  ChevronDown,
  FlaskConical,
  ListChecks,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  PlugZap,
  Search,
  ShieldCheck,
} from "lucide-react";

import { Button } from "../components/ui/button";
import { useConsoleStore } from "../stores/consoleStore";
import { environmentLabel } from "../lib/labels";
import { cn } from "../lib/utils";

const navItems = [
  { to: "/agents", label: "Agent", en: "Agents", icon: Bot },
  { to: "/runs", label: "Run 历史", en: "Runs", icon: ListChecks },
  { to: "/subagents", label: "子 Agent", en: "Subagents", icon: Bot },
  { to: "/sandboxes", label: "沙箱", en: "Sandboxes", icon: Box },
  { to: "/tools", label: "工具", en: "Tools", icon: PlugZap },
  { to: "/observability", label: "观测", en: "Observability", icon: Activity },
  { to: "/evals", label: "评测", en: "Evals", icon: FlaskConical },
  { to: "/settings/policies", label: "策略", en: "Policies", icon: ShieldCheck },
  { to: "/settings/models", label: "模型", en: "Models", icon: Brain },
];

export function ConsoleShell({ children, title }: { children: ReactNode; title: string }) {
  const navigate = useNavigate();
  const location = useLocation();
  const environment = useConsoleStore((state) => state.environment);
  const locale = useConsoleStore((state) => state.locale);
  const setLocale = useConsoleStore((state) => state.setLocale);
  const isChinese = locale === "zh-CN";
  const isWorkspaceRoute =
    location.pathname.includes("/workspace") || location.pathname.includes("/chat");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(isWorkspaceRoute);

  useEffect(() => {
    if (isWorkspaceRoute) {
      setSidebarCollapsed(true);
    }
  }, [isWorkspaceRoute]);

  return (
    <div className="flex min-h-screen bg-page text-slate-800" lang={isChinese ? "zh-CN" : "en-US"} translate="no">
      <aside
        className={cn(
          "flex shrink-0 flex-col border-r border-slate-200 bg-white transition-[width] duration-200",
          sidebarCollapsed ? "w-[64px]" : "w-[248px]",
        )}
      >
        <div
          className={cn(
            "flex h-14 items-center border-b border-slate-200",
            sidebarCollapsed ? "justify-center px-2" : "gap-2 px-4",
          )}
        >
          <div
            className={cn(
              "flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-slate-900 transition-opacity",
              sidebarCollapsed && "pointer-events-none absolute opacity-0",
            )}
          >
            <div className="h-3 w-3 border border-b-0 border-r-0 border-white" />
          </div>
          <div
            className={cn(
              "min-w-0 transition-opacity",
              sidebarCollapsed && "pointer-events-none absolute opacity-0",
            )}
          >
            <div className="text-sm font-semibold tracking-tight text-slate-900">Harness</div>
            <div className="-mt-0.5 text-[10px] text-slate-500">acme-prod · vpc-east</div>
          </div>
          <Button
            variant="ghost"
            className={cn("ml-auto h-7 w-7 px-0", sidebarCollapsed && "ml-0")}
            onClick={() => setSidebarCollapsed((value) => !value)}
            aria-label={sidebarCollapsed ? (isChinese ? "展开侧边栏" : "Expand sidebar") : (isChinese ? "折叠侧边栏" : "Collapse sidebar")}
            title={sidebarCollapsed ? (isChinese ? "展开侧边栏" : "Expand sidebar") : (isChinese ? "折叠侧边栏" : "Collapse sidebar")}
          >
            <PanelLeftOpen className={cn("h-4 w-4", !sidebarCollapsed && "hidden")} />
            <PanelLeftClose className={cn("h-4 w-4", sidebarCollapsed && "hidden")} />
          </Button>
        </div>
        <nav className="flex-1 p-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                title={isChinese ? item.label : item.en}
                className={({ isActive }) =>
                  cn(
                    "mb-0.5 flex h-8 items-center rounded-md text-[13px]",
                    sidebarCollapsed ? "justify-center px-0" : "gap-2 px-2.5",
                    isActive
                      ? "bg-slate-100 text-slate-900"
                      : "text-slate-600 hover:bg-slate-50 hover:text-slate-900",
                  )
                }
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span
                  className={cn(
                    "flex-1 truncate transition-opacity",
                    sidebarCollapsed && "pointer-events-none absolute opacity-0",
                  )}
                >
                  {isChinese ? item.label : item.en}
                </span>
              </NavLink>
            );
          })}
        </nav>
        <div
          className={cn(
            "border-t border-slate-200 text-[11px] text-slate-500",
            sidebarCollapsed ? "p-2" : "p-3",
          )}
        >
          <div className="mb-1 flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            <span
              className={cn(
                "transition-opacity",
                sidebarCollapsed && "pointer-events-none absolute opacity-0",
              )}
            >
              {isChinese ? "系统运行正常" : "All systems operational"}
            </span>
          </div>
          <div
            className={cn(
              "font-mono transition-opacity",
              sidebarCollapsed && "pointer-events-none absolute opacity-0",
            )}
          >
            api 0.1.0 · console 0.1.0
          </div>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center gap-3 border-b border-slate-200 bg-white px-5">
          <div className="flex items-center gap-2 text-[13px] text-slate-500">
            <span>{isChinese ? "控制台" : "Console"}</span>
            <span className="text-slate-300">/</span>
            <span className="text-slate-900">{title}</span>
          </div>
          <div className="ml-6 flex h-8 w-72 items-center gap-2 rounded-md border border-slate-200 bg-slate-50/70 px-2.5">
            <Search className="h-3.5 w-3.5 text-slate-400" />
            <input
              aria-label={isChinese ? "搜索" : "Search"}
              placeholder={isChinese ? "搜索 Run、Agent、事件..." : "Search runs, agents, events..."}
              className="min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-slate-400"
            />
            <span className="font-mono text-[10px] text-slate-400">⌘K</span>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Button className="gap-1.5">
              {isChinese ? "环境" : "env"}: {isChinese ? environmentLabel(environment) : environment}{" "}
              <ChevronDown className="h-3 w-3" />
            </Button>
            <Button
              variant="ghost"
              onClick={() => setLocale(isChinese ? "en-US" : "zh-CN")}
              aria-label={isChinese ? "语言" : "Language"}
            >
              {isChinese ? "中文" : "English"}
            </Button>
            <Button variant="ghost" className="w-8 px-0" aria-label={isChinese ? "告警" : "Alerts"}>
              <Bell className="h-4 w-4" />
            </Button>
            <Button variant="primary" onClick={() => navigate("/agents/default/workspace")}>
              <Plus className="h-3.5 w-3.5" /> {isChinese ? "新对话" : "New chat"}
            </Button>
            <div className="ml-1 flex h-7 w-7 items-center justify-center rounded-full bg-slate-200 text-[11px] text-slate-700">
              LH
            </div>
          </div>
        </header>
        <div className="min-h-0 flex-1 overflow-auto">{children}</div>
      </main>
    </div>
  );
}
