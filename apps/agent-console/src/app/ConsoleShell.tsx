import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  Activity,
  ClipboardList,
  Bot,
  Box,
  Brain,
  BrainCircuit,
  ChevronDown,
  CircleHelp,
  Database,
  FlaskConical,
  Gauge,
  KeyRound,
  LayoutDashboard,
  LibraryBig,
  ListChecks,
  LogOut,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  PlugZap,
  Search,
  Settings2,
  ShieldCheck,
  Store,
  UserRound,
  Users,
} from "lucide-react";

import { Button } from "../components/ui/button";
import { FeedbackToastViewport } from "../components/ui/feedback-toast";
import { QuickActionFAB } from "../components/ui/QuickActionFAB";
import { WorkspaceSwitcher } from "../components/WorkspaceSwitcher";
import { useOptionalAuth } from "../features/auth/AuthProvider";
import { AlertBell } from "../features/observability/components/AlertBell";
import { useConsoleStore } from "../stores/consoleStore";
import { environmentLabel } from "../lib/labels";
import { cn } from "../lib/utils";
import { consoleNavEntries } from "./consoleNav";

const navIconByKey = {
  activity: Activity,
  audit: ClipboardList,
  bot: Bot,
  box: Box,
  brain: Brain,
  brainCircuit: BrainCircuit,
  dashboard: LayoutDashboard,
  database: Database,
  evals: FlaskConical,
  gauge: Gauge,
  help: CircleHelp,
  key: KeyRound,
  knowledge: LibraryBig,
  network: Network,
  runs: ListChecks,
  settings: Settings2,
  shield: ShieldCheck,
  store: Store,
  tools: PlugZap,
  users: Users,
} as const;

export const consoleNavItems = consoleNavEntries.map((item) => ({
  to: item.to,
  label: item.label,
  icon: navIconByKey[item.iconKey],
}));

