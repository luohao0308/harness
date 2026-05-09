import { FormEvent, type ReactNode, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  Boxes,
  Braces,
  Check,
  Code2,
  FileCode2,
  GitBranch,
  Layers3,
  Pause,
  Pencil,
  Pin,
  Play,
  Send,
  Shield,
  Sparkles,
  Wrench,
  X,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, Dot, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Textarea } from "../../../components/ui/input";
import { useI18n } from "../../../lib/i18n";
import { cn, formatShortDate } from "../../../lib/utils";
import {
  approveToolApproval,
  getAgent,
  getAgentRunWorkspace,
  getModelSettings,
  getToolRegistry,
  modifyToolApproval,
  rejectToolApproval,
  streamAgentChatRun,
  type AgentChatStreamEvent,
  type AgentRunWorkspace,
  type ToolApproval,
  type ToolCall,
  type ToolMetadata,
} from "../../tasks/api";
import {
  useWorkspaceStore,
  type ConversationArtifact,
  type ConversationNode,
} from "../../../stores/workspaceStore";
import { extractArtifactsFromNode } from "../workspaceArtifacts";

export function AgentWorkspacePage() {
  const { text } = useI18n();
  const { agentId = "default" } = useParams();
  const queryClient = useQueryClient();
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [modifyApprovalId, setModifyApprovalId] = useState<string | null>(null);
  const [modifiedInput, setModifiedInput] = useState("{}");

  const draft = useWorkspaceStore((state) => state.draft);
  const setDraft = useWorkspaceStore((state) => state.setDraft);
  const pinnedNodeIds = useWorkspaceStore((state) => state.pinnedNodeIds);
  const contextWindowTurns = useWorkspaceStore((state) => state.contextWindowTurns);
  const setContextWindowTurns = useWorkspaceStore((state) => state.setContextWindowTurns);
  const activeStream = useWorkspaceStore((state) => state.activeStream);
  const activePath = useWorkspaceStore((state) => state.activePath());
  const appendNode = useWorkspaceStore((state) => state.appendNode);
  const appendContent = useWorkspaceStore((state) => state.appendContent);
  const appendArtifact = useWorkspaceStore((state) => state.appendArtifact);
  const updateNode = useWorkspaceStore((state) => state.updateNode);
  const togglePinned = useWorkspaceStore((state) => state.togglePinned);
  const startEdit = useWorkspaceStore((state) => state.startEdit);
  const getSiblings = useWorkspaceStore((state) => state.getSiblings);
  const switchToBranch = useWorkspaceStore((state) => state.switchToBranch);
  const setActiveStream = useWorkspaceStore((state) => state.setActiveStream);
  const draftFromNodeId = useWorkspaceStore((state) => state.draftFromNodeId);

  const agent = useQuery({ queryKey: ["agents", agentId], queryFn: () => getAgent(agentId) });
  const settings = useQuery({ queryKey: ["settings", "models"], queryFn: getModelSettings });
  const tools = useQuery({ queryKey: ["tools", "registry"], queryFn: getToolRegistry });
  const workspace = useQuery({
    queryKey: ["agent-run-workspace", activeRunId],
    queryFn: () => getAgentRunWorkspace(activeRunId!),
    enabled: Boolean(activeRunId),
    refetchInterval: activeStream ? false : 5000,
  });
  const approve = useMutation({
    mutationFn: (approvalId: string) =>
      approveToolApproval(activeRunId!, approvalId, "Approved from Workspace Pro"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["agent-run-workspace", activeRunId] }),
  });
  const reject = useMutation({
    mutationFn: (approvalId: string) =>
      rejectToolApproval(activeRunId!, approvalId, "Rejected from Workspace Pro"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["agent-run-workspace", activeRunId] }),
  });
  const modify = useMutation({
    mutationFn: ({ approvalId, input }: { approvalId: string; input: Record<string, unknown> }) =>
      modifyToolApproval(activeRunId!, approvalId, input, "Modified from Workspace Pro"),
    onSuccess: () => {
      setModifyApprovalId(null);
      queryClient.invalidateQueries({ queryKey: ["agent-run-workspace", activeRunId] });
    },
  });

  const modelLabel =
    agent.data?.model_provider === "default" || !agent.data
      ? `${settings.data?.default_provider ?? "default"} / ${settings.data?.default_model ?? "default"}`
      : `${agent.data.model_provider} / ${agent.data.model_name}`;
  const contextPreview = useMemo(
    () => buildContextPreview(activePath, pinnedNodeIds, contextWindowTurns),
    [activePath, pinnedNodeIds, contextWindowTurns],
  );
  const artifacts = useMemo(
    () => collectArtifacts(activePath, workspace.data),
    [activePath, workspace.data],
  );
  const usage = useMemo(() => summarizeUsage(activePath, workspace.data), [activePath, workspace.data]);
  const toolMentions = useMemo(
    () => extractToolMentions(draft, tools.data?.items ?? []),
    [draft, tools.data?.items],
  );

  async function submit(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || activeStream) return;

    const userNodeId = appendNode({
      parent_id: null,
      role: "user",
      content,
      state: "done",
      metadata: {},
      tool_calls: [],
      artifacts: [],
    });
    const assistantNodeId = appendNode({
      parent_id: userNodeId,
      role: "assistant",
      content: "",
      state: "streaming",
      metadata: {},
      tool_calls: [],
      artifacts: [],
    });
    setDraft("");
    await runStream({ assistantNodeId, goal: content });
  }

  async function runStream({
    assistantNodeId,
    goal,
    continueFromNodeId,
    partialContent,
  }: {
    assistantNodeId: string;
    goal: string;
    continueFromNodeId?: string;
    partialContent?: string;
  }) {
    const controller = new AbortController();
    setActiveStream({ node_id: assistantNodeId, controller, started_at: performance.now() });
    const startedAt = performance.now();
    try {
      await streamAgentChatRun(
        agentId,
        {
          goal,
          messages: serializeMessages(useWorkspaceStore.getState().activePath()),
          active_leaf_id: useWorkspaceStore.getState().activeLeafId,
          pinned_node_ids: pinnedNodeIds,
          context_window_turns: contextWindowTurns,
          continue_from_node_id: continueFromNodeId,
          partial_assistant_content: partialContent,
          tool_mentions: toolMentions,
        },
        (streamEvent) => handleStreamEvent(assistantNodeId, streamEvent, startedAt),
        controller.signal,
      );
    } catch (error) {
      if (controller.signal.aborted) {
        updateNode(assistantNodeId, { state: "paused" });
      } else {
        updateNode(assistantNodeId, {
          state: "error",
          content: error instanceof Error ? error.message : "stream failed",
        });
      }
    } finally {
      setActiveStream(null);
    }
  }

  function handleStreamEvent(nodeId: string, event: AgentChatStreamEvent, startedAt: number) {
    if (event.type === "think_delta") {
      appendContent(nodeId, `<think>${event.content}</think>`);
      return;
    }
    if (event.type === "delta") {
      appendContent(nodeId, event.content);
      return;
    }
    if (event.type === "tool_call_requested") {
      updateNode(nodeId, {
        tool_calls: [
          ...(useWorkspaceStore.getState().nodesById[nodeId]?.tool_calls ?? []),
          {
            tool_name: event.tool_name,
            source: event.source,
            input_json: event.input_json,
            status: event.status,
          },
        ],
      });
      return;
    }
    if (event.type === "artifact_created") {
      appendArtifact(nodeId, {
        id: `${nodeId}-${event.name}`,
        name: event.name,
        artifact_type: event.artifact_type,
        status: event.status,
        content: event.content,
        run_id: event.run_id,
      });
      return;
    }
    if (event.type === "usage") {
      updateNode(nodeId, {
        metadata: {
          input_tokens: event.input_tokens,
          output_tokens: event.output_tokens,
          cost_usd: event.cost_usd,
          ttfb_ms: event.ttfb_ms,
          duration_ms: event.duration_ms || Math.round(performance.now() - startedAt),
        },
      });
      return;
    }
    if (event.type === "done") {
      setActiveRunId(event.run_id);
      updateNode(nodeId, { state: "done", run_id: event.run_id });
      queryClient.invalidateQueries({ queryKey: ["agent-run-workspace", event.run_id] });
      messagesEndRef.current?.scrollIntoView({ block: "end" });
      return;
    }
    if (event.type === "error") {
      updateNode(nodeId, { state: "error", content: event.message });
    }
  }

  function pauseStream() {
    if (!activeStream) return;
    activeStream.controller.abort();
    updateNode(activeStream.node_id, { state: "paused" });
    setActiveStream(null);
  }

  function continueStream() {
    const paused = [...activePath].reverse().find((node) => node.state === "paused");
    const previousUser = [...activePath].reverse().find((node) => node.role === "user");
    if (!paused || !previousUser || activeStream) return;
    updateNode(paused.id, { state: "streaming" });
    void runStream({
      assistantNodeId: paused.id,
      goal: previousUser.content,
      continueFromNodeId: paused.id,
      partialContent: paused.content,
    });
  }

  function submitModifyApproval() {
    if (!modifyApprovalId) return;
    try {
      const parsed = JSON.parse(modifiedInput) as Record<string, unknown>;
      modify.mutate({ approvalId: modifyApprovalId, input: parsed });
    } catch {
      setModifiedInput('{"error":"invalid json"}');
    }
  }

  return (
    <ConsoleShell title={text("Agent 工作台 Pro", "Agent Workspace Pro")}>
      <div className="grid h-[calc(100vh-3.5rem)] grid-cols-[300px_minmax(520px,1fr)_420px] gap-3 bg-[#f4f6f8] p-3">
        <Explorer
          modelLabel={modelLabel}
          tools={tools.data?.items ?? []}
          pinnedNodes={activePath.filter((node) => pinnedNodeIds.includes(node.id))}
          contextWindowTurns={contextWindowTurns}
          contextPreview={contextPreview}
          onContextWindowChange={setContextWindowTurns}
          onInsertMention={(name) => setDraft(`${draft}${draft.endsWith(" ") ? "" : " "}@${name} `)}
        />

        <main className="min-h-0 overflow-hidden rounded-lg border border-slate-200 bg-white">
          <div className="flex h-full flex-col">
            <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-4 py-3">
              <div>
                <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
                  <Sparkles className="h-4 w-4 text-slate-500" />
                  Workspace Pro
                  <Badge tone="info">Plan-Act</Badge>
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {activeRunId ? `Run ${activeRunId.slice(0, 8)}` : "树状对话 · 可暂停 · 可分支"}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {workspace.data?.run && <Badge tone={statusTone(workspace.data.run.status)}>{workspace.data.run.status}</Badge>}
                {activeRunId && (
                  <Link to={`/runs/${activeRunId}`}>
                    <Button>
                      <GitBranch className="h-3.5 w-3.5" />
                      Run Detail
                    </Button>
                  </Link>
                )}
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
              <div className="mx-auto flex max-w-3xl flex-col gap-5">
                {activePath.length === 0 && <WelcomeMessage />}
                {activePath.map((node) => (
                  <Message
                    key={node.id}
                    node={node}
                    pinned={pinnedNodeIds.includes(node.id)}
                    siblings={getSiblings(node.id)}
                    onPin={() => togglePinned(node.id)}
                    onEdit={() => startEdit(node.id)}
                    onSwitchBranch={(nodeId) => switchToBranch(nodeId)}
                  />
                ))}
                <div ref={messagesEndRef} />
              </div>
            </div>

            <form onSubmit={submit} className="shrink-0 border-t border-slate-100 bg-white p-4">
              <div className="mx-auto max-w-3xl">
                <div className="mb-2 flex items-center justify-between gap-3 text-xs text-slate-600">
                  <div className="flex items-center gap-2">
                    <Dot tone={activeStream ? "running" : "info"} />
                    {draftFromNodeId ? "编辑历史并创建新分支" : "Chat Console"}
                    {toolMentions.length > 0 && <Badge tone="purple">{toolMentions.length} mentions</Badge>}
                  </div>
                  <div className="flex gap-2">
                    <Button type="button" disabled={!activeStream} onClick={pauseStream}>
                      <Pause className="h-3.5 w-3.5" />
                      暂停
                    </Button>
                    <Button type="button" disabled={Boolean(activeStream)} onClick={continueStream}>
                      <Play className="h-3.5 w-3.5" />
                      Continue
                    </Button>
                  </div>
                </div>
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-2 focus-within:border-slate-400">
                  <Textarea
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={(event) => {
                      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                        event.currentTarget.form?.requestSubmit();
                      }
                    }}
                    placeholder="输入目标，使用 @ 唤起工具，例如 @mcp_context_search 或 @read_file"
                    className="min-h-24 resize-none border-0 bg-transparent px-2 py-2 shadow-none focus:border-0 focus:ring-0"
                  />
                  {draft.includes("@") && (
                    <MentionTray tools={tools.data?.items ?? []} onInsert={(name) => setDraft(`${draft}@${name} `)} />
                  )}
                  <div className="flex justify-end">
                    <Button type="submit" variant="primary" className="h-9 px-4" disabled={Boolean(activeStream) || !draft.trim()}>
                      <Send className="h-4 w-4" />
                      发送
                    </Button>
                  </div>
                </div>
              </div>
            </form>
          </div>
        </main>

        <aside className="min-h-0 space-y-3 overflow-y-auto">
          <MetricsPanel usage={usage} workspace={workspace.data} />
          <ArtifactsPanel artifacts={artifacts} />
          <ToolRuntimePanel
            workspace={workspace.data}
            modifyApprovalId={modifyApprovalId}
            modifiedInput={modifiedInput}
            onApprove={(id) => approve.mutate(id)}
            onReject={(id) => reject.mutate(id)}
            onStartModify={(approval) => {
              setModifyApprovalId(approval.id);
              setModifiedInput(JSON.stringify(approval.request_json.input_json ?? {}, null, 2));
            }}
            onModifiedInputChange={setModifiedInput}
            onSubmitModify={submitModifyApproval}
          />
        </aside>
      </div>
    </ConsoleShell>
  );
}

