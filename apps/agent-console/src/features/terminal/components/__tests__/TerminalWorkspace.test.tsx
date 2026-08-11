import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'
import { TerminalWorkspace } from '../TerminalWorkspace'
import { useTerminalStore } from '../../../../stores/terminalStore'

vi.mock('../../../../stores/terminalStore')
vi.mock('../../../../app/ConsoleShell', () => ({
  ConsoleShell: ({ children }: { children: ReactNode }) => children,
}))
vi.mock('../TerminalPane', () => ({
  TerminalPane: ({ id }: { id: string }) => <div data-testid={`terminal-pane-${id}`}>{id}</div>,
}))
vi.mock('../hooks/useTerminalKeyboardNav', () => ({
  useTerminalKeyboardNav: () => {},
}))

// Mock react-resizable-panels
vi.mock('react-resizable-panels', () => ({
  Panel: ({ children, id }: any) => <div data-testid={`panel-${id}`}>{children}</div>,
  Group: ({ children, onLayoutChange, orientation }: any) => (
    <div data-testid={`group-${orientation || 'unknown'}`}>
      <button
        data-testid={`layout-${orientation || 'unknown'}`}
        type="button"
        onClick={() => onLayoutChange?.(orientation === 'vertical' ? [62, 38] : [40, 30, 30])}
      />
      {children}
    </div>
  ),
  Separator: () => <div data-testid="separator" />,
}))

function renderWorkspace() {
  return render(
    <MemoryRouter initialEntries={['/terminal']}>
      <TerminalWorkspace />
    </MemoryRouter>
  )
}

describe('TerminalWorkspace', () => {
  const mockCreateTerminal = vi.fn()
  const mockSetLayout = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    window.desktopApi = undefined
    vi.mocked(useTerminalStore).mockImplementation((selector: any) =>
      selector({
        terminals: {},
        layout: {
          direction: 'horizontal',
          sizes: [33.334, 33.333, 33.333],
          verticalSizes: [50, 50],
          collapsed: {},
        },
        activeTerminalId: null,
        createTerminal: mockCreateTerminal,
        setLayout: mockSetLayout,
      })
    )
  })

  it('renders without crashing', () => {
    renderWorkspace()
    expect(screen.getByRole('region', { name: 'Terminal workspace' })).toBeInTheDocument()
    expect(screen.getByTestId('terminal-pane-term-1')).toBeInTheDocument()
    expect(screen.getByTestId('terminal-pane-term-2')).toBeInTheDocument()
    expect(screen.getByTestId('terminal-pane-term-3')).toBeInTheDocument()
    expect(screen.getByTestId('terminal-pane-term-4')).toBeInTheDocument()
  })

  it('creates all 4 terminals on mount', () => {
    renderWorkspace()
    expect(mockCreateTerminal).toHaveBeenCalledWith('term-1')
    expect(mockCreateTerminal).toHaveBeenCalledWith('term-2')
    expect(mockCreateTerminal).toHaveBeenCalledWith('term-3')
    expect(mockCreateTerminal).toHaveBeenCalledWith('term-4')
  })

  it('uses one terminal session in the desktop operation shell', () => {
    window.desktopApi = {}

    renderWorkspace()

    expect(screen.getByTestId('terminal-pane-term-1')).toBeInTheDocument()
    expect(screen.queryByTestId('terminal-pane-term-2')).not.toBeInTheDocument()
    expect(mockCreateTerminal).toHaveBeenCalledTimes(1)
    expect(mockCreateTerminal).toHaveBeenCalledWith('term-1')
  })

  it('does not create terminals that already exist', () => {
    vi.mocked(useTerminalStore).mockImplementation((selector: any) =>
      selector({
        terminals: {
          'term-1': { id: 'term-1', title: 'Terminal 1', active: true },
          'term-2': { id: 'term-2', title: 'Terminal 2', active: true },
        },
        layout: {
          direction: 'horizontal',
          sizes: [33.334, 33.333, 33.333],
          verticalSizes: [50, 50],
          collapsed: {},
        },
        activeTerminalId: null,
        createTerminal: mockCreateTerminal,
        setLayout: mockSetLayout,
      })
    )

    renderWorkspace()
    expect(mockCreateTerminal).not.toHaveBeenCalledWith('term-1')
    expect(mockCreateTerminal).not.toHaveBeenCalledWith('term-2')
    expect(mockCreateTerminal).toHaveBeenCalledWith('term-3')
    expect(mockCreateTerminal).toHaveBeenCalledWith('term-4')
  })

  it('persists horizontal and vertical panel layouts separately', () => {
    renderWorkspace()

    screen.getByTestId('layout-horizontal').click()
    expect(mockSetLayout).toHaveBeenLastCalledWith({
      direction: 'horizontal',
      sizes: [40, 30, 30],
      verticalSizes: [50, 50],
      collapsed: {},
    })

    screen.getByTestId('layout-vertical').click()
    expect(mockSetLayout).toHaveBeenLastCalledWith({
      direction: 'horizontal',
      sizes: [33.334, 33.333, 33.333],
      verticalSizes: [62, 38],
      collapsed: {},
    })
  })
})
