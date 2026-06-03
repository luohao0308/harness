import { expect, test } from "@playwright/test";

test("deployed stack exposes auth entry and console shell", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("body")).toBeVisible();

  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "登录 Harness Console" })).toBeVisible();

  await page.goto("/register");
  await expect(page.getByRole("heading", { name: "创建 Harness 工作区" })).toBeVisible();
});

test("registered user reaches dashboard shell", async ({ page }) => {
  const unique = Date.now();
  await page.goto("/register");
  await page.getByLabel("姓名").fill(`Deploy Smoke ${unique}`);
  await page.getByLabel("邮箱").fill(`deploy-smoke-${unique}@example.com`);
  await page.getByLabel("工作区名称").fill(`Deploy Smoke ${unique}`);
  await page.getByLabel("密码").fill("correct-password");
  await page.getByRole("button", { name: "创建并登录" }).click();

  await expect(page.getByText("控制台")).toBeVisible();
  await expect(page.getByText("Dashboard")).toBeVisible();
});
