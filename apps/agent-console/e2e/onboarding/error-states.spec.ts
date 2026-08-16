/**
 * Comprehensive error state testing for onboarding wizard
 * Tests: loading states, error states, empty states, and error recovery
 */
import { expect, test, type Page } from "@playwright/test";
import { setupOnboardingMocks } from "./fixtures";

const API_RE = /http:\/\/(?:127\.0\.0\.1|localhost):(?:8000|5177|15174)\/api\/.*/;

test.describe("Onboarding Wizard - Error States", () => {
  test.describe("Loading States", () => {
    test("shows loading spinner during initial page load", async ({ page }) => {
      let shouldDelay = true;

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/onboarding/state" && shouldDelay) {
          // Delay response to show loading state
          await new Promise((resolve) => setTimeout(resolve, 1000));
          shouldDelay = false;
        }
        await route.continue();
      });

      const navigationPromise = page.goto("/onboarding");

      // Check loading spinner appears
      await expect(page.getByTestId("onboarding-loading")).toBeVisible();

      await navigationPromise;

      // Check loading spinner disappears after data loads
      await expect(page.getByTestId("onboarding-loading")).not.toBeVisible();
    });

    test("shows data fetching indicators during step transitions", async ({ page }) => {
      await setupOnboardingMocks(page, { initialStep: 1 });
      await page.goto("/onboarding");

      // Enter API key and proceed
      await page.getByLabel("API Key").fill("sk-test-key");

      const nextButton = page.getByRole("button", { name: /next|continue/i });
      await nextButton.click();

      // Check for loading state during API call
      await expect(page.getByTestId("step-loading")).toBeVisible();
      await expect(nextButton).toBeDisabled();

      // Wait for loading to complete
      await expect(page.getByTestId("step-loading")).not.toBeVisible();
      await expect(nextButton).not.toBeDisabled();
    });

    test("shows button loading state during form submission", async ({ page }) => {
      await setupOnboardingMocks(page, { initialStep: 2 });
      await page.goto("/onboarding");

      await page.getByLabel("Agent ID").fill("my-agent");
      await page.getByLabel("Agent Name").fill("My Agent");

      const createButton = page.getByRole("button", { name: /create|submit/i });
      await createButton.click();

      // Check button shows loading state
      await expect(createButton).toHaveAttribute("data-loading", "true");
      await expect(createButton.getByTestId("button-spinner")).toBeVisible();
      await expect(createButton).toBeDisabled();
    });

    test("shows skeleton loaders for content placeholders", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/agents/definitions") {
          await new Promise((resolve) => setTimeout(resolve, 800));
        }
        await route.continue();
      });

      await setupOnboardingMocks(page);
      await page.goto("/onboarding/step/3");

      // Check skeleton loaders for agent list
      await expect(page.getByTestId("skeleton-loader")).toBeVisible();
      await expect(page.getByTestId("skeleton-loader")).toHaveCount(3);

      // Wait for real content
      await expect(page.getByTestId("skeleton-loader")).not.toBeVisible();
    });

    test("shows progress indicators during demo data load", async ({ page }) => {
      await setupOnboardingMocks(page, { initialStep: 3 });
      await page.goto("/onboarding");

      const loadDemoButton = page.getByRole("button", { name: /load demo/i });
      await loadDemoButton.click();

      // Check progress indicator appears
      await expect(page.getByTestId("progress-bar")).toBeVisible();
      await expect(page.getByText(/loading demo data/i)).toBeVisible();

      // Wait for completion
      await expect(page.getByText(/demo data loaded/i)).toBeVisible();
    });
  });

  test.describe("Error States - Network & API", () => {
    test("handles network failure (offline)", async ({ page, context }) => {
      await setupOnboardingMocks(page);
      await page.goto("/onboarding");

      // Simulate going offline
      await context.setOffline(true);

      await page.getByLabel("API Key").fill("sk-test-key");
      const nextButton = page.getByRole("button", { name: /next/i });
      await nextButton.click();

      // Check error message
      await expect(page.getByTestId("error-message")).toBeVisible();
      await expect(page.getByText(/network error|offline|connection failed/i)).toBeVisible();

      // Check retry button appears
      await expect(page.getByRole("button", { name: /retry/i })).toBeVisible();
    });

    test("handles API 500 errors", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/onboarding/state" && route.request().method() === "PATCH") {
          await route.fulfill({
            status: 500,
            contentType: "application/json",
            body: JSON.stringify({
              error: "Internal Server Error",
              detail: "An unexpected error occurred on the server",
            }),
          });
          return;
        }
        await route.continue();
      });

      await setupOnboardingMocks(page);
      await page.goto("/onboarding");

      await page.getByLabel("API Key").fill("sk-test-key");
      await page.getByRole("button", { name: /next/i }).click();

      // Check error display
      await expect(page.getByTestId("error-banner")).toBeVisible();
      await expect(page.getByText(/server error|internal error/i)).toBeVisible();
      await expect(page.getByText(/please try again/i)).toBeVisible();
    });

    test("handles API 404 errors", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/agents/definitions/missing-agent") {
          await route.fulfill({
            status: 404,
            contentType: "application/json",
            body: JSON.stringify({
              error: "Not Found",
              detail: "Agent not found",
            }),
          });
          return;
        }
        await route.continue();
      });

      await setupOnboardingMocks(page);
      await page.goto("/onboarding");

      await expect(page.getByText(/not found|resource not found/i)).toBeVisible();
    });

    test("handles API 401/403 errors (unauthorized)", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/onboarding/state") {
          await route.fulfill({
            status: 401,
            contentType: "application/json",
            body: JSON.stringify({
              error: "Unauthorized",
              detail: "Authentication required",
            }),
          });
          return;
        }
        await route.continue();
      });

      await page.goto("/onboarding");

      await expect(page.getByText(/unauthorized|authentication required/i)).toBeVisible();
      await expect(page.getByRole("link", { name: /sign in|log in/i })).toBeVisible();
    });

    test("handles timeout errors", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/demo/load") {
          // Never resolve to simulate timeout
          await new Promise((resolve) => setTimeout(resolve, 60000));
        }
        await route.continue();
      });

      await setupOnboardingMocks(page, { initialStep: 3 });
      await page.goto("/onboarding");

      const loadDemoButton = page.getByRole("button", { name: /load demo/i });
      await loadDemoButton.click();

      // Check timeout error after reasonable wait
      await expect(page.getByText(/timeout|request timed out/i)).toBeVisible({ timeout: 10000 });
      await expect(page.getByRole("button", { name: /retry/i })).toBeVisible();
    });

    test("handles validation errors from API", async ({ page }) => {
      await setupOnboardingMocks(page, {
        initialStep: 1,
        shouldFailValidation: { apiKey: true },
      });
      await page.goto("/onboarding");

      await page.getByLabel("API Key").fill("invalid-key");
      await page.getByRole("button", { name: /next/i }).click();

      // Check validation error display
      await expect(page.getByTestId("field-error")).toBeVisible();
      await expect(page.getByText(/invalid api key|api key is invalid/i)).toBeVisible();
    });

    test("handles form submission errors", async ({ page }) => {
      await setupOnboardingMocks(page, {
        initialStep: 2,
        shouldFailValidation: { agentCreation: true },
      });
      await page.goto("/onboarding");

      await page.getByLabel("Agent ID").fill("my-agent");
      await page.getByLabel("Agent Name").fill("My Agent");
      await page.getByRole("button", { name: /create/i }).click();

      // Check submission error
      await expect(page.getByTestId("form-error")).toBeVisible();
      await expect(page.getByText(/agent creation failed/i)).toBeVisible();
    });

    test("handles rate limit errors (429)", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/onboarding/state" && route.request().method() === "PATCH") {
          await route.fulfill({
            status: 429,
            contentType: "application/json",
            headers: {
              "Retry-After": "60",
            },
            body: JSON.stringify({
              error: "Too Many Requests",
              detail: "Rate limit exceeded. Please try again in 60 seconds.",
            }),
          });
          return;
        }
        await route.continue();
      });

      await setupOnboardingMocks(page);
      await page.goto("/onboarding");

      await page.getByLabel("API Key").fill("sk-test-key");
      await page.getByRole("button", { name: /next/i }).click();

      await expect(page.getByText(/rate limit|too many requests/i)).toBeVisible();
      await expect(page.getByText(/try again in 60 seconds/i)).toBeVisible();
    });
  });

  test.describe("Error States - Specific Scenarios", () => {
    test("handles parse errors (invalid JSON)", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/onboarding/state" && route.request().method() === "GET") {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: "invalid json {{{",
          });
          return;
        }
        await route.continue();
      });

      await page.goto("/onboarding");

      await expect(page.getByText(/failed to load|error parsing data/i)).toBeVisible();
    });

    test("handles demo load failure errors", async ({ page }) => {
      await setupOnboardingMocks(page, {
        initialStep: 3,
        shouldFailValidation: { demoLoad: true },
      });
      await page.goto("/onboarding");

      const loadDemoButton = page.getByRole("button", { name: /load demo/i });
      await loadDemoButton.click();

      await expect(page.getByTestId("error-alert")).toBeVisible();
      await expect(page.getByText(/demo load failed|failed to initialize demo/i)).toBeVisible();
      await expect(page.getByText(/check system configuration/i)).toBeVisible();
    });

    test("handles session timeout errors", async ({ page }) => {
      await setupOnboardingMocks(page);
      await page.goto("/onboarding");

      // Simulate session timeout
      await page.route(API_RE, async (route) => {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({
            error: "Session Expired",
            detail: "Your session has expired. Please log in again.",
          }),
        });
      });

      await page.getByLabel("API Key").fill("sk-test-key");
      await page.getByRole("button", { name: /next/i }).click();

      await expect(page.getByText(/session expired|session timeout/i)).toBeVisible();
      await expect(page.getByRole("link", { name: /log in/i })).toBeVisible();
    });

    test("handles CSRF token errors", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (route.request().method() === "PATCH" || route.request().method() === "POST") {
          await route.fulfill({
            status: 403,
            contentType: "application/json",
            body: JSON.stringify({
              error: "CSRF Token Missing",
              detail: "CSRF token validation failed",
            }),
          });
          return;
        }
        await route.continue();
      });

      await setupOnboardingMocks(page);
      await page.goto("/onboarding");

      await page.getByLabel("API Key").fill("sk-test-key");
      await page.getByRole("button", { name: /next/i }).click();

      await expect(page.getByText(/csrf|security token/i)).toBeVisible();
      await expect(page.getByRole("button", { name: /refresh|reload/i })).toBeVisible();
    });
  });

  test.describe("Empty States", () => {
    test("shows empty state when no data available", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/onboarding/state") {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(null),
          });
          return;
        }
        await route.continue();
      });

      await page.goto("/onboarding");

      await expect(page.getByTestId("empty-state")).toBeVisible();
      await expect(page.getByText(/no data available|start onboarding/i)).toBeVisible();
    });

    test("shows empty state for no agents created", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/agents/definitions" && route.request().method() === "GET") {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ items: [], next_cursor: null }),
          });
          return;
        }
        await route.continue();
      });

      await setupOnboardingMocks(page, { initialStep: 3 });
      await page.goto("/onboarding");

      await expect(page.getByTestId("empty-agents")).toBeVisible();
      await expect(page.getByText(/no agents created|create your first agent/i)).toBeVisible();
      await expect(page.getByRole("button", { name: /create agent/i })).toBeVisible();
    });

    test("shows empty state for no tools configured", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/tools" && route.request().method() === "GET") {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ items: [], next_cursor: null }),
          });
          return;
        }
        await route.continue();
      });

      await setupOnboardingMocks(page, { initialStep: 3 });
      await page.goto("/onboarding");

      await expect(page.getByTestId("empty-tools")).toBeVisible();
      await expect(page.getByText(/no tools configured|add tools to get started/i)).toBeVisible();
    });

    test("shows empty state for no demo data loaded", async ({ page }) => {
      await setupOnboardingMocks(page, { initialStep: 3 });
      await page.goto("/onboarding");

      // Before loading demo
      await expect(page.getByTestId("empty-demo")).toBeVisible();
      await expect(page.getByText(/no demo data|load demo to explore/i)).toBeVisible();
    });
  });

  test.describe("Error Recovery", () => {
    test("retry button recovers from network error", async ({ page, context }) => {
      await setupOnboardingMocks(page);
      await page.goto("/onboarding");

      // Simulate offline
      await context.setOffline(true);

      await page.getByLabel("API Key").fill("sk-test-key");
      await page.getByRole("button", { name: /next/i }).click();

      await expect(page.getByText(/network error/i)).toBeVisible();

      // Go back online
      await context.setOffline(false);

      // Click retry
      const retryButton = page.getByRole("button", { name: /retry/i });
      await retryButton.click();

      // Check success
      await expect(page.getByText(/network error/i)).not.toBeVisible();
      await expect(page.getByTestId("step-indicator").filter({ hasText: "2" })).toBeVisible();
    });

    test("auto-retry with exponential backoff", async ({ page }) => {
      let attemptCount = 0;

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/demo/load" && route.request().method() === "POST") {
          attemptCount++;
          if (attemptCount < 3) {
            await route.fulfill({
              status: 500,
              contentType: "application/json",
              body: JSON.stringify({ error: "Temporary failure" }),
            });
            return;
          }
          // Succeed on 3rd attempt
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ status: "loaded", task_id: "demo-001" }),
          });
          return;
        }
        await route.continue();
      });

      await setupOnboardingMocks(page, { initialStep: 3 });
      await page.goto("/onboarding");

      const loadDemoButton = page.getByRole("button", { name: /load demo/i });
      await loadDemoButton.click();

      // Check retry attempts
      await expect(page.getByText(/retrying.*attempt 1/i)).toBeVisible();
      await expect(page.getByText(/retrying.*attempt 2/i)).toBeVisible();

      // Check eventual success
      await expect(page.getByText(/demo data loaded|success/i)).toBeVisible();
    });

    test("refresh to recover from error", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/onboarding/state") {
          await route.fulfill({
            status: 500,
            contentType: "application/json",
            body: JSON.stringify({ error: "Server error" }),
          });
          return;
        }
        await route.continue();
      });

      await page.goto("/onboarding");

      await expect(page.getByText(/server error/i)).toBeVisible();

      // Clear error and refresh
      const refreshButton = page.getByRole("button", { name: /refresh|reload/i });
      await expect(refreshButton).toBeVisible();

      // Fix the error condition
      await page.unroute(API_RE);
      await setupOnboardingMocks(page);

      await refreshButton.click();

      // Check recovery
      await expect(page.getByText(/server error/i)).not.toBeVisible();
      await expect(page.getByTestId("onboarding-wizard")).toBeVisible();
    });

    test("clear error and continue workflow", async ({ page }) => {
      await setupOnboardingMocks(page, {
        initialStep: 2,
        shouldFailValidation: { agentCreation: true },
      });
      await page.goto("/onboarding");

      await page.getByLabel("Agent ID").fill("my-agent");
      await page.getByLabel("Agent Name").fill("My Agent");
      await page.getByRole("button", { name: /create/i }).click();

      // Error appears
      await expect(page.getByTestId("form-error")).toBeVisible();

      // Clear error
      const dismissButton = page.getByRole("button", { name: /dismiss|close/i });
      await dismissButton.click();

      await expect(page.getByTestId("form-error")).not.toBeVisible();

      // Can continue editing
      await page.getByLabel("Agent ID").fill("corrected-agent");
      await expect(page.getByLabel("Agent ID")).toHaveValue("corrected-agent");
    });

    test("fallback to cached data on error", async ({ page }) => {
      // First, load successfully and cache
      await setupOnboardingMocks(page);
      await page.goto("/onboarding");
      await expect(page.getByTestId("onboarding-wizard")).toBeVisible();

      // Navigate away
      await page.goto("/");

      // Set up error response
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/onboarding/state") {
          await route.fulfill({
            status: 500,
            contentType: "application/json",
            body: JSON.stringify({ error: "Server error" }),
          });
          return;
        }
        await route.continue();
      });

      // Return to onboarding - should use cached data
      await page.goto("/onboarding");

      // Check fallback message
      await expect(page.getByText(/using cached data|showing offline data/i)).toBeVisible();
      await expect(page.getByTestId("onboarding-wizard")).toBeVisible();
    });
  });
});