function Explorer({
  modelLabel,
  tools,
  pinnedNodes,
  contextWindowTurns,
  contextPreview,
  onContextWindowChange,
  onInsertMention,
}: {
  modelLabel: string;
  tools: ToolMetadata[];
  pinnedNodes: ConversationNode[];
  contextWindowTurns: number;
  contextPreview: { messageCount: number; estimatedTokens: number };
  onContextWindowChange: (turns: number) => void;
  onInsertMention: (name: string) => void;
}) {
  return (
    <aside className="min-h-0 overflow-y-auto rounded-lg border border-slate-200 bg-white">
      <div className="border-b border-slate-100 p-4">
        <div className="flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-950 text-white">
            <Bot className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-slate-950">Explorer</div>
            <div className="mt-0.5 truncate text-[11px] text-slate-500">{modelLabel}</div>
          </div>
        </div>
      </div>
      <div className="space-y-4 p-3">
        <PanelTitle icon={<Layers3 className="h-3.5 w-3.5" />} label="上下文" />
        <label className="block rounded-md border border-slate-200 bg-slate-50 p-2">
          <div className="mb-2 flex justify-between text-xs">
            <span className="text-slate-500">最近 N 轮</span>
            <span className="font-mono text-slate-900">{contextWindowTurns}</span>
          </div>
          <input
            type="range"
            min={2}
            max={20}
            value={contextWindowTurns}
            onChange={(event) => onContextWindowChange(Number(event.target.value))}
            className="w-full accent-slate-900"
          />
        </label>
        <div className="grid grid-cols-2 gap-2">
          <SmallMetric label="消息" value={contextPreview.messageCount} />
          <SmallMetric label="估算 tokens" value={contextPreview.estimatedTokens} />
        </div>

        <PanelTitle icon={<Pin className="h-3.5 w-3.5" />} label="Pinned" />
        {pinnedNodes.length ? (
          pinnedNodes.map((node) => (
            <div key={node.id} className="rounded-md border border-slate-100 bg-slate-50 p-2 text-xs text-slate-600">
              {node.content.slice(0, 120)}
            </div>
          ))
        ) : (
          <EmptyState label="暂无置顶消息" />
        )}

        <PanelTitle icon={<Wrench className="h-3.5 w-3.5" />} label="Tool Tray" />
        <div className="space-y-2">
          {tools.slice(0, 10).map((tool) => (
            <button
              key={tool.name}
              type="button"
              onClick={() => onInsertMention(tool.name)}
              className="flex w-full items-center justify-between rounded-md border border-slate-100 bg-white px-2 py-2 text-left text-xs hover:bg-slate-50"
            >
              <span className="truncate font-mono text-slate-700">@{tool.name}</span>
              <Badge tone={tool.source === "mcp" ? "purple" : "neutral"}>{tool.source}</Badge>
            </button>
          ))}
        </div>

        <PanelTitle icon={<Boxes className="h-3.5 w-3.5" />} label="Files" />
        <div className="rounded-md border border-slate-100 bg-slate-50 p-2 text-xs text-slate-500">
          本地文件桥接通过 Tool Runtime 和 Sandbox 接入，当前不绕过策略直接读写。
        </div>
      </div>
    </aside>
  );
}

