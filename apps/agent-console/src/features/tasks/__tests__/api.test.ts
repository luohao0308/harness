import { afterEach, describe, expect, it, vi } from "vitest";

import {
  AUTH_SESSION_EXPIRED_EVENT,
  clearAuthTokens,
  createAgentKnowledgeSource,
  deleteAgentKnowledgeSource,
  getAuthBearerToken,
  getStoredAccessToken,
  getStoredRefreshToken,
  importAgentKnowledgeSourceFile,
  resolveApiBaseUrl,
  saveStoredSecret,
  setAuthTokens,
  uploadCurrentUserAvatar,
} from "../api";

function stubBrowserStorage() {
  const store = new Map<string, string>();
  const dispatchEvent = vi.fn(() => true);
  vi.stubGlobal("window", {
    localStorage: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => {
        store.set(key, value);
      },
      removeItem: (key: string) => store.delete(key),
    },
    location: { hostname: "127.0.0.1" },
    dispatchEvent,
  });
  return { dispatchEvent };
}

afterEach(() => {
  clearAuthTokens();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("resolveApiBaseUrl", () => {
  it("defaults to same-origin requests when no API base URL is configured", () => {
    expect(resolveApiBaseUrl(undefined, "127.0.0.1")).toBe("");
  });

  it("uses same-origin requests when configured with a relative API base URL", () => {
    expect(resolveApiBaseUrl("/", "127.0.0.1")).toBe("");
  });

  it("keeps loopback API URLs for loopback console hosts", () => {
    expect(resolveApiBaseUrl("http://127.0.0.1:8000", "127.0.0.1")).toBe("http://127.0.0.1:8000");
    expect(resolveApiBaseUrl("http://127.0.0.1:8000", "localhost")).toBe("http://127.0.0.1:8000");
  });

  it("rewrites loopback API URLs when the console is opened through a LAN host", () => {
    expect(resolveApiBaseUrl("http://127.0.0.1:8000", "192.168.1.23")).toBe("http://192.168.1.23:8000");
  });

  it("preserves explicit non-loopback API URLs", () => {
    expect(resolveApiBaseUrl("http://api.internal:8000", "192.168.1.23")).toBe("http://api.internal:8000");
  });
});

describe("json API requests", () => {
  it("uses the stored JWT before development bearer tokens", async () => {
    stubBrowserStorage();
    setAuthTokens({ access_token: "jwt-access-token", refresh_token: "jwt-refresh-token" });
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          id: "secret-1",
          scope: "org",
          provider: "deepseek",
          purpose: "model_provider",
          configured: true,
          source: "stored_secret_org",
          status: "active",
          created_at: "2026-06-03T00:00:00Z",
          updated_at: "2026-06-03T00:00:00Z",
          last_used_at: null,
          owner_user_id: null,
          secret_ref: null,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    expect(getAuthBearerToken()).toBe("jwt-access-token");
    await saveStoredSecret({
      scope: "org",
      provider: "deepseek",
      purpose: "model_provider",
      secret_value: "sk-test",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/secrets",
      expect.objectContaining({
        method: "PUT",
        headers: expect.objectContaining({ Authorization: "Bearer jwt-access-token" }),
      }),
    );
  });

  it("falls back to the development bearer token only when no JWT is stored", () => {
    clearAuthTokens();
    expect(getAuthBearerToken()).toBe("dev-engineer-token");
  });

  it("clears stored tokens and notifies auth state when refresh fails", async () => {
    const { dispatchEvent } = stubBrowserStorage();
    setAuthTokens({ access_token: "expired-access-token", refresh_token: "expired-refresh-token" });
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/secrets") {
        return new Response(JSON.stringify({ detail: "expired" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (path === "/api/auth/refresh") {
        return new Response(JSON.stringify({ detail: "refresh expired" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify({ detail: `unexpected ${path}` }), { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(saveStoredSecret({
      scope: "org",
      provider: "deepseek",
      purpose: "model_provider",
      secret_value: "sk-test",
    })).rejects.toThrow("请求失败 401");

    expect(getStoredAccessToken()).toBe("");
    expect(getStoredRefreshToken()).toBe("");
    expect(dispatchEvent).toHaveBeenCalledWith(
      expect.objectContaining({ type: AUTH_SESSION_EXPIRED_EVENT }),
    );
  });

  it("refreshes expired JWTs before retrying multipart avatar uploads", async () => {
    stubBrowserStorage();
    setAuthTokens({ access_token: "expired-access-token", refresh_token: "valid-refresh-token" });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const authorization = new Headers(init?.headers).get("authorization");
      if (path === "/api/auth/me/avatar" && authorization === "Bearer expired-access-token") {
        return new Response(JSON.stringify({ detail: "expired" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (path === "/api/auth/refresh") {
        return new Response(
          JSON.stringify({
            access_token: "fresh-access-token",
            refresh_token: "fresh-refresh-token",
            token_type: "bearer",
            expires_in: 3600,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (path === "/api/auth/me/avatar" && authorization === "Bearer fresh-access-token") {
        return new Response(
          JSON.stringify({
            user_id: "user-1",
            email: "owner@example.com",
            name: "Owner",
            avatar_data_url: "data:image/png;base64,YXZhdGFy",
            organization_id: "org-1",
            role: "owner",
            permissions: [],
            organizations: [{ id: "org-1", name: "Acme", slug: "acme", role: "owner" }],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(JSON.stringify({ detail: `unexpected ${path} ${authorization}` }), { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const response = await uploadCurrentUserAvatar(
      new File(["avatar-bytes"], "avatar.png", { type: "image/png" }),
    );

    expect(response.avatar_data_url).toBe("data:image/png;base64,YXZhdGFy");
    expect(getStoredAccessToken()).toBe("fresh-access-token");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("uses the refreshed JWT when retrying multipart uploads with an explicit stored token", async () => {
    stubBrowserStorage();
    setAuthTokens({ access_token: "expired-access-token", refresh_token: "valid-refresh-token" });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const authorization = new Headers(init?.headers).get("authorization");
      if (
        path === "/api/agents/default/knowledge/sources/import" &&
        authorization === "Bearer expired-access-token"
      ) {
        return new Response(JSON.stringify({ detail: "expired" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (path === "/api/auth/refresh") {
        return new Response(
          JSON.stringify({
            access_token: "fresh-access-token",
            refresh_token: "fresh-refresh-token",
            token_type: "bearer",
            expires_in: 3600,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (
        path === "/api/agents/default/knowledge/sources/import" &&
        authorization === "Bearer fresh-access-token"
      ) {
        return new Response(JSON.stringify({ id: "source-1" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify({ detail: `unexpected ${path} ${authorization}` }), { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const response = await importAgentKnowledgeSourceFile(
      "default",
      new File(["knowledge"], "knowledge.md", { type: "text/markdown" }),
      { title: "Knowledge", scope: "org" },
    );

    expect(response.id).toBe("source-1");
    expect(getStoredAccessToken()).toBe("fresh-access-token");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("handles no-content knowledge source deletion responses", async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(deleteAgentKnowledgeSource("default", "source-1")).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/agents/default/knowledge/sources/source-1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("times out stalled knowledge connector creation requests", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
        const signal = init?.signal;
        return new Promise<Response>((_resolve, reject) => {
          signal?.addEventListener(
            "abort",
            () => reject(new DOMException("aborted", "AbortError")),
            { once: true },
          );
        });
      }),
    );

    const createPromise = createAgentKnowledgeSource("default", {
      name: "Dify 知识库",
      description: "Dify API 接入配置",
      scope: "agent",
      source_type: "connector",
      title: "Dify API 连接器",
      content: "连接器配置。",
      uri: "https://api.dify.ai/v1",
      mime_type: "text/markdown",
      connector_settings_json: {
        provider: "dify",
        endpoint: "https://api.dify.ai/v1",
        secret_ref: "secret://dify",
        dataset_id: "dataset-123",
      },
    });

    const assertion = expect(createPromise).rejects.toThrow("请求超时");
    await vi.advanceTimersByTimeAsync(12_000);
    await assertion;
  });
});
