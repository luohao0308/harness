/**
 * E2E Test: Onboarding Wizard - Happy Path
 *
 * Tests the complete onboarding wizard flow from start to finish,
 * verifying all 4 steps complete successfully.
 */
import { expect, test } from "@playwright/test";
import { setupOnboardingMocks } from "./fixtures";

test.describe("Onboarding Wizard - Happy Path", () => {
  test("should complete all 4 wizard steps successfully", async ({ page }) => {
    const state = await setupOnboardingMocks(page);

    // Navigate to onboarding wizard
    await page.goto("/onboarding");

    // Step 1: Welcome / Provider Selection
    await expect(page.locator("h1")).toContainText("首次运行设置");
    await expect(page.locator("text=Step 1")).toBeVisible();

    // Select DeepSeek provider
    await page.locator('button:has-text("DeepSeek")').click();
    await expect(page.locator('button:has-text("DeepSeek")')).toHaveClass(/border-slate-900/);

    // Move to step 2
    await page.locator('button:has-text("下一步")').click();

    // Step 2: Model Provider Configuration
    await expect(page.locator("text=Step 2")).toBeVisible();
    await expect(page.locator("text=配置模型连接")).toBeVisible();

    // Fill in endpoint and API key
    await page.locator('input[type="text"]').first().fill("https://api.deepseek.com");
    await page.locator('input[type="password"]').fill("sk-test-key-12345");

    // Save and continue
    await page.locator('button:has-text("保存并继续")').click();

    // Verify state was updated
    await page.waitForTimeout(200);
    expect(state.onboarding.current_step).toBe(3);
    expect(state.onboarding.provider_json).toHaveProperty("provider", "deepseek");

    // Step 3: Create First Agent
    await expect(page.locator("text=Step 3")).toBeVisible();
    await expect(page.locator("text=创建第一个智能体")).toBeVisible();

    // Select research template
    await page.locator('button:has-text("研究助手")').click();
    await expect(page.locator('button:has-text("研究助手")')).toHaveClass(/border-slate-900/);

    // Agent ID should be pre-filled
    const agentIdInput = page.locator('input[type="text"]').last();
    await expect(agentIdInput).toHaveValue("first-run-agent");

    // Create agent
    await page.locator('button:has-text("从模板创建")').click();

    // Wait for success notification
    await expect(page.locator("text=首个智能体已创建")).toBeVisible({ timeout: 5000 });

    // Verify agent was created
    expect(state.agentCreated).toBe(true);
    expect(state.onboarding.agent_id).toBe("first-run-agent");
    expect(state.onboarding.current_step).toBe(4);

    // Step 4: Run Demo Task
    await expect(page.locator("text=Step 4")).toBeVisible();
    await expect(page.locator("text=运行演示任务")).toBeVisible();

    // Trigger demo
    await page.locator('button:has-text("触发演示")').click();

    // Wait for demo load success
    await expect(page.locator("text=演示运行已创建")).toBeVisible({ timeout: 5000 });
    await expect(page.locator("text=demo-task-001")).toBeVisible();

    // Verify demo was loaded
    expect(state.demoLoaded).toBe(true);
    expect(state.onboarding.demo_task_id).toBe("demo-task-001");

    // Complete setup
    await page.locator('button:has-text("完成设置")').click();

    // Wait for navigation to home page
    await page.waitForURL("/", { timeout: 5000 });

    // Verify onboarding is completed
    expect(state.onboarding.completed).toBe(true);
    expect(state.onboarding.completed_at).not.toBeNull();
  });

  test("should allow navigation between steps using step indicators", async ({ page }) => {
    const state = await setupOnboardingMocks(page, { initialStep: 2 });

    await page.goto("/onboarding?step=2");

    // Should start at step 2
    await expect(page.locator("text=Step 2")).toBeVisible();

    // Click on step indicator for step 1
    await page.locator('button[aria-label="步骤 1"]').click();

    // Should navigate to step 1
    await expect(page.locator("text=Step 1")).toBeVisible();
    await expect(page.locator("text=选择 LLM Provider")).toBeVisible();

    // Click on step indicator for step 3
    await page.locator('button[aria-label="步骤 3"]').click();

    // Should navigate to step 3
    await expect(page.locator("text=Step 3")).toBeVisible();
    await expect(page.locator("text=创建第一个智能体")).toBeVisible();
  });
});
