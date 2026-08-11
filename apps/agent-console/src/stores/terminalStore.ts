import { create } from 'zustand'
import type { TerminalState, TerminalLayout } from '../features/terminal/types'

interface TerminalStore {
  terminals: Record<string, TerminalState>
  layout: TerminalLayout
  activeTerminalId: string | null

  createTerminal: (id: string) => void
  removeTerminal: (id: string) => void
  updateTerminal: (id: string, updates: Partial<TerminalState>) => void
  setLayout: (layout: TerminalLayout) => void
  setActiveTerminal: (id: string) => void
}

const STORAGE_KEY = 'terminal-layout'
const DEFAULT_LAYOUT: TerminalLayout = {
  direction: 'horizontal',
  sizes: [33.334, 33.333, 33.333],
  verticalSizes: [50, 50],
  collapsed: {},
}

function terminalTitle(id: string): string {
  const suffix = id.match(/\d+$/)?.[0]
  return suffix ? `Terminal ${suffix}` : `Terminal ${id}`
}

function normalizeLayout(layout: Partial<TerminalLayout> | null): TerminalLayout {
  return {
    direction: layout?.direction ?? DEFAULT_LAYOUT.direction,
    sizes: layout?.sizes?.length ? layout.sizes : DEFAULT_LAYOUT.sizes,
    verticalSizes: layout?.verticalSizes?.length
      ? layout.verticalSizes
      : DEFAULT_LAYOUT.verticalSizes,
    collapsed: layout?.collapsed ?? DEFAULT_LAYOUT.collapsed,
  }
}

function loadLayoutFromStorage(): TerminalLayout {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      return normalizeLayout(JSON.parse(stored))
    }
  } catch (error) {
    console.error('Failed to load terminal layout from localStorage:', error)
  }
  return DEFAULT_LAYOUT
}

function saveLayoutToStorage(layout: TerminalLayout): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(layout))
  } catch (error) {
    console.error('Failed to save terminal layout to localStorage:', error)
  }
}

export const useTerminalStore = create<TerminalStore>((set) => ({
  terminals: {},
  layout: loadLayoutFromStorage(),
  activeTerminalId: null,

  createTerminal: (id) =>
    set((state) => {
      if (state.terminals[id]) {
        return state
      }

      return {
        terminals: {
          ...state.terminals,
          [id]: {
            id,
            title: terminalTitle(id),
            cwd: '~',
            shell: 'zsh',
            history: [],
            scrollback: [],
            active: true,
          },
        },
      }
    }),

  removeTerminal: (id) =>
    set((state) => {
      const { [id]: removed, ...rest } = state.terminals
      return { terminals: rest }
    }),

  updateTerminal: (id, updates) =>
    set((state) => ({
      terminals: {
        ...state.terminals,
        [id]: { ...state.terminals[id]!, ...updates },
      },
    })),

  setLayout: (layout) =>
    set(() => {
      saveLayoutToStorage(layout)
      return { layout }
    }),
  setActiveTerminal: (id) => set({ activeTerminalId: id }),
}))
