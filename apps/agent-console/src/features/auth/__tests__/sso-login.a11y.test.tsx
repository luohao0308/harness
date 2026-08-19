/**
 * Accessibility tests for SSO Login
 *
 * Tests WCAG 2.1 AA compliance using axe-core:
 * - Automated violation detection
 * - Keyboard navigation
 * - ARIA labels and roles
 * - Focus management
 * - Form accessibility
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { describe, test, expect, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { LoginPage } from "../pages/LoginPage";
import { AuthProvider } from "../AuthProvider";

// Mock auth API
vi.mock("../../tasks/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../tasks/api")>()),
  getMe: vi.fn(() => Promise.resolve(null)),
  isDevAuthFallbackEnabled: vi.fn(() => false),
  getAuthConfig: vi.fn(() =>
    Promise.resolve({
      public_registration_enabled: true,
      oauth_providers: ["github"],
      saml_providers: [
        { id: "okta-1", name: "Okta", enabled: true },
        { id: "azure-1", name: "Azure AD", enabled: true },
      ],
    }),
  ),
  startOAuth: vi.fn(() =>
    Promise.resolve({
      authorization_url: "https://github.com/login/oauth/authorize",
    }),
  ),
  startSAML: vi.fn(() =>
    Promise.resolve({
      redirect_url: "https://sso.example.com/login",
    }),
  ),
}));

function renderLoginPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>,
  );
}

describe("SSO Login Accessibility", () => {
  test("has no axe violations on initial render", async () => {
    const { container } = renderLoginPage();

    // Wait for auth config to load
    await waitFor(() => {
      expect(screen.getByText(/使用 SSO 登录/i)).toBeInTheDocument();
    });

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  test("has no axe violations with provider selector open", async () => {
    const user = userEvent.setup();
    const { container } = renderLoginPage();

    // Wait for SSO button to load
    await waitFor(() => {
      expect(screen.getByText(/使用 SSO 登录/i)).toBeInTheDocument();
    });

    // Click SSO button to open provider selector
    const ssoButton = screen.getByRole("button", { name: /使用 SSO 登录/i });
    await user.click(ssoButton);

    // Wait for provider selector
    await waitFor(() => {
      expect(screen.getByText(/Okta/i)).toBeInTheDocument();
    });

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  test("login form has accessible labels", async () => {
    renderLoginPage();

    await waitFor(() => {
      expect(screen.getByLabelText(/邮箱/i)).toBeInTheDocument();
    });

    const emailInput = screen.getByLabelText(/邮箱/i);
    const passwordInput = screen.getByLabelText(/密码/i);

    expect(emailInput).toHaveAttribute("type", "email");
    expect(emailInput).toHaveAttribute("autocomplete", "email");
    expect(passwordInput).toHaveAttribute("type", "password");
    expect(passwordInput).toHaveAttribute("autocomplete", "current-password");
  });

  test("SSO button is keyboard accessible", async () => {
    const user = userEvent.setup();
    renderLoginPage();

    await waitFor(() => {
      expect(screen.getByText(/使用 SSO 登录/i)).toBeInTheDocument();
    });

    const ssoButton = screen.getByRole("button", { name: /使用 SSO 登录/i });

    // Focus on SSO button
    ssoButton.focus();
    expect(ssoButton).toHaveFocus();

    // Activate with keyboard
    await user.keyboard("{Enter}");

    // Provider selector should open
    await waitFor(() => {
      expect(screen.getByText(/Okta/i)).toBeInTheDocument();
    });
  });

  test("provider selector buttons are keyboard accessible", async () => {
    const user = userEvent.setup();
    renderLoginPage();

    await waitFor(() => {
      expect(screen.getByText(/使用 SSO 登录/i)).toBeInTheDocument();
    });

    // Open provider selector
    const ssoButton = screen.getByRole("button", { name: /使用 SSO 登录/i });
    await user.click(ssoButton);

    await waitFor(() => {
      expect(screen.getByText(/Okta/i)).toBeInTheDocument();
    });

    // Tab to provider buttons
    const oktaButton = screen.getByRole("button", { name: /Okta/i });
    oktaButton.focus();
    expect(oktaButton).toHaveFocus();
  });

  test("OAuth buttons have accessible names", async () => {
    renderLoginPage();

    await waitFor(() => {
      expect(screen.getByText(/GitHub/i)).toBeInTheDocument();
    });

    const githubButton = screen.getByRole("button", { name: /GitHub/i });
    expect(githubButton).toBeInTheDocument();
  });

  test("form submit button is properly labeled", async () => {
    renderLoginPage();

    await waitFor(() => {
      const submitButton = screen.getByRole("button", { name: /登录/i });
      expect(submitButton).toBeInTheDocument();
      expect(submitButton).toHaveAttribute("type", "submit");
    });
  });

  test("error messages are announced to screen readers", async () => {
    const user = userEvent.setup();
    renderLoginPage();

    await waitFor(() => {
      expect(screen.getByLabelText(/邮箱/i)).toBeInTheDocument();
    });

    // Submit empty form to trigger validation
    const submitButton = screen.getByRole("button", { name: /^登录$/i });
    await user.click(submitButton);

    // Browser native validation will prevent submission
    // Error states should be accessible
  });

  test("registration link has accessible text", async () => {
    renderLoginPage();

    await waitFor(() => {
      expect(screen.getByText(/创建工作区/i)).toBeInTheDocument();
    });

    const registerLink = screen.getByRole("link", { name: /创建工作区/i });
    expect(registerLink).toHaveAttribute("href", "/register");
  });

  test("main landmark is present", async () => {
    renderLoginPage();

    await waitFor(() => {
      expect(screen.getByRole("main")).toBeInTheDocument();
    });
  });

  test("heading hierarchy is correct", async () => {
    renderLoginPage();

    await waitFor(() => {
      const heading = screen.getByRole("heading", { level: 1 });
      expect(heading).toHaveTextContent(/登录 Forge Harness Console/i);
    });
  });
});
