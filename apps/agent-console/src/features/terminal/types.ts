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
  sizes: number[]
  verticalSizes: number[]
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
