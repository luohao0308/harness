import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createAgentKnowledgeSource,
  deleteAgentKnowledgeSource,
  resolveApiBaseUrl,
} from "../api";

afterEach(() => {
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
