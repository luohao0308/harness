# Phase 1 Implementation Plan: Multi-Terminal Architecture with Drag-Split Layouts

> Status: implemented. The checklists below are retained as verified acceptance evidence; active gaps are tracked only in `docs/TASKS.md`.

## Executive Summary

The agent-console implements a four-terminal split-pane system with independent sessions, persisted layout, keyboard focus, and macOS-oriented presentation. This document records the implemented Phase 1 architecture and its verified acceptance checklist.

---

## 1. Component Architecture

### 1.1 Terminal Stack Selection

**Primary Terminal Emulator: xterm.js**
- Industry standard, battle-tested
- Excellent performance (handles 4 concurrent instances)
- Rich addon ecosystem (fit, web-links, search)
- Bundle impact: ~300KB (acceptable for Phase 1, optimize in Phase 3)

**Dependencies to add:**
```json
{
  "@xterm/xterm": "^5.5.0",
  "@xterm/addon-fit": "^0.10.0",
  "@xterm/addon-web-links": "^0.11.0"
}
```

### 1.2 Split Layout Library Selection

**Selected: react-resizable-panels**
- Modern, declarative API
- Built-in drag handles
- Performant resize operations
- Small bundle (~15KB)
- Integrates well with React 18

### 1.3 Component Hierarchy

```
TerminalWorkspace (new top-level page)
├── TerminalLayoutProvider (state management)
├── PanelGroup (horizontal split)
│   ├── Panel (left-top)
│   │   └── TerminalPane
│   │       └── XtermTerminal
│   ├── PanelResizeHandle
│   ├── Panel (right container - vertical split)
│   │   ├── Panel (right-top)
│   │   │   └── TerminalPane
│   │   │       └── XtermTerminal
│   │   ├── PanelResizeHandle
│   │   └── Panel (right-bottom)
│   │       └── TerminalPane
│   │           └── XtermTerminal
│   └── Panel (optional 4th terminal)
```

---

## 2. Drag-Split Implementation Approach

### 2.1 react-resizable-panels Integration

```typescript
// Drag handles come built-in with declarative API
<PanelGroup direction="horizontal">
  <Panel defaultSize={50} minSize={20}>
    <TerminalPane id="term-1" />
  </Panel>
  <PanelResizeHandle /> {/* Drag handle - automatic */}
  <Panel defaultSize={50}>
    <TerminalPane id="term-2" />
  </Panel>
</PanelGroup>
```

### 2.2 Handle Styling (macOS Aesthetic)

```typescript
// Custom handle with macOS-inspired design
function TerminalResizeHandle({ direction }: { direction: 'horizontal' | 'vertical' }) {
  return (
    <PanelResizeHandle
      className={cn(
        "group relative bg-slate-100 transition-colors hover:bg-slate-200",
        direction === "horizontal" ? "w-1" : "h-1"
      )}
    >
      <div className={cn(
        "absolute inset-0 flex items-center justify-center",
        "opacity-0 group-hover:opacity-100 transition-opacity"
      )}>
        <div className={cn(
          "bg-slate-400 rounded-full",
          direction === "horizontal" ? "w-1 h-8" : "w-8 h-1"
        )} />
      </div>
    </PanelResizeHandle>
  )
}
```

### 2.3 Layout Persistence

```typescript
// Save layout to localStorage
const [layout, setLayout] = useState<number[]>(() => {
  const saved = localStorage.getItem('terminal-layout')
  return saved ? JSON.parse(saved) : [25, 25, 25, 25]
})

useEffect(() => {
  localStorage.setItem('terminal-layout', JSON.stringify(layout))
}, [layout])
```

---

## 3. Performance Considerations for 4 Concurrent Terminals

### 3.1 Terminal Instance Management

**Key optimizations:**

1. **Lazy Rendering**: Only render visible terminals
2. **Shared WebGL Renderer**: xterm.js can share renderer across instances
3. **Output Buffering**: Limit scrollback buffer (default 1000 lines, configurable)
4. **Debounced Resize**: Throttle terminal.fit() during drag operations

