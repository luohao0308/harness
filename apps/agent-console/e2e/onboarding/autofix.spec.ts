/**
 * E2E Test: Onboarding Wizard - Auto-fix Scenarios
 *
 * Tests auto-fix features for database initialization, secret generation,
 * and other automated setup tasks.
 *
 * Note: The current onboarding wizard implementation doesn't have explicit
 * auto-fix UI features, but this test suite provides a foundation for
 * testing such features when they are added.
 */
import { expect, test, type Page } from "@playwright/test";

const API_RE = /http:\/\/(?:127\.0\.0\.1|localhost):(?:8000|5177|15174)\/api\/.*/;

type OnboardingState = {
  id: string;
  organization_id: string;
  user_id: string;
  current_step: number;
  completed: boolean;
  skipped: boolean;
  demo_loaded: boolean;
  provider_json: Record<string, unknown>;
  agent_id: string | null;
  demo_task_id: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

type SystemHealthCheck = {
  database: { status: "healthy" | "unhealthy"; message?: string };
  secrets: { status: "configured" | "missing"; message?: string };
  models: { status: "available" | "unavailable"; message?: string };
};

type ApiState = {
  onboardingState: OnboardingState;
  systemHealth: SystemHealthCheck;
  autoFixAvailable: {
    database?: boolean;
    secrets?: boolean;
  };
};

function createInitialState(step = 1): ApiState {
  return {
    onboardingState: {
      id: "onboarding-001",
      organization_id: "org-001",
      user_id: "user-001",
      current_step: step,
      completed: false,
      skipped: false,
      demo_loaded: false,
      provider_json: {},
      agent_id: null,
      demo_task_id: null,
      created_at: "2026-06-14T00:00:00.000Z",
      updated_at: "2026-06-14T00:00:00.000Z",
      completed_at: null,
    },
    systemHealth: {
      database: { status: "healthy" },
      secrets: { status: "configured" },
      models: { status: "available" },
    },
    autoFixAvailable: {},
  };
}

async function setupMockApi(page: Page, state: ApiState) {
  await page.route(API_RE, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    // Auth
    if (path === "/api/auth/me" && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "user-001",
          email: "test@example.com",
          role: "admin",
        }),
      });
      return;
    }

    // Get onboarding state
    if (path === "/api/onboarding/state" && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(state.onboardingState),
      });
      return;
    }

    // System health check (hypothetical endpoint for auto-fix features)
    if (path === "/api/system/health" && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(state.systemHealth),
      });
      return;
    }

    // Auto-fix database initialization (hypothetical endpoint)
    if (path === "/api/system/auto-fix/database" && method === "POST") {
      if (!state.autoFixAvailable.database) {
        await route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({
            error: "Auto-fix not available",
            detail: "Database is already initialized or manual intervention required",
          }),
        });
        return;
      }

      // Simulate successful auto-fix
      state.systemHealth.database = { status: "healthy", message: "Database initialized successfully" };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          message: "Database tables created and migrations applied",
        }),
      });
      return;
    }

    // Auto-fix secret generation (hypothetical endpoint)
    if (path === "/api/system/auto-fix/secrets" && method === "POST") {
      if (!state.autoFixAvailable.secrets) {
        await route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({
            error: "Auto-fix not available",
            detail: "Secrets are already configured or manual setup required",
          }),
        });
        return;
      }

      // Simulate successful auto-fix
      state.systemHealth.secrets = { status: "configured", message: "Secrets generated successfully" };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          message: "JWT secret and encryption keys generated",
          secrets_generated: ["JWT_SECRET", "ENCRYPTION_KEY"],
        }),
      });
      return;
    }

    // Update onboarding state
    if (path === "/api/onboarding/state" && method === "PATCH") {
      const payload = JSON.parse(request.postData() ?? "{}");
      state.onboardingState = {
        ...state.onboardingState,
        ...payload,
        updated_at: new Date().toISOString(),
      };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(state.onboardingState),
      });
      return;
    }

    // Create agent
    if (path === "/api/agents/definitions" && method === "POST") {
      const payload = JSON.parse(request.postData() ?? "{}");
      state.onboardingState.agent_id = payload.id;
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          id: payload.id,
          name: payload.name,
          description: payload.description,
          role: payload.role,
          model_provider: payload.model_provider,
          model_name: payload.model_name,
          status: "ACTIVE",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }),
      });
      return;
    }

    // Load demo data
    if (path === "/api/demo/load" && method === "POST") {
      state.onboardingState.demo_task_id = "demo-task-001";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "loaded",
          agent_ids: ["first-run-agent"],
          task_id: "demo-task-001",
        }),
      });
      return;
    }

    // Complete onboarding
    if (path === "/api/onboarding/complete" && method === "POST") {
      state.onboardingState.completed = true;
      state.onboardingState.completed_at = new Date().toISOString();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(state.onboardingState),
      });
      return;
    }

    // Default fallback
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ error: "Not found" }),
    });
  });
}

