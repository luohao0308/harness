import { expect, test } from "@playwright/test";

function collectBrowserFailures(page: import("@playwright/test").Page) {
  const failures: string[] = [];
  page.on("dialog", (dialog) => {
    failures.push(`原生浏览器弹窗：${dialog.type()} ${dialog.message()}`);
    void dialog.dismiss().catch(() => undefined);
  });
  page.on("pageerror", (error) => {
    failures.push(`页面错误：${error.message}`);
  });
  return failures;
}

test.describe("Live MCP / 技能商店浏览器验证", () => {
  test("真实后端下完成 MCP 案例测试与技能安装反馈", async ({ page }) => {
    const failures = collectBrowserFailures(page);

    await page.goto("/tools");
    await expect(page.getByText("MCP / 技能商店")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("新手安装向导")).toBeVisible();
    await expect(page.getByRole("button", { name: "打开安装向导" })).toBeVisible();

    await page.getByRole("button", { name: "打开安装向导" }).click();
    const dialog = page.getByRole("dialog", { name: "MCP / 技能商店" });
    await expect(dialog).toBeVisible({ timeout: 15_000 });
    await expect(dialog.getByText("安装工作台")).toBeVisible();
    await expect(dialog.getByText("商店条目")).toBeVisible();
    await expect(dialog.getByText(/未安装|待审批|待安装|已安装/).first()).toBeVisible();

    const contextCard = dialog.getByRole("button", { name: /上下文搜索/ }).first();
    await expect(contextCard).toBeVisible();
    await expect(contextCard.getByText("已安装")).toBeVisible();
    await contextCard.click();
    await dialog.getByRole("button", { name: "案例：发布准备情况" }).click();
    await dialog.getByRole("button", { name: "一键测试" }).click();
    await expect(page.getByRole("status").getByText("商店案例测试通过")).toBeVisible({ timeout: 10_000 });
    await expect(dialog.getByText("Context match 1")).toBeVisible();

    const braveCard = dialog.getByRole("button", { name: /Brave Search/ }).first();
    await expect(braveCard).toBeVisible({ timeout: 15_000 });
    await braveCard.click();
    await expect(dialog.getByText(/使用 Brave 独立索引进行网页、新闻、图片和视频搜索/).first()).toBeVisible();
    await expect(dialog.getByText("已安装").first()).toBeVisible();
    await dialog.getByRole("button", { name: "案例：OpenAI 最新动态" }).click();
    await dialog.getByRole("button", { name: "一键测试" }).click();
    await expect(page.getByRole("status").getByText("商店案例测试通过")).toBeVisible({ timeout: 10_000 });
    await expect(dialog.getByText("brave MCP result 1")).toBeVisible();

    const skillCard = dialog.getByRole("button", { name: /保守上下文优化/ }).first();
    await expect(skillCard).toBeVisible();
    await skillCard.click();
    await expect(dialog.getByText("建议验证案例")).toBeVisible();
    await dialog.getByRole("complementary", { name: "商店安装工作台" }).getByRole("button", { name: "本地安装" }).click();
    await expect(page.getByRole("status").getByText("商店本地技能安装成功")).toBeVisible({ timeout: 10_000 });
    await expect(dialog.getByText(/已安装|待安装/).first()).toBeVisible();

    const visibleText = await dialog.textContent();
    expect(visibleText ?? "").not.toMatch(/Install workbench|Marketplace entries|Current status|No matching/i);
    expect(failures).toEqual([]);
  });

  test("移动视口下商店弹窗可用且没有横向溢出", async ({ page }) => {
    const failures = collectBrowserFailures(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/tools");
    await page.getByRole("button", { name: "打开安装向导" }).click();
    const dialog = page.getByRole("dialog", { name: "MCP / 技能商店" });

    await expect(dialog).toBeVisible({ timeout: 15_000 });
    await expect(dialog.getByLabel("搜索 MCP 和技能商店")).toBeVisible();
    await expect(dialog.getByText("安装工作台")).toBeVisible();
    await expect(dialog.getByText("商店条目")).toBeVisible();

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    expect(failures).toEqual([]);
  });
});
