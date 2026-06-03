import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const authState = vi.hoisted(() => ({
  value: {
    user: null as null | { user_id: string },
    loading: false,
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
  authState.value = { user: null, loading: false };
});

describe("RequireAuth", () => {
  it("redirects unauthenticated console routes to login", () => {
    renderProtected("/settings/secrets");

    expect(screen.getByText("登录页")).toBeInTheDocument();
    expect(screen.queryByText("受保护页面")).not.toBeInTheDocument();
  });

  it("renders protected routes when the current user is loaded", () => {
    authState.value = { user: { user_id: "user-1" }, loading: false };

    renderProtected("/settings/secrets");

    expect(screen.getByText("受保护页面")).toBeInTheDocument();
  });

  it("shows a loading state while auth is unresolved", () => {
    authState.value = { user: null, loading: true };

    renderProtected("/runs");

    expect(screen.getByText("正在验证登录状态...")).toBeInTheDocument();
  });
});
