import { flattenConsoleNavEntries } from "./consoleNav";

export const sidebarRouteInventory = flattenConsoleNavEntries().map((item) => ({
  href: item.to,
  label: item.label,
}));

export const staticConsoleRoutePaths = [
  "/",
  "/login",
  "/register",
  "/oauth/callback",
  "/onboarding",
  "/desktop",
  "/agents",
  "/teams",
  "/runs",
  "/tasks",
  "/subagents",
  "/subagent-specialists",
  "/subagent-marketplace",
  "/sandboxes",
  "/observability",
  "/observability/cost",
  "/observability/trace",
  "/observability/alerts",
  "/token-savings",
  "/terminal",
  "/tools",
  "/tools/config",
  "/knowledge",
  "/evals",
  "/help",
  "/help/troubleshooting",
  "/settings/models",
  "/settings/secrets",
  "/settings/policies",
  "/settings/users",
  "/settings/api-keys",
  "/settings/audit",
  "/settings/data-management",
  "/settings/frontend-errors",
] as const;

export const dynamicConsoleRouteSamples = [
  {
    name: "Workspace",
    pattern: "/agents/:agentId/workspace",
    sample: "/agents/default/workspace",
  },
  {
    name: "Legacy Chat Redirect",
    pattern: "/agents/:agentId/chat",
    sample: "/agents/default/chat",
  },
  {
    name: "Team Detail",
    pattern: "/teams/:teamId",
    sample: "/teams/team-enterprise",
  },
  {
    name: "Run Detail",
    pattern: "/runs/:runId",
    sample: "/runs/run-enterprise",
  },
  {
    name: "Run Events",
    pattern: "/runs/:runId/events",
    sample: "/runs/run-enterprise/events",
  },
  {
    name: "Run Subagents",
    pattern: "/runs/:runId/subagents",
    sample: "/runs/run-enterprise/subagents",
  },
  {
    name: "Subagent Detail",
    pattern: "/subagents/:subagentId",
    sample: "/subagents/subagent-enterprise",
  },
  {
    name: "Specialist Detail",
    pattern: "/subagent-specialists/:specialistId",
    sample: "/subagent-specialists/specialist-enterprise",
  },
  {
    name: "Marketplace Detail",
    pattern: "/subagent-marketplace/:listingId",
    sample: "/subagent-marketplace/listing-enterprise",
  },
] as const;
