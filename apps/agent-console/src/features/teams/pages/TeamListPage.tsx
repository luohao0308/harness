import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { Clock3, MessageSquare, Network, Plus, Users } from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card } from "../../../components/ui/card";
import { useI18n } from "../../../lib/i18n";
import { statusLabel } from "../../../lib/labels";
import { formatShortDate } from "../../../lib/utils";
import { listTeams } from "../../tasks/api";
import { TeamRail, TeamRailMobileStrip } from "../components/TeamRail";
import { TeamCreateModal } from "./TeamCreateModal";

export function TeamListPage() {
  const { text } = useI18n();
  const navigate = useNavigate();
  const [createOpen, setCreateOpen] = useState(false);

  const teamsQuery = useQuery({ queryKey: ["teams"], queryFn: listTeams });
  const teams = teamsQuery.data?.items ?? [];

  const activeTeams = teams.filter((team) => team.status !== "ARCHIVED");

  return (
    <ConsoleShell title={text("团队", "Teams")}>
      <div className="flex h-[100vh] min-h-0 overflow-hidden bg-white">
        <TeamRail teams={teams} onCreate={() => setCreateOpen(true)} />
        <main className="flex min-w-0 flex-1 flex-col">
          <TeamRailMobileStrip teams={teams} />
          <div className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white px-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-[13px] font-semibold text-slate-950">
                <Network className="h-4 w-4" />
                <span>{text("团队模式", "Team Mode")}</span>
                <Badge tone="neutral">{activeTeams.length}</Badge>
              </div>
              <div className="mt-0.5 truncate text-[11px] text-slate-500">
                {text("选择左侧团队进入多列协作界面。", "Choose a team to open the multi-column collaboration surface.")}
              </div>
            </div>
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="h-3.5 w-3.5" />
              {text("创建团队", "Create Team")}
            </Button>
          </div>

          <div className="min-h-0 flex-1 overflow-auto bg-slate-50/60 p-3 sm:p-4">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {activeTeams.map((team) => {
                const messageCount = team.messages.length;
                const unreadTotal = Object.values(team.unread_counts).reduce((total, count) => total + count, 0);
                const activeAgentCount = team.agents.filter((agent) => agent.status !== "completed").length;
                return (
                  <Link key={team.id} to={`/teams/${team.id}`} className="block">
                    <Card className="h-full rounded-lg p-4 transition hover:border-slate-300 hover:shadow-md">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-semibold text-slate-950">{team.name}</div>
                          <div className="mt-1 font-mono text-[11px] text-slate-400">{team.id.slice(0, 8)}</div>
                        </div>
                        <Badge tone={team.status === "ACTIVE" ? "success" : "neutral"}>{statusLabel(team.status)}</Badge>
                      </div>
                      <div className="mt-4 grid grid-cols-3 gap-2">
                        <Metric icon={<Users className="h-3.5 w-3.5" />} label={text("成员", "Agents")} value={activeAgentCount} />
                        <Metric icon={<MessageSquare className="h-3.5 w-3.5" />} label={text("消息", "Messages")} value={messageCount} />
                        <Metric icon={<Clock3 className="h-3.5 w-3.5" />} label={text("未读", "Unread")} value={unreadTotal} />
                      </div>
                      <div className="mt-4 flex flex-wrap gap-1.5">
                        {team.agents.slice(0, 4).map((agent) => (
                          <span
                            key={agent.slot_id}
                            className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] text-slate-600"
                          >
                            {agent.role === "leader" ? text("队长", "Leader") : agent.agent_name}
                          </span>
                        ))}
                      </div>
                      <div className="mt-4 text-[11px] text-slate-400">
                        {text("更新时间", "Updated")} {formatShortDate(team.updated_at)}
                      </div>
                    </Card>
                  </Link>
                );
              })}
            </div>

            {!teamsQuery.isLoading && activeTeams.length === 0 ? (
              <Card className="flex min-h-[220px] items-center justify-center p-6 text-center">
                <div>
                  <Network className="mx-auto h-7 w-7 text-slate-300" />
                  <div className="mt-3 text-sm font-semibold text-slate-900">{text("还没有团队", "No teams yet")}</div>
                  <p className="mt-1 text-xs text-slate-500">
                    {text("创建一个团队后，就可以看到队长和成员的多列协作界面。", "Create a team to open the multi-agent collaboration surface.")}
                  </p>
                </div>
              </Card>
            ) : null}
          </div>
          <TeamCreateModal
            open={createOpen}
            onClose={() => setCreateOpen(false)}
            onCreated={(team) => navigate(`/teams/${team.id}`)}
          />
        </main>
      </div>
    </ConsoleShell>
  );
}

function Metric({ icon, label, value }: { icon: ReactNode; label: string; value: number }) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50/70 p-2">
      <div className="flex items-center gap-1 text-[11px] text-slate-500">
        {icon}
        {label}
      </div>
      <div className="mt-1 font-mono text-sm font-semibold text-slate-900">{value}</div>
    </div>
  );
}
