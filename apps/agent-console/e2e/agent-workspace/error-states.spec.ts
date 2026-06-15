/**
 * Comprehensive error state testing for agent workspace
 * Tests: loading states, error states, empty states, and error recovery
 */
import { expect, test, type Page } from "@playwright/test";

const API_RE = /http:\/\/(?:127\.0\.0\.1|localhost):(?:8000|5177|15174)\/api\/.*/;
const CHAT_STREAM_RE = /http:\/\/(?:127\.0\.0\.1|localhost):(?:8000|5177|15174)\/api\/agents\/.*\/runs\/chat\/stream/;

const now = "2026-06-15T00:00:00.000Z";

const agent = {
  id: "default",
  name: "Default Agent",
  description: "Test agent",
  role: "engineer",
  status: "active",
  model_provider: "deepseek-flash",
  model_name: "deepseek-v4-flash",
  system_prompt: "You are a helpful agent.",
  tools_json: ["read_file"],
  routing_tags: ["test"],
  max_parallel_assignments: 2,
  created_at: now,
  updated_at: now,
};

function setupWorkspaceMocks(page: Page) {
  return page.route(API_RE, async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    if (path === "/api/auth/me" && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user_id: "user-001",
          email: "test@example.com",
          name: "Test User",
          organization_id: "org-001",
        }),
      });
      return;
    }

    if (path === "/api/agents/definitions" && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [agent], next_cursor: null }),
      });
      return;
    }

    await route.continue();
  });
}