```typescript
// Terminal instance with performance optimizations
function XtermTerminal({ id }: { id: string }) {
  const terminalRef = useRef<Terminal | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const terminal = new Terminal({
      scrollback: 1000, // Limit scrollback
      rows: 24,
      cols: 80,
      fontFamily: '"SF Mono", Menlo, monospace', // macOS fonts
      fontSize: 13,
      theme: {
        background: '#FFFFFF',
        foreground: '#1E2227',
        cursor: '#3C5A78',
        // macOS-inspired theme colors
      },
      rendererType: 'canvas', // Better performance than DOM
      allowTransparency: false,
    })

    terminal.open(containerRef.current!)
    terminalRef.current = terminal

    return () => terminal.dispose()
  }, [id])

  // Debounced resize
  const handleResize = useMemo(
    () => debounce(() => {
      if (!terminalRef.current) return
      const fitAddon = new FitAddon()
      terminalRef.current.loadAddon(fitAddon)
      fitAddon.fit()
    }, 100),
    []
  )

  return <div ref={containerRef} className="h-full w-full" />
}
```

### 3.2 Memory Management

```typescript
// Terminal state management with cleanup
interface TerminalState {
  id: string
  history: string[] // Command history (max 100)
  scrollback: string[] // Output buffer (max 1000 lines)
  cwd: string
}

const MAX_HISTORY_SIZE = 100
const MAX_SCROLLBACK_SIZE = 1000

function pruneTerminalState(state: TerminalState): TerminalState {
  return {
    ...state,
    history: state.history.slice(-MAX_HISTORY_SIZE),
    scrollback: state.scrollback.slice(-MAX_SCROLLBACK_SIZE),
  }
}
```

---

## 4. File Structure and Key Interfaces

### 4.1 New File Structure

```
apps/agent-console/src/features/terminal/
├── components/
│   ├── TerminalWorkspace.tsx          # Main workspace page
│   ├── TerminalLayoutProvider.tsx     # State management
│   ├── TerminalPane.tsx               # Individual pane wrapper
│   ├── XtermTerminal.tsx              # xterm.js integration
│   ├── TerminalResizeHandle.tsx       # Custom drag handle
│   ├── TerminalToolbar.tsx            # Per-pane controls
│   └── TerminalTabs.tsx               # Tab switcher (future)
├── hooks/
│   ├── useTerminalInstance.ts         # Terminal lifecycle
│   ├── useTerminalLayout.ts           # Layout persistence
│   ├── useTerminalShell.ts            # Shell I/O (WebSocket/SSE)
│   └── useTerminalResize.ts           # Debounced resize
├── lib/
│   ├── terminalTheme.ts               # macOS color scheme
│   ├── terminalConfig.ts              # xterm.js config
│   └── shellCommands.ts               # Command parsing
├── types.ts                            # TypeScript interfaces
└── __tests__/
    ├── TerminalWorkspace.test.tsx
    └── XtermTerminal.test.tsx
```

### 4.2 Key TypeScript Interfaces

```typescript
// types.ts

export interface TerminalState {
  id: string
  title: string
  cwd: string
  shell: 'bash' | 'zsh' | 'fish'
  history: string[]
  scrollback: string[]
  active: boolean
  pid?: number
}

export interface TerminalLayout {
  direction: 'horizontal' | 'vertical'
  sizes: number[] // Percentage splits
  collapsed: Record<string, boolean>
}

export interface TerminalTheme {
  background: string
  foreground: string
  cursor: string
  selection: string
  black: string
  red: string
  green: string
  yellow: string
  blue: string
  magenta: string
  cyan: string
  white: string
  brightBlack: string
  brightRed: string
  brightGreen: string
  brightYellow: string
  brightBlue: string
  brightMagenta: string
  brightCyan: string
  brightWhite: string
}

export interface TerminalAction {
  type: 'write' | 'clear' | 'resize' | 'kill'
  terminalId: string
  payload?: unknown
}

export interface ShellMessage {
  type: 'output' | 'exit' | 'error'
  terminalId: string
  data: string
  timestamp: number
}
```

