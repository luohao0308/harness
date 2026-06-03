import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const authState = vi.hoisted(() => ({ role: "engineer" }));

vi.mock("../../../auth/AuthProvider", () => ({
  useAuth: () => ({
    user: { role: authState.role },
  }),
  useOptionalAuth: () => ({
    user: { role: authState.role },
    isUsingDevToken: true,
    currentOrganization: { id: "dev-org", name: "Dev Org", slug: "dev", role: authState.role },
    logoutCurrentUser: vi.fn(),
  }),
}));

import { SecretVaultPage } from "../SecretVaultPage";

const apiBaseUrl = "http://127.0.0.1:8000";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function requestPath(input: RequestInfo | URL) {
  const url = String(input);
  return new URL(url.startsWith("http") ? url : `${apiBaseUrl}${url}`).pathname;
}

function secretsPayload() {
  return {
    items: [
      {
        id: "secret-user",
        organization_id: "dev-org",
        owner_user_id: "dev-engineer",
        scope: "user",
        provider: "deepseek-pro",
        purpose: "model_provider",
        secret_ref: "secret://models/deepseek-pro/api-key",
        status: "active",
        configured: true,
        source: "stored_secret_user",
        created_at: "2026-06-03T00:00:00Z",
        updated_at: "2026-06-03T00:00:00Z",
        last_used_at: null,
      },
      {
        id: "secret-org",
        organization_id: "dev-org",
        owner_user_id: null,
        scope: "org",
        provider: "tavily",
        purpose: "web_research",
        secret_ref: "env://TAVILY_API_KEY",
        status: "active",
        configured: true,
        source: "stored_secret_org",
        created_at: "2026-06-03T00:00:00Z",
        updated_at: "2026-06-03T00:00:00Z",
        last_used_at: null,
      },
    ],
    next_cursor: null,
  };
}

function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/settings/secrets"]}>
      <QueryClientProvider client={queryClient}>
        <SecretVaultPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  authState.role = "engineer";
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("SecretVaultPage", () => {
  it("hides organization write actions for ordinary users and clears one-time values after save", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/api/secrets" && !init?.method) return jsonResponse(secretsPayload());
      if (path === "/api/secrets" && init?.method === "PUT") {
        return jsonResponse({
          ...secretsPayload().items[0],
          id: "saved-user-secret",
          provider: "deepseek-flash",
          secret_ref: null,
        });
      }
      return jsonResponse({ detail: `unexpected ${path}` }, 404);
    });
    const user = userEvent.setup();
    renderPage(fetchMock);

    await screen.findByText("deepseek-pro");
    expect(screen.queryByRole("button", { name: "组织共享" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "导入环境变量" })).not.toBeInTheDocument();

    await user.clear(screen.getByLabelText("Provider"));
    await user.type(screen.getByLabelText("Provider"), "deepseek-flash");
    await user.type(screen.getByLabelText("密钥值"), "sk-user-only");
    await user.click(screen.getByRole("button", { name: /加密保存/ }));

    await waitFor(() => {
      const saveCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input) === "/api/secrets" && init?.method === "PUT",
      );
      expect(saveCall).toBeDefined();
      expect(JSON.parse(String(saveCall?.[1]?.body))).toMatchObject({
        scope: "user",
        provider: "deepseek-flash",
        secret_value: "sk-user-only",
      });
      expect(screen.getByLabelText("密钥值")).toHaveValue("");
    });
  });

  it("shows organization write actions to admins", async () => {
    authState.role = "admin";
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (requestPath(input) === "/api/secrets") return jsonResponse(secretsPayload());
      return jsonResponse({ detail: "unexpected" }, 404);
    });
    renderPage(fetchMock);

    await screen.findByText("deepseek-pro");
    expect(screen.getByRole("button", { name: "组织共享" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "导入环境变量" })).toBeInTheDocument();
  });
});