function Message({
  node,
  pinned,
  siblings,
  onPin,
  onEdit,
  onSwitchBranch,
}: {
  node: ConversationNode;
  pinned: boolean;
  siblings: ConversationNode[];
  onPin: () => void;
  onEdit: () => void;
  onSwitchBranch: (nodeId: string) => void;
}) {
  const isUser = node.role === "user";
  const thinkBlocks = extractThinkBlocks(node.content);
  const visibleContent = node.content.replace(/<think>[\s\S]*?<\/think>/g, "").trim();
  return (
    <div className={cn("flex gap-3", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-950 text-white">
          <Sparkles className="h-4 w-4" />
        </div>
      )}
      <div className={cn("min-w-0 max-w-[82%]", isUser && "order-first")}>
        <div
          className={cn(
            "whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm leading-6",
            isUser
              ? "bg-slate-950 text-white"
              : node.state === "error"
                ? "border border-red-200 bg-red-50 text-red-800"
                : "border border-slate-200 bg-slate-50 text-slate-800",
          )}
        >
          {thinkBlocks.map((block, index) => (
            <details key={`${node.id}-think-${index}`} className="mb-2 rounded-md border border-slate-200 bg-white p-2 text-xs text-slate-500">
              <summary className="cursor-pointer font-medium text-slate-700">思考 / Plan trace</summary>
              <div className="mt-2 whitespace-pre-wrap">{block}</div>
            </details>
          ))}
          <span>{visibleContent || (node.state === "streaming" ? "正在生成..." : "")}</span>
          <span className={cn("ml-1 inline-block h-3 w-1 rounded-sm bg-slate-400 align-middle", node.state === "streaming" ? "animate-pulse opacity-100" : "opacity-0")} />
        </div>
        <div className={cn("mt-1 flex flex-wrap items-center gap-2 text-[10px] text-slate-400", isUser && "justify-end")}>
          <span>{formatShortDate(node.created_at)}</span>
          {node.metadata.input_tokens !== undefined && <span>{node.metadata.input_tokens} in</span>}
          {node.metadata.output_tokens !== undefined && <span>{node.metadata.output_tokens} out</span>}
          {node.metadata.duration_ms !== undefined && <span>{node.metadata.duration_ms}ms</span>}
          {siblings.length > 1 && (
            <BranchSwitcher activeNodeId={node.id} siblings={siblings} onSwitchBranch={onSwitchBranch} />
          )}
          <button type="button" onClick={onPin} className={pinned ? "text-slate-900" : "hover:text-slate-700"}>
            Pin
          </button>
          <button type="button" onClick={onEdit} className="hover:text-slate-700">
            Edit & Resend
          </button>
        </div>
      </div>
      {isUser && (
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-200 text-[11px] font-semibold text-slate-700">
          U
        </div>
      )}
    </div>
  );
}

