import { Columns3, GitFork, MessagesSquare } from "lucide-react";

import { cn } from "../../../../lib/utils";

import type { TextFn } from "./types";

export type TeamWorkspaceView = "collaboration" | "graph" | "columns";

export function DesktopTeamViewSwitch({
  value,
  text,
  onChange,
}: {
  value: TeamWorkspaceView;
  text: TextFn;
  onChange: (value: TeamWorkspaceView) => void;
}) {
  const options = [
    { value: "collaboration" as const, label: text("协作", "Collaboration"), icon: MessagesSquare },
    { value: "graph" as const, label: text("任务图", "Task graph"), icon: GitFork },
    { value: "columns" as const, label: text("多列", "Columns"), icon: Columns3 },
  ];

  return (
    <div
      role="group"
      aria-label={text("团队工作区视图", "Team workspace view")}
      className="inline-flex h-8 shrink-0 items-center gap-0.5 rounded-md border border-slate-200 bg-slate-50 p-0.5"
    >
      {options.map((option) => {
        const Icon = option.icon;
        const selected = value === option.value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={selected}
            title={option.label}
            onClick={() => onChange(option.value)}
            className={cn(
              "inline-flex h-6 items-center gap-1 rounded-[5px] px-2 text-[11px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500",
              selected
                ? "bg-white text-slate-950 shadow-sm"
                : "text-slate-500 hover:bg-white/70 hover:text-slate-900",
            )}
          >
            <Icon aria-hidden="true" className="h-3.5 w-3.5" />
            <span>{option.label}</span>
          </button>
        );
      })}
    </div>
  );
}
