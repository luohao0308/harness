import { describe, expect, it } from "vitest";

import { resolveTerminalWebSocketBaseUrl } from "../terminalUrl";

describe("resolveTerminalWebSocketBaseUrl", () => {
  it("keeps the signed local runtime origin and random HTTP port", () => {
    expect(
      resolveTerminalWebSocketBaseUrl({
        localRuntime: true,
        pageOrigin: "http://127.0.0.1:49152",
        configuredUrl: "ws://localhost:8000/ws/terminal",
      }),
    ).toBe("ws://127.0.0.1:49152/ws/terminal");
  });

  it("uses wss for an HTTPS runtime origin", () => {
    expect(
      resolveTerminalWebSocketBaseUrl({
        localRuntime: true,
        pageOrigin: "https://127.0.0.1:49153",
      }),
    ).toBe("wss://127.0.0.1:49153/ws/terminal");
  });

  it("preserves the configured enterprise endpoint", () => {
    expect(
      resolveTerminalWebSocketBaseUrl({
        localRuntime: false,
        pageOrigin: "https://console.example.com",
        configuredUrl: "wss://terminal.example.com/ws/terminal",
      }),
    ).toBe("wss://terminal.example.com/ws/terminal");
  });
});
