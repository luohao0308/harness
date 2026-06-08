import { expect, test, type Page } from "@playwright/test";

import {
  dynamicConsoleRouteSamples,
  sidebarRouteInventory,
} from "../src/app/routeInventory";
import {
  enterpriseIds,
  expectNoDocumentOverflow,
  expectNoRouteError,
  registerEnterpriseApiRoutes,
} from "./fixtures/enterpriseHarness";

type RuntimeErrors = {
  consoleErrors: string[];
  pageErrors: string[];
};

const sidebarAssertions: Record<string, RegExp> = {
  "/": /Dashboard|Recent Activity|Quick Actions/,
  "/agents": /智能体|Default Agent|Token/,
  "/teams": /团队|Enterprise Team/,
  "/runs": /运行历史|Validate Enterprise Harness Chain/,
  "/subagents": /子代理|subagent-enterprise|code-reviewer/,
  "/subagent-specialists": /专家库|代码审查专家|code-reviewer/,
  "/subagent-marketplace": /专家市场|Enterprise Reviewer/,
  "/sandboxes": /沙箱|Warm|Quota|配额/,
  "/tools": /工具|read_file|MCP/,
  "/tools/config": /工具配置|read_file|运行配置/,
  "/knowledge": /知识库|Enterprise Knowledge|Release Grounding/,
  "/observability": /观测|enterprise trace linked|Trace/,
  "/token-savings": /标记节省|Token|Balanced/,
  "/evals": /评测|Enterprise Cost Gate|成本契约/,
  "/settings/policies": /策略|approval|sandbox|高风险/,
  "/settings/models": /模型|内置模型成本|DeepSeek Flash/,
  "/settings/users": /用户|engineer@dev.local/,
  "/settings/api-keys": /API Keys|hk_live_|CI Key/,
  "/settings/audit": /审计|team\.subagent\.projected|team/,
  "/settings/data-management": /数据|export-enterprise|retention/i,
  "/help": /帮助|Quickstart|Troubleshooting|Specialist/i,
};

const dynamicAssertions: Record<string, RegExp> = {
  "/agents/default/workspace": /Default Agent|直接与智能体对话|Team/,
  "/agents/default/chat": /Default Agent|直接与智能体对话|Team/,
  [`/teams/${enterpriseIds.teamId}`]: /Enterprise Team|Review Agent|Review release chain/,
  [`/runs/${enterpriseIds.runId}`]: /Validate Enterprise Harness Chain|read_file|deepseek-v4-flash/,
  [`/runs/${enterpriseIds.runId}/events`]: /PLAN_CREATED|计划已创建|事件/,
  [`/runs/${enterpriseIds.runId}/subagents`]: /subagent-enterprise|code-reviewer|Team bridge output/,
  [`/subagents/${enterpriseIds.subagentId}`]: /Team release reviewer|Team bridge output|fanout-enterprise/,
  [`/subagent-specialists/${enterpriseIds.specialistId}`]: /代码审查专家|code-reviewer|调用/,
  [`/subagent-marketplace/${enterpriseIds.listingId}`]: /Enterprise Reviewer|verified|Harness/i,
};

test.describe("enterprise sidebar route coverage", () => {
  for (const item of sidebarRouteInventory) {
    test(`renders sidebar entry: ${item.label}`, async ({ page }) => {
      const runtimeErrors = trackRuntimeErrors(page);
      const harness = await registerEnterpriseApiRoutes(page);
      await page.setViewportSize({ width: 1440, height: 900 });

      await page.goto(item.href);

      await expectNoRouteError(page);
      await expect(page.locator("body")).toContainText(sidebarAssertions[item.href]);
      await expectNoDocumentOverflow(page);
      await harness.assertNoUnhandledApiRequests();
      expect(runtimeErrors).toEqual({ consoleErrors: [], pageErrors: [] });
    });
  }

  for (const sample of dynamicConsoleRouteSamples) {
    test(`renders dynamic route sample: ${sample.pattern}`, async ({ page }) => {
      const runtimeErrors = trackRuntimeErrors(page);
      const harness = await registerEnterpriseApiRoutes(page);
      await page.setViewportSize({ width: 1440, height: 900 });

      await page.goto(sample.sample);

      await expectNoRouteError(page);
      await expect(page.locator("body")).toContainText(dynamicAssertions[sample.sample]);
      await expectNoDocumentOverflow(page);
      await harness.assertNoUnhandledApiRequests();
      expect(runtimeErrors).toEqual({ consoleErrors: [], pageErrors: [] });
    });
  }

  for (const viewport of [
    { name: "compact desktop", width: 1640, height: 768 },
    { name: "mobile", width: 390, height: 844 },
  ]) {
    for (const routePath of [
      "/agents/default/workspace",
      `/teams/${enterpriseIds.teamId}`,
      `/runs/${enterpriseIds.runId}`,
      "/token-savings",
      "/settings/models",
    ]) {
      test(`${routePath} has no document overflow at ${viewport.name}`, async ({ page }) => {
        const runtimeErrors = trackRuntimeErrors(page);
        const harness = await registerEnterpriseApiRoutes(page);
        await page.setViewportSize(viewport);

        await page.goto(routePath);

        await expectNoRouteError(page);
        await expect(page.locator("body")).not.toHaveText("");
        await expectNoDocumentOverflow(page);
        await harness.assertNoUnhandledApiRequests();
        expect(runtimeErrors).toEqual({ consoleErrors: [], pageErrors: [] });
      });
    }
  }
});

function trackRuntimeErrors(page: Page): RuntimeErrors {
  const runtimeErrors: RuntimeErrors = { consoleErrors: [], pageErrors: [] };
  page.on("pageerror", (error) => runtimeErrors.pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const text = message.text();
    if (text.includes("Failed to load resource")) return;
    runtimeErrors.consoleErrors.push(text);
  });
  return runtimeErrors;
}
