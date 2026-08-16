import { afterEach, describe, expect, it, vi } from 'vitest'

import { TerminalWebSocket } from '../terminalWebSocket'

class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3
  static instances: MockWebSocket[] = []

  readyState = MockWebSocket.CONNECTING
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: ((event: unknown) => void) | null = null
  onclose: (() => void) | null = null
  sent: string[] = []

  constructor(public url: string) {
    MockWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.()
  }

  open() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.()
  }

  serverClose() {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.()
  }
}

function flushPromises() {
  return Promise.resolve()
}

describe('TerminalWebSocket', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    MockWebSocket.instances = []
  })

  it('adds a one-time terminal token before connecting', async () => {
    vi.stubGlobal('WebSocket', MockWebSocket)
    const tokenProvider = vi.fn(async () => 'token-1')
    const socket = new TerminalWebSocket(
      {
        url: 'ws://localhost:8000/ws/terminal?terminal_id=term-1',
        tokenProvider,
      },
      vi.fn(),
      vi.fn()
    )

    socket.connect()
    await flushPromises()
    await flushPromises()

    expect(tokenProvider).toHaveBeenCalledWith('term-1')
    expect(MockWebSocket.instances).toHaveLength(1)
    const url = new URL(MockWebSocket.instances[0].url)
    expect(url.searchParams.get('terminal_id')).toBe('term-1')
    expect(url.searchParams.get('terminal_token')).toBe('token-1')
  })

  it('requests a fresh token when reconnecting', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('WebSocket', MockWebSocket)
    const tokenProvider = vi
      .fn<() => Promise<string>>()
      .mockResolvedValueOnce('token-1')
      .mockResolvedValueOnce('token-2')
    const socket = new TerminalWebSocket(
      {
        url: 'ws://localhost:8000/ws/terminal?terminal_id=term-1',
        reconnectDelay: 10,
        maxReconnectAttempts: 2,
        tokenProvider: async () => tokenProvider(),
      },
      vi.fn(),
      vi.fn()
    )

    socket.connect()
    await vi.runAllTimersAsync()
    await flushPromises()
    await flushPromises()
    MockWebSocket.instances[0].open()
    MockWebSocket.instances[0].serverClose()
    await vi.advanceTimersByTimeAsync(10)
    await flushPromises()
    await flushPromises()

    expect(tokenProvider).toHaveBeenCalledTimes(2)
    expect(MockWebSocket.instances).toHaveLength(2)
    expect(new URL(MockWebSocket.instances[0].url).searchParams.get('terminal_token')).toBe('token-1')
    expect(new URL(MockWebSocket.instances[1].url).searchParams.get('terminal_token')).toBe('token-2')
  })
})
