import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useConsoleStore } from "../../stores/consoleStore";
import { ConsoleShell } from "../ConsoleShell";

const authMock = vi.hoisted(() => ({
  logoutCurrentUser: vi.fn(async () => undefined),
  uploadAvatar: vi.fn(async () => undefined),
  value: {
    user: {
      user_id: "dev-engineer",
      email: "dev-engineer@dev.local",
      name: "Dev User",
      avatar_data_url: null,
      organization_id: "dev-org",
      role: "engineer",
      permissions: [],
      organizations: [
        { id: "dev-org", name: "Dev Org", slug: "dev", role: "engineer" },
      ],
    },
    loading: false,
    error: null,
    isUsingDevToken: true,
    currentOrganization: { id: "dev-org", name: "Dev Org", slug: "dev", role: "engineer" },
    reload: vi.fn(),
    loginWithPassword: vi.fn(),
    registerWithPassword: vi.fn(),
    logoutCurrentUser: vi.fn(async () => undefined),
    uploadAvatar: vi.fn(async () => undefined),
    switchOrganization: vi.fn(),
  },
}));

const avatarUploadMock = vi.hoisted(() => ({
  prepareAvatarUpload: vi.fn(async (file: File) => file),
}));

vi.mock("../../features/auth/AuthProvider", () => ({
  useOptionalAuth: () => authMock.value,
}));

vi.mock("../../features/auth/avatarUpload", () => ({
  prepareAvatarUpload: avatarUploadMock.prepareAvatarUpload,
}));

function resetAuthMock() {
  authMock.logoutCurrentUser.mockClear();
  authMock.uploadAvatar.mockClear();
  avatarUploadMock.prepareAvatarUpload.mockClear();
  avatarUploadMock.prepareAvatarUpload.mockImplementation(async (file: File) => file);
  authMock.value = {
    user: {
      user_id: "dev-engineer",
      email: "dev-engineer@dev.local",
      name: "Dev User",
      avatar_data_url: null,
      organization_id: "dev-org",
      role: "engineer",
      permissions: [],
      organizations: [
        { id: "dev-org", name: "Dev Org", slug: "dev", role: "engineer" },
      ],
    },
    loading: false,
    error: null,
    isUsingDevToken: true,
    currentOrganization: { id: "dev-org", name: "Dev Org", slug: "dev", role: "engineer" },
    reload: vi.fn(),
    loginWithPassword: vi.fn(),
    registerWithPassword: vi.fn(),
    logoutCurrentUser: authMock.logoutCurrentUser,
    uploadAvatar: authMock.uploadAvatar,
    switchOrganization: vi.fn(),
  };
}

function renderShell(path: string, title: string, content: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      new Response(JSON.stringify({ items: [], next_cursor: null }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={queryClient}>
        <ConsoleShell title={title}>
          <div>{content}</div>
        </ConsoleShell>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  resetAuthMock();
  vi.unstubAllGlobals();
});

describe("ConsoleShell", () => {
  it("embeds the workspace route inside the normal console frame", () => {
    useConsoleStore.getState().setLocale("en-US");

    renderShell("/agents/default/workspace", "智能体工作台", "工作台内容");

    expect(screen.getByText("工作台内容")).toBeInTheDocument();
    expect(screen.getByText("控制台")).toBeInTheDocument();
    expect(screen.getByText("智能体工作台")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Language|语言/ })).not.toBeInTheDocument();
    const sidebarToggle = screen.getByLabelText("侧边栏已收起");
    expect(sidebarToggle).toBeInTheDocument();
    expect(sidebarToggle).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByLabelText("搜索")).toBeInTheDocument();
  });

  it("shows the knowledge base navigation item", () => {
    renderShell("/knowledge", "知识库", "知识库内容");

    expect(screen.getByText("知识库内容")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "知识库" })).toHaveAttribute("href", "/knowledge");
  });

  it("shows a dev-token account menu without the formal logout action", async () => {
    const user = userEvent.setup();
    renderShell("/knowledge", "知识库", "知识库内容");

    await user.click(screen.getByRole("button", { name: "账号菜单" }));

    expect(screen.getByText("开发令牌会话")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "使用账号登录" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "退出登录" })).not.toBeInTheDocument();
  });

  it("shows user and organization details plus logout for JWT sessions", async () => {
    authMock.value = {
      ...authMock.value,
      user: {
        ...authMock.value.user,
        user_id: "user-1",
        email: "owner@example.com",
        name: "Owner User",
        avatar_data_url: null,
        organization_id: "org-1",
        role: "owner",
        organizations: [{ id: "org-1", name: "Acme Production", slug: "acme-prod", role: "owner" }],
      },
      isUsingDevToken: false,
      currentOrganization: { id: "org-1", name: "Acme Production", slug: "acme-prod", role: "owner" },
      logoutCurrentUser: authMock.logoutCurrentUser,
      uploadAvatar: authMock.uploadAvatar,
    };
    const user = userEvent.setup();
    renderShell("/settings/secrets", "密钥库", "密钥库内容");

    await user.click(screen.getByRole("button", { name: "账号菜单" }));

    expect(screen.getByText("owner@example.com")).toBeInTheDocument();
    expect(screen.getAllByText("Acme Production").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("owner")).toBeInTheDocument();
    expect(screen.queryByText("开发令牌会话")).not.toBeInTheDocument();

    await user.click(screen.getByRole("menuitem", { name: "退出登录" }));
    await waitFor(() => expect(authMock.logoutCurrentUser).toHaveBeenCalledTimes(1));
  });

  it("uploads an avatar from the account menu for JWT sessions", async () => {
    authMock.value = {
      ...authMock.value,
      user: {
        ...authMock.value.user,
        user_id: "user-1",
        email: "owner@example.com",
        name: "Owner User",
        avatar_data_url: null,
        organization_id: "org-1",
        role: "owner",
        organizations: [{ id: "org-1", name: "Acme Production", slug: "acme-prod", role: "owner" }],
      },
      isUsingDevToken: false,
      currentOrganization: { id: "org-1", name: "Acme Production", slug: "acme-prod", role: "owner" },
      logoutCurrentUser: authMock.logoutCurrentUser,
      uploadAvatar: authMock.uploadAvatar,
    };
    const user = userEvent.setup();
    renderShell("/settings/secrets", "密钥库", "密钥库内容");

    await user.click(screen.getByRole("button", { name: "账号菜单" }));
    const file = new File(["avatar-bytes"], "avatar.png", { type: "image/png" });
    const preparedFile = new File(["prepared-avatar-bytes"], "avatar.jpg", { type: "image/jpeg" });
    avatarUploadMock.prepareAvatarUpload.mockResolvedValueOnce(preparedFile);
    await user.upload(screen.getByLabelText("上传头像文件"), file);

    await waitFor(() => expect(avatarUploadMock.prepareAvatarUpload).toHaveBeenCalledWith(file));
    expect(authMock.uploadAvatar).toHaveBeenCalledWith(preparedFile);
  });
});