test.describe("Agent Workspace - Error States", () => {
  test.describe("Loading States", () => {
    test("shows loading spinner during workspace initialization", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/agents/definitions") {
          await new Promise((resolve) => setTimeout(resolve, 1000));
        }
        await route.continue();
      });

      const navigationPromise = page.goto("/workspace");

      await expect(page.getByTestId("workspace-loading")).toBeVisible();

      await navigationPromise;

      await expect(page.getByTestId("workspace-loading")).not.toBeVisible();
    });

    test("shows streaming data loading indicators", async ({ page }) => {
      await setupWorkspaceMocks(page);
      await page.goto("/workspace");

      await page.route(CHAT_STREAM_RE, async (route) => {
        await route.fulfill({
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
          body: "data: {}\n\n",
        });
      });

      const input = page.getByPlaceholder(/type a message/i);
      await input.fill("Hello agent");
      await page.getByRole("button", { name: /send/i }).click();

      await expect(page.getByTestId("stream-loading")).toBeVisible();
      await expect(page.getByTestId("typing-indicator")).toBeVisible();
    });

    test("shows file upload progress indicators", async ({ page }) => {
      await setupWorkspaceMocks(page);
      await page.goto("/workspace");

      const fileInput = page.getByTestId("file-upload-input");
      const filePath = "/tmp/test-file.txt";

      await page.evaluate(() => {
        const file = new File(["test content"], "test-file.txt", { type: "text/plain" });
        const input = document.querySelector('[data-testid="file-upload-input"]') as HTMLInputElement;
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        input.files = dataTransfer.files;
        input.dispatchEvent(new Event("change", { bubbles: true }));
      });

      await expect(page.getByTestId("upload-progress")).toBeVisible();
      await expect(page.getByTestId("progress-bar")).toBeVisible();
    });

    test("shows background refresh indicators", async ({ page }) => {
      await setupWorkspaceMocks(page);
      await page.goto("/workspace");

      // Trigger background refresh
      await page.getByRole("button", { name: /refresh/i }).click();

      await expect(page.getByTestId("refresh-indicator")).toBeVisible();
      await expect(page.getByTestId("refresh-indicator")).not.toBeVisible({ timeout: 5000 });
    });

    test("shows pagination loading state", async ({ page }) => {
      await setupWorkspaceMocks(page);
      await page.goto("/workspace/runs");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/runs") && url.searchParams.get("cursor")) {
          await new Promise((resolve) => setTimeout(resolve, 500));
        }
        await route.continue();
      });

      const nextPageButton = page.getByRole("button", { name: /next page/i });
      await nextPageButton.click();

      await expect(page.getByTestId("pagination-loading")).toBeVisible();
      await expect(nextPageButton).toBeDisabled();
    });

    test("shows infinite scroll loading state", async ({ page }) => {
      await setupWorkspaceMocks(page);
      await page.goto("/workspace/history");

      // Scroll to bottom
      await page.evaluate(() => {
        window.scrollTo(0, document.body.scrollHeight);
      });

      await expect(page.getByTestId("infinite-scroll-loader")).toBeVisible();
    });
  });

  test.describe("Error States - Network & API", () => {
    test("handles network failure during chat", async ({ page, context }) => {
      await setupWorkspaceMocks(page);
      await page.goto("/workspace");

      await context.setOffline(true);

      const input = page.getByPlaceholder(/type a message/i);
      await input.fill("Hello");
      await page.getByRole("button", { name: /send/i }).click();

      await expect(page.getByText(/network error|connection failed/i)).toBeVisible();
      await expect(page.getByRole("button", { name: /retry/i })).toBeVisible();
    });

    test("handles API 500 errors during agent execution", async ({ page }) => {
      await setupWorkspaceMocks(page);
      await page.goto("/workspace");

      await page.route(CHAT_STREAM_RE, async (route) => {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({
            error: "Internal Server Error",
            detail: "Agent execution failed",
          }),
        });
      });

      const input = page.getByPlaceholder(/type a message/i);
      await input.fill("Hello");
      await page.getByRole("button", { name: /send/i }).click();

      await expect(page.getByTestId("error-message")).toBeVisible();
      await expect(page.getByText(/agent execution failed/i)).toBeVisible();
    });

    test("handles API 404 errors for missing agent", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/agents/")) {
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

      await page.goto("/workspace/agent/missing-agent");

      await expect(page.getByText(/agent not found/i)).toBeVisible();
      await expect(page.getByRole("link", { name: /back to agents/i })).toBeVisible();
    });

    test("handles unauthorized access (401)", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({
            error: "Unauthorized",
            detail: "Authentication required",
          }),
        });
      });

      await page.goto("/workspace");

      await expect(page.getByText(/unauthorized|authentication required/i)).toBeVisible();
      await expect(page.getByRole("link", { name: /sign in/i })).toBeVisible();
    });

    test("handles timeout during long-running tasks", async ({ page }) => {
      await setupWorkspaceMocks(page);
      await page.goto("/workspace");

      await page.route(CHAT_STREAM_RE, async (route) => {
        // Simulate timeout by never responding
        await new Promise((resolve) => setTimeout(resolve, 30000));
      });

      const input = page.getByPlaceholder(/type a message/i);
      await input.fill("Run long task");
      await page.getByRole("button", { name: /send/i }).click();

      await expect(page.getByText(/timeout|request timed out/i)).toBeVisible({ timeout: 15000 });
      await expect(page.getByRole("button", { name: /cancel|stop/i })).toBeVisible();
    });

    test("handles validation errors from agent", async ({ page }) => {
      await setupWorkspaceMocks(page);
      await page.goto("/workspace");

      await page.route(CHAT_STREAM_RE, async (route) => {
        await route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({
            error: "Validation Error",
            detail: "Invalid input format",
          }),
        });
      });

      const input = page.getByPlaceholder(/type a message/i);
      await input.fill("<invalid>");
      await page.getByRole("button", { name: /send/i }).click();

      await expect(page.getByText(/validation error|invalid input/i)).toBeVisible();
    });

    test("handles file upload errors", async ({ page }) => {
      await setupWorkspaceMocks(page);
      await page.goto("/workspace");

      await page.route(/\/api\/.*\/upload/, async (route) => {
        await route.fulfill({
          status: 413,
          contentType: "application/json",
          body: JSON.stringify({
            error: "Payload Too Large",
            detail: "File size exceeds maximum limit of 10MB",
          }),
        });
      });

      await page.evaluate(() => {
        const file = new File(["x".repeat(11 * 1024 * 1024)], "large-file.txt", { type: "text/plain" });
        const input = document.querySelector('[data-testid="file-upload-input"]') as HTMLInputElement;
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        input.files = dataTransfer.files;
        input.dispatchEvent(new Event("change", { bubbles: true }));
      });

      await expect(page.getByText(/file size exceeds|too large/i)).toBeVisible();
    });

    test("handles rate limit errors (429)", async ({ page }) => {
      await setupWorkspaceMocks(page);
      await page.goto("/workspace");

      await page.route(CHAT_STREAM_RE, async (route) => {
        await route.fulfill({
          status: 429,
          headers: { "Retry-After": "60" },
          contentType: "application/json",
          body: JSON.stringify({
            error: "Rate Limited",
            detail: "Too many requests. Try again in 60 seconds.",
          }),
        });
      });

      const input = page.getByPlaceholder(/type a message/i);
      await input.fill("Hello");
      await page.getByRole("button", { name: /send/i }).click();

      await expect(page.getByText(/rate limit|too many requests/i)).toBeVisible();
      await expect(page.getByText(/60 seconds/i)).toBeVisible();
    });

    test("handles database connection errors", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({
            error: "Service Unavailable",
            detail: "Database connection failed",
          }),
        });
      });

      await page.goto("/workspace");

      await expect(page.getByText(/service unavailable|database connection/i)).toBeVisible();
      await expect(page.getByRole("button", { name: /retry/i })).toBeVisible();
    });
  });

  test.describe("Empty States", () => {
    test("shows empty state when no agents available", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/agents/definitions") {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ items: [], next_cursor: null }),
          });
          return;
        }
        await route.continue();
      });

      await page.goto("/workspace");

      await expect(page.getByTestId("empty-agents")).toBeVisible();
      await expect(page.getByText(/no agents available|create an agent/i)).toBeVisible();
      await expect(page.getByRole("button", { name: /create agent/i })).toBeVisible();
    });

    test("shows empty state for no chat history", async ({ page }) => {
      await setupWorkspaceMocks(page);
      await page.goto("/workspace");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/runs")) {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ items: [], next_cursor: null }),
          });
          return;
        }
        await route.continue();
      });

      await expect(page.getByTestId("empty-history")).toBeVisible();
      await expect(page.getByText(/no conversation history|start a conversation/i)).toBeVisible();
    });

    test("shows empty state for no teams joined", async ({ page }) => {
      await setupWorkspaceMocks(page);
      await page.goto("/workspace/teams");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/teams")) {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ items: [], next_cursor: null }),
          });
          return;
        }
        await route.continue();
      });

      await expect(page.getByTestId("empty-teams")).toBeVisible();
      await expect(page.getByText(/no teams|create or join a team/i)).toBeVisible();
    });

    test("shows empty state for filtered results", async ({ page }) => {
      await setupWorkspaceMocks(page);
      await page.goto("/workspace/runs");

      await page.getByPlaceholder(/search/i).fill("nonexistent");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/runs") && url.searchParams.get("search")) {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ items: [], next_cursor: null }),
          });
          return;
        }
        await route.continue();
      });

      await expect(page.getByTestId("empty-search-results")).toBeVisible();
      await expect(page.getByText(/no results found|try different keywords/i)).toBeVisible();
      await expect(page.getByRole("button", { name: /clear search/i })).toBeVisible();
    });
  });

  test.describe("Error Recovery", () => {
    test("retry button recovers from network error", async ({ page, context }) => {
      await setupWorkspaceMocks(page);
      await page.goto("/workspace");

      await context.setOffline(true);

      const input = page.getByPlaceholder(/type a message/i);
      await input.fill("Hello");
      await page.getByRole("button", { name: /send/i }).click();

      await expect(page.getByText(/network error/i)).toBeVisible();

      await context.setOffline(false);

      const retryButton = page.getByRole("button", { name: /retry/i });
      await retryButton.click();

      await expect(page.getByText(/network error/i)).not.toBeVisible();
    });

    test("auto-retry with exponential backoff for transient failures", async ({ page }) => {
      let attemptCount = 0;

      await setupWorkspaceMocks(page);
      await page.goto("/workspace");

      await page.route(CHAT_STREAM_RE, async (route) => {
        attemptCount++;
        if (attemptCount < 3) {
          await route.fulfill({
            status: 503,
            contentType: "application/json",
            body: JSON.stringify({ error: "Service temporarily unavailable" }),
          });
          return;
        }
        await route.fulfill({
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
          body: 'data: {"type":"text","text":"Hello"}\n\n',
        });
      });

      const input = page.getByPlaceholder(/type a message/i);
      await input.fill("Hello");
      await page.getByRole("button", { name: /send/i }).click();

      await expect(page.getByText(/retrying/i)).toBeVisible();
      await expect(page.getByText(/hello/i)).toBeVisible({ timeout: 10000 });
    });

    test("refresh workspace to recover from error", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ error: "Server error" }),
        });
      });

      await page.goto("/workspace");

      await expect(page.getByText(/server error/i)).toBeVisible();

      await page.unroute(API_RE);
      await setupWorkspaceMocks(page);

      const refreshButton = page.getByRole("button", { name: /refresh|reload/i });
      await refreshButton.click();

      await expect(page.getByText(/server error/i)).not.toBeVisible();
    });

    test("clear error and continue working", async ({ page }) => {
      await setupWorkspaceMocks(page);
      await page.goto("/workspace");

      await page.route(CHAT_STREAM_RE, async (route) => {
        await route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({ error: "Invalid input" }),
        });
      });

      const input = page.getByPlaceholder(/type a message/i);
      await input.fill("Invalid");
      await page.getByRole("button", { name: /send/i }).click();

      await expect(page.getByTestId("error-alert")).toBeVisible();

      const dismissButton = page.getByRole("button", { name: /dismiss|close/i });
      await dismissButton.click();

      await expect(page.getByTestId("error-alert")).not.toBeVisible();

      // Can continue using workspace
      await input.fill("Valid message");
      await expect(input).toHaveValue("Valid message");
    });

    test("fallback to cached data when offline", async ({ page, context }) => {
      await setupWorkspaceMocks(page);
      await page.goto("/workspace");

      await expect(page.getByTestId("agent-list")).toBeVisible();

      await context.setOffline(true);
      await page.reload();

      await expect(page.getByText(/using cached data|offline mode/i)).toBeVisible();
      await expect(page.getByTestId("agent-list")).toBeVisible();
    });
  });
});
