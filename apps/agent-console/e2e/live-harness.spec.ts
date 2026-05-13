/**
 * L3 Live Browser Validation: Harness Chain Continuity
 *
 * These tests run against a REAL backend (no Playwright route mocks).
 * They require:
 *   - Harness API running on http://127.0.0.1:8000
 *   - Agent Console on http://127.0.0.1:5177
 *   - HARNESS_E2E_RUN_ID env var (from canonical backend smoke evidence)
 *
 * Run with: npm run e2e:live
 *
 * Part of the Complete Harness Validation Flow (L3 layer).
 */
import { expect, test } from "@playwright/test";

const RUN_ID = process.env.HARNESS_E2E_RUN_ID;
const REPLAY_SEQUENCE = process.env.HARNESS_E2E_REPLAY_SEQUENCE
  ? Number(process.env.HARNESS_E2E_REPLAY_SEQUENCE)
  : undefined;

test.describe("L3A: Canonical Run browser continuity", () => {
  test.skip(!RUN_ID, "HARNESS_E2E_RUN_ID not set — skip live validation");

  test("Run Detail shows the canonical run with full Harness evidence", async ({
    page,
  }) => {
    await page.goto(`/runs/${RUN_ID}`);

    // Run summary visible
    await expect(page.locator("h1")).toBeVisible({ timeout: 15_000 });

    // Status badge visible
    await expect(page.getByText(/COMPLETED|RUNNING|PLANNED|FAILED/).first()).toBeVisible();

    // Plan DAG visible
    await expect(page.getByText("Plan DAG")).toBeVisible();

    // Event Stream visible
    await expect(page.getByText("Event Stream")).toBeVisible();

    // Tool Calls visible
    await expect(page.getByText("Tool Calls")).toBeVisible();

    // Model Calls visible
    await expect(page.getByText("Model Calls")).toBeVisible();

    // Replay panel visible
    await expect(page.getByText("Replay")).toBeVisible();
  });

  test("Replay works for the canonical run", async ({ page }) => {
    test.skip(!RUN_ID, "HARNESS_E2E_RUN_ID not set");

    await page.goto(`/runs/${RUN_ID}`);
    await expect(page.getByText("Replay")).toBeVisible({ timeout: 15_000 });

    if (REPLAY_SEQUENCE) {
      await page.getByLabel(/Replay sequence/).fill(String(REPLAY_SEQUENCE));
    }

    await page.getByRole("button", { name: /Replay|重放/ }).click();

    // Replay result should appear
    await expect(page.getByText(/replayed|manual_review/)).toBeVisible({ timeout: 10_000 });
  });

  test("/runs/:runId/events shows event evidence", async ({ page }) => {
    await page.goto(`/runs/${RUN_ID}/events`);
    await expect(page.getByText("Event Stream")).toBeVisible({ timeout: 15_000 });
    // At least one event should be visible
    await expect(page.locator("[class*='border-slate-100']").first()).toBeVisible();
  });

  test("/runs/:runId/subagents shows subagent evidence", async ({ page }) => {
    await page.goto(`/runs/${RUN_ID}/subagents`);
    await expect(page.getByText("Subagents").last()).toBeVisible({ timeout: 15_000 });
  });
});

test.describe("L3B: Live Workspace user journey", () => {
  test.skip(
    !process.env.HARNESS_E2E_LIVE_WORKSPACE,
    "HARNESS_E2E_LIVE_WORKSPACE not set — skip live Workspace validation (requires model credentials)",
  );

  test("submit a goal through Workspace and perceive a created Run", async ({
    page,
  }) => {
    await page.goto("/agents/default/workspace");

    // Switch to English
    const langBtn = page.getByRole("button", { name: "语言" });
    if (await langBtn.isVisible()) {
      await langBtn.click();
    }

    const composer = page.getByPlaceholder(/Chat with the agent/);
    await expect(composer).toBeVisible({ timeout: 10_000 });

    // Submit a deterministic validation goal
    await composer.fill("List the files in the current directory");
    await page.getByRole("button", { name: "Send" }).click();

    // Observe run_created: Run chip/link should appear
    await expect(
      page.getByRole("link", { name: /Run Detail|Run 详情|[0-9a-f]{8}/ }),
    ).toBeVisible({
      timeout: 30_000,
    });

    // Observe assistant output or terminal state
    // Either content appears or an error state is shown
    const hasContent = await page
      .locator("[data-testid='assistant-content'], .prose, [class*='text-slate-600']")
      .first()
      .isVisible()
      .catch(() => false);
    const hasError = await page
      .getByRole("alert")
      .isVisible()
      .catch(() => false);
    expect(hasContent || hasError).toBe(true);

    // Composer remains usable after stream
    await expect(composer).toBeVisible();
    await expect(composer).toBeEnabled();

    // No unhandled frontend errors
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));
    await page.waitForTimeout(2000);
    expect(errors).toEqual([]);
  });
});
