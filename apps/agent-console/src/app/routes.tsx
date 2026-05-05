import { createBrowserRouter, Navigate } from "react-router-dom";

import { ObservabilityPage } from "../features/observability/pages/ObservabilityPage";
import { SandboxesPage } from "../features/sandboxes/pages/SandboxesPage";
import { ModelSettingsPage } from "../features/settings/pages/ModelSettingsPage";
import { PolicySettingsPage } from "../features/settings/pages/PolicySettingsPage";
import { SubagentsPage } from "../features/subagents/pages/SubagentsPage";
import { TaskCreatePage } from "../features/tasks/pages/TaskCreatePage";
import { TaskDetailPage } from "../features/tasks/pages/TaskDetailPage";
import { TaskListPage } from "../features/tasks/pages/TaskListPage";

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/tasks" replace /> },
  { path: "/tasks", element: <TaskListPage /> },
  { path: "/tasks/new", element: <TaskCreatePage /> },
  { path: "/tasks/:taskId", element: <TaskDetailPage /> },
  { path: "/tasks/:taskId/events", element: <TaskDetailPage focus="events" /> },
  { path: "/tasks/:taskId/subagents", element: <TaskDetailPage focus="subagents" /> },
  { path: "/subagents", element: <SubagentsPage /> },
  { path: "/sandboxes", element: <SandboxesPage /> },
  { path: "/observability", element: <ObservabilityPage /> },
  { path: "/settings/models", element: <ModelSettingsPage /> },
  { path: "/settings/policies", element: <PolicySettingsPage /> },
]);