export function ConsoleShell({ children, title }: { children: ReactNode; title: string }) {
  const navigate = useNavigate();
  const location = useLocation();
  const environment = useConsoleStore((state) => state.environment);
  const auth = useOptionalAuth();
  const isUsingDevToken = auth?.isUsingDevToken ?? true;
  const logoutCurrentUser = auth?.logoutCurrentUser;
  const user = auth?.user ?? null;
  const isWorkspaceRoute = /^\/agents\/[^/]+\/workspace$/.test(location.pathname);
  const isTeamRoute = /^\/teams(?:\/|$)/.test(location.pathname);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(isWorkspaceRoute);
  const [isNarrowShell, setIsNarrowShell] = useState(false);
  const sidebarForceCollapsed = isWorkspaceRoute || isTeamRoute || isNarrowShell;
  const effectiveSidebarCollapsed = sidebarCollapsed || sidebarForceCollapsed;
  const canToggleSidebar = !sidebarForceCollapsed;
  const sidebarToggleLabel = canToggleSidebar
    ? effectiveSidebarCollapsed
      ? "展开侧边栏"
      : "折叠侧边栏"
    : "侧边栏已收起";

  useEffect(() => {
    if (isWorkspaceRoute || isTeamRoute) {
      setSidebarCollapsed(true);
    }
  }, [isTeamRoute, isWorkspaceRoute]);

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
      className="flex h-screen overflow-hidden bg-page text-slate-800"
      lang="zh-CN"
      translate="no"
    >
      <FeedbackToastViewport />
      <QuickActionFAB />
      <aside
        className={cn(
          "flex h-screen min-h-0 shrink-0 flex-col border-r border-slate-200 bg-white transition-[width] duration-200",
          effectiveSidebarCollapsed ? (isTeamRoute ? "w-[44px]" : "w-[64px]") : "w-[248px]",
        )}
      >
        <div
          className={cn(
            "flex h-14 items-center border-b border-slate-200",
            effectiveSidebarCollapsed ? (isTeamRoute ? "justify-center px-1" : "justify-center px-2") : "gap-2 px-4",
          )}
        >
          <div
            className={cn(
              "flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-slate-900 transition-opacity",
              effectiveSidebarCollapsed && "hidden",
            )}
          >
            <div className="h-3 w-3 border border-b-0 border-r-0 border-white" />
          </div>
          <div
            className={cn(
              "min-w-0 transition-opacity",
              effectiveSidebarCollapsed && "hidden",
            )}
          >
            <div className="text-sm font-semibold tracking-tight text-slate-900">运行平台</div>
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
        <nav className="min-h-0 flex-1 overflow-y-auto p-2">
          {consoleNavItems.map((item) => {
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
                    effectiveSidebarCollapsed && "hidden",
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
                effectiveSidebarCollapsed && "hidden",
              )}
            >
              系统运行正常
            </span>
          </div>
          <div
            className={cn(
              "font-mono transition-opacity",
              effectiveSidebarCollapsed && "hidden",
            )}
          >
            api 0.1.0 · console 0.1.0
          </div>
        </div>
      </aside>

      <main className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header
          className={cn(
            "flex min-w-0 items-center gap-2 border-b border-slate-200 bg-white px-3 sm:gap-3 sm:px-5",
            isTeamRoute ? "h-0 overflow-hidden border-b-0 px-0" : "h-14",
          )}
        >
          <div className="flex min-w-0 items-center gap-2 text-[13px] text-slate-500">
            <span>控制台</span>
            <span className="text-slate-300">/</span>
            <span className="truncate text-slate-900">{title}</span>
          </div>
          {!isTeamRoute ? (
            <div className="ml-6 hidden h-8 w-72 items-center gap-2 rounded-md border border-slate-200 bg-slate-50/70 px-2.5 lg:flex">
              <Search className="h-3.5 w-3.5 text-slate-400" />
              <input
                aria-label="搜索"
                placeholder="搜索运行、智能体、事件..."
                className="min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-slate-400"
              />
              <span className="font-mono text-[10px] text-slate-400">⌘K</span>
            </div>
          ) : null}
          <div className="ml-auto flex shrink-0 items-center gap-1.5 sm:gap-2">
            <WorkspaceSwitcher />
            <Button className="hidden gap-1.5 md:inline-flex">
              环境: {environmentLabel(environment)}{" "}
              <ChevronDown className="h-3 w-3" />
            </Button>
            <AlertBell />
            {!isTeamRoute ? (
              <Button
                variant="ghost"
                className="h-7 w-7 px-0"
                title="帮助中心"
                aria-label="帮助中心"
                onClick={() => navigate("/help")}
              >
                <CircleHelp className="h-3.5 w-3.5" />
              </Button>
            ) : null}
            {!isTeamRoute ? (
              <Button
                variant="primary"
                className="hidden sm:inline-flex"
                onClick={() => navigate("/agents/default/workspace")}
              >
                <Plus className="h-3.5 w-3.5" /> 新对话
              </Button>
            ) : null}
            <div
              className="ml-1 hidden max-w-40 items-center gap-2 rounded-full bg-slate-100 px-2 py-1 text-[11px] text-slate-700 sm:flex"
              title={user?.email ?? "dev-token"}
            >
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-slate-200">
                <UserRound className="h-3 w-3" />
              </span>
              <span className="truncate">{user?.name ?? "Dev User"}</span>
              {isUsingDevToken ? <span className="font-mono text-[10px] text-slate-400">dev</span> : null}
            </div>
            {!isUsingDevToken ? (
              <Button
                variant="ghost"
                className="h-7 w-7 px-0"
                title="退出登录"
                onClick={() => void logoutCurrentUser?.()}
              >
                <LogOut className="h-3.5 w-3.5" />
              </Button>
            ) : null}
          </div>
        </header>
        <div
          className={cn(
            "min-h-0 flex-1",
            isWorkspaceRoute || isTeamRoute ? "overflow-hidden" : "overflow-auto",
          )}
        >
          {children}
        </div>
      </main>
    </div>
  );
}
