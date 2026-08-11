import type { ITerminalOptions } from '@xterm/xterm'
import { macOSTerminalTheme } from './terminalTheme'

export const defaultTerminalConfig: ITerminalOptions = {
  scrollback: 1000,
  fontFamily: '"SF Mono", Menlo, Monaco, "Courier New", monospace',
  fontSize: 13,
  fontWeight: 400,
  lineHeight: 1.2,
  letterSpacing: 0,
  cursorBlink: true,
  cursorStyle: 'block',
  theme: macOSTerminalTheme,
  allowTransparency: false,
  convertEol: true,
}
