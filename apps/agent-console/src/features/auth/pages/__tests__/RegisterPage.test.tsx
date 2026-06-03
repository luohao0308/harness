import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const authMock = vi.hoisted(() => ({
  registerWithPassword: vi.fn(async () => ({
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
  })),
}));

vi.mock("../../AuthProvider", () => ({
  useAuth: () => ({
    registerWithPassword: authMock.registerWithPassword,
  }),
}));

vi.mock("../../../tasks/api", () => ({
  getAuthConfig: apiMock.getAuthConfig,
}));

import { RegisterPage } from "../RegisterPage";

function renderRegister() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/register"]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/" element={<div>控制台首页</div>} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  authMock.registerWithPassword.mockClear();
  apiMock.getAuthConfig.mockReset();
  apiMock.getAuthConfig.mockResolvedValue({
    public_registration_enabled: false,
    oauth_providers: [],
  });
});

describe("RegisterPage", () => {
  it("shows a closed-registration state and does not render the registration form", async () => {
    renderRegister();

    expect(await screen.findByText("注册已关闭")).toBeInTheDocument();
    expect(screen.getByText(/管理员邀请流程/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "创建并登录" })).not.toBeInTheDocument();
  });

  it("allows account creation only when public registration is enabled", async () => {
    apiMock.getAuthConfig.mockResolvedValue({
      public_registration_enabled: true,
      oauth_providers: [],
    });
    const user = userEvent.setup();
    renderRegister();

    await user.type(await screen.findByLabelText("姓名"), "Owner User");
    await user.type(screen.getByLabelText("邮箱"), "owner@example.com");
    await user.type(screen.getByLabelText("工作区名称"), "Acme Production");
    await user.type(screen.getByLabelText("密码"), "correct-password");
    await user.click(screen.getByRole("button", { name: "创建并登录" }));

    await screen.findByText("控制台首页");
    expect(authMock.registerWithPassword).toHaveBeenCalledWith({
      email: "owner@example.com",
      password: "correct-password",
      name: "Owner User",
      organization_name: "Acme Production",
    });
  });
});
