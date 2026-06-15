/**
 * Comprehensive error state testing for admin panel (SAML/SSO configuration)
 * Tests: loading states, error states, empty states, and error recovery
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const API_RE = /http:\/\/(?:127\.0\.0\.1|localhost):(?:8000|5177|15174)\/api\/.*/;

interface SAMLProvider {
  id: string;
  organization_id: string;
  name: string;
  entity_id: string;
  sso_url: string;
  idp_metadata_url: string | null;
  idp_metadata_xml: string | null;
  certificate: string | null;
  status: "active" | "inactive";
  test_connection_status: "success" | "failed" | null;
  test_connection_error: string | null;
  created_at: string;
  updated_at: string;
}

const mockProvider: SAMLProvider = {
  id: "provider-1",
  organization_id: "org-1",
  name: "Okta",
  entity_id: "https://app.example.com/saml/metadata",
  sso_url: "https://okta.example.com/sso/saml",
  idp_metadata_url: "https://okta.example.com/metadata.xml",
  idp_metadata_xml: null,
  certificate: null,
  status: "active",
  test_connection_status: "success",
  test_connection_error: null,
  created_at: "2026-06-15T00:00:00Z",
  updated_at: "2026-06-15T00:00:00Z",
};

function fulfillJson(route: Route, payload: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}

async function setupAdminMocks(page: Page) {
  await page.route(API_RE, async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    if (path === "/api/auth/me" && method === "GET") {
      await fulfillJson(route, {
        user_id: "admin-001",
        email: "admin@example.com",
        role: "admin",
        permissions: ["admin:sso"],
      });
      return;
    }

    if (path === "/api/auth/saml/providers" && method === "GET") {
      await fulfillJson(route, [mockProvider]);
      return;
    }

    await route.continue();
  });
}

