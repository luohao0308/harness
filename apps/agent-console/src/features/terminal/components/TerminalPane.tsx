import { useRef, useCallback } from 'react'
import { useTerminalStore } from '../../../stores/terminalStore'
import { XtermTerminal, type XtermTerminalRef } from './XtermTerminal'
import { useTerminalWebSocket } from '../hooks/useTerminalWebSocket'

interface TerminalPaneProps {
  id: string
}

export function TerminalPane({ id }: TerminalPaneProps) {
  const terminal = useTerminalStore((state) => state.terminals[id])
  const activeTerminalId = useTerminalStore((state) => state.activeTerminalId)
  const setActiveTerminal = useTerminalStore((state) => state.setActiveTerminal)
  const xtermRef = useRef<XtermTerminalRef>(null)

  const isActive = activeTerminalId === id

  const handleTerminalOutput = useCallback((data: string) => {
    xtermRef.current?.write(data)
  }, [])

  const { sendInput } = useTerminalWebSocket({
    terminalId: id,
    onData: handleTerminalOutput,
    enabled: true,
  })

  const handleUserInput = useCallback((data: string) => {
    sendInput(data)
  }, [sendInput])

  return (
    <div
      className={`h-full w-full border ${isActive ? 'border-[#3C5A78]' : 'border-[#E7E3DA]'} rounded-lg overflow-hidden bg-white`}
      onClick={() => setActiveTerminal(id)}
    >
      <div className="h-8 bg-[#F7F5F1] border-b border-[#E7E3DA] flex items-center px-3">
        <span className="text-sm text-[#6B7077]">{terminal?.title || `Terminal ${id}`}</span>
      </div>
      <div className="h-[calc(100%-2rem)]">
        <XtermTerminal ref={xtermRef} id={id} onData={handleUserInput} />
      </div>
    </div>
  )
}
