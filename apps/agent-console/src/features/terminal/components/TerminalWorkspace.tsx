import { useEffect } from 'react'
import { Panel, Group, Separator, type Layout } from 'react-resizable-panels'
import { useTerminalStore } from '../../../stores/terminalStore'
import { TerminalPane } from './TerminalPane'
import { useTerminalKeyboardNav } from '../hooks/useTerminalKeyboardNav'
import { ConsoleShell } from '../../../app/ConsoleShell'
import { isDesktopRuntime } from '../../../lib/desktop-bridge'

const WEB_TERMINAL_IDS = ['term-1', 'term-2', 'term-3', 'term-4'] as const
const DESKTOP_TERMINAL_IDS = ['term-1'] as const

export function TerminalWorkspace() {
  const createTerminal = useTerminalStore((state) => state.createTerminal)
  const terminals = useTerminalStore((state) => state.terminals)
  const layout = useTerminalStore((state) => state.layout)
  const setLayout = useTerminalStore((state) => state.setLayout)
  const desktop = isDesktopRuntime()

  useTerminalKeyboardNav()

  useEffect(() => {
    const terminalIds = desktop ? DESKTOP_TERMINAL_IDS : WEB_TERMINAL_IDS
    terminalIds.forEach((id) => {
      if (!terminals[id]) {
        createTerminal(id)
      }
    })
  }, [createTerminal, desktop, terminals])

  const horizontalSizes = layout.sizes.length >= 3 ? layout.sizes : [33.334, 33.333, 33.333]
  const verticalSizes = layout.verticalSizes.length >= 2 ? layout.verticalSizes : [50, 50]

  const handleLayoutChange = (newLayout: Layout) => {
    const sizes = Object.values(newLayout)
    setLayout({
      direction: layout.direction,
      sizes,
      verticalSizes: layout.verticalSizes,
      collapsed: layout.collapsed,
    })
  }

  const handleVerticalLayoutChange = (newLayout: Layout) => {
    const verticalSizes = Object.values(newLayout)
    setLayout({
      direction: layout.direction,
      sizes: layout.sizes,
      verticalSizes,
      collapsed: layout.collapsed,
    })
  }

  if (desktop) {
    return (
      <ConsoleShell title="终端">
        <div aria-label="Terminal workspace" className="h-full min-h-0 w-full bg-slate-50 p-2" role="region">
          <TerminalPane id="term-1" />
        </div>
      </ConsoleShell>
    )
  }

  return (
    <ConsoleShell title="终端">
      <div aria-label="Terminal workspace" className="h-full min-h-0 w-full bg-slate-50 p-2" role="region">
        <Group orientation="horizontal" onLayoutChange={handleLayoutChange}>
        <Panel id="term-1" defaultSize={horizontalSizes[0] || 33} minSize={20}>
          <TerminalPane id="term-1" />
        </Panel>

        <Separator className="w-1 bg-[#E7E3DA] hover:bg-[#3C5A78] transition-colors" />

        <Panel id="term-2-3-group" defaultSize={horizontalSizes[1] || 34} minSize={20}>
          <Group orientation="vertical" onLayoutChange={handleVerticalLayoutChange}>
            <Panel id="term-2" defaultSize={verticalSizes[0] || 50} minSize={20}>
              <TerminalPane id="term-2" />
            </Panel>

            <Separator className="h-1 bg-[#E7E3DA] hover:bg-[#3C5A78] transition-colors" />

            <Panel id="term-3" defaultSize={verticalSizes[1] || 50} minSize={20}>
              <TerminalPane id="term-3" />
            </Panel>
          </Group>
        </Panel>

        <Separator className="w-1 bg-[#E7E3DA] hover:bg-[#3C5A78] transition-colors" />

        <Panel id="term-4" defaultSize={horizontalSizes[2] || 33} minSize={20}>
          <TerminalPane id="term-4" />
        </Panel>
        </Group>
      </div>
    </ConsoleShell>
  )
}
