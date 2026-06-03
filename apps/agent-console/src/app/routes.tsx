import { createBrowserRouter, isRouteErrorResponse, Navigate, useRouteError } from "react-router-dom";

import { AgentListPage } from "../features/agents/pages/AgentListPage";
import { AgentWorkspacePage } from "../features/agents/pages/AgentWorkspacePage";
import { EvalHarnessPage } from "../features/evals/pages/EvalHarnessPage";
import { KnowledgePage } from "../features/knowledge/pages/KnowledgePage";
import { AlertRulesPage } from "../features/observability/pages/AlertRulesPage";
import { CostDashboardPage } from "../features/observability/pages/CostDashboardPage";
import { ObservabilityPage } from "../features/observability/pages/ObservabilityPage";
import { TokenSavingsPage } from "../features/observability/pages/TokenSavingsPage";
import { TraceExplorerPage } from "../features/observability/pages/TraceExplorerPage";
import { SandboxesPage } from "../features/sandboxes/pages/SandboxesPage";
import { ModelSettingsPage } from "../features/settings/pages/ModelSettingsPage";
import { PolicySettingsPage } from "../features/settings/pages/PolicySettingsPage";
import { SubagentDetailPage } from "../features/subagents/pages/SubagentDetailPage";
import { SubagentMarketplaceDetailPage } from "../features/subagents/pages/SubagentMarketplaceDetailPage";
import { SubagentMarketplacePage } from "../features/subagents/pages/SubagentMarketplacePage";
import { SubagentSpecialistDetailPage } from "../features/subagents/pages/SubagentSpecialistDetailPage";
import { SubagentSpecialistsPage } from "../features/subagents/pages/SubagentSpecialistsPage";
import { SubagentsPage } from "../features/subagents/pages/SubagentsPage";
import { TeamListPage } from "../features/teams/pages/TeamListPage";
import { TeamPage } from "../features/teams/pages/TeamPage";
import { RunDetailPage } from "../features/runs/pages/RunDetailPage";
import { RunHistoryPage } from "../features/runs/pages/RunHistoryPage";
import { ToolConfigurationPage } from "../features/tools/pages/ToolConfigurationPage";
import { ToolRegistryPage } from "../features/tools/pages/ToolRegistryPage";

export const router = createBrowserRouter([
  {
    path: "/",
    errorElement: <ConsoleRouteError />,
    children: [
      { index: true, element: <Navigate to="/agents/default/workspace" replace /> },
      { path: "agents", element: <AgentListPage /> },
      { path: "agents/:agentId/workspace", element: <AgentWorkspacePage /> },
      { path: "agents/:agentId/chat", element: <Navigate to="/agents/default/workspace" replace /> },
      { path: "teams", element: <TeamListPage /> },
      { path: "teams/:teamId", element: <TeamPage /> },
      { path: "runs", element: <RunHistoryPage /> },
      { path: "runs/:runId", element: <RunDetailPage /> },
      { path: "runs/:runId/events", element: <RunDetailPage focus="events" /> },
      { path: "runs/:runId/subagents", element: <RunDetailPage focus="subagents" /> },
      { path: "tasks", element: <Navigate to="/runs" replace /> },
      { path: "subagents", element: <SubagentsPage /> },
      { path: "subagents/:subagentId", element: <SubagentDetailPage /> },
      { path: "subagent-specialists", element: <SubagentSpecialistsPage /> },
      { path: "subagent-specialists/:specialistId", element: <SubagentSpecialistDetailPage /> },
      { path: "subagent-marketplace", element: <SubagentMarketplacePage /> },
      { path: "subagent-marketplace/:listingId", element: <SubagentMarketplaceDetailPage /> },
      { path: "sandboxes", element: <SandboxesPage /> },
      { path: "observability", element: <ObservabilityPage /> },
      { path: "observability/cost", element: <CostDashboardPage /> },
      { path: "observability/trace", element: <TraceExplorerPage /> },
      { path: "observability/alerts", element: <AlertRulesPage /> },
      { path: "token-savings", element: <TokenSavingsPage /> },
      { path: "tools", element: <ToolRegistryPage /> },
      { path: "tools/config", element: <ToolConfigurationPage /> },
      { path: "knowledge", element: <KnowledgePage /> },
      { path: "evals", element: <EvalHarnessPage /> },
      { path: "settings/models", element: <ModelSettingsPage /> },
      { path: "settings/policies", element: <PolicySettingsPage /> },
    ],
  },
]);

function ConsoleRouteError() {
  const error = useRouteError();
  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : "未知错误";
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6 text-slate-900">
      <div className="w-full max-w-lg rounded-lg border border-slate-200 bg-white p-5 shadow-panel">
        <div className="text-base font-semibold">控制台出现异常</div>
        <div className="mt-1 text-xs text-slate-400">控制台路由错误</div>
        <p className="mt-3 rounded-md bg-slate-50 p-3 text-sm text-slate-600">{message}</p>
        <div className="mt-4 flex gap-2">
          <a
            href="/agents/default/workspace"
            className="inline-flex h-8 items-center rounded-md bg-slate-900 px-3 text-xs font-medium text-white"
          >
            返回智能体工作台
          </a>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="inline-flex h-8 items-center rounded-md border border-slate-200 px-3 text-xs font-medium text-slate-700"
          >
            刷新页面
          </button>
        </div>
      </div>
    </div>
  );
}
