/**
 * Comprehensive error state testing for SSO login flow
 * Tests: loading states, error states, empty states, and error recovery
 */
import { expect, test, type Page, type Route } from "@playwright/test";

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

function fulfillJson(route: Route, payload: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}

async function setupSSOMocks(
  page: Page,
  config: {
    samlProviders?: Array<{ id: string; name: string; enabled: boolean }>;
    oauthProviders?: string[];
  } = {},
) {
  const authConfig: AuthConfig = {
    public_registration_enabled: false,
    oauth_providers: config.oauthProviders ?? ["google", "github"],
    saml_providers: config.samlProviders ?? [
      { id: "okta-prod", name: "Okta", enabled: true },
      { id: "azure-ad", name: "Azure AD", enabled: true },
    ],
  };

  await page.route(API_RE, async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    if (path === "/api/auth/config" && method === "GET") {
      await fulfillJson(route, authConfig);
      return;
    }

    if (path.startsWith("/api/auth/saml/") && path.endsWith("/start") && method === "POST") {
      const providerId = path.split("/")[4];
      await fulfillJson(route, {
        redirect_url: `https://idp.example.com/saml/sso?provider=${providerId}`,
      });
      return;
    }

    if (path.startsWith("/api/auth/oauth/") && path.endsWith("/start") && method === "GET") {
      const provider = path.split("/")[4];
      await fulfillJson(route, {
        redirect_url: `https://oauth.example.com/authorize?provider=${provider}`,
      });
      return;
    }

    await route.continue();
  });
}

