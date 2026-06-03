import { expect, test } from "@playwright/test";

import {
  enterpriseIds,
  expectNoRouteError,
  registerEnterpriseApiRoutes,
} from "./fixtures/enterpriseHarness";

test.describe("enterprise cross-feature harness chains", () => {
  test("models flow into workspace, model calls, cost rollup, and eval cost gate", async ({ page }) => {
    const harness = await registerEnterpriseApiRoutes(page);

    await page.goto("/settings/models");
    await expectNoRouteError(page);
    await expect(page.locator("body")).toContainText("deepseek-flash/deepseek-v4-flash");
    await expect(page.locator("body")).toContainText("kimi/kimi-k2.6");
    await expect(page.locator("body")).not.toContainText("USD rollup blocked");

    await page.goto(`/runs/${enterpriseIds.runId}`);
    await expect(page.locator("body")).toContainText("deepseek-v4-flash");
    await expect(page.locator("body")).toContainText("modelcall-enterprise");

    await page.goto("/observability/cost");
    await expect(page.locator("body")).toContainText("deepseek-flash/deepseek-v4-flash");
    await expect(page.locator("body")).toContainText("unknown-provider/unknown-model");
    await expect(page.locator("body")).toContainText("缺失价格");

    await page.goto("/evals");
    await expect(page.locator("body")).toContainText("Enterprise Cost Gate");
    await expect(page.locator("body")).toContainText(/pricing_blocking_statuses|成本契约|missing_pricing/i);
    await harness.assertNoUnhandledApiRequests();
  });

  test("tools are linked through run evidence, registry, and audit", async ({ page }) => {
    const harness = await registerEnterpriseApiRoutes(page);

    await page.goto("/tools");
    await expectNoRouteError(page);
    await expect(page.locator("body")).toContainText("read_file");

    await page.goto(`/runs/${enterpriseIds.runId}`);
    await expect(page.locator("body")).toContainText("toolcall-enterprise");
    await expect(page.locator("body")).toContainText("read_file");

    await page.goto("/settings/audit");
    await expect(page.locator("body")).toContainText("team.subagent.projected");
    await expect(page.locator("body")).toContainText(enterpriseIds.teamId);
    await harness.assertNoUnhandledApiRequests();
  });

  test("knowledge source grounds workspace, run detail, and observability", async ({ page }) => {
    const harness = await registerEnterpriseApiRoutes(page);

    await page.goto("/knowledge");
    await expectNoRouteError(page);
    await expect(page.locator("body")).toContainText("Enterprise Knowledge");
    await expect(page.locator("body")).toContainText("Release Grounding");

    await page.goto(`/runs/${enterpriseIds.runId}`);
    await expect(page.locator("body")).toContainText(/Knowledge source grounded|知识依据|grounded/i);

    await page.goto("/observability");
    await expect(page.locator("body")).toContainText(/grounding|local_evidence|enterprise trace linked/i);
    await harness.assertNoUnhandledApiRequests();
  });

  test("workspace and team-created subagents share durable evidence surfaces", async ({ page }) => {
    const harness = await registerEnterpriseApiRoutes(page);

    await page.goto(`/agents/${enterpriseIds.agentId}/workspace`);
    await expectNoRouteError(page);
    await expect(page.locator("body")).toContainText("Default Agent");

    await page.goto(`/teams/${enterpriseIds.teamId}`);
    await expect(page.locator("body")).toContainText("Review Agent");
    await expect(page.locator("body")).toContainText("Review release chain");

    await page.goto("/subagents");
    await expect(page.locator("body")).toContainText(enterpriseIds.subagentId);
    await expect(page.locator("body")).toContainText("code-reviewer");

    await page.goto(`/subagents/${enterpriseIds.subagentId}`);
    await expect(page.locator("body")).toContainText("Team bridge output");
    await expect(page.locator("body")).toContainText("fanout-enterprise");

    await page.goto(`/runs/${enterpriseIds.runId}/subagents`);
    await expect(page.locator("body")).toContainText(enterpriseIds.subagentId);
    await expect(page.locator("body")).toContainText("Team bridge output");

    await page.goto(`/subagent-specialists/${enterpriseIds.specialistId}`);
    await expect(page.locator("body")).toContainText("代码审查专家");
    await expect(page.locator("body")).toContainText("3");

    await page.goto(`/observability/trace?trace_id=${enterpriseIds.traceId}`);
    await expect(page.locator("body")).toContainText("team.subagent.project");
    await expect(page.locator("body")).toContainText(enterpriseIds.subagentId);
    await harness.assertNoUnhandledApiRequests();
  });

  test("data export chain preserves audit evidence", async ({ page }) => {
    const harness = await registerEnterpriseApiRoutes(page);

    await page.goto("/settings/data-management");
    await expectNoRouteError(page);
    await expect(page.locator("body")).toContainText("export-enterprise");
    await expect(page.locator("body")).toContainText("completed");

    await page.goto("/settings/audit");
    await expect(page.locator("body")).toContainText("team.subagent.projected");
    await expect(page.locator("body")).toContainText(enterpriseIds.subagentId);
    await harness.assertNoUnhandledApiRequests();
  });
});
