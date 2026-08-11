import { lazy, Suspense, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { createBrowserRouter, createHashRouter, Navigate, useLocation } from "react-router-dom";

import { RouteErrorBoundary } from "../components/RouteErrorBoundary";
import { RouteSkeleton } from "../components/ui/RouteSkeleton";
import { useAuth } from "../features/auth/AuthProvider";
import { API_BASE_URL, getOnboardingState } from "../features/tasks/api";
import { isLocalRuntimeProfile } from "../lib/local-runtime";

const AgentListPage = lazy(() => import("../features/agents/pages/AgentListPage").then((module) => ({ default: module.AgentListPage })));
const AgentWorkspacePage = lazy(() => import("../features/agents/pages/AgentWorkspacePage").then((module) => ({ default: module.AgentWorkspacePage })));
const LoginPage = lazy(() => import("../features/auth/pages/LoginPage").then((module) => ({ default: module.LoginPage })));
const OAuthCallbackPage = lazy(() => import("../features/auth/pages/OAuthCallbackPage").then((module) => ({ default: module.OAuthCallbackPage })));
const RegisterPage = lazy(() => import("../features/auth/pages/RegisterPage").then((module) => ({ default: module.RegisterPage })));
const DashboardPage = lazy(() => import("../features/dashboard/pages/DashboardPage").then((module) => ({ default: module.DashboardPage })));
const EvalHarnessPage = lazy(() => import("../features/evals/pages/EvalHarnessPage").then((module) => ({ default: module.EvalHarnessPage })));
const HelpCenterPage = lazy(() => import("../features/help/pages/HelpCenterPage").then((module) => ({ default: module.HelpCenterPage })));
const KnowledgePage = lazy(() => import("../features/knowledge/pages/KnowledgePage").then((module) => ({ default: module.KnowledgePage })));
const OnboardingWizardPage = lazy(() => import("../features/onboarding/pages/OnboardingWizardPage").then((module) => ({ default: module.OnboardingWizardPage })));
const AlertRulesPage = lazy(() => import("../features/observability/pages/AlertRulesPage").then((module) => ({ default: module.AlertRulesPage })));
const CostDashboardPage = lazy(() => import("../features/observability/pages/CostDashboardPage").then((module) => ({ default: module.CostDashboardPage })));
const ObservabilityPage = lazy(() => import("../features/observability/pages/ObservabilityPage").then((module) => ({ default: module.ObservabilityPage })));
const TokenSavingsPage = lazy(() => import("../features/observability/pages/TokenSavingsPage").then((module) => ({ default: module.TokenSavingsPage })));
const TraceExplorerPage = lazy(() => import("../features/observability/pages/TraceExplorerPage").then((module) => ({ default: module.TraceExplorerPage })));
const SandboxesPage = lazy(() => import("../features/sandboxes/pages/SandboxesPage").then((module) => ({ default: module.SandboxesPage })));
const AdvancedFeaturesPage = lazy(() => import("../features/settings/pages/AdvancedFeaturesPage").then((module) => ({ default: module.AdvancedFeaturesPage })));
const DesktopSettingsRoutePage = lazy(() => import("../features/settings/pages/DesktopSettingsRoutePage").then((module) => ({ default: module.DesktopSettingsRoutePage })));
const ApiKeysPage = lazy(() => import("../features/settings/pages/ApiKeysPage").then((module) => ({ default: module.ApiKeysPage })));
const AuditLogPage = lazy(() => import("../features/settings/pages/AuditLogPage").then((module) => ({ default: module.AuditLogPage })));
const DataManagementPage = lazy(() => import("../features/settings/pages/DataManagementPage").then((module) => ({ default: module.DataManagementPage })));
const FrontendErrorsPage = lazy(() => import("../features/settings/pages/FrontendErrorsPage").then((module) => ({ default: module.FrontendErrorsPage })));
const ModelSettingsPage = lazy(() => import("../features/settings/pages/ModelSettingsPage").then((module) => ({ default: module.ModelSettingsPage })));
const PolicySettingsPage = lazy(() => import("../features/settings/pages/PolicySettingsPage").then((module) => ({ default: module.PolicySettingsPage })));
const SecretVaultPage = lazy(() => import("../features/settings/pages/SecretVaultPage").then((module) => ({ default: module.SecretVaultPage })));
const UserManagementPage = lazy(() => import("../features/settings/pages/UserManagementPage").then((module) => ({ default: module.UserManagementPage })));
const SubagentDetailPage = lazy(() => import("../features/subagents/pages/SubagentDetailPage").then((module) => ({ default: module.SubagentDetailPage })));
const SubagentMarketplaceDetailPage = lazy(() => import("../features/subagents/pages/SubagentMarketplaceDetailPage").then((module) => ({ default: module.SubagentMarketplaceDetailPage })));
const SubagentMarketplacePage = lazy(() => import("../features/subagents/pages/SubagentMarketplacePage").then((module) => ({ default: module.SubagentMarketplacePage })));
const SubagentSpecialistDetailPage = lazy(() => import("../features/subagents/pages/SubagentSpecialistDetailPage").then((module) => ({ default: module.SubagentSpecialistDetailPage })));
const SubagentSpecialistsPage = lazy(() => import("../features/subagents/pages/SubagentSpecialistsPage").then((module) => ({ default: module.SubagentSpecialistsPage })));
const SubagentsPage = lazy(() => import("../features/subagents/pages/SubagentsPage").then((module) => ({ default: module.SubagentsPage })));
const TeamListPage = lazy(() => import("../features/teams/pages/TeamListPage").then((module) => ({ default: module.TeamListPage })));
const TeamPage = lazy(() => import("../features/teams/pages/TeamPage").then((module) => ({ default: module.TeamPage })));
const RunDetailPage = lazy(() => import("../features/runs/pages/RunDetailPage").then((module) => ({ default: module.RunDetailPage })));
const RunHistoryPage = lazy(() => import("../features/runs/pages/RunHistoryPage").then((module) => ({ default: module.RunHistoryPage })));
const ToolConfigurationPage = lazy(() => import("../features/tools/pages/ToolConfigurationPage").then((module) => ({ default: module.ToolConfigurationPage })));
const ToolRegistryPage = lazy(() => import("../features/tools/pages/ToolRegistryPage").then((module) => ({ default: module.ToolRegistryPage })));
const TerminalWorkspace = lazy(() => import("../features/terminal/components/TerminalWorkspace").then((module) => ({ default: module.TerminalWorkspace })));

const createConsoleRouter =
  import.meta.env.VITE_DESKTOP_ROUTER === "hash" ? createHashRouter : createBrowserRouter;

export const router = createConsoleRouter([
  {
    path: "/",
    errorElement: <RouteErrorBoundary />,
    children: [
      { path: "login", element: routeElement(<LoginPage />) },
      { path: "register", element: routeElement(<RegisterPage />) },
      { path: "oauth/callback", element: routeElement(<OAuthCallbackPage />) },
      { path: "setup/model", element: <LegacyModelSetupRedirect /> },
      { index: true, element: protectedElement(<OnboardingGate />) },
      { path: "onboarding", element: protectedElement(<OnboardingWizardPage />) },
      { path: "agents", element: protectedElement(<AgentListPage />) },
      { path: "agents/:agentId/workspace", element: protectedElement(<AgentWorkspacePage />) },
      { path: "agents/:agentId/chat", element: <Navigate to="/agents/default/workspace" replace /> },
      { path: "teams", element: protectedElement(<TeamListPage />) },
      { path: "teams/:teamId", element: protectedElement(<TeamPage />) },
      { path: "runs", element: protectedElement(<RunHistoryPage />) },
      { path: "runs/:runId", element: protectedElement(<RunDetailPage />) },
      { path: "runs/:runId/events", element: protectedElement(<RunDetailPage focus="events" />) },
      { path: "runs/:runId/subagents", element: protectedElement(<RunDetailPage focus="subagents" />) },
      { path: "tasks", element: <Navigate to="/runs" replace /> },
      { path: "subagents", element: protectedElement(<SubagentsPage />) },
      { path: "subagents/:subagentId", element: protectedElement(<SubagentDetailPage />) },
      { path: "subagent-specialists", element: protectedElement(<SubagentSpecialistsPage />) },
      { path: "subagent-specialists/:specialistId", element: protectedElement(<SubagentSpecialistDetailPage />) },
      { path: "subagent-marketplace", element: protectedElement(<SubagentMarketplacePage />) },
      { path: "subagent-marketplace/:listingId", element: protectedElement(<SubagentMarketplaceDetailPage />) },
      { path: "sandboxes", element: protectedElement(<SandboxesPage />) },
      { path: "observability", element: protectedElement(<ObservabilityPage />) },
      { path: "observability/cost", element: protectedElement(<CostDashboardPage />) },
      { path: "observability/trace", element: protectedElement(<TraceExplorerPage />) },
      { path: "observability/alerts", element: protectedElement(<AlertRulesPage />) },
      { path: "token-savings", element: protectedElement(<TokenSavingsPage />) },
      { path: "desktop", element: protectedElement(<DesktopSettingsRoutePage />) },
      { path: "tools", element: protectedElement(<ToolRegistryPage />) },
      { path: "tools/config", element: protectedElement(<ToolConfigurationPage />) },
      { path: "knowledge", element: protectedElement(<KnowledgePage />) },
      { path: "evals", element: protectedElement(<EvalHarnessPage />) },
      { path: "help", element: protectedElement(<HelpCenterPage />) },
      { path: "help/troubleshooting", element: protectedElement(<HelpCenterPage />) },
      { path: "settings/models", element: protectedElement(<ModelSettingsPage />) },
      { path: "settings/advanced", element: protectedElement(<AdvancedFeaturesPage />) },
      { path: "settings/secrets", element: protectedElement(<SecretVaultPage />) },
      { path: "settings/policies", element: protectedElement(<PolicySettingsPage />) },
      { path: "settings/users", element: protectedElement(<UserManagementPage />) },
      { path: "settings/api-keys", element: protectedElement(<ApiKeysPage />) },
      { path: "settings/audit", element: protectedElement(<AuditLogPage />) },
      { path: "settings/data-management", element: protectedElement(<DataManagementPage />) },
      { path: "settings/frontend-errors", element: protectedElement(<FrontendErrorsPage />) },
      { path: "terminal", element: protectedElement(<TerminalWorkspace />) },
    ],
  },
]);

function routeElement(element: ReactNode) {
  return <Suspense fallback={<RouteSkeleton />}>{element}</Suspense>;
}

export function LegacyModelSetupRedirect() {
  return <Navigate to="/desktop?section=models" replace />;
}

function protectedElement(element: ReactNode) {
  return <RequireAuth>{routeElement(element)}</RequireAuth>;
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const location = useLocation();
  const next = `${location.pathname}${location.search}${location.hash}`;
  if (auth.loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500">
        正在验证登录状态...
      </div>
    );
  }
  if (!auth.user && auth.error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
        <div className="w-full max-w-md rounded-lg border border-red-100 bg-white p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-red-600">API 连接异常</p>
          <h1 className="mt-2 text-lg font-semibold text-slate-950">无法打开控制台页面</h1>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            登录态验证没有完成，请确认本地 API 正在响应。
          </p>
          <div className="mt-3 rounded-md bg-slate-50 p-3 text-xs leading-5 text-slate-600">
            <div>API：{API_BASE_URL || "/"}</div>
            <div className="mt-1 break-words">错误：{auth.error}</div>
          </div>
          <button
            type="button"
            className="mt-4 inline-flex h-8 items-center justify-center rounded-md border border-slate-900 bg-slate-900 px-3 text-xs font-medium text-white hover:bg-slate-800"
            onClick={() => void auth.reload()}
          >
            重新验证
          </button>
        </div>
      </div>
    );
  }
  if (!auth.user) {
    if (isLocalRuntimeProfile()) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
          <div className="w-full max-w-md rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <h1 className="text-base font-semibold text-slate-950">Local session unavailable</h1>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Reopen this surface from Harness Desktop to establish a same-origin session.
            </p>
          </div>
        </div>
      );
    }
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />;
  }
  return <>{children}</>;
}

function OnboardingGate() {
  const localRuntime = isLocalRuntimeProfile();
  const onboarding = useQuery({
    queryKey: ["onboarding", "state"],
    queryFn: getOnboardingState,
    enabled: !localRuntime,
    retry: false,
  });
  if (localRuntime) {
    return <Navigate to="/agents/default/workspace" replace />;
  }
  if (onboarding.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500">
        正在加载控制台...
      </div>
    );
  }
  if (onboarding.data && !onboarding.data.completed && !onboarding.data.skipped) {
    return <Navigate to="/onboarding" replace />;
  }
  return routeElement(<DashboardPage />);
}