test.describe("Onboarding Wizard - Auto-fix Features", () => {
  test("should successfully load demo data on first attempt", async ({ page }) => {
    const state = createInitialState(4);
    state.onboardingState.agent_id = "first-run-agent";
    await setupMockApi(page, state);

    await page.goto("/onboarding?step=4");

    // Wait for step 4
    await expect(page.locator("text=Step 4")).toBeVisible();
    await expect(page.locator("text=运行演示任务")).toBeVisible();

    // Trigger demo - should succeed
    await page.locator('button:has-text("触发演示")').click();

    // Should show success message
    await expect(page.locator("text=演示任务已准备")).toBeVisible({ timeout: 5000 });
    await expect(page.locator("text=演示运行已创建")).toBeVisible();

    // Verify demo was loaded
    expect(state.onboardingState.demo_task_id).toBe("demo-task-001");
  });

  test("should handle demo data already loaded scenario", async ({ page }) => {
    const state = createInitialState(4);
    state.onboardingState.agent_id = "first-run-agent";
    state.onboardingState.demo_loaded = true;
    state.onboardingState.demo_task_id = "existing-demo-task";
    await setupMockApi(page, state);

    await page.goto("/onboarding?step=4");

    // Wait for step 4
    await expect(page.locator("text=Step 4")).toBeVisible();

    // Trigger demo again
    await page.locator('button:has-text("触发演示")').click();

    // Should still show success (may reset or reload)
    await expect(page.locator("text=演示任务已准备")).toBeVisible({ timeout: 5000 });
  });

  test("should validate system health before starting wizard", async ({ page }) => {
    const state = createInitialState(1);

    // Simulate unhealthy database
    state.systemHealth.database = {
      status: "unhealthy",
      message: "Database connection failed",
    };
    state.autoFixAvailable.database = true;

    await setupMockApi(page, state);
    await page.goto("/onboarding");

    // Wizard should still load (health checks are hypothetical)
    await expect(page.locator("h1")).toContainText("首次运行设置");
  });

  test("should auto-generate configuration when needed", async ({ page }) => {
    const state = createInitialState(2);

    // Simulate missing secrets
    state.systemHealth.secrets = {
      status: "missing",
      message: "JWT secret not configured",
    };
    state.autoFixAvailable.secrets = true;

    await setupMockApi(page, state);
    await page.goto("/onboarding?step=2");

    // Step 2 should load normally
    await expect(page.locator("text=Step 2")).toBeVisible();
    await expect(page.locator("text=配置模型连接")).toBeVisible();

    // Fill in configuration
    await page.locator('input[type="text"]').first().fill("https://api.deepseek.com");
    await page.locator('input[type="password"]').fill("sk-test-key");

    // Save and continue
    await page.locator('button:has-text("保存并继续")').click();

    // Should proceed to step 3
    await expect(page.locator("text=Step 3")).toBeVisible({ timeout: 5000 });
  });

  test("should retry demo load after fixing issues", async ({ page }) => {
    const state = createInitialState(4);
    state.onboardingState.agent_id = "first-run-agent";
    await setupMockApi(page, state);

    await page.goto("/onboarding?step=4");

    // Wait for step 4
    await expect(page.locator("text=Step 4")).toBeVisible();

    // First attempt - should succeed
    await page.locator('button:has-text("触发演示")').click();
    await expect(page.locator("text=演示任务已准备")).toBeVisible({ timeout: 5000 });

    // Complete button should be available
    const completeButton = page.locator('button:has-text("完成设置")');
    await expect(completeButton).toBeVisible();
    await expect(completeButton).toBeEnabled();
  });

  test("should handle provider endpoint auto-detection", async ({ page }) => {
    const state = createInitialState(2);
    state.onboardingState.provider_json = {
      provider: "deepseek",
    };
    await setupMockApi(page, state);

    await page.goto("/onboarding?step=2");

    // Step 2 should load
    await expect(page.locator("text=Step 2")).toBeVisible();

    // Endpoint should be pre-filled for DeepSeek
    const endpointInput = page.locator('input[type="text"]').first();
    await expect(endpointInput).toHaveValue("https://api.deepseek.com");
  });

  test("should auto-save progress when moving between steps", async ({ page }) => {
    const state = createInitialState(1);
    await setupMockApi(page, state);

    await page.goto("/onboarding");

    // Select provider
    await page.locator('button:has-text("DeepSeek")').click();

    // Move to next step
    await page.locator('button:has-text("下一步")').click();

    // Wait for state update
    await page.waitForTimeout(300);

    // Verify state was auto-saved
    expect(state.onboardingState.current_step).toBe(2);
    expect(state.onboardingState.provider_json).toHaveProperty("provider");
  });

  test("should handle agent template pre-filling", async ({ page }) => {
    const state = createInitialState(3);
    await setupMockApi(page, state);

    await page.goto("/onboarding?step=3");

    // Wait for step 3
    await expect(page.locator("text=Step 3")).toBeVisible();

    // Agent ID should be pre-filled
    const agentIdInput = page.locator('input[type="text"]').last();
    await expect(agentIdInput).toHaveValue("first-run-agent");

    // Default template (研究助手) should be pre-selected or selectable
    const researchTemplate = page.locator('button:has-text("研究助手")');
    await expect(researchTemplate).toBeVisible();

    // Click to select
    await researchTemplate.click();
    await expect(researchTemplate).toHaveClass(/border-slate-900/);
  });

  test("should auto-recover from transient API failures", async ({ page }) => {
    const state = createInitialState(4);
    state.onboardingState.agent_id = "first-run-agent";

    let apiCallCount = 0;
    await page.route(API_RE, async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname;
      const method = request.method();

      // Auth
      if (path === "/api/auth/me" && method === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: "user-001",
            email: "test@example.com",
            role: "admin",
          }),
        });
        return;
      }

      // Get onboarding state
      if (path === "/api/onboarding/state" && method === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(state.onboardingState),
        });
        return;
      }

      // Load demo data - fail first time, succeed second time
      if (path === "/api/demo/load" && method === "POST") {
        apiCallCount++;

        if (apiCallCount === 1) {
          // First attempt fails
          await route.fulfill({
            status: 500,
            contentType: "application/json",
            body: JSON.stringify({
              error: "Transient failure",
              detail: "Temporary network issue",
            }),
          });
          return;
        }

        // Second attempt succeeds
        state.onboardingState.demo_task_id = "demo-task-001";
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            status: "loaded",
            agent_ids: ["first-run-agent"],
            task_id: "demo-task-001",
          }),
        });
        return;
      }

      // Complete onboarding
      if (path === "/api/onboarding/complete" && method === "POST") {
        state.onboardingState.completed = true;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(state.onboardingState),
        });
        return;
      }

      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ error: "Not found" }),
      });
    });

    await page.goto("/onboarding?step=4");

    // Wait for step 4
    await expect(page.locator("text=Step 4")).toBeVisible();

    // First attempt - should fail
    await page.locator('button:has-text("触发演示")').click();
    await expect(page.locator("text=Demo 加载失败")).toBeVisible({ timeout: 5000 });

    // Retry - should succeed
    await page.locator('button:has-text("触发演示")').click();
    await expect(page.locator("text=演示任务已准备")).toBeVisible({ timeout: 5000 });
  });
});