function BranchSwitcher({
  activeNodeId,
  siblings,
  onSwitchBranch,
}: {
  activeNodeId: string;
  siblings: ConversationNode[];
  onSwitchBranch: (nodeId: string) => void;
}) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-1.5 py-0.5">
      <GitBranch className="h-3 w-3" />
      {siblings.map((sibling, index) => (
        <button
          key={sibling.id}
          type="button"
          onClick={() => onSwitchBranch(sibling.id)}
          className={cn(
            "rounded-full px-1.5 py-0.5 font-mono",
            sibling.id === activeNodeId ? "bg-slate-900 text-white" : "text-slate-500 hover:text-slate-900",
          )}
          title={sibling.content.slice(0, 80) || sibling.id}
        >
          {index + 1}
        </button>
      ))}
    </span>
  );
}

function MetricsPanel({ usage, workspace }: { usage: UsageSummary; workspace?: AgentRunWorkspace }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white">
      <Header icon={<Braces className="h-4 w-4" />} title="Metadata" aside={workspace?.run.status ?? "idle"} />
      <div className="grid grid-cols-2 gap-2 p-3">
        <SmallMetric label="Input" value={usage.inputTokens} />
        <SmallMetric label="Output" value={usage.outputTokens} />
        <SmallMetric label="Cost" value={usage.costUsd} />
        <SmallMetric label="Duration" value={`${usage.durationMs}ms`} />
        <SmallMetric label="Model Calls" value={workspace?.model_calls.length ?? 0} />
        <SmallMetric label="Tool Calls" value={workspace?.tool_calls.length ?? 0} />
      </div>
    </section>
  );
}

