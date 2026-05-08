import type { FormEvent, ReactNode } from "react";
import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot, Boxes, Brain, CheckCircle2, GitBranch, Play, Send, Shield } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { Textarea } from "../../../components/ui/input";
import { useI18n } from "../../../lib/i18n";
import { executionModeLabel, riskLabel, statusLabel } from "../../../lib/labels";
import {
  executeAgentRun,
  executeAgentOrchestration,
  enqueueAgentOrchestration,
  autoWithAgent,
  createAgentSession,
  getModelSettings,
  getAgent,
  orchestrateAgentRun,
  planWithAgent,
  sendAgentMessage,
  type AgentAssignment,
  type AgentMessage,
  type AgentSession,
  type AgentPlanResult,
  type TaskPlanStep,
} from "../../tasks/api";

const modes = ["Chat", "Plan", "Execute", "Auto"] as const;
type AgentMode = (typeof modes)[number];

export function AgentWorkspacePage() {
  const { text } = useI18n();
  const { agentId = "default" } = useParams();
  const [mode, setMode] = useState<AgentMode>("Plan");
  const [goal, setGoal] = useState(
    "帮我分析这个项目，先只做目标分解与规划，不要执行工具。",
  );
  const [chatSession, setChatSession] = useState<AgentSession | null>(null);
  const [chatMessages, setChatMessages] = useState<AgentMessage[]>([]);
  const agent = useQuery({ queryKey: ["agents", agentId], queryFn: () => getAgent(agentId) });
  const settings = useQuery({ queryKey: ["settings", "models"], queryFn: getModelSettings });
  const planMutation = useMutation({
    mutationFn: () =>
      planWithAgent({
        agent_id: agentId,
        goal,
        model_provider: "default",
        model_name: "default",
        max_runtime_seconds: 1800,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: false,
      }),
  });
  const executeMutation = useMutation({
    mutationFn: (runId: string) => executeAgentRun(runId),
  });
  const orchestrateMutation = useMutation({
    mutationFn: (runId: string) => orchestrateAgentRun(runId),
  });
  const executeOrchestrationMutation = useMutation({
    mutationFn: (runId: string) => executeAgentOrchestration(runId),
  });
  const enqueueOrchestrationMutation = useMutation({
    mutationFn: (runId: string) => enqueueAgentOrchestration(runId),
  });
  const chatMutation = useMutation({
    mutationFn: async () => {
      const session =
        chatSession ?? (await createAgentSession(agentId, goal.trim().slice(0, 48) || "Agent Chat"));
      const result = await sendAgentMessage(session.id, goal);
      return result;
    },
    onSuccess: (result) => {
      setChatSession(result.session);
      setChatMessages((messages) => [...messages, ...result.messages]);
    },
  });
  const autoMutation = useMutation({
    mutationFn: () =>
      autoWithAgent({
        agent_id: agentId,
        goal,
        model_provider: "default",
        model_name: "default",
        max_runtime_seconds: 1800,
        max_subagents: 5,
        enable_sandbox: true,
        enable_network: false,
      }),
  });
  const agentModel =
    agent.data?.model_provider === "default" || !agent.data
      ? `${settings.data?.default_provider ?? "default"} / ${settings.data?.default_model ?? "default"}`
      : `${agent.data.model_provider} / ${agent.data.model_name}`;
  const run = planMutation.data ?? autoMutation.data;
  const executedRun = executeMutation.data ?? autoMutation.data?.task;
  const orchestration =
    executeOrchestrationMutation.data ??
    enqueueOrchestrationMutation.data ??
    orchestrateMutation.data ??
    autoMutation.data?.orchestration;
  const currentRunStatus = executedRun?.status ?? run?.task.status;
  const canPlan = mode === "Plan" && goal.trim().length > 0;
  const canExecute =
    Boolean(run) &&
    currentRunStatus === "PLANNED" &&
    mode === "Execute" &&
    !executeMutation.isPending;
  const summary = useMemo(() => planSummary(run), [run]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (canPlan) {
      planMutation.mutate();
      return;
    }
    if (mode === "Chat" && goal.trim().length > 0) {
      chatMutation.mutate();
      return;
    }
    if (mode === "Auto" && goal.trim().length > 0) {
      autoMutation.mutate();
      return;
    }
    if (canExecute && run) {
      executeMutation.mutate(run.run_id);
    }
  }

  return (
    <ConsoleShell title={text("Agent 工作台", "Agent Workspace")}>
      <div className="grid grid-cols-12 gap-4 p-4">
        <section className="col-span-8 space-y-4">
          <Card>
            <CardHeader>
              <div>
                <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                  <Bot className="h-4 w-4" /> {agent.data?.name ?? agentLabel(agentId)}
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {agent.data?.description ??
                    text("这是 Agent 主入口。Plan 模式只做目标分解，不执行工具。", "This is the Agent entry point. Plan mode decomposes the goal without executing tools.")}
                </div>
              </div>
              <div className="text-right text-[11px] text-slate-500">
                <div>{text("默认模型", "Default model")}</div>
                <Link to="/settings/models" className="font-mono text-slate-800 hover:text-slate-950">
                  {agentModel}
                </Link>
              </div>
            </CardHeader>
            <div className="border-t border-slate-100 p-3">
              <div className="inline-flex rounded-md border border-slate-200 bg-slate-50 p-1">
                {modes.map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => setMode(item)}
                    className={`h-8 rounded px-3 text-xs font-medium transition ${
                      mode === item
                        ? "bg-white text-slate-950 shadow-sm"
                        : "text-slate-500 hover:text-slate-900"
                    }`}
                  >
                    {modeLabel(item)}
                  </button>
                ))}
              </div>
            </div>
          </Card>

          <Card>
            <div className="space-y-4 p-4">
              {chatMessages.map((message) => (
                <Message
                  key={message.id}
                  role={message.role === "user" ? "user" : "agent"}
                  content={message.content}
                />
              ))}
              {mode !== "Chat" && (
                <Message role="user" content={goal || text("输入你的目标...", "Enter your goal...")} />
              )}
              {chatMutation.isPending && (
                <Message
                  role="agent"
                  content={text("我正在写入 Agent Session 并生成回复...", "Writing to the Agent Session and generating a reply...")}
                />
              )}
              {planMutation.isPending && (
                <Message
                  role="agent"
                  content={text("我正在进入 Plan 模式，生成结构化目标分解...", "Entering Plan mode and generating a structured plan...")}
                />
              )}
              {run && (
                <Message
                  role="agent"
                  content={`${run.message} ${text("切换到 Execute 模式即可确认执行这个 Run。", "Switch to Execute mode to run this plan.")}`}
                />
              )}
              {executeMutation.isPending && (
                <Message
                  role="agent"
                  content={text("我正在执行已确认的计划，步骤、工具和事件会写入同一个 Run。", "Executing the confirmed plan in the same Run with steps, tools, and events.")}
                />
              )}
              {executedRun && (
                <Message
                  role="agent"
                  content={text(
                    `执行完成，当前 Run 状态：${statusLabel(executedRun.status)}。`,
                    `Execution finished. Run status: ${statusLabel(executedRun.status)}.`,
                  )}
                />
              )}
              {orchestrateMutation.data && (
                <Message
                  role="agent"
                  content={`${orchestrateMutation.data.message} ${text("右侧会显示参与协作的具名 Agent。", "Named collaborating Agents are shown on the right.")}`}
                />
              )}
              {executeOrchestrationMutation.data && (
                <Message
                  role="agent"
                  content={`${executeOrchestrationMutation.data.message} ${text("Reducer 输出已写入 reviewer assignment。", "Reducer output was written to the reviewer assignment.")}`}
                />
              )}
              {enqueueOrchestrationMutation.data && (
                <Message
                  role="agent"
                  content={`${enqueueOrchestrationMutation.data.message} ${text("Worker 会异步接管 queued assignments。", "Workers will asynchronously take queued assignments.")}`}
                />
              )}
              {autoMutation.data && (
                <Message role="agent" content={autoMutation.data.message} />
              )}
              {!run && !planMutation.isPending && chatMessages.length === 0 && (
                <Message
                  role="agent"
                  content={text(
                    "Chat 会保存到 Agent Session；选择 Plan 模式后，我会拆解目标、标注风险、工具意图和是否需要 Subagent/Sandbox。",
                    "Chat is persisted to an Agent Session; in Plan mode I decompose the goal, label risk, tool intent, and whether Subagents/Sandbox are needed.",
                  )}
                />
              )}
            </div>
            <form onSubmit={submit} className="border-t border-slate-100 p-3">
              <Textarea
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
                className="min-h-24"
                placeholder={text("告诉 Agent 你想完成什么...", "Tell the Agent what you want done...")}
              />
              <div className="mt-3 flex items-center justify-between">
                <span className="text-xs text-slate-500">
                  {mode === "Plan"
                    ? text("Plan 模式不会执行工具、沙箱或 Subagent。", "Plan mode will not run tools, sandboxes, or subagents.")
                    : mode === "Execute"
                      ? text("Execute 模式会执行已生成计划，不会重新规划。", "Execute mode runs the generated plan without replanning.")
                      : mode === "Chat"
                        ? text("Chat 模式会写入 Agent Session。", "Chat mode writes to an Agent Session.")
                        : text("Auto 模式会自动规划、编排并执行。", "Auto mode plans, orchestrates, and executes automatically.")}
                </span>
                <div className="flex items-center gap-2">
                  {run && (
                    <Link to={`/tasks/${run.run_id}`}>
                      <Button type="button">
                        <Play className="h-3.5 w-3.5" /> {text("打开 Run 详情", "Open Run")}
                      </Button>
                    </Link>
                  )}
                  {run && (
                    <Button
                      type="button"
                      onClick={() => orchestrateMutation.mutate(run.run_id)}
                      disabled={orchestrateMutation.isPending}
                    >
                      <GitBranch className="h-3.5 w-3.5" />
                      {orchestrateMutation.isPending
                        ? text("编排中...", "Orchestrating...")
                        : text("编排 Agent", "Orchestrate")}
                    </Button>
                  )}
                  {orchestration && run && (
                    <Button
                      type="button"
                      onClick={() => executeOrchestrationMutation.mutate(run.run_id)}
                      disabled={executeOrchestrationMutation.isPending}
                    >
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      {executeOrchestrationMutation.isPending
                        ? text("运行中...", "Running...")
                        : text("运行编排", "Run Orchestration")}
                    </Button>
                  )}
                  {orchestration && run && (
                    <Button
                      type="button"
                      onClick={() => enqueueOrchestrationMutation.mutate(run.run_id)}
                      disabled={enqueueOrchestrationMutation.isPending}
                    >
                      <GitBranch className="h-3.5 w-3.5" />
                      {enqueueOrchestrationMutation.isPending
                        ? text("入队中...", "Queueing...")
                        : text("入队运行", "Queue Run")}
                    </Button>
                  )}
                  {mode === "Chat" ? (
                    <Button type="submit" variant="primary" disabled={goal.trim().length === 0 || chatMutation.isPending}>
                      <Send className="h-3.5 w-3.5" />
                      {chatMutation.isPending ? text("发送中...", "Sending...") : text("发送", "Send")}
                    </Button>
                  ) : mode === "Auto" ? (
                    <Button type="submit" variant="primary" disabled={goal.trim().length === 0 || autoMutation.isPending}>
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      {autoMutation.isPending ? text("自动运行中...", "Running Auto...") : text("自动运行", "Run Auto")}
                    </Button>
                  ) : mode === "Execute" ? (
                    <Button type="submit" variant="primary" disabled={!canExecute}>
                      <Play className="h-3.5 w-3.5" />
                      {executeMutation.isPending ? text("执行中...", "Executing...") : text("执行计划", "Execute Plan")}
                    </Button>
                  ) : (
                    <Button type="submit" variant="primary" disabled={!canPlan || planMutation.isPending}>
                      <Send className="h-3.5 w-3.5" />
                      {planMutation.isPending ? text("规划中...", "Planning...") : text("生成计划", "Generate Plan")}
                    </Button>
                  )}
                </div>
              </div>
              {planMutation.error && (
                <div className="mt-2 rounded border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-700">
                  {planMutation.error instanceof Error ? planMutation.error.message : text("规划失败", "Planning failed")}
                </div>
              )}
              {chatMutation.error && (
                <div className="mt-2 rounded border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-700">
                  {chatMutation.error instanceof Error ? chatMutation.error.message : text("发送失败", "Send failed")}
                </div>
              )}
              {autoMutation.error && (
                <div className="mt-2 rounded border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-700">
                  {autoMutation.error instanceof Error ? autoMutation.error.message : text("Auto 失败", "Auto failed")}
                </div>
              )}
              {executeMutation.error && (
                <div className="mt-2 rounded border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-700">
                  {executeMutation.error instanceof Error ? executeMutation.error.message : text("执行失败", "Execution failed")}
                </div>
              )}
              {orchestrateMutation.error && (
                <div className="mt-2 rounded border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-700">
                  {orchestrateMutation.error instanceof Error ? orchestrateMutation.error.message : text("编排失败", "Orchestration failed")}
                </div>
              )}
              {executeOrchestrationMutation.error && (
                <div className="mt-2 rounded border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-700">
                  {executeOrchestrationMutation.error instanceof Error ? executeOrchestrationMutation.error.message : text("运行编排失败", "Run orchestration failed")}
                </div>
              )}
              {enqueueOrchestrationMutation.error && (
                <div className="mt-2 rounded border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-700">
                  {enqueueOrchestrationMutation.error instanceof Error ? enqueueOrchestrationMutation.error.message : text("入队失败", "Queue failed")}
                </div>
              )}
            </form>
          </Card>
        </section>

        <aside className="col-span-4 space-y-4">
          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Brain className="h-4 w-4" /> {text("Plan 结果", "Plan Result")}
              </div>
              {run && (
                <Link to={`/tasks/${run.run_id}`} className="font-mono text-[11px] text-slate-500 hover:text-slate-900">
                  {run.run_id.slice(0, 8)}
                </Link>
              )}
            </CardHeader>
            {run ? (
              <div className="space-y-3 p-3">
                <div className="grid grid-cols-3 gap-2 text-xs">
                  <Metric label={text("步骤", "Steps")} value={String(summary.steps)} />
                  <Metric label={text("异步", "Async")} value={String(summary.asyncSteps)} />
                  <Metric
                    label={text("状态", "Status")}
                    value={currentRunStatus ? statusLabel(currentRunStatus) : String(summary.sandboxSteps)}
                  />
                </div>
                <div className="space-y-2">
                  {run.plan.steps.map((step, index) => (
                    <PlanStepCard key={step.step_key} step={step} index={index} />
                  ))}
                </div>
              </div>
            ) : (
              <div className="p-4 text-xs text-slate-500">
                {text("生成计划后，结构化步骤会显示在这里。", "After planning, structured steps appear here.")}
              </div>
            )}
          </Card>
          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Shield className="h-4 w-4" /> {text("运行时能力", "Runtime Capabilities")}
              </div>
            </CardHeader>
            <div className="grid gap-2 p-3 text-xs text-slate-600">
              <Capability icon={<Brain className="h-3.5 w-3.5" />} label="Planner" value={text("Plan 模式显式调用", "Explicit in Plan mode")} />
              <Capability icon={<Boxes className="h-3.5 w-3.5" />} label="Sandbox" value={text("Execute/Auto 时自动分配", "Allocated during Execute/Auto")} />
              <Capability icon={<GitBranch className="h-3.5 w-3.5" />} label="Subagent" value={text("异步步骤自动派生", "Spawned for async steps")} />
              <Capability icon={<CheckCircle2 className="h-3.5 w-3.5" />} label="Event Sourcing" value={text("Plan 也写审计事件", "Plan writes audit events")} />
            </div>
          </Card>
          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <GitBranch className="h-4 w-4" /> {text("多 Agent 编排", "Multi-agent Orchestration")}
              </div>
              {orchestration && (
                <span className="font-mono text-[11px] text-slate-500">
                  {orchestration.strategy}
                </span>
              )}
            </CardHeader>
            {orchestration ? (
              <div className="space-y-2 p-3">
                <div className="grid grid-cols-2 gap-2">
                  <Metric
                    label={text("Assignments", "Assignments")}
                    value={String(orchestration.assignments.length)}
                  />
                  <Metric
                    label={text("Handoffs", "Handoffs")}
                    value={String(orchestration.handoffs.length)}
                  />
                </div>
                {orchestration.routing_reasoning && (
                  <div className="rounded border border-cyan-100 bg-cyan-50 px-2 py-1.5 text-[11px] leading-4 text-cyan-800">
                    {orchestration.routing_reasoning}
                  </div>
                )}
                {orchestration.assignments.map((assignment) => (
                  <AssignmentRow key={assignment.id} assignment={assignment} />
                ))}
              </div>
            ) : (
              <div className="p-4 text-xs text-slate-500">
                {text(
                  "生成计划后点击“编排 Agent”，Router 会选择具名 Agent 并创建 assignments。",
                  "After planning, click Orchestrate to let the Router create named Agent assignments.",
                )}
              </div>
            )}
          </Card>
        </aside>
      </div>
    </ConsoleShell>
  );
}

