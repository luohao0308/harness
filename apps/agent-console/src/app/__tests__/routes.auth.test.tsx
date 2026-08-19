import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
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

import {
  LegacyModelSetupRedirect,
  LegacyPathRedirect,
  LegacySpecialistDetailRedirect,
  RequireAuth,
  router,
} from "../routes";

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
  vi.unstubAllEnvs();
  authState.value = {
    user: null,
    loading: false,
    error: null,
    reload: vi.fn(async () => null),
  };
});

describe("RequireAuth", () => {
  it("registers the desktop change review route", () => {
    const rootRoute = router.routes.find((route) => route.path === "/");
    expect(rootRoute?.children?.some((route) => route.path === "changes")).toBe(true);
  });

  it("redirects unauthenticated console routes to login", () => {
    renderProtected("/settings/secrets");

    expect(screen.getByText("登录页")).toBeInTheDocument();
    expect(screen.queryByText("受保护页面")).not.toBeInTheDocument();
  });

  it("does not expose enterprise login for a missing local cookie session", () => {
    vi.stubEnv("VITE_RUNTIME_PROFILE", "local");
    renderProtected("/agents/default/workspace");

    expect(screen.getByText("Local session unavailable")).toBeInTheDocument();
    expect(screen.queryByText("登录页")).not.toBeInTheDocument();
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

  it("keeps the local workspace open without a global model setup gate", () => {
    vi.stubEnv("VITE_RUNTIME_PROFILE", "local");
    authState.value = {
      user: { user_id: "local-user" },
      loading: false,
      error: null,
      reload: vi.fn(async () => null),
    };

    renderProtected("/agents/default/workspace");

    expect(screen.getByText("受保护页面")).toBeInTheDocument();
    expect(screen.queryByText("正在检查模型配置...")).not.toBeInTheDocument();
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

describe("LegacyModelSetupRedirect", () => {
  it("keeps old setup links compatible with the desktop model category", () => {
    render(
      <MemoryRouter initialEntries={["/setup/model"]}>
        <Routes>
          <Route path="/setup/model" element={<LegacyModelSetupRedirect />} />
          <Route path="/desktop" element={<div>桌面模型设置</div>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("桌面模型设置")).toBeInTheDocument();
  });

  it("normalizes old data-management links and preserves location state", () => {
    render(
      <MemoryRouter initialEntries={["/settings/data?scope=org#retention"]}>
        <Routes>
          <Route path="/settings/data" element={<LegacyPathRedirect to="/settings/data-management" />} />
          <Route path="/settings/data-management" element={<RouteLocation />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("/settings/data-management?scope=org#retention")).toBeInTheDocument();
  });

  it("normalizes old specialist detail links without treating specialists as a subagent ID", () => {
    render(
      <MemoryRouter initialEntries={["/subagents/specialists/spec reviewer?window=30d#history"]}>
        <Routes>
          <Route path="/subagents/specialists/:specialistId" element={<LegacySpecialistDetailRedirect />} />
          <Route path="/subagent-specialists/:specialistId" element={<RouteLocation />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("/subagent-specialists/spec%20reviewer?window=30d#history")).toBeInTheDocument();
  });
});

function RouteLocation() {
  const location = useLocation();
  return <div>{`${location.pathname}${location.search}${location.hash}`}</div>;
}