function ArtifactsPanel({ artifacts }: { artifacts: ConversationArtifact[] }) {
  const [selectedId, setSelectedId] = useState<string | null>(artifacts[0]?.id ?? null);
  const selected = artifacts.find((artifact) => artifact.id === selectedId) ?? artifacts[0];
  return (
    <section className="rounded-lg border border-slate-200 bg-white">
      <Header icon={<FileCode2 className="h-4 w-4" />} title="Artifacts / Preview" aside={String(artifacts.length)} />
      <div className="grid grid-cols-[130px_1fr] border-t border-slate-100">
        <div className="max-h-80 overflow-auto border-r border-slate-100 p-2">
          {artifacts.map((artifact) => (
            <button
              key={artifact.id}
              type="button"
              onClick={() => setSelectedId(artifact.id)}
              className={cn(
                "mb-1 flex w-full items-center gap-1 rounded px-2 py-1 text-left text-xs",
                selected?.id === artifact.id ? "bg-slate-900 text-white" : "hover:bg-slate-50",
              )}
            >
              <Code2 className="h-3 w-3" />
              <span className="truncate">{artifact.name}</span>
            </button>
          ))}
          {artifacts.length === 0 && <EmptyState label="暂无产物" />}
        </div>
        <div className="max-h-80 overflow-auto p-3">
          {selected ? <ArtifactPreview artifact={selected} /> : <EmptyState label="代码、JSON 和 Diff 会在这里渲染" />}
        </div>
      </div>
    </section>
  );
}

