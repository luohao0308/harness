import { createBrowserRouter, Navigate } from "react-router-dom";

import { AgentListPage } from "../features/agents/pages/AgentListPage";
import { AgentWorkspacePage } from "../features/agents/pages/AgentWorkspacePage";
import { EvalHarnessPage } from "../features/evals/pages/EvalHarnessPage";
import { ObservabilityPage } from "../features/observability/pages/ObservabilityPage";
import { SandboxesPage } from "../features/sandboxes/pages/SandboxesPage";
import { ModelSettingsPage } from "../features/settings/pages/ModelSettingsPage";
import { PolicySettingsPage } from "../features/settings/pages/PolicySettingsPage";
import { SubagentDetailPage } from "../features/subagents/pages/SubagentDetailPage";
import { SubagentsPage } from "../features/subagents/pages/SubagentsPage";
import { TaskCreatePage } from "../features/tasks/pages/TaskCreatePage";
import { TaskDetailPage } from "../features/tasks/pages/TaskDetailPage";
import { TaskListPage } from "../features/tasks/pages/TaskListPage";
import { ToolRegistryPage } from "../features/tools/pages/ToolRegistryPage";

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/agents/default/chat" replace /> },
  { path: "/agents", element: <AgentListPage /> },
  { path: "/agents/:agentId/chat", element: <AgentWorkspacePage /> },
  { path: "/tasks", element: <TaskListPage /> },
  { path: "/tasks/new", element: <TaskCreatePage /> },
  { path: "/tasks/:taskId", element: <TaskDetailPage /> },
  { path: "/tasks/:taskId/events", element: <TaskDetailPage focus="events" /> },
  { path: "/tasks/:taskId/subagents", element: <TaskDetailPage focus="subagents" /> },
  { path: "/subagents", element: <SubagentsPage /> },
  { path: "/subagents/:subagentId", element: <SubagentDetailPage /> },
  { path: "/sandboxes", element: <SandboxesPage /> },
  { path: "/observability", element: <ObservabilityPage /> },
  { path: "/tools", element: <ToolRegistryPage /> },
  { path: "/evals", element: <EvalHarnessPage /> },
  { path: "/settings/models", element: <ModelSettingsPage /> },
  { path: "/settings/policies", element: <PolicySettingsPage /> },
]);
