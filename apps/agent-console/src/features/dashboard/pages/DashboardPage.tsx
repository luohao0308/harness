import type { ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, AlertTriangle, BarChart3, Bot, Gauge, Plus, Settings2 } from "lucide-react";
import { Link } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { feedbackErrorMessage, notifyFeedback } from "../../../components/ui/feedback-toast";
import { SkeletonCard, SkeletonTable } from "../../../components/ui/Skeleton";
import { Walkthrough } from "../../../components/ui/Walkthrough";
import { cn } from "../../../lib/utils";
import {
  getCostRollup,
  getObservabilitySummary,
  getOnboardingState,
  listAgents,
  listRuns,
  loadDemoData,
  type OnboardingState,
} from "../../tasks/api";
import { QuickStatsCard } from "../components/QuickStatsCard";
import { RecentActivityList } from "../components/RecentActivityList";
import { WhatsNewPanel } from "../components/WhatsNewPanel";

export function DashboardPage() {
  const queryClient = useQueryClient();
  const onboarding = useQuery({ queryKey: ["onboarding", "state"], queryFn: getOnboardingState });
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const runs = useQuery({ queryKey: ["agent-runs"], queryFn: listRuns });
  const summary = useQuery({ queryKey: ["observability", "summary"], queryFn: getObservabilitySummary });
  const cost = useQuery({
    queryKey: ["observability", "cost-rollup", "30d", "agent"],
    queryFn: () => getCostRollup({ window: "30d", group_by: "agent" }),
  });
  const loadDemo = useMutation({
    mutationFn: loadDemoData,
    onSuccess: async (result) => {
      if (result.demo_loaded) {
        queryClient.setQueryData<OnboardingState>(["onboarding", "state"], (current) =>
          current
            ? {
                ...current,
                demo_loaded: true,
                demo_task_id: result.task_id ?? current.demo_task_id,
                agent_id: result.agent_ids[0] ?? current.agent_id,
                updated_at: new Date().toISOString(),
              }
            : current,
        );
      }
      notifyFeedback({
        tone: "success",
        title: result.status === "already_loaded" ? "Demo 数据已存在" : "Demo 数据已加载",
        description: result.task_id ? `演示运行：${result.task_id}` : undefined,
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["agent-runs"] }),
        queryClient.invalidateQueries({ queryKey: ["agents"] }),
        queryClient.invalidateQueries({ queryKey: ["onboarding", "state"] }),
      ]);
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: "Demo 加载失败",
        description: feedbackErrorMessage(error, "请确认当前账号具备管理员权限。"),
      });
    },
  });

  const activeAgents = agents.data?.items.filter((agent) => agent.status !== "ARCHIVED").length ?? 0;
  const todayRuns = runs.data?.items.filter((run) => isToday(run.created_at)).length ?? 0;
  const activeAlerts =
    summary.data?.tasks_by_status.find((item) => item.name === "FAILED")?.count ??
    summary.data?.failed_task_total ??
    0;
  const onboardingIncomplete = onboarding.data && !onboarding.data.completed;
  const demoLoaded = onboarding.data?.demo_loaded ?? false;
  const demoTaskId = onboarding.data?.demo_task_id ?? null;
  const demoQuickActionTo = demoLoaded ? (demoTaskId ? `/runs/${demoTaskId}` : "/runs") : null;

  return (
    <ConsoleShell title="看板">
      <Walkthrough
        storageKey="harness.walkthrough.dashboard.v1"
        steps={[
          {
            title: "查看运行状态",
            body: "看板汇总智能体、运行、成本和失败风险，是进入控制台后的第一张运营看板。",
            targetLabel: "快速指标",
          },
          {
            title: "创建或选择智能体",
            body: "从智能体进入工作室，配置模型、Prompt、工具、RAG 和 Token 预算。",
            targetLabel: "智能体",
          },
          {
            title: "执行第一个任务",
            body: "新对话会进入智能体工作区，运行、Trace、工具调用和 Eval 证据都会被记录。",
            targetLabel: "新对话",
          },
          {
            title: "遇到问题看帮助",
            body: "帮助中心收录快速开始、排障、专家模板、运行清单和数据留存说明。",
            targetLabel: "帮助中心",
          },
        ]}
      />
      <div className="space-y-4 p-4">
        {onboardingIncomplete ? (
          <section className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-cyan-200 bg-cyan-50 px-4 py-3">
            <div>
              <div className="text-sm font-semibold text-slate-950">继续完成首次设置</div>
              <div className="mt-1 text-xs text-slate-600">
                当前进度 {onboarding.data.current_step}/4，完成后首页会隐藏这条提醒。
              </div>
            </div>
            <Link to="/onboarding">
              <Button variant="primary">继续设置</Button>
            </Link>
          </section>
        ) : null}

        {!demoLoaded ? (
          <section className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
            <div>
              <div className="text-sm font-semibold text-slate-950">Demo 数据未加载</div>
              <div className="mt-1 text-xs text-slate-600">
                加载后会创建示例智能体、知识源、评测数据集和历史运行。
              </div>
            </div>
            <Button onClick={() => loadDemo.mutate()} disabled={loadDemo.isPending}>
              <Gauge className="h-3.5 w-3.5" />
              一键加载 Demo
            </Button>
          </section>
        ) : null}

        <section className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          {agents.isLoading || runs.isLoading || summary.isLoading || cost.isLoading ? (
            <>
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
            </>
          ) : (
            <>
              <QuickStatsCard
                icon={<Bot className="h-4 w-4" />}
                label="Active Agents"
                value={activeAgents}
                trend="最近 7 天配置保持可运行"
              />
              <QuickStatsCard
                icon={<Activity className="h-4 w-4" />}
                label="Today's Runs"
                value={todayRuns}
                trend={`${runs.data?.items.length ?? 0} 条总运行记录`}
                tone="cyan"
              />
              <QuickStatsCard
                icon={<BarChart3 className="h-4 w-4" />}
                label="This Month Cost"
                value={`$${(cost.data?.total_cost_usd ?? 0).toFixed(2)}`}
                trend={`${cost.data?.total_runs ?? 0} 次计费运行`}
                tone="emerald"
              />
              <QuickStatsCard
                icon={<AlertTriangle className="h-4 w-4" />}
                label="Active Alerts"
                value={activeAlerts}
                trend="失败任务计入活跃风险"
                tone="amber"
                to="/observability/alerts"
              />
            </>
          )}
        </section>

        <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
          <Card>
            <CardHeader>
              <div className="text-sm font-semibold text-slate-900">Recent Activity</div>
              <Badge tone="neutral">{runs.data?.items.length ?? 0}</Badge>
            </CardHeader>
            {runs.isLoading ? <SkeletonTable rows={6} columns={3} /> : <RecentActivityList items={runs.data?.items ?? []} />}
          </Card>

          <div className="space-y-4">
            <Card>
              <CardHeader>
                <div className="text-sm font-semibold text-slate-900">Quick Actions</div>
              </CardHeader>
              <div className="grid gap-2 p-3">
                <QuickAction to="/agents" icon={<Plus className="h-3.5 w-3.5" />} label="新建智能体" />
                <QuickAction
                  to={demoQuickActionTo}
                  icon={<Gauge className="h-3.5 w-3.5" />}
                  label={demoLoaded ? "打开演示运行" : "加载演示任务"}
                  onClick={demoLoaded ? undefined : () => loadDemo.mutate()}
                  disabled={!demoLoaded && loadDemo.isPending}
                />
                <QuickAction to="/observability/cost" icon={<BarChart3 className="h-3.5 w-3.5" />} label="看 Cost" />
                <QuickAction to="/settings/models" icon={<Settings2 className="h-3.5 w-3.5" />} label="配 LLM" />
              </div>
            </Card>
            <Card>
              <CardHeader>
                <div className="text-sm font-semibold text-slate-900">What's New</div>
              </CardHeader>
              <div className="p-3">
                <WhatsNewPanel />
              </div>
            </Card>
          </div>
        </section>
      </div>
    </ConsoleShell>
  );
}

function QuickAction({
  to,
  icon,
  label,
  onClick,
  disabled = false,
}: {
  to: string | null;
  icon: ReactNode;
  label: string;
  onClick?: () => void;
  disabled?: boolean;
}) {
  const className = cn(
    "inline-flex h-8 w-full items-center justify-start gap-1.5 rounded-md border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 transition-[background-color,color,border-color,transform,box-shadow] hover:bg-slate-50 active:translate-y-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300",
    disabled && "cursor-not-allowed opacity-50",
  );

  if (to) {
    return (
      <Link to={to} className={className}>
        {icon}
        {label}
      </Link>
    );
  }

  return (
    <button type="button" className={className} onClick={onClick} disabled={disabled}>
      {icon}
      {label}
    </button>
  );
}

function isToday(date: string) {
  const input = new Date(date);
  const now = new Date();
  return (
    input.getFullYear() === now.getFullYear() &&
    input.getMonth() === now.getMonth() &&
    input.getDate() === now.getDate()
  );
}
