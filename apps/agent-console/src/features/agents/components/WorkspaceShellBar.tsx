import type { JSX, ReactNode } from "react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  Bot,
  GitBranch,
  Loader2,
  MessageSquareText,
  Monitor,
  Sparkles,
  Wrench,
  X,
} from "lucide-react";

import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { MenuSelect } from "../../../components/ui/menu-select";
import { useI18n } from "../../../lib/i18n";
import { cn } from "../../../lib/utils";
import { statusLabel } from "../../../lib/labels";
import type { AgentDefinition, LocalAgentConnection, ToolMetadata } from "../../tasks/api";
import { useOutsideClick } from "../hooks/useOutsideClick";
import type { InspectorSection } from "../lib/types";
import { InspectorMenu } from "./InspectorMenu";
import type { ModelOption } from "./ModelPicker";

export type WorkspaceShellBarProps = {
  agentId: string;
  agentName: string;
  activeRunId: string | null;
  runStatus?: string;
  tools: ToolMetadata[];
  providers: ModelOption[];
  selectedProviderId: string | null;
  selectedModelId: string | null;
  isStreaming: boolean;
  onModelChange: (providerId: string, modelId: string) => void;
  onInsertToolMention: (toolName: string) => void;
  onOpenInspector: (section: InspectorSection) => void;
  onCreateTeamFromConversation?: () => void;
  isCreatingTeam?: boolean;
  summaryManager?: ReactNode;
  agents?: AgentDefinition[];
  agentsLoading?: boolean;
  onAgentChange?: (agentId: string) => void;
  localAgentEnabled?: boolean;
  localAgentConnections?: LocalAgentConnection[];
  selectedLocalConnectionId?: string | null;
  onLocalAgentTargetChange?: (connectionId: string) => void;
  localAgentControl?: ReactNode;
};