function Message({ role, content }: { role: "user" | "agent"; content: string }) {
  return (
    <div className={`flex ${role === "user" ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-md border px-3 py-2 text-sm ${
          role === "user"
            ? "border-slate-900 bg-slate-900 text-white"
            : "border-slate-200 bg-white text-slate-700"
        }`}
      >
        {content}
      </div>
    </div>
  );
}

function PlanStepCard({ step, index }: { step: TaskPlanStep; index: number }) {
  return (
    <div className="rounded-md border border-slate-100 bg-white p-2">
      <div className="flex items-start gap-2">
        <span className="w-5 font-mono text-[11px] text-slate-400">{index + 1}</span>
        <div className="min-w-0 flex-1">
          <div className="truncate font-mono text-xs text-slate-900">{step.step_key}</div>
          <div className="mt-1 text-xs text-slate-600">{step.description}</div>
          <div className="mt-2 flex flex-wrap gap-1">
            <Badge tone={step.execution_mode === "async" ? "purple" : "neutral"}>
              {executionModeLabel(step.execution_mode)}
            </Badge>
            <Badge tone={step.requires_sandbox ? "warning" : "neutral"}>
              {step.requires_sandbox ? "Sandbox" : "No sandbox"}
            </Badge>
            <Badge tone={step.can_spawn_subagent ? "purple" : "neutral"}>
              {step.can_spawn_subagent ? "Subagent" : "Sync"}
            </Badge>
            <Badge tone="neutral">{riskLabel(step.risk_level)}</Badge>
          </div>
          {step.tool_hints.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1 text-[10px] text-slate-500">
              {step.tool_hints.map((tool) => (
                <span key={tool} className="rounded border border-slate-200 px-1 py-0.5 font-mono">
                  {tool}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Capability({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center justify-between rounded border border-slate-100 bg-slate-50 px-3 py-2">
      <span className="inline-flex items-center gap-2 font-mono text-slate-800">
        {icon}
        {label}
      </span>
      <span className="text-right text-slate-500">{value}</span>
    </div>
  );
}

function AssignmentRow({ assignment }: { assignment: AgentAssignment }) {
  const summary =
    typeof assignment.output_json.summary === "string"
      ? assignment.output_json.summary
      : typeof assignment.output_json.reduced_summary === "string"
        ? assignment.output_json.reduced_summary
        : null;
  return (
    <div className="rounded-md border border-slate-100 bg-white p-2">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-mono text-xs text-slate-900">{assignment.agent_id}</div>
          <div className="mt-0.5 text-[11px] text-slate-500">{assignment.role}</div>
        </div>
        <Badge tone={assignment.status === "PENDING" ? "pending" : "neutral"}>
          {assignment.status}
        </Badge>
      </div>
      {summary && <div className="mt-2 text-[11px] leading-4 text-slate-500">{summary}</div>}
      {Array.isArray(assignment.output_json.allowed_tools) && (
        <div className="mt-2 flex flex-wrap gap-1">
          {assignment.output_json.allowed_tools.slice(0, 5).map((tool) => (
            <span
              key={String(tool)}
              className="rounded border border-slate-200 px-1.5 py-0.5 font-mono text-[10px] text-slate-500"
            >
              {String(tool)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-slate-100 bg-slate-50 p-2">
      <div className="text-[10px] text-slate-500">{label}</div>
      <div className="mt-1 font-mono text-sm text-slate-900">{value}</div>
    </div>
  );
}

function planSummary(run?: { plan: { steps: TaskPlanStep[] } }) {
  const steps = run?.plan.steps ?? [];
  return {
    steps: steps.length,
    asyncSteps: steps.filter((step) => step.execution_mode === "async").length,
    sandboxSteps: steps.filter((step) => step.requires_sandbox).length,
  };
}

function agentLabel(agentId: string) {
  if (agentId === "default") return "Default Agent";
  return `${agentId} Agent`;
}

function modeLabel(mode: AgentMode) {
  const labels: Record<AgentMode, string> = {
    Chat: "Chat",
    Plan: "Plan",
    Execute: "Execute",
    Auto: "Auto",
  };
  return labels[mode];
}
