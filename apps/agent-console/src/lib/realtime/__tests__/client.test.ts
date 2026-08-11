import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  createReconnectingRealtimeClient,
  type RealtimeConnectionStatus,
} from "../client";

describe("createReconnectingRealtimeClient", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  const createMockEventSource = () => {
    const listeners: Record<string, Array<(event: MessageEvent) => void>> = {};
    let openHandler: (() => void) | null = null;
    let errorHandler: (() => void) | null = null;

    const mockEventSource = {
      onopen: null as (() => void) | null,
      onerror: null as (() => void) | null,
      onmessage: null as ((event: MessageEvent) => void) | null,
      addEventListener: vi.fn((type: string, handler: (event: MessageEvent) => void) => {
        if (!listeners[type]) listeners[type] = [];
        listeners[type].push(handler);
      }),
      close: vi.fn(),
      readyState: 1,
      url: "",
      withCredentials: false,
      CONNECTING: 0,
      OPEN: 1,
      CLOSED: 2,
      dispatchEvent: vi.fn(),
      removeEventListener: vi.fn(),
    };

    Object.defineProperty(mockEventSource, "onopen", {
      get: () => openHandler,
      set: (handler) => {
        openHandler = handler;
      },
    });

    Object.defineProperty(mockEventSource, "onerror", {
      get: () => errorHandler,
      set: (handler) => {
        errorHandler = handler;
      },
    });

    const triggerOpen = () => openHandler?.();
    const triggerError = () => errorHandler?.();
    const triggerMessage = (data: string, lastEventId?: string) => {
      const event = new MessageEvent("message", {
        data,
        lastEventId: lastEventId ?? "",
      });
      mockEventSource.onmessage?.(event);
    };

    return { mockEventSource, triggerOpen, triggerError, triggerMessage };
  };

  it("creates EventSource with initial URL", () => {
    const urlFactory = vi.fn((lastEventId: string | null) =>
      lastEventId ? `/stream?last=${lastEventId}` : "/stream"
    );
    const mockES = createMockEventSource();
    vi.stubGlobal("EventSource", vi.fn(() => mockES.mockEventSource));

    createReconnectingRealtimeClient(urlFactory, {
      parse: (data) => JSON.parse(data),
      onMessage: vi.fn(),
    });

    expect(urlFactory).toHaveBeenCalledWith(null);
    expect(EventSource).toHaveBeenCalledWith("/stream");
  });

  it("transitions status from connecting to open", () => {
    const statuses: RealtimeConnectionStatus[] = [];
    const mockES = createMockEventSource();
    vi.stubGlobal("EventSource", vi.fn(() => mockES.mockEventSource));

    createReconnectingRealtimeClient(
      () => "/stream",
      {
        parse: (data) => JSON.parse(data),
        onMessage: vi.fn(),
        onStatus: (status) => statuses.push(status),
      }
    );

    expect(statuses).toEqual(["connecting"]);

    mockES.triggerOpen();
    expect(statuses).toEqual(["connecting", "open"]);
  });

  it("parses and delivers messages", () => {
    const onMessage = vi.fn();
    const mockES = createMockEventSource();
    vi.stubGlobal("EventSource", vi.fn(() => mockES.mockEventSource));

    createReconnectingRealtimeClient(
      () => "/stream",
      {
        parse: (data) => JSON.parse(data),
        onMessage,
      }
    );

    mockES.triggerOpen();
    mockES.triggerMessage(JSON.stringify({ type: "test", value: 42 }));

    expect(onMessage).toHaveBeenCalledWith(
      { type: "test", value: 42 },
      expect.any(MessageEvent)
    );
  });

  it("tracks lastEventId for reconnection", () => {
    const urlFactory = vi.fn((lastEventId: string | null) =>
      lastEventId ? `/stream?last=${lastEventId}` : "/stream"
    );
    const mockES = createMockEventSource();
    vi.stubGlobal("EventSource", vi.fn(() => mockES.mockEventSource));

    createReconnectingRealtimeClient(urlFactory, {
      parse: (data) => JSON.parse(data),
      onMessage: vi.fn(),
    });

    mockES.triggerOpen();
    mockES.triggerMessage(JSON.stringify({ seq: 1 }), "event-123");
    mockES.triggerError();

    vi.advanceTimersByTime(1000);

    expect(urlFactory).toHaveBeenCalledWith("event-123");
  });

  it("uses exponential backoff for reconnection", () => {
    const mockES1 = createMockEventSource();
    const mockES2 = createMockEventSource();
    const mockES3 = createMockEventSource();
    const sources = [mockES1, mockES2, mockES3];
    let callCount = 0;

    vi.stubGlobal(
      "EventSource",
      vi.fn(() => sources[callCount++]?.mockEventSource ?? mockES1.mockEventSource)
    );

    createReconnectingRealtimeClient(
      () => "/stream",
      {
        parse: (data) => JSON.parse(data),
        onMessage: vi.fn(),
        maxRetryDelayMs: 30_000,
      }
    );

    // Initial connection
    expect(EventSource).toHaveBeenCalledTimes(1);

    // First error: 1s delay (2^0 * 1000)
    mockES1.triggerError();
    vi.advanceTimersByTime(999);
    expect(EventSource).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(1);
    expect(EventSource).toHaveBeenCalledTimes(2);

    // Second error: 2s delay (2^1 * 1000)
    mockES2.triggerError();
    vi.advanceTimersByTime(1999);
    expect(EventSource).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(1);
    expect(EventSource).toHaveBeenCalledTimes(3);
  });

  it("caps retry delay at maxRetryDelayMs", () => {
    const sources: ReturnType<typeof createMockEventSource>[] = [];
    let callCount = 0;

    vi.stubGlobal(
      "EventSource",
      vi.fn(() => {
        const mockES = createMockEventSource();
        sources.push(mockES);
        callCount++;
        return mockES.mockEventSource;
      })
    );

    createReconnectingRealtimeClient(
      () => "/stream",
      {
        parse: (data) => JSON.parse(data),
        onMessage: vi.fn(),
        maxRetryDelayMs: 5_000,
      }
    );

    // Simulate many failures to reach max delay
    // After 3 failures: 1s, 2s, 4s → next should be capped at 5s
    sources[0].triggerError();
    vi.advanceTimersByTime(1_000);

    sources[1].triggerError();
    vi.advanceTimersByTime(2_000);

    sources[2].triggerError();
    vi.advanceTimersByTime(4_000);

    // 4th failure: delay should be capped at 5s (not 8s)
    const beforeCount = vi.mocked(EventSource).mock.calls.length;
    sources[3].triggerError();
    vi.advanceTimersByTime(4_999);
    expect(vi.mocked(EventSource).mock.calls.length).toBe(beforeCount);
    vi.advanceTimersByTime(1);
    expect(vi.mocked(EventSource).mock.calls.length).toBe(beforeCount + 1);
  });

  it("transitions to failed status after maxAttemptsBeforeNotice", () => {
    const statuses: RealtimeConnectionStatus[] = [];
    const mockES = createMockEventSource();
    vi.stubGlobal("EventSource", vi.fn(() => mockES.mockEventSource));

    createReconnectingRealtimeClient(
      () => "/stream",
      {
        parse: (data) => JSON.parse(data),
        onMessage: vi.fn(),
        onStatus: (status) => statuses.push(status),
        maxAttemptsBeforeNotice: 3,
      }
    );

    mockES.triggerError(); // Attempt 1
    expect(statuses[statuses.length - 1]).toBe("retrying");

    vi.advanceTimersByTime(1000);
    mockES.triggerError(); // Attempt 2
    expect(statuses[statuses.length - 1]).toBe("retrying");

    vi.advanceTimersByTime(2000);
    mockES.triggerError(); // Attempt 3
    expect(statuses[statuses.length - 1]).toBe("failed");
  });

  it("resets reconnectAttempts on successful connection", () => {
    const statuses: RealtimeConnectionStatus[] = [];
    const mockES1 = createMockEventSource();
    const mockES2 = createMockEventSource();
    const sources = [mockES1, mockES2];
    let callCount = 0;

    vi.stubGlobal(
      "EventSource",
      vi.fn(() => sources[callCount++]?.mockEventSource ?? mockES1.mockEventSource)
    );

    const client = createReconnectingRealtimeClient(
      () => "/stream",
      {
        parse: (data) => JSON.parse(data),
        onMessage: vi.fn(),
        onStatus: (status) => statuses.push(status),
      }
    );

    // Fail once
    mockES1.triggerError();
    vi.advanceTimersByTime(1000);

    // Succeed
    mockES2.triggerOpen();
    expect(statuses[statuses.length - 1]).toBe("open");

    // Fail again - should use 1s delay (attempt 1), not 2s (attempt 2)
    mockES2.triggerError();
    vi.advanceTimersByTime(999);
    expect(vi.mocked(EventSource).mock.calls.length).toBe(2);
    vi.advanceTimersByTime(1);
    expect(vi.mocked(EventSource).mock.calls.length).toBe(3);

    // Clean up
    client.close();
    vi.clearAllTimers();
  });

  it("closes connection and prevents reconnection", () => {
    const sources: ReturnType<typeof createMockEventSource>[] = [];
    let callCount = 0;

    const EventSourceMock = vi.fn(() => {
      const mockES = createMockEventSource();
      sources.push(mockES);
      callCount++;
      return mockES.mockEventSource;
    });

    vi.stubGlobal("EventSource", EventSourceMock);

    const client = createReconnectingRealtimeClient(
      () => "/stream",
      {
        parse: (data) => JSON.parse(data),
        onMessage: vi.fn(),
      }
    );

    sources[0].triggerOpen();

    // Trigger an error BEFORE close to create a pending timer
    sources[0].triggerError();

    // Now close the client BEFORE the timer fires
    client.close();

    // Advance timers - the timer should have been cleared by close()
    vi.advanceTimersByTime(5000);

    // Should still be 1 because close() should have cleared the pending timer
    expect(callCount).toBe(1);
  });

  it("retryNow resets attempts and reconnects immediately", () => {
    const mockES1 = createMockEventSource();
    const mockES2 = createMockEventSource();
    const sources = [mockES1, mockES2];
    let callCount = 0;

    vi.stubGlobal(
      "EventSource",
      vi.fn(() => sources[callCount++]?.mockEventSource ?? mockES1.mockEventSource)
    );

    const client = createReconnectingRealtimeClient(
      () => "/stream",
      {
        parse: (data) => JSON.parse(data),
        onMessage: vi.fn(),
      }
    );

    // Fail once to increment attempts
    mockES1.triggerError();
    vi.advanceTimersByTime(1000);

    // Manual retry
    const beforeCount = vi.mocked(EventSource).mock.calls.length;
    client.retryNow();
    expect(vi.mocked(EventSource).mock.calls.length).toBe(beforeCount + 1);
  });

  it("handles parse errors by setting failed status", () => {
    const statuses: RealtimeConnectionStatus[] = [];
    const mockES = createMockEventSource();
    vi.stubGlobal("EventSource", vi.fn(() => mockES.mockEventSource));

    createReconnectingRealtimeClient(
      () => "/stream",
      {
        parse: (data) => JSON.parse(data),
        onMessage: vi.fn(),
        onStatus: (status) => statuses.push(status),
      }
    );

    mockES.triggerOpen();
    mockES.triggerMessage("invalid json{{");

    expect(statuses[statuses.length - 1]).toBe("failed");
  });
});