export function WorkspaceShellBar({
  agentId,
  agentName,
  activeRunId,
  runStatus,
  tools,
  isStreaming,
  onInsertToolMention,
  onOpenInspector,
  onCreateTeamFromConversation,
  isCreatingTeam = false,
  summaryManager = null,
  agents = [],
  agentsLoading = false,
  onAgentChange,
  localAgentEnabled = false,
  localAgentConnections = [],
  selectedLocalConnectionId = null,
  onLocalAgentTargetChange,
  localAgentControl = null,
}: WorkspaceShellBarProps): JSX.Element {
  const { text } = useI18n();
  const [toolsOpen, setToolsOpen] = useState(false);
  const toolsPickerRef = useRef<HTMLDivElement | null>(null);
  const runLabel = activeRunId
    ? text("运行详情", "Run Detail")
    : text("运行未创建", "No run yet");
  const runStatusText = runStatus ? statusLabel(runStatus) : text("已创建", "Created");
  const toolsChipLabel = text(
    `工具/MCP（模型上下文协议）: ${tools.length} 个可用`,
    `Tools/MCP: ${tools.length} available`,
  );
  const toolsPreviewLabel = formatToolsPreview(tools, text);
  const agentTargetValue =
    localAgentEnabled && selectedLocalConnectionId !== null
      ? localAgentTargetValue(selectedLocalConnectionId)
      : cloudAgentTargetValue(agentId);
  const cloudAgentOptions =
    agents.length > 0
      ? agents.map((agent) => ({
          value: cloudAgentTargetValue(agent.id),
          label: agent.name,
          description: `${text("工作台", "Workspace")} · ${agent.id}`,
          meta: agent.status === "ACTIVE" ? text("可用", "Active") : agent.status,
          leading: <Bot aria-hidden="true" className="h-3.5 w-3.5" />,
          group: text("智能体", "Agents"),
        }))
      : [
          {
            value: cloudAgentTargetValue(agentId),
            label: agentName,
            description: `${text("工作台", "Workspace")} · ${agentId}`,
            meta: agentsLoading ? text("同步中", "Loading") : undefined,
            leading: <Bot aria-hidden="true" className="h-3.5 w-3.5" />,
            group: text("智能体", "Agents"),
          },
        ];
  const usableLocalAgentConnections = localAgentConnections.filter(isUsableLocalAgentConnection);
  const localAgentOptions = usableLocalAgentConnections.map((connection) => ({
    value: localAgentTargetValue(connection.id),
    label: connection.display_name,
    description: localAgentOptionDescription(connection),
    meta: localAgentStatusLabel(connection.status),
    leading: (
      <Monitor
        aria-hidden="true"
        className={cn(
          "h-3.5 w-3.5",
          connection.status === "online" || connection.status === "busy"
            ? "text-emerald-600"
            : connection.status === "offline"
              ? "text-amber-600"
              : "text-slate-500",
        )}
      />
    ),
    group: text("本地 Agent", "Local Agents"),
  }));
  const agentOptions = [...cloudAgentOptions, ...localAgentOptions];

  useOutsideClick(toolsPickerRef, () => setToolsOpen(false), toolsOpen);

  return (
    <header className="relative z-30 shrink-0 border-b border-slate-200 bg-white/95 px-3 py-2 backdrop-blur sm:px-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex min-w-0 flex-[1_1_16rem] items-start gap-2 sm:min-w-[260px]">
          <Link
            to="/agents"
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
            aria-label={text("返回智能体列表", "Back to Agent Studio")}
            title={text("返回智能体列表", "Back to Agent Studio")}
          >
            <ArrowLeft aria-hidden="true" className="h-4 w-4" />
          </Link>
          <div className="min-w-0 flex-1">
            {onAgentChange ? (
              <MenuSelect
                ariaLabel={text("切换智能体或本地 Agent", "Switch Agent or Local Agent")}
                value={agentTargetValue}
                options={agentOptions}
                onChange={(value) => {
                  if (value.startsWith("local:")) {
                    onLocalAgentTargetChange?.(value.slice("local:".length));
                    return;
                  }
                  if (value.startsWith("agent:")) {
                    onAgentChange(value.slice("agent:".length));
                  }
                }}
                size="compact"
                className="w-full max-w-[20rem] min-w-0"
                buttonClassName="h-9 rounded-lg border-transparent bg-transparent px-1.5 py-1 shadow-none hover:border-slate-200"
                menuClassName="left-auto right-0 w-[min(18rem,calc(100vw-3rem))] max-w-[calc(100vw-3rem)]"
              />
            ) : (
              <span className="inline-flex min-w-0 items-center gap-1.5 text-sm font-semibold text-slate-900">
                <Bot aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-500" />
                <span className="truncate">{agentName}</span>
              </span>
            )}
            <div className="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-[11px] leading-4 text-slate-500">
              <span className="hidden sm:inline">
                {text("模型加运行平台组成智能体", "Model + Harness = Agent")}
              </span>
              <span className="hidden text-slate-300 sm:inline">·</span>
              {localAgentControl}
            </div>
          </div>
        </div>

        <div className="flex min-w-0 flex-wrap items-center justify-end gap-1.5">
          {summaryManager}

          {onCreateTeamFromConversation ? (
            <Button
              type="button"
              variant="ghost"
              onClick={onCreateTeamFromConversation}
              disabled={isCreatingTeam}
              aria-label={text("新开团队模式", "Create Team Mode")}
              title={text("新开团队模式", "Create Team Mode")}
              className="h-8 px-2"
            >
              {isCreatingTeam ? (
                <Loader2 aria-hidden="true" className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <GitBranch aria-hidden="true" className="h-3.5 w-3.5" />
              )}
              <span className="hidden lg:inline">{text("团队模式", "Team Mode")}</span>
            </Button>
          ) : null}

          <div ref={toolsPickerRef} className="relative">
            <button
              type="button"
              onClick={() => setToolsOpen((open) => !open)}
              aria-label={toolsChipLabel}
              aria-haspopup="dialog"
              aria-expanded={toolsOpen}
              title={toolsChipLabel}
              className="inline-flex h-8 max-w-[12rem] items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
            >
              <Wrench aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-slate-500" />
              <span className="min-w-0 truncate">{toolsPreviewLabel}</span>
            </button>

            {toolsOpen && (
              <div
                role="dialog"
                aria-modal="false"
                aria-label={text("工具", "Tools")}
                className="absolute right-0 top-full z-40 mt-1.5 w-[min(280px,calc(100vw-1rem))] rounded-2xl border border-slate-200 bg-white p-2 shadow-none"
              >
                <div className="mb-2 flex items-start justify-between gap-2 border-b border-slate-100 px-1 pb-2">
                  <div className="min-w-0">
                    <div className="text-xs font-semibold text-slate-900">
                      {text("工具快捷插入", "Quick tool insert")}
                    </div>
                    <div className="mt-0.5 text-[11px] leading-4 text-slate-500">
                      {text(
                        "点击任一能力名，立即把 @工具 名称写入输入框。",
                        "Click a capability to insert its @mention into the composer.",
                      )}
                    </div>
                  </div>
                  <button
                    type="button"
                    aria-label={text("关闭工具列表", "Close tool list")}
                    onClick={() => setToolsOpen(false)}
                    className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
                  >
                    <X aria-hidden="true" className="h-4 w-4" />
                  </button>
                </div>
                <div className="max-h-44 overflow-y-auto">
                  {tools.length === 0 ? (
                    <p className="px-2 py-1.5 text-xs text-slate-500">
                      {text("暂无工具功能", "No tool capabilities")}
                    </p>
                  ) : (
                    tools.map((tool) => (
                      <button
                        key={`${tool.source ?? "tool"}:${tool.name}`}
                        type="button"
                        onClick={() => {
                          onInsertToolMention(tool.name);
                          setToolsOpen(false);
                        }}
                        className="block w-full rounded-md px-1.5 py-1 text-left text-xs text-slate-700 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
                      >
                        <span className="block truncate font-mono">@{tool.name}</span>
                        <span className="block truncate text-[11px] text-slate-500">
                          {tool.description || tool.category}
                        </span>
                      </button>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          {isStreaming && (
            <Badge tone="warning" className="shrink-0">
              <Sparkles aria-hidden="true" className="h-3 w-3" />
              {text("生成中", "Streaming")}
            </Badge>
          )}

          {activeRunId ? (
            <Link
              to={`/runs/${activeRunId}`}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
              aria-label={runLabel}
              title={runLabel}
            >
              <GitBranch aria-hidden="true" className="h-3.5 w-3.5" />
              <span className="hidden text-slate-500 lg:inline">运行</span>
              <span>{runStatusText}</span>
            </Link>
          ) : (
            <span
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2 text-xs font-medium text-slate-500"
              aria-label={runLabel}
              title={runLabel}
            >
              <MessageSquareText aria-hidden="true" className="h-3.5 w-3.5" />
              <span className="hidden lg:inline">运行</span>
              <span>{text("待创建", "Idle")}</span>
            </span>
          )}

          <InspectorMenu onOpenInspector={onOpenInspector} />
        </div>
      </div>
    </header>
  );
}

function cloudAgentTargetValue(agentId: string): string {
  return `agent:${agentId}`;
}

function localAgentTargetValue(connectionId: string): string {
  return `local:${connectionId}`;
}

function isUsableLocalAgentConnection(connection: LocalAgentConnection): boolean {
  return (
    connection.status !== "revoked" &&
    connection.status !== "pending_confirmation" &&
    connection.onboarding_confirmed === true
  );
}

function localAgentOptionDescription(connection: LocalAgentConnection): string {
  if (
    connection.adapter_kind === "claude_code" &&
    connection.capabilities_json.permission_bridge === "harness_local_tool_request_v1"
  ) {
    return "Claude Code · 权限桥";
  }
  if (connection.adapter_kind === "claude_code") {
    return "Claude Code · 对话模式";
  }
  return `本地连接 · ${connection.adapter_kind}`;
}

function localAgentStatusLabel(status: string): string {
  switch (status) {
    case "online":
      return "在线";
    case "busy":
      return "执行中";
    case "offline":
      return "离线";
    case "revoked":
      return "已撤销";
    default:
      return status || "未知";
  }
}

function formatToolsPreview(
  tools: ToolMetadata[],
  text: (zh: string, en: string) => string,
): string {
  if (tools.length === 0) return text("无工具", "No tools");
  const first = tools[0]?.name ?? text("工具", "Tools");
  if (tools.length === 1) return first;
  return `${first} +${tools.length - 1}`;
}
