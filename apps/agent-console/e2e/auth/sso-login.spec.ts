/**
 * E2E Test: SSO/SAML Login Flow
 *
 * Tests the Single Sign-On (SAML) authentication flow including:
 * - Single provider direct flow
 * - Multiple providers selection
 * - Error handling
 * - Loading states
 */
import { expect, test } from "@playwright/test";
import type { Page, Route } from "@playwright/test";

const API_RE = /http:\/\/(?:127\.0\.0\.1|localhost):(?:8000|5177|15174)\/api\/.*/;

interface AuthConfig {
  public_registration_enabled: boolean;
  oauth_providers: string[];
  saml_providers: Array<{
    id: string;
    name: string;
    enabled: boolean;
  }>;
}

interface SAMLStartResponse {
  redirect_url: string;
}

function fulfillJson(route: Route, payload: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}

async function setupAuthMocks(
  page: Page,
  config: {
    samlProviders?: Array<{ id: string; name: string; enabled: boolean }>;
    shouldFailSAML?: boolean;
    samlErrorMessage?: string;
  } = {},
) {
  const authConfig: AuthConfig = {
    public_registration_enabled: false,
    oauth_providers: [],
    saml_providers: config.samlProviders ?? [
      { id: "okta-prod", name: "Okta", enabled: true },
    ],
  };

  await page.route(API_RE, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    // Get auth config
    if (path === "/api/auth/config" && method === "GET") {
      await fulfillJson(route, authConfig);
      return;
    }

    // Start SAML flow
    if (path.startsWith("/api/auth/saml/") && path.endsWith("/start") && method === "POST") {
      const providerId = path.split("/")[4];

      if (config.shouldFailSAML) {
        await fulfillJson(
          route,
          {
            error: "SAML initiation failed",
            detail: config.samlErrorMessage ?? "IdP is temporarily unavailable",
          },
          503,
        );
        return;
      }

      const response: SAMLStartResponse = {
        redirect_url: `https://idp.example.com/saml/sso?SAMLRequest=mock-request-${providerId}`,
      };
      await fulfillJson(route, response);
      return;
    }

    // Fallback for unhandled routes
    if (method === "GET") {
      await fulfillJson(route, { items: [], next_cursor: null });
      return;
    }

    await fulfillJson(
      route,
      {
        error: "Not found",
        detail: `Unhandled route: ${method} ${path}`,
      },
      404,
    );
  });
}