test.describe("SSO Login - Error States", () => {
  test.describe("Loading States", () => {
    test("shows loading spinner during SSO configuration fetch", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/auth/config") {
          await new Promise((resolve) => setTimeout(resolve, 1000));
        }
        await route.continue();
      });

      const navigationPromise = page.goto("/auth/login");

      await expect(page.getByTestId("auth-loading")).toBeVisible();

      await navigationPromise;

      await expect(page.getByTestId("auth-loading")).not.toBeVisible();
    });

    test("shows button loading state during SAML initiation", async ({ page }) => {
      await setupSSOMocks(page);
      await page.goto("/auth/login");

      const samlButton = page.getByRole("button", { name: /sign in with okta/i });
      await samlButton.click();

      await expect(samlButton).toHaveAttribute("data-loading", "true");
      await expect(samlButton.getByTestId("button-spinner")).toBeVisible();
      await expect(samlButton).toBeDisabled();
    });

    test("shows loading state during OAuth redirect", async ({ page }) => {
      await setupSSOMocks(page);
      await page.goto("/auth/login");

      const googleButton = page.getByRole("button", { name: /sign in with google/i });
      await googleButton.click();

      await expect(page.getByTestId("oauth-redirect-loading")).toBeVisible();
      await expect(page.getByText(/redirecting to google/i)).toBeVisible();
    });

    test("shows loading indicator during SAML callback processing", async ({ page }) => {
      await setupSSOMocks(page);

      await page.goto("/auth/saml/callback?SAMLResponse=mock-response&RelayState=state");

      await expect(page.getByTestId("saml-callback-loading")).toBeVisible();
      await expect(page.getByText(/completing sign in|verifying/i)).toBeVisible();
    });

    test("shows progress indicator for multi-step SSO flow", async ({ page }) => {
      await setupSSOMocks(page);
      await page.goto("/auth/login");

      const samlButton = page.getByRole("button", { name: /sign in with okta/i });
      await samlButton.click();

      await expect(page.getByTestId("sso-progress")).toBeVisible();
      await expect(page.getByText(/step 1|initiating/i)).toBeVisible();
    });
  });

  test.describe("Error States - SAML Errors", () => {
    test("handles SAML IdP unavailable (503)", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/saml/") && url.pathname.endsWith("/start")) {
          await fulfillJson(
            route,
            {
              error: "Service Unavailable",
              detail: "SAML Identity Provider is temporarily unavailable",
            },
            503,
          );
          return;
        }
        await route.continue();
      });

      await setupSSOMocks(page);
      await page.goto("/auth/login");

      const samlButton = page.getByRole("button", { name: /sign in with okta/i });
      await samlButton.click();

      await expect(page.getByTestId("error-alert")).toBeVisible();
      await expect(page.getByText(/identity provider.*unavailable/i)).toBeVisible();
      await expect(page.getByRole("button", { name: /try again|retry/i })).toBeVisible();
    });

    test("handles SAML configuration errors", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/saml/") && url.pathname.endsWith("/start")) {
          await fulfillJson(
            route,
            {
              error: "Configuration Error",
              detail: "SAML provider is not properly configured",
            },
            500,
          );
          return;
        }
        await route.continue();
      });

      await setupSSOMocks(page);
      await page.goto("/auth/login");

      const samlButton = page.getByRole("button", { name: /sign in with okta/i });
      await samlButton.click();

      await expect(page.getByText(/configuration error|not properly configured/i)).toBeVisible();
      await expect(page.getByText(/contact administrator/i)).toBeVisible();
    });

    test("handles SAML assertion validation failures", async ({ page }) => {
      await setupSSOMocks(page);

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/saml/callback")) {
          await fulfillJson(
            route,
            {
              error: "Invalid SAML Response",
              detail: "SAML assertion validation failed",
            },
            400,
          );
          return;
        }
        await route.continue();
      });

      await page.goto("/auth/saml/callback?SAMLResponse=invalid");

      await expect(page.getByText(/invalid saml response|validation failed/i)).toBeVisible();
      await expect(page.getByRole("link", { name: /back to login/i })).toBeVisible();
    });

    test("handles SAML timeout errors", async ({ page }) => {
      await setupSSOMocks(page);
      await page.goto("/auth/login");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/saml/")) {
          await new Promise((resolve) => setTimeout(resolve, 60000));
        }
        await route.continue();
      });

      const samlButton = page.getByRole("button", { name: /sign in with okta/i });
      await samlButton.click();

      await expect(page.getByText(/timeout|request timed out/i)).toBeVisible({ timeout: 15000 });
      await expect(page.getByRole("button", { name: /retry/i })).toBeVisible();
    });

    test("handles SAML RelayState tampering", async ({ page }) => {
      await setupSSOMocks(page);

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/saml/callback")) {
          await fulfillJson(
            route,
            {
              error: "Security Error",
              detail: "RelayState validation failed. Possible CSRF attack.",
            },
            403,
          );
          return;
        }
        await route.continue();
      });

      await page.goto("/auth/saml/callback?SAMLResponse=mock&RelayState=tampered");

      await expect(page.getByText(/security error|relaystate validation/i)).toBeVisible();
      await expect(page.getByRole("link", { name: /start over|back to login/i })).toBeVisible();
    });
  });

  test.describe("Error States - OAuth Errors", () => {
    test("handles OAuth provider errors", async ({ page }) => {
      await setupSSOMocks(page);
      await page.goto("/auth/oauth/callback?error=access_denied&error_description=User+cancelled");

      await expect(page.getByTestId("oauth-error")).toBeVisible();
      await expect(page.getByText(/access denied|user cancelled/i)).toBeVisible();
      await expect(page.getByRole("link", { name: /try again|back to login/i })).toBeVisible();
    });

    test("handles OAuth state mismatch (CSRF)", async ({ page }) => {
      await setupSSOMocks(page);

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/oauth/callback")) {
          await fulfillJson(
            route,
            {
              error: "State Mismatch",
              detail: "OAuth state parameter does not match. Possible CSRF attack.",
            },
            403,
          );
          return;
        }
        await route.continue();
      });

      await page.goto("/auth/oauth/callback?code=abc&state=invalid");

      await expect(page.getByText(/state mismatch|csrf/i)).toBeVisible();
    });

    test("handles OAuth token exchange failures", async ({ page }) => {
      await setupSSOMocks(page);

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/oauth/callback")) {
          await fulfillJson(
            route,
            {
              error: "Token Exchange Failed",
              detail: "Failed to exchange authorization code for access token",
            },
            502,
          );
          return;
        }
        await route.continue();
      });

      await page.goto("/auth/oauth/callback?code=abc&state=valid");

      await expect(page.getByText(/token exchange failed/i)).toBeVisible();
      await expect(page.getByRole("button", { name: /retry/i })).toBeVisible();
    });

    test("handles OAuth invalid_grant errors", async ({ page }) => {
      await setupSSOMocks(page);
      await page.goto("/auth/oauth/callback?error=invalid_grant&error_description=Code+expired");

      await expect(page.getByText(/invalid grant|code expired/i)).toBeVisible();
      await expect(page.getByText(/start the sign-in process again/i)).toBeVisible();
    });
  });

  test.describe("Error States - Network & API", () => {
    test("handles network failure during SSO", async ({ page, context }) => {
      await setupSSOMocks(page);
      await page.goto("/auth/login");

      await context.setOffline(true);

      const samlButton = page.getByRole("button", { name: /sign in with okta/i });
      await samlButton.click();

      await expect(page.getByText(/network error|connection failed/i)).toBeVisible();
      await expect(page.getByRole("button", { name: /retry/i })).toBeVisible();
    });

    test("handles API 500 errors during auth config fetch", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/auth/config") {
          await fulfillJson(
            route,
            {
              error: "Internal Server Error",
              detail: "Failed to load authentication configuration",
            },
            500,
          );
          return;
        }
        await route.continue();
      });

      await page.goto("/auth/login");

      await expect(page.getByText(/failed to load.*configuration/i)).toBeVisible();
      await expect(page.getByRole("button", { name: /reload|refresh/i })).toBeVisible();
    });

    test("handles rate limiting on SSO endpoints (429)", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/auth/")) {
          await fulfillJson(
            route,
            {
              error: "Too Many Requests",
              detail: "Rate limit exceeded. Please wait 60 seconds.",
            },
            429,
          );
          return;
        }
        await route.continue();
      });

      await setupSSOMocks(page);
      await page.goto("/auth/login");

      const samlButton = page.getByRole("button", { name: /sign in with okta/i });
      await samlButton.click();

      await expect(page.getByText(/rate limit|too many requests/i)).toBeVisible();
      await expect(page.getByText(/wait 60 seconds/i)).toBeVisible();
    });

    test("handles session timeout during SSO flow", async ({ page }) => {
      await setupSSOMocks(page);
      await page.goto("/auth/login");

      const samlButton = page.getByRole("button", { name: /sign in with okta/i });
      await samlButton.click();

      // Simulate session timeout during redirect
      await page.route(API_RE, async (route) => {
        await fulfillJson(
          route,
          {
            error: "Session Expired",
            detail: "Authentication session expired. Please start over.",
          },
          401,
        );
      });

      await page.goto("/auth/saml/callback?SAMLResponse=mock");

      await expect(page.getByText(/session expired/i)).toBeVisible();
      await expect(page.getByRole("link", { name: /start over/i })).toBeVisible();
    });
  });

  test.describe("Empty States", () => {
    test("shows empty state when no SSO providers configured", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/auth/config") {
          await fulfillJson(route, {
            public_registration_enabled: false,
            oauth_providers: [],
            saml_providers: [],
          });
          return;
        }
        await route.continue();
      });

      await page.goto("/auth/login");

      await expect(page.getByTestId("empty-sso-providers")).toBeVisible();
      await expect(page.getByText(/no sign-in methods available/i)).toBeVisible();
      await expect(page.getByText(/contact administrator/i)).toBeVisible();
    });

    test("shows empty state for disabled providers", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/auth/config") {
          await fulfillJson(route, {
            public_registration_enabled: false,
            oauth_providers: [],
            saml_providers: [
              { id: "okta-prod", name: "Okta", enabled: false },
              { id: "azure-ad", name: "Azure AD", enabled: false },
            ],
          });
          return;
        }
        await route.continue();
      });

      await page.goto("/auth/login");

      await expect(page.getByText(/all sign-in methods are disabled/i)).toBeVisible();
    });
  });

  test.describe("Error Recovery", () => {
    test("retry button recovers from network error", async ({ page, context }) => {
      await setupSSOMocks(page);
      await page.goto("/auth/login");

      await context.setOffline(true);

      const samlButton = page.getByRole("button", { name: /sign in with okta/i });
      await samlButton.click();

      await expect(page.getByText(/network error/i)).toBeVisible();

      await context.setOffline(false);

      const retryButton = page.getByRole("button", { name: /retry/i });
      await retryButton.click();

      await expect(page.getByText(/network error/i)).not.toBeVisible();
    });

    test("refresh to reload SSO configuration", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/auth/config") {
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

      await page.goto("/auth/login");

      await expect(page.getByText(/failed to load/i)).toBeVisible();

      await page.unroute(API_RE);
      await setupSSOMocks(page);

      const refreshButton = page.getByRole("button", { name: /reload|refresh/i });
      await refreshButton.click();

      await expect(page.getByText(/failed to load/i)).not.toBeVisible();
      await expect(page.getByRole("button", { name: /sign in with okta/i })).toBeVisible();
    });

    test("back to login link from error state", async ({ page }) => {
      await setupSSOMocks(page);
      await page.goto("/auth/saml/callback?error=invalid_response");

      const backLink = page.getByRole("link", { name: /back to login/i });
      await expect(backLink).toBeVisible();
      await backLink.click();

      await expect(page).toHaveURL(/\/auth\/login/);
      await expect(page.getByRole("button", { name: /sign in with okta/i })).toBeVisible();
    });

    test("clear error and try different provider", async ({ page }) => {
      await setupSSOMocks(page);
      await page.goto("/auth/login");

      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname.includes("/saml/okta-prod")) {
          await fulfillJson(
            route,
            {
              error: "Service Unavailable",
            },
            503,
          );
          return;
        }
        await route.continue();
      });

      const oktaButton = page.getByRole("button", { name: /sign in with okta/i });
      await oktaButton.click();

      await expect(page.getByText(/service unavailable/i)).toBeVisible();

      const dismissButton = page.getByRole("button", { name: /dismiss|close/i });
      await dismissButton.click();

      await expect(page.getByText(/service unavailable/i)).not.toBeVisible();

      // Try different provider
      const azureButton = page.getByRole("button", { name: /sign in with azure/i });
      await expect(azureButton).toBeVisible();
      await expect(azureButton).not.toBeDisabled();
    });

    test("fallback to alternative authentication method", async ({ page }) => {
      await page.route(API_RE, async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/auth/config") {
          await fulfillJson(route, {
            public_registration_enabled: true,
            oauth_providers: ["google"],
            saml_providers: [{ id: "okta-prod", name: "Okta", enabled: false }],
          });
          return;
        }
        await route.continue();
      });

      await page.goto("/auth/login");

      await expect(page.getByText(/okta.*unavailable|disabled/i)).toBeVisible();
      await expect(page.getByRole("button", { name: /sign in with google/i })).toBeVisible();
      await expect(page.getByRole("link", { name: /use email and password/i })).toBeVisible();
    });
  });
});
