// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  initializeLocalRuntimeSession,
  isLocalRuntimeProfile,
  isLocalWebExtension,
} from "../local-runtime";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  delete window.desktopApi;
  window.history.replaceState(null, "", "/");
});

describe("local runtime session bootstrap", () => {
  it("is opt-in and distinguishes Desktop from the browser Web Extension", () => {
    vi.stubEnv("VITE_RUNTIME_PROFILE", "local");
    expect(isLocalRuntimeProfile()).toBe(true);
    expect(isLocalWebExtension()).toBe(true);

    window.desktopApi = {};
    expect(isLocalWebExtension()).toBe(false);
  });

  it("clears the one-time token before exchanging it for an HttpOnly cookie", async () => {
    vi.stubEnv("VITE_RUNTIME_PROFILE", "local");
    window.history.replaceState(null, "", "/agents#bootstrap=one-time-secret&panel=runs");
    const fetchMock = vi.fn(async () => {
      expect(window.location.hash).toBe("#panel=runs");
      return new Response(null, { status: 204 });
    });

    await initializeLocalRuntimeSession(fetchMock as typeof fetch);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/local-runtime/web/bootstrap/exchange",
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        body: JSON.stringify({ token: "one-time-secret" }),
      }),
    );
    expect(window.location.hash).toBe("#panel=runs");
  });

  it("does not exchange fragments in enterprise mode", async () => {
    vi.stubEnv("VITE_RUNTIME_PROFILE", "enterprise");
    window.history.replaceState(null, "", "/#bootstrap=enterprise-fragment");
    const fetchMock = vi.fn();

    await initializeLocalRuntimeSession(fetchMock as typeof fetch);

    expect(fetchMock).not.toHaveBeenCalled();
    expect(window.location.hash).toContain("enterprise-fragment");
  });
});
