/**
 * E2E Test: Onboarding Wizard - Edge Cases
 *
 * Tests browser refresh handling, skip functionality, and other edge cases.
 */
import { expect, test } from "@playwright/test";
import { setupOnboardingMocks } from "./fixtures";

test.describe("Onboarding Wizard - Edge Cases", () => {
  test("should preserve wizard state after browser refresh", async ({ page }) => {
    const state = await setupOnboardingMocks(page, { initialStep: 1 });

    await page.goto("/onboarding");

    // Step 1: Select provider and move to step 2
    await expect(page.locator("text=Step 1")).toBeVisible();
    await page.locator('button:has-text("DeepSeek")').click();
    await page.locator('button:has-text("下一步")').click();

    // Wait for step 2
    await expect(page.locator("text=Step 2")).toBeVisible();

    // Verify state was saved
    expect(state.onboarding.current_step).toBe(2);

    // Refresh the page
    await page.reload();

    // Should return to step 2 (preserved state)
    await expect(page.locator("text=Step 2")).toBeVisible();
    await expect(page.locator("text=配置模型连接")).toBeVisible();
  });

  test("should preserve wizard state when navigating to step 3 and refreshing", async ({ page }) => {
    const state = setupOnboardingMocks(page, { initialStep: 3);
    state.onboarding.provider_json = {
      provider: "deepseek",
      endpoint: "https://api.deepseek.com",
      key_configured: true,
    };
    });

    await page.goto("/onboarding?step=3");

    // Should load at step 3
    await expect(page.locator("text=Step 3")).toBeVisible();
    await expect(page.locator("text=创建第一个智能体")).toBeVisible();

    // Refresh the page
    await page.reload();

    // Should still be at step 3
    await expect(page.locator("text=Step 3")).toBeVisible();
    await expect(page.locator("text=创建第一个智能体")).toBeVisible();
  });

  test("should allow skipping the entire onboarding wizard", async ({ page }) => {
    const state = setupOnboardingMocks(page, { initialStep: 1);
    });

    await page.goto("/onboarding");

    // Wait for wizard to load
    await expect(page.locator("h1")).toContainText("首次运行设置");
    await expect(page.locator("text=Step 1")).toBeVisible();

    // Click skip button
    const skipButton = page.locator('button:has-text("跳过")');
    await expect(skipButton).toBeVisible();
    await skipButton.click();

    // Should navigate to home page
    await page.waitForURL("/", { timeout: 5000 });

    // Verify state was updated to skipped
    expect(state.onboarding.skipped).toBe(true);
  });

  test("should handle direct URL navigation to specific step", async ({ page }) => {
    const state = setupOnboardingMocks(page, { initialStep: 4);
    state.onboarding.agent_id = "first-run-agent";
    state.onboarding.provider_json = {
      provider: "deepseek",
      endpoint: "https://api.deepseek.com",
      key_configured: true,
    };
    });

    // Navigate directly to step 4 via URL
    await page.goto("/onboarding?step=4");

    // Should load at step 4
    await expect(page.locator("text=Step 4")).toBeVisible();
    await expect(page.locator("text=运行演示任务")).toBeVisible();
  });

  test("should respect step progression and not allow skipping ahead", async ({ page }) => {
    const state = setupOnboardingMocks(page, { initialStep: 1);
    });

    // Try to navigate directly to step 3 when current_step is 1
    await page.goto("/onboarding?step=3");

    // Frontend may show step 3, but the step indicator will reflect actual progress
    await expect(page.locator("h1")).toContainText("首次运行设置");

    // The step indicator should show we're at step 1
    const stepIndicators = page.locator('button[aria-label^="步骤"]');
    const firstIndicator = stepIndicators.nth(0);

    // First indicator should be active (darker background)
    await expect(firstIndicator).toHaveClass(/bg-slate-900/);
  });

  test("should handle multiple rapid clicks on navigation buttons", async ({ page }) => {
    const state = setupOnboardingMocks(page, { initialStep: 1);
    });

    await page.goto("/onboarding");

    // Wait for page to load
    await expect(page.locator("text=Step 1")).toBeVisible();

    // Select provider
    await page.locator('button:has-text("DeepSeek")').click();

    // Rapidly click next button multiple times
    const nextButton = page.locator('button:has-text("下一步")');
    await nextButton.click();
    await nextButton.click();
    await nextButton.click();

    // Should handle gracefully and only advance once
    await page.waitForTimeout(500);

    // Should be at step 2
    await expect(page.locator("text=Step 2")).toBeVisible();
  });

  test("should maintain provider selection after going back to step 1", async ({ page }) => {
    const state = setupOnboardingMocks(page, { initialStep: 1);
    });

    await page.goto("/onboarding");

    // Select OpenAI provider
    await page.locator('button:has-text("OpenAI GPT-5.5")').click();
    await expect(page.locator('button:has-text("OpenAI GPT-5.5")')).toHaveClass(/border-slate-900/);

    // Move to step 2
    await page.locator('button:has-text("下一步")').click();
    await expect(page.locator("text=Step 2")).toBeVisible();

    // Go back to step 1
    await page.locator('button[aria-label="步骤 1"]').click();
    await expect(page.locator("text=Step 1")).toBeVisible();

    // OpenAI selection should still be active (in component state)
    // Note: This tests frontend state persistence within the session
    await expect(page.locator('button:has-text("OpenAI GPT-5.5")')).toHaveClass(/border-slate-900/);
  });

  test("should handle completed onboarding state", async ({ page }) => {
    const state = setupOnboardingMocks(page, { initialStep: 4);
    state.onboarding.completed = true;
    state.onboarding.completed_at = "2026-06-14T10:00:00.000Z";
    });

    await page.goto("/onboarding");

    // Should show completed status
    await expect(page.locator("h1")).toContainText("首次运行设置");
    await expect(page.locator('text="已完成"')).toBeVisible();
  });

  test("should handle empty agent ID edge case", async ({ page }) => {
    const state = setupOnboardingMocks(page, { initialStep: 3);
    });

    await page.goto("/onboarding?step=3");

    // Wait for step 3
    await expect(page.locator("text=Step 3")).toBeVisible();

    // Select template
    await page.locator('button:has-text("研究助手")').click();

    // Get agent ID input
    const agentIdInput = page.locator('input[type="text"]').last();

    // Clear the pre-filled value
    await agentIdInput.clear();

    // Try to create agent - button should be disabled
    const createButton = page.locator('button:has-text("从模板创建")');
    await expect(createButton).toBeDisabled();

    // Fill in a valid ID
    await agentIdInput.fill("valid-agent-id");

    // Button should now be enabled
    await expect(createButton).toBeEnabled();
  });

  test("should handle navigation after demo is loaded", async ({ page }) => {
    const state = setupOnboardingMocks(page, { initialStep: 4);
    state.onboarding.agent_id = "first-run-agent";
    });

    await page.goto("/onboarding?step=4");

    // Wait for step 4
    await expect(page.locator("text=Step 4")).toBeVisible();

    // Load demo
    await page.locator('button:has-text("触发演示")').click();
    await expect(page.locator("text=演示运行已创建")).toBeVisible({ timeout: 5000 });

    // Check that "打开运行详情" link appears
    const runDetailLink = page.locator('a:has-text("打开运行详情")');
    await expect(runDetailLink).toBeVisible();

    // Verify the link points to the correct run
    await expect(runDetailLink).toHaveAttribute("href", "/runs/demo-task-001");
  });
});
