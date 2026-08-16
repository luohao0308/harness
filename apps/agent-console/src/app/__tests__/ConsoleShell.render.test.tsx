import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

beforeEach(() => {
  delete window.desktopApi;
});

afterEach(() => {
  delete window.desktopApi;
  resetAuthMock();
  useConsoleStore.setState({
    environment: "production",
    locale: "zh-CN",
    sidebarNavScrollTop: 0,
  });
  vi.unstubAllGlobals();
});

describe("ConsoleShell", () => {
  it("keeps the browser workspace inside the normal console frame", () => {
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
    expect(screen.queryByRole("button", { name: "打开快捷操作" })).not.toBeInTheDocument();
  });

  it("uses a chrome-free task shell for the desktop workspace", () => {
    window.desktopApi = {};

    renderShell("/agents/default/workspace", "智能体工作台", "工作台内容");

    expect(screen.getByTestId("desktop-workspace-shell")).toBeInTheDocument();
    expect(screen.getByText("工作台内容")).toBeInTheDocument();
    expect(screen.queryByText("控制台")).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "控制台导航" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("搜索")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "账号菜单" })).not.toBeInTheDocument();
  });

  it.each([
    ["/teams/team-1", "团队"],
    ["/runs/run-1", "审批"],
    ["/terminal", "终端"],
    ["/desktop", "设置"],
  ])("uses the compact desktop operation shell for %s", (path, activeLabel) => {
    window.desktopApi = {};

    renderShell(path, "桌面操作", "操作内容");

    expect(screen.getByTestId("desktop-operation-shell")).toBeInTheDocument();
    expect(screen.getByTestId("desktop-operation-rail")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: activeLabel })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "文件" })).toHaveAttribute(
      "href",
      "/agents/default/workspace?desktop_panel=files",
    );
    expect(screen.getByRole("link", { name: "审批" })).toHaveAttribute(
      "href",
      "/agents/default/workspace?desktop_panel=approvals",
    );
    expect(screen.queryByRole("navigation", { name: "控制台导航" })).not.toBeInTheDocument();
    expect(screen.queryByText("控制台")).not.toBeInTheDocument();
  });

  it("keeps browser Team routes inside the normal console frame", () => {
    renderShell("/teams/team-1", "团队", "团队内容");

    expect(screen.getByRole("navigation", { name: "控制台导航" })).toBeInTheDocument();
    expect(screen.queryByTestId("desktop-operation-shell")).not.toBeInTheDocument();
  });

  it("shows the knowledge base navigation item", () => {
    renderShell("/knowledge", "知识库", "知识库内容");

    expect(screen.getByText("知识库内容")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "知识库" })).toHaveAttribute("href", "/knowledge");
    expect(screen.getByRole("button", { name: "打开快捷操作" })).toBeInTheDocument();
  });

  it("groups secondary navigation without removing primary routes", async () => {
    const user = userEvent.setup();
    renderShell("/tools", "工具市场", "工具内容");

    expect(screen.getByRole("navigation", { name: "控制台导航" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "智能体" })).toHaveAttribute("href", "/agents");
    expect(screen.getByRole("link", { name: "团队" })).toHaveAttribute("href", "/teams");
    expect(screen.getByRole("link", { name: "知识库" })).toHaveAttribute("href", "/knowledge");

    const agentMarketplace = screen.getByRole("button", { name: /专家与子代理/ });
    expect(agentMarketplace).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link", { name: "子代理" })).not.toBeInTheDocument();
    await user.click(agentMarketplace);
    expect(agentMarketplace).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: "子代理" })).toHaveAttribute("href", "/subagents");
    expect(screen.getByRole("link", { name: "专家库" })).toHaveAttribute("href", "/subagent-specialists");
    expect(screen.getByRole("link", { name: "专家市场" })).toHaveAttribute("href", "/subagent-marketplace");

    const toolsGroup = screen.getByRole("button", { name: /工具与能力/ });
    expect(toolsGroup).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: "工具市场" })).toHaveAttribute("href", "/tools");
    expect(screen.getByRole("link", { name: "工具配置" })).toHaveAttribute("href", "/tools/config");
    expect(screen.getByRole("link", { name: "沙箱" })).toHaveAttribute("href", "/sandboxes");
  });

  it("keeps collapsed team navigation links at the 44px touch target width", () => {
    renderShell("/teams/team-enterprise", "团队", "团队内容");

    const nav = screen.getByRole("navigation", { name: "控制台导航" });
    expect(nav).toHaveClass("px-0");
    expect(screen.getByRole("link", { name: "智能体" })).toHaveClass("w-full");
    expect(screen.queryByRole("button", { name: "打开快捷操作" })).not.toBeInTheDocument();
  });

  it("restores sidebar scroll after route-owned shell remounts", async () => {
    const first = renderShell("/knowledge", "知识库", "知识库内容");
    const firstNav = screen.getByRole("navigation", { name: "控制台导航" });
    firstNav.scrollTop = 420;
    fireEvent.scroll(firstNav);
    expect(useConsoleStore.getState().sidebarNavScrollTop).toBe(420);

    first.unmount();
    renderShell("/tools", "工具市场", "工具内容");

    const secondNav = screen.getByRole("navigation", { name: "控制台导航" });
    await waitFor(() => expect(secondNav.scrollTop).toBe(420));
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

  it("supports keyboard navigation inside the account menu", async () => {
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

    const accountButton = screen.getByRole("button", { name: "账号菜单" });
    accountButton.focus();
    await user.keyboard("{ArrowDown}");

    const uploadAvatar = await screen.findByRole("menuitem", { name: "上传头像" });
    await waitFor(() => expect(uploadAvatar).toHaveFocus());
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("menuitem", { name: "退出登录" })).toHaveFocus();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("menu", { name: "账号菜单" })).not.toBeInTheDocument());
    expect(accountButton).toHaveFocus();
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
