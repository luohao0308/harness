import {
  FolderOpen,
  MessageSquareText,
  Settings2,
  ShieldCheck,
  SquareTerminal,
  Users,
} from "lucide-react";
import type { JSX } from "react";
import { Link, useLocation } from "react-router-dom";

import { cn } from "../../lib/utils";
import { useWorkspaceStore } from "../../stores/workspaceStore";

type DesktopOperation = "tasks" | "teams" | "terminal" | "files" | "approvals" | "settings";

export function DesktopOperationRail(): JSX.Element {
  const location = useLocation();
  const activeWorkspaceId = useWorkspaceStore((state) => state.activeWorkspaceId);
  const activeWorkspace = useWorkspaceStore((state) => state.workspaceRegistry[activeWorkspaceId]);
  const workspaceMatch = location.pathname.match(/^\/agents\/[^/]+\/workspace$/);
  const workspacePath = workspaceMatch
    ? location.pathname
    : `/agents/${encodeURIComponent(activeWorkspace?.agentId ?? "default")}/workspace`;
  const panel = new URLSearchParams(location.search).get("desktop_panel");

  const items = [
    {
      key: "tasks" as const,
      to: workspacePath,
      label: "任务",
      icon: MessageSquareText,
    },
    {
      key: "teams" as const,
      to: "/teams",
      label: "团队",
      icon: Users,
    },
    {
      key: "terminal" as const,
      to: "/terminal",
      label: "终端",
      icon: SquareTerminal,
    },
    {
      key: "files" as const,
      to: `${workspacePath}?desktop_panel=files`,
      label: "文件",
      icon: FolderOpen,
    },
    {
      key: "approvals" as const,
      to: `${workspacePath}?desktop_panel=approvals`,
      label: "审批",
      icon: ShieldCheck,
    },
  ];

  return (
    <aside
      data-testid="desktop-operation-rail"
      aria-label="桌面操作"
      className="flex h-screen w-14 shrink-0 flex-col items-center border-r border-slate-200 bg-[#f7f7f8] py-2"
    >
      <Link
        to={workspacePath}
        aria-label="返回任务"
        title="返回任务"
        className="mb-3 flex h-8 w-8 items-center justify-center rounded-md bg-slate-900 font-mono text-xs font-semibold text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
      >
        H
      </Link>

      <nav aria-label="桌面常用功能" className="flex flex-col items-center gap-1">
        {items.map((item) => (
          <DesktopOperationLink
            key={item.key}
            to={item.to}
            label={item.label}
            active={isOperationActive(item.key, location.pathname, panel)}
            icon={<item.icon aria-hidden="true" className="h-4 w-4" />}
          />
        ))}
      </nav>

      <div className="mt-auto">
        <DesktopOperationLink
          to="/desktop"
          label="设置"
          active={isOperationActive("settings", location.pathname, panel)}
          icon={<Settings2 aria-hidden="true" className="h-4 w-4" />}
        />
      </div>
    </aside>
  );
}

function DesktopOperationLink({
  to,
  label,
  active,
  icon,
}: {
  to: string;
  label: string;
  active: boolean;
  icon: JSX.Element;
}): JSX.Element {
  return (
    <Link
      to={to}
      aria-label={label}
      title={label}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex h-9 w-9 items-center justify-center rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400",
        active
          ? "bg-slate-200 text-slate-950"
          : "text-slate-500 hover:bg-slate-200/70 hover:text-slate-900",
      )}
    >
      {icon}
    </Link>
  );
}

function isOperationActive(
  operation: DesktopOperation,
  pathname: string,
  panel: string | null,
): boolean {
  if (operation === "tasks") return /^\/agents\/[^/]+\/workspace$/.test(pathname) && panel === null;
  if (operation === "teams") return /^\/teams(?:\/|$)/.test(pathname);
  if (operation === "terminal") return pathname === "/terminal";
  if (operation === "files") return /^\/agents\/[^/]+\/workspace$/.test(pathname) && panel === "files";
  if (operation === "approvals") {
    return (/^\/agents\/[^/]+\/workspace$/.test(pathname) && panel === "approvals") || /^\/runs(?:\/|$)/.test(pathname);
  }
  return pathname === "/desktop" || pathname === "/settings/advanced";
}
