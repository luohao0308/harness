import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiHttpError } from "../../tasks/api";
import { AuthProvider, useAuth } from "../AuthProvider";

const apiMock = vi.hoisted(() => ({
  getMe: vi.fn(),
}));

vi.mock("../../tasks/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../tasks/api")>()),
  getMe: apiMock.getMe,
  getStoredAccessToken: vi.fn(() => ""),
  isDevAuthFallbackEnabled: vi.fn(() => false),
}));

function AuthProbe() {
  const auth = useAuth();
  if (auth.loading) return <div>loading</div>;
  return <div>{auth.error ?? (auth.user ? "authenticated" : "anonymous")}</div>;
}

function renderProvider() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe("AuthProvider bootstrap", () => {
  beforeEach(() => {
    apiMock.getMe.mockReset();
    delete window.desktopApi;
  });

  it("treats a 401 response as an anonymous login state", async () => {
    apiMock.getMe.mockRejectedValue(new ApiHttpError(401));
    renderProvider();

    expect(await screen.findByText("anonymous")).toBeInTheDocument();
  });

  it("keeps network failures visible as connection errors", async () => {
    apiMock.getMe.mockRejectedValue(new Error("Failed to fetch"));
    renderProvider();

    expect(await screen.findByText("Failed to fetch")).toBeInTheDocument();
  });

  it("retries a transient desktop local-runtime failure before showing an error", async () => {
    window.desktopApi = { localRuntime: {} };
    apiMock.getMe
      .mockRejectedValueOnce(new Error("请求超时：API 5 秒内未响应"))
      .mockResolvedValueOnce({
        user_id: "local-owner",
        email: "local@harness.invalid",
        name: "Local Owner",
        avatar_data_url: null,
        organization_id: "local",
        role: "owner",
        permissions: ["*"],
        organizations: [{ id: "local", name: "Local", slug: "local", role: "owner" }],
      });

    renderProvider();

    expect(await screen.findByText("authenticated")).toBeInTheDocument();
    await waitFor(() => expect(apiMock.getMe).toHaveBeenCalledTimes(2));
    expect(screen.queryByText(/请求超时/)).not.toBeInTheDocument();
  });

  it("stops after the bounded desktop retries and keeps the final error", async () => {
    window.desktopApi = { localRuntime: {} };
    apiMock.getMe.mockRejectedValue(new Error("harnessd still starting"));

    renderProvider();

    expect(await screen.findByText("harnessd still starting", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(apiMock.getMe).toHaveBeenCalledTimes(3);
  });
});
