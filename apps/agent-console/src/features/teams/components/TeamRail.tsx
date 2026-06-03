import { Link } from "react-router-dom";
import { MessageSquare, Network, Plus, Users } from "lucide-react";

import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { cn } from "../../../lib/utils";
import type { Team } from "../../tasks/api";

export function TeamRail({
  teams,
  activeTeamId,
  onCreate,
  className,
}: {
  teams: Team[];
  activeTeamId?: string;
  onCreate: () => void;
  className?: string;
}) {
  const activeTeams = teams.filter((team) => team.status !== "ARCHIVED");

  return (
    <aside
      className={cn(
        "hidden w-[144px] shrink-0 flex-col border-r border-slate-200 bg-white md:flex xl:w-[152px]",
        className,
      )}
      aria-label="Team rail"
    >
      <div className="flex h-10 items-center justify-between border-b border-slate-200 px-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <Network className="h-4 w-4 shrink-0 text-slate-700" />
          <span className="truncate text-[13px] font-semibold text-slate-950">Team</span>
        </div>
        <Button
          variant="ghost"
          className="h-7 w-7 px-0"
          onClick={onCreate}
          aria-label="新团队"
          title="新团队"
        >
          <Plus className="h-3.5 w-3.5" />
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto px-1.5 py-1.5">
        <div className="space-y-0.5">
          {activeTeams.map((team) => {
            const unreadTotal = Object.values(team.unread_counts).reduce((total, count) => total + count, 0);
            const isActive = team.id === activeTeamId;
            return (
              <Link
                key={team.id}
                to={`/teams/${team.id}`}
                className={cn(
                  "group flex h-8 min-w-0 items-center gap-1.5 rounded-md px-1.5 text-[12px] transition-colors",
                  isActive
                    ? "bg-slate-100 text-slate-950"
                    : "text-slate-600 hover:bg-slate-50 hover:text-slate-950",
                )}
              >
                <span
                  className={cn(
                    "flex h-6 w-6 shrink-0 items-center justify-center rounded-md border",
                    isActive
                      ? "border-slate-300 bg-white text-slate-900"
                      : "border-slate-200 bg-slate-50 text-slate-500",
                  )}
                >
                  <Users className="h-3.5 w-3.5" />
                </span>
                <span className="min-w-0 flex-1 truncate font-medium">{team.name}</span>
                {unreadTotal > 0 ? (
                  <span className="flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full bg-red-600 px-1.5 text-[10px] font-semibold leading-none text-white">
                    {unreadTotal > 99 ? "99+" : unreadTotal}
                  </span>
                ) : null}
              </Link>
            );
          })}
        </div>
      </div>

      <div className="border-t border-slate-200 px-2 py-2">
        <Button className="h-8 w-full justify-center text-xs" onClick={onCreate} aria-label="新团队">
          <Plus className="h-3.5 w-3.5" />
          创建团队
        </Button>
      </div>
    </aside>
  );
}

export function TeamRailMobileStrip({
  teams,
  activeTeamId,
}: {
  teams: Team[];
  activeTeamId?: string;
}) {
  const activeTeams = teams.filter((team) => team.status !== "ARCHIVED");

  if (activeTeams.length === 0) {
    return null;
  }

  return (
    <div aria-hidden="true" className="border-b border-slate-200 bg-white px-2 py-2 md:hidden">
      <div className="flex gap-1 overflow-x-auto">
        {activeTeams.map((team) => {
          const unreadTotal = Object.values(team.unread_counts).reduce((total, count) => total + count, 0);
          return (
            <Link
              key={team.id}
              to={`/teams/${team.id}`}
              className={cn(
                "inline-flex h-8 max-w-48 shrink-0 items-center gap-1.5 rounded-md border px-2 text-xs",
                team.id === activeTeamId
                  ? "border-slate-300 bg-slate-100 text-slate-950"
                  : "border-slate-200 bg-white text-slate-600",
              )}
            >
              <MessageSquare className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{team.name}</span>
              {unreadTotal > 0 ? <Badge tone="warning" className="px-1.5">{unreadTotal}</Badge> : null}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
