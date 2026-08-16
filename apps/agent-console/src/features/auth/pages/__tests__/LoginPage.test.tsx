import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const authMock = vi.hoisted(() => ({
  loginWithPassword: vi.fn(async () => ({
    user_id: "user-1",
    email: "owner@example.com",
    name: "Owner User",
    organization_id: "org-1",
    role: "owner",
    permissions: [],
    organizations: [{ id: "org-1", name: "Acme", slug: "acme", role: "owner" }],
  })),
}));

const apiMock = vi.hoisted(() => ({
  getAuthConfig: vi.fn(async () => ({
    public_registration_enabled: false,
    oauth_providers: [] as string[],
    saml_providers: [] as Array<{ id: string; name: string; enabled: boolean }>,
  })),
  startOAuth: vi.fn(),
  startSAML: vi.fn(),
}));

const originalLocationDescriptor = Object.getOwnPropertyDescriptor(window, "location");

vi.mock("../../AuthProvider", () => ({
  useAuth: () => ({
    loginWithPassword: authMock.loginWithPassword,
  }),
}));

vi.mock("../../../tasks/api", () => ({
  getAuthConfig: apiMock.getAuthConfig,
  startOAuth: apiMock.startOAuth,
  startSAML: apiMock.startSAML,
}));

import { LoginPage } from "../LoginPage";

function renderLogin(initialPath = "/login") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/settings/secrets" element={<div>密钥库页面</div>} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  if (originalLocationDescriptor) {
    Object.defineProperty(window, "location", originalLocationDescriptor);
  }
  authMock.loginWithPassword.mockClear();
  apiMock.getAuthConfig.mockReset();
  apiMock.getAuthConfig.mockResolvedValue({
    public_registration_enabled: false,
    oauth_providers: [],
    saml_providers: [],
  });
  apiMock.startOAuth.mockReset();
  apiMock.startSAML.mockReset();
});

describe("LoginPage", () => {
  it("hides public registration and OAuth actions when auth config disables them", async () => {
    renderLogin();

    await waitFor(() => expect(apiMock.getAuthConfig).toHaveBeenCalledTimes(1));

    expect(screen.queryByRole("link", { name: "创建工作区" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "GitHub" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Google" })).not.toBeInTheDocument();
  });

  it("shows only backend-configured registration and OAuth providers", async () => {
    apiMock.getAuthConfig.mockResolvedValue({
      public_registration_enabled: true,
      oauth_providers: ["github"],
      saml_providers: [],
    });

    renderLogin();

    expect(await screen.findByRole("link", { name: "创建工作区" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "GitHub" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Google" })).not.toBeInTheDocument();
  });

  it("returns to the requested route after password login", async () => {
    const user = userEvent.setup();
    renderLogin("/login?next=/settings/secrets");

    await user.type(screen.getByLabelText("邮箱"), "owner@example.com");
    await user.type(screen.getByLabelText("密码"), "correct-password");
    await user.click(screen.getByRole("button", { name: "登录" }));

    await screen.findByText("密钥库页面");
    expect(authMock.loginWithPassword).toHaveBeenCalledWith({
      email: "owner@example.com",
      password: "correct-password",
    });
  });

  it("shows SSO button when SAML providers are configured", async () => {
    apiMock.getAuthConfig.mockResolvedValue({
      public_registration_enabled: false,
      oauth_providers: [],
      saml_providers: [{ id: "okta-1", name: "Okta", enabled: true }],
    });

    renderLogin();

    expect(await screen.findByRole("button", { name: /使用 SSO 登录/i })).toBeInTheDocument();
  });

  it("hides SSO button when no SAML providers are configured", async () => {
    renderLogin();

    await waitFor(() => expect(apiMock.getAuthConfig).toHaveBeenCalledTimes(1));

    expect(screen.queryByRole("button", { name: /使用 SSO 登录/i })).not.toBeInTheDocument();
  });

  it("initiates SAML SSO flow when SSO button is clicked", async () => {
    const user = userEvent.setup();
    const mockRedirectUrl = "https://idp.example.com/saml/login?SAMLRequest=...";
    apiMock.getAuthConfig.mockResolvedValue({
      public_registration_enabled: false,
      oauth_providers: [],
      saml_providers: [{ id: "okta-1", name: "Okta", enabled: true }],
    });
    apiMock.startSAML.mockResolvedValue({ redirect_url: mockRedirectUrl });

    Object.defineProperty(window, "location", {
      writable: true,
      value: { assign: vi.fn() },
    });

    renderLogin();

    const ssoButton = await screen.findByRole("button", { name: /使用 SSO 登录/i });
    await user.click(ssoButton);

    await waitFor(() => {
      expect(apiMock.startSAML).toHaveBeenCalledWith("okta-1");
      expect(window.location.assign).toHaveBeenCalledWith(mockRedirectUrl);
    });
  });
});
