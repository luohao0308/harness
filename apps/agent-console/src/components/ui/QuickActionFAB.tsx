import { useEffect, useMemo, useState } from "react";
import { BarChart3, Bot, Gauge, Plus, Settings2, X } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";

import { cn } from "../../lib/utils";
import { Button } from "./button";

type RouteQuickAction = {
  label: string;
  to: string;
  icon: React.ElementType;
};

type EventQuickAction = {
  label: string;
  icon: React.ElementType;
  eventName: string;
};

type QuickAction = RouteQuickAction | EventQuickAction;

const actions: RouteQuickAction[] = [
  { label: "新建 Agent", to: "/agents", icon: Bot },
  { label: "跑 Demo Task", to: "/onboarding?step=4", icon: Gauge },
  { label: "看 Cost", to: "/observability/cost", icon: BarChart3 },
  { label: "配 LLM", to: "/settings/models", icon: Settings2 },
];

const MODEL_SETTINGS_ADD_CUSTOM_EVENT = "harness:model-settings:add-custom-model";

const ROUTE_ACTIONS: Record<string, RouteQuickAction[]> = {
  "/agents": [{ label: "新建智能体", to: "/agents", icon: Bot }],
  "/runs": [
    { label: "新建运行", to: "/agents/default/workspace", icon: Bot },
    { label: "看 Cost", to: "/observability/cost", icon: BarChart3 },
  ],
  "/knowledge": [
    { label: "上传文档", to: "/knowledge", icon: Plus },
    { label: "配 LLM", to: "/settings/models", icon: Settings2 },
  ],
  "/observability": [
    { label: "看 Cost", to: "/observability/cost", icon: BarChart3 },
    { label: "配 LLM", to: "/settings/models", icon: Settings2 },
  ],
};

export function QuickActionFAB() {
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const visibleActions = useMemo(() => {
    if (location.pathname === "/settings/models") {
      return actions.map((action) =>
        action.to === "/settings/models"
          ? { label: "添加自定义模型", eventName: MODEL_SETTINGS_ADD_CUSTOM_EVENT, icon: Plus }
          : action,
      );
    }

    const exact = ROUTE_ACTIONS[location.pathname];
    if (exact) {
      return exact;
    }

    const prefix = Object.keys(ROUTE_ACTIONS).find((key) => location.pathname.startsWith(key) && key !== "/");
    return prefix ? ROUTE_ACTIONS[prefix] : actions;
  }, [location.pathname]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <div className="pointer-events-none fixed bottom-5 right-5 z-40 flex flex-col items-end gap-2">
      <div
        className={cn(
          "grid gap-2 transition",
          open ? "pointer-events-auto translate-y-0 opacity-100" : "pointer-events-none translate-y-2 opacity-0",
        )}
      >
        {visibleActions.map((action) => {
          const Icon = action.icon;
          const actionKey = "eventName" in action ? action.eventName : action.to;
          return (
            <Button
              key={actionKey}
              className="justify-start bg-white shadow-panel"
              onClick={() => {
                if ("eventName" in action) {
                  window.dispatchEvent(new CustomEvent(action.eventName));
                } else {
                  navigate(action.to);
                }
                setOpen(false);
              }}
            >
              <Icon className="h-3.5 w-3.5" />
              {action.label}
            </Button>
          );
        })}
      </div>
      <button
        type="button"
        aria-label={open ? "关闭快捷操作" : "打开快捷操作"}
        title={open ? "关闭快捷操作" : "打开快捷操作"}
        onClick={() => setOpen((value) => !value)}
        className="pointer-events-auto inline-flex h-11 w-11 items-center justify-center rounded-full border border-slate-200 bg-slate-900 text-white shadow-lg transition hover:bg-slate-800"
      >
        {open ? <X className="h-5 w-5" /> : <Plus className="h-5 w-5" />}
      </button>
    </div>
  );
}