---

## 5. Integration Points with Existing Codebase

### 5.1 Routing Integration

```typescript
// apps/agent-console/src/app/routes.tsx

import { TerminalWorkspace } from '../features/terminal/components/TerminalWorkspace'

const routes = [
  // ... existing routes
  {
    path: '/terminal',
    element: <TerminalWorkspace />,
  },
]
```

### 5.2 Navigation Integration

```typescript
// apps/agent-console/src/app/consoleNav.ts

export const consoleNavEntries: ConsoleNavEntry[] = [
  // ... existing entries
  {
    to: '/terminal',
    label: '终端',
    iconKey: 'terminal', // Need to add terminal icon
  },
]
```

### 5.3 State Management Integration

**Using Zustand Store:**
```typescript
// apps/agent-console/src/stores/terminalStore.ts

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

export const useTerminalStore = create<TerminalStore>((set) => ({
  terminals: {},
  layout: { direction: 'horizontal', sizes: [25, 25, 25, 25], collapsed: {} },
  activeTerminalId: null,

  createTerminal: (id) => set((state) => ({
    terminals: {
      ...state.terminals,
      [id]: {
        id,
        title: `Terminal ${Object.keys(state.terminals).length + 1}`,
        cwd: '~',
        shell: 'zsh',
        history: [],
        scrollback: [],
        active: true,
      },
    },
  })),

  removeTerminal: (id) => set((state) => {
    const { [id]: removed, ...rest } = state.terminals
    return { terminals: rest }
  }),

  updateTerminal: (id, updates) => set((state) => ({
    terminals: {
      ...state.terminals,
      [id]: { ...state.terminals[id]!, ...updates },
    },
  })),

  setLayout: (layout) => set({ layout }),
  setActiveTerminal: (id) => set({ activeTerminalId: id }),
}))
```

### 5.4 Backend Integration

**WebSocket for Shell I/O:**

```typescript
// features/terminal/hooks/useTerminalShell.ts

export function useTerminalShell(terminalId: string) {
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    // Connect to backend shell service
    const ws = new WebSocket(`ws://localhost:8080/api/terminal/${terminalId}`)

    ws.onopen = () => setConnected(true)
    ws.onmessage = (event) => {
      const message: ShellMessage = JSON.parse(event.data)
      // Handle shell output
    }
    ws.onerror = () => setConnected(false)
    ws.onclose = () => setConnected(false)

    wsRef.current = ws

    return () => ws.close()
  }, [terminalId])

  const writeToShell = useCallback((data: string) => {
    if (!wsRef.current || !connected) return
    wsRef.current.send(JSON.stringify({ type: 'input', data }))
  }, [connected])

  return { connected, writeToShell }
}
```

**Backend Endpoint Requirements:**
- `POST /api/terminal` - Create new shell session
- `WS /api/terminal/:id` - Bidirectional shell I/O
- `DELETE /api/terminal/:id` - Terminate shell session

---

## 6. Verification Strategy for Phase 1 Checkpoint

### 6.1 Functional Verification Checklist

**Core Functionality:**
- [x] 4 terminals render simultaneously without crashes
- [x] Each terminal has independent xterm.js instance
- [x] Drag handles allow smooth resizing in both directions
- [x] Layout persists across page reloads
- [x] Each terminal maintains independent command history
- [x] Each terminal maintains independent output buffer
- [x] Each terminal has independent scroll position

**Performance Metrics:**
- [x] Page load time: <2s (with 4 terminals)
- [x] Drag resize: <16ms frame time (60fps)
- [x] Terminal output: Handles 1000 lines/sec without lag
- [x] Memory usage: <200MB total for 4 terminals
- [x] Bundle size: <10MB (will optimize in Phase 3)

**UI/UX:**
- [x] macOS-style aesthetics match design system
- [x] Drag handles visible on hover
- [x] Active terminal visually distinguished
- [x] Minimum panel size enforced (prevents collapse)
- [x] Keyboard navigation between panes (Cmd+1/2/3/4)

### 6.2 Manual Testing Script

```markdown
# Phase 1 Manual Verification Script

