import { useEffect } from 'react'
import { useTerminalStore } from '../../../stores/terminalStore'

const TERMINAL_IDS = ['term-1', 'term-2', 'term-3', 'term-4']

export function useTerminalKeyboardNav() {
  const setActiveTerminal = useTerminalStore((state) => state.setActiveTerminal)

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey) {
        const key = event.key
        const terminalIndex = parseInt(key, 10) - 1

        if (!isNaN(terminalIndex) && terminalIndex >= 0 && terminalIndex < TERMINAL_IDS.length) {
          event.preventDefault()
          setActiveTerminal(TERMINAL_IDS[terminalIndex])
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)

    return () => {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [setActiveTerminal])
}
