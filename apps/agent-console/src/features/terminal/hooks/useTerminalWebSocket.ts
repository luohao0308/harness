import { useEffect, useRef, useCallback } from 'react'
import { TerminalWebSocket, TerminalMessage } from '../services/terminalWebSocket'
import { useTerminalStore } from '../../../stores/terminalStore'
import { createTerminalToken } from '../../tasks/api'
import { isLocalRuntimeProfile } from '../../../lib/local-runtime'
import { resolveTerminalWebSocketBaseUrl } from '../services/terminalUrl'

interface UseTerminalWebSocketOptions {
  terminalId: string
  onData: (data: string) => void
  enabled?: boolean
}

export function useTerminalWebSocket({
  terminalId,
  onData,
  enabled = true,
}: UseTerminalWebSocketOptions) {
  const wsRef = useRef<TerminalWebSocket | null>(null)
  const updateTerminal = useTerminalStore((state) => state.updateTerminal)

  const handleMessage = useCallback(
    (message: TerminalMessage) => {
      if (message.terminalId !== terminalId) {
        return
      }

      switch (message.type) {
        case 'output':
          if (message.data) {
            onData(message.data)
          }
          break

        case 'exit':
          updateTerminal(terminalId, { active: false })
          if (message.exitCode !== undefined) {
            console.log(`Terminal ${terminalId} exited with code ${message.exitCode}`)
          }
          break

        default:
          break
      }
    },
    [terminalId, onData, updateTerminal]
  )

  const handleConnectionChange = useCallback(
    (connected: boolean) => {
      updateTerminal(terminalId, { active: connected })
    },
    [terminalId, updateTerminal]
  )

  useEffect(() => {
    if (!enabled) {
      return
    }

    const baseWsUrl = resolveTerminalWebSocketBaseUrl({
      localRuntime: isLocalRuntimeProfile(),
      pageOrigin: window.location.origin,
      configuredUrl: import.meta.env.VITE_TERMINAL_WS_URL,
    })
    const wsUrl = new URL(baseWsUrl)
    wsUrl.searchParams.set('terminal_id', terminalId)

    wsRef.current = new TerminalWebSocket(
      {
        url: wsUrl.toString(),
        tokenProvider: async (requestedTerminalId) => {
          const response = await createTerminalToken(requestedTerminalId)
          return response.token
        },
      },
      handleMessage,
      handleConnectionChange
    )

    const connectTimer = window.setTimeout(() => {
      wsRef.current?.connect()
    }, 0)

    return () => {
      window.clearTimeout(connectTimer)
      wsRef.current?.disconnect()
      wsRef.current = null
    }
  }, [enabled, handleMessage, handleConnectionChange])

  const sendInput = useCallback(
    (data: string) => {
      wsRef.current?.sendInput(terminalId, data)
    },
    [terminalId]
  )

  const sendResize = useCallback(
    (rows: number, cols: number) => {
      wsRef.current?.sendResize(terminalId, rows, cols)
    },
    [terminalId]
  )

  return {
    sendInput,
    sendResize,
    isConnected: wsRef.current?.isConnected() ?? false,
  }
}
