/**
 * WebSocket service for terminal shell I/O
 * Connects xterm.js frontend to backend shell processes
 */

export interface TerminalWebSocketConfig {
  url: string
  tokenProvider?: (terminalId: string) => Promise<string>
  reconnectDelay?: number
  maxReconnectAttempts?: number
}

export interface TerminalMessage {
  type: 'input' | 'output' | 'resize' | 'exit'
  terminalId: string
  data?: string
  rows?: number
  cols?: number
  exitCode?: number
}

export class TerminalWebSocket {
  private ws: WebSocket | null = null
  private reconnectAttempts = 0
  private reconnectTimer: NodeJS.Timeout | null = null
  private messageQueue: TerminalMessage[] = []
  private connecting = false
  private manuallyDisconnected = false

  constructor(
    private config: TerminalWebSocketConfig,
    private onMessage: (message: TerminalMessage) => void,
    private onConnectionChange: (connected: boolean) => void
  ) {
    this.config.reconnectDelay = config.reconnectDelay ?? 1000
    this.config.maxReconnectAttempts = config.maxReconnectAttempts ?? 5
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN || this.connecting) {
      return
    }

    this.manuallyDisconnected = false
    void this.openWebSocket()
  }

  private async openWebSocket(): Promise<void> {
    this.connecting = true
    try {
      const url = await this.resolveConnectionUrl()
      if (this.manuallyDisconnected) {
        this.connecting = false
        return
      }
      this.ws = new WebSocket(url)

      this.ws.onopen = () => {
        this.connecting = false
        this.reconnectAttempts = 0
        this.onConnectionChange(true)
        this.flushMessageQueue()
      }

      this.ws.onmessage = (event) => {
        try {
          const message: TerminalMessage = JSON.parse(event.data)
          this.onMessage(message)
        } catch (error) {
          console.error('Failed to parse terminal message:', error)
        }
      }

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error)
      }

      this.ws.onclose = () => {
        this.connecting = false
        this.onConnectionChange(false)
        if (!this.manuallyDisconnected) {
          this.attemptReconnect()
        }
      }
    } catch (error) {
      this.connecting = false
      console.error('Failed to create WebSocket:', error)
      if (!this.manuallyDisconnected) {
        this.attemptReconnect()
      }
    }
  }

  disconnect(): void {
    this.manuallyDisconnected = true
    this.connecting = false
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }

    if (this.ws) {
      this.ws.close()
      this.ws = null
    }

    this.messageQueue = []
  }

  send(message: TerminalMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message))
    } else {
      this.messageQueue.push(message)
      if (!this.ws || this.ws.readyState === WebSocket.CLOSED) {
        this.connect()
      }
    }
  }

  sendInput(terminalId: string, data: string): void {
    this.send({
      type: 'input',
      terminalId,
      data,
    })
  }

  sendResize(terminalId: string, rows: number, cols: number): void {
    this.send({
      type: 'resize',
      terminalId,
      rows,
      cols,
    })
  }

  private attemptReconnect(): void {
    if (
      this.reconnectAttempts >= (this.config.maxReconnectAttempts ?? 5) ||
      this.reconnectTimer
    ) {
      return
    }

    this.reconnectAttempts++
    const delay = (this.config.reconnectDelay ?? 1000) * this.reconnectAttempts

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.connect()
    }, delay)
  }

  private async resolveConnectionUrl(): Promise<string> {
    const url = new URL(this.config.url)
    const terminalId = url.searchParams.get('terminal_id') || 'terminal'
    if (this.config.tokenProvider) {
      const token = await this.config.tokenProvider(terminalId)
      url.searchParams.set('terminal_token', token)
    }
    return url.toString()
  }

  private flushMessageQueue(): void {
    while (this.messageQueue.length > 0 && this.ws?.readyState === WebSocket.OPEN) {
      const message = this.messageQueue.shift()
      if (message) {
        this.ws.send(JSON.stringify(message))
      }
    }
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }
}