function ToolRuntimePanel({
  workspace,
  modifyApprovalId,
  modifiedInput,
  onApprove,
  onReject,
  onStartModify,
  onModifiedInputChange,
  onSubmitModify,
}: {
  workspace?: AgentRunWorkspace;
  modifyApprovalId: string | null;
  modifiedInput: string;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  onStartModify: (approval: ToolApproval) => void;
  onModifiedInputChange: (value: string) => void;
  onSubmitModify: () => void;
}) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white">
      <Header icon={<Shield className="h-4 w-4" />} title="Plan-Act Runtime" aside={`${workspace?.approvals.length ?? 0} approvals`} />
      <div className="space-y-3 p-3">
        {(workspace?.approvals ?? []).map((approval) => (
          <div key={approval.id} className="rounded-md border border-amber-100 bg-amber-50 p-2 text-xs">
            <div className="flex items-center justify-between gap-2">
              <Badge tone={statusTone(approval.status)}>{approval.status}</Badge>
              <span className="font-mono text-amber-900">{approval.risk_level}</span>
            </div>
            <div className="mt-2 text-amber-800">{approval.reason}</div>
            <pre className="mt-2 max-h-24 overflow-auto rounded bg-white p-2 font-mono text-[10px] text-slate-600">
              {JSON.stringify(approval.request_json.input_json ?? {}, null, 2)}
            </pre>
            {approval.status === "PENDING" && (
              <div className="mt-2 flex flex-wrap gap-1">
                <Button onClick={() => onApprove(approval.id)}>
                  <Check className="h-3.5 w-3.5" />
                  Approve
                </Button>
                <Button onClick={() => onReject(approval.id)}>
                  <X className="h-3.5 w-3.5" />
                  Reject
                </Button>
                <Button onClick={() => onStartModify(approval)}>
                  <Pencil className="h-3.5 w-3.5" />
                  Modify
                </Button>
              </div>
            )}
            {modifyApprovalId === approval.id && (
              <div className="mt-2 space-y-2">
                <Textarea value={modifiedInput} onChange={(event) => onModifiedInputChange(event.target.value)} className="min-h-28 font-mono text-xs" />
                <Button onClick={onSubmitModify}>提交修改并批准</Button>
              </div>
            )}
          </div>
        ))}
        <div className="space-y-2">
          {(workspace?.tool_calls ?? []).map((call) => <ToolCallCard key={call.id} call={call} />)}
          {!workspace?.tool_calls.length && <EmptyState label="暂无工具调用" />}
        </div>
      </div>
    </section>
  );
}