## Setup
1. Start dev server: `npm run dev`
2. Open http://127.0.0.1:5175/terminal
3. Open Chrome DevTools (Performance tab)

## Test Cases

### TC1: Four Terminals Render
- [x] All 4 terminal panes visible
- [x] Each shows unique terminal prompt
- [x] No console errors

### TC2: Independent State
- [x] Type command in Terminal 1
- [x] Verify output only in Terminal 1
- [x] Repeat for Terminals 2, 3, 4
- [x] Verify histories are separate

### TC3: Drag Resize (Horizontal)
- [x] Hover over vertical divider
- [x] Drag left/right
- [x] Terminals resize smoothly
- [x] No flickering or lag

### TC4: Drag Resize (Vertical)
- [x] Hover over horizontal divider
- [x] Drag up/down
- [x] Terminals resize smoothly
- [x] Text reflows correctly

### TC5: Layout Persistence
- [x] Resize panels to custom layout
- [x] Refresh page (Cmd+R)
- [x] Verify layout restored exactly

### TC6: Performance Under Load
- [x] Run `yes` command in all 4 terminals
- [x] Observe CPU usage (<50%)
- [x] Observe memory usage (<200MB)
- [x] Stop commands (Ctrl+C)
- [x] Verify UI still responsive

### TC7: Minimum Size Constraints
- [x] Try to collapse panel completely
- [x] Verify minimum size enforced (20%)
- [x] No terminal content cut off

### TC8: Keyboard Navigation
- [x] Press Cmd+1 → Focus Terminal 1
- [x] Press Cmd+2 → Focus Terminal 2
- [x] Press Cmd+3 → Focus Terminal 3
- [x] Press Cmd+4 → Focus Terminal 4

### TC9: Scroll Independence
- [x] Generate 50 lines in Terminal 1
- [x] Scroll to top of Terminal 1
- [x] Verify other terminals unchanged

### TC10: macOS Aesthetics
- [x] Verify SF Mono font rendering
- [x] Verify color scheme matches design
- [x] Verify drag handles look native
- [x] Verify no visual glitches
```

---

## 7. Implementation Timeline

**Estimated effort: 3-5 days**

| Day | Tasks | Deliverables |
|-----|-------|--------------|
| 1 | Setup dependencies, file structure, basic xterm.js integration | Single terminal rendering |
| 2 | Implement 4-pane layout with react-resizable-panels | Static 4-terminal layout |
| 3 | Add drag-resize, layout persistence, state management | Fully interactive layout |
| 4 | Performance optimization, testing, macOS styling | All tests passing |
| 5 | Manual verification, bug fixes, documentation | Phase 1 complete |

---

## 8. Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| xterm.js bundle too large | High | Lazy load terminal feature, code-split |
| 4 terminals cause lag | High | Implement output throttling, virtual scrollback |
| Drag resize janky | Medium | Use requestAnimationFrame, debounce fit() |
| Backend shell service missing | High | Mock WebSocket in frontend for Phase 1 |
| Layout state corruption | Low | Validate localStorage, provide reset button |

---

## 9. Success Criteria

**Phase 1 is complete when:**

1. ✅ User can open 4 terminals simultaneously
2. ✅ Each terminal operates independently (history, output, scroll)
3. ✅ Drag handles resize panels smoothly (60fps)
4. ✅ Layout persists across sessions
5. ✅ No performance degradation with 4 active terminals
6. ✅ macOS-style aesthetics match design system
7. ✅ All automated tests pass
8. ✅ Manual verification checklist 100% complete
9. ✅ Bundle size documented (baseline for Phase 3 optimization)
10. ✅ Zero crashes or console errors

**Proceed to Phase 3 only after all criteria met.**
