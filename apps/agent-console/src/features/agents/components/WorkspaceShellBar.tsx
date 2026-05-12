import type { JSX } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  Bot,
  GitBranch,
  MessageSquareText,
  Sparkles,
  Square,
} from "lucide-react";

import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { useI18n } from "../../../lib/i18n";
import type { InspectorSection } from "../lib/types";
import { InspectorMenu } from "./InspectorMenu";

export type WorkspaceShellBarProps = {
  agentId: string;
  agentName: string;
  activeRunId: string | null;
  runStatus?: string;
  isStreaming: boolean;
  onOpenInspector: (section: InspectorSection) => void;
  onStop: () => void;
};

export function WorkspaceShellBar({
  agentId,
  agentName,
  activeRunId,
  runStatus,
  isStreaming,
  onOpenInspector,
  onStop,
}: WorkspaceShellBarProps): JSX.Element {
  const { text } = useI18n();
  const runLabel = activeRunId
    ? text("Run 详情", "Run Detail")
    : text("Run 未创建", "No run yet");

  return (
    <header className="relative z-30 shrink-0 border-b border-slate-200 bg-white/95 px-3 py-2 backdrop-blur sm:px-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex min-w-[220px] flex-1 items-center gap-2">
          <Link
            to="/agents"
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
            aria-label={text("返回 Agent Studio", "Back to Agent Studio")}
            title={text("返回 Agent Studio", "Back to Agent Studio")}
          >
            <ArrowLeft aria-hidden="true" className="h-4 w-4" />
          </Link>
          <div className="min-w-0">
            <span className="inline-flex min-w-0 items-center gap-1.5 text-sm font-semibold text-slate-900">
              <Bot aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-500" />
              <span className="truncate">{agentName}</span>
            </span>
            <div className="hidden text-[11px] leading-4 text-slate-500 sm:block">
              {text("Model + Harness = Agent", "Model + Harness = Agent")}
              <span className="mx-1 text-slate-300">·</span>
              {text("工作台", "Workspace")} · {agentId}
            </div>
          </div>
        </div>

        <div className="flex min-w-0 items-center gap-1.5">
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
              <span className="hidden text-slate-500 lg:inline">Run</span>
              <span>{runStatus ?? text("已创建", "Created")}</span>
            </Link>
          ) : (
            <span
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2 text-xs font-medium text-slate-500"
              aria-label={runLabel}
              title={runLabel}
            >
              <MessageSquareText aria-hidden="true" className="h-3.5 w-3.5" />
              <span className="hidden lg:inline">Run</span>
              <span>{text("待创建", "Idle")}</span>
            </span>
          )}

          <InspectorMenu onOpenInspector={onOpenInspector} />
        </div>
      </div>
    </header>
  );
}