function ToolCallCard({ call }: { call: ToolCall }) {
  return (
    <div className="rounded-md border border-slate-100 bg-white p-2 text-xs">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-mono text-slate-800">{call.tool_name}</span>
        <Badge tone={statusTone(call.status)}>{call.status}</Badge>
      </div>
      <div className="mt-1 text-slate-500">{call.duration_ms}ms · {call.risk_level}</div>
      <details className="mt-2">
        <summary className="cursor-pointer text-slate-500">JSON</summary>
        <pre className="mt-1 max-h-32 overflow-auto rounded bg-slate-50 p-2 font-mono text-[10px] text-slate-600">
          {JSON.stringify({ input: call.input_json, output: call.output_json }, null, 2)}
        </pre>
      </details>
    </div>
  );
}

function MentionTray({ tools, onInsert }: { tools: ToolMetadata[]; onInsert: (name: string) => void }) {
  return (
    <div className="mb-2 flex flex-wrap gap-1 px-2">
      {tools.slice(0, 6).map((tool) => (
        <button
          key={tool.name}
          type="button"
          onClick={() => onInsert(tool.name)}
          className="rounded border border-slate-200 bg-white px-2 py-1 font-mono text-xs text-slate-600 hover:bg-slate-50"
        >
          @{tool.name}
        </button>
      ))}
    </div>
  );
}

function ArtifactPreview({ artifact }: { artifact: ConversationArtifact }) {
  const content =
    typeof artifact.content === "string"
      ? artifact.content
      : JSON.stringify(artifact.content, null, 2);
  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-xs">
        <span className="font-mono text-slate-800">{artifact.name}</span>
        <Badge tone="info">{artifact.artifact_type}</Badge>
      </div>
      <pre className="max-h-72 overflow-auto rounded-md border border-slate-100 bg-slate-950 p-3 font-mono text-[11px] leading-5 text-slate-100">
        {content}
      </pre>
    </div>
  );
}

function WelcomeMessage() {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-600">
      这是 Workspace Pro：支持树状分支、暂停/继续、Pin 上下文、Tool Tray、Artifacts 预览和运行元数据监控。
    </div>
  );
}

function Header({ icon, title, aside }: { icon: ReactNode; title: string; aside?: ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">{icon}{title}</div>
      <span className="text-xs text-slate-500">{aside}</span>
    </div>
  );
}

