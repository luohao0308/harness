import { createBrowserRouter, Navigate } from "react-router-dom";

import { PlaceholderPage } from "../features/tasks/pages/PlaceholderPage";
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
  { path: "/sandboxes", element: <PlaceholderPage title="Sandboxes" /> },
  { path: "/observability", element: <PlaceholderPage title="Observability" chart /> },
  { path: "/settings/models", element: <PlaceholderPage title="Model Settings" /> },
  { path: "/settings/policies", element: <PlaceholderPage title="Policy Settings" /> },
]);
