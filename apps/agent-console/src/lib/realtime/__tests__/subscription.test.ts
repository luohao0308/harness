import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as clientModule from "../client";
import { useRealtimeSubscription } from "../subscription";

// Mock the client module
vi.mock("../client", () => {
  const createMockClient = () => ({
    close: vi.fn(),
    retryNow: vi.fn(),
  });

  return {
    createReconnectingRealtimeClient: vi.fn((urlFactory, options) => {
      const mockClient = createMockClient();
      // Simulate initial connection
      setTimeout(() => options.onStatus?.("connecting"), 0);
      return mockClient;
    }),
  };
});

describe("useRealtimeSubscription", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("creates client with urlFactory and options", () => {
    const urlFactory = vi.fn(() => "/stream");
    const parse = vi.fn((data: string) => JSON.parse(data));
    const onMessage = vi.fn();

    renderHook(() =>
      useRealtimeSubscription(urlFactory, {
        parse,
        onMessage,
      })
    );

    expect(clientModule.createReconnectingRealtimeClient).toHaveBeenCalledWith(
      urlFactory,
      expect.objectContaining({
        parse: expect.any(Function),
        onMessage: expect.any(Function),
        onStatus: expect.any(Function),
      })
    );
  });

  it("returns closed status when urlFactory is null", () => {
    const { result } = renderHook(() =>
      useRealtimeSubscription(null, {
        parse: (data: string) => JSON.parse(data),
        onMessage: vi.fn(),
      })
    );

    expect(result.current.status).toBe("closed");
    expect(result.current.connected).toBe(false);
  });

  it("updates status when client status changes", async () => {
    let capturedOnStatus: ((status: clientModule.RealtimeConnectionStatus) => void) | null = null;
    vi.mocked(clientModule.createReconnectingRealtimeClient).mockImplementation((urlFactory, options) => {
      capturedOnStatus = options.onStatus ?? null;
      return { close: vi.fn(), retryNow: vi.fn() };
    });

    const { result } = renderHook(() =>
      useRealtimeSubscription(() => "/stream", {
        parse: (data: string) => JSON.parse(data),
        onMessage: vi.fn(),
      })
    );

    // Initial status should be closed before any status updates
    expect(result.current.status).toBe("closed");

    // Trigger status change to connecting
    capturedOnStatus!("connecting");

    await waitFor(() => {
      expect(result.current.status).toBe("connecting");
    });

    // Trigger status change to open
    capturedOnStatus!("open");

    await waitFor(() => {
      expect(result.current.status).toBe("open");
      expect(result.current.connected).toBe(true);
    });
  });

  it("calls user onStatus callback when provided", async () => {
    let capturedOnStatus: ((status: clientModule.RealtimeConnectionStatus) => void) | null = null;
    vi.mocked(clientModule.createReconnectingRealtimeClient).mockImplementation((urlFactory, options) => {
      capturedOnStatus = options.onStatus ?? null;
      return { close: vi.fn(), retryNow: vi.fn() };
    });

    const userOnStatus = vi.fn();

    renderHook(() =>
      useRealtimeSubscription(() => "/stream", {
        parse: (data: string) => JSON.parse(data),
        onMessage: vi.fn(),
        onStatus: userOnStatus,
      })
    );

    capturedOnStatus!("open");

    await waitFor(() => {
      expect(userOnStatus).toHaveBeenCalledWith("open");
    });
  });

  it("closes client on unmount", () => {
    const mockClose = vi.fn();
    vi.mocked(clientModule.createReconnectingRealtimeClient).mockReturnValue({
      close: mockClose,
      retryNow: vi.fn(),
    });

    const { unmount } = renderHook(() =>
      useRealtimeSubscription(() => "/stream", {
        parse: (data: string) => JSON.parse(data),
        onMessage: vi.fn(),
      })
    );

    unmount();

    expect(mockClose).toHaveBeenCalled();
  });

  it("closes old client when urlFactory changes", async () => {
    const mockClose1 = vi.fn();
    const mockClose2 = vi.fn();

    vi.mocked(clientModule.createReconnectingRealtimeClient)
      .mockReturnValueOnce({ close: mockClose1, retryNow: vi.fn() })
      .mockReturnValueOnce({ close: mockClose2, retryNow: vi.fn() });

    const { rerender } = renderHook(
      ({ url }) =>
        useRealtimeSubscription(
          () => url,
          {
            parse: (data: string) => JSON.parse(data),
            onMessage: vi.fn(),
          }
        ),
      { initialProps: { url: "/stream1" } }
    );

    expect(clientModule.createReconnectingRealtimeClient).toHaveBeenCalledTimes(1);

    rerender({ url: "/stream2" });

    await waitFor(() => {
      expect(mockClose1).toHaveBeenCalled();
      expect(clientModule.createReconnectingRealtimeClient).toHaveBeenCalledTimes(2);
    });
  });

  it("uses stable callback references via ref", async () => {
    let capturedParse: ((data: string) => unknown) | null = null;
    let capturedOnMessage: ((event: unknown, raw: MessageEvent<string>) => void) | null = null;
    let clientCallCount = 0;

    vi.mocked(clientModule.createReconnectingRealtimeClient).mockImplementation((urlFactory, options) => {
      // Only capture on first call
      if (clientCallCount === 0) {
        capturedParse = options.parse;
        capturedOnMessage = options.onMessage;
      }
      clientCallCount++;
      return { close: vi.fn(), retryNow: vi.fn() };
    });

    const parse = vi.fn((data: string) => JSON.parse(data));
    const onMessage1 = vi.fn();
    const urlFactory = () => "/stream";

    // Pass stable maxRetryDelayMs and maxAttemptsBeforeNotice values
    const { rerender } = renderHook(
      ({ onMessage }) =>
        useRealtimeSubscription(urlFactory, {
          parse,
          onMessage,
          maxRetryDelayMs: 30_000,
          maxAttemptsBeforeNotice: 5,
        }),
      { initialProps: { onMessage: onMessage1 } }
    );

    const firstParse = capturedParse;
    const firstOnMessage = capturedOnMessage;

    const onMessage2 = vi.fn();
    rerender({ onMessage: onMessage2 });

    // Verify client was only created once (no recreation on rerender)
    await waitFor(() => {
      expect(clientCallCount).toBe(1);
    });

    // Verify callback references are stable (same wrapper functions)
    expect(capturedParse).toBe(firstParse);
    expect(capturedOnMessage).toBe(firstOnMessage);

    // Verify the ref was updated and calls the new callback
    const rawEvent = {} as MessageEvent<string>;
    capturedOnMessage!(JSON.parse('{"test": true}'), rawEvent);
    expect(onMessage2).toHaveBeenCalledWith({ test: true }, rawEvent);
    expect(onMessage1).not.toHaveBeenCalled();
  });

  it("recreates client when maxRetryDelayMs changes", async () => {
    const mockClose1 = vi.fn();
    const mockClose2 = vi.fn();

    vi.mocked(clientModule.createReconnectingRealtimeClient)
      .mockReturnValueOnce({ close: mockClose1, retryNow: vi.fn() })
      .mockReturnValueOnce({ close: mockClose2, retryNow: vi.fn() });

    const { rerender } = renderHook(
      ({ maxRetryDelayMs }) =>
        useRealtimeSubscription(() => "/stream", {
          parse: (data: string) => JSON.parse(data),
          onMessage: vi.fn(),
          maxRetryDelayMs,
        }),
      { initialProps: { maxRetryDelayMs: 30_000 } }
    );

    expect(clientModule.createReconnectingRealtimeClient).toHaveBeenCalledTimes(1);

    rerender({ maxRetryDelayMs: 60_000 });

    await waitFor(() => {
      expect(mockClose1).toHaveBeenCalled();
      expect(clientModule.createReconnectingRealtimeClient).toHaveBeenCalledTimes(2);
    });
  });

  it("recreates client when maxAttemptsBeforeNotice changes", async () => {
    const mockClose1 = vi.fn();
    const mockClose2 = vi.fn();

    vi.mocked(clientModule.createReconnectingRealtimeClient)
      .mockReturnValueOnce({ close: mockClose1, retryNow: vi.fn() })
      .mockReturnValueOnce({ close: mockClose2, retryNow: vi.fn() });

    const { rerender } = renderHook(
      ({ maxAttemptsBeforeNotice }) =>
        useRealtimeSubscription(() => "/stream", {
          parse: (data: string) => JSON.parse(data),
          onMessage: vi.fn(),
          maxAttemptsBeforeNotice,
        }),
      { initialProps: { maxAttemptsBeforeNotice: 5 } }
    );

    expect(clientModule.createReconnectingRealtimeClient).toHaveBeenCalledTimes(1);

    rerender({ maxAttemptsBeforeNotice: 10 });

    await waitFor(() => {
      expect(mockClose1).toHaveBeenCalled();
      expect(clientModule.createReconnectingRealtimeClient).toHaveBeenCalledTimes(2);
    });
  });

  it("handles transition from null to valid urlFactory", async () => {
    const { result, rerender } = renderHook(
      ({ urlFactory }) =>
        useRealtimeSubscription(urlFactory, {
          parse: (data: string) => JSON.parse(data),
          onMessage: vi.fn(),
        }),
      { initialProps: { urlFactory: null as (() => string) | null } }
    );

    expect(result.current.status).toBe("closed");
    expect(clientModule.createReconnectingRealtimeClient).not.toHaveBeenCalled();

    rerender({ urlFactory: () => "/stream" });

    await waitFor(() => {
      expect(clientModule.createReconnectingRealtimeClient).toHaveBeenCalled();
    });
  });

  it("handles transition from valid urlFactory to null", async () => {
    const mockClose = vi.fn();
    vi.mocked(clientModule.createReconnectingRealtimeClient).mockReturnValue({
      close: mockClose,
      retryNow: vi.fn(),
    });

    const { result, rerender } = renderHook(
      ({ urlFactory }) =>
        useRealtimeSubscription(urlFactory, {
          parse: (data: string) => JSON.parse(data),
          onMessage: vi.fn(),
        }),
      { initialProps: { urlFactory: (() => "/stream") as (() => string) | null } }
    );

    expect(clientModule.createReconnectingRealtimeClient).toHaveBeenCalled();

    rerender({ urlFactory: null });

    await waitFor(() => {
      expect(mockClose).toHaveBeenCalled();
      expect(result.current.status).toBe("closed");
    });
  });
});
