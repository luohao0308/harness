import { expect, test } from "@playwright/test";

import {
  expectNoRouteError,
  registerEnterpriseApiRoutes,
} from "./fixtures/enterpriseHarness";

test.describe("enterprise model pricing source gate", () => {
  test("models page shows official-source pricing for every built-in preset", async ({ page }) => {
    const harness = await registerEnterpriseApiRoutes(page);

    await page.goto("/settings/models");

    await expectNoRouteError(page);
    await expect(page.locator("body")).toContainText("内置模型成本");
    await expect(page.locator("body")).toContainText("DeepSeek Flash");
    await expect(page.locator("body")).toContainText("OpenAI GPT-5.5");
    await expect(page.locator("body")).toContainText("Kimi K2.6");
    await expect(page.locator("body")).toContainText("Z.AI GLM-5.1");
    await expect(page.locator("body")).not.toContainText(["openai-compatible", "gpt"].join("/"));
    await expect(page.locator("body")).toContainText("已验证");
    await expect(page.locator("body")).toContainText("USD 0.95");
    await expect(page.locator("body")).toContainText("USD 1.4");
    await expect(page.getByRole("link", { name: /官方来源/ }).first()).toBeVisible();
    await expect(page.locator("body")).not.toContainText("USD rollup blocked");
    await harness.assertNoUnhandledApiRequests();
  });

  test("models page uses bundled pricing when the pricing API is missing", async ({ page }) => {
    const harness = await registerEnterpriseApiRoutes(page, {
      missingModelPricingSources: true,
      expectedApi404Paths: ["/api/settings/models/pricing-sources"],
    });

    await page.goto("/settings/models");

    await expectNoRouteError(page);
    await expect(page.locator("body")).toContainText("内置模型成本");
    await expect(page.locator("body")).toContainText("DeepSeek Flash");
    await expect(page.locator("body")).toContainText("OpenAI GPT-5.5");
    await expect(page.locator("body")).toContainText("Kimi K2.6");
    await expect(page.locator("body")).toContainText("Z.AI GLM-5.1");
    await expect(page.locator("body")).not.toContainText("成本来源暂不可用");
    await expect(page.locator("body")).not.toContainText("价格来源接口返回 404");
    await harness.assertNoUnhandledApiRequests();
  });

  test("cost dashboard keeps unresolved pricing visible instead of reporting green zero cost", async ({ page }) => {
    const harness = await registerEnterpriseApiRoutes(page);

    await page.goto("/observability/cost");

    await expectNoRouteError(page);
    await expect(page.locator("body")).toContainText("模型价格来源存在企业门禁阻塞");
    await expect(page.locator("body")).toContainText("unknown-provider/unknown-model: 缺失价格");
    await expect(page.locator("body")).toContainText("deepseek-flash/deepseek-v4-flash");
    await harness.assertNoUnhandledApiRequests();
  });

  test("eval page preserves cost-contract pricing blocking evidence", async ({ page }) => {
    const harness = await registerEnterpriseApiRoutes(page);

    await page.goto("/evals");

    await expectNoRouteError(page);
    await expect(page.locator("body")).toContainText("Enterprise Cost Gate");
    await expect(page.locator("body")).toContainText(/成本契约|cost_contract|pricing_blocking_statuses/i);
    await expect(page.locator("body")).toContainText(/missing_pricing|缺失价格/i);
    await harness.assertNoUnhandledApiRequests();
  });
});
