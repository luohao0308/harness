/**
 * Comprehensive error state testing for settings pages
 * Tests: loading states, error states, empty states, and error recovery
 * Covers: User settings, organization settings, notification settings, API keys
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const API_RE = /http:\/\/(?:127\.0\.0\.1|localhost):(?:8000|5177|15174)\/api\/.*/;

interface UserSettings {
  user_id: string;
  email: string;
  name: string;
  avatar_url: string | null;
  timezone: string;
  language: string;
  theme: "light" | "dark" | "system";
  notifications_enabled: boolean;
  email_notifications: boolean;
}

interface OrganizationSettings {
  organization_id: string;
  name: string;
  slug: string;
  plan: string;
  max_agents: number;
  max_users: number;
  features: string[];
}

const mockUserSettings: UserSettings = {
  user_id: "user-001",
  email: "test@example.com",
  name: "Test User",
  avatar_url: null,
  timezone: "UTC",
  language: "en",
  theme: "system",
  notifications_enabled: true,
  email_notifications: true,
};

const mockOrgSettings: OrganizationSettings = {
  organization_id: "org-001",
  name: "Test Org",
  slug: "test-org",
  plan: "enterprise",
  max_agents: 100,
  max_users: 50,
  features: ["sso", "teams", "audit_logs"],
};

function fulfillJson(route: Route, payload: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}

async function setupSettingsMocks(page: Page) {
  await page.route(API_RE, async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    if (path === "/api/users/me/settings" && method === "GET") {
      await fulfillJson(route, mockUserSettings);
      return;
    }

    if (path === "/api/organizations/current/settings" && method === "GET") {
      await fulfillJson(route, mockOrgSettings);
      return;
    }

    if (path === "/api/users/me/api-keys" && method === "GET") {
      await fulfillJson(route, {
        items: [
          {
            id: "key-001",
            name: "Production Key",
            prefix: "sk-prod-",
            created_at: "2026-06-01T00:00:00Z",
            last_used_at: "2026-06-14T00:00:00Z",
          },
        ],
        next_cursor: null,
      });
      return;
    }

    await route.continue();
  });
}

