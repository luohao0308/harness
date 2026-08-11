import type { Dispatch, ReactNode, SetStateAction } from "react";
import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  Activity,
  AppWindow,
  ClipboardList,
  Bot,
  Box,
  Brain,
  BrainCircuit,
  Camera,
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
  Terminal,
  UserCircle,
  UserRound,
  Users,
} from "lucide-react";

import { Button } from "../components/ui/button";
import { FeedbackToastViewport } from "../components/ui/feedback-toast";
import { DesktopOperationRail } from "../components/desktop/DesktopOperationRail";
import { QuickActionFAB } from "../components/ui/QuickActionFAB";
import { WorkspaceSwitcher } from "../components/WorkspaceSwitcher";
import { prepareAvatarUpload } from "../features/auth/avatarUpload";
import { useOptionalAuth } from "../features/auth/AuthProvider";
import { AlertBell } from "../features/observability/components/AlertBell";
import { useConsoleStore } from "../stores/consoleStore";
import { environmentLabel } from "../lib/labels";
import { isDesktopRuntime } from "../lib/desktop-bridge";
import { cn } from "../lib/utils";
import {
  consoleNavEntries,
  flattenConsoleNavEntries,
  isConsoleNavGroup,
  type ConsoleNavEntry,
  type ConsoleNavGroup,
  type ConsoleNavItem,
} from "./consoleNav";

const navIconByKey = {
  activity: Activity,
  appWindow: AppWindow,
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
  terminal: Terminal,
  tools: PlugZap,
  users: Users,
} as const;

const flatConsoleNavItems = flattenConsoleNavEntries().map((item) => ({
  to: item.to,
  label: item.label,
  icon: navIconByKey[item.iconKey],
}));