function PanelTitle({ icon, label }: { icon: ReactNode; label: string }) {
  return <div className="flex items-center gap-2 text-xs font-semibold text-slate-800">{icon}{label}</div>;
}

function SmallMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50 p-2">
      <div className="text-[10px] text-slate-500">{label}</div>
      <div className="mt-1 truncate font-mono text-xs text-slate-900">{value}</div>
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return <div className="rounded-md border border-dashed border-slate-200 p-3 text-center text-xs text-slate-400">{label}</div>;
}

function serializeMessages(nodes: ConversationNode[]) {
  return nodes.map((node) => ({
    id: node.id,
    parent_id: node.parent_id,
    children_ids: node.children_ids,
    role: node.role,
    content: node.content,
    state: node.state,
    run_id: node.run_id,
    metadata: node.metadata,
    tool_calls: node.tool_calls,
    artifacts: node.artifacts,
  }));
}

function buildContextPreview(nodes: ConversationNode[], pinnedNodeIds: string[], turns: number) {
  const pinned = nodes.filter((node) => pinnedNodeIds.includes(node.id));
  const recent = nodes.slice(-turns);
  const unique = new Map([...pinned, ...recent].map((node) => [node.id, node]));
  const contentLength = [...unique.values()].reduce((total, node) => total + node.content.length, 0);
  return { messageCount: unique.size, estimatedTokens: Math.max(1, Math.round(contentLength / 4)) };
}

function collectArtifacts(nodes: ConversationNode[], workspace?: AgentRunWorkspace) {
  const nodeArtifacts = nodes.flatMap((node) => node.artifacts);
  const extractedArtifacts = nodes.flatMap((node) => extractArtifactsFromNode(node));
  const planArtifact: ConversationArtifact[] = workspace?.plan
    ? [
        {
          id: `${workspace.plan.id}-plan`,
          name: "plan.json",
          artifact_type: "json",
          status: workspace.plan.status,
          content: workspace.plan.plan_json,
          run_id: workspace.run.id,
        },
      ]
    : [];
  return dedupeArtifacts([...nodeArtifacts, ...extractedArtifacts, ...planArtifact]);
}

function dedupeArtifacts(artifacts: ConversationArtifact[]) {
  const byId = new Map<string, ConversationArtifact>();
  artifacts.forEach((artifact) => byId.set(artifact.id, artifact));
  return [...byId.values()];
}

type UsageSummary = {
  inputTokens: number;
  outputTokens: number;
  costUsd: string;
  durationMs: number;
};

function summarizeUsage(nodes: ConversationNode[], workspace?: AgentRunWorkspace): UsageSummary {
  const nodeInput = nodes.reduce((total, node) => total + Number(node.metadata.input_tokens ?? 0), 0);
  const nodeOutput = nodes.reduce((total, node) => total + Number(node.metadata.output_tokens ?? 0), 0);
  const modelInput = workspace?.model_calls.reduce((total, call) => total + call.prompt_tokens, 0) ?? 0;
  const modelOutput = workspace?.model_calls.reduce((total, call) => total + call.completion_tokens, 0) ?? 0;
  const durationMs = Math.max(
    0,
    ...nodes.map((node) => Number(node.metadata.duration_ms ?? 0)),
    ...(workspace?.model_calls.map((call) => call.duration_ms) ?? []),
  );
  return {
    inputTokens: Math.max(nodeInput, modelInput),
    outputTokens: Math.max(nodeOutput, modelOutput),
    costUsd: "0",
    durationMs,
  };
}

function extractToolMentions(content: string, tools: ToolMetadata[]) {
  const names = new Set((content.match(/@([\w-]+)/g) ?? []).map((item) => item.slice(1)));
  return tools
    .filter((tool) => names.has(tool.name))
    .map((tool) => ({ name: tool.name, source: tool.source, payload: { mention: `@${tool.name}` } }));
}

function extractThinkBlocks(content: string) {
  return [...content.matchAll(/<think>([\s\S]*?)<\/think>/g)].map((match) => match[1].trim());
}
