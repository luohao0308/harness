import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { XtermTerminal } from '../XtermTerminal'

// Create mock instances
const mockTerminalInstance = {
  loadAddon: vi.fn(),
  open: vi.fn(),
  write: vi.fn(),
  writeln: vi.fn(),
  clear: vi.fn(),
  onData: vi.fn(),
  dispose: vi.fn(),
}

const mockFitAddonInstance = {
  fit: vi.fn(),
}

// Mock xterm.js completely to avoid canvas/DOM dependencies
vi.mock('@xterm/xterm', () => ({
  Terminal: vi.fn(() => mockTerminalInstance),
}))

vi.mock('@xterm/addon-fit', () => ({
  FitAddon: vi.fn(() => mockFitAddonInstance),
}))

vi.mock('@xterm/addon-web-links', () => ({
  WebLinksAddon: vi.fn(() => ({})),
}))

// Mock the CSS import to prevent module resolution errors
vi.mock('@xterm/xterm/css/xterm.css', () => ({}))

describe('XtermTerminal', () => {
  const mockOnData = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.clearAllTimers()
  })

  it('renders terminal container', () => {
    render(<XtermTerminal id="test-terminal" />)
    const container = screen.getByTestId('xterm-container')
    expect(container).toBeInTheDocument()
  })

  it('initializes xterm.js terminal on mount', async () => {
    const { Terminal } = await import('@xterm/xterm')
    render(<XtermTerminal id="test-terminal" onData={mockOnData} />)

    await waitFor(() => {
      expect(Terminal).toHaveBeenCalled()
      expect(mockTerminalInstance.open).toHaveBeenCalled()
      expect(mockTerminalInstance.loadAddon).toHaveBeenCalledTimes(2)
      expect(mockFitAddonInstance.fit).toHaveBeenCalled()
    })
  })

  it('registers onData callback', async () => {
    render(<XtermTerminal id="test-terminal" onData={mockOnData} />)

    await waitFor(() => {
      expect(mockTerminalInstance.onData).toHaveBeenCalledWith(mockOnData)
    })
  })

  it('writes welcome message on mount', async () => {
    render(<XtermTerminal id="test-terminal" />)

    await waitFor(() => {
      expect(mockTerminalInstance.writeln).toHaveBeenCalledWith('Welcome to Terminal')
      expect(mockTerminalInstance.writeln).toHaveBeenCalledWith('Type a command to get started')
      expect(mockTerminalInstance.write).toHaveBeenCalledWith('$ ')
    })
  })

  it('exposes write method via ref', async () => {
    const ref = { current: null as any }
    render(<XtermTerminal ref={ref} id="test-terminal" />)

    await waitFor(() => {
      expect(ref.current).not.toBeNull()
      expect(ref.current.write).toBeDefined()
    })

    ref.current.write('test data')
    expect(mockTerminalInstance.write).toHaveBeenCalledWith('test data')
  })

  it('exposes clear method via ref', async () => {
    const ref = { current: null as any }
    render(<XtermTerminal ref={ref} id="test-terminal" />)

    await waitFor(() => {
      expect(ref.current).not.toBeNull()
      expect(ref.current.clear).toBeDefined()
    })

    ref.current.clear()
    expect(mockTerminalInstance.clear).toHaveBeenCalled()
  })

  it('exposes fit method via ref', async () => {
    const ref = { current: null as any }
    render(<XtermTerminal ref={ref} id="test-terminal" />)

    await waitFor(() => {
      expect(ref.current).not.toBeNull()
      expect(ref.current.fit).toBeDefined()
    })

    ref.current.fit()
    expect(mockFitAddonInstance.fit).toHaveBeenCalled()
  })

  it('disposes terminal on unmount', async () => {
    const { unmount } = render(<XtermTerminal id="test-terminal" />)

    await waitFor(() => {
      expect(mockTerminalInstance.open).toHaveBeenCalled()
    })

    unmount()
    expect(mockTerminalInstance.dispose).toHaveBeenCalled()
  })

  it('sets up ResizeObserver for auto-fitting', async () => {
    const mockObserve = vi.fn()
    const mockDisconnect = vi.fn()

    global.ResizeObserver = vi.fn(() => ({
      observe: mockObserve,
      disconnect: mockDisconnect,
      unobserve: vi.fn(),
    })) as any

    const { unmount } = render(<XtermTerminal id="test-terminal" />)

    await waitFor(() => {
      expect(mockObserve).toHaveBeenCalled()
    })

    unmount()
    expect(mockDisconnect).toHaveBeenCalled()
  })
})