function initialsForName(name: string | undefined, email: string | undefined) {
  const source = (name || email || "Dev User").trim();
  if (!source) return "DU";
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0][0] ?? ""}${parts[1][0] ?? ""}`.toUpperCase();
  }
  return source.slice(0, 2).toUpperCase();
}

function navItemIsActive(pathname: string, to: string) {
  if (to === "/") return pathname === "/";
  return pathname === to || pathname.startsWith(`${to}/`);
}

function ConsoleNavEntryView({
  entry,
  pathname,
  openNavGroups,
  setOpenNavGroups,
}: {
  entry: ConsoleNavEntry;
  pathname: string;
  openNavGroups: Record<string, boolean>;
  setOpenNavGroups: Dispatch<SetStateAction<Record<string, boolean>>>;
}) {
  if (isConsoleNavGroup(entry)) {
    return (
      <ConsoleNavGroupView
        group={entry}
        pathname={pathname}
        openNavGroups={openNavGroups}
        setOpenNavGroups={setOpenNavGroups}
      />
    );
  }
  return <ConsoleNavLink item={entry} />;
}

function ConsoleNavGroupView({
  group,
  pathname,
  openNavGroups,
  setOpenNavGroups,
}: {
  group: ConsoleNavGroup;
  pathname: string;
  openNavGroups: Record<string, boolean>;
  setOpenNavGroups: Dispatch<SetStateAction<Record<string, boolean>>>;
}) {
  const Icon = navIconByKey[group.iconKey];
  const childActive = group.children.some((child) => navItemIsActive(pathname, child.to));
  const isOpen = openNavGroups[group.id] ?? childActive;
  const childListId = `console-nav-group-${group.id}`;

  const setOpen = (open: boolean) => {
    setOpenNavGroups((current) => ({ ...current, [group.id]: open }));
  };

  return (
    <div className="mb-1">
      <button
        type="button"
        className={cn(
          "flex min-h-11 w-full items-center gap-2 rounded-md px-2.5 text-left text-[13px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300",
          childActive
            ? "bg-slate-100 text-slate-900"
            : "text-slate-600 hover:bg-slate-50 hover:text-slate-900",
        )}
        aria-controls={childListId}
        aria-expanded={isOpen}
        onClick={() => setOpen(!isOpen)}
        onKeyDown={(event) => {
          if (event.key === "ArrowRight") {
            event.preventDefault();
            setOpen(true);
          }
          if (event.key === "ArrowLeft" || event.key === "Escape") {
            event.preventDefault();
            setOpen(false);
          }
        }}
      >
        <Icon className="h-4 w-4 shrink-0" />
        <span className="min-w-0 flex-1 truncate">{group.label}</span>
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 shrink-0 text-slate-400 transition-transform",
            isOpen && "rotate-180",
          )}
          aria-hidden="true"
        />
      </button>
      {isOpen ? (
        <div id={childListId} className="mt-1 grid gap-1 pl-3">
          {group.children.map((child) => (
            <ConsoleNavLink key={child.to} item={child} child />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ConsoleNavLink({ item, child = false }: { item: ConsoleNavItem; child?: boolean }) {
  const Icon = navIconByKey[item.iconKey];
  return (
    <NavLink
      to={item.to}
      title={item.label}
      className={({ isActive }) =>
        cn(
          "mb-1 flex min-h-11 items-center rounded-md text-[13px]",
          child ? "gap-2 px-2" : "gap-2 px-2.5",
          child && isActive
            ? "border-l-2 border-slate-900 bg-slate-100 pl-[10px] font-semibold text-slate-900"
            : child
              ? "pl-3 text-slate-500 hover:bg-slate-50 hover:text-slate-700"
              : isActive
                ? "bg-slate-100 text-slate-900"
                : "text-slate-600 hover:bg-slate-50 hover:text-slate-900",
        )
      }
    >
      <Icon className="h-4 w-4 shrink-0" />
      <span className="min-w-0 flex-1 truncate">{item.label}</span>
    </NavLink>
  );
}

export function ConsoleShell({ children, title }: { children: ReactNode; title: string }) {
  const navigate = useNavigate();
  const location = useLocation();
  const environment = useConsoleStore((state) => state.environment);
  const setSidebarNavScrollTop = useConsoleStore((state) => state.setSidebarNavScrollTop);
  const auth = useOptionalAuth();
  const isUsingDevToken = auth?.isUsingDevToken ?? true;
  const logoutCurrentUser = auth?.logoutCurrentUser;
  const uploadAvatar = auth?.uploadAvatar;
  const user = auth?.user ?? null;
  const currentOrganization = auth?.currentOrganization ?? null;
  const isWorkspaceRoute = /^\/agents\/[^/]+\/workspace$/.test(location.pathname);
  const isTeamRoute = /^\/teams(?:\/|$)/.test(location.pathname);
  const isRunRoute = /^\/runs(?:\/|$)/.test(location.pathname);
  const isTerminalRoute = location.pathname === "/terminal";
  const isDesktopSettingsRoute = location.pathname === "/desktop" || location.pathname === "/settings/advanced";
  const desktop = isDesktopRuntime();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(isWorkspaceRoute);
  const [isNarrowShell, setIsNarrowShell] = useState(false);
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const [openNavGroups, setOpenNavGroups] = useState<Record<string, boolean>>({});
  const [avatarUploadPending, setAvatarUploadPending] = useState(false);
  const [avatarUploadError, setAvatarUploadError] = useState<string | null>(null);
  const accountMenuRef = useRef<HTMLDivElement>(null);
  const accountMenuButtonRef = useRef<HTMLButtonElement>(null);
  const avatarFileInputRef = useRef<HTMLInputElement>(null);
  const sidebarNavRef = useRef<HTMLElement>(null);
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

  useEffect(() => {
    setAccountMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    const nav = sidebarNavRef.current;
    if (!nav) return;
    const scrollTop = useConsoleStore.getState().sidebarNavScrollTop;
    const frame = window.requestAnimationFrame(() => {
      nav.scrollTop = scrollTop;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [effectiveSidebarCollapsed, location.pathname]);

  useEffect(() => {
    if (!accountMenuOpen) return;
    const handlePointer = (event: MouseEvent | TouchEvent) => {
      const element = accountMenuRef.current;
      if (!element) {
        setAccountMenuOpen(false);
        return;
      }
      const target = event.target;
      if (target instanceof Node && element.contains(target)) return;
      setAccountMenuOpen(false);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setAccountMenuOpen(false);
        accountMenuButtonRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", handlePointer);
    document.addEventListener("touchstart", handlePointer);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointer);
      document.removeEventListener("touchstart", handlePointer);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [accountMenuOpen]);

  const displayName = user?.name || "Dev User";
  const displayEmail = user?.email || "dev-token";
  const displayRole = user?.role || currentOrganization?.role || "engineer";
  const displayOrganization = currentOrganization?.name || currentOrganization?.slug || user?.organization_id || "开发工作区";
  const initials = initialsForName(user?.name, user?.email);
  const avatarDataUrl = user?.avatar_data_url ?? null;

  async function handleLogout() {
    setAccountMenuOpen(false);
    await logoutCurrentUser?.();
    navigate("/login", { replace: true });
  }

  async function handleAvatarSelected(file: File | undefined) {
    if (!file || !uploadAvatar) return;
    setAvatarUploadPending(true);
    setAvatarUploadError(null);
    try {
      const preparedFile = await prepareAvatarUpload(file);
      await uploadAvatar(preparedFile);
    } catch (error) {
      setAvatarUploadError(error instanceof Error ? error.message : "头像上传失败");
    } finally {
      setAvatarUploadPending(false);
      if (avatarFileInputRef.current) {
        avatarFileInputRef.current.value = "";
      }
    }
  }

  if (desktop && isWorkspaceRoute) {
    return (
      <div
        data-testid="desktop-workspace-shell"
        className="flex h-screen min-h-0 min-w-0 overflow-hidden bg-white text-slate-800"
        lang="zh-CN"
        translate="no"
      >
        <FeedbackToastViewport />
        <main className="flex min-h-0 min-w-0 flex-1 flex-col">{children}</main>
      </div>
    );
  }

  if (desktop && (isTeamRoute || isRunRoute || isTerminalRoute || isDesktopSettingsRoute)) {
    return (
      <div
        data-testid="desktop-operation-shell"
        className="flex h-screen min-h-0 min-w-0 overflow-hidden bg-white text-slate-800"
        lang="zh-CN"
        translate="no"
      >
        <FeedbackToastViewport />
        <DesktopOperationRail />
        <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">{children}</main>
      </div>
    );
  }

  return (
    <div
      className="flex h-screen overflow-hidden bg-page text-slate-800"
      lang="zh-CN"
      translate="no"
    >
      <FeedbackToastViewport />
      {!isWorkspaceRoute && !isTeamRoute ? <QuickActionFAB /> : null}
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
        <nav
          ref={sidebarNavRef}
          aria-label="控制台导航"
          onScroll={(event) => {
            const scrollTop = event.currentTarget.scrollTop;
            setSidebarNavScrollTop(scrollTop);
          }}
          className={cn(
            "min-h-0 flex-1 overflow-y-auto",
            effectiveSidebarCollapsed && isTeamRoute ? "px-0 py-2" : "p-2",
          )}
        >
          {(effectiveSidebarCollapsed ? flatConsoleNavItems : null)?.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                title={item.label}
                aria-label={item.label}
                className={({ isActive }) =>
                  cn(
                    "mb-1 flex min-h-11 w-full items-center rounded-md text-[13px]",
                    "justify-center px-0",
                    isActive
                      ? "bg-slate-100 text-slate-900"
                      : "text-slate-600 hover:bg-slate-50 hover:text-slate-900",
                  )
                }
              >
                <Icon className="h-4 w-4 shrink-0" />
              </NavLink>
            );
          })}
          {!effectiveSidebarCollapsed
            ? consoleNavEntries.map((entry) => (
                <ConsoleNavEntryView
                  key={isConsoleNavGroup(entry) ? entry.id : entry.to}
                  entry={entry}
                  pathname={location.pathname}
                  openNavGroups={openNavGroups}
                  setOpenNavGroups={setOpenNavGroups}
                />
              ))
            : null}
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
            <div ref={accountMenuRef} className="relative ml-1">
              <button
                ref={accountMenuButtonRef}
                type="button"
                aria-haspopup="menu"
                aria-expanded={accountMenuOpen}
                aria-label="账号菜单"
                title={displayEmail}
                onClick={() => setAccountMenuOpen((value) => !value)}
                onKeyDown={(event) => {
                  if (event.key !== "ArrowDown" && event.key !== "Enter" && event.key !== " ") return;
                  event.preventDefault();
                  setAccountMenuOpen(true);
                  window.requestAnimationFrame(() => {
                    const firstItem = accountMenuRef.current?.querySelector<HTMLElement>('[role="menuitem"]:not([disabled])');
                    firstItem?.focus();
                  });
                }}
                className="flex h-8 min-w-8 max-w-44 items-center gap-2 rounded-full border border-slate-200 bg-white px-1.5 text-left text-[11px] text-slate-700 shadow-sm transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300 sm:min-w-36 sm:px-2"
              >
                <span className="flex h-6 w-6 shrink-0 items-center justify-center overflow-hidden rounded-full bg-slate-900 text-[10px] font-semibold text-white">
                  {avatarDataUrl ? (
                    <img src={avatarDataUrl} alt="" className="h-full w-full object-cover" />
                  ) : (
                    initials
                  )}
                </span>
                <span className="hidden min-w-0 flex-1 sm:block">
                  <span className="block truncate font-medium text-slate-800">{displayName}</span>
                  {isUsingDevToken ? (
                    <span className="block truncate font-mono text-[10px] text-slate-400">dev-token</span>
                  ) : null}
                </span>
                <ChevronDown className="hidden h-3.5 w-3.5 shrink-0 text-slate-400 sm:block" />
              </button>
              {accountMenuOpen ? (
                <div
                  role="menu"
                  aria-label="账号菜单"
                  onKeyDown={(event) => {
                    const items = Array.from(
                      event.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"]:not([disabled])'),
                    );
                    if (items.length === 0) return;
                    const currentIndex = items.findIndex((item) => item === document.activeElement);
                    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                      event.preventDefault();
                      const delta = event.key === "ArrowDown" ? 1 : -1;
                      const nextIndex = currentIndex < 0 ? 0 : (currentIndex + delta + items.length) % items.length;
                      items[nextIndex]?.focus();
                    }
                    if (event.key === "Home") {
                      event.preventDefault();
                      items[0]?.focus();
                    }
                    if (event.key === "End") {
                      event.preventDefault();
                      items[items.length - 1]?.focus();
                    }
                  }}
                  className="absolute right-0 top-full z-40 mt-2 w-72 overflow-hidden rounded-lg border border-slate-200 bg-white p-1 text-sm shadow-none"
                >
                  <div className="border-b border-slate-100 px-3 py-3">
                    <div className="flex items-center gap-2">
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full bg-slate-900 text-xs font-semibold text-white">
                        {avatarDataUrl ? (
                          <img src={avatarDataUrl} alt="" className="h-full w-full object-cover" />
                        ) : (
                          initials
                        )}
                      </span>
                      <div className="min-w-0">
                        <div className="truncate font-semibold text-slate-900">{displayName}</div>
                        <div className="truncate text-xs text-slate-500">{displayEmail}</div>
                      </div>
                    </div>
                    <div className="mt-3 grid grid-cols-[72px_minmax(0,1fr)] gap-x-2 gap-y-1 text-xs">
                      <span className="text-slate-400">组织</span>
                      <span className="truncate text-slate-700">{displayOrganization}</span>
                      <span className="text-slate-400">角色</span>
                      <span className="truncate font-medium text-slate-700">{displayRole}</span>
                    </div>
                    {isUsingDevToken ? (
                      <div className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2 py-1 text-[11px] font-medium text-amber-700">
                        <UserCircle className="h-3 w-3" />
                        开发令牌会话
                      </div>
                    ) : null}
                  </div>
                  {!isUsingDevToken ? (
                    <div className="border-b border-slate-100 px-3 py-2">
                      <input
                        ref={avatarFileInputRef}
                        type="file"
                        accept="image/png,image/jpeg,image/webp,image/gif"
                        aria-label="上传头像文件"
                        className="hidden"
                        onChange={(event) => void handleAvatarSelected(event.target.files?.[0])}
                      />
                      <button
                        type="button"
                        role="menuitem"
                        className="flex w-full items-center gap-2 rounded-md px-0 py-1.5 text-left text-xs font-medium text-slate-700 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-60"
                        disabled={avatarUploadPending}
                        onClick={() => avatarFileInputRef.current?.click()}
                      >
                        <Camera className="h-3.5 w-3.5 text-slate-500" />
                        {avatarUploadPending ? "上传中..." : "上传头像"}
                      </button>
                      {avatarUploadError ? (
                        <div className="mt-1 rounded-md bg-red-50 px-2 py-1 text-[11px] text-red-700">
                          {avatarUploadError}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  {isUsingDevToken ? (
                    <button
                      type="button"
                      role="menuitem"
                      className="mt-1 flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-xs font-medium text-slate-700 hover:bg-slate-50"
                      onClick={() => {
                        setAccountMenuOpen(false);
                        navigate("/login");
                      }}
                    >
                      <UserRound className="h-3.5 w-3.5 text-slate-500" />
                      使用账号登录
                    </button>
                  ) : (
                    <button
                      type="button"
                      role="menuitem"
                      className="mt-1 flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-xs font-medium text-slate-700 hover:bg-slate-50"
                      onClick={() => void handleLogout()}
                    >
                      <LogOut className="h-3.5 w-3.5 text-slate-500" />
                      退出登录
                    </button>
                  )}
                </div>
              ) : null}
            </div>
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
