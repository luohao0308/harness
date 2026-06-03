import { lazy, Suspense, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { createBrowserRouter, Navigate, useLocation } from "react-router-dom";

import { RouteErrorBoundary } from "../components/RouteErrorBoundary";
import { RouteSkeleton } from "../components/ui/RouteSkeleton";
import { useAuth } from "../features/auth/AuthProvider";
import { getOnboardingState } from "../features/tasks/api";

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

export const router = createBrowserRouter([
  {
    path: "/",
    errorElement: <RouteErrorBoundary />,
    children: [
      { path: "login", element: routeElement(<LoginPage />) },
      { path: "register", element: routeElement(<RegisterPage />) },
      { path: "oauth/callback", element: routeElement(<OAuthCallbackPage />) },
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
      { path: "tools", element: protectedElement(<ToolRegistryPage />) },
      { path: "tools/config", element: protectedElement(<ToolConfigurationPage />) },
      { path: "knowledge", element: protectedElement(<KnowledgePage />) },
      { path: "evals", element: protectedElement(<EvalHarnessPage />) },
      { path: "help", element: protectedElement(<HelpCenterPage />) },
      { path: "help/troubleshooting", element: protectedElement(<HelpCenterPage />) },
      { path: "settings/models", element: protectedElement(<ModelSettingsPage />) },
      { path: "settings/secrets", element: protectedElement(<SecretVaultPage />) },
      { path: "settings/policies", element: protectedElement(<PolicySettingsPage />) },
      { path: "settings/users", element: protectedElement(<UserManagementPage />) },
      { path: "settings/api-keys", element: protectedElement(<ApiKeysPage />) },
      { path: "settings/audit", element: protectedElement(<AuditLogPage />) },
      { path: "settings/data-management", element: protectedElement(<DataManagementPage />) },
      { path: "settings/frontend-errors", element: protectedElement(<FrontendErrorsPage />) },
    ],
  },
]);

function routeElement(element: ReactNode) {
  return <Suspense fallback={<RouteSkeleton />}>{element}</Suspense>;
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
  if (!auth.user) {
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />;
  }
  return <>{children}</>;
}

function OnboardingGate() {
  const onboarding = useQuery({
    queryKey: ["onboarding", "state"],
    queryFn: getOnboardingState,
    retry: false,
  });
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
