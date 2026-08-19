import { describe, expect, it } from "vitest";

import {
  dynamicConsoleRouteSamples,
  sidebarRouteInventory,
  staticConsoleRoutePaths,
} from "../routeInventory";
import { consoleNavEntries } from "../consoleNav";
import { router } from "../routes";

const requiredDynamicSamples = [
  "/agents/default/workspace",
  "/teams/team-enterprise",
  "/runs/run-enterprise",
  "/runs/run-enterprise/events",
  "/runs/run-enterprise/subagents",
  "/subagents/subagent-enterprise",
  "/subagents/specialists/specialist-enterprise",
  "/subagent-specialists/specialist-enterprise",
  "/subagent-marketplace/listing-enterprise",
  "/observability/cost",
  "/observability/trace",
  "/observability/alerts",
  "/settings/frontend-errors",
];

const requiredCompatibilityPaths = [
  "/settings/data",
  "/subagents/specialists",
  "/subagents/specialists/:specialistId",
];

describe("enterprise route inventory", () => {
  it("locks all left-sidebar links to routable static paths", () => {
    const routerPaths = routePathsFromRouter();

    expect(consoleNavEntries).toHaveLength(13);
    expect(sidebarRouteInventory).toHaveLength(24);
    expect(new Set(sidebarRouteInventory.map((item) => item.href)).size).toBe(24);
    for (const item of sidebarRouteInventory) {
      expect(staticConsoleRoutePaths).toContain(item.href);
      expect(routerPaths).toContain(item.href);
    }
  });

  it("keeps enterprise dynamic route samples visible to smoke tests", () => {
    const allSamples = new Set([
      ...staticConsoleRoutePaths,
      ...dynamicConsoleRouteSamples.map((item) => item.sample),
    ]);

    for (const sample of requiredDynamicSamples) {
      expect(allSamples).toContain(sample);
    }
  });

  it("fails on stale dynamic samples with unresolved path params", () => {
    const routerPaths = routePathsFromRouter();
    for (const item of dynamicConsoleRouteSamples) {
      expect(routerPaths).toContain(item.pattern);
      expect(item.sample).not.toMatch(/:[A-Za-z]/);
      expect(item.sample.startsWith("/")).toBe(true);
    }
  });

  it("keeps audited legacy URLs routed instead of falling into error or ID routes", () => {
    const routerPaths = routePathsFromRouter();

    for (const path of requiredCompatibilityPaths) {
      expect(routerPaths).toContain(path);
    }
  });

  it("keeps the desktop attention route registered", () => {
    expect(routePathsFromRouter()).toContain("/attention");
  });
});

function routePathsFromRouter() {
  const root = router.routes[0];
  const children = root.children ?? [];
  const paths = new Set<string>();
  if (children.some((route) => route.index)) {
    paths.add("/");
  }
  for (const route of children) {
    if (route.path) {
      paths.add(`/${route.path}`.replace(/\/+/g, "/"));
    }
  }
  return paths;
}
