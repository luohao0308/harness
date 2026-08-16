import { app } from 'electron'

export interface WindowConfig {
  width: number
  height: number
  minWidth: number
  minHeight: number
}

export interface AppConfig {
  devServerUrl: string
  isDev: boolean
  openDevTools: boolean
  window: WindowConfig
}

const DEFAULT_WINDOW_CONFIG: WindowConfig = {
  width: 1280,
  height: 800,
  minWidth: 1024,
  minHeight: 768
}

export function getAppConfig(): AppConfig {
  const usePackagedRenderer = process.env.HARNESS_DESKTOP_USE_PACKAGED_RENDERER === '1'
  const isDev = !app.isPackaged && !usePackagedRenderer

  return {
    devServerUrl: process.env.VITE_DEV_SERVER_URL || 'http://localhost:5173',
    isDev,
    openDevTools: process.env.HARNESS_DESKTOP_OPEN_DEVTOOLS === '1',
    window: DEFAULT_WINDOW_CONFIG
  }
}
