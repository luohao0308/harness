import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Plus, X } from "lucide-react";

import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { MenuSelect } from "../../../components/ui/menu-select";
import { useI18n } from "../../../lib/i18n";
import { createTeam, listAgents, listTeams, type Team } from "../../tasks/api";

export function nextAvailableTeamName(teams: { name: string }[], baseName: string) {
  const existingNames = new Set(teams.map((team) => team.name.trim()));
  if (!existingNames.has(baseName)) {
    return baseName;
  }

  let suffix = 2;
  while (existingNames.has(`${baseName} ${suffix}`)) {
    suffix += 1;
  }
  return `${baseName} ${suffix}`;
}

export function TeamCreateModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (team: Team) => void;
}) {
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const [teamName, setTeamName] = useState<string | null>(null);
  const [leaderAgentId, setLeaderAgentId] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState("");

  const teamsQuery = useQuery({ queryKey: ["teams"], queryFn: listTeams, enabled: open });
  const agentsQuery = useQuery({ queryKey: ["agents"], queryFn: listAgents, enabled: open });
  const teams = teamsQuery.data?.items ?? [];
  const agents = agentsQuery.data?.items ?? [];
  const leaderAgent = useMemo(
    () => agents.find((agent) => agent.id === leaderAgentId) ?? null,
    [agents, leaderAgentId],
  );
  const suggestedTeamName = useMemo(() => nextAvailableTeamName(teams, "Team Mode 协作团队"), [teams]);
  const queriesReady = teamsQuery.isSuccess && agentsQuery.isSuccess;
  const queryError = teamsQuery.error ?? agentsQuery.error;
  const queryErrorMessage = queryError instanceof Error ? queryError.message : null;
  const agentOptions = useMemo(
    () =>
      agents.map((agent) => ({
        value: agent.id,
        label: agent.name,
        description: agent.description,
        meta: `${agent.model_provider}/${agent.model_name}`,
        leading: <Bot className="h-3.5 w-3.5" />,
      })),
    [agents],
  );

  useEffect(() => {
    if (!open) {
      return;
    }
    setTeamName(null);
    setLeaderAgentId(null);
    setWorkspace("");
  }, [open]);

  useEffect(() => {
    if (!open || leaderAgentId || agents.length === 0) {
      return;
    }
    setLeaderAgentId(agents.find((agent) => agent.id === "default")?.id ?? agents[0].id);
  }, [agents, leaderAgentId, open]);

  const createMutation = useMutation({
    mutationFn: () =>
      createTeam({
        name: teamName?.trim() || suggestedTeamName,
        workspace: workspace.trim(),
        workspace_mode: "shared",
        leader_agent_id: leaderAgent?.id ?? "default",
      }),
    onSuccess: async (team) => {
      await queryClient.invalidateQueries({ queryKey: ["teams"] });
      setTeamName(null);
      setLeaderAgentId(null);
      setWorkspace("");
      onCreated(team);
      onClose();
    },
  });

  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/30 p-4">
      <Card
        role="dialog"
        aria-modal="true"
        aria-label={text("创建团队", "Create Team")}
        className="w-full max-w-xl overflow-hidden rounded-xl p-0 shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-5">
          <div>
            <div className="text-lg font-medium text-slate-950">{text("创建团队", "Create Team")}</div>
            <div className="mt-1 text-xs text-slate-500">
              {text("Leader 接收指令、拆解任务，并协调团队成员。", "The leader receives instructions, breaks down work, and coordinates teammates.")}
            </div>
          </div>
          <button
            type="button"
            aria-label={text("关闭", "Close")}
            onClick={onClose}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-900"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 px-6 py-5">
          <label className="flex flex-col gap-1.5 text-xs font-medium text-slate-600">
            {text("团队名称", "Team name")}
            <Input value={teamName ?? suggestedTeamName} onChange={(event) => setTeamName(event.target.value)} />
          </label>
          <div className="space-y-1.5 text-xs font-medium text-slate-600">
            <div className="flex items-center justify-between gap-2">
              <span>{text("Leader Agent", "Leader Agent")}</span>
              <Badge tone={leaderAgent ? "success" : queryErrorMessage ? "failed" : "neutral"}>
                {leaderAgent
                  ? text("已选择", "Selected")
                  : queryErrorMessage
                    ? text("加载失败", "Failed")
                    : text("请选择", "Select")}
              </Badge>
            </div>
            {agents.length === 0 ? (
              <div className="flex items-center justify-center rounded-md border border-dashed border-slate-200 bg-slate-50/70 px-4 py-5 text-xs text-slate-500">
                {text("没有可用的 leader agent", "No supported agents installed")}
              </div>
            ) : (
              <MenuSelect
                ariaLabel={text("Leader Agent", "Leader Agent")}
                value={leaderAgentId ?? ""}
                onChange={setLeaderAgentId}
                placeholder={text("选择团队 Leader", "Select team leader")}
                options={agentOptions}
                buttonClassName="rounded-md border-slate-200 px-3 py-2 shadow-none"
                menuClassName="max-h-72"
              />
            )}
          </div>
          <label className="flex flex-col gap-1.5 text-xs font-medium text-slate-600">
            {text("工作区", "Workspace")}
            <Input
              value={workspace}
              onChange={(event) => setWorkspace(event.target.value)}
              placeholder={text("共享团队工作区路径（可留空）", "Shared workspace path (optional)")}
            />
          </label>
          {leaderAgent ? (
            <div className="rounded-md border border-slate-100 bg-slate-50/70 p-3 text-xs text-slate-500">
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-1.5 font-medium text-slate-700">
                  <Bot className="h-3.5 w-3.5" />
                  <span>{text("Leader Agent 定义", "Leader agent definition")}</span>
                </div>
                <Badge tone="success">{text("可用", "Ready")}</Badge>
              </div>
              <div className="mt-2 truncate font-mono text-[11px] text-slate-600">
                {leaderAgent.id} · {leaderAgent.model_provider}/{leaderAgent.model_name}
              </div>
            </div>
          ) : null}
          {queryErrorMessage ? (
            <div className="text-xs text-red-600">
              {text("创建团队所需数据加载失败：", "Failed to load required team data: ")}
              {queryErrorMessage}
            </div>
          ) : null}
          {createMutation.isError ? (
            <div className="text-xs text-red-600">{(createMutation.error as Error).message}</div>
          ) : null}
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-200 bg-white px-6 py-5">
          <Button variant="secondary" onClick={onClose}>
            {text("取消", "Cancel")}
          </Button>
          <Button
            onClick={() => createMutation.mutate()}
            disabled={createMutation.isPending || !leaderAgent || !queriesReady}
          >
            <Plus className="h-3.5 w-3.5" />
            {createMutation.isPending ? text("创建中", "Creating") : text("创建团队", "Create Team")}
          </Button>
        </div>
      </Card>
    </div>
  );
}
