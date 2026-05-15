import type { JSX, ReactNode } from "react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  Bot,
  GitBranch,
  MessageSquareText,
  Sparkles,
  Square,
  Wrench,
} from "lucide-react";

import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { useI18n } from "../../../lib/i18n";
import type { ToolMetadata } from "../../tasks/api";
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
  onStop: () => void;
  summaryManager?: ReactNode;
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
  onStop,
  summaryManager = null,
}: WorkspaceShellBarProps): JSX.Element {
  const { text } = useI18n();
  const [toolsOpen, setToolsOpen] = useState(false);
  const toolsPickerRef = useRef<HTMLDivElement | null>(null);
  const runLabel = activeRunId
    ? text("运行详情", "Run Detail")
    : text("运行未创建", "No run yet");
  const toolsChipLabel = text(
    `工具/MCP: ${tools.length} 个可用`,
    `Tools/MCP: ${tools.length} available`,
  );
  const toolsPreviewLabel = formatToolsPreview(tools, text);

  useOutsideClick(toolsPickerRef, () => setToolsOpen(false), toolsOpen);

  return (
    <header className="relative z-30 shrink-0 border-b border-slate-200 bg-white/95 px-3 py-2 backdrop-blur sm:px-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex min-w-[220px] flex-1 items-center gap-2">
          <Link
            to="/agents"
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
            aria-label={text("返回智能体列表", "Back to Agent Studio")}
            title={text("返回智能体列表", "Back to Agent Studio")}
          >
            <ArrowLeft aria-hidden="true" className="h-4 w-4" />
          </Link>
          <div className="min-w-0">
            <span className="inline-flex min-w-0 items-center gap-1.5 text-sm font-semibold text-slate-900">
              <Bot aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-500" />
              <span className="truncate">{agentName}</span>
            </span>
            <div className="hidden text-[11px] leading-4 text-slate-500 sm:block">
              {text("模型 + Harness = 智能体", "Model + Harness = Agent")}
              <span className="mx-1 text-slate-300">·</span>
              {text("工作台", "Workspace")} · {agentId}
            </div>
          </div>
        </div>

        <div className="flex min-w-0 flex-wrap items-center justify-end gap-1.5">
          {summaryManager}

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
                className="absolute left-0 top-full z-40 mt-1.5 w-[min(240px,calc(100vw-2rem))] rounded-lg border border-slate-200 bg-white p-1.5 shadow-lg sm:left-auto sm:right-0"
              >
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

          {isStreaming && (
            <Button
              type="button"
              variant="ghost"
              onClick={onStop}
              aria-label={text("停止生成", "Stop generation")}
              title={text("停止生成", "Stop generation")}
              className="h-8 px-2"
            >
              <Square aria-hidden="true" className="h-3.5 w-3.5" />
              <span className="hidden lg:inline">{text("停止", "Stop")}</span>
            </Button>
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
              <span>{runStatus ?? text("已创建", "Created")}</span>
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

function formatToolsPreview(
  tools: ToolMetadata[],
  text: (zh: string, en: string) => string,
): string {
  if (tools.length === 0) return text("无工具", "No tools");
  const first = tools[0]?.name ?? text("工具", "Tools");
  if (tools.length === 1) return first;
  return `${first} +${tools.length - 1}`;
}