test.describe("Admin Panel - Error States", () => {
  test.describe("Loading States", () => {
    test("shows loading spinner during providers fetch", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/auth/saml/providers") {
          await new Promise((resolve) => setTimeout(resolve, 1000));
        }
        await route.continue();
      });

      const navigationPromise = page.goto("/admin/sso");

      await expect(page.getByTestId("admin-loading")).toBeVisible();

      await navigationPromise;

      await expect(page.getByTestId("admin-loading")).not.toBeVisible();
    });

    test("shows skeleton loaders for provider cards", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/auth/saml/providers") {
          await new Promise((resolve) => setTimeout(resolve, 800));
        }
        await route.continue();
      });

      await page.goto("/admin/sso");

      await expect(page.getByTestId("skeleton-provider-card")).toBeVisible();
      await expect(page.getByTestId("skeleton-provider-card")).toHaveCount(3);

      await expect(page.getByTestId("skeleton-provider-card")).not.toBeVisible({ timeout: 2000 });
    });

    test("shows button loading state during provider creation", async ({ page }) => {
      await setupAdminMocks(page);
      await page.goto("/admin/sso");

      await page.getByRole("button", { name: /add provider/i }).click();

      await page.getByLabel("Provider Name").fill("New Provider");
      await page.getByLabel("Entity ID").fill("https://example.com/entity");
      await page.getByLabel("SSO URL").fill("https://example.com/sso");

      const createButton = page.getByRole("button", { name: /create|save/i });
      await createButton.click();

      await expect(createButton).toHaveAttribute("data-loading", "true");
      await expect(createButton.getByTestId("button-spinner")).toBeVisible();
      await expect(createButton).toBeDisabled();
    });

    test("shows progress indicator during connection test", async ({ page }) => {
      await setupAdminMocks(page);
      await page.goto("/admin/sso");

      const testButton = page.getByRole("button", { name: /test connection/i }).first();
      await testButton.click();

      await expect(page.getByTestId("test-progress")).toBeVisible();
      await expect(page.getByText(/testing connection/i)).toBeVisible();
    });

    test("shows loading during metadata fetch", async ({ page }) => {
      await setupAdminMocks(page);
      await page.goto("/admin/sso");

      await page.getByRole("button", { name: /add provider/i }).click();

      await page.getByLabel("Metadata URL").fill("https://example.com/metadata.xml");
      await page.getByRole("button", { name: /fetch metadata/i }).click();

      await expect(page.getByTestId("metadata-loading")).toBeVisible();
      await expect(page.getByText(/fetching metadata/i)).toBeVisible();
    });
  });

  test.describe("Error States - Provider Management", () => {
    test("handles provider creation validation errors", async ({ page }) => {
      await setupAdminMocks(page);
      await page.goto("/admin/sso");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/auth/saml/providers" && route.request().method() === "POST") {
          await fulfillJson(
            route,
            {
              error: "Validation Error",
              detail: "Entity ID must be a valid URL",
              field_errors: {
                entity_id: ["Must be a valid URL"],
              },
            },
            400,
          );
          return;
        }
        await route.continue();
      });

      await page.getByRole("button", { name: /add provider/i }).click();

      await page.getByLabel("Provider Name").fill("Invalid Provider");
      await page.getByLabel("Entity ID").fill("not-a-url");
      await page.getByLabel("SSO URL").fill("https://example.com/sso");
      await page.getByRole("button", { name: /create/i }).click();

      await expect(page.getByTestId("field-error-entity_id")).toBeVisible();
      await expect(page.getByText(/must be a valid url/i)).toBeVisible();
    });

    test("handles duplicate provider name errors", async ({ page }) => {
      await setupAdminMocks(page);
      await page.goto("/admin/sso");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/auth/saml/providers" && route.request().method() === "POST") {
          await fulfillJson(
            route,
            {
              error: "Conflict",
              detail: "A provider with this name already exists",
            },
            409,
          );
          return;
        }
        await route.continue();
      });

      await page.getByRole("button", { name: /add provider/i }).click();

      await page.getByLabel("Provider Name").fill("Okta");
      await page.getByLabel("Entity ID").fill("https://example.com/entity");
      await page.getByLabel("SSO URL").fill("https://example.com/sso");
      await page.getByRole("button", { name: /create/i }).click();

      await expect(page.getByTestId("form-error")).toBeVisible();
      await expect(page.getByText(/already exists/i)).toBeVisible();
    });

    test("handles provider update failures", async ({ page }) => {
      await setupAdminMocks(page);
      await page.goto("/admin/sso");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/providers/") && route.request().method() === "PATCH") {
          await fulfillJson(
            route,
            {
              error: "Update Failed",
              detail: "Provider is currently in use and cannot be modified",
            },
            409,
          );
          return;
        }
        await route.continue();
      });

      await page.getByRole("button", { name: /edit/i }).first().click();
      await page.getByLabel("SSO URL").fill("https://new-url.example.com");
      await page.getByRole("button", { name: /save/i }).click();

      await expect(page.getByText(/currently in use|cannot be modified/i)).toBeVisible();
    });

    test("handles provider deletion errors", async ({ page }) => {
      await setupAdminMocks(page);
      await page.goto("/admin/sso");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/providers/") && route.request().method() === "DELETE") {
          await fulfillJson(
            route,
            {
              error: "Deletion Failed",
              detail: "Cannot delete active provider with existing users",
            },
            409,
          );
          return;
        }
        await route.continue();
      });

      await page.getByRole("button", { name: /delete/i }).first().click();
      await page.getByRole("button", { name: /confirm/i }).click();

      await expect(page.getByText(/cannot delete.*existing users/i)).toBeVisible();
    });

    test("handles connection test failures", async ({ page }) => {
      await setupAdminMocks(page);
      await page.goto("/admin/sso");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/test-connection")) {
          await fulfillJson(
            route,
            {
              error: "Connection Test Failed",
              detail: "Unable to connect to IdP. Certificate validation failed.",
            },
            502,
          );
          return;
        }
        await route.continue();
      });

      await page.getByRole("button", { name: /test connection/i }).first().click();

      await expect(page.getByTestId("test-result-error")).toBeVisible();
      await expect(page.getByText(/certificate validation failed/i)).toBeVisible();
    });

    test("handles metadata fetch failures", async ({ page }) => {
      await setupAdminMocks(page);
      await page.goto("/admin/sso");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/fetch-metadata")) {
          await fulfillJson(
            route,
            {
              error: "Metadata Fetch Failed",
              detail: "Unable to retrieve metadata from URL. Server returned 404.",
            },
            502,
          );
          return;
        }
        await route.continue();
      });

      await page.getByRole("button", { name: /add provider/i }).click();
      await page.getByLabel("Metadata URL").fill("https://invalid.example.com/metadata.xml");
      await page.getByRole("button", { name: /fetch metadata/i }).click();

      await expect(page.getByText(/unable to retrieve metadata.*404/i)).toBeVisible();
    });

    test("handles invalid XML metadata errors", async ({ page }) => {
      await setupAdminMocks(page);
      await page.goto("/admin/sso");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/fetch-metadata")) {
          await fulfillJson(
            route,
            {
              error: "Invalid Metadata",
              detail: "Metadata XML is malformed or invalid",
            },
            400,
          );
          return;
        }
        await route.continue();
      });

      await page.getByRole("button", { name: /add provider/i }).click();
      await page.getByLabel("Metadata URL").fill("https://example.com/invalid.xml");
      await page.getByRole("button", { name: /fetch metadata/i }).click();

      await expect(page.getByText(/malformed or invalid/i)).toBeVisible();
    });
  });

  test.describe("Error States - Network & API", () => {
    test("handles network failure during admin operations", async ({ page, context }) => {
      await setupAdminMocks(page);
      await page.goto("/admin/sso");

      await context.setOffline(true);

      await page.getByRole("button", { name: /add provider/i }).click();
      await page.getByLabel("Provider Name").fill("Test");
      await page.getByLabel("Entity ID").fill("https://example.com/entity");
      await page.getByLabel("SSO URL").fill("https://example.com/sso");
      await page.getByRole("button", { name: /create/i }).click();

      await expect(page.getByText(/network error|connection failed/i)).toBeVisible();
    });

    test("handles API 500 errors", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/auth/saml/providers") {
          await fulfillJson(
            route,
            {
              error: "Internal Server Error",
              detail: "Database query failed",
            },
            500,
          );
          return;
        }
        await route.continue();
      });

      await page.goto("/admin/sso");

      await expect(page.getByText(/internal server error|database query failed/i)).toBeVisible();
    });

    test("handles unauthorized access (403)", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/admin") || url.pathname.includes("/saml/providers")) {
          await fulfillJson(
            route,
            {
              error: "Forbidden",
              detail: "Admin permissions required",
            },
            403,
          );
          return;
        }
        await route.continue();
      });

      await page.goto("/admin/sso");

      await expect(page.getByText(/forbidden|admin permissions required/i)).toBeVisible();
      await expect(page.getByRole("link", { name: /back to home/i })).toBeVisible();
    });

    test("handles timeout during long operations", async ({ page }) => {
      await setupAdminMocks(page);
      await page.goto("/admin/sso");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/test-connection")) {
          await new Promise((resolve) => setTimeout(resolve, 30000));
        }
        await route.continue();
      });

      await page.getByRole("button", { name: /test connection/i }).first().click();

      await expect(page.getByText(/timeout|request timed out/i)).toBeVisible({ timeout: 15000 });
      await expect(page.getByRole("button", { name: /cancel/i })).toBeVisible();
    });

    test("handles rate limiting (429)", async ({ page }) => {
      await setupAdminMocks(page);
      await page.goto("/admin/sso");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (route.request().method() === "POST") {
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

      await page.getByRole("button", { name: /add provider/i }).click();
      await page.getByLabel("Provider Name").fill("Test");
      await page.getByLabel("Entity ID").fill("https://example.com/entity");
      await page.getByLabel("SSO URL").fill("https://example.com/sso");
      await page.getByRole("button", { name: /create/i }).click();

      await expect(page.getByText(/rate limit|too many requests/i)).toBeVisible();
    });
  });

  test.describe("Empty States", () => {
    test("shows empty state when no providers configured", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/auth/saml/providers") {
          await fulfillJson(route, []);
          return;
        }
        await route.continue();
      });

      await page.goto("/admin/sso");

      await expect(page.getByTestId("empty-providers")).toBeVisible();
      await expect(page.getByText(/no sso providers configured/i)).toBeVisible();
      await expect(page.getByRole("button", { name: /add provider/i })).toBeVisible();
    });

    test("shows empty state for filtered results", async ({ page }) => {
      await setupAdminMocks(page);
      await page.goto("/admin/sso");

      await page.getByPlaceholder(/search providers/i).fill("nonexistent");

      await expect(page.getByTestId("empty-search-results")).toBeVisible();
      await expect(page.getByText(/no providers match your search/i)).toBeVisible();
      await expect(page.getByRole("button", { name: /clear search/i })).toBeVisible();
    });

    test("shows empty state for audit logs", async ({ page }) => {
      await setupAdminMocks(page);
      await page.goto("/admin/sso/audit");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/audit")) {
          await fulfillJson(route, { items: [], next_cursor: null });
          return;
        }
        await route.continue();
      });

      await expect(page.getByTestId("empty-audit-logs")).toBeVisible();
      await expect(page.getByText(/no audit logs|no activity recorded/i)).toBeVisible();
    });
  });

  test.describe("Error Recovery", () => {
    test("retry button recovers from network error", async ({ page, context }) => {
      await setupAdminMocks(page);
      await page.goto("/admin/sso");

      await context.setOffline(true);

      await page.getByRole("button", { name: /add provider/i }).click();
      await page.getByLabel("Provider Name").fill("Test");
      await page.getByLabel("Entity ID").fill("https://example.com/entity");
      await page.getByLabel("SSO URL").fill("https://example.com/sso");
      await page.getByRole("button", { name: /create/i }).click();

      await expect(page.getByText(/network error/i)).toBeVisible();

      await context.setOffline(false);

      const retryButton = page.getByRole("button", { name: /retry/i });
      await retryButton.click();

      await expect(page.getByText(/network error/i)).not.toBeVisible();
    });

    test("refresh to reload providers list", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/auth/saml/providers") {
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

      await page.goto("/admin/sso");

      await expect(page.getByText(/server error/i)).toBeVisible();

      await page.unroute(API_RE);
      await setupAdminMocks(page);

      const refreshButton = page.getByRole("button", { name: /refresh|reload/i });
      await refreshButton.click();

      await expect(page.getByText(/server error/i)).not.toBeVisible();
      await expect(page.getByTestId("provider-card")).toBeVisible();
    });

    test("clear error and continue editing", async ({ page }) => {
      await setupAdminMocks(page);
      await page.goto("/admin/sso");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/auth/saml/providers" && route.request().method() === "POST") {
          await fulfillJson(
            route,
            {
              error: "Validation Error",
              detail: "SSO URL is required",
            },
            400,
          );
          return;
        }
        await route.continue();
      });

      await page.getByRole("button", { name: /add provider/i }).click();
      await page.getByLabel("Provider Name").fill("Test");
      await page.getByLabel("Entity ID").fill("https://example.com/entity");
      await page.getByRole("button", { name: /create/i }).click();

      await expect(page.getByTestId("form-error")).toBeVisible();

      const dismissButton = page.getByRole("button", { name: /dismiss|close/i });
      await dismissButton.click();

      await expect(page.getByTestId("form-error")).not.toBeVisible();

      // Can continue editing
      await page.getByLabel("SSO URL").fill("https://example.com/sso");
      await expect(page.getByLabel("SSO URL")).toHaveValue("https://example.com/sso");
    });

    test("cancel operation and return to list", async ({ page }) => {
      await setupAdminMocks(page);
      await page.goto("/admin/sso");

      await page.getByRole("button", { name: /add provider/i }).click();

      const cancelButton = page.getByRole("button", { name: /cancel/i });
      await cancelButton.click();

      await expect(page.getByTestId("provider-form")).not.toBeVisible();
      await expect(page.getByTestId("provider-list")).toBeVisible();
    });

    test("auto-save draft on form error", async ({ page }) => {
      await setupAdminMocks(page);
      await page.goto("/admin/sso");

      await page.getByRole("button", { name: /add provider/i }).click();

      await page.getByLabel("Provider Name").fill("Draft Provider");
      await page.getByLabel("Entity ID").fill("https://example.com/entity");

      // Trigger error without SSO URL
      await page.getByRole("button", { name: /create/i }).click();

      await expect(page.getByText(/draft saved|auto-saved/i)).toBeVisible();

      // Refresh page
      await page.reload();

      // Check draft is restored
      await expect(page.getByLabel("Provider Name")).toHaveValue("Draft Provider");
      await expect(page.getByLabel("Entity ID")).toHaveValue("https://example.com/entity");
    });
  });
});
