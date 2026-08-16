import { useRef, useCallback } from 'react'
import { useTerminalStore } from '../../../stores/terminalStore'
import { XtermTerminal, type XtermTerminalRef } from './XtermTerminal'
import { useTerminalWebSocket } from '../hooks/useTerminalWebSocket'
import { cn } from '../../../lib/utils'

interface TerminalPaneProps {
  id: string
  appearance?: 'panel' | 'integrated'
}

export function TerminalPane({ id, appearance = 'panel' }: TerminalPaneProps) {
  const terminal = useTerminalStore((state) => state.terminals[id])
  const activeTerminalId = useTerminalStore((state) => state.activeTerminalId)
  const setActiveTerminal = useTerminalStore((state) => state.setActiveTerminal)
  const xtermRef = useRef<XtermTerminalRef>(null)

  const isActive = activeTerminalId === id
  const isIntegrated = appearance === 'integrated'

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
      data-appearance={appearance}
      className={cn(
        'h-full w-full overflow-hidden border bg-white transition-[border-color,box-shadow]',
        isIntegrated
          ? 'rounded-md border-slate-200/80 shadow-[0_1px_2px_rgba(15,23,42,0.03)]'
          : 'rounded-lg border-[#E7E3DA]',
        isActive &&
          (isIntegrated
            ? 'border-slate-300 shadow-[0_0_0_1px_rgba(148,163,184,0.12),0_1px_2px_rgba(15,23,42,0.03)]'
            : 'border-[#3C5A78]'),
      )}
      onClick={() => setActiveTerminal(id)}
    >
      <div
        className={cn(
          'flex h-9 items-center border-b px-3.5',
          isIntegrated ? 'border-slate-100 bg-[#fafafa]' : 'border-[#E7E3DA] bg-[#F7F5F1]',
        )}
      >
        <span className="text-xs font-medium text-slate-500">{terminal?.title || `Terminal ${id}`}</span>
      </div>
      <div className="h-[calc(100%-2.25rem)] bg-[#fbfbfc]">
        <XtermTerminal ref={xtermRef} id={id} onData={handleUserInput} className="box-border p-3" />
      </div>
    </div>
  )
}
