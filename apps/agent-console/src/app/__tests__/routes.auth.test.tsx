import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const authState = vi.hoisted(() => ({
  value: {
    user: null as null | { user_id: string },
    loading: false,
    error: null as string | null,
    reload: vi.fn(async () => null),
  },
}));

vi.mock("../../features/auth/AuthProvider", () => ({
  useAuth: () => authState.value,
}));

import { RequireAuth } from "../routes";

function renderProtected(path = "/settings/secrets") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<div>登录页</div>} />
        <Route
          path="*"
          element={
            <RequireAuth>
              <div>受保护页面</div>
            </RequireAuth>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  authState.value = {
    user: null,
    loading: false,
    error: null,
    reload: vi.fn(async () => null),
  };
});

describe("RequireAuth", () => {
  it("redirects unauthenticated console routes to login", () => {
    renderProtected("/settings/secrets");

    expect(screen.getByText("登录页")).toBeInTheDocument();
    expect(screen.queryByText("受保护页面")).not.toBeInTheDocument();
  });

  it("renders protected routes when the current user is loaded", () => {
    authState.value = {
      user: { user_id: "user-1" },
      loading: false,
      error: null,
      reload: vi.fn(async () => null),
    };

    renderProtected("/settings/secrets");

    expect(screen.getByText("受保护页面")).toBeInTheDocument();
  });

  it("shows a loading state while auth is unresolved", () => {
    authState.value = {
      user: null,
      loading: true,
      error: null,
      reload: vi.fn(async () => null),
    };

    renderProtected("/runs");

    expect(screen.getByText("正在验证登录状态...")).toBeInTheDocument();
  });

  it("shows an actionable API error when auth validation fails", () => {
    authState.value = {
      user: null,
      loading: false,
      error: "请求超时：API 5 秒内未响应",
      reload: vi.fn(async () => null),
    };

    renderProtected("/agents");

    expect(screen.getByText("API 连接异常")).toBeInTheDocument();
    expect(screen.getByText("无法打开控制台页面")).toBeInTheDocument();
    expect(screen.getByText(/请求超时/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新验证" })).toBeInTheDocument();
    expect(screen.queryByText("登录页")).not.toBeInTheDocument();
  });
});