test.describe("SSO/SAML Login Flow", () => {
  test("should show SSO button when single provider is configured", async ({ page }) => {
    await setupAuthMocks(page, {
      samlProviders: [{ id: "okta-prod", name: "Okta", enabled: true }],
    });

    await page.goto("/login");

    // Verify SSO button is visible
    await expect(page.locator('button:has-text("使用 SSO 登录")')).toBeVisible();

    // Verify it shows the building icon
    await expect(page.locator('button:has-text("使用 SSO 登录") svg')).toBeVisible();
  });

  test("should initiate SAML flow with single provider", async ({ page }) => {
    await setupAuthMocks(page, {
      samlProviders: [{ id: "okta-prod", name: "Okta", enabled: true }],
    });

    await page.goto("/login");

    // Click SSO login button
    const ssoButton = page.locator('button:has-text("使用 SSO 登录")');
    await expect(ssoButton).toBeVisible();

    // Set up navigation interception to verify redirect URL
    const navigationPromise = page.waitForURL(/idp\.example\.com\/saml\/sso/, {
      timeout: 5000,
    });

    await ssoButton.click();

    // Should show loading state
    await expect(page.locator('button:has-text("使用 SSO 登录") svg.animate-spin')).toBeVisible({
      timeout: 1000,
    });

    // Should redirect to IdP
    await navigationPromise;
    expect(page.url()).toContain("idp.example.com/saml/sso");
    expect(page.url()).toContain("SAMLRequest=mock-request-okta-prod");
  });

  test("should show provider selector with multiple providers", async ({ page }) => {
    await setupAuthMocks(page, {
      samlProviders: [
        { id: "okta-prod", name: "Okta", enabled: true },
        { id: "azure-ad", name: "Azure AD", enabled: true },
        { id: "google-workspace", name: "Google Workspace", enabled: true },
      ],
    });

    await page.goto("/login");

    // Click SSO login button
    const ssoButton = page.locator('button:has-text("使用 SSO 登录")');
    await expect(ssoButton).toBeVisible();
    await ssoButton.click();

    // Should show provider selector
    await expect(page.locator('text=选择 SSO 提供商')).toBeVisible();

    // Should show all enabled providers
    await expect(page.locator('button:has-text("Okta")')).toBeVisible();
    await expect(page.locator('button:has-text("Azure AD")')).toBeVisible();
    await expect(page.locator('button:has-text("Google Workspace")')).toBeVisible();

    // Should show cancel button
    await expect(page.locator('button:has-text("取消")')).toBeVisible();
  });

  test("should initiate SAML flow after provider selection", async ({ page }) => {
    await setupAuthMocks(page, {
      samlProviders: [
        { id: "okta-prod", name: "Okta", enabled: true },
        { id: "azure-ad", name: "Azure AD", enabled: true },
      ],
    });

    await page.goto("/login");

    // Click SSO login button
    await page.locator('button:has-text("使用 SSO 登录")').click();

    // Wait for provider selector
    await expect(page.locator('text=选择 SSO 提供商')).toBeVisible();

    // Select Azure AD
    const azureButton = page.locator('button:has-text("Azure AD")');
    await expect(azureButton).toBeVisible();

    // Set up navigation interception
    const navigationPromise = page.waitForURL(/idp\.example\.com\/saml\/sso/, {
      timeout: 5000,
    });

    await azureButton.click();

    // Should redirect to IdP with correct provider ID
    await navigationPromise;
    expect(page.url()).toContain("SAMLRequest=mock-request-azure-ad");
  });

  test("should allow canceling provider selection", async ({ page }) => {
    await setupAuthMocks(page, {
      samlProviders: [
        { id: "okta-prod", name: "Okta", enabled: true },
        { id: "azure-ad", name: "Azure AD", enabled: true },
      ],
    });

    await page.goto("/login");

    // Click SSO login button
    await page.locator('button:has-text("使用 SSO 登录")').click();

    // Wait for provider selector
    await expect(page.locator('text=选择 SSO 提供商')).toBeVisible();

    // Click cancel
    await page.locator('button:has-text("取消")').click();

    // Provider selector should disappear
    await expect(page.locator('text=选择 SSO 提供商')).not.toBeVisible();

    // SSO button should be visible again
    await expect(page.locator('button:has-text("使用 SSO 登录")')).toBeVisible();
  });

  test("should handle SAML initiation errors gracefully", async ({ page }) => {
    await setupAuthMocks(page, {
      samlProviders: [{ id: "okta-prod", name: "Okta", enabled: true }],
      shouldFailSAML: true,
      samlErrorMessage: "IdP is temporarily unavailable",
    });

    await page.goto("/login");

    // Click SSO login button
    const ssoButton = page.locator('button:has-text("使用 SSO 登录")');
    await ssoButton.click();

    // Should show error message
    await expect(page.locator('text=IdP is temporarily unavailable')).toBeVisible({
      timeout: 5000,
    });

    // Error should be in red background
    await expect(page.locator('.bg-red-50:has-text("IdP is temporarily unavailable")')).toBeVisible();

    // Button should be enabled again (not stuck in loading state)
    await expect(ssoButton).toBeEnabled();

    // Loading spinner should not be visible
    await expect(page.locator('button:has-text("使用 SSO 登录") svg.animate-spin')).not.toBeVisible();
  });

  test("should handle network errors during SAML initiation", async ({ page }) => {
    await setupAuthMocks(page, {
      samlProviders: [{ id: "okta-prod", name: "Okta", enabled: true }],
      shouldFailSAML: true,
      samlErrorMessage: "Network request failed",
    });

    await page.goto("/login");

    // Click SSO login button
    await page.locator('button:has-text("使用 SSO 登录")').click();

    // Should show network error
    await expect(page.locator('.bg-red-50:has-text("Network request failed")')).toBeVisible({
      timeout: 5000,
    });

    // User should be able to retry
    const ssoButton = page.locator('button:has-text("使用 SSO 登录")');
    await expect(ssoButton).toBeEnabled();
  });

  test("should hide SSO button when no providers are enabled", async ({ page }) => {
    await setupAuthMocks(page, {
      samlProviders: [
        { id: "okta-prod", name: "Okta", enabled: false },
        { id: "azure-ad", name: "Azure AD", enabled: false },
      ],
    });

    await page.goto("/login");

    // SSO button should not be visible
    await expect(page.locator('button:has-text("使用 SSO 登录")')).not.toBeVisible();

    // Only regular login form should be visible
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]:has-text("登录")')).toBeVisible();
  });

  test("should filter out disabled providers from selector", async ({ page }) => {
    await setupAuthMocks(page, {
      samlProviders: [
        { id: "okta-prod", name: "Okta", enabled: true },
        { id: "azure-ad", name: "Azure AD", enabled: false },
        { id: "google-workspace", name: "Google Workspace", enabled: true },
      ],
    });

    await page.goto("/login");

    // Click SSO login button
    await page.locator('button:has-text("使用 SSO 登录")').click();

    // Should show provider selector
    await expect(page.locator('text=选择 SSO 提供商')).toBeVisible();

    // Should only show enabled providers
    await expect(page.locator('button:has-text("Okta")')).toBeVisible();
    await expect(page.locator('button:has-text("Google Workspace")')).toBeVisible();

    // Should NOT show disabled provider
    await expect(page.locator('button:has-text("Azure AD")')).not.toBeVisible();
  });

  test("should disable SSO button when regular login is pending", async ({ page }) => {
    await setupAuthMocks(page, {
      samlProviders: [{ id: "okta-prod", name: "Okta", enabled: true }],
    });

    // Add a delay to password login to simulate pending state
    await page.route(API_RE, async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname;

      if (path === "/api/auth/login" && request.method() === "POST") {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        await fulfillJson(route, { error: "Invalid credentials" }, 401);
        return;
      }

      await route.continue();
    });

    await page.goto("/login");

    // Fill in credentials
    await page.locator('input[type="email"]').fill("test@example.com");
    await page.locator('input[type="password"]').fill("password123");

    // Submit login form
    await page.locator('button[type="submit"]:has-text("登录")').click();

    // SSO button should be disabled while regular login is pending
    const ssoButton = page.locator('button:has-text("使用 SSO 登录")');
    await expect(ssoButton).toBeDisabled();
  });

  test("should show loading spinner during SAML initiation", async ({ page }) => {
    await setupAuthMocks(page, {
      samlProviders: [{ id: "okta-prod", name: "Okta", enabled: true }],
    });

    // Add delay to SAML start endpoint
    await page.route(API_RE, async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname;

      if (path.includes("/api/auth/saml/") && path.endsWith("/start")) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        await fulfillJson(route, {
          redirect_url: "https://idp.example.com/saml/sso?SAMLRequest=mock-request",
        });
        return;
      }

      await route.continue();
    });

    await page.goto("/login");

    // Click SSO button
    const ssoButton = page.locator('button:has-text("使用 SSO 登录")');
    await ssoButton.click();

    // Should show loading spinner (Loader2 icon with animate-spin)
    await expect(page.locator('button:has-text("使用 SSO 登录") svg.animate-spin')).toBeVisible();

    // Button should be disabled during loading
    await expect(ssoButton).toBeDisabled();
  });

  test("should handle provider selection error and allow retry", async ({ page }) => {
    let attemptCount = 0;

    await setupAuthMocks(page, {
      samlProviders: [
        { id: "okta-prod", name: "Okta", enabled: true },
        { id: "azure-ad", name: "Azure AD", enabled: true },
      ],
    });

    // Override to fail first attempt, succeed second
    await page.route(API_RE, async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname;

      if (path.includes("/api/auth/saml/azure-ad/start") && request.method() === "POST") {
        attemptCount++;
        if (attemptCount === 1) {
          await fulfillJson(
            route,
            { error: "Temporary error", detail: "Service temporarily unavailable" },
            503,
          );
          return;
        }
      }

      await route.continue();
    });

    await page.goto("/login");

    // Click SSO button
    await page.locator('button:has-text("使用 SSO 登录")').click();

    // Select Azure AD
    await page.locator('button:has-text("Azure AD")').click();

    // Should show error
    await expect(page.locator('text=Service temporarily unavailable')).toBeVisible();

    // Provider selector should still be visible for retry
    await expect(page.locator('text=选择 SSO 提供商')).toBeVisible();

    // Try again with Azure AD
    const navigationPromise = page.waitForURL(/idp\.example\.com\/saml\/sso/, { timeout: 5000 });
    await page.locator('button:has-text("Azure AD")').click();

    // Should succeed on second attempt
    await navigationPromise;
    expect(page.url()).toContain("SAMLRequest=mock-request-azure-ad");
  });
});
