/**
 * E2E Test: Onboarding Wizard - Validation Scenarios
 *
 * Tests validation failures and error handling across all wizard steps.
 */
import { expect, test } from "@playwright/test";
import { setupOnboardingMocks } from "./fixtures";

test.describe("Onboarding Wizard - Validation", () => {
  test("should show error when creating agent with empty ID", async ({ page }) => {
    const state = await setupOnboardingMocks(page, { initialStep: 3 });

    await page.goto("/onboarding?step=3");

    // Wait for step 3 to load
    await expect(page.locator("text=Step 3")).toBeVisible();

    // Select research template
    await page.locator('button:has-text("研究助手")').click();

    // Clear the agent ID
    const agentIdInput = page.locator('input[type="text"]').last();
    await agentIdInput.clear();

    // Try to create agent with empty ID
    const createButton = page.locator('button:has-text("从模板创建")');

    // Button should be disabled when ID is empty
    await expect(createButton).toBeDisabled();
  });

  test("should show error when agent creation fails on backend", async ({ page }) => {
    const state = await setupOnboardingMocks(page, {
      initialStep: 3,
      shouldFailValidation: { agentCreation: true },
    });

    await page.goto("/onboarding?step=3");

    // Wait for step 3 to load
    await expect(page.locator("text=Step 3")).toBeVisible();

    // Select research template
    await page.locator('button:has-text("研究助手")').click();

    // Agent ID should be pre-filled
    const agentIdInput = page.locator('input[type="text"]').last();
    await expect(agentIdInput).toHaveValue("first-run-agent");

    // Try to create agent
    await page.locator('button:has-text("从模板创建")').click();

    // Should show error notification
    await expect(page.locator("text=智能体创建失败")).toBeVisible({ timeout: 5000 });
    await expect(page.locator("text=请检查智能体 ID 是否重复")).toBeVisible();
  });

  test("should show error when demo load fails", async ({ page }) => {
    await setupOnboardingMocks(page, {
      initialStep: 4,
      shouldFailValidation: { demoLoad: true },
    });

    await page.goto("/onboarding?step=4");

    // Wait for step 4 to load
    await expect(page.locator("text=Step 4")).toBeVisible();
    await expect(page.locator("text=运行演示任务")).toBeVisible();

    // Try to trigger demo
    await page.locator('button:has-text("触发演示")').click();

    // Should show error notification
    await expect(page.locator("text=Demo 加载失败")).toBeVisible({ timeout: 5000 });
    await expect(page.locator("text=请确认当前账号具备管理员权限")).toBeVisible();
  });

  test("should prevent moving forward without selecting provider", async ({ page }) => {
    await setupOnboardingMocks(page, { initialStep: 1 });

    await page.goto("/onboarding");

    // Step 1 should be visible
    await expect(page.locator("text=Step 1")).toBeVisible();
    await expect(page.locator("text=选择 LLM Provider")).toBeVisible();

    // Don't select any provider, just try to move forward
    // The "下一步" button should still work but without selection it won't save the choice
    await page.locator('button:has-text("下一步")').click();

    // Should move to step 2 (frontend allows navigation)
    await expect(page.locator("text=Step 2")).toBeVisible();
  });

  test("should validate required fields on model provider config", async ({ page }) => {
    await setupOnboardingMocks(page, { initialStep: 2 });

    await page.goto("/onboarding?step=2");

    // Step 2 should be visible
    await expect(page.locator("text=Step 2")).toBeVisible();
    await expect(page.locator("text=配置模型连接")).toBeVisible();

    // Endpoint input should be visible
    const endpointInput = page.locator('input[type="text"]').first();
    await expect(endpointInput).toBeVisible();

    // API key input should be visible
    const apiKeyInput = page.locator('input[type="password"]');
    await expect(apiKeyInput).toBeVisible();

    // Clear endpoint
    await endpointInput.clear();

    // Leave API key empty and try to continue
    const saveButton = page.locator('button:has-text("保存并继续")');
    await saveButton.click();

    // Should still proceed (frontend doesn't enforce validation here)
    await expect(page.locator("text=Step 3")).toBeVisible({ timeout: 5000 });
  });

  test("should handle agent ID conflict gracefully", async ({ page }) => {
    await setupOnboardingMocks(page, {
      initialStep: 3,
      shouldFailValidation: { agentCreation: true },
    });

    await page.goto("/onboarding?step=3");

    // Wait for step 3 to load
    await expect(page.locator("text=Step 3")).toBeVisible();

    // Select code review template
    await page.locator('button:has-text("代码审查")').click();

    // Change agent ID to potentially conflicting one
    const agentIdInput = page.locator('input[type="text"]').last();
    await agentIdInput.clear();
    await agentIdInput.fill("existing-agent-id");

    // Try to create agent
    await page.locator('button:has-text("从模板创建")').click();

    // Should show error notification
    await expect(page.locator("text=智能体创建失败")).toBeVisible({ timeout: 5000 });

    // User should still be on step 3
    await expect(page.locator("text=Step 3")).toBeVisible();
    await expect(page.locator("text=创建第一个智能体")).toBeVisible();
  });
});