test.describe("Settings - Error States", () => {
  test.describe("Loading States", () => {
    test("shows loading spinner during settings fetch", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/settings")) {
          await new Promise((resolve) => setTimeout(resolve, 1000));
        }
        await route.continue();
      });

      const navigationPromise = page.goto("/settings");

      await expect(page.getByTestId("settings-loading")).toBeVisible();

      await navigationPromise;

      await expect(page.getByTestId("settings-loading")).not.toBeVisible();
    });

    test("shows skeleton loaders for settings sections", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/settings")) {
          await new Promise((resolve) => setTimeout(resolve, 800));
        }
        await route.continue();
      });

      await page.goto("/settings/profile");

      await expect(page.getByTestId("skeleton-settings-form")).toBeVisible();
      await expect(page.getByTestId("skeleton-settings-form")).not.toBeVisible({ timeout: 2000 });
    });

    test("shows button loading state during settings save", async ({ page }) => {
      await setupSettingsMocks(page);
      await page.goto("/settings/profile");

      await page.getByLabel("Name").fill("Updated Name");

      const saveButton = page.getByRole("button", { name: /save|update/i });
      await saveButton.click();

      await expect(saveButton).toHaveAttribute("data-loading", "true");
      await expect(saveButton.getByTestId("button-spinner")).toBeVisible();
      await expect(saveButton).toBeDisabled();
    });

    test("shows progress indicator during avatar upload", async ({ page }) => {
      await setupSettingsMocks(page);
      await page.goto("/settings/profile");

      await page.evaluate(() => {
        const file = new File(["image data"], "avatar.png", { type: "image/png" });
        const input = document.querySelector('[data-testid="avatar-upload"]') as HTMLInputElement;
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        input.files = dataTransfer.files;
        input.dispatchEvent(new Event("change", { bubbles: true }));
      });

      await expect(page.getByTestId("upload-progress")).toBeVisible();
      await expect(page.getByTestId("progress-bar")).toBeVisible();
    });

    test("shows loading during API key generation", async ({ page }) => {
      await setupSettingsMocks(page);
      await page.goto("/settings/api-keys");

      const generateButton = page.getByRole("button", { name: /generate.*key/i });
      await generateButton.click();

      await expect(page.getByTestId("key-generation-loading")).toBeVisible();
      await expect(page.getByText(/generating/i)).toBeVisible();
    });
  });

  test.describe("Error States - User Settings", () => {
    test("handles validation errors on profile update", async ({ page }) => {
      await setupSettingsMocks(page);
      await page.goto("/settings/profile");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/users/me/settings") && route.request().method() === "PATCH") {
          await fulfillJson(
            route,
            {
              error: "Validation Error",
              detail: "Name must be at least 2 characters",
              field_errors: {
                name: ["Must be at least 2 characters"],
              },
            },
            400,
          );
          return;
        }
        await route.continue();
      });

      await page.getByLabel("Name").fill("A");
      await page.getByRole("button", { name: /save/i }).click();

      await expect(page.getByTestId("field-error-name")).toBeVisible();
      await expect(page.getByText(/must be at least 2 characters/i)).toBeVisible();
    });

    test("handles email already in use errors", async ({ page }) => {
      await setupSettingsMocks(page);
      await page.goto("/settings/profile");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/users/me/settings") && route.request().method() === "PATCH") {
          await fulfillJson(
            route,
            {
              error: "Conflict",
              detail: "Email address is already in use",
            },
            409,
          );
          return;
        }
        await route.continue();
      });

      await page.getByLabel("Email").fill("existing@example.com");
      await page.getByRole("button", { name: /save/i }).click();

      await expect(page.getByText(/email.*already in use/i)).toBeVisible();
    });

    test("handles avatar upload size errors", async ({ page }) => {
      await setupSettingsMocks(page);
      await page.goto("/settings/profile");

      await page.route(/\/api\/.*\/upload/, async (route) => {
        await fulfillJson(
          route,
          {
            error: "Payload Too Large",
            detail: "Avatar file size must be less than 5MB",
          },
          413,
        );
      });

      await page.evaluate(() => {
        const file = new File(["x".repeat(6 * 1024 * 1024)], "large.png", { type: "image/png" });
        const input = document.querySelector('[data-testid="avatar-upload"]') as HTMLInputElement;
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        input.files = dataTransfer.files;
        input.dispatchEvent(new Event("change", { bubbles: true }));
      });

      await expect(page.getByText(/file size.*must be less than 5mb/i)).toBeVisible();
    });

    test("handles invalid avatar format errors", async ({ page }) => {
      await setupSettingsMocks(page);
      await page.goto("/settings/profile");

      await page.route(/\/api\/.*\/upload/, async (route) => {
        await fulfillJson(
          route,
          {
            error: "Invalid Format",
            detail: "Avatar must be PNG, JPG, or GIF",
          },
          400,
        );
      });

      await page.evaluate(() => {
        const file = new File(["data"], "avatar.txt", { type: "text/plain" });
        const input = document.querySelector('[data-testid="avatar-upload"]') as HTMLInputElement;
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        input.files = dataTransfer.files;
        input.dispatchEvent(new Event("change", { bubbles: true }));
      });

      await expect(page.getByText(/must be png, jpg, or gif/i)).toBeVisible();
    });

    test("handles password change errors", async ({ page }) => {
      await setupSettingsMocks(page);
      await page.goto("/settings/security");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/password")) {
          await fulfillJson(
            route,
            {
              error: "Authentication Failed",
              detail: "Current password is incorrect",
            },
            401,
          );
          return;
        }
        await route.continue();
      });

      await page.getByLabel("Current Password").fill("wrongpassword");
      await page.getByLabel("New Password").fill("newpassword123");
      await page.getByRole("button", { name: /change password/i }).click();

      await expect(page.getByText(/current password is incorrect/i)).toBeVisible();
    });
  });

  test.describe("Error States - Organization Settings", () => {
    test("handles insufficient permissions errors", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/organizations/")) {
          await fulfillJson(
            route,
            {
              error: "Forbidden",
              detail: "Admin permissions required to modify organization settings",
            },
            403,
          );
          return;
        }
        await route.continue();
      });

      await page.goto("/settings/organization");

      await expect(page.getByText(/admin permissions required/i)).toBeVisible();
      await expect(page.getByTestId("settings-form")).toHaveAttribute("data-disabled", "true");
    });

    test("handles plan limit exceeded errors", async ({ page }) => {
      await setupSettingsMocks(page);
      await page.goto("/settings/organization");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/organizations/") && route.request().method() === "PATCH") {
          await fulfillJson(
            route,
            {
              error: "Limit Exceeded",
              detail: "Maximum agent limit for your plan is 100",
            },
            400,
          );
          return;
        }
        await route.continue();
      });

      await page.getByLabel("Max Agents").fill("200");
      await page.getByRole("button", { name: /save/i }).click();

      await expect(page.getByText(/maximum.*limit.*100/i)).toBeVisible();
      await expect(page.getByRole("link", { name: /upgrade plan/i })).toBeVisible();
    });

    test("handles organization name conflict", async ({ page }) => {
      await setupSettingsMocks(page);
      await page.goto("/settings/organization");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/organizations/") && route.request().method() === "PATCH") {
          await fulfillJson(
            route,
            {
              error: "Conflict",
              detail: "Organization name is already taken",
            },
            409,
          );
          return;
        }
        await route.continue();
      });

      await page.getByLabel("Organization Name").fill("Existing Org");
      await page.getByRole("button", { name: /save/i }).click();

      await expect(page.getByText(/already taken/i)).toBeVisible();
    });
  });

  test.describe("Error States - API Keys", () => {
    test("handles API key generation failures", async ({ page }) => {
      await setupSettingsMocks(page);
      await page.goto("/settings/api-keys");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/api-keys") && route.request().method() === "POST") {
          await fulfillJson(
            route,
            {
              error: "Generation Failed",
              detail: "Maximum number of API keys reached (10)",
            },
            400,
          );
          return;
        }
        await route.continue();
      });

      await page.getByRole("button", { name: /generate.*key/i }).click();

      await expect(page.getByText(/maximum number.*reached/i)).toBeVisible();
    });

    test("handles API key deletion errors", async ({ page }) => {
      await setupSettingsMocks(page);
      await page.goto("/settings/api-keys");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/api-keys/") && route.request().method() === "DELETE") {
          await fulfillJson(
            route,
            {
              error: "Deletion Failed",
              detail: "Cannot delete the last API key",
            },
            400,
          );
          return;
        }
        await route.continue();
      });

      await page.getByRole("button", { name: /delete/i }).first().click();
      await page.getByRole("button", { name: /confirm/i }).click();

      await expect(page.getByText(/cannot delete.*last api key/i)).toBeVisible();
    });

    test("handles API key name validation errors", async ({ page }) => {
      await setupSettingsMocks(page);
      await page.goto("/settings/api-keys");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/api-keys") && route.request().method() === "POST") {
          await fulfillJson(
            route,
            {
              error: "Validation Error",
              detail: "API key name must be unique",
              field_errors: {
                name: ["Name already exists"],
              },
            },
            400,
          );
          return;
        }
        await route.continue();
      });

      await page.getByRole("button", { name: /generate.*key/i }).click();
      await page.getByLabel("Key Name").fill("Production Key");
      await page.getByRole("button", { name: /create/i }).click();

      await expect(page.getByText(/name already exists/i)).toBeVisible();
    });
  });

  test.describe("Error States - Network & API", () => {
    test("handles network failure during settings update", async ({ page, context }) => {
      await setupSettingsMocks(page);
      await page.goto("/settings/profile");

      await context.setOffline(true);

      await page.getByLabel("Name").fill("Updated Name");
      await page.getByRole("button", { name: /save/i }).click();

      await expect(page.getByText(/network error|connection failed/i)).toBeVisible();
    });

    test("handles API 500 errors", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/settings")) {
          await fulfillJson(
            route,
            {
              error: "Internal Server Error",
              detail: "Failed to load settings",
            },
            500,
          );
          return;
        }
        await route.continue();
      });

      await page.goto("/settings/profile");

      await expect(page.getByText(/internal server error|failed to load/i)).toBeVisible();
    });

    test("handles timeout during save operations", async ({ page }) => {
      await setupSettingsMocks(page);
      await page.goto("/settings/profile");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (route.request().method() === "PATCH") {
          await new Promise((resolve) => setTimeout(resolve, 30000));
        }
        await route.continue();
      });

      await page.getByLabel("Name").fill("Updated Name");
      await page.getByRole("button", { name: /save/i }).click();

      await expect(page.getByText(/timeout|request timed out/i)).toBeVisible({ timeout: 15000 });
    });

    test("handles rate limiting (429)", async ({ page }) => {
      await setupSettingsMocks(page);
      await page.goto("/settings/profile");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (route.request().method() === "PATCH") {
          await fulfillJson(
            route,
            {
              error: "Too Many Requests",
              detail: "Rate limit exceeded. Try again in 60 seconds.",
            },
            429,
          );
          return;
        }
        await route.continue();
      });

      await page.getByLabel("Name").fill("Updated Name");
      await page.getByRole("button", { name: /save/i }).click();

      await expect(page.getByText(/rate limit|too many requests/i)).toBeVisible();
    });
  });

  test.describe("Empty States", () => {
    test("shows empty state when no API keys exist", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/api-keys")) {
          await fulfillJson(route, { items: [], next_cursor: null });
          return;
        }
        await route.continue();
      });

      await setupSettingsMocks(page);
      await page.goto("/settings/api-keys");

      await expect(page.getByTestId("empty-api-keys")).toBeVisible();
      await expect(page.getByText(/no api keys|generate your first key/i)).toBeVisible();
      await expect(page.getByRole("button", { name: /generate.*key/i })).toBeVisible();
    });

    test("shows empty state for notification history", async ({ page }) => {
      await setupSettingsMocks(page);
      await page.goto("/settings/notifications");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/notifications/history")) {
          await fulfillJson(route, { items: [], next_cursor: null });
          return;
        }
        await route.continue();
      });

      await expect(page.getByTestId("empty-notification-history")).toBeVisible();
      await expect(page.getByText(/no notifications|no activity/i)).toBeVisible();
    });

    test("shows empty state for team members", async ({ page }) => {
      await setupSettingsMocks(page);
      await page.goto("/settings/team");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/team/members")) {
          await fulfillJson(route, { items: [], next_cursor: null });
          return;
        }
        await route.continue();
      });

      await expect(page.getByTestId("empty-team-members")).toBeVisible();
      await expect(page.getByText(/no team members|invite members/i)).toBeVisible();
    });
  });

  test.describe("Error Recovery", () => {
    test("retry button recovers from network error", async ({ page, context }) => {
      await setupSettingsMocks(page);
      await page.goto("/settings/profile");

      await context.setOffline(true);

      await page.getByLabel("Name").fill("Updated Name");
      await page.getByRole("button", { name: /save/i }).click();

      await expect(page.getByText(/network error/i)).toBeVisible();

      await context.setOffline(false);

      const retryButton = page.getByRole("button", { name: /retry/i });
      await retryButton.click();

      await expect(page.getByText(/network error/i)).not.toBeVisible();
      await expect(page.getByText(/saved|updated/i)).toBeVisible();
    });

    test("refresh to reload settings", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/settings")) {
          await fulfillJson(
            route,
            {
              error: "Server error",
            },
            500,
          );
          return;
        }
        await route.continue();
      });

      await page.goto("/settings/profile");

      await expect(page.getByText(/server error/i)).toBeVisible();

      await page.unroute(API_RE);
      await setupSettingsMocks(page);

      const refreshButton = page.getByRole("button", { name: /refresh|reload/i });
      await refreshButton.click();

      await expect(page.getByText(/server error/i)).not.toBeVisible();
      await expect(page.getByLabel("Name")).toHaveValue("Test User");
    });

    test("clear error and continue editing", async ({ page }) => {
      await setupSettingsMocks(page);
      await page.goto("/settings/profile");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (route.request().method() === "PATCH") {
          await fulfillJson(
            route,
            {
              error: "Validation Error",
              detail: "Invalid input",
            },
            400,
          );
          return;
        }
        await route.continue();
      });

      await page.getByLabel("Name").fill("A");
      await page.getByRole("button", { name: /save/i }).click();

      await expect(page.getByTestId("form-error")).toBeVisible();

      const dismissButton = page.getByRole("button", { name: /dismiss|close/i });
      await dismissButton.click();

      await expect(page.getByTestId("form-error")).not.toBeVisible();

      // Continue editing
      await page.getByLabel("Name").fill("Valid Name");
      await expect(page.getByLabel("Name")).toHaveValue("Valid Name");
    });

    test("reset form to original values", async ({ page }) => {
      await setupSettingsMocks(page);
      await page.goto("/settings/profile");

      await page.getByLabel("Name").fill("Changed Name");
      await page.getByLabel("Email").fill("changed@example.com");

      const resetButton = page.getByRole("button", { name: /reset|cancel/i });
      await resetButton.click();

      await expect(page.getByLabel("Name")).toHaveValue("Test User");
      await expect(page.getByLabel("Email")).toHaveValue("test@example.com");
    });

    test("auto-save draft on navigation", async ({ page }) => {
      await setupSettingsMocks(page);
      await page.goto("/settings/profile");

      await page.getByLabel("Name").fill("Unsaved Name");

      // Navigate away
      await page.goto("/settings/organization");

      await expect(page.getByText(/unsaved changes|draft saved/i)).toBeVisible();

      // Return to profile
      await page.goto("/settings/profile");

      // Check draft is restored
      await expect(page.getByLabel("Name")).toHaveValue("Unsaved Name");
    });
  });
});
