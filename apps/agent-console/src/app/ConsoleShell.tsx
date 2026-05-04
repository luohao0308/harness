import type { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  Activity,
  Bell,
  Bot,
  Box,
  Brain,
  ChevronDown,
  ListChecks,
  Plus,
  Search,
  Settings,
  ShieldCheck,
} from "lucide-react";

import { Button } from "../components/ui/button";
import { useConsoleStore } from "../stores/consoleStore";
import { cn } from "../lib/utils";

const navItems = [
  { to: "/tasks", label: "Tasks", icon: ListChecks },
  { to: "/tasks/demo/subagents", label: "Subagents", icon: Bot },
  { to: "/sandboxes", label: "Sandboxes", icon: Box },
  { to: "/observability", label: "Observability", icon: Activity },
  { to: "/settings/policies", label: "Policies", icon: ShieldCheck },
  { to: "/settings/models", label: "Models", icon: Brain },
];

export function ConsoleShell({ children, title }: { children: ReactNode; title: string }) {
  const navigate = useNavigate();
  const environment = useConsoleStore((state) => state.environment);

  return (
    <div className="flex min-h-screen bg-page text-slate-800">
      <aside className="flex w-[248px] shrink-0 flex-col border-r border-slate-200 bg-white">
        <div className="flex h-14 items-center gap-2 border-b border-slate-200 px-4">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-slate-900">
            <div className="h-3 w-3 border border-b-0 border-r-0 border-white" />
          </div>
          <div>
            <div className="text-sm font-semibold tracking-tight text-slate-900">Harness</div>
            <div className="-mt-0.5 text-[10px] text-slate-500">acme-prod · vpc-east</div>
          </div>
        </div>
        <nav className="flex-1 p-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "mb-0.5 flex h-8 items-center gap-2 rounded-md px-2.5 text-[13px]",
                    isActive
                      ? "bg-slate-100 text-slate-900"
                      : "text-slate-600 hover:bg-slate-50 hover:text-slate-900",
                  )
                }
              >
                <Icon className="h-4 w-4" />
                <span className="flex-1">{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
        <div className="border-t border-slate-200 p-3 text-[11px] text-slate-500">
          <div className="mb-1 flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            All systems operational
          </div>
          <div className="font-mono">api 0.1.0 · console 0.1.0</div>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center gap-3 border-b border-slate-200 bg-white px-5">
          <div className="flex items-center gap-2 text-[13px] text-slate-500">
            <span>Console</span>
            <span className="text-slate-300">/</span>
            <span className="text-slate-900">{title}</span>
          </div>
          <div className="ml-6 flex h-8 w-72 items-center gap-2 rounded-md border border-slate-200 bg-slate-50/70 px-2.5">
            <Search className="h-3.5 w-3.5 text-slate-400" />
            <input
              aria-label="Search"
              placeholder="Search tasks, agents, events..."
              className="min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-slate-400"
            />
            <span className="font-mono text-[10px] text-slate-400">⌘K</span>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Button className="gap-1.5">
              env: {environment} <ChevronDown className="h-3 w-3" />
            </Button>
            <Button variant="ghost" className="w-8 px-0" aria-label="Alerts">
              <Bell className="h-4 w-4" />
            </Button>
            <Button variant="primary" onClick={() => navigate("/tasks/new")}>
              <Plus className="h-3.5 w-3.5" /> Create Task
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
