import { Bot, Plus } from "lucide-react";

import { Badge } from "../../../../components/ui/badge";
import { Button } from "../../../../components/ui/button";
import { ConfigDialog } from "../../../../components/ui/config-dialog";
import { Input } from "../../../../components/ui/input";
import { MenuSelect } from "../../../../components/ui/menu-select";
import { statusLabel } from "../../../../lib/labels";
import type { AgentDefinition } from "../../../tasks/api";

import type { TextFn } from "./types";

export function TeamAddMemberModal({
  open,
  agents,
  selectedAgentId,
  memberName,
  loading,
  errorMessage,
  submitting,
  text,
  onClose,
  onAgentChange,
  onMemberNameChange,
  onSubmit,
}: {
  open: boolean;
  agents: AgentDefinition[];
  selectedAgentId: string;
  memberName: string;
  loading: boolean;
  errorMessage: string | null;
  submitting: boolean;
  text: TextFn;
  onClose: () => void;
  onAgentChange: (agentId: string) => void;
  onMemberNameChange: (name: string) => void;
  onSubmit: () => void;
}) {
  const selectedAgent = agents.find((agent) => agent.id === selectedAgentId) ?? agents[0] ?? null;
  const agentOptions = agents.map((agent) => ({
    value: agent.id,
    label: agent.name,
    description: agent.description,
    meta: `${agent.model_provider}/${agent.model_name}`,
    leading: <Bot className="h-3.5 w-3.5" />,
  }));
  const canSubmit = Boolean(selectedAgent) && !submitting;

  return (
    <ConfigDialog
      open={open}
      title={text("添加成员", "Add member")}
      description={text("选择一个智能体定义加入当前团队。", "Choose an agent definition to join this team.")}
      onClose={onClose}
      className="max-w-lg"
    >
        <div className="space-y-4">
          <div className="space-y-1.5 text-xs font-medium text-slate-600">
            <div className="flex items-center justify-between gap-2">
              <span>{text("智能体定义", "Agent definition")}</span>
              <Badge tone={selectedAgent ? "success" : errorMessage ? "failed" : "neutral"}>
                {loading
                  ? text("加载中", "Loading")
                  : selectedAgent
                    ? text("已选择", "Selected")
                    : text("请选择", "Select")}
              </Badge>
            </div>
            {agents.length === 0 ? (
              <div className="flex items-center justify-center rounded-md border border-dashed border-slate-200 bg-slate-50/70 px-4 py-5 text-xs text-slate-500">
                {loading
                  ? text("正在加载智能体...", "Loading agents...")
                  : text("没有可用的智能体", "No supported agents installed")}
              </div>
            ) : (
              <MenuSelect
                ariaLabel={text("智能体定义", "Agent definition")}
                value={selectedAgentId}
                onChange={onAgentChange}
                placeholder={text("选择智能体", "Select agent")}
                options={agentOptions}
                buttonClassName="rounded-md border-slate-200 px-3 py-2 shadow-none"
                menuClassName="max-h-72"
              />
            )}
          </div>
          <label className="flex flex-col gap-1.5 text-xs font-medium text-slate-600">
            {text("成员名称", "Member name")}
            <Input
              value={memberName}
              onChange={(event) => onMemberNameChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && canSubmit) {
                  event.preventDefault();
                  onSubmit();
                }
              }}
              placeholder={selectedAgent?.name ?? text("例如：前端工程师", "Example: Frontend engineer")}
            />
          </label>
          {selectedAgent ? (
            <div className="rounded-md border border-slate-100 bg-slate-50/70 p-3 text-xs text-slate-500">
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-1.5 font-medium text-slate-700">
                  <Bot className="h-3.5 w-3.5" />
                  <span className="truncate">{selectedAgent.name}</span>
                </div>
                <Badge tone="success">{statusLabel(selectedAgent.status)}</Badge>
              </div>
              <div className="mt-2 truncate font-mono text-[11px] text-slate-600">
                {selectedAgent.id} · {selectedAgent.model_provider}/{selectedAgent.model_name}
              </div>
            </div>
          ) : null}
          {errorMessage ? <div className="text-xs text-red-600">{errorMessage}</div> : null}
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-200 pt-5">
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            {text("取消", "Cancel")}
          </Button>
          <Button onClick={onSubmit} disabled={!canSubmit}>
            <Plus className="h-3.5 w-3.5" />
            {submitting ? text("添加中", "Adding") : text("添加成员", "Add member")}
          </Button>
        </div>
    </ConfigDialog>
  );
}
