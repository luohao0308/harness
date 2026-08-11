import { useEffect, useRef, useImperativeHandle, forwardRef } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import { defaultTerminalConfig } from '../lib/terminalConfig'
import '@xterm/xterm/css/xterm.css'

interface XtermTerminalProps {
  id: string
  onData?: (data: string) => void
  className?: string
}

export interface XtermTerminalRef {
  write: (data: string) => void
  clear: () => void
  fit: () => void
}

export const XtermTerminal = forwardRef<XtermTerminalRef, XtermTerminalProps>(
  ({ id, onData, className }, ref) => {
    const terminalRef = useRef<Terminal | null>(null)
    const fitAddonRef = useRef<FitAddon | null>(null)
    const containerRef = useRef<HTMLDivElement>(null)

    useImperativeHandle(ref, () => ({
      write: (data: string) => {
        terminalRef.current?.write(data)
      },
      clear: () => {
        terminalRef.current?.clear()
      },
      fit: () => {
        fitAddonRef.current?.fit()
      },
    }))

    useEffect(() => {
      if (!containerRef.current) return

      const terminal = new Terminal(defaultTerminalConfig)
      const fitAddon = new FitAddon()
      const webLinksAddon = new WebLinksAddon()

      terminal.loadAddon(fitAddon)
      terminal.loadAddon(webLinksAddon)
      terminal.open(containerRef.current)

      fitAddon.fit()

      terminalRef.current = terminal
      fitAddonRef.current = fitAddon

      if (onData) {
        terminal.onData(onData)
      }

      terminal.writeln('Welcome to Terminal')
      terminal.writeln('Type a command to get started')
      terminal.write('$ ')

      return () => {
        terminal.dispose()
      }
    }, [id, onData])

  useEffect(() => {
    const handleResize = () => {
      if (fitAddonRef.current) {
        fitAddonRef.current.fit()
      }
    }

    const resizeObserver = new ResizeObserver(handleResize)
    if (containerRef.current) {
      resizeObserver.observe(containerRef.current)
    }

    return () => {
      resizeObserver.disconnect()
    }
  }, [])

    return <div ref={containerRef} data-testid="xterm-container" className={className} style={{ width: '100%', height: '100%' }} />
  }
)

XtermTerminal.displayName = 'XtermTerminal'
