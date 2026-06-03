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
  { to: "/agents", label: "智能体", icon: Bot },
  { to: "/runs", label: "运行历史", icon: ListChecks },
  { to: "/subagents", label: "子代理", icon: Bot },
  { to: "/sandboxes", label: "沙箱", icon: Box },
  { to: "/tools", label: "工具", icon: PlugZap },
  { to: "/observability", label: "观测", icon: Activity },
  { to: "/evals", label: "评测", icon: FlaskConical },
  { to: "/settings/policies", label: "策略", icon: ShieldCheck },
  { to: "/settings/models", label: "模型", icon: Brain },
];

export function ConsoleShell({ children, title }: { children: ReactNode; title: string }) {
  const navigate = useNavigate();
  const location = useLocation();
  const environment = useConsoleStore((state) => state.environment);
  const isWorkspaceRoute = /^\/agents\/[^/]+\/workspace$/.test(location.pathname);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(isWorkspaceRoute);
  const [isNarrowShell, setIsNarrowShell] = useState(false);
  const sidebarForceCollapsed = isWorkspaceRoute || isNarrowShell;
  const effectiveSidebarCollapsed = sidebarCollapsed || sidebarForceCollapsed;
  const canToggleSidebar = !sidebarForceCollapsed;
  const sidebarToggleLabel = canToggleSidebar
    ? effectiveSidebarCollapsed
      ? "展开侧边栏"
      : "折叠侧边栏"
    : "侧边栏已收起";

  useEffect(() => {
    if (isWorkspaceRoute) {
      setSidebarCollapsed(true);
    }
  }, [isWorkspaceRoute]);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(max-width: 767px)");
    const apply = (): void => setIsNarrowShell(query.matches);
    apply();
    query.addEventListener("change", apply);
    return () => query.removeEventListener("change", apply);
  }, []);

  return (
    <div
      className="flex min-h-screen bg-page text-slate-800"
      lang="zh-CN"
      translate="no"
    >
      <aside
        className={cn(
          "flex shrink-0 flex-col border-r border-slate-200 bg-white transition-[width] duration-200",
          effectiveSidebarCollapsed ? "w-[64px]" : "w-[248px]",
        )}
      >
        <div
          className={cn(
            "flex h-14 items-center border-b border-slate-200",
            effectiveSidebarCollapsed ? "justify-center px-2" : "gap-2 px-4",
          )}
        >
          <div
            className={cn(
              "flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-slate-900 transition-opacity",
              effectiveSidebarCollapsed && "pointer-events-none absolute opacity-0",
            )}
          >
            <div className="h-3 w-3 border border-b-0 border-r-0 border-white" />
          </div>
          <div
            className={cn(
              "min-w-0 transition-opacity",
              effectiveSidebarCollapsed && "pointer-events-none absolute opacity-0",
            )}
          >
            <div className="text-sm font-semibold tracking-tight text-slate-900">Harness</div>
            <div className="-mt-0.5 text-[10px] text-slate-500">智能体运行平台 · acme-prod · vpc-east</div>
          </div>
          <Button
            variant="ghost"
            className={cn(
              "ml-auto h-7 w-7 px-0",
              effectiveSidebarCollapsed && "ml-0",
              !canToggleSidebar && "cursor-default text-slate-400 hover:bg-transparent",
            )}
            onClick={() => {
              if (!canToggleSidebar) return;
              setSidebarCollapsed((value) => !value);
            }}
            aria-disabled={!canToggleSidebar}
            aria-label={sidebarToggleLabel}
            title={sidebarToggleLabel}
          >
            <PanelLeftOpen className={cn("h-4 w-4", !effectiveSidebarCollapsed && "hidden")} />
            <PanelLeftClose className={cn("h-4 w-4", effectiveSidebarCollapsed && "hidden")} />
          </Button>
        </div>
        <nav className="flex-1 p-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                title={item.label}
                className={({ isActive }) =>
                  cn(
                    "mb-0.5 flex h-8 items-center rounded-md text-[13px]",
                    effectiveSidebarCollapsed ? "justify-center px-0" : "gap-2 px-2.5",
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
                    effectiveSidebarCollapsed && "pointer-events-none absolute opacity-0",
                  )}
                >
                  {item.label}
                </span>
              </NavLink>
            );
          })}
        </nav>
        <div
          className={cn(
            "border-t border-slate-200 text-[11px] text-slate-500",
            effectiveSidebarCollapsed ? "p-2" : "p-3",
          )}
        >
          <div className="mb-1 flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            <span
              className={cn(
                "transition-opacity",
                effectiveSidebarCollapsed && "pointer-events-none absolute opacity-0",
              )}
            >
              系统运行正常
            </span>
          </div>
          <div
            className={cn(
              "font-mono transition-opacity",
              effectiveSidebarCollapsed && "pointer-events-none absolute opacity-0",
            )}
          >
            api 0.1.0 · console 0.1.0
          </div>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 min-w-0 items-center gap-2 border-b border-slate-200 bg-white px-3 sm:gap-3 sm:px-5">
          <div className="flex min-w-0 items-center gap-2 text-[13px] text-slate-500">
            <span>控制台</span>
            <span className="text-slate-300">/</span>
            <span className="truncate text-slate-900">{title}</span>
          </div>
          <div className="ml-6 hidden h-8 w-72 items-center gap-2 rounded-md border border-slate-200 bg-slate-50/70 px-2.5 lg:flex">
            <Search className="h-3.5 w-3.5 text-slate-400" />
            <input
              aria-label="搜索"
              placeholder="搜索运行、智能体、事件..."
              className="min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-slate-400"
            />
            <span className="font-mono text-[10px] text-slate-400">⌘K</span>
          </div>
          <div className="ml-auto flex shrink-0 items-center gap-1.5 sm:gap-2">
            <Button className="hidden gap-1.5 md:inline-flex">
              环境: {environmentLabel(environment)}{" "}
              <ChevronDown className="h-3 w-3" />
            </Button>
            <Button variant="ghost" className="w-8 px-0" aria-label="告警">
              <Bell className="h-4 w-4" />
            </Button>
            <Button
              variant="primary"
              className="hidden sm:inline-flex"
              onClick={() => navigate("/agents/default/workspace")}
            >
              <Plus className="h-3.5 w-3.5" /> 新对话
            </Button>
            <div className="ml-1 hidden h-7 w-7 items-center justify-center rounded-full bg-slate-200 text-[11px] text-slate-700 sm:flex">
              LH
            </div>
          </div>
        </header>
        <div className="min-h-0 flex-1 overflow-auto">{children}</div>
      </main>
    </div>
  );
}
